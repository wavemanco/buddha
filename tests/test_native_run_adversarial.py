"""Additional fixed-worker provenance checks through the actual host constructor."""

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import test_native_run as fixtures

from buddha.native_run import NativeRunError
from buddha.releases import MAX_JSON_BYTES, Release, _json, inventory


class NativeRunAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NativeSessionTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_matching_unused_worker_copy_cannot_authorize_a_different_entrypoint(self):
        fixture = self.fixture
        runner = fixture.fixture.roots["runner"]
        # Source data only: this file is never imported or executed by this test.
        (runner / "alternate.py").write_text("VALUE = 'different driver'\n", encoding="utf-8")
        fixture.worker["inventories"]["runner"] = inventory(runner)
        fixture.record["executor"]["runner_entrypoint"] = "alternate.py"
        fixture.freeze()
        with self.assertRaises(NativeRunError):
            fixture.session()
        self.assertFalse(fixture.output.exists())
        self.assertEqual(fixture.fixture.authority.summary()["operation_count"], 0)

    def test_descriptor_bytes_consumed_after_hash_must_match_the_frozen_digest(self):
        fixture = self.fixture
        changed = copy.deepcopy(fixture.record)
        changed["executor"]["limits"]["wall_seconds"] = 1
        original = Path.open
        injected = []

        class ChangedStream:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def read(self, size=-1):
                if size in {-1, MAX_JSON_BYTES + 1}:
                    # Ordinary bounded hash chunks still read the original file.
                    injected.append(size)
                    return _json(changed)
                return self.stream.read(size)

        def changed_during_read(path, *args, **kwargs):
            stream = original(path, *args, **kwargs)
            return ChangedStream(stream) if path == fixture.descriptor else stream

        with (
            patch.object(Path, "open", changed_during_read),
            self.assertRaises(NativeRunError),
        ):
            fixture.session()
        self.assertTrue(injected, "test did not exercise the consumed descriptor read")
        self.assertFalse(fixture.output.exists())
        self.assertEqual(fixture.fixture.authority.summary()["operation_count"], 0)

    def test_selected_bytecode_or_cache_directory_is_rejected_before_output(self):
        fixture = self.fixture
        for role, relative in (
            ("official", "src/cached.pyc"),
            ("runner", "buddha/cached.pyo"),
            ("runner", "buddha/__pycache__/otherwise-plain.txt"),
        ):
            root = fixture.fixture.roots[role]
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"cache inventory fixture; never executed")
            fixture.worker["inventories"][role] = inventory(root)
            if role == "official":
                fixture.fixture.release_record["source"] = inventory(root)
                fixture.worker["release_sha256"] = Release.from_record(
                    fixture.fixture.release_record
                ).fingerprint()
            fixture.freeze()
            with self.subTest(role=role, path=relative), self.assertRaises(NativeRunError):
                fixture.session()
            self.assertFalse(fixture.output.exists())
            self.assertEqual(fixture.fixture.authority.summary()["operation_count"], 0)
            path.unlink()
            fixture.worker["inventories"][role] = inventory(root)
            if role == "official":
                fixture.fixture.release_record["source"] = inventory(root)
                fixture.worker["release_sha256"] = Release.from_record(
                    fixture.fixture.release_record
                ).fingerprint()


if __name__ == "__main__":
    unittest.main()
