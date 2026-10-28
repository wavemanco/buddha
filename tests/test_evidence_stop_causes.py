"""Evidence limits survive real redacting wrappers without revealing error text."""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import test_comparison_observation as observation_fixtures
import test_unified_launch as unified_fixtures

from buddha import credentials, doctor, improver_study, launch_common, search_evidence
from buddha.common import ValidationError


class UntrustedError(RuntimeError):
    @property
    def code(self):
        raise AssertionError("arbitrary error code was inspected")

    def __str__(self):
        raise AssertionError("private exception text was inspected")


class EvidenceStopCauseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.observed = self.root / "observation"
        self.observed.mkdir()
        self.payload = self.root / "PRIVATE-CANARY.bin"
        self.payload.write_bytes(b"data")
        self.handoff = self.root / "handoff.json"
        self.handoff.write_bytes(b"{}")

    @improver_study._checked
    def overflow(self):
        with patch.object(doctor, "MAX_TOTAL_BYTES", 3):
            doctor._Capture(self.observed).read(self.payload, 8)

    def overflow_error(self):
        try:
            self.overflow()
        except improver_study.ImproverStudyError as error:
            return error
        self.fail("the genuine evidence overflow was accepted")

    def test_genuine_aggregate_guard_survives_real_from_none_decorator(self):
        error = self.overflow_error()
        self.assertTrue(error.__suppress_context__)
        self.assertIsNotNone(error.__context__)
        self.assertEqual(launch_common._stop_reason(error), "evidence_total_bytes_limit")

    def test_field_and_path_limits_have_distinct_safe_causes(self):
        for field, total in ((2, 8), (2, 1)):
            with (
                self.subTest(field=field, total=total),
                patch.object(doctor, "MAX_TOTAL_BYTES", total),
            ):
                with self.assertRaises(ValidationError) as stopped:
                    doctor._Capture(self.observed).read(self.payload, field)
                self.assertEqual(
                    launch_common._stop_reason(stopped.exception), "evidence_field_bytes_limit"
                )
        with patch.object(doctor, "MAX_FILES", 0), self.assertRaises(ValidationError) as stopped:
            doctor._Capture(self.observed).read(self.payload)
        self.assertEqual(launch_common._stop_reason(stopped.exception), "evidence_path_count_limit")
        with self.assertRaises(ValidationError) as stopped:
            search_evidence._read(self.payload, 2)
        self.assertEqual(
            launch_common._stop_reason(stopped.exception), "evidence_field_bytes_limit"
        )
        capture = doctor._Capture(self.observed)
        capture.read(self.payload, 4)
        with self.assertRaises(ValidationError) as stopped:
            capture.read(self.payload, 3)
        self.assertEqual(
            launch_common._stop_reason(stopped.exception), "evidence_field_bytes_limit"
        )

    def test_shared_total_read_retains_field_priority_and_pre_read_aggregate_bound(self):
        class FalseyReader:
            def __init__(self):
                self.maximums = []

            def __bool__(self):
                return False

            def __call__(self, path, maximum):
                self.maximums.append(maximum)
                return search_evidence._read(path, maximum)

        for maximum, remaining, reason in (
            (8, 3, "evidence_total_bytes_limit"),
            (2, 3, "evidence_field_bytes_limit"),
            (2, 1, "evidence_field_bytes_limit"),
        ):
            reader = FalseyReader()
            with (
                self.subTest(reason=reason),
                patch.object(
                    search_evidence,
                    "_open_binary",
                    side_effect=AssertionError("over-limit evidence was opened"),
                ),
                self.assertRaises(ValidationError) as stopped,
            ):
                search_evidence._total_read(self.payload, maximum, remaining, read=reader)
            self.assertEqual(launch_common._stop_reason(stopped.exception), reason)
            self.assertEqual(reader.maximums, [min(maximum, remaining)])

    def test_unknown_text_codes_cycles_and_long_chains_stay_bounded_and_redacted(self):
        unknown = UntrustedError("PRIVATE-CANARY")
        unknown.__context__ = unknown
        self.assertEqual(launch_common._stop_reason(unknown), "launch_stopped")
        forged = RuntimeError("PRIVATE-CANARY")
        forged.code = "evidence_total_bytes_limit"
        self.assertEqual(launch_common._stop_reason(forged), "launch_stopped")
        current = self.overflow_error()
        for _ in range(40):
            outer = RuntimeError("PRIVATE-CANARY")
            outer.__context__ = current
            current = outer
        self.assertEqual(launch_common._stop_reason(current), "launch_stopped")
        current.__cause__ = self.overflow_error()
        self.assertEqual(launch_common._stop_reason(current), "evidence_total_bytes_limit")
        for code in ("key_terminal_required", "key_input_unavailable", "key_input_invalid"):
            self.assertEqual(launch_common._stop_reason(credentials.KeyInputError(code)), code)
        key_error = credentials.KeyInputError("key_input_invalid")
        key_error.code = "PRIVATE-CANARY"
        self.assertEqual(launch_common._stop_reason(key_error), "launch_stopped")

    def cli(self, name):
        path = Path(__file__).parents[1] / "docs/conformance" / name
        spec = importlib.util.spec_from_file_location("safe_stop_" + name, path)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        return cli

    def test_all_operator_clis_keep_the_real_launcher_context_and_safe_receipt(self):
        from buddha import improver_launch, policy_launch, source_launch, unified_launch

        for name, module in (
            ("src02-run.py", source_launch),
            ("pol02-run.py", policy_launch),
            ("imp01-run.py", improver_launch),
            ("unified-run.py", unified_launch),
        ):
            cli = self.cli(name)
            output, errors = io.StringIO(), io.StringIO()
            args = ["--handoff", str(self.handoff), "--sha256", "0" * 64]
            receipt = self.root / (name + ".receipt.json")
            if name != "unified-run.py":
                args.extend(("--receipt", str(receipt)))
            boundary = "_configuration" if name == "unified-run.py" else "check_launch"
            with (
                self.subTest(operator=name),
                patch.object(module, boundary, side_effect=lambda *a, **k: self.overflow()),
                patch.object(launch_common, "_receipt_roots", return_value=[]),
                redirect_stdout(output),
                redirect_stderr(errors),
            ):
                self.assertEqual(cli.main(args), 2)
            record = json.loads(output.getvalue())
            self.assertEqual(record["reason"], "evidence_total_bytes_limit", name)
            self.assertNotIn("PRIVATE-CANARY", output.getvalue() + errors.getvalue())
            if receipt.exists():
                self.assertEqual(json.loads(receipt.read_bytes())["reason"], record["reason"])

    def test_all_operator_clis_preserve_unknown_key_and_cancel_results(self):
        for name in ("src02-run.py", "pol02-run.py", "imp01-run.py", "unified-run.py"):
            cli = self.cli(name)
            args = ["--handoff", str(self.handoff), "--sha256", "0" * 64]
            if name != "unified-run.py":
                args.extend(("--receipt", str(self.root / (name + ".unused"))))
            for error, code, reason in (
                (UntrustedError("PRIVATE-CANARY"), 2, "launch_stopped"),
                (credentials.KeyInputError("key_input_invalid"), 2, "key_input_invalid"),
                (KeyboardInterrupt("PRIVATE-CANARY"), 130, "cancelled"),
            ):
                output = io.StringIO()
                with self.subTest(operator=name, reason=reason), redirect_stdout(output):
                    with patch.object(cli, "launch", side_effect=error):
                        self.assertEqual(cli.main(args), code)
                    self.assertEqual(json.loads(output.getvalue())["reason"], reason)
                    self.assertNotIn("PRIVATE-CANARY", output.getvalue())

    def test_unified_forwards_safe_cause_and_real_observation_retains_it(self):
        fixture = unified_fixtures.UnifiedLaunchLifecycleTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.primary_error = self.overflow_error()
        with (
            fixture.seams(),
            patch.object(
                launch_common, "_stop_reason", wraps=launch_common._stop_reason
            ) as reasons,
            self.assertRaises(improver_study.ImproverStudyError),
        ):
            fixture.launch(notice=lambda text: fixture.events.append(("notice", text)))
        self.assertEqual(reasons.call_count, 1)
        stopped = (
            "notice",
            "Launch stopped: evidence_total_bytes_limit. "
            "Recording saved evidence; no new provider requests.",
        )
        observation = ("observation", "primary", "evidence_total_bytes_limit")
        self.assertLess(fixture.events.index(stopped), fixture.events.index(observation))
        self.assertNotIn("PRIVATE-CANARY", repr(fixture.events))
        self.assertFalse(fixture.prepared)
        saved = observation_fixtures.ComparisonObservationTests("runTest")
        saved.setUp()
        self.addCleanup(saved.doCleanups)
        reason = launch_common._stop_reason(fixture.primary_error)
        report = saved.save(phase="primary", reason=reason)
        self.assertEqual(saved.read(report)["stop"]["reason"], reason)
        self.assertEqual(json.loads(Path(report["path"]).read_bytes())["stop"]["reason"], reason)


if __name__ == "__main__":
    unittest.main()
