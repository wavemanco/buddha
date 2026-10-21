"""Run one approved POL-02 study with temporary hidden provider keys.

--handoff and --sha256 identify the separately approved funded launch record.
--receipt must name a NEW output outside the study/components. Checking prints
progress immediately; --live and --confirm-project-keys are required before
unfinished execution. Ctrl+C retains original evidence and exits130.
"""

import argparse
import json
import sys
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from buddha import credentials, policy_run
from buddha.policy_launch import PolicyLaunchError, launch


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PolicyLaunchError("invalid command options")


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
            live=args.live,
            prompt_keys=args.prompt_keys,
            confirm_project_keys=args.confirm_project_keys,
            receipt=args.receipt.absolute(),
        )
        code = 0 if record["status"] == "complete" else 3
    except policy_run.PolicyRunInterrupted as error:
        record = {
            "status": "cancelled",
            "reason": "cancelled",
            "observation": error.partial["observation"],
        }
        code = 130
    except policy_run.PolicyRunStopped as error:
        record = {
            "status": "incomplete",
            "reason": error.partial["reason"],
            "observation": error.partial["observation"],
        }
        code = 3
    except KeyboardInterrupt:
        record, code = {"status": "cancelled", "reason": "cancelled"}, 130
    except Exception as error:
        reason = error.code if isinstance(error, credentials.KeyInputError) else "launch_stopped"
        record, code = {"status": "stopped", "reason": reason}, 2
    print(json.dumps({"format": "buddha.policy-operator.v1", **record}), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
