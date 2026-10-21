"""Live operator preserves the controller's durable partial result and refusal reason."""

import json
import unittest
from unittest.mock import Mock, patch

import test_meas02_operator as operator_fixture

main = operator_fixture.main
namespace = operator_fixture.namespace


class StudyRefused(ValueError):
    pass


class PartialOperatorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = operator_fixture.OperatorTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.controller.NativeAuditError = StudyRefused
        self.partial = {
            "status": "incomplete",
            "result": "partial",
            "observation": "observations/retained.json",
            "stop": {"reason": "money", "codes": ["money"]},
            "coverage": {
                "expected_count": 40,
                "sealed_target_ids": [],
                "partial_target_ids": ["one-validated-target"],
                "missing_target_ids": ["unmeasured"],
            },
        }
        self.fixture.controller.record_stopped_audit = Mock(return_value=self.partial)

    def command(self, live=True):
        return ["run", "--run", str(self.fixture.directory)] + (["--live"] if live else [])

    def test_partial_cli_preserves_label_reason_codes_and_observation(self):
        with (
            self.fixture.operator(),
            patch.dict(namespace, {"execute": Mock(return_value=self.partial)}),
        ):
            self.assertEqual(main(self.command()), 3)
        result = json.loads(self.fixture.out.getvalue())
        self.assertEqual(result["result"], "partial")
        self.assertEqual(result["reason"], "money")
        self.assertEqual(result["reason_codes"], ["money"])
        self.assertEqual(result["observation"], self.partial["observation"])

    def test_live_preflight_refusal_records_partial_before_any_key_or_worker(self):
        self.fixture.controller.check_native_audit.side_effect = StudyRefused("PRIVATE-CAUSE")
        with self.fixture.operator() as getpass:
            self.assertEqual(main(self.command()), 3)
            getpass.assert_not_called()
        self.fixture.controller.record_stopped_audit.assert_called_once_with(
            self.fixture.directory, reason="preflight"
        )
        self.fixture.controller.run_native_audit.assert_not_called()
        self.assertNotIn("PRIVATE-CAUSE", self.fixture.out.getvalue() + self.fixture.err.getvalue())
        self.assertEqual(json.loads(self.fixture.out.getvalue())["reason"], "money")

    def test_check_refusal_does_not_write_a_partial_observation(self):
        self.fixture.controller.check_native_audit.side_effect = StudyRefused("PRIVATE-CAUSE")
        with self.fixture.operator() as getpass:
            self.assertEqual(main(["check", "--run", str(self.fixture.directory)]), 2)
            getpass.assert_not_called()
        self.fixture.controller.record_stopped_audit.assert_not_called()

    def test_unfunded_without_live_flag_keeps_check_read_only(self):
        self.fixture.controller.check_native_audit.side_effect = StudyRefused("PRIVATE-CAUSE")
        with self.fixture.operator():
            self.assertEqual(main(self.command(live=False)), 2)
        self.fixture.controller.record_stopped_audit.assert_not_called()

    def test_failed_partial_write_does_not_claim_a_saved_partial_result(self):
        self.fixture.controller.check_native_audit.side_effect = StudyRefused("PRIVATE-CAUSE")
        self.fixture.controller.record_stopped_audit.side_effect = OSError("PRIVATE-WRITE")
        with self.fixture.operator() as getpass:
            self.assertEqual(main(self.command()), 2)
            getpass.assert_not_called()
        result = json.loads(self.fixture.out.getvalue())
        self.assertEqual(result["status"], "stopped")
        self.assertNotIn("observation", result)
        self.assertNotIn("PRIVATE-", self.fixture.out.getvalue() + self.fixture.err.getvalue())


if __name__ == "__main__":
    unittest.main()
