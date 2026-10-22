"""Protected launching joins one approved destination before hidden entry."""

import copy
import hashlib
import io
import json
import os
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import test_gateway as gateway_fixtures
import test_policy_handoff as handoff_fixtures

from buddha import policy_launch, policy_run
from buddha.policy_launch import PolicyLaunchError, check_launch, launch
from buddha.releases import _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PolicyLaunchTests(unittest.TestCase):
    def setUp(self):
        self.h = handoff_fixtures.PolicyHandoffTests("runTest")
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f = self.h.f
        self.root = self.h.root
        self.review = self.root / "launch-review.json"
        self.f.descriptor.write_bytes(_json(self.f.record))
        terms = self.f.authority.summary()
        self.h.record["requested_terms"] = {
            key: terms[key] for key in ("budget_microusd", "max_calls")
        }
        self.proposal_sha = self.h.save()
        self.approval_path = self.root / "approval.json"
        self.approval = {
            "format": "buddha.policy-approval.v1",
            "proposal_sha256": self.proposal_sha,
            "study_sha256": self.f.study.fingerprint(),
            "directory": str(self.f.directory),
            "review": str(self.review),
            "authorization": self.f.record["authorization"],
            **self.h.record["requested_terms"],
            "account_scope": "Synthetic standard/default public PAYG; no account overrides",
        }
        self.launch_path = self.root / "launch.json"
        self.record = {
            "format": "buddha.policy-launch.v1",
            "proposal": self.h.reference(self.h.handoff),
            "execution": self.h.reference(self.f.descriptor),
            "approval": {},
            "directory": str(self.f.directory),
            "review": str(self.review),
            "source_sha256": {str(p): sha(p.read_bytes()) for p in policy_launch._sources()},
            "timeout_seconds": 600,
        }
        self.receipt = self.root / "launch-receipt.json"

    def save(self):
        self.approval_path.write_bytes(_json(self.approval))
        self.record["approval"] = self.h.reference(self.approval_path)
        self.launch_path.write_bytes(_json(self.record))
        return sha(self.launch_path.read_bytes())

    @contextmanager
    def passive(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("passive launch check used a key, writer or worker")

        with ExitStack() as stack:
            for name in (
                "buddha.authorization.Authorization.__init__",
                "buddha.authorization.Authorization.summary",
                "buddha.gateway.Gateway.__init__",
                "buddha.ledger.Ledger.__init__",
                "buddha.policy_run.prepare_study",
                "buddha.policy_run.run_study",
                "buddha.executor.run_container",
                "getpass.getpass",
                "os.getenv",
                "os.environ.get",
                "http.client.HTTPSConnection",
            ):
                stack.enter_context(patch(name, side_effect=forbidden))
            yield

    def check(self):
        pin = self.save()
        with self.passive():
            return check_launch(self.launch_path, expected_sha256=pin)

    def test_fresh_check_is_passive_and_binds_destination_terms_and_original_proposal(self):
        pin = self.save()
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.passive():
            result = check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(result["state"], "fresh")
        self.assertIsNone(result["stop_code"])
        self.assertEqual(result["directory"], str(self.f.directory))
        self.assertEqual(result["funding"]["operation_count"], 0)
        self.assertEqual(result["bindings"][str(self.launch_path)], pin)
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before)
        self.assertFalse(self.f.directory.exists())

    def test_external_pin_destination_and_actual_terms_cannot_be_rebound(self):
        pin = self.save()
        self.record["directory"] = str(self.root / "different-study")
        self.launch_path.write_bytes(_json(self.record))
        with self.assertRaises(PolicyLaunchError):
            check_launch(self.launch_path, expected_sha256=pin)
        self.record["directory"] = str(self.f.directory)
        for key, value in (
            ("directory", str(self.root / "different-study")),
            ("budget_microusd", 2),
            ("max_calls", False),
        ):
            original = copy.deepcopy(self.approval)
            self.approval[key] = value
            try:
                with self.subTest(key=key), self.assertRaises(PolicyLaunchError):
                    self.check()
            finally:
                self.approval = original

    def test_required_launch_source_and_partial_preparation_are_not_adopted(self):
        removed = self.record["source_sha256"].pop(str(Path(policy_launch.__file__).absolute()))
        with self.assertRaises(PolicyLaunchError):
            self.check()
        self.record["source_sha256"][str(Path(policy_launch.__file__).absolute())] = removed
        self.f.directory.mkdir()
        with self.assertRaises(PolicyLaunchError):
            self.check()
        self.assertEqual(list(self.f.directory.iterdir()), [])

    def test_extracted_native_custody_helper_requires_its_original_launch_pin(self):
        helper = (
            Path(policy_launch.policy_results.__file__).absolute().with_name("native_evidence.py")
        )
        expected = sha(helper.read_bytes())
        self.record["source_sha256"][str(helper)] = expected
        self.assertEqual(self.check()["state"], "fresh")
        for supplied in (None, "0" * 64):
            with self.subTest(supplied=supplied):
                if supplied is None:
                    self.record["source_sha256"].pop(str(helper))
                else:
                    self.record["source_sha256"][str(helper)] = supplied
                try:
                    with self.assertRaises(PolicyLaunchError):
                        self.check()
                finally:
                    self.record["source_sha256"][str(helper)] = expected
        checked = self.check()
        self.assertEqual(checked["bindings"][str(helper)], expected)
        self.assertEqual(self.f.fixture.physical_sends, 0)
        self.assertFalse(self.review.exists())
        self.assertFalse(self.f.directory.exists())

    def test_live_and_manual_account_confirmation_gate_precede_key_entry(self):
        pin = self.save()
        for options in ({}, {"live": True}):
            with (
                self.subTest(options=options),
                patch(
                    "buddha.credentials.key_environment", side_effect=AssertionError("key entry")
                ),
                self.assertRaises(PolicyLaunchError),
            ):
                launch(self.launch_path, expected_sha256=pin, **options)
        self.assertFalse(self.f.directory.exists())

    def test_pre_key_stop_has_independent_new_receipt_and_immediate_phase(self):
        pin = self.save()
        notices = []
        with patch.object(policy_launch, "check_launch", side_effect=PolicyLaunchError("bad")):
            with self.assertRaises(PolicyLaunchError):
                launch(
                    self.launch_path,
                    expected_sha256=pin,
                    live=True,
                    confirm_project_keys=True,
                    receipt=self.receipt,
                    notice=notices.append,
                )
        record = json.loads(self.receipt.read_bytes())
        self.assertEqual(record["status"], "stopped")
        self.assertEqual(record["phase"], "checking")
        self.assertTrue(notices and "Checking" in notices[0])
        self.assertNotIn("bad", self.receipt.read_text())
        with self.assertRaises(PolicyLaunchError):
            launch(self.launch_path, expected_sha256=pin, receipt=self.receipt)

    def test_untrusted_handoff_cannot_choose_receipt_or_leak_parser_text(self):
        pin = self.save()
        self.record["receipt"] = str(self.root / "forged-output.json")
        self.launch_path.write_bytes(_json(self.record))
        with self.assertRaises(PolicyLaunchError):
            launch(
                self.launch_path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                receipt=self.receipt,
            )
        self.assertFalse((self.root / "forged-output.json").exists())
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location("pol02_operator_test", policy_launch._entrypoint())
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        output, errors = io.StringIO(), io.StringIO()
        with patch("sys.stdout", output), patch("sys.stderr", errors):
            code = module.main(["--accidental-secret=FAKE-SENTINEL"])
        self.assertEqual(code, 2)
        self.assertNotIn("FAKE-SENTINEL", output.getvalue() + errors.getvalue())

    def test_hidden_key_feedback_cleanup_and_post_prompt_drift_stop_before_prepare(self):
        pin = self.save()
        sentinel = "synthetic-key-for-entry-only"
        original = self.f.descriptor.read_bytes()

        def entered(*args, **kwargs):
            self.f.descriptor.write_bytes(original + b"\n")
            return sentinel

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stderr.isatty", return_value=True),
            patch("getpass.getpass", entered),
            patch.object(policy_run, "prepare_study", side_effect=AssertionError("prepare")),
        ):
            with self.assertRaises(PolicyLaunchError):
                launch(
                    self.launch_path,
                    expected_sha256=pin,
                    live=True,
                    prompt_keys=True,
                    confirm_project_keys=True,
                    receipt=self.receipt,
                    notice=lambda text: None,
                )
            self.assertNotIn("OPENAI_API_KEY", os.environ)
        self.assertNotIn(sentinel, self.receipt.read_text())
        self.assertFalse(self.review.exists())

    def test_existing_review_is_not_replaced_and_completed_state_is_keyless(self):
        pin = self.save()
        checked = {
            "state": "complete",
            "stop_code": None,
            "directory": str(self.f.directory),
            "observation": None,
            "bindings": {},
            "funding": {},
        }
        with (
            patch.object(policy_launch, "check_launch", return_value=checked),
            patch("buddha.credentials.key_environment", side_effect=AssertionError("key entry")),
            patch.object(policy_run, "run_study", side_effect=AssertionError("run")),
        ):
            result = launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(result["status"], "complete")
        self.assertFalse(self.review.exists())

    def test_controller_interruption_carries_exact_saved_observation(self):
        partial = {
            "status": "incomplete",
            "reason": "cancelled",
            "observation": "observations/7.json",
        }
        error = policy_run.PolicyRunInterrupted(partial)
        self.assertIsInstance(error, KeyboardInterrupt)
        self.assertEqual(error.partial, partial)
        partial["reason"] = "changed"
        self.assertEqual(error.partial["reason"], "cancelled")

    def test_real_unknown_stop_and_passive_resume_preserve_original_owners_and_holds(self):
        pin = self.save()
        self.f.fixture.timeout_native_once = True
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=self.f.execute),
        ):
            result = launch(
                self.launch_path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                receipt=self.receipt,
                notice=lambda text: None,
            )
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["reason"], "unknown")
        observation = self.f.directory / result["observation"]
        self.assertEqual(json.loads(observation.read_bytes())["reason"], "unknown")
        self.assertEqual(self.f.fixture.physical_sends, 5)
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        totals = self.f.authority.summary()
        with self.passive():
            checked = check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(checked["state"], "partial")
        self.assertEqual(checked["stop_code"], "unknown")
        second_receipt = self.root / "resume-receipt.json"
        with (
            patch("getpass.getpass", side_effect=AssertionError("key entry")),
            patch.object(policy_run, "run_study", side_effect=AssertionError("worker")),
        ):
            stopped = launch(
                self.launch_path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                prompt_keys=True,
                receipt=second_receipt,
                notice=lambda text: None,
            )
        self.assertEqual(stopped["reason"], "unknown")
        self.assertEqual(self.f.authority.summary(), totals)
        self.assertEqual(self.f.fixture.physical_sends, 5)
        self.assertTrue(all(p.read_bytes() == raw for p, raw in before.items()))

    def test_same_grant_at_another_root_rejects_before_keys(self):
        pin = self.save()
        self.f.directory = self.root / "foreign-comparison"
        self.f.prepare()
        with self.passive(), self.assertRaises(PolicyLaunchError):
            check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(self.f.fixture.physical_sends, 0)

    def test_second_provider_cancellation_removes_first_key_and_does_not_prepare(self):
        from dataclasses import replace

        pin = self.save()
        checked = check_launch(self.launch_path, expected_sha256=pin)
        spec = policy_launch._profiles(checked)[0]
        notices = []
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stderr.isatty", return_value=True),
            patch("getpass.getpass", side_effect=["synthetic-only-key", KeyboardInterrupt]),
            patch.object(
                policy_launch, "_profiles", return_value=[spec, replace(spec, provider="anthropic")]
            ),
        ):
            with self.assertRaises(KeyboardInterrupt):
                launch(
                    self.launch_path,
                    expected_sha256=pin,
                    live=True,
                    prompt_keys=True,
                    confirm_project_keys=True,
                    receipt=self.receipt,
                    notice=notices.append,
                )
            self.assertNotIn("OPENAI_API_KEY", os.environ)
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)
        self.assertTrue(any("received" in text for text in notices))
        self.assertEqual(json.loads(self.receipt.read_bytes())["phase"], "keys")
        self.assertFalse(self.review.exists())
        self.assertFalse(self.f.directory.exists())

    def test_conflicting_checked_binding_and_late_selected_drift_are_rejected(self):
        pin = self.save()
        real = policy_launch.policy_handoff.check_handoff

        def conflict(*args, **kwargs):
            result = real(*args, **kwargs)
            result["reviewed_bindings"][str(self.launch_path)] = "0" * 64
            return result

        with patch.object(policy_launch.policy_handoff, "check_handoff", side_effect=conflict):
            with self.assertRaises(PolicyLaunchError):
                check_launch(self.launch_path, expected_sha256=pin)
        component = self.f.fixture.native_roots["runner"] / "buddha/native_worker.py"
        original = component.read_bytes()
        real_profiles = policy_launch._profiles

        def changed(value):
            result = real_profiles(value)
            component.write_bytes(original + b"\n# late drift\n")
            return result

        try:
            with patch.object(policy_launch, "_profiles", side_effect=changed):
                with self.assertRaises(PolicyLaunchError):
                    check_launch(self.launch_path, expected_sha256=pin)
        finally:
            component.write_bytes(original)

    def test_transport_pin_and_nonfinite_timeout_stop_before_keys_or_preparation(self):
        pin = self.save()
        from buddha.gateway import RawHTTPTransport

        with patch("getpass.getpass", side_effect=AssertionError("key entry")):
            with self.assertRaises(PolicyLaunchError):
                launch(
                    self.launch_path,
                    expected_sha256=pin,
                    live=True,
                    prompt_keys=True,
                    confirm_project_keys=True,
                    transport=RawHTTPTransport(allow_paid=True, timeout_seconds=60),
                )
        self.assertFalse(self.review.exists())
        self.assertFalse(self.f.directory.exists())
        for value in (True, 0, 601, float("inf")):
            self.record["timeout_seconds"] = value
            if value == float("inf"):
                self.launch_path.write_bytes(json.dumps(self.record).encode())
                pin = sha(self.launch_path.read_bytes())
            else:
                pin = self.save()
            with self.subTest(value=value), self.assertRaises(PolicyLaunchError):
                check_launch(self.launch_path, expected_sha256=pin)

    def test_console_and_receipt_failure_preserve_completed_outcome(self):
        pin = self.save()
        complete = {"state": "complete", "stop_code": None, "protected_roots": []}
        with (
            patch.object(policy_launch, "check_launch", return_value=complete),
            patch.object(policy_launch.pipeline, "_write", side_effect=OSError("SENTINEL")),
        ):
            result = launch(
                self.launch_path,
                expected_sha256=pin,
                receipt=self.receipt,
                notice=lambda text: (_ for _ in ()).throw(OSError("SENTINEL")),
            )
        self.assertEqual(result["status"], "complete")
        self.assertIs(result["receipt_saved"], False)
        self.assertFalse(self.receipt.exists())

    def test_completed_child_custody_does_not_import_or_project_scientific_metrics(self):
        import sys

        pin = self.save()

        def execute(spec, *, initial, **kwargs):
            if spec.role == "evaluator" and "judgments" in dict(spec.mounts)["/inputs"].parts:
                self.f.fixture.timeout_native_once = True
            return self.f.execute(spec, initial=initial, **kwargs)

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=execute),
        ):
            result = launch(
                self.launch_path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                receipt=self.receipt,
                notice=lambda text: None,
            )
        self.assertEqual(result["reason"], "unknown")
        self.assertEqual(self.f.fixture.physical_sends, 7)
        with (
            self.passive(),
            patch.dict(sys.modules, {"buddha.noveltybench_results": None}),
            patch.object(
                policy_launch.policy_results,
                "_analyze",
                side_effect=AssertionError("scientific projection"),
            ),
        ):
            checked = check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(checked["stop_code"], "unknown")
        self.assertEqual(checked["state"], "partial")

    def test_nonpaying_summary_is_not_blocked_by_exhausted_attempt_capacity(self):
        from buddha.authorization import Authorization

        self.f.authority = self.f.fixture.authority = Authorization.create(
            self.root / "six-attempt-authorization.sqlite3",
            authorization_id="six-synthetic",
            budget_microusd=1_000_000,
            max_calls=6,
            scope="policy study: " + self.f.study.fingerprint(),
        )
        terms = self.f.authority.summary()
        self.f.record["authorization"] = {
            "path": str(self.f.authority.path),
            "id": terms["authorization_id"],
            "terms_sha256": terms["terms_sha256"],
            "scope": terms["scope"],
        }
        self.f.descriptor.write_bytes(_json(self.f.record))
        self.h.record["requested_terms"]["max_calls"] = 6
        self.proposal_sha = self.h.save()
        self.approval.update(
            proposal_sha256=self.proposal_sha,
            max_calls=6,
            authorization=self.f.record["authorization"],
        )
        self.record["proposal"] = self.h.reference(self.h.handoff)
        self.record["execution"] = self.h.reference(self.f.descriptor)
        pin = self.save()

        def execute(spec, *, initial, **kwargs):
            if spec.role == "evaluator" and initial["command"]["index"] == 2:
                return self.f.fixture.agent.execution(exit_code=1)
            return self.f.execute(spec, initial=initial, **kwargs)

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=execute),
        ):
            result = launch(
                self.launch_path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                notice=lambda text: None,
            )
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(self.f.fixture.physical_sends, 6)
        with self.passive():
            checked = check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(Path(checked["next_owner"]).name, "3")
        self.assertIsNone(checked["stop_code"])
        self.assertEqual(checked["funding"]["operation_count"], 6)

    def test_actual_controller_cancel_preserves_exact_partial_when_receipt_write_fails(self):
        pin = self.save()
        real_write = policy_launch.pipeline._write

        def write(path, raw):
            if path == self.receipt:
                raise OSError("simulated receipt I/O")
            return real_write(path, raw)

        def execute(spec, *, initial, **kwargs):
            if spec.role == "agent" and initial["task_index"] == 1:
                raise KeyboardInterrupt
            return self.f.execute(spec, initial=initial, **kwargs)

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=execute),
            patch.object(policy_launch.pipeline, "_write", side_effect=write),
        ):
            with self.assertRaises(policy_run.PolicyRunInterrupted) as caught:
                launch(
                    self.launch_path,
                    expected_sha256=pin,
                    live=True,
                    confirm_project_keys=True,
                    receipt=self.receipt,
                    notice=lambda text: None,
                )
        partial = caught.exception.partial
        self.assertEqual(partial["reason"], "cancelled")
        self.assertEqual(
            json.loads((self.f.directory / partial["observation"]).read_bytes()), partial
        )
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.f.fixture.physical_sends, 2)

    def test_heartbeat_starts_during_slow_check_with_unknown_accounting(self):
        import threading

        pin = self.save()
        ticked = threading.Event()
        notices = []

        def notice(text):
            notices.append(text)
            if "Phase:" in text:
                ticked.set()

        def checking(*args, **kwargs):
            self.assertTrue(ticked.wait(timeout=2))
            raise PolicyLaunchError("synthetic stopped check")

        with patch.object(policy_launch, "check_launch", side_effect=checking):
            with self.assertRaises(PolicyLaunchError):
                launch(
                    self.launch_path,
                    expected_sha256=pin,
                    notice=notice,
                    receipt=self.receipt,
                    heartbeat_seconds=0.01,
                )
        self.assertIn("Checking", notices[0])
        self.assertTrue(any("elapsed" in text and "accounting unknown" in text for text in notices))

    def test_retired_unsealed_future_owner_stops_before_keys_without_banning_zero_op_preallocation(
        self,
    ):
        from datetime import UTC, datetime

        from buddha import baseline

        pin = self.save()
        checked = check_launch(self.launch_path, expected_sha256=pin)
        review = {
            "checked_on": datetime.now(UTC).date().isoformat(),
            "credential_sha256": {"openai": sha(gateway_fixtures.KEY.encode())},
            "account_scope": self.approval["account_scope"],
        }
        self.review.write_bytes(_json(review))
        bindings = {Path(path): digest for path, digest in checked["bindings"].items()}
        bindings[self.review] = sha(self.review.read_bytes())
        policy_run.prepare_study(
            self.f.directory,
            descriptor=self.f.descriptor,
            authorization=self.f.authority,
            review=review,
            input_bindings=bindings,
        )
        initial = json.loads(
            (self.f.directory / "cells/0/baseline/owners/0/manifest.json").read_bytes()
        )
        controls = {
            Path(item["path"]): item["sha256"]
            for item in initial["invocation"]["inputs"]
            if not Path(item["path"]).is_relative_to(self.f.directory)
            or item["path"] == str(self.f.directory / "context.json")
        }
        execution = policy_run._configuration(self.f.record["study"], self.f.record["baseline"])
        future = policy_run._materialize(self.f.directory, 1, self.f.study.schedule()[1], execution)
        child = future.parent / "baseline"
        baseline.prepare_baseline(
            child,
            descriptor=future,
            authorization=self.f.authority,
            review=review,
            input_files=list(controls),
            expected_input_hashes=controls,
        )
        with self.passive():
            allowed = check_launch(self.launch_path, expected_sha256=pin)
        self.assertIsNone(allowed["stop_code"])
        manifest = json.loads((child / "owners/0/manifest.json").read_bytes())
        self.f.authority.deactivate(manifest["run_id"], "explicit offline retirement")
        with self.passive():
            stopped = check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(stopped["stop_code"], "inactive")
        self.assertEqual(self.f.fixture.physical_sends, 0)
        with (
            patch("getpass.getpass", side_effect=AssertionError("key entry")),
            patch.object(policy_run, "run_study", side_effect=AssertionError("worker")),
        ):
            result = launch(
                self.launch_path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                prompt_keys=True,
                notice=lambda text: None,
            )
        self.assertEqual(result["reason"], "inactive")
