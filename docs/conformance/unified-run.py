"""Check, run or resume one approved primary-and-plain comparison.

--check reads configuration and original state only. Live work requires --live
and --confirm-project-keys; --prompt-keys enters missing keys temporarily.
Runs once. Ctrl+C retains original work and attempts a new partial observation.
Wait for the exact funded command; see docs/UNIFIED-LAUNCH.md.
"""

import argparse
import hashlib
import json
import sys
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


def main(argv=None):
    continuation_sha256 = None
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--handoff", type=Path, required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--continuation", action="store_true")
        parser.add_argument("--check", action="store_true")
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--prompt-keys", action="store_true")
        parser.add_argument("--confirm-project-keys", action="store_true")
        args = parser.parse_args(argv)
        if args.continuation:
            continuation_sha256 = _digest(args.sha256)
            from buddha.unified_continuation import (
                check_trial_continuation,
                launch_trial_continuation,
            )
        if args.check:
            if args.live or args.prompt_keys or args.confirm_project_keys:
                raise UnifiedLaunchError("check mode cannot request live work or keys")
            checked = (
                check_trial_continuation(
                    args.handoff.absolute(), expected_sha256=args.sha256
                ).summary()
                if args.continuation
                else check_launch(args.handoff.absolute(), expected_sha256=args.sha256)
            )
            record = {
                "status": "checked",
                "phase": checked["phase"],
                "stop_code": checked["stop_code"],
            }
            code = 0 if checked["stop_code"] is None else 3
        else:
            execute = launch_trial_continuation if args.continuation else launch
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
