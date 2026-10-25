"""The actual operator script provides help and never echoes invalid arguments."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


class ImproverLaunchCLITests(unittest.TestCase):
    def invoke(self, *arguments):
        root = Path(__file__).absolute().parents[1]
        return subprocess.run(
            [sys.executable, "-B", str(root / "docs/conformance/imp01-run.py"), *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_help_exits_without_a_launch_or_key_prompt(self):
        result = self.invoke("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--confirm-project-keys", result.stdout)
        self.assertIn("does not allocate money", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_invalid_arguments_never_echo_potential_credentials(self):
        canary = "CANARY-INVALID-CLI-ARGUMENT"
        result = self.invoke("--unrecognized", canary)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "format": "buddha.improver-operator.v1",
                "status": "stopped",
                "reason": "launch_stopped",
            },
        )
        self.assertNotIn(canary, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
