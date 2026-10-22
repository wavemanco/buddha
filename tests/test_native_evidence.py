"""Shared passive native custody without a policy study or executing owner."""

import hashlib
import json
import sqlite3
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from test_native_evaluation import NativeEvaluationFixture

from buddha.authorization import Authorization
from buddha.doctor import _authority
from buddha.gateway import Gateway
from buddha.native_evidence import (
    NativeEvidence,
    NativeEvidenceError,
    authority_observation,
)
from buddha.policy_results import PolicyResultsError, _Reader
from buddha.releases import ReleaseError, _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CallerEvidenceError(ReleaseError):
    pass


class NativeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = f = NativeEvaluationFixture("runTest")
        f.setUp()
        cls.addClassCleanup(f.doCleanups)
        f.prepare()
        cls.report = f.run_evaluation()
        if cls.report["status"] != "complete":
            raise AssertionError("genuine mocked native fixture did not complete")

    def files(self):
        return {
            path.relative_to(self.fixture.root).as_posix(): (
                sha(path.read_bytes()),
                path.stat().st_mtime_ns,
            )
            for path in self.fixture.root.rglob("*")
            if path.is_file()
        }

    def reader(self, error_type=NativeEvidenceError):
        f = self.fixture
        reader = NativeEvidence(f.directory, f.fixture.authority.path, error_type=error_type)
        reader.release = f.fixture.agent.release
        reader.template = {"native": f.record["native"], "stages": f.record["stages"]}
        owners = [reader.owner(f.directory / "owners" / str(index)) for index in range(1, 4)]
        reader.funded = _authority(reader.capture, f.fixture.authority.path, owners)
        self.assertIsNotNone(reader.funded)
        return reader

    @contextmanager
    def passive(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("native evidence attempted execution, credentials or writes")

        real_connect, real_open = sqlite3.connect, Path.open

        def connect(path, *args, **kwargs):
            if path != ":memory:":
                forbidden()
            return real_connect(path, *args, **kwargs)

        def opened(path, mode="r", *args, **kwargs):
            if any(character in mode for character in "wax+"):
                forbidden()
            return real_open(path, mode, *args, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(patch.object(Authorization, "__init__", side_effect=forbidden))
            stack.enter_context(patch.object(Gateway, "__init__", side_effect=forbidden))
            for name in (
                "buddha.executor.run_container",
                "buddha.releases.verify_selection",
                "getpass.getpass",
                "os.environ.get",
                "http.client.HTTPSConnection",
                "socket.create_connection",
                "subprocess.Popen",
            ):
                stack.enter_context(patch(name, side_effect=forbidden))
            stack.enter_context(patch("sqlite3.connect", side_effect=connect))
            stack.enter_context(patch.object(Path, "open", opened))
            yield

    @contextmanager
    def changed(self, path, raw):
        before = path.read_bytes()
        try:
            path.write_bytes(raw)
            yield
        finally:
            path.write_bytes(before)

    def test_complete_native_chain_is_passive_without_a_policy_study(self):
        f = self.fixture
        before, sends = self.files(), f.fixture.physical_sends
        with self.passive():
            reader = self.reader()
            answers_name = reader.release.to_record()["artifacts"]["answers"]
            available = {answers_name: f.directory / "native-answers.jsonl"}
            reports = []
            for index in range(1, 4):
                report, attempt = reader.stage(f.directory, index, baseline=False)
                reader.native(f.directory, index, report, f.answers_path, available)
                reports.append(report)
                for output in f.record["stages"][index - 1]["outputs"]:
                    available[output["path"]] = attempt / "artifacts" / output["path"]
            self.assertEqual(reports, self.report["stages"])
            self.assertEqual(len(reader.seals), 3)
            reader.capture.finish()
        self.assertEqual(self.files(), before)
        self.assertEqual(f.fixture.physical_sends, sends)

    def test_original_hash_and_custom_error_identity_are_preserved(self):
        path = self.fixture.directory / "context.json"
        reader = self.reader(CallerEvidenceError)
        self.assertEqual(reader.raw(path, sha(path.read_bytes())), path.read_bytes())
        with self.assertRaisesRegex(CallerEvidenceError, "retained input differs"):
            reader.raw(path, "0" * 64)
        default = self.reader()
        with self.assertRaises(NativeEvidenceError):
            default.raw(path, "0" * 64)

    def test_policy_reader_inherits_shared_boundary_with_original_error_type(self):
        reader = _Reader(self.fixture.directory, self.fixture.fixture.authority.path)
        self.assertIsInstance(reader, NativeEvidence)
        with self.assertRaisesRegex(PolicyResultsError, "retained input differs"):
            reader.raw(self.fixture.directory / "context.json", "0" * 64)

    def test_seal_boolean_index_and_unsealed_extra_file_are_rejected(self):
        f = self.fixture
        path = f.directory / "completed/1.json"
        seal = json.loads(path.read_bytes())
        invalid = seal | {"index": True}
        with self.changed(path, _json(invalid)):
            with self.assertRaisesRegex(NativeEvidenceError, "completion anchor"):
                self.reader().stage(f.directory, 1, baseline=False)
        extra = f.directory / seal["attempt"] / "unsealed.txt"
        try:
            extra.write_bytes(b"not in the original stage inventory")
            with self.assertRaisesRegex(CallerEvidenceError, "inventory differs"):
                self.reader(CallerEvidenceError).stage(f.directory, 1, baseline=False)
        finally:
            extra.unlink(missing_ok=True)

    def test_changed_staging_cannot_be_adopted_as_new_native_input(self):
        f = self.fixture
        reader = self.reader()
        report, _ = reader.stage(f.directory, 1, baseline=False)
        staged = f.directory / "staging/1/0.bin"
        with self.changed(staged, staged.read_bytes() + b"\n"):
            with self.assertRaisesRegex(NativeEvidenceError, "retained input differs"):
                self.reader().native(
                    f.directory,
                    1,
                    report,
                    f.answers_path,
                    {"answers.jsonl": f.directory / "native-answers.jsonl"},
                )

    def test_authority_summary_uses_only_validated_capture_and_is_detached(self):
        f = self.fixture
        before = self.files()
        expected = f.fixture.authority.summary()
        with self.passive():
            reader = self.reader()
            observed = authority_observation(
                reader.capture, f.fixture.authority.path, reader.funded
            )
            self.assertEqual(observed, expected)
            observed["runs"][0]["spent_microusd"] = -1
            self.assertEqual(
                authority_observation(reader.capture, f.fixture.authority.path, reader.funded),
                expected,
            )
            reader.capture.finish()
        self.assertEqual(self.files(), before)
