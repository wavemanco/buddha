"""Run a caller-pinned matched trial through its original controllers and grants."""

import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from buddha import (
    credentials,
    gateway,
    improver_handoff,
    improver_launch_state,
    improver_study,
    trial_fence,
    validation_study,
)
from buddha import final_evaluation as final
from buddha import improver_assessment as assessment
from buddha import launch_common as common
from buddha import native_pipeline as pipeline
from buddha.authorization import Authorization
from buddha.doctor import _Busy, _Unsupported
from buddha.gateway import RawHTTPTransport
from buddha.provider import ModelSpec
from buddha.releases import ReleaseError, _digest, _json, _load, _object, _root, _text, file_hash

_PHASES = ("search", "validation", "final")
_AMOUNTS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")


class ImproverLaunchError(ReleaseError):
    """A fixed launch refusal; untrusted inputs never become public reasons."""


def _entrypoint() -> Path:
    return Path(__file__).absolute().parent.parent / "docs/conformance/imp01-run.py"


def _sources() -> list[Path]:
    return sorted(
        {
            *improver_handoff._sources(),
            Path(__file__).absolute(),
            Path(improver_launch_state.__file__).absolute(),
            Path(credentials.__file__).absolute(),
            _entrypoint(),
        }
    )


def _path(value: object) -> Path:
    return common._path(value, error=ImproverLaunchError)


def _absent(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    return False


def _funding(paths: dict[str, Path]) -> dict[str, Any]:
    phases, captures = {}, {}
    for phase, path in paths.items():
        observed, raw = common._snapshot(path)
        phases[phase] = _object(observed["config"]) | _object(observed["totals"])
        captures[path] = raw
    for path, raw in captures.items():
        common._finish_snapshot(path, raw, error=ImproverLaunchError)
    return {
        "phases": phases,
        "totals": {name: sum(value[name] for value in phases.values()) for name in _AMOUNTS},
    }


def _profiles(state: dict[str, Any]) -> list[ModelSpec]:
    result: list[ModelSpec] = []
    for screen in state["screens"]:
        record = screen.to_record()
        choices = common._model_specs(
            _object(record["generation"]),
            _object(record["native"]),
            _object(state["development"]["proposal_template"]),
        )
        result.extend(spec for members in choices.values() for spec in members)
    choices = common._model_specs(
        _object(state["record"]["generation"]), _object(state["record"]["native"])
    )
    result.extend(spec for members in choices.values() for spec in members)
    return list(dict.fromkeys(result))


def _capacity(state: dict[str, Any], root: Path, bindings: dict[Path, str]) -> None:
    controls = dict(state["controls"])
    improver_study._bind_controls(controls, bindings)
    prospective = assessment._prospective_controls(state, root)
    improver_study._bind_controls(prospective, controls)
    validation_study._capacity(
        state,
        {"directory": str(root / "final"), "controls": {str(p): d for p, d in prospective.items()}},
        receipts={root / "freeze" / name: "0" * 64 for name in ("schedule.json", "ready.json")},
    )
    assessment._development_capacity(state, root, controls)


def check_launch(path: Path, *, expected_sha256: str) -> dict[str, object]:
    """Check original configuration/funding/state without keys, writers or workers."""
    try:
        if not isinstance(path, Path):
            raise ImproverLaunchError("launch needs an explicit Path")
        path, expected = _path(str(path.absolute())), _digest(expected_sha256)
        record = _object(
            _load(pipeline._read(path, expected)),
            {
                "format",
                "proposal",
                "approval",
                "directory",
                "review",
                "source_sha256",
                "timeout_seconds",
            },
        )
        if record["format"] != "buddha.improver-launch.v1":
            raise ImproverLaunchError("unsupported matched launch")
        timeout = record["timeout_seconds"]
        if type(timeout) not in (int, float):
            raise ImproverLaunchError("transport timeout must be finite within 600 seconds")
        timeout = cast(int | float, timeout)
        if not 0 < timeout <= 600:
            raise ImproverLaunchError("transport timeout must be finite within 600 seconds")
        bindings: dict[Path, str] = {path: expected}

        def reference(value: object) -> tuple[Path, dict[str, object]]:
            item = _object(value, {"path", "sha256"})
            source, digest = _path(item["path"]), _digest(item["sha256"])
            improver_study._bind_controls(bindings, {source: digest})
            return source, _load(pipeline._read(source, digest))

        proposal_path, proposal = reference(record["proposal"])
        _, approval = reference(record["approval"])
        directory, review_path = _path(record["directory"]), _path(record["review"])
        _root(directory.parent)
        _root(review_path.parent)
        fresh = _absent(directory)
        if fresh:
            improver_handoff.check_improver_handoff(
                proposal_path, expected_sha256=bindings[proposal_path]
            )
        state = improver_handoff._configuration(proposal_path, bindings[proposal_path], fresh=False)
        if state["directory"] != directory:
            raise ImproverLaunchError("launch replaces its reviewed destination")
        for pins, self_path in (
            (_object(proposal["source_sha256"]), proposal_path),
            (_object(record["source_sha256"]), path),
        ):
            if not 1 <= len(pins) <= 1024:
                raise ImproverLaunchError("source inventory exceeds its boundary")
            for name, digest in pins.items():
                source = _path(name)
                if source == self_path:
                    raise ImproverLaunchError("source inventory references itself")
                improver_study._bind_controls(bindings, {source: _digest(digest)})
        required_sources = common._historical_sources(
            {str(source): file_hash(source) for source in _sources()}
        )
        if any(
            _object(record["source_sha256"]).get(source) != pin
            for source, pin in required_sources.items()
        ):
            raise ImproverLaunchError("installed launch helper is not reviewed")
        declaration = state["declaration"]
        improver_study._bind_controls(bindings, {declaration: state["declared_sha256"]})
        identity = pipeline._sha(state["definition"])
        approved = _object(approval["authorizations"], set(_PHASES))
        paths, phases, snapshots = {}, {}, {}
        for phase in _PHASES:
            grant = _object(
                approved[phase],
                {"path", "id", "terms_sha256", "scope", "budget_microusd", "max_calls"},
            )
            grant_path = _path(grant["path"])
            observed, raw = common._snapshot(grant_path)
            config, totals = _object(observed["config"]), _object(observed["totals"])
            scope = trial_fence._scope_text(
                trial_fence._TrialScope(
                    directory, identity, phase, version=final._version(state["record"])
                )
            )
            expected_grant = {
                "path": str(grant_path),
                "id": config["authorization_id"],
                "terms_sha256": config["terms_sha256"],
                "scope": scope,
                **state["record"]["phase_limits"][phase],
            }
            if (
                _json(grant) != _json(expected_grant)
                or config["scope"] != scope
                or any(
                    config[key] != value
                    for key, value in state["record"]["phase_limits"][phase].items()
                )
                or grant_path in bindings
                or grant_path in state["controls"]
            ):
                raise ImproverLaunchError(
                    "approved phase grant differs from the original definition"
                )
            if fresh and any(
                observed[key]
                for key in (
                    "auth_runs",
                    "auth_operations",
                    "auth_acceptances",
                    "auth_deactivations",
                )
            ):
                raise ImproverLaunchError("missing trial cannot replace used phase funding")
            paths[phase], phases[phase], snapshots[grant_path] = grant_path, config | totals, raw
        if (
            len(set(paths.values())) != 3
            or len({value["authorization_id"] for value in phases.values()}) != 3
        ):
            raise ImproverLaunchError("phase grants must be distinct originals")
        expected_approval = {
            "format": "buddha.improver-approval.v1",
            "proposal_sha256": bindings[proposal_path],
            "definition_sha256": identity,
            "directory": str(directory),
            "review": str(review_path),
            "account_scope": _text(approval["account_scope"]),
            "authorizations": approved,
        }
        if _json(approval) != _json(expected_approval):
            raise ImproverLaunchError("approval differs from the exact reviewed launch")
        protected = {
            *bindings,
            *state["controls"],
            *state["protected"],
            *paths.values(),
            *(
                Path(value)
                for role in ("generation", "native")
                for value in state["record"][role]["roots"].values()
            ),
        }
        if any(directory.is_relative_to(p) or p.is_relative_to(directory) for p in protected):
            raise ImproverLaunchError("trial overlaps original inputs or funding")
        if (
            review_path.is_relative_to(directory)
            or directory.is_relative_to(review_path)
            or any(
                review_path.is_relative_to(p) or p.is_relative_to(review_path) for p in protected
            )
        ):
            raise ImproverLaunchError(
                "review overlaps original inputs, components, funding or trial"
            )
        profiles = _profiles(state)
        providers = {spec.provider for spec in profiles}
        review: dict[str, object] | None = None
        retained: dict[str, Any] = {
            "state": "fresh",
            "phase": "search",
            "blocked_reasons": [],
            "next_position": {"stage": "preparation"},
            "state_sha256": pipeline._sha(
                {str(p): hashlib.sha256(raw).hexdigest() for p, raw in snapshots.items()}
            ),
        }
        if fresh:
            if not _absent(review_path):
                raise ImproverLaunchError("partial review cannot be replaced")
            _capacity(state, directory, bindings | {review_path: "0" * 64})
        else:
            review_raw = pipeline._read(review_path)
            review = gateway._review(_load(review_raw))
            if (
                review.get("format") != "buddha.account-review.v2"
                or review["credential_context"] != expected
                or review["account_scope"] != approval["account_scope"]
                or set(_object(review["credential_fingerprints"])) != providers
            ):
                raise ImproverLaunchError("original keyed review differs from approved launch")
            bindings[review_path] = hashlib.sha256(review_raw).hexdigest()
            retained = improver_launch_state.inspect_prepared_improver_trial(
                directory,
                declaration=declaration,
                expected_sha256=state["declared_sha256"],
                expected_runtime_sha256=state["runtime"],
                authorizations=paths,
                development_review=review,
                input_bindings=bindings,
            )
            if retained["phase"] in {"final", "complete"}:
                schedule = _load(pipeline._read(directory / "freeze/schedule.json"))
                if schedule["review"] != review:
                    raise ImproverLaunchError("final freeze replaces the reviewed account binding")
        reasons = retained["blocked_reasons"]
        stop = reasons[0] if reasons else None
        if retained["state"] != "complete" and review is not None and stop is None:
            try:
                gateway._review(review, fresh=True)
            except ValueError:
                stop = "review_expired"
        if retained["state"] == "fresh":
            improver_handoff._components(state, state["runtime"])
        controls = dict(state["controls"])
        improver_study._bind_controls(controls, bindings)
        for source, digest in controls.items():
            if fresh or source not in state["retirable_producers"] or source in bindings:
                if file_hash(source, max_bytes=256 * 1024**2) != digest:
                    raise ImproverLaunchError("approved launch input changed during checking")
        for grant_path, raw in snapshots.items():
            common._finish_snapshot(grant_path, raw, error=ImproverLaunchError)
        if fresh:
            improver_handoff._destination(directory)
            if not _absent(review_path):
                raise ImproverLaunchError("review appeared during checking")
        return _load(
            _json(
                {
                    "format": "buddha.improver-launch-check.v1",
                    "state": retained["state"],
                    "phase": retained["phase"],
                    "stop_code": stop,
                    "directory": str(directory),
                    "review_path": str(review_path),
                    "review": review,
                    "bindings": {str(p): d for p, d in bindings.items()},
                    "authorizations": {phase: str(p) for phase, p in paths.items()},
                    "funding": {
                        "phases": phases,
                        "totals": {
                            name: sum(p[name] for p in phases.values()) for name in _AMOUNTS
                        },
                    },
                    "profiles": [asdict(spec) for spec in profiles],
                    "state_sha256": retained["state_sha256"],
                    "next_position": retained["next_position"],
                    "timeout_seconds": timeout,
                    "protected_roots": [
                        str(p) for p in sorted(protected | {directory, review_path})
                    ],
                    "proposal": proposal,
                    "definition_sha256": identity,
                    "account_scope": approval["account_scope"],
                    "claim": "Original configuration/funding observation; "
                    "no account authentication or completion-cost guarantee.",
                }
            )
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
        OverflowError,
        StopIteration,
        sqlite3.Error,
        _Busy,
        _Unsupported,
    ):
        raise ImproverLaunchError(
            "approved matched checks failed; original records retained"
        ) from None


class _Profiles:
    def __init__(self, values: list[ModelSpec]):
        self.values = values

    def profiles(self) -> list[ModelSpec]:
        return self.values


def _notice(message: str) -> None:
    common._notice("improver", message)


def _saved_partial(
    directory: Path,
    phase: str,
    paths: dict[str, Path],
    expected: dict[str, Any] | None = None,
) -> dict[str, object]:
    if phase == "search":
        reader, state = improver_study._restore(directory / "search/study", paths["search"])
        history = state["observations"]
        prefix = "search/study/"
    else:
        state, schedule, pins = assessment._restore_grid(directory, active=False)
        reader, current = final._census(state, schedule, pins)
        history = final._partials(state, schedule, reader, current)
        state["development_capture"].finish()
        prefix = "final/"
    if not history or history[-1]["status"] != "incomplete":
        raise ImproverLaunchError("controller has no verified original partial")
    result = history[-1]
    if expected is not None and _json(result) != _json(expected):
        raise ImproverLaunchError("controller result differs from its saved original partial")
    reader.capture.finish()
    return {name: result[name] for name in ("status", "reason", "position", "coverage")} | {
        "observation": prefix + "observations/" + str(len(history) - 1) + ".json"
    }


def launch(
    path: Path,
    *,
    expected_sha256: str,
    live: bool = False,
    prompt_keys: bool = False,
    confirm_project_keys: bool = False,
    receipt: Path | None = None,
    transport: RawHTTPTransport | None = None,
    notice: Callable[[str], None] = _notice,
    heartbeat_seconds: float = 10,
    on_incomplete: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    """Check, enter keys once, recheck, then use original phase controllers.

    An optional incomplete observer receives a fresh inline metadata projection
    before saved-partial verification; it cannot change the canonical result.
    """
    if (
        any(type(v) is not bool for v in (live, prompt_keys, confirm_project_keys))
        or type(heartbeat_seconds) not in (int, float)
        or not 0 < heartbeat_seconds <= 60
        or not callable(notice)
        or on_incomplete is not None
        and not callable(on_incomplete)
        or transport is not None
        and not isinstance(transport, RawHTTPTransport)
    ):
        raise ImproverLaunchError("invalid matched launch options")
    requested = (
        None if receipt is None else common._receipt_path(receipt, error=ImproverLaunchError)
    )
    output = None
    phase, current_grant = ["checking"], cast(list[Path | None], [None])
    paths: dict[str, Path] = {}
    public: dict[str, object] = {"format": "buddha.improver-launch-receipt.v1"}

    def observe_incomplete(result: dict[str, object], stage: str) -> None:
        if on_incomplete is not None:
            try:
                on_incomplete(common._result_diagnostic(result, phase=stage))
            except (Exception, KeyboardInterrupt):
                pass  # Observers cannot change the controller result or its normal saved partial.

    try:
        common._emit(
            notice, "Checking approved matched configuration and original state; no keys read yet."
        )
        with common._heartbeat(
            notice, phase, current_grant, heartbeat_seconds, thread_name="improver-progress"
        ):
            if requested is not None:
                roots = common._receipt_roots(path, expected_sha256)
                if any(requested.is_relative_to(root) for root in roots):
                    raise ImproverLaunchError("receipt overlaps original controls or output")
                output = requested
            checked = check_launch(path, expected_sha256=expected_sha256)
            paths = {name: _path(p) for name, p in _object(checked["authorizations"]).items()}
            public["funding"] = checked["funding"]
            if output is not None and any(
                output.is_relative_to(_path(root))
                for root in cast(list[object], checked["protected_roots"])
            ):
                output = None
                raise ImproverLaunchError("receipt overlaps original controls or output")
            phase[0] = cast(str, checked["phase"])
            current_grant[0] = paths["search" if phase[0] == "search" else "final"]
            if checked["state"] == "complete" and checked["stop_code"] is None:
                public.update(status="complete", phase="complete")
                return public
            if checked["stop_code"] is not None:
                public.update(
                    status="stopped",
                    phase=phase[0],
                    reason=checked["stop_code"],
                    position=checked["next_position"],
                )
                return public
            if not live or not confirm_project_keys:
                raise ImproverLaunchError(
                    "live execution and manual account confirmation are required"
                )
            if transport is not None and (
                not transport.allow_paid or transport.timeout_seconds != checked["timeout_seconds"]
            ):
                raise ImproverLaunchError("transport differs from declared launch options")
            specs = [gateway._spec(p) for p in cast(list[object], checked["profiles"])]
            phase[0] = "keys"
            with credentials.key_environment(
                _Profiles(specs),
                prompt_keys=prompt_keys,
                notice=lambda text: common._emit(notice, text),
            ):
                fingerprints = gateway.credential_fingerprints(
                    list(dict.fromkeys(p.provider for p in specs)), context=expected_sha256
                )
                review = cast(dict[str, object] | None, checked["review"])
                if review is not None and review["credential_fingerprints"] != fingerprints:
                    raise ImproverLaunchError("credential differs from original reviewed binding")
                phase[0] = "rechecking"
                repeated = check_launch(path, expected_sha256=expected_sha256)
                if repeated["stop_code"] is not None or any(
                    _json(repeated[k]) != _json(checked[k])
                    for k in ("bindings", "state", "phase", "state_sha256", "funding")
                ):
                    raise ImproverLaunchError("original saved state changed during key entry")
                authorities = {name: Authorization(p) for name, p in paths.items()}
                proposal = _object(checked["proposal"])
                if checked["state"] == "fresh":
                    review = gateway._review(
                        {
                            "format": "buddha.account-review.v2",
                            "checked_on": datetime.now(UTC).date().isoformat(),
                            "credential_context": expected_sha256,
                            "credential_fingerprints": fingerprints,
                            "account_scope": checked["account_scope"],
                        },
                        fresh=True,
                    )
                    review_path = _path(checked["review_path"])
                    review_raw = _json(review)
                    pipeline._write(review_path, review_raw)
                    pins = {Path(p): _digest(d) for p, d in _object(checked["bindings"]).items()}
                    pins[review_path] = hashlib.sha256(review_raw).hexdigest()
                    reference = _object(proposal["assessment"])
                    phase[0] = "preparing"
                    assessment.prepare_improver_assessment_trial(
                        _path(checked["directory"]),
                        declaration=_path(reference["path"]),
                        expected_sha256=_digest(reference["sha256"]),
                        expected_runtime_sha256=_digest(proposal["expected_runtime_sha256"]),
                        authorizations=authorities,
                        development_review=review,
                        input_bindings=pins,
                    )
                if review is None:
                    raise ImproverLaunchError("original matched review is unavailable")
                directory = _path(checked["directory"])
                active_transport = transport or RawHTTPTransport(
                    allow_paid=True, timeout_seconds=cast(float, checked["timeout_seconds"])
                )
                if checked["phase"] == "search":
                    phase[0], current_grant[0] = "search", paths["search"]
                    common._emit(
                        notice,
                        "Starting original matched development; "
                        "progress accounting is for the active phase only.",
                    )
                    developed = improver_study.run_improver_study(
                        directory / "search/study", transport=active_transport
                    )
                    if developed["status"] != "complete":
                        observe_incomplete(developed, "search")
                        public.update(
                            _saved_partial(directory, "search", paths, developed), phase="search"
                        )
                        return public
                phase[0], current_grant[0] = "freeze", paths["final"]
                assessment.freeze_improver_descendants(
                    directory,
                    expected_development_report_sha256=file_hash(
                        directory / "search/study/report.json"
                    ),
                    review=review,
                )
                phase[0] = "final"
                common._emit(
                    notice,
                    "Starting original sealed final assessment; "
                    "final results stay outside improvement feedback.",
                )
                result = assessment.run_improver_assessment(
                    directory,
                    authorization=authorities["final"],
                    review=review,
                    transport=active_transport,
                )
                if result["status"] == "complete":
                    public.update(status="complete", phase="complete")
                else:
                    observe_incomplete(result, "final")
                    public.update(_saved_partial(directory, "final", paths, result), phase="final")
                return public
    except KeyboardInterrupt:
        public.update(status="cancelled", phase=phase[0], reason="cancelled")
        if paths and phase[0] in {"search", "final"}:
            common._emit(notice, "Checking the saved cancellation; no new provider requests.")
            try:
                with common._heartbeat(notice, phase, current_grant, heartbeat_seconds):
                    observed = _saved_partial(_path(checked["directory"]), phase[0], paths)
                if observed["reason"] == "cancelled":
                    public.update(observed, status="cancelled", phase=phase[0])
                else:
                    public["observation_status"] = "unavailable"
            except Exception:
                public["observation_status"] = "unavailable"
        raise
    except Exception as error:
        reason = common._stop_reason(error)
        public.update(status="stopped", phase=phase[0], reason=reason)
        if isinstance(error, credentials.KeyInputError):
            raise
        raise ImproverLaunchError("matched launch stopped; original evidence retained") from None
    finally:
        if paths:
            try:
                public["funding"] = _funding(paths)
            except Exception:
                public["funding"] = {"status": "unavailable"}
        if requested is not None and output is None:
            public["receipt_saved"] = False
            common._emit(notice, "Launch receipt not saved: protected output checks did not pass.")
        if output is not None:
            public["receipt_saved"] = True
            try:
                pipeline._write(output, _json(public))
            except (OSError, ValueError):
                public["receipt_saved"] = False
                common._emit(
                    notice, "Launch receipt unavailable; original execution records remain."
                )
