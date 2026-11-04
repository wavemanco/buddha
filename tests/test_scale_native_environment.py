"""Small installed-tree/hash checks; the full scale producer is separate."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scale_native_environment import build_environment

from buddha import native_worker


class ScaleNativeEnvironmentTests(unittest.TestCase):
    def test_supported_environment_joins_real_files_manifest_and_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "synthetic-image"
            environment = build_environment(root, inventory_count=64)
            self.assertEqual(set(environment), {"helper_sha256", "manifest_sha256", "inventory"})
            self.assertEqual(len(environment["inventory"]), 64)
            manifest = (root / "runtime-manifest.json").read_bytes()
            self.assertEqual(hashlib.sha256(manifest).hexdigest(), environment["manifest_sha256"])
            self.assertEqual(json.loads(manifest)["inventory"], environment["inventory"])
            worker = object.__new__(native_worker.NativeWorker)
            worker.inventories = {"environment": environment}
            previous = sys.modules.get("_buddha_runtime_audit")
            try:
                with (
                    patch.object(native_worker, "RUNTIME_HELPER", root / "runtime-prepare.py"),
                    patch.object(native_worker, "RUNTIME_MANIFEST", root / "runtime-manifest.json"),
                ):
                    self.assertEqual(worker._environment(), environment["inventory"])
                    member = root / "venv" / next(iter(environment["inventory"]))
                    member.write_bytes(b"Changed installed fixture bytes.\n")
                    with self.assertRaises(native_worker.WorkerError):
                        worker._environment()
            finally:
                if previous is None:
                    sys.modules.pop("_buddha_runtime_audit", None)
                else:
                    sys.modules["_buddha_runtime_audit"] = previous

    def test_bounds_and_fresh_destination_refuse_before_rewriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "synthetic-image"
            for invalid in (True, 0, 24_044):
                with self.subTest(count=invalid), self.assertRaises(ValueError):
                    build_environment(root, inventory_count=invalid)
            self.assertFalse(root.exists())
            build_environment(root, inventory_count=1)
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            with self.assertRaises(FileExistsError):
                build_environment(root, inventory_count=1)
            self.assertEqual(
                {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}, before
            )


if __name__ == "__main__":
    unittest.main()
