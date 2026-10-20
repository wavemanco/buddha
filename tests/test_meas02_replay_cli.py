"""The source-executing research replay must retain its assertion guards."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ReplayCLITests(unittest.TestCase):
    def test_optimized_modes_stop_before_dependencies_inputs_or_output(self):
        script = Path(__file__).resolve().parents[1] / "docs/conformance/meas02-official-replay.py"
        with tempfile.TemporaryDirectory() as temporary:
            for mode in ("-O", "-OO"):
                with self.subTest(mode=mode):
                    output = Path(temporary) / (mode.lstrip("-") + ".json")
                    completed = subprocess.run(
                        [sys.executable, "-B", mode, str(script), "--out", str(output)],
                        capture_output=True,
                        check=False,
                        timeout=20,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertIn(b"MEAS02_REPLAY_OPTIMIZED_MODE_UNSUPPORTED", completed.stderr)
                    self.assertEqual(completed.stdout, b"")
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
