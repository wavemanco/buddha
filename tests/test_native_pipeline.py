"""Shared completion publication preserves types outside its financial snapshot."""

import copy
import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_baseline as baseline_fixtures

from buddha import native_pipeline
from buddha.authorization import Authorization
from buddha.native_pipeline import PipelineError, publish_complete
from buddha.releases import ReleaseError, _json


class PublicationTests(unittest.TestCase):
    def test_replay_rejects_boolean_substitution_in_original_nonfinancial_payload(self):
        with tempfile.TemporaryDirectory() as location:
            directory = Path(location)
            authority = Authorization.create(
                directory / "authorization.sqlite3",
                authorization_id="synthetic-publication-test",
                budget_microusd=1000,
                max_calls=10,
                scope="synthetic publication integrity only",
            )
            path = directory / "report.json"
            expected = {"cells": [{"arm_index": 0}], "authorization": authority.summary()}
            self.assertEqual(publish_complete(path, expected, authority, set()), expected)
            changed = copy.deepcopy(expected)
            changed["cells"][0]["arm_index"] = False
            path.write_bytes(_json(changed))
            with self.assertRaises(PipelineError):
                publish_complete(path, expected, authority, set())


class NativeStagingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = baseline_fixtures.BaselineTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.input = self.root / "literal-native-input.jsonl"
        self.input.write_bytes(b'{"literal":"complete unchanged input"}\n')
        self.available = {
            name: self.input for stage in self.fixture.record["stages"] for name in stage["inputs"]
        }
        self.frozen = {self.input: hashlib.sha256(self.input.read_bytes()).hexdigest()}

    def descriptor(self, directory, index, **kwargs):
        path, inputs = native_pipeline._native_descriptor(
            directory,
            index,
            self.fixture.record,
            self.fixture.agent.release,
            self.input,
            self.available,
            self.frozen,
            **kwargs,
        )
        return json.loads(path.read_bytes()), inputs

    def test_legacy_default_preserves_its_original_staging_path_and_bytes(self):
        directory = self.root / "legacy-evaluation"
        (directory / "staging").mkdir(parents=True)
        descriptor, inputs = self.descriptor(directory, 1)
        self.assertEqual(inputs, [directory / "staging/1/0.bin"])
        self.assertEqual(inputs[0].read_bytes(), self.input.read_bytes())
        self.assertEqual(
            dict(descriptor["executor"]["mounts"])["/inputs"],
            str(directory / "staging/1"),
        )

    def test_explicit_staging_is_shallow_deterministic_and_distinct_by_stage_and_evaluation(self):
        root = self.root / "native-inputs"
        deep = self.root.joinpath(*("d" + str(i) for i in range(18)))
        other = deep / "other"
        other.mkdir(parents=True)
        leaves = []
        for directory, index in ((deep, 1), (deep, 2), (other, 1)):
            descriptor, inputs = self.descriptor(directory, index, staging_root=root)
            expected = root / hashlib.sha256(_json([str(directory.absolute()), index])).hexdigest()
            self.assertEqual(inputs, [expected / "0.bin"])
            self.assertEqual(dict(descriptor["executor"]["mounts"])["/inputs"], str(expected))
            self.assertEqual(inputs[0].read_bytes(), self.input.read_bytes())
            self.assertEqual(len(expected.relative_to(root).parts), 1)
            self.assertFalse((directory / "staging").exists())
            repeated, repeated_inputs = self.descriptor(directory, index, staging_root=root)
            self.assertEqual((repeated, repeated_inputs), (descriptor, inputs))
            leaves.append(expected)
        self.assertEqual(len(set(leaves)), 3)

    def test_private_staging_still_rejects_extra_files_without_replacing_input(self):
        directory = self.root / "evaluation"
        directory.mkdir()
        root = self.root / "native-inputs"
        _, inputs = self.descriptor(directory, 1, staging_root=root)
        before = inputs[0].read_bytes()
        (inputs[0].parent / "foreign.bin").write_bytes(b"not selected")
        with self.assertRaises(PipelineError):
            self.descriptor(directory, 1, staging_root=root)
        self.assertEqual(inputs[0].read_bytes(), before)

    def test_private_staging_rejects_a_link_root_before_copying_input_bytes(self):
        directory, root = self.root / "evaluation", self.root / "native-inputs"
        directory.mkdir()
        root.mkdir()
        lstat = Path.lstat

        def information(path, *args, **kwargs):
            if path == root:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
            return lstat(path, *args, **kwargs)

        with patch.object(Path, "lstat", information), self.assertRaises(ReleaseError):
            self.descriptor(directory, 1, staging_root=root)
        self.assertEqual(list(root.rglob("*.bin")), [])


if __name__ == "__main__":
    unittest.main()
