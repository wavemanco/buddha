"""Run one separately approved matched trial with temporary hidden API keys.

--handoff and --sha256 identify its reviewed funded launch. --receipt names a
NEW file outside original inputs and output. Runs once; Ctrl+C retains original
evidence. Unfinished work needs --live and --confirm-project-keys. This command
does not allocate money. See docs/IMPROVER-LAUNCH.md before live use.
"""

import argparse
import json
import sys
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from buddha import credentials as credentials
from buddha import launch_common
from buddha.improver_launch import ImproverLaunchError, launch


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ImproverLaunchError("invalid command options")


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--handoff", type=Path, required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--receipt", type=Path, required=True)
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--prompt-keys", action="store_true")
        parser.add_argument("--confirm-project-keys", action="store_true")
        args = parser.parse_args(argv)
        record = launch(
            args.handoff.absolute(),
            expected_sha256=args.sha256,
            receipt=args.receipt.absolute(),
            live=args.live,
            prompt_keys=args.prompt_keys,
            confirm_project_keys=args.confirm_project_keys,
        )
        code = 0 if record["status"] == "complete" else 3
    except KeyboardInterrupt:
        record, code = {"status": "cancelled", "reason": "cancelled"}, 130
    except Exception as error:
        reason = launch_common._stop_reason(error)
        record, code = {"status": "stopped", "reason": reason}, 2
    print(json.dumps({"format": "buddha.improver-operator.v1", **record}), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
