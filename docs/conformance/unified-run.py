"""Check, run or resume one approved primary-and-plain comparison.

--check reads configuration and original state only. Live work requires --live
and --confirm-project-keys; --prompt-keys enters missing keys temporarily.
Runs once. Ctrl+C retains original work and attempts a new partial observation.
Wait for the exact funded command; see docs/UNIFIED-LAUNCH.md.
"""

import argparse
import hashlib
import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from buddha import credentials as credentials
from buddha import launch_common
from buddha.releases import _digest, _json, file_hash
from buddha.unified_launch import UnifiedLaunchError, check_launch, launch


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UnifiedLaunchError("invalid command options")


def _inspect_check(operation, handoff, expected_sha256, runtime):
    """Keep framework state in a fresh folder, outside all original inputs."""
    from buddha.inspect_study import run

    runtime = launch_common._receipt_path(runtime)
    roots = launch_common._receipt_roots(handoff, _digest(expected_sha256))
    roots += [path.parent for path in roots if path.suffix.lower() == ".py"]
    if any(runtime.is_relative_to(root) or root.is_relative_to(runtime) for root in roots):
        raise UnifiedLaunchError("Inspect output overlaps original comparison evidence")
    runtime.mkdir()
    (runtime / ".env").write_bytes(b"")
    settings = {
        "WIN_PD_OVERRIDE_LOCAL_APPDATA": str(runtime / "appdata"),
        "WIN_PD_OVERRIDE_APPDATA": str(runtime / "roaming"),
        "WIN_PD_OVERRIDE_COMMON_APPDATA": str(runtime / "programdata"),
        "XDG_DATA_HOME": str(runtime / "data"),
        "XDG_CACHE_HOME": str(runtime / "cache"),
        "INSPECT_LOG_DIR": str(runtime / "logs"),
        "INSPECT_CACHE_DIR": str(runtime / "cache"),
        "INSPECT_TRACE_FILE": str(runtime / "trace.log"),
        "INSPECT_PY_LOGGER_FILE": str(runtime / "python.log"),
        "INSPECT_TRACE_LEVEL": "TRACE",
        "INSPECT_TRACEBACK_LOCALS": "0",
        "MPLCONFIGDIR": str(runtime / "mpl"),
        "PYTHON_DOTENV_DISABLED": "1",
        "DO_NOT_TRACK": "1",
    }
    previous = {name: os.environ.get(name) for name in settings}
    original_directory = Path.cwd()

    def checked():
        os.chdir(original_directory)
        try:
            return operation()
        finally:
            os.chdir(runtime)

    try:
        os.environ.update(settings)
        os.chdir(runtime)
        return run(checked, log_dir=runtime / "logs")
    finally:
        os.chdir(original_directory)
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main(argv=None):
    continuation_sha256 = None
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--handoff", type=Path, required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--continuation", action="store_true")
        parser.add_argument("--resume-decision", type=Path)
        parser.add_argument("--resume-sha256")
        parser.add_argument("--check", action="store_true")
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--prompt-keys", action="store_true")
        parser.add_argument("--confirm-project-keys", action="store_true")
        parser.add_argument("--inspect-log-dir", type=Path)
        args = parser.parse_args(argv)
        if (args.resume_decision is None) != (args.resume_sha256 is None) or (
            args.resume_decision is not None
            and (args.continuation or args.inspect_log_dir is not None)
        ):
            raise UnifiedLaunchError("held recovery requires one paired decision and digest")
        scope = (
            nullcontext()
            if args.resume_decision is None
            else launch_common._held_recovery(
                args.resume_decision.absolute(),
                args.resume_sha256,
                args.handoff.absolute(),
                args.sha256,
            )
        )
        if args.inspect_log_dir is not None and (not args.check or args.continuation):
            raise UnifiedLaunchError("Inspect currently supports fresh read-only checks only")
        if args.continuation:
            continuation_sha256 = _digest(args.sha256)
            from buddha.unified_continuation import (
                check_trial_continuation,
                launch_trial_continuation,
            )
        if args.check:
            if args.live or args.prompt_keys or args.confirm_project_keys:
                raise UnifiedLaunchError("check mode cannot request live work or keys")
            handoff = args.handoff.absolute()

            def check():
                return (
                    check_trial_continuation(handoff, expected_sha256=args.sha256).summary()
                    if args.continuation
                    else check_launch(handoff, expected_sha256=args.sha256)
                )

            with scope:
                checked = (
                    check()
                    if args.inspect_log_dir is None
                    else _inspect_check(
                        check, handoff, args.sha256, args.inspect_log_dir.absolute()
                    )
                )
            record = {
                "status": "checked",
                "phase": checked["phase"],
                "stop_code": checked["stop_code"],
            }
            code = 0 if checked["stop_code"] is None else 3
        else:
            execute = launch_trial_continuation if args.continuation else launch
            with scope:
                result = execute(
                    args.handoff.absolute(),
                    expected_sha256=args.sha256,
                    live=args.live,
                    prompt_keys=args.prompt_keys,
                    confirm_project_keys=args.confirm_project_keys,
                )
            record = {
                key: result[key]
                for key in (
                    "status",
                    "phase",
                    "reason",
                    "review_status",
                    "claim",
                    "observation_saved",
                    "observation",
                    "publication_path",
                )
                if key in result
            }
            if "publication_path" in record:
                expected = hashlib.sha256(_json(result)).hexdigest()
                if file_hash(Path(record["publication_path"])) != expected:
                    raise UnifiedLaunchError(
                        "comparison publication changed before terminal output"
                    )
                record["publication_sha256"] = expected
            code = 0 if record["status"] == "complete" else 3
    except KeyboardInterrupt:
        record, code = {"status": "cancelled", "reason": "cancelled"}, 130
    except Exception as error:
        reason = launch_common._stop_reason(error)
        record, code = {"status": "stopped", "reason": reason}, 2
    if continuation_sha256 is not None:
        record["continuation_sha256"] = continuation_sha256
    print(json.dumps({"format": "buddha.unified-operator.v1", **record}), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
