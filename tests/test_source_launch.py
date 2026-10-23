"""Protected source launching: original custody, synthetic workers and HTTPS."""

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
import test_source_search as search_fixtures

from buddha.gateway import RawHTTPTransport
from buddha.releases import _json

WITNESS_POLICY = {
    "format": "buddha.source-mutation-witness.v1",
    "task_policy": "first_ordered_development_task",
    "depth": 1,
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourcePublicResultTests(unittest.TestCase):
    def test_fixed_host_stop_reasons_retain_exact_observation_reference(self):
        from buddha.source_launch import SourceLaunchError, _public_result

        # Pure public-shape check; this does not reproduce these stops end to end.
        for reason in ("owner_prefix", "quota"):
            record = {
                "status": "incomplete",
                "reason": reason,
                "observation": "observations/7.json",
                "iteration": 1,
                "stage": "proposal",
            }
            with self.subTest(reason=reason):
                self.assertEqual(_public_result(record), record)
        with self.assertRaises(SourceLaunchError):
            _public_result(record | {"reason": "UNTRUSTED-RAW-ERROR"})

    def test_no_eligible_parent_is_explicit_without_changing_old_completion_receipts(self):
        from buddha.source_launch import _public_result

        self.assertEqual(_public_result({"status": "complete"}), {"status": "complete"})
        self.assertEqual(
            _public_result({"status": "complete", "reason": "bounded_iterations_complete"}),
            {"status": "complete"},
        )
        self.assertEqual(
            _public_result({"status": "complete", "reason": "no_parent_eligible"}),
            {"status": "complete", "reason": "no_parent_eligible"},
        )


class SourceInterruptionTests(unittest.TestCase):
    def test_original_controller_cancellation_carries_detached_saved_observation(self):
        f = search_fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(f.doCleanups)
        f.prepare()
        with (
            patch("buddha.source_screen.run_source_screen", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt) as caught,
        ):
            f.run_api(f.directory, transport=RawHTTPTransport(allow_paid=False))
        path = f.directory / "observations/0.json"
        saved = json.loads(path.read_bytes())
        self.assertEqual(saved["reason"], "cancelled")
        self.assertEqual(caught.exception.partial, saved)
        caught.exception.partial["reason"] = "changed by caller"
        self.assertEqual(json.loads(path.read_bytes())["reason"], "cancelled")
        self.assertEqual(f.engine.physical_sends, 0)

    def test_original_controller_protocol_stop_carries_detached_saved_observation(self):
        f = search_fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(f.doCleanups)
        f.prepare()
        with (
            patch("buddha.source_screen.run_source_screen", side_effect=ValueError("UNSAFE-TEXT")),
            self.assertRaises(f.Error) as caught,
        ):
            f.run_api(f.directory, transport=RawHTTPTransport(allow_paid=False))
        path = f.directory / "observations/0.json"
        saved = json.loads(path.read_bytes())
        self.assertEqual(saved["reason"], "protocol")
        self.assertEqual(caught.exception.partial, saved)
        caught.exception.partial["reason"] = "changed by caller"
        self.assertEqual(json.loads(path.read_bytes())["reason"], "protocol")
        self.assertNotIn("UNSAFE-TEXT", path.read_text())
        self.assertEqual(f.engine.physical_sends, 0)


class SourceLaunchTests(unittest.TestCase):
    def setUp(self):
        # A missing interface is setup evidence, not a behavioral failure.
        from buddha import source_handoff, source_launch

        self.api = source_launch
        self.Error = source_launch.SourceLaunchError
        self.f = search_fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(self.f.doCleanups)
        if self._testMethodName.startswith("test_real_"):
            # One task exercises launcher custody; source-search/state suites cover task prefixes.
            record = self.f.seed.to_record()
            record["selected_ids"] = ["1"]
            self.f.seed = self.f.h.screen(record)
            self.f.authority = self.f.h.authority(self.f.seed)
        self.root = self.f.root
        self.review = self.root / "source-launch-review.json"
        self.proposal_path = self.root / "source-proposal.json"
        self.approval_path = self.root / "source-approval.json"
        self.launch_path = self.root / "source-launch.json"
        self.receipt = self.root / "source-launch-receipt.json"
        self.control = self.root / "reviewed-source-protocol.md"
        self.control.write_bytes(b"One fixed development experiment; synthetic credentials only.\n")
        generation = self.f.seed.to_record()["generation"]
        runtime = Path(generation["runtime"]["path"])
        terms = self.f.authority.summary()
        self.proposal = {
            "format": "buddha.source-handoff.v1",
            "seed_screen": self.f.seed.to_record(),
            "proposal_template": copy.deepcopy(self.f.template),
            "spec": self.f.spec.to_record(),
            "expected_runtime_sha256": self.f.engine.candidate.expected_runtime,
            "source_sha256": {
                str(path): sha(path.read_bytes())
                for path in (*source_handoff._sources(), runtime, self.control)
            },
            "requested_terms": {key: terms[key] for key in ("budget_microusd", "max_calls")},
        }
        self.proposal_path.write_bytes(_json(self.proposal))
        self.proposal_sha = sha(self.proposal_path.read_bytes())
        self.approval = {
            "format": "buddha.source-approval.v1",
            "proposal_sha256": self.proposal_sha,
            "comparison_key": self.f.seed.comparison_key(),
            "directory": str(self.f.directory),
            "review": str(self.review),
            "authorization": {
                "path": str(self.f.authority.path),
                "id": terms["authorization_id"],
                "terms_sha256": terms["terms_sha256"],
                "scope": terms["scope"],
            },
            **self.proposal["requested_terms"],
            "account_scope": "Synthetic standard/default public PAYG; no account overrides",
        }
        self.record = {
            "format": "buddha.source-launch.v1",
            "proposal": self.reference(self.proposal_path),
            "approval": {},
            "directory": str(self.f.directory),
            "review": str(self.review),
            "source_sha256": {
                str(path): sha(path.read_bytes()) for path in source_launch._sources()
            },
            "timeout_seconds": 300,
        }

    @staticmethod
    def reference(path):
        return {"path": str(path), "sha256": sha(path.read_bytes())}

    def save(self):
        self.approval_path.write_bytes(_json(self.approval))
        self.record["approval"] = self.reference(self.approval_path)
        self.launch_path.write_bytes(_json(self.record))
        return sha(self.launch_path.read_bytes())

    def witness_handoff(self):
        self.proposal.update(
            format="buddha.source-handoff.v2", mutation_witness=copy.deepcopy(WITNESS_POLICY)
        )
        self.proposal_path.write_bytes(_json(self.proposal))
        self.proposal_sha = sha(self.proposal_path.read_bytes())
        self.approval["proposal_sha256"] = self.proposal_sha
        self.record["proposal"] = self.reference(self.proposal_path)

    def snapshot(self):
        return {
            str(path.relative_to(self.root)): sha(path.read_bytes())
            for path in self.root.rglob("*")
            if path.is_file()
        }

    @contextmanager
    def passive(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("passive source check used credentials, a writer or execution")

        with ExitStack() as stack:
            for name in (
                "buddha.authorization.Authorization.__init__",
                "buddha.authorization.Authorization.summary",
                "buddha.gateway.Gateway.__init__",
                "buddha.ledger.Ledger.__init__",
                "buddha.source_search.prepare_source_search",
                "buddha.source_search.run_source_search",
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
            return self.api.check_launch(self.launch_path, expected_sha256=pin)

    def run_launch(self, pin, *, receipt=None):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=self.f.execute),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("unexpected HTTPS")),
        ):
            return self.api.launch(
                self.launch_path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                receipt=self.receipt if receipt is None else receipt,
                transport=RawHTTPTransport(
                    allow_paid=True, timeout_seconds=self.record["timeout_seconds"]
                ),
                notice=lambda text: None,
            )

    def test_fresh_check_is_passive_and_binds_original_funding_and_destination(self):
        pin = self.save()
        before = self.snapshot()
        with patch.dict(os.environ, {}, clear=True), self.passive():
            checked = self.api.check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(checked["format"], "buddha.source-launch-check.v1")
        self.assertEqual(checked["state"], "fresh")
        self.assertIsNone(checked["stop_code"])
        self.assertEqual(checked["directory"], str(self.f.directory))
        self.assertEqual(checked["authorization_path"], str(self.f.authority.path))
        self.assertEqual(checked["review_path"], str(self.review))
        self.assertIsNone(checked["review"])
        self.assertEqual(checked["bindings"][str(self.launch_path)], pin)
        self.assertEqual(checked["bindings"][str(self.proposal_path)], self.proposal_sha)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.f.directory.exists())
        self.assertFalse(self.review.exists())

    def test_returned_bindings_are_detached(self):
        checked = self.check()
        checked["bindings"].clear()
        again = self.check()
        self.assertIn(str(self.proposal_path), again["bindings"])

    def test_wrong_caller_pin_and_malformed_json_refuse_without_keys(self):
        self.save()
        with self.passive(), self.assertRaises(self.Error):
            self.api.check_launch(self.launch_path, expected_sha256="0" * 64)
        for raw in (b"{}", b"{", b'{"format":1,"format":2}', b'{"format":NaN}'):
            with self.subTest(raw=raw):
                self.launch_path.write_bytes(raw)
                with self.passive(), self.assertRaises(self.Error):
                    self.api.check_launch(self.launch_path, expected_sha256=sha(raw))
        self.assertFalse(self.f.directory.exists())

    def test_approval_cannot_rebind_destination_actual_terms_or_scope(self):
        changes = [
            ("directory", str(self.root / "replacement-run")),
            ("review", str(self.root / "replacement-review.json")),
            ("proposal_sha256", "0" * 64),
            ("comparison_key", "0" * 64),
            ("budget_microusd", 2),
            ("max_calls", False),
            ("authorization", self.approval["authorization"] | {"id": "another-id"}),
            ("authorization", self.approval["authorization"] | {"scope": "another-scope"}),
            ("authorization", self.approval["authorization"] | {"terms_sha256": "0" * 64}),
        ]
        for field, value in changes:
            original = copy.deepcopy(self.approval)
            self.approval[field] = value
            try:
                with self.subTest(field=field), self.assertRaises(self.Error):
                    self.check()
            finally:
                self.approval = original
        self.assertFalse(self.f.directory.exists())

    def test_required_launch_pin_and_conflicting_control_are_rejected(self):
        name = str(Path(self.api.__file__).absolute())
        original = self.record["source_sha256"].pop(name)
        with self.assertRaises(self.Error):
            self.check()
        self.record["source_sha256"][name] = original
        self.record["source_sha256"][str(self.control)] = "0" * 64
        with self.assertRaises(self.Error):
            self.check()
        self.assertFalse(self.review.exists())

    def test_input_drift_and_partial_preparation_are_not_adopted(self):
        pin = self.save()
        original = self.control.read_bytes()
        self.control.write_bytes(original + b"changed")
        with self.passive(), self.assertRaises(self.Error):
            self.api.check_launch(self.launch_path, expected_sha256=pin)
        self.control.write_bytes(original)
        self.f.directory.mkdir()
        with self.passive(), self.assertRaises(self.Error):
            self.api.check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(list(self.f.directory.iterdir()), [])

    def test_selected_component_and_authority_cannot_be_output_destinations(self):
        agent = self.proposal["seed_screen"]["generation"]["roots"]["agent"]
        for destination in (agent, str(self.f.authority.path), str(self.control)):
            original = self.record["directory"], self.approval["directory"]
            self.record["directory"] = self.approval["directory"] = destination
            try:
                with self.subTest(destination=destination), self.assertRaises(self.Error):
                    self.check()
            finally:
                self.record["directory"], self.approval["directory"] = original

    def test_closed_launch_schema_and_finite_bounded_timeout(self):
        for value in (True, 0, -1, 601, "300", None):
            original = self.record["timeout_seconds"]
            self.record["timeout_seconds"] = value
            try:
                with self.subTest(timeout=value), self.assertRaises(self.Error):
                    self.check()
            finally:
                self.record["timeout_seconds"] = original
        self.record["receipt"] = str(self.root / "untrusted-output.json")
        with self.assertRaises(self.Error):
            self.check()
        self.assertFalse((self.root / "untrusted-output.json").exists())

    def test_live_and_manual_project_confirmation_precede_any_key_entry(self):
        pin = self.save()
        for flags in ({}, {"live": True}, {"confirm_project_keys": True}):
            with (
                self.subTest(flags=flags),
                patch(
                    "buddha.credentials.key_environment", side_effect=AssertionError("key entry")
                ),
                self.assertRaises(self.Error),
            ):
                self.api.launch(self.launch_path, expected_sha256=pin, **flags)
        self.assertFalse(self.f.directory.exists())
        self.assertFalse(self.review.exists())

    def test_pre_key_failure_records_fixed_reason_and_immediate_phase(self):
        pin = self.save()
        notices = []
        with patch.object(self.api, "check_launch", side_effect=self.Error("SECRET-ERROR-TEXT")):
            with self.assertRaises(self.Error):
                self.api.launch(
                    self.launch_path,
                    expected_sha256=pin,
                    live=True,
                    confirm_project_keys=True,
                    receipt=self.receipt,
                    notice=notices.append,
                )
        receipt = json.loads(self.receipt.read_bytes())
        self.assertEqual(receipt["format"], "buddha.source-launch-receipt.v1")
        self.assertEqual(receipt["status"], "stopped")
        self.assertEqual(receipt["phase"], "checking")
        self.assertTrue(receipt["reason"])
        self.assertTrue(notices and "Checking" in notices[0])
        self.assertNotIn("SECRET-ERROR-TEXT", self.receipt.read_text())
        original = self.receipt.read_bytes()
        with self.assertRaises(self.Error):
            self.api.launch(self.launch_path, expected_sha256=pin, receipt=self.receipt)
        self.assertEqual(self.receipt.read_bytes(), original)

    def test_receipt_cannot_overwrite_original_controls_or_authority(self):
        pin = self.save()
        for destination in (
            self.launch_path,
            self.proposal_path,
            self.approval_path,
            self.f.authority.path,
            self.control,
        ):
            original = destination.read_bytes()
            with self.subTest(destination=destination), self.assertRaises(self.Error):
                self.api.launch(
                    self.launch_path,
                    expected_sha256=pin,
                    live=True,
                    confirm_project_keys=True,
                    receipt=destination,
                )
            self.assertEqual(destination.read_bytes(), original)
        with self.assertRaises(self.Error):
            self.api.launch(
                self.launch_path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                receipt=self.review,
            )
        self.assertFalse(self.review.exists())

    def test_cli_unknown_arguments_never_echo_potential_credentials(self):
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location("src02_operator_test", self.api._entrypoint())
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        output, errors = io.StringIO(), io.StringIO()
        with patch("sys.stdout", output), patch("sys.stderr", errors):
            code = module.main(["--accidental-secret=FAKE-SENTINEL"])
        self.assertEqual(code, 2)
        self.assertNotIn("FAKE-SENTINEL", output.getvalue() + errors.getvalue())

    def test_hidden_key_cleanup_and_post_prompt_drift_stop_before_preparation(self):
        pin = self.save()
        sentinel = "synthetic-key-for-hidden-source-entry"
        original = self.control.read_bytes()

        def entered(*args, **kwargs):
            self.control.write_bytes(original + b"changed during hidden key entry")
            return sentinel

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stderr.isatty", return_value=True),
            patch("getpass.getpass", side_effect=entered),
            patch(
                "buddha.source_search.prepare_source_search", side_effect=AssertionError("prepare")
            ),
        ):
            with self.assertRaises(self.Error):
                self.api.launch(
                    self.launch_path,
                    expected_sha256=pin,
                    live=True,
                    prompt_keys=True,
                    confirm_project_keys=True,
                    receipt=self.receipt,
                    notice=lambda text: None,
                )
            self.assertNotIn("OPENAI_API_KEY", os.environ)
        self.assertFalse(self.review.exists())
        self.assertFalse(self.f.directory.exists())
        self.assertNotIn(sentinel, self.receipt.read_text())

    def test_real_controller_completes_once_and_repeats_keylessly(self):
        pin = self.save()
        result = self.run_launch(pin)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(json.loads(self.receipt.read_bytes()), result)
        saved_review = json.loads(self.review.read_bytes())
        self.assertEqual(saved_review["format"], "buddha.account-review.v2")
        self.assertEqual(saved_review["credential_context"], pin)
        self.assertEqual(saved_review["account_scope"], self.approval["account_scope"])
        self.assertNotIn("credential_sha256", saved_review)
        self.assertNotIn(gateway_fixtures.KEY, self.review.read_text())
        report = json.loads((self.f.directory / "report.json").read_bytes())
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["decisions"][0]["status"], "candidate_execution_failed")
        before = self.snapshot()
        sends = self.f.engine.physical_sends
        self.assertGreater(sends, 0)
        summary = self.f.authority.summary()
        self.assertEqual(summary["reserved_microusd"], 0)
        self.assertFalse(any(owner["active"] for owner in summary["runs"]))
        with patch.dict(os.environ, {}, clear=True), self.passive():
            checked = self.api.check_launch(self.launch_path, expected_sha256=pin)
            repeated = self.api.launch(self.launch_path, expected_sha256=pin, notice=lambda _: None)
        self.assertEqual(checked["state"], "complete")
        self.assertEqual(repeated["status"], "complete")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.f.engine.physical_sends, sends)
        review_raw = self.review.read_bytes()
        for field, value in (
            ("credential_context", "0" * 64),
            ("account_scope", "another account scope"),
            ("format", "buddha.account-review.v1"),
        ):
            self.review.write_bytes(_json(saved_review | {field: value}))
            try:
                with self.subTest(field=field), self.passive(), self.assertRaises(self.Error):
                    self.api.check_launch(self.launch_path, expected_sha256=pin)
            finally:
                self.review.write_bytes(review_raw)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.f.engine.physical_sends, sends)

    def test_real_unknown_result_remains_partial_and_cannot_replace_original_owners(self):
        pin = self.save()
        self.f.proposal_timeout_once = True
        result = self.run_launch(pin)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["reason"], "unknown")
        self.assertEqual(json.loads(self.receipt.read_bytes()), result)
        observation = json.loads((self.f.directory / result["observation"]).read_bytes())
        self.assertEqual(observation["status"], "incomplete")
        self.assertEqual(observation["reason"], "unknown")
        summary = self.f.authority.summary()
        self.assertGreater(summary["reserved_microusd"], 0)
        before = self.snapshot()
        sends = self.f.engine.physical_sends
        with patch.dict(os.environ, {}, clear=True), self.passive():
            checked = self.api.check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(checked["state"], "prepared")
        self.assertEqual(checked["stop_code"], "unknown")
        with patch("buddha.credentials.key_environment", side_effect=AssertionError("key entry")):
            stopped = self.api.launch(
                self.launch_path,
                expected_sha256=pin,
                live=True,
                confirm_project_keys=True,
                notice=lambda _: None,
            )
        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual(stopped["phase"], "funding")
        self.assertEqual(stopped["reason"], "unknown")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.f.engine.physical_sends, sends)
        after = self.f.authority.summary()
        for field in ("operation_count", "spent_microusd", "reserved_microusd", "runs"):
            self.assertEqual(after[field], summary[field])

    def test_witness_handoff_check_uses_existing_approval_and_launch_schema(self):
        self.witness_handoff()
        pin = self.save()
        before = self.snapshot()
        with self.passive():
            checked = self.api.check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(checked["state"], "fresh")
        self.assertEqual(checked["proposal"]["format"], "buddha.source-handoff.v2")
        self.assertEqual(checked["proposal"]["mutation_witness"], WITNESS_POLICY)
        self.assertEqual(checked["bindings"][str(self.proposal_path)], self.proposal_sha)
        self.assertEqual(self.record["format"], "buddha.source-launch.v1")
        self.assertEqual(self.approval["format"], "buddha.source-approval.v1")
        self.assertEqual(self.snapshot(), before)

    def test_planned_witness_owners_are_exact_siblings_and_legacy_default_is_unchanged(self):
        directory, seed, iterations = self.f.directory, self.f.seed, 3
        legacy = self.api._planned_owners(directory, seed, iterations)
        self.assertEqual(
            self.api._planned_owners(directory, seed, iterations, mutation_witness=False), legacy
        )
        witnessed = self.api._planned_owners(directory, seed, iterations, mutation_witness=True)
        locations = [directory / "seed-witness"] + [
            directory / "iterations" / str(i) / "witness" for i in range(iterations)
        ]
        extra = {
            path / role / "owners/0" for path in locations for role in ("proposal", "generation")
        }
        self.assertEqual(witnessed, legacy | extra)
        self.assertEqual(len(witnessed) - len(legacy), 8)
        stages = len(seed.to_record()["stages"])
        self.assertEqual(len(legacy), 4 * len(seed.tasks.tasks) * (1 + stages) + 3)
        self.assertFalse(any("screen/witness" in path.as_posix() for path in witnessed))
        for value in (None, 0, 1, "true"):
            with self.subTest(value=value), self.assertRaises(self.Error):
                self.api._planned_owners(directory, seed, iterations, mutation_witness=value)

    def test_new_handoff_rejoins_actual_required_preparation_before_execution(self):
        from buddha import source_launch_state, source_search

        self.witness_handoff()
        pin = self.save()
        with (
            patch(
                "buddha.source_search.prepare_source_search",
                wraps=source_search.prepare_source_search,
            ) as prepared,
            patch(
                "buddha.source_launch_state.inspect_prepared_search",
                wraps=source_launch_state.inspect_prepared_search,
            ) as inspected,
            patch("buddha.source_search.run_source_search", side_effect=KeyboardInterrupt) as run,
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_launch(pin)
        self.assertIs(prepared.call_args.kwargs["mutation_witness"], True)
        self.assertIs(inspected.call_args.kwargs["mutation_witness"], True)
        run.assert_called_once()
        manifest = json.loads((self.f.directory / "manifest.json").read_bytes())
        self.assertEqual(manifest["format"], "buddha.source-search-manifest.v3")
        self.assertEqual(manifest["mutation_witness"], WITNESS_POLICY)
        self.assertEqual(self.f.engine.physical_sends, 0)
        before = self.snapshot()
        with self.passive():
            checked = self.api.check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(checked["state"], "prepared")
        self.assertEqual(self.snapshot(), before)

    def test_new_handoff_cannot_dispatch_coherently_prepared_task_only_downgrade(self):
        from buddha import source_search

        self.witness_handoff()
        pin = self.save()
        original = source_search.prepare_source_search

        def downgrade(*args, **kwargs):
            self.assertIs(kwargs["mutation_witness"], True)
            kwargs["mutation_witness"] = False
            return original(*args, **kwargs)

        with (
            patch("buddha.source_search.prepare_source_search", side_effect=downgrade),
            patch(
                "buddha.source_search.run_source_search",
                side_effect=AssertionError("no execution of downgraded preparation"),
            ) as run,
            self.assertRaises(self.Error),
        ):
            self.run_launch(pin)
        run.assert_not_called()
        self.assertEqual(self.f.engine.physical_sends, 0)
        self.assertTrue(
            (self.f.directory / "seed/tasks/0/generation/owners/0/manifest.json").is_file()
        )
        manifest = json.loads((self.f.directory / "manifest.json").read_bytes())
        self.assertEqual(manifest["format"], "buddha.source-search-manifest.v2")
        self.assertNotIn("mutation_witness", manifest)
        self.assertEqual(self.f.authority.summary()["operation_count"], 0)
        before = self.snapshot()
        with self.passive(), self.assertRaises(self.Error):
            self.api.check_launch(self.launch_path, expected_sha256=pin)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
