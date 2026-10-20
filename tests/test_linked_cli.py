"""Exercise linked preparation, authority enforcement and cached CLI execution."""

import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import test_continuation as fixtures

from buddha.__main__ import main
from buddha.benchmark import _canonical
from buddha.evaluation import ValidationError
from buddha.progress import snapshot
from buddha.run import _sha
from buddha.search import load_search, run_search


class LinkedCLITests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ContinuationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_prepare_command_binds_real_continuation_without_keys_or_network(self):
        fixture = self.fixture
        with (
            patch("http.client.HTTPSConnection") as connection,
            patch("buddha.__main__._key_environment") as keys,
            redirect_stdout(io.StringIO()) as output,
        ):
            result = main(
                [
                    "continuation-prepare",
                    "--source",
                    str(fixture.source),
                    "--manifest-sha256",
                    fixture.source_manifest_sha,
                    "--ledger-sha256",
                    fixture.source_ledger_sha,
                    "--archive",
                    str(fixtures.ARCHIVE),
                    "--archive-sha256",
                    fixtures.ARCHIVE_SHA,
                    "--authorization",
                    str(fixture.authority_path),
                    "--out",
                    str(fixture.out),
                ]
            )
        self.assertEqual(result, 0)
        record = json.loads(output.getvalue())
        self.assertEqual(record["status"], "prepared")
        self.assertEqual(record["model_calls"], 0)
        self.assertEqual(record["inherited_replies"], 9)
        self.assertEqual(record["max_calls"], 55)
        self.assertEqual(fixture.authority.for_run(fixture.out).totals()["operation_count"], 0)
        connection.assert_not_called()
        keys.assert_not_called()
        fixture.assert_source_unchanged()

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

    def test_cli_uses_shared_authority_for_synthetic_execution_and_cached_restart(self):
        fixture = self.fixture
        fixture.prepare()
        arguments = [
            "search-run",
            "--run",
            str(fixture.out),
            "--authorization",
            str(fixture.authority_path),
        ]
        with (
            patch("buddha.__main__._SearchReplay", return_value=fixtures.SyntheticTransport()),
            redirect_stdout(io.StringIO()) as output,
            redirect_stderr(io.StringIO()) as progress,
        ):
            self.assertEqual(main(arguments), 0)
        report = json.loads(output.getvalue())["report"]
        self.assertEqual(report["costs"]["operation_count"], 55)
        self.assertEqual(report["inherited_costs"]["operation_count"], 9)
        self.assertEqual(snapshot(fixture.out)["status"], "complete")
        self.assertIn("9 inherited", progress.getvalue())
        self.assertIn("new API", progress.getvalue())
        with (
            patch("buddha.__main__._SearchReplay", return_value=fixtures.NoSend()),
            redirect_stdout(io.StringIO()) as output,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(arguments), 0)
        self.assertEqual(json.loads(output.getvalue())["report"], report)

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
