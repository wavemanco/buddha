"""Exercise linked preparation, authority enforcement and cached CLI execution."""

import hashlib
import unittest

import test_continuation as fixtures

from buddha.benchmark import _canonical
from buddha.evaluation import ValidationError
from buddha.run import _sha
from buddha.search import load_search, run_search


class LinkedCLITests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ContinuationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_library_requires_authority_even_for_synthetic_linked_execution(self):
        fixture = self.fixture
        fixture.prepare()
        transport = fixtures.SyntheticTransport()
        with self.assertRaises(ValidationError):
            run_search(fixture.out, transport=transport)
        self.assertEqual(transport.sent, [])
        self.assertEqual(fixture.authority.for_run(fixture.out).totals()["operation_count"], 0)

    def test_unhashable_manifest_format_is_a_typed_validation_failure(self):
        fixture = self.fixture
        for value in ([], {}):
            with self.subTest(format=value):
                manifest = dict(fixture.source_manifest, format=value)
                manifest.pop("record_sha256")
                (fixture.source / "manifest.json").write_bytes(
                    _canonical(manifest | {"record_sha256": _sha(manifest)})
                )
                with self.assertRaises(ValidationError):
                    load_search(fixture.source)

    def test_rehashed_malformed_runtime_archive_is_a_typed_validation_failure(self):
        fixture = self.fixture
        fixture.prepare()
        manifest = load_search(fixture.out)[0]
        broken = b"not a zip archive"
        (fixture.out / "runtime-source.zip").write_bytes(broken)
        manifest["continuation"]["runtime_archive_sha256"] = hashlib.sha256(broken).hexdigest()
        (fixture.out / "manifest.json").write_bytes(
            _canonical(manifest | {"record_sha256": _sha(manifest)})
        )
        with self.assertRaises(ValidationError):
            load_search(fixture.out)

    def test_cached_report_stays_stable_after_continuation_deactivation(self):
        fixture = self.fixture
        fixture.prepare()
        report = run_search(
            fixture.out, transport=fixtures.SyntheticTransport(), authorization=fixture.authority
        )
        fixture.authority.deactivate(report["run_id"], "Completed continuation retained for audit")
        self.assertEqual(
            run_search(fixture.out, transport=fixtures.NoSend(), authorization=fixture.authority),
            report,
        )


if __name__ == "__main__":
    unittest.main()
