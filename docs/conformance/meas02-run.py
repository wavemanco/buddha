"""Local operator entry for the frozen MEAS-02 supplied-control study.

Preparation/checks are offline. Incomplete work requires explicit --live before
hidden key entry; the controller owns all request identities, funding and stops.
"""

import argparse
import hashlib
import json
import math
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.authorization import Authorization  # noqa: E402
from buddha.baseline import _read  # noqa: E402
from buddha.gateway import RawHTTPTransport  # noqa: E402
from buddha.provider import ModelSpec  # noqa: E402
from buddha.releases import _load, _path  # noqa: E402

CONTROLLER = Path(__file__).with_name("meas02-native-audit.py")
CONTROLLER_SHA256 = "ac7cddb5021507712206352cd95fc1264f061e55a3c5fa0b298b8428c5ca23f1"


class OperatorError(ValueError):
    """Safe, fixed operator-facing reason; never a provider's exception text."""


def _notice(message):
    try:
        print("[meas02] " + message, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass  # Observation failure cannot change a paid operation's result.


def _controller():
    try:
        raw = _read(CONTROLLER, CONTROLLER_SHA256)
        module = ModuleType("_meas02_operator_controller")
        module.__file__ = str(CONTROLLER)
        # Exact reviewed first-party bytes; no cached .pyc or official/agent code.
        exec(  # nosec B102
            compile(raw, str(CONTROLLER), "exec"), module.__dict__
        )
        return module
    except Exception:
        raise OperatorError("reviewed study controller is unavailable or changed") from None


class _Profiles:
    """Only the existing key-entry helper's profile view, not legacy RunSettings."""

    def __init__(self, profiles):
        if (
            not isinstance(profiles, list)
            or not profiles
            or any(
                not isinstance(spec, ModelSpec) or spec.provider != "openai" for spec in profiles
            )
        ):
            raise OperatorError("preflight did not provide the reviewed OpenAI profile")
        self.values = tuple(profiles)

    def profiles(self):
        return self.values


def _credentials(profiles, expected):
    for provider in dict.fromkeys(spec.provider for spec in profiles.profiles()):
        value = os.environ.get({"openai": "OPENAI_API_KEY"}[provider], "")
        if (
            not value
            or len(value) > 4096
            or any(not 33 <= ord(char) <= 126 for char in value)
            or hashlib.sha256(value.encode("ascii")).hexdigest() != expected.get(provider)
        ):
            raise OperatorError("provider key is missing or differs from the reviewed account")


@contextmanager
def _heartbeat(authority_path, interval):
    stop, started = threading.Event(), time.monotonic()
    authority = Authorization(authority_path)

    def tick():
        try:
            current = authority.summary()
            elapsed = int(time.monotonic() - started)
            _notice(
                f"[{elapsed // 60:02d}:{elapsed % 60:02d}] "
                f"Shared attempts {current['operation_count']}; "
                f"spent ${current['spent_microusd'] / 1_000_000:.6f}; "
                f"held ${current['reserved_microusd'] / 1_000_000:.6f}; "
                f"cap ${current['budget_microusd'] / 1_000_000:.6f}."
            )
        except Exception:
            _notice("Progress temporarily unavailable; execution remains independently guarded.")

    def watch():
        while not stop.wait(interval):
            tick()

    tick()
    thread = threading.Thread(target=watch, name="meas02-operator-progress", daemon=True)
    try:
        thread.start()
    except Exception:
        _notice("Progress observer unavailable; execution remains independently guarded.")
    try:
        yield
    finally:
        stop.set()
        if thread.is_alive():
            thread.join(timeout=0.5)
        tick()


def execute(directory, *, live=False, prompt_keys=False, transport=None, heartbeat_seconds=10.0):
    """Check, optionally obtain a temporary key, then run the same original owners.

    The check is keyless; execution rechecks all guards after key entry. No worker
    runs while the operator is entering a key. Complete-only replay needs no key.
    """
    if (
        not isinstance(directory, Path)
        or type(live) is not bool
        or type(prompt_keys) is not bool
        or type(heartbeat_seconds) not in (int, float)
        or not math.isfinite(heartbeat_seconds)
        or not 0 < heartbeat_seconds <= 60
        or transport is not None
        and not isinstance(transport, RawHTTPTransport)
    ):
        raise OperatorError("invalid operator execution options")
    controller = _controller()
    directory = directory.absolute()
    try:
        checked = controller.check_native_audit(directory)
    except Exception as error:
        if not live or not isinstance(error, getattr(controller, "NativeAuditError", ())):
            raise
        # A real run refusal is an observation, never an altered completion or
        # authorization. The controller must revalidate original state to save it.
        return _finish(controller.record_stopped_audit(directory, reason="preflight"))
    if checked["status"] == "complete":
        _notice("Rechecking stored completion; no keys or provider calls are needed.")
        result = controller.run_native_audit(
            directory, transport=RawHTTPTransport(allow_paid=False)
        )
    else:
        if checked["status"] != "ready":
            raise OperatorError("study preflight did not permit execution")
        if not live:
            raise OperatorError("--live is required for unfinished work; no key was requested")
        transport = RawHTTPTransport(allow_paid=True) if transport is None else transport
        if not transport.allow_paid:
            raise OperatorError("unfinished live work requires an explicitly paid transport")
        profiles = _Profiles(checked["profiles"])
        # Reuse the established hidden-input/confirmation/finally-cleanup behavior.
        # This private helper only calls profiles(); no legacy RunSettings is made.
        from buddha.__main__ import _key_environment

        with _key_environment(profiles, prompt_keys=prompt_keys):
            _credentials(profiles, checked["credential_sha256"])
            _notice("Starting frozen study. Provider calls and native startup can take time.")
            with _heartbeat(Path(checked["authorization_path"]), heartbeat_seconds):
                result = controller.run_native_audit(directory, transport=transport)
    return _finish(result)


def public_result(result):
    """Safe CLI fields; partial output must name its durable controller observation."""
    if not isinstance(result, dict) or result.get("status") not in {"complete", "incomplete"}:
        raise OperatorError("study returned no supported completion state; saved evidence retained")
    record = {"status": result["status"]}
    if result["status"] == "incomplete":
        stop = result.get("stop")
        if (
            result.get("result") != "partial"
            or not isinstance(stop, dict)
            or not isinstance(stop.get("reason"), str)
            or not stop["reason"]
            or not isinstance(stop.get("codes"), list)
            or not stop["codes"]
            or any(
                not isinstance(code, str)
                or not code
                or len(code) > 64
                or any(char not in "abcdefghijklmnopqrstuvwxyz_" for char in code)
                for code in [stop["reason"], *stop["codes"]]
            )
            or not isinstance(result.get("observation"), str)
            or not _path(result["observation"]).startswith("observations/")
        ):
            raise OperatorError("study returned no supported durable partial observation")
        record |= {
            "result": "partial",
            "reason": stop["reason"],
            "reason_codes": list(stop["codes"]),
            "observation": result["observation"],
        }
    return record


def _finish(result):
    record = public_result(result)
    _notice(
        "Run complete (four saved, authority-anchored batches)."
        if record["status"] == "complete"
        else "Run partial (incomplete); reason "
        + record["reason"]
        + "; saved "
        + record["observation"]
        + ". Original owners, replies and holds retained."
    )
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Unknown arguments can contain accidentally pasted credentials.
        raise OperatorError("invalid operator command or options")


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True)
        for name in ("check", "prepare", "run"):
            command = commands.add_parser(name)
            command.add_argument("--run", type=Path, required=True)
            if name == "prepare":
                command.add_argument("--descriptor", type=Path, required=True)
                command.add_argument("--authorization", type=Path, required=True)
                command.add_argument("--review", type=Path, required=True)
            if name == "run":
                command.add_argument("--live", action="store_true")
                command.add_argument("--prompt-keys", action="store_true")
        args = parser.parse_args(argv)
        if args.command == "run":
            result = execute(args.run, live=args.live, prompt_keys=args.prompt_keys)
            record = public_result(result)
            code = 0 if result["status"] == "complete" else 3
        else:
            controller = _controller()
            if args.command == "prepare":
                controller.prepare_native_audit(
                    args.run.absolute(),
                    descriptor=args.descriptor.absolute(),
                    authorization=Authorization(args.authorization.absolute()),
                    review=_load(_read(args.review.absolute())),
                )
            checked = controller.check_native_audit(args.run.absolute())
            record = {
                "status": "prepared" if args.command == "prepare" else checked["status"],
                "next_batch": checked["next_batch"],
                "next_occasion": checked["next_occasion"],
                "provider_calls": 0,
            }
            code = 0
        print(json.dumps({"format": "buddha.meas02-operator.v1", **record}), flush=True)
        return code
    except KeyboardInterrupt:
        _notice(
            "Cancelled. Saved state and any outstanding holds remain; completion is not claimed."
        )
        print(
            json.dumps({"format": "buddha.meas02-operator.v1", "status": "cancelled"}), flush=True
        )
        return 130
    except Exception as error:
        message = (
            str(error)
            if isinstance(error, OperatorError)
            else "operator checks or execution failed"
        )
        _notice("Stopped: " + message + "; saved state retained.")
        print(json.dumps({"format": "buddha.meas02-operator.v1", "status": "stopped"}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
