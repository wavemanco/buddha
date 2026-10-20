"""Engineering helper seals bind consumed source despite adjacent bytecode."""

import hashlib
import importlib.util
import os
import py_compile
import sys
import tempfile
import unittest
from pathlib import Path


class EngineeringHelperTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.original = Path(__file__).resolve().parents[1] / "docs/conformance"
        self.directory = self.root / "docs/conformance"
        self.directory.mkdir(parents=True)
        metadata = self.directory / "nb02c3-runtime-environment.json"
        metadata.write_bytes(b"{}")
        installed = self.root / "runs/reviews/nb02c3-runtime-installed.json"
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b"{}")
        old_path, old_bytecode = sys.path[:], sys.dont_write_bytecode
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))
        self.addCleanup(setattr, sys, "dont_write_bytecode", old_bytecode)

    def fixture(self, kind):
        stem = "funded-native-probe" if kind == "funded" else "direct-worker"
        helper = self.directory / ("nb02c3-" + stem + ".py")
        original = (self.original / helper.name).read_bytes()
        helper.write_bytes(original)
        target = self.directory / ("nb02c3b-" + stem + ".py")
        target.write_bytes((self.original / target.name).read_bytes())
        return helper, target, original

    def load(self, target):
        namespace = {"__name__": "engineering_fixture", "__file__": str(target)}
        exec(compile(target.read_bytes(), str(target), "exec"), namespace)
        return namespace

    def test_both_helpers_ignore_real_timestamp_and_size_matching_poisoned_cache(self):
        for kind in ("funded", "direct"):
            with self.subTest(kind=kind):
                helper, target, original = self.fixture(kind)
                poison = b"raise RuntimeError('cached-poison')\n"
                helper.write_bytes(poison + b"#" * (len(original) - len(poison)))
                os.utime(helper, (1_700_000_000, 1_700_000_000))
                py_compile.compile(str(helper), doraise=True)
                helper.write_bytes(original)
                os.utime(helper, (1_700_000_000, 1_700_000_000))
                expected = hashlib.sha256(original).hexdigest()
                spec = importlib.util.spec_from_file_location("poison_demonstration", helper)
                self.assertIsNotNone(spec)
                module = importlib.util.module_from_spec(spec)
                with self.assertRaisesRegex(RuntimeError, "cached-poison"):
                    spec.loader.exec_module(module)
                loaded = self.load(target)
                actual = loaded["score_fixture"] if kind == "funded" else loaded["score_oracle"]
                self.assertTrue(hasattr(actual, "Funded" if kind == "funded" else "DirectWorker"))
                self.assertEqual(hashlib.sha256(helper.read_bytes()).hexdigest(), expected)

    def test_both_helpers_reject_changed_source_before_execution(self):
        for kind in ("funded", "direct"):
            with self.subTest(kind=kind):
                helper, target, _ = self.fixture(kind)
                helper.write_bytes(b"raise AssertionError('unsealed-source-executed')\n")
                with self.assertRaisesRegex(ValueError, "engineering helper differs"):
                    self.load(target)


if __name__ == "__main__":
    unittest.main()
