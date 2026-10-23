"""Launch one approved source search through its original controller and owners.

The caller supplies the trusted raw launch hash. Passive checks precede key
entry; fingerprints, account assertions and configuration checks grant no money.
"""

import hashlib
import math
import sqlite3
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from buddha import (
    credentials,
    gateway,
    source_handoff,
    source_launch_state,
    source_screen,
    source_search,
)
from buddha import launch_common as common
from buddha import native_pipeline as pipeline
from buddha.authorization import Authorization
from buddha.doctor import _Busy, _Unsupported
from buddha.gateway import RawHTTPTransport
from buddha.provider import ModelSpec
from buddha.releases import (
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _root,
    _text,
    file_hash,
)


class SourceLaunchError(ReleaseError):
    """A fixed launch failure; input and exception contents are not CLI reasons."""


def _entrypoint() -> Path:
    return Path(__file__).absolute().parent.parent / "docs/conformance/src02-run.py"


def _sources() -> list[Path]:
    return list(
        dict.fromkeys(
            [
                *source_handoff._sources(),
                Path(__file__).absolute(),
                Path(source_launch_state.__file__).absolute(),
                Path(common.__file__).absolute(),
                Path(credentials.__file__).absolute(),
                _entrypoint(),
            ]
        )
    )


def _path(value: object) -> Path:
    return common._path(value, error=SourceLaunchError)


def _rows(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        raise SourceLaunchError("expected recorded funding rows")
    return [_object(row) for row in value]


def _specs(
    screen: source_screen.SourceScreen, template: dict[str, object]
) -> dict[str, list[ModelSpec]]:
    record = screen.to_record()
    generation, native = _object(record["generation"]), _object(record["native"])
    selected = {
        name: gateway._profiles(
            Selection.from_bytes(_json(section["selection"])), source_screen._roots(section)
        )
        for name, section in (("generation", generation), ("native", native))
    }

    def choice(section: dict[str, object]) -> ModelSpec:
        role = _object(section["profile"])
        choices = _object(
            _object(selected["generation"][cast(str, role["capability"])])["profiles"]
        )
        return gateway._spec(_object(choices[cast(str, role["profile_id"])])["spec"])

    result = {"generation": [choice(generation)], "proposal": [choice(template)], "native": []}
    for provider, models in _object(native["profiles"]).items():
        capability = next(
            key for key, value in gateway.CAPABILITIES.items() if value[0] == provider
        )
        choices = _object(_object(selected["native"][capability])["profiles"])
        for profile_id in _object(models).values():
            spec = gateway._spec(_object(choices[_text(profile_id)])["spec"])
            if spec not in result["native"]:
                result["native"].append(spec)
    return result


def _planned_owners(
    directory: Path,
    seed: source_screen.SourceScreen,
    iterations: int,
    *,
    mutation_witness: bool = False,
) -> set[Path]:
    if type(mutation_witness) is not bool:
        raise SourceLaunchError("mutation witness must be an explicit boolean")
    screens = [directory / "seed"] + [
        directory / "iterations" / str(i) / "screen" for i in range(iterations)
    ]
    stages = len(cast(list[object], seed.to_record()["stages"]))
    owners = {
        screen / "tasks" / str(i) / role / "owners" / str(j)
        for screen in screens
        for i in range(len(seed.tasks.tasks))
        for role, ordinals in (("generation", range(1)), ("evaluation", range(1, stages + 1)))
        for j in ordinals
    } | {directory / "iterations" / str(i) / "proposal/owners/0" for i in range(iterations)}
    if mutation_witness:
        witnesses = [directory / "seed-witness"] + [
            directory / "iterations" / str(i) / "witness" for i in range(iterations)
        ]
        owners |= {
            witness / role / "owners/0"
            for witness in witnesses
            for role in ("proposal", "generation")
        }
    return owners


def check_launch(path: Path, *, expected_sha256: str) -> dict[str, object]:
    """Read controls and original funding/state without keys, writable SQL or execution."""
    try:
        if not isinstance(path, Path):
            raise SourceLaunchError("launch needs an explicit Path")
        path, expected_sha256 = _path(str(path.absolute())), _digest(expected_sha256)
        raw = pipeline._read(path, expected_sha256)
        record = _object(
            _load(raw),
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
        if _text(record["format"]) != "buddha.source-launch.v1":
            raise SourceLaunchError("unsupported funded source launch")
        timeout = record["timeout_seconds"]
        if type(timeout) not in (int, float):
            raise SourceLaunchError("transport timeout must be finite within 600 seconds")
        timeout = cast(int | float, timeout)
        if not math.isfinite(timeout) or not 0 < timeout <= 600:
            raise SourceLaunchError("transport timeout must be finite within 600 seconds")
        bindings: dict[str, str] = {str(path): expected_sha256}

        def reference(value: object) -> tuple[Path, dict[str, object]]:
            item = _object(value, {"path", "sha256"})
            source, digest = _path(item["path"]), _digest(item["sha256"])
            if str(source) in bindings and bindings[str(source)] != digest:
                raise SourceLaunchError("conflicting launch references")
            data = pipeline._read(source, digest)
            bindings[str(source)] = digest
            return source, _load(data)

        proposal_path, proposal = reference(record["proposal"])
        checked = source_handoff.check_source_handoff(
            proposal_path, expected_sha256=bindings[str(proposal_path)]
        )
        mutation_witness = source_handoff._mutation_witness(proposal)
        source_copy = source_handoff._source_copy(proposal)
        for name, digest in _object(checked["reviewed_bindings"]).items():
            expected = _digest(digest)
            if name in bindings and bindings[name] != expected:
                raise SourceLaunchError("reviewed controls conflict with launch identity")
            bindings[name] = expected
        _, approval = reference(record["approval"])
        directory, review_path = _path(record["directory"]), _path(record["review"])
        _root(directory.parent)
        _root(review_path.parent)
        if directory.is_symlink():
            raise SourceLaunchError("search output is a link")
        authority = _object(approval["authorization"], {"path", "id", "terms_sha256", "scope"})
        authority_path = _path(authority["path"])
        funding, authority_raw = common._snapshot(authority_path)
        config, totals = _object(funding["config"]), _object(funding["totals"])
        expected_authority = {
            "path": str(authority_path),
            "id": config["authorization_id"],
            "terms_sha256": config["terms_sha256"],
            "scope": _object(checked["funding"])["scope"],
        }
        expected_approval = {
            "format": "buddha.source-approval.v1",
            "proposal_sha256": bindings[str(proposal_path)],
            "comparison_key": checked["comparison_key"],
            "directory": str(directory),
            "review": str(review_path),
            "authorization": expected_authority,
            **{key: config[key] for key in ("budget_microusd", "max_calls")},
            "account_scope": _text(approval["account_scope"]),
        }
        if (
            _json(authority) != _json(expected_authority)
            or config["scope"] != expected_authority["scope"]
            or _json(approval) != _json(expected_approval)
            or any(
                config[key] != _object(checked["requested_terms"])[key]
                for key in ("budget_microusd", "max_calls")
            )
        ):
            raise SourceLaunchError("approval or actual immutable funding differs")
        pins = _object(record["source_sha256"])
        if not 1 <= len(pins) <= 1024:
            raise SourceLaunchError("launch source inventory exceeds its ceiling")
        seen: set[Path] = set()
        for name, digest in pins.items():
            source, expected = _path(name), _digest(digest)
            if (
                source in seen
                or source == path
                or (name in bindings and bindings[name] != expected)
            ):
                raise SourceLaunchError("source pins have aliases, self-reference or conflicts")
            seen.add(source)
            bindings[name] = expected
        if any(str(source) not in pins for source in _sources()):
            raise SourceLaunchError("required launch source is not reviewed")
        seed = source_screen.SourceScreen.from_bytes(_json(proposal["seed_screen"]))
        template = source_search._template(proposal["proposal_template"])
        spec = source_search.SourceSearchSpec.from_bytes(_json(proposal["spec"]))
        roots = [
            _path(value)
            for role in ("generation", "native")
            for value in _object(_object(seed.to_record()[role])["roots"]).values()
        ]
        protected = [authority_path, *(Path(name) for name in bindings), *roots]
        if any(directory.is_relative_to(p) or p.is_relative_to(directory) for p in protected):
            raise SourceLaunchError(
                "search output overlaps original controls, components or funding"
            )
        if review_path.is_relative_to(directory) or any(
            review_path.is_relative_to(p) for p in protected
        ):
            raise SourceLaunchError(
                "review overlaps search, selected components or original controls"
            )
        planned = _planned_owners(
            directory,
            seed,
            cast(int, spec.to_record()["iterations"]),
            mutation_witness=mutation_witness,
        )
        runs, operations = _rows(funding["auth_runs"]), _rows(funding["auth_operations"])
        if any(_path(row["directory"]) not in planned for row in runs):
            raise SourceLaunchError("dedicated allocation contains another destination or owner")
        # Exact initial generation invocation projection. Later proposal/native
        # highwater needs the concrete full-schedule rehearsal before funding.
        initial_paths = {Path(name) for name in bindings} | {
            review_path,
            directory / "manifest.json",
            directory / "context.json",
            directory / "seed/screen.json",
            directory / "seed/context.json",
            directory / "seed/tasks/0/task.json",
            directory / "seed/tasks/0/generation.json",
            directory / "seed/tasks/0/generation/context.json",
        }
        if len(initial_paths) > 1024:
            raise SourceLaunchError("initial owner exceeds the existing invocation input boundary")
        profiles = _specs(seed, template)
        providers = {spec.provider for choices in profiles.values() for spec in choices}
        review: dict[str, object] | None = None
        retained: dict[str, object] = {
            "state": "fresh",
            "busy": False,
            "inactive_pending": False,
            "next_owner": str(directory / "seed/tasks/0/generation/owners/0"),
            "next_role": "generation",
            "state_sha256": hashlib.sha256(authority_raw).hexdigest(),
        }
        if directory.exists():
            review_raw = pipeline._read(review_path)
            review = gateway._review(_load(review_raw))
            if (
                review.get("format") != "buddha.account-review.v2"
                or review["credential_context"] != expected_sha256
                or review["account_scope"] != approval["account_scope"]
                or set(_object(review["credential_fingerprints"])) != providers
            ):
                raise SourceLaunchError("original keyed review differs from approved launch")
            bindings[str(review_path)] = hashlib.sha256(review_raw).hexdigest()
            retained = source_launch_state.inspect_prepared_search(
                directory,
                authority_path,
                seed_screen=seed,
                proposal_template=template,
                spec=spec,
                review=review,
                expected_runtime_sha256=_digest(proposal["expected_runtime_sha256"]),
                input_bindings={Path(name): digest for name, digest in bindings.items()},
                mutation_witness=mutation_witness,
                source_copy=source_copy,
            )
        elif review_path.exists() or review_path.is_symlink() or runs or totals["operation_count"]:
            raise SourceLaunchError("partial preparation or retained work cannot be replaced")
        stop = "busy" if retained["busy"] else "inactive" if retained["inactive_pending"] else None
        if retained["state"] != "complete" and stop is None:
            if any(row["status"] == "unknown" for row in operations):
                stop = "unknown"
            elif any(row["status"] == "dispatched" for row in operations):
                stop = "dispatched"
            elif any(
                row["actual_microusd"] is not None
                and cast(int, row["actual_microusd"]) > cast(int, row["reserve_microusd"])
                for row in operations
            ):
                stop = "overrun"
            elif review is not None:
                try:
                    gateway._review(review, fresh=True)
                except ValueError:
                    stop = "review_expired"
            role, next_owner = retained["next_role"], retained["next_owner"]
            paying = (
                role in {"generation", "proposal"}
                or role == "native"
                and next_owner is not None
                and _object(
                    cast(list[object], seed.to_record()["stages"])[
                        int(Path(cast(str, next_owner)).name) - 1
                    ]
                )["allow_model"]
                is True
            )
            if stop is None and paying:
                choices = profiles[cast(str, role)]
                reserve = max(choice.reserve_microusd() for choice in choices)
                own = next((row["run_id"] for row in runs if row["directory"] == next_owner), None)
                owned = [row for row in operations if row["run_id"] == own]
                reusable = any(
                    row["status"] == "reserved" and cast(int, row["reserve_microusd"]) >= reserve
                    for row in owned
                )
                replay = any(row["status"] == "completed" for row in owned)
                local = _object(
                    template
                    if role == "proposal"
                    else seed.to_record()["generation" if role == "generation" else "native"]
                )
                if (
                    not reusable
                    and not replay
                    and (
                        cast(int, config["max_calls"]) <= cast(int, totals["operation_count"])
                        or cast(int, config["budget_microusd"])
                        - cast(int, totals["committed_microusd"])
                        < reserve
                        or cast(int, local["budget_microusd"]) < reserve
                    )
                ):
                    stop = "capacity"
        # The final checks follow all component/state reads, including extra pins.
        source_screen._configuration(seed, _digest(proposal["expected_runtime_sha256"]))
        source_screen._configuration(
            source_search._template_screen(seed, template),
            _digest(proposal["expected_runtime_sha256"]),
        )
        for name, digest in bindings.items():
            if file_hash(Path(name), max_bytes=256 * 1024**2) != digest:
                raise SourceLaunchError("approved launch control changed during checking")
        common._finish_snapshot(authority_path, authority_raw, error=SourceLaunchError)
        result = {
            "format": "buddha.source-launch-check.v1",
            "state": retained["state"],
            "stop_code": stop,
            "directory": str(directory),
            "review_path": str(review_path),
            "review": review,
            "authorization_path": str(authority_path),
            "account_scope": approval["account_scope"],
            "bindings": bindings,
            "profiles": {
                name: [asdict(value) for value in choices] for name, choices in profiles.items()
            },
            "funding": config | totals,
            "state_sha256": retained["state_sha256"],
            "next_owner": retained["next_owner"],
            "timeout_seconds": timeout,
            "protected_roots": [
                str(directory),
                str(review_path),
                str(authority_path),
                *bindings,
                *(str(root) for root in roots),
            ],
            "initial_invocation_control_count": len(initial_paths),
            "proposal": proposal,
            "claim": "passive identity/funding checks; "
            "no account authentication or completion-cost guarantee",
        }
        if mutation_witness and retained.get("reason") == "no_parent_eligible":
            result["reason"] = "no_parent_eligible"
        return result
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
        StopIteration,
        OverflowError,
        sqlite3.Error,
        _Busy,
        _Unsupported,
    ):
        raise SourceLaunchError(
            "approved source checks failed; original records retained"
        ) from None


def _notice(message: str) -> None:
    common._notice("source", message)


class _Profiles:
    def __init__(self, profiles: list[ModelSpec]):
        self._profiles = profiles

    def profiles(self) -> list[ModelSpec]:
        return self._profiles


def _public_result(result: dict[str, object]) -> dict[str, object]:
    if result.get("status") == "complete":
        return (
            {"status": "complete", "reason": "no_parent_eligible"}
            if result.get("reason") == "no_parent_eligible"
            else {"status": "complete"}
        )
    from buddha.releases import _path as relative_path

    observation = relative_path(result["observation"])
    if (
        result.get("status") != "incomplete"
        or not observation.startswith("observations/")
        or result["reason"]
        not in {
            "unknown",
            "authority",
            "protocol",
            "cancelled",
            "native_error",
            "agent_error",
            "seed_ineligible",
            "feedback_capacity",
            "owner_prefix",
            "quota",
        }
    ):
        raise SourceLaunchError("controller returned no supported saved stop")
    return {
        "status": "incomplete",
        "reason": result["reason"],
        "observation": observation,
        "iteration": result["iteration"],
        "stage": result["stage"],
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
) -> dict[str, object]:
    """Check, enter reviewed keys once, recheck, then run the original controller."""
    if (
        any(type(value) is not bool for value in (live, prompt_keys, confirm_project_keys))
        or type(heartbeat_seconds) not in (int, float)
        or not 0 < heartbeat_seconds <= 60
        or not callable(notice)
        or transport is not None
        and not isinstance(transport, RawHTTPTransport)
    ):
        raise SourceLaunchError("invalid launch options")
    requested = None if receipt is None else common._receipt_path(receipt, error=SourceLaunchError)
    output = None
    phase, progress_authority = ["checking"], cast(list[Path | None], [None])
    public: dict[str, object] = {"format": "buddha.source-launch-receipt.v1"}
    try:
        common._emit(
            notice, "Checking approved configuration and original saved state; no keys read yet."
        )
        with common._heartbeat(
            notice, phase, progress_authority, heartbeat_seconds, thread_name="source-progress"
        ):
            if requested is not None:
                exclusions = common._receipt_roots(path, expected_sha256)
                if any(requested.is_relative_to(root) for root in exclusions):
                    raise SourceLaunchError("receipt overlaps declared original controls or output")
                output = requested
            checked = check_launch(path, expected_sha256=expected_sha256)
            progress_authority[0] = _path(checked["authorization_path"])
            if output is not None and any(
                output.is_relative_to(_path(root))
                for root in cast(list[object], checked["protected_roots"])
            ):
                output = None
                raise SourceLaunchError("receipt overlaps original controls or output")
            if checked["state"] == "complete" and checked["stop_code"] is None:
                public.update(status="complete", phase="complete")
                if checked.get("reason") == "no_parent_eligible":
                    public["reason"] = "no_parent_eligible"
                return public
            if checked["stop_code"] is not None:
                public.update(status="stopped", phase="funding", reason=checked["stop_code"])
                return public
            if not live or not confirm_project_keys:
                raise SourceLaunchError(
                    "live execution and manual account confirmation are required"
                )
            if transport is not None and (
                not transport.allow_paid or transport.timeout_seconds != checked["timeout_seconds"]
            ):
                raise SourceLaunchError("transport differs from the declared launch timeout")
            specs = [
                gateway._spec(value)
                for choices in _object(checked["profiles"]).values()
                for value in cast(list[object], choices)
            ]
            phase[0] = "keys"
            with credentials.key_environment(
                _Profiles(specs),
                prompt_keys=prompt_keys,
                notice=lambda text: common._emit(notice, text),
            ):
                fingerprints = gateway.credential_fingerprints(
                    list(dict.fromkeys(spec.provider for spec in specs)), context=expected_sha256
                )
                review = cast(dict[str, object] | None, checked["review"])
                if review is not None and _json(review["credential_fingerprints"]) != _json(
                    fingerprints
                ):
                    raise SourceLaunchError("credential differs from original reviewed binding")
                phase[0] = "rechecking"
                repeated = check_launch(path, expected_sha256=expected_sha256)
                if (
                    any(
                        _json(repeated[name]) != _json(checked[name])
                        for name in ("bindings", "state", "state_sha256", "funding")
                    )
                    or repeated["stop_code"] is not None
                ):
                    raise SourceLaunchError("saved state changed during key entry")
                authority = Authorization(_path(checked["authorization_path"]))
                if checked["state"] == "fresh":
                    review = {
                        "format": "buddha.account-review.v2",
                        "checked_on": datetime.now(UTC).date().isoformat(),
                        "credential_context": expected_sha256,
                        "credential_fingerprints": fingerprints,
                        "account_scope": checked["account_scope"],
                    }
                    review_raw = _json(gateway._review(review, fresh=True))
                    review_path = _path(checked["review_path"])
                    pipeline._write(review_path, review_raw)
                    pins = {
                        Path(name): _digest(value)
                        for name, value in _object(checked["bindings"]).items()
                    }
                    pins[review_path] = hashlib.sha256(review_raw).hexdigest()
                    proposal = _object(checked["proposal"])
                    mutation_witness = source_handoff._mutation_witness(proposal)
                    source_copy = source_handoff._source_copy(proposal)
                    phase[0] = "preparing"
                    source_search.prepare_source_search(
                        _path(checked["directory"]),
                        seed_screen=source_screen.SourceScreen.from_bytes(
                            _json(proposal["seed_screen"])
                        ),
                        proposal_template=_object(proposal["proposal_template"]),
                        spec=source_search.SourceSearchSpec.from_bytes(_json(proposal["spec"])),
                        authorization=authority,
                        review=review,
                        expected_runtime_sha256=_digest(proposal["expected_runtime_sha256"]),
                        input_bindings=pins,
                        mutation_witness=mutation_witness,
                        source_copy=source_copy,
                    )
                    source_launch_state.inspect_prepared_search(
                        _path(checked["directory"]),
                        authority.path,
                        seed_screen=source_screen.SourceScreen.from_bytes(
                            _json(proposal["seed_screen"])
                        ),
                        proposal_template=_object(proposal["proposal_template"]),
                        spec=source_search.SourceSearchSpec.from_bytes(_json(proposal["spec"])),
                        review=review,
                        expected_runtime_sha256=_digest(proposal["expected_runtime_sha256"]),
                        input_bindings=pins,
                        mutation_witness=mutation_witness,
                        source_copy=source_copy,
                    )
                phase[0] = "executing"
                common._emit(
                    notice,
                    "Starting the original source search; "
                    "recorded attempts may include unsent requests.",
                )
                result = source_search.run_source_search(
                    _path(checked["directory"]),
                    transport=transport
                    or RawHTTPTransport(
                        allow_paid=True, timeout_seconds=cast(float, checked["timeout_seconds"])
                    ),
                )
                public.update(_public_result(result), phase="finished")
                return public
    except source_search.SourceSearchInterrupted as error:
        public.update(_public_result(error.partial), status="cancelled", phase=phase[0])
        raise
    except source_search.SourceSearchStopped as error:
        public.update(_public_result(error.partial), phase=phase[0])
        return public
    except KeyboardInterrupt:
        public.update(status="cancelled", phase=phase[0], reason="cancelled")
        raise
    except Exception as error:
        code = error.code if isinstance(error, credentials.KeyInputError) else "launch_stopped"
        public.update(status="stopped", phase=phase[0], reason=code)
        if isinstance(error, credentials.KeyInputError):
            raise
        raise SourceLaunchError("source launch stopped; original records retained") from None
    finally:
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
