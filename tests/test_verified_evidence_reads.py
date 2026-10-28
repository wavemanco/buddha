"""Fresh receipt transfers avoid rereading bytes just to export their digests."""

import hashlib
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import test_generation_evidence_pair as fixtures
import test_native_evaluation as baseline_fixtures

from buddha import candidate_generation, doctor, native_evaluation
from buddha.native_evidence import NativeEvidence, NativeEvidenceError, _adopt_capture
from buddha.search_evidence import (
    EvidenceFieldLimitError,
    EvidencePathLimitError,
    EvidenceTotalLimitError,
)


class VerifiedReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source_root, self.target_root = self.base / "source", self.base / "target"
        self.source_root.mkdir()
        self.target_root.mkdir()
        self.files = [self.base / (str(index) + ".bin") for index in range(4)]
        for index, path in enumerate(self.files):
            path.write_bytes(bytes([65 + index]) * 4)

    def captures(self):
        return doctor._Capture(self.source_root), doctor._Capture(self.target_root)

    def snapshot(self, capture):
        return dict(capture._receipts), capture.total, set(capture.databases)

    def test_adoption_costs_one_fresh_source_pass_and_preserves_every_receipt(self):
        source, target = self.captures()
        source.read(self.files[0])
        source.database(self.files[1])
        sidecar = self.files[1].with_name(self.files[1].name + "-wal")
        sidecar.write_bytes(b"")
        source.sidecars(self.files[1])
        target.read(self.files[0])  # Shared receipts count once in the union.
        with patch.object(doctor, "_read", wraps=doctor._read) as reads:
            expected = source.fingerprints()
            fresh_pass = Counter(call.args[0] for call in reads.call_args_list)
            reads.reset_mock()
            _adopt_capture(source, target)
            adopted = Counter(call.args[0] for call in reads.call_args_list)
        self.assertEqual(adopted, fresh_pass)
        self.assertEqual(target.fingerprints(), expected)
        self.assertEqual(target.total, 8)
        self.assertEqual(target.databases, source.databases)
        self.assertIn(sidecar, target.raw)

    def test_adoption_preserves_legacy_external_collision_and_database_sidecar_order(self):
        for kind in ("external", "sidecar"):
            with self.subTest(kind=kind):
                source, target = self.captures()
                sidecar = None
                if kind == "external":
                    source.read(self.files[0])
                    expected = self.files[0]
                else:
                    source.read(self.files[1])
                    sidecar = self.files[1].with_name(self.files[1].name + "-wal")
                    sidecar.write_bytes(b"")
                    expected = self.files[1]
                source.database(self.files[1])
                try:
                    _adopt_capture(source, target)
                    self.assertEqual(
                        target.finish(),
                        {"authorization": hashlib.sha256(expected.read_bytes()).hexdigest()},
                    )
                    self.assertEqual(target.fingerprints(), source.fingerprints())
                finally:
                    if sidecar is not None:
                        sidecar.unlink()

    def test_partial_database_cannot_bypass_original_receipt_or_database_field_ceiling(self):
        for known in (False, True):
            with self.subTest(known_receipt=known):
                source, target = self.captures()
                if known:
                    source.read(self.files[0])
                target.read(self.files[2])
                before = self.snapshot(target)
                with patch.object(doctor, "MAX_LEDGER_BYTES", 3):
                    with self.assertRaises(EvidenceFieldLimitError):
                        source.database(self.files[0])
                    error_type = EvidenceFieldLimitError if known else doctor.ValidationError
                    with self.assertRaises(error_type) as stopped:
                        _adopt_capture(source, target)
                    if known:
                        self.assertEqual(stopped.exception.minimum_bytes, 4)
                self.assertEqual(self.snapshot(target), before)

    def test_total_limit_rejects_the_whole_union_without_partial_mutation(self):
        source = doctor._Capture(self.source_root)
        source.database(self.files[0])
        source.read(self.files[1])
        with patch.object(doctor, "MAX_TOTAL_BYTES", 8):
            target = doctor._Capture(self.target_root)
        target.read(self.files[2])
        before = self.snapshot(target)
        with self.assertRaises(EvidenceTotalLimitError):
            _adopt_capture(source, target)
        self.assertEqual(self.snapshot(target), before)

    def test_path_limit_rejects_the_whole_union_without_partial_mutation(self):
        source = doctor._Capture(self.source_root)
        source.database(self.files[0])
        source.read(self.files[1])
        with patch.object(doctor, "MAX_FILES", 2):
            target = doctor._Capture(self.target_root)
        target.read(self.files[2])
        before = self.snapshot(target)
        with self.assertRaises(EvidencePathLimitError):
            _adopt_capture(source, target)
        self.assertEqual(self.snapshot(target), before)

    def test_conflicting_original_is_busy_and_does_not_admit_earlier_new_receipts(self):
        source, target = self.captures()
        target.read(self.files[0])
        source.database(self.files[1])
        self.files[0].write_bytes(b"XXXX")
        source.read(self.files[0])
        before = self.snapshot(target)
        with self.assertRaises(doctor._Busy):
            _adopt_capture(source, target)
        self.assertEqual(self.snapshot(target), before)

    def test_preexisting_source_drift_cannot_be_adopted(self):
        for drift in ("bytes", "tree", "sidecar"):
            with self.subTest(drift=drift):
                source, target = self.captures()
                source.database(self.files[0])
                before = self.snapshot(target)
                changed = None
                if drift == "bytes":
                    self.files[0].write_bytes(b"XXXX")
                elif drift == "tree":
                    changed = self.source_root / "late.bin"
                    changed.write_bytes(b"late")
                else:
                    changed = self.files[0].with_name(self.files[0].name + "-wal")
                    changed.write_bytes(b"live writer")
                try:
                    with self.assertRaises(doctor._Busy):
                        _adopt_capture(source, target)
                    self.assertEqual(self.snapshot(target), before)
                finally:
                    self.files[0].write_bytes(b"AAAA")
                    if changed is not None:
                        changed.unlink()

    def test_change_after_source_observation_cut_is_caught_by_outer_finish(self):
        source, target = self.captures()
        source.read(self.files[0])
        finish = source.finish

        def changed_after_verification():
            observed = finish()
            self.files[0].write_bytes(b"XXXX")
            return observed

        with patch.object(source, "finish", side_effect=changed_after_verification):
            _adopt_capture(source, target)
        with self.assertRaises(doctor._Busy):
            target.finish()

    def test_original_type_guard_rejects_subclasses_and_self_adoption(self):
        class Derived(doctor._Capture):
            pass

        source, target = self.captures()
        for left, right in ((source, source), (Derived(self.source_root), target)):
            with self.subTest(left=type(left)), self.assertRaises(NativeEvidenceError):
                _adopt_capture(left, right)
            with self.assertRaises(doctor.ValidationError):
                right.adopt(left)

    def test_native_fingerprints_keep_absolute_keys_and_retained_sibling_checks(self):
        data = self.source_root / "reply.bin"
        data.write_bytes(b"original")
        source = doctor._Capture(self.source_root)
        source.read(data)
        reader = NativeEvidence(self.target_root, self.base / "unused.sqlite3")
        local = self.target_root / "local.bin"
        local.write_bytes(b"local")
        reader.capture = doctor._Capture(self.target_root)
        reader.capture.read(local)
        reader.retain_capture(source)
        expected = {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (local, data)
        }
        self.assertEqual(reader.fingerprints(), expected)
        self.assertEqual(
            reader.finish(),
            {"local.bin": expected[str(local)], "authorization": expected[str(data)]},
        )
        (self.source_root / "foreign.bin").write_bytes(b"late entry")
        with self.assertRaises(doctor._Busy):
            reader.fingerprints()


class GenerationFingerprintWorkTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket", side_effect=AssertionError("no network")))
        self.enterContext(
            patch("http.client.HTTPSConnection", side_effect=AssertionError("no live HTTPS"))
        )
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("no process")))

    def projection(self, call):
        original_read, original_finish = doctor._read, doctor._Capture.finish
        count, finished = 0, []

        def read(*args, **kwargs):
            nonlocal count
            count += 1
            return original_read(*args, **kwargs)

        def finish(capture):
            result = original_finish(capture)
            finished.append(count)
            return result

        with (
            patch.object(doctor, "_read", side_effect=read),
            patch.object(doctor._Capture, "finish", new=finish),
        ):
            result = call()
        self.assertTrue(finished)
        self.assertEqual(count - finished[-1], 0, "digest export reread every verified byte")
        return result

    def assert_original_files(self, files, authority):
        self.assertEqual(
            files,
            {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        )
        self.assertTrue(all(isinstance(path, Path) for path in files))
        self.assertNotIn(authority, files)

    def test_source_projection_needs_no_second_byte_pass_after_final_verification(self):
        helper = fixtures.GenerationEvidencePairTests("runTest")
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        fixture, report = helper.fixture(callbacks=1)
        authority = fixture.fixture.authority.path
        evidence = self.projection(
            lambda: candidate_generation._read_evidence(report["source_generation"], authority)
        )
        self.assertEqual(set(evidence["files"]), set(evidence["capture"].raw) - {authority})
        self.assert_original_files(evidence["files"], authority)

    def test_plain_projection_keeps_path_keys_and_excludes_only_authority(self):
        fixture = baseline_fixtures.NativeEvaluationFixture("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        authority = fixture.fixture.authority.path
        observed = []
        original = doctor._Capture.fingerprints

        def fingerprints(capture):
            result = original(capture)
            observed.append(set(capture.raw))
            return result

        with patch.object(doctor._Capture, "fingerprints", new=fingerprints):
            generation = self.projection(
                lambda: native_evaluation._read_baseline_generation(
                    fixture.record["source_generation"], authority
                )
            )
        self.assertEqual(len(observed), 1)
        self.assertEqual(set(generation.files), observed[0] - {authority})
        self.assert_original_files(generation.files, authority)


if __name__ == "__main__":
    unittest.main()
