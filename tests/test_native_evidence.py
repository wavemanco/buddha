"""Shared passive native custody without a policy study or executing owner."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from test_native_evaluation import NativeEvaluationFixture

from buddha import native_pipeline
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


class RetainedCaptureTests(unittest.TestCase):
    def test_external_tree_watch_keeps_the_existing_entry_ceiling(self):
        from buddha.doctor import _Capture, _observation_policy
        from buddha.search_evidence import EvidencePathLimitError

        reader, _, _, _ = self.fixture()
        leaf = reader.root.parent / "selected-inputs"
        leaf.mkdir()
        (leaf / "0.bin").write_bytes(b"selected")
        with _observation_policy(
            {
                "format": "buddha.evidence-observation-policy.v2",
                "max_total_bytes": 1024,
                "max_resident_bytes": 0,
                "max_tree_entries": 1,
                "max_consumed_paths": 10,
            }
        ):
            capture = _Capture(reader.root)
        entries = capture.watch_tree(leaf)
        entries.clear()
        capture.finish()
        (leaf / "foreign.bin").write_bytes(b"unselected")
        with self.assertRaises(EvidencePathLimitError):
            capture.watch_tree(leaf)

    def fixture(self):
        from buddha.doctor import _Capture

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        development, final = root / "development", root / "final"
        development.mkdir()
        final.mkdir()
        data, ledger = development / "reply.bin", development / "ledger.sqlite3"
        data.write_bytes(b"original")
        ledger.write_bytes(b"capture bytes only; not a parsed SQL owner")
        captured = _Capture(development)
        captured.read(data)
        captured.database(ledger)
        reader = NativeEvidence(final, root / "unused-authorization.sqlite3")
        reader.retain_capture(captured)
        return reader, captured, data, ledger

    def test_join_retains_every_consumed_byte_and_database_without_source_execution(self):
        reader, captured, _, ledger = self.fixture()
        self.assertTrue(set(captured.raw) <= set(reader.capture.raw))
        self.assertIn(ledger, reader.capture.databases)
        self.assertEqual(reader.capture.raw, captured.raw)
        reader.finish()

    def test_nested_hash_verification_preserves_capture_and_refuses_invalid_inputs(self):
        reader, captured, data, ledger = self.fixture()
        expected = {path: sha(raw) for path, raw in captured.raw.items()}
        reader.verify_files(expected)
        self.assertEqual(reader.capture.raw, captured.raw)
        for hashes in (None, {str(data): expected[data]}, {ledger: "0" * 64}):
            with self.subTest(hashes=hashes), self.assertRaises(NativeEvidenceError):
                reader.verify_files(hashes)
        reader.finish()

    def test_join_catches_new_entries_in_a_sibling_tree(self):
        from buddha.doctor import _Busy

        reader, _, data, _ = self.fixture()
        (data.parent / "foreign.bin").write_bytes(b"not in the original observation")
        with self.assertRaises(_Busy):
            reader.finish()

    def test_capture_adoption_retains_an_external_tree_watch(self):
        from buddha.doctor import _Busy

        reader, captured, data, _ = self.fixture()
        leaf = data.parent.parent / "native-input-leaf"
        leaf.mkdir()
        (leaf / "0.bin").write_bytes(b"original selected input")
        captured.watch_tree(leaf)
        reader.capture.adopt(captured)
        (leaf / "late.bin").write_bytes(b"foreign entry after adoption")
        with self.assertRaises(_Busy):
            reader.capture.finish()

    def test_join_catches_late_bytes_and_sidecars_even_when_metadata_is_held_constant(self):
        from buddha.doctor import _Busy

        reader, captured, data, ledger = self.fixture()
        snapshots = {reader.root: reader.capture.entries, captured.root: captured.entries}
        with patch("buddha.doctor._entries", side_effect=lambda root: snapshots[root]):
            data.write_bytes(b"modified")
            with self.assertRaises(_Busy):
                reader.finish()
            data.write_bytes(b"original")
            ledger.with_name(ledger.name + "-wal").write_bytes(b"live sidecar")
            with self.assertRaises(_Busy):
                reader.finish()


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

    def reader(self, error_type=NativeEvidenceError, *, fixture=None):
        f = fixture or self.fixture
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
        command = json.loads((f.directory / "command-1.json").read_bytes())
        staged = Path(dict(command["executor"]["mounts"])["/inputs"]) / "0.bin"
        with self.changed(staged, staged.read_bytes() + b"\n"):
            with self.assertRaisesRegex(NativeEvidenceError, "retained input differs"):
                self.reader().native(
                    f.directory,
                    1,
                    report,
                    f.answers_path,
                    {
                        reader.release.to_record()["artifacts"]["answers"]: f.directory
                        / "native-answers.jsonl"
                    },
                )

    def test_private_staging_rejects_an_existing_extra_entry(self):
        fixture, reader = self.fixture, self.reader()
        command = json.loads((fixture.directory / "command-1.json").read_bytes())
        extra = Path(dict(command["executor"]["mounts"])["/inputs"]) / "foreign.bin"
        extra.write_bytes(b"unselected private-mount entry")
        try:
            with self.passive(), self.assertRaisesRegex(NativeEvidenceError, "unselected entries"):
                reader.native_configuration(
                    fixture.directory,
                    1,
                    fixture.answers_path,
                    {
                        reader.release.to_record()["artifacts"]["answers"]: fixture.directory
                        / "native-answers.jsonl"
                    },
                )
        finally:
            extra.unlink()

    def test_private_staging_rejects_an_existing_link_entry(self):
        from buddha.common import ValidationError

        fixture, reader = self.fixture, self.reader()
        command = json.loads((fixture.directory / "command-1.json").read_bytes())
        root = Path(dict(command["executor"]["mounts"])["/inputs"])
        link = root / "foreign-link.bin"
        try:
            link.symlink_to(root / "0.bin")
        except OSError:
            self.skipTest("host cannot create symlinks")
        try:
            with self.passive(), self.assertRaises(ValidationError):
                reader.native_configuration(
                    fixture.directory,
                    1,
                    fixture.answers_path,
                    {
                        reader.release.to_record()["artifacts"]["answers"]: fixture.directory
                        / "native-answers.jsonl"
                    },
                )
        finally:
            link.unlink()

    def test_private_staging_watch_detects_a_late_entry_after_configuration(self):
        from buddha.doctor import _Busy

        fixture, reader = self.fixture, self.reader()
        with self.passive():
            reader.native_configuration(
                fixture.directory,
                1,
                fixture.answers_path,
                {
                    reader.release.to_record()["artifacts"]["answers"]: fixture.directory
                    / "native-answers.jsonl"
                },
            )
        command = json.loads((fixture.directory / "command-1.json").read_bytes())
        extra = Path(dict(command["executor"]["mounts"])["/inputs"]) / "late.bin"
        extra.write_bytes(b"foreign entry after configuration")
        try:
            with self.passive(), self.assertRaises(_Busy):
                reader.capture.finish()
        finally:
            extra.unlink()

    def staging_fixture(self, *, legacy):
        fixture = NativeEvaluationFixture("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original = native_pipeline._native_descriptor

        def staged(*args, **kwargs):
            kwargs["staging_root"] = None if legacy else fixture.root / "foreign-inputs"
            return original(*args, **kwargs)

        with patch.object(native_pipeline, "_native_descriptor", side_effect=staged):
            fixture.prepare()
            self.assertEqual(fixture.run_evaluation()["status"], "complete")
        return fixture

    def test_original_legacy_staging_still_verifies_with_the_passive_reader(self):
        fixture = self.staging_fixture(legacy=True)
        with self.passive():
            reader = self.reader(fixture=fixture)
            answers_name = reader.release.to_record()["artifacts"]["answers"]
            available = {answers_name: fixture.directory / "native-answers.jsonl"}
            for index, stage in enumerate(fixture.record["stages"], 1):
                report, attempt = reader.stage(fixture.directory, index, baseline=False)
                reader.native(fixture.directory, index, report, fixture.answers_path, available)
                for output in stage["outputs"]:
                    available[output["path"]] = attempt / "artifacts" / output["path"]
            reader.finish()

    def test_bound_but_unapproved_external_staging_is_rejected_by_the_passive_reader(self):
        fixture = self.staging_fixture(legacy=False)
        with self.passive():
            reader = self.reader(fixture=fixture)
            report, _ = reader.stage(fixture.directory, 1, baseline=False)
            with self.assertRaises(NativeEvidenceError):
                reader.native(
                    fixture.directory,
                    1,
                    report,
                    fixture.answers_path,
                    {
                        reader.release.to_record()["artifacts"]["answers"]: fixture.directory
                        / "native-answers.jsonl"
                    },
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
