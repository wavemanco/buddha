"""Thin entry point; requires an explicitly pinned, separately funded handoff."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from buddha.capacity_launch import CapacityLaunchError, run_launch


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CapacityLaunchError("invalid capacity command")


if __name__ == "__main__":
    parser = _Parser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--prompt-keys", action="store_true")
    parser.add_argument("--confirm-project-key", action="store_true")
    try:
        args = parser.parse_args()
        result = run_launch(
            args.handoff,
            expected_sha256=args.expected_sha256,
            live=args.live,
            prompt_keys=args.prompt_keys,
            confirm_project_key=args.confirm_project_key,
            notice=lambda text: print("[capacity] " + text, flush=True),
        )
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in ("format", "status", "reason", "stage")
                    if key in result
                }
            )
        )
        raise SystemExit(0 if result.get("status") == "complete" else 1)
    except CapacityLaunchError:
        print("[capacity] Checks or execution stopped; original evidence retained.", flush=True)
        raise SystemExit(2) from None
