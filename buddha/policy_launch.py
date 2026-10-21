"""Launch one caller-pinned, separately approved policy study.

Checks are passive. Only the existing prepare/run functions create owners or
dispatch requests. Reviewed hashes/manual approval do not authenticate accounts.
"""

import hashlib
import math
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from buddha import credentials, gateway, policy_handoff, policy_results, policy_run
from buddha import native_pipeline as pipeline
from buddha.authorization import Authorization
from buddha.gateway import RawHTTPTransport
from buddha.gateway_history import MAX_LEDGER_BYTES
from buddha.provider import ModelSpec
from buddha.releases import ReleaseError, _digest, _json, _load, _object, _root, _text, file_hash
from buddha.search_evidence import _read, _sidecars, read_authority


class PolicyLaunchError(ReleaseError):
    """A static launch failure; raw input/exception text is never a CLI reason."""


def _entrypoint() -> Path:
    return Path(__file__).absolute().parent.parent / "docs/conformance/pol02-run.py"


def _sources() -> list[Path]:
    # Explicit host closure supplements the existing configuration/core closure.
    package = Path(__file__).absolute().parent
    return list(
        dict.fromkeys(
            [
                *policy_handoff._sources(),
                _entrypoint(),
                Path(__file__).absolute(),
                *(
                    package / name
                    for name in (
                        "credentials.py",
                        "policy_results.py",
                        "doctor.py",
                        "search_evidence.py",
                        "gateway_history.py",
                        "history.py",
                        "policy_analysis.py",
                    )
                ),
            ]
        )
    )


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _path(value: object) -> Path:
    # Destinations/receipt leaves need not exist yet. Existing input reads and
    # output parents separately enforce the shared no-link filesystem guards.
    path = pipeline._absolute(value)
    if str(path) != value or ".." in path.parts or str(value).startswith(("//", "\\\\")):
        raise PolicyLaunchError("launch paths must have one canonical spelling")
    return path


def _snapshot(path: Path) -> tuple[dict[str, object], bytes]:
    _sidecars(path)
    raw = _read(path, MAX_LEDGER_BYTES)
    result = read_authority(raw)
    _sidecars(path)
    return result, raw


def _finish_snapshot(path: Path, raw: bytes) -> None:
    _sidecars(path)
    if _read(path, len(raw)) != raw:
        raise PolicyLaunchError("funding changed while checking")
    _sidecars(path)


def _rows(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        raise PolicyLaunchError("expected bounded recorded rows")
    return [_object(row) for row in value]


def _profiles(checked: dict[str, object]) -> list[ModelSpec]:
    profiles = _object(checked["profiles"])
    generation = _object(_object(profiles["generation"])["profile"])
    records = [generation] + [_object(row["profile"]) for row in _rows(profiles["native"])]
    return list(dict.fromkeys(gateway._spec(row["spec"]) for row in records))


def check_launch(path: Path, *, expected_sha256: str) -> dict[str, object]:
    """Inspect original controls/funding/state without keys, locks or writers.

    Passing capacity is conservative potential-dispatch capacity, not a promise
    that the remaining scientific schedule can finish within the allocation.
    """
    try:
        if not isinstance(path, Path):
            raise PolicyLaunchError("launch needs an explicit Path")
        path = _path(str(path.absolute()))
        raw = pipeline._read(path, _digest(expected_sha256))
        record = _object(
            _load(raw),
            {
                "format",
                "proposal",
                "execution",
                "approval",
                "directory",
                "review",
                "source_sha256",
                "timeout_seconds",
            },
        )
        if record["format"] != "buddha.policy-launch.v1":
            raise PolicyLaunchError("unsupported funded launch")
        timeout = record["timeout_seconds"]
        if type(timeout) not in (int, float):
            raise PolicyLaunchError("launch transport timeout must be finite within 600 seconds")
        timeout = cast(int | float, timeout)
        if not math.isfinite(timeout) or not 0 < timeout <= 600:
            raise PolicyLaunchError("launch transport timeout must be finite within 600 seconds")
        bindings: dict[str, str] = {str(path): expected_sha256}

        def reference(value: object) -> tuple[Path, dict[str, object]]:
            item = _object(value, {"path", "sha256"})
            source, digest = _path(item["path"]), _digest(item["sha256"])
            if str(source) in bindings and bindings[str(source)] != digest:
                raise PolicyLaunchError("conflicting launch references")
            data = pipeline._read(source, digest)
            bindings[str(source)] = digest
            return source, _load(data)

        proposal_path, proposal = reference(record["proposal"])
        checked = policy_handoff.check_handoff(
            proposal_path, expected_sha256=bindings[str(proposal_path)]
        )
        specs = _profiles(checked)
        for name, digest in _object(checked["reviewed_bindings"]).items():
            expected = _digest(digest)
            if name in bindings and bindings[name] != expected:
                raise PolicyLaunchError("reviewed controls conflict with launch identity")
            bindings[name] = expected
        descriptor, execution = reference(record["execution"])
        approval_path, approval = reference(record["approval"])
        if set(execution) != {"format", "study", "baseline", "authorization"} or (
            execution["format"] != "buddha.policy-execution.v1"
            or _json(execution["study"]) != _json(proposal["study"])
            or _json(execution["baseline"]) != _json(proposal["baseline"])
        ):
            raise PolicyLaunchError("funded execution changes the checked proposal")
        directory, review_path = _path(record["directory"]), _path(record["review"])
        _root(directory.parent)
        _root(review_path.parent)
        authority = _object(execution["authorization"], {"path", "id", "terms_sha256", "scope"})
        authority_path = _path(authority["path"])
        funding, authority_raw = _snapshot(authority_path)
        config, totals = _object(funding["config"]), _object(funding["totals"])
        expected_authority = {
            "path": str(authority_path),
            "id": config["authorization_id"],
            "terms_sha256": config["terms_sha256"],
            "scope": "policy study: " + _text(checked["study_sha256"]),
        }
        requested = _object(checked["funding"])
        expected_approval = {
            "format": "buddha.policy-approval.v1",
            "proposal_sha256": bindings[str(proposal_path)],
            "study_sha256": checked["study_sha256"],
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
            or any(config[key] != requested[key] for key in ("budget_microusd", "max_calls"))
        ):
            raise PolicyLaunchError("approval or actual immutable funding differs")
        pins = _object(record["source_sha256"])
        if len(pins) > 1024:
            raise PolicyLaunchError("launch source inventory exceeds its ceiling")
        for name, digest in pins.items():
            source = _path(name)
            expected = _digest(digest)
            if str(source) in bindings and bindings[str(source)] != expected:
                raise PolicyLaunchError("source pin conflicts with reviewed configuration")
            if file_hash(source, max_bytes=256 * 1024**2) != expected:
                raise PolicyLaunchError("launch source changed")
            bindings[str(source)] = expected
        if any(str(source) not in pins for source in _sources()):
            raise PolicyLaunchError("required launch source is not reviewed")
        if len(bindings) >= 1024:
            raise PolicyLaunchError("launch controls exceed preparation's input ceiling")
        definition = policy_run._configuration(execution["study"], execution["baseline"])
        roots = [
            _path(value)
            for role in ("generation", "native")
            for value in _object(_object(definition.template[role])["roots"]).values()
        ]
        for root in roots:
            if directory.is_relative_to(root) or root.is_relative_to(directory):
                raise PolicyLaunchError("study overlaps selected input components")
        if review_path.is_relative_to(directory) or any(
            review_path.is_relative_to(p) for p in roots
        ):
            raise PolicyLaunchError("review must be outside study and selected components")
        if any(Path(name).is_relative_to(directory) for name in bindings):
            raise PolicyLaunchError("immutable launch controls must be outside study output")
        schedule = definition.study.schedule()
        stages = _rows(definition.template["stages"])
        planned = {
            directory
            / "cells"
            / str(i)
            / ("baseline" if j == 0 else f"judgments/{j}")
            / "owners"
            / str(k)
            for i, cell in enumerate(schedule)
            for j in range(len(_rows(cell["judge_occasions"])))
            for k in range(0 if j == 0 else 1, len(stages) + 1)
        }
        if any(_path(row["directory"]) not in planned for row in _rows(funding["auth_runs"])):
            raise PolicyLaunchError("dedicated allocation contains another destination or owner")
        review: dict[str, object] | None = None
        next_owner: Path | None = directory / "cells/0/baseline/owners/0"
        state = "fresh"
        busy = False
        inactive_pending = False
        if directory.exists():
            review_raw = pipeline._read(review_path)
            review = gateway._review(_load(review_raw))
            if review["account_scope"] != approval["account_scope"]:
                raise PolicyLaunchError("original review changes approved account scope")
            if set(_object(review["credential_sha256"])) != {spec.provider for spec in specs}:
                raise PolicyLaunchError("original review does not cover the selected providers")
            bindings[str(review_path)] = _sha(review_raw)
            retained = policy_results.inspect_prepared_study(
                directory,
                authorization=authority_path,
                descriptor=descriptor,
                expected_inputs={Path(name): digest for name, digest in bindings.items()},
                review=review,
            )
            state = _text(retained["state"])
            busy = retained["busy"] is True
            inactive_pending = retained["inactive_pending"] is True
            next_owner = None if retained["next_owner"] is None else _path(retained["next_owner"])
        elif review_path.exists() or _rows(funding["auth_runs"]) or totals["operation_count"]:
            raise PolicyLaunchError("partial preparation or retained work cannot be replaced")
        stop: str | None = "busy" if busy else "inactive" if inactive_pending else None
        if state != "complete":
            operations = _rows(funding["auth_operations"])
            if stop is not None:
                pass
            elif any(row["status"] == "unknown" for row in operations):
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
            paying = next_owner is not None and (
                next_owner.name == "0" or stages[int(next_owner.name) - 1]["allow_model"] is True
            )
            if stop is None and next_owner is not None and paying:
                generation = next_owner.name == "0"
                selected = _object(definition.template["generation" if generation else "native"])
                reserve = (
                    specs[0].reserve_microusd()
                    if generation
                    else max(spec.reserve_microusd() for spec in specs)
                )
                own = next(
                    (
                        row["run_id"]
                        for row in _rows(funding["auth_runs"])
                        if row["directory"] == str(next_owner)
                    ),
                    None,
                )
                owned = [row for row in operations if row["run_id"] == own]
                reusable = any(
                    row["status"] == "reserved" and cast(int, row["reserve_microusd"]) >= reserve
                    for row in owned
                )
                # A completed prefix may replay before a new request. Passing this
                # conservative test is not a prediction of the next model/body.
                replay = any(row["status"] == "completed" for row in owned)
                if (
                    not reusable
                    and not replay
                    and (
                        cast(int, config["max_calls"]) <= cast(int, totals["operation_count"])
                        or cast(int, config["budget_microusd"])
                        - cast(int, totals["committed_microusd"])
                        < reserve
                        or cast(int, selected["budget_microusd"]) < reserve
                    )
                ):
                    stop = "capacity"
        for name, digest in bindings.items():
            if file_hash(Path(name), max_bytes=256 * 1024**2) != digest:
                raise PolicyLaunchError("an approved launch control changed during checking")
        for role in ("generation", "native"):
            pipeline._component(_object(definition.template[role]))
        if pipeline._read(path, expected_sha256) != raw:
            raise PolicyLaunchError("launch changed during checking")
        _finish_snapshot(authority_path, authority_raw)
        return {
            "format": "buddha.policy-launch-check.v1",
            "state": state,
            "stop_code": stop,
            "directory": str(directory),
            "descriptor": str(descriptor),
            "review_path": str(review_path),
            "review": review,
            "authorization_path": str(authority_path),
            "account_scope": approval["account_scope"],
            "bindings": bindings,
            "profiles": checked["profiles"],
            "funding": config | totals,
            "next_owner": None if next_owner is None else str(next_owner),
            "protected_roots": [str(directory), *(str(root) for root in roots)],
            "timeout_seconds": timeout,
            "claim": "passive checks; no account authentication or completion-cost guarantee",
        }
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        raise PolicyLaunchError(
            "approved launch checks failed; original records retained"
        ) from None


def _notice(message: str) -> None:
    print("[policy] " + message, file=sys.stderr, flush=True)


def _emit(notice: Callable[[str], None], message: str) -> None:
    try:
        notice(message)
    except Exception:
        # Console/callback failures must not alter paid execution or leak a
        # background traceback containing unrelated application data.
        return


@contextmanager
def _heartbeat(
    notice: Callable[[str], None], phase: list[str], authority: list[Path | None], seconds: float
) -> Iterator[None]:
    stop = threading.Event()
    started = time.monotonic()

    def accounting() -> str:
        if authority[0] is None:
            return "recorded accounting unknown"
        try:
            funding, raw = _snapshot(authority[0])
            _finish_snapshot(authority[0], raw)
            config, totals = _object(funding["config"]), _object(funding["totals"])
            return (
                f"recorded attempts {totals['operation_count']}; "
                f"recorded cost ${cast(int, totals['spent_microusd']) / 1_000_000:.6f}; "
                f"held ${cast(int, totals['reserved_microusd']) / 1_000_000:.6f}; "
                f"cap ${cast(int, config['budget_microusd']) / 1_000_000:.6f}"
            )
        except Exception:
            return "recorded accounting unavailable"

    def tick() -> None:
        while not stop.wait(seconds):
            if phase[0] != "keys":
                _emit(
                    notice,
                    f"Phase: {phase[0]}; elapsed {int(time.monotonic() - started)}s; "
                    + accounting(),
                )

    worker = threading.Thread(target=tick, name="policy-progress", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=0.5)


def _receipt_path(path: Path) -> Path:
    if not isinstance(path, Path):
        raise PolicyLaunchError("receipt needs an explicit new Path")
    result = _path(str(path.absolute()))
    _root(result.parent)
    if result.exists():
        raise PolicyLaunchError("receipt already exists; nothing overwritten")
    return result


def _key_fingerprints(
    profiles: list[ModelSpec], review: dict[str, object] | None
) -> dict[str, str]:
    result = {}
    for provider in dict.fromkeys(spec.provider for spec in profiles):
        value = os.environ.get(
            {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[provider]
        )
        if not value or len(value) > 4096 or any(not 33 <= ord(c) <= 126 for c in value):
            raise credentials.KeyInputError("key_input_invalid")
        result[provider] = _sha(value.encode("ascii"))
    if review is not None and _json(review["credential_sha256"]) != _json(result):
        raise PolicyLaunchError("credential differs from the original reviewed fingerprint")
    return result


class _Profiles:
    def __init__(self, profiles: list[ModelSpec]):
        self._profiles = profiles

    def profiles(self) -> list[ModelSpec]:
        return self._profiles


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
    """Check first, enter keys once, recheck, then use the original controller."""
    if (
        any(type(value) is not bool for value in (live, prompt_keys, confirm_project_keys))
        or type(heartbeat_seconds) not in (int, float)
        or not math.isfinite(heartbeat_seconds)
        or not 0 < heartbeat_seconds <= 60
        or not callable(notice)
        or transport is not None
        and not isinstance(transport, RawHTTPTransport)
    ):
        raise PolicyLaunchError("invalid launch options")
    output = None if receipt is None else _receipt_path(receipt)
    phase = ["checking"]
    progress_authority: list[Path | None] = [None]
    public: dict[str, object] = {"format": "buddha.policy-launch-receipt.v1"}
    try:
        _emit(notice, "Checking approved configuration and original saved state; no keys read yet.")
        with _heartbeat(notice, phase, progress_authority, heartbeat_seconds):
            checked = check_launch(path, expected_sha256=expected_sha256)
            if "authorization_path" in checked:
                progress_authority[0] = _path(checked["authorization_path"])
            if output is not None and any(
                output.is_relative_to(_path(root))
                for root in cast(list[object], checked["protected_roots"])
            ):
                output = None
                raise PolicyLaunchError("receipt overlaps study or selected input components")
            if checked["state"] == "complete" and checked["stop_code"] is None:
                public.update(status="complete", phase="complete")
                return public
            if not live or not confirm_project_keys:
                raise PolicyLaunchError(
                    "live execution and manual account confirmation are required"
                )
            if checked["stop_code"] is not None:
                public.update(status="stopped", phase="funding", reason=checked["stop_code"])
                return public
            if transport is not None and (
                not transport.allow_paid or transport.timeout_seconds != checked["timeout_seconds"]
            ):
                raise PolicyLaunchError("transport differs from the declared launch timeout")
            phase[0] = "keys"
            profiles = _profiles(checked)
            with credentials.key_environment(
                _Profiles(profiles),
                prompt_keys=prompt_keys,
                notice=lambda text: _emit(notice, text),
            ):
                fingerprints = _key_fingerprints(
                    profiles, cast(dict[str, object] | None, checked["review"])
                )
                phase[0] = "rechecking"
                repeated = check_launch(path, expected_sha256=expected_sha256)
                if (
                    _json(repeated["bindings"]) != _json(checked["bindings"])
                    or repeated["state"] != checked["state"]
                    or repeated["stop_code"] is not None
                ):
                    raise PolicyLaunchError("saved state changed during hidden entry")
                authorization = Authorization(_path(checked["authorization_path"]))
                if checked["state"] == "fresh":
                    review = {
                        "checked_on": datetime.now(UTC).date().isoformat(),
                        "credential_sha256": fingerprints,
                        "account_scope": checked["account_scope"],
                    }
                    review_path = _path(checked["review_path"])
                    review_raw = _json(gateway._review(review, fresh=True))
                    pipeline._write(review_path, review_raw)
                    pins = {
                        Path(name): _digest(value)
                        for name, value in _object(checked["bindings"]).items()
                    }
                    pins[review_path] = _sha(review_raw)
                    phase[0] = "preparing"
                    policy_run.prepare_study(
                        _path(checked["directory"]),
                        descriptor=_path(checked["descriptor"]),
                        authorization=authorization,
                        review=review,
                        input_bindings=pins,
                    )
                phase[0] = "executing"
                _emit(
                    notice,
                    "Starting the original study; recorded attempts may include unsent requests.",
                )
                actual_transport = transport or RawHTTPTransport(
                    allow_paid=True, timeout_seconds=cast(float, checked["timeout_seconds"])
                )
                result = policy_run.run_study(
                    _path(checked["directory"]), transport=actual_transport
                )
                public.update(_public_result(result), phase="finished")
                return public
    except policy_run.PolicyRunInterrupted as error:
        public.update(_public_result(error.partial), status="cancelled", phase=phase[0])
        raise
    except policy_run.PolicyRunStopped as error:
        public.update(_public_result(error.partial), phase=phase[0])
        raise
    except KeyboardInterrupt:
        public.update(status="cancelled", phase=phase[0], reason="cancelled")
        raise
    except Exception as error:
        code = error.code if isinstance(error, credentials.KeyInputError) else "launch_stopped"
        public.update(status="stopped", phase=phase[0], reason=code)
        if isinstance(error, credentials.KeyInputError):
            raise
        raise PolicyLaunchError("launch stopped; original records retained") from None
    finally:
        if output is not None:
            try:
                pipeline._write(output, _json(public))
            except (OSError, ValueError):
                public["receipt_saved"] = False
                _emit(notice, "Launch receipt unavailable; original execution records remain.")
            else:
                public["receipt_saved"] = True


def _public_result(result: dict[str, object]) -> dict[str, object]:
    if result.get("status") == "complete":
        return {"status": "complete"}
    if result.get("status") != "incomplete":
        raise PolicyLaunchError("controller returned no supported state")
    from buddha.releases import _path as relative_path

    observation = relative_path(result["observation"])
    reason = _text(result["reason"])
    if not observation.startswith("observations/") or reason not in {
        "unknown",
        "authority",
        "protocol",
        "cancelled",
        "native_error",
        "agent_error",
    }:
        raise PolicyLaunchError("controller returned no supported saved stop")
    return {"status": "incomplete", "reason": reason, "observation": observation}
