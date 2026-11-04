"""Passive original-owner readiness, without constructing a spending interface."""

import copy
import json
import os
import unittest
from unittest.mock import patch

import test_source_search
from test_source_mutation_witness import _Harness

from buddha import candidate_generation, native_pipeline
from buddha.gateway import execution_identity
from buddha.releases import _json
from buddha.source_launch_state import inspect_prepared_search
from buddha.source_search import SourceSearchError, _sources


class SourceLaunchStateTests(unittest.TestCase):
    def fixture(self):
        h = test_source_search.SourceSearchTests("runTest")
        h.fixture(iterations=1)
        self.addCleanup(h.doCleanups)
        return h

    def inspect(self, h, **changes):
        values = {
            "seed_screen": h.seed,
            "proposal_template": h.template,
            "spec": h.spec,
            "review": h.engine.fixture.review,
            "expected_runtime_sha256": h.engine.candidate.expected_runtime,
            "input_bindings": {},
            "mutation_witness": getattr(h, "mutation_witness", False),
            "source_copy": False,
        }
        before = h.h.files(h.directory), h.authority.path.read_bytes(), h.engine.physical_sends
        with (
            h.h.readonly(),
            patch.dict(os.environ, {}, clear=True),
            patch("socket.socket", side_effect=AssertionError("passive socket")),
        ):
            try:
                return inspect_prepared_search(h.directory, h.authority.path, **(values | changes))
            finally:
                self.assertEqual(
                    (
                        h.h.files(h.directory),
                        h.authority.path.read_bytes(),
                        h.engine.physical_sends,
                    ),
                    before,
                )

    def test_original_fresh_owner_is_passive_and_stable_and_all_locks_are_busy(self):
        h = self.fixture()
        h.prepare()
        first = self.inspect(h)
        self.assertEqual(first["state"], "prepared")
        self.assertEqual(first["next_role"], "generation")
        self.assertEqual(first["next_owner"], str(h.directory / "seed/tasks/0/generation/owners/0"))
        self.assertFalse(first["busy"])
        self.assertFalse(first["inactive_pending"])
        self.assertEqual(self.inspect(h), first)
        lock = h.directory / "seed/tasks/0/generation/running.lock"
        lock.write_bytes(b"1234567")
        busy = self.inspect(h)
        self.assertTrue(busy["busy"])
        self.assertNotEqual(busy["state_sha256"], first["state_sha256"])
        self.assertEqual(lock.read_bytes(), b"1234567")
        lock.unlink()
        after = self.inspect(h)
        self.assertFalse(after["busy"])
        self.assertNotEqual(after["state_sha256"], first["state_sha256"])
        self.assertEqual(self.inspect(h), after)

    def test_all_approved_initial_fields_and_external_controls_stay_original(self):
        h = self.fixture()
        control = h.root / "approved-launch.json"
        control.write_bytes(b"{}")
        bindings = {control: test_source_search.sha(b"{}")}
        h.prepare(input_bindings=bindings)
        self.inspect(h, input_bindings=bindings)
        review = copy.deepcopy(h.engine.fixture.review)
        review["account_scope"] += "; changed"
        template = copy.deepcopy(h.template)
        template["budget_microusd"] += 1
        for changes in (
            {"input_bindings": {}},
            {"input_bindings": {control: "0" * 64}},
            {"review": review},
            {"proposal_template": template},
            {"spec": h.Spec.from_bytes(_json(h.specification(iterations=2)))},
            {"expected_runtime_sha256": "0" * 64},
        ):
            with self.subTest(changes=list(changes)), self.assertRaises(SourceSearchError):
                self.inspect(h, **({"input_bindings": bindings} | changes))
        helper = next(path for path in _sources() if path.name == "source_search.py")
        with self.assertRaises(SourceSearchError):
            self.inspect(h, input_bindings=bindings | {helper: "0" * 64})

    def test_inactive_unfinished_original_owner_is_reported_without_reactivation(self):
        h = self.fixture()
        h.prepare()
        owner = h.authority.summary()["runs"][0]
        h.authority.deactivate(owner["run_id"], "test-only stop; no completion seal")
        result = self.inspect(h)
        self.assertTrue(result["inactive_pending"])
        self.assertEqual(result["next_owner"], owner["directory"])
        self.assertFalse(h.authority.summary()["runs"][0]["active"])

    def test_orphan_owner_and_future_task_are_rejected_before_execution(self):
        h = self.fixture()
        h.prepare()
        orphan = h.directory / "seed/tasks/0/generation/owners/1"
        orphan.mkdir()
        with self.assertRaises(SourceSearchError):
            self.inspect(h)
        orphan.rmdir()
        future = h.directory / "seed/tasks/9"
        future.mkdir()
        with self.assertRaises(SourceSearchError):
            self.inspect(h)

    def test_pending_native_readiness_retains_its_original_owner(self):
        h = self.fixture()
        h.prepare()
        h.engine.native_fail_once = True
        first = h.run_search()
        self.assertEqual(first["status"], "incomplete")
        before = h.authority.summary()
        native = self.inspect(h)
        self.assertEqual(native["next_role"], "native")
        self.assertFalse(native["inactive_pending"])
        self.assertEqual(h.authority.summary(), before)
        self.assertIn(native["next_owner"], {row["directory"] for row in before["runs"]})

    def test_pending_native_command_cannot_change_the_prescribed_flow(self):
        h = self.fixture()
        h.prepare()
        original = native_pipeline._native_descriptor

        def wrong_command(*args, **kwargs):
            path, inputs = original(*args, **kwargs)
            record = json.loads(path.read_bytes())
            command = record["worker"]["command"]
            command["module"] = "unapproved.module"
            command.pop("sha256")
            command["sha256"] = test_source_search.sha(_json(command))
            path.write_bytes(_json(record))
            return path, inputs

        with (
            patch("buddha.native_pipeline._native_descriptor", side_effect=wrong_command),
            patch("buddha.native_evaluation.run_evaluation", side_effect=ValueError("test stop")),
            self.assertRaises(SourceSearchError),
        ):
            h.run_search()
        native = h.directory / "seed/tasks/0/evaluation/owners/1"
        # This is the actual original, internally consistent owner prepared with
        # the wrong command. No manifest, local DB or grant was rewritten.
        execution_identity(native)
        self.assertEqual(h.engine.physical_sends, 2)
        with self.assertRaises(SourceSearchError):
            self.inspect(h)

    def test_witness_policy_requires_the_explicit_original_approval(self):
        legacy = self.fixture()
        legacy.prepare()
        with self.assertRaises(SourceSearchError):
            self.inspect(legacy, mutation_witness=True)
        for value in (None, 0, 1, "true"):
            with self.subTest(value=value), self.assertRaises(SourceSearchError):
                self.inspect(legacy, mutation_witness=value)
        witness = _Harness(self)
        witness.prepare()
        self.assertEqual(self.inspect(witness.case)["next_role"], "generation")
        with self.assertRaises(SourceSearchError):
            self.inspect(witness.case, mutation_witness=False)

    def test_pending_seed_witness_retains_original_owner_and_inactive_stop(self):
        witness = _Harness(self)
        witness.witness_callbacks, witness.interrupt_once = 1, True
        witness.prepare()
        witness.case.partial(witness.run())
        owner_path = witness.case.directory / "seed-witness/proposal/owners/0"
        result = self.inspect(witness.case)
        self.assertEqual((result["next_owner"], result["next_role"]), (str(owner_path), "proposal"))
        self.assertFalse(result["inactive_pending"])
        owner = next(
            row
            for row in witness.case.authority.summary()["runs"]
            if row["directory"] == str(owner_path)
        )
        witness.case.authority.deactivate(owner["run_id"], "test-only unfinished witness stop")
        stopped = self.inspect(witness.case)
        self.assertTrue(stopped["inactive_pending"])
        self.assertEqual(stopped["next_owner"], str(owner_path))
        self.assertFalse((witness.case.directory / "iterations/0").exists())

    def test_sealed_witness_publication_does_not_require_another_paid_attempt(self):
        witness = _Harness(self)
        witness.prepare()
        proposal = witness.case.directory / "seed-witness/proposal"
        generation = witness.case.directory / "seed-witness/generation"
        publish = native_pipeline.publish_complete

        def before_publication(path, *args, **kwargs):
            if path == proposal / "report.json":
                raise KeyboardInterrupt("synthetic sealed witness publication stop")
            return publish(path, *args, **kwargs)

        with (
            patch("buddha.native_pipeline.publish_complete", side_effect=before_publication),
            self.assertRaises(KeyboardInterrupt),
        ):
            witness.run()
        self.assertTrue((proposal / "completed/0.json").is_file())
        self.assertFalse((proposal / "report.json").exists())
        pending_publication = self.inspect(witness.case)
        self.assertEqual(
            (pending_publication["next_owner"], pending_publication["next_role"]), (None, None)
        )
        self.assertFalse(pending_publication["inactive_pending"])
        run_generation = candidate_generation.run_candidate_generation

        def before_generation(path, **kwargs):
            if path == generation:
                raise KeyboardInterrupt("synthetic original witness generation stop")
            return run_generation(path, **kwargs)

        with (
            patch(
                "buddha.candidate_generation.run_candidate_generation",
                side_effect=before_generation,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            witness.run()
        ready = self.inspect(witness.case)
        self.assertEqual(
            (ready["next_owner"], ready["next_role"]),
            (str(generation / "owners/0"), "generation"),
        )
        self.assertFalse(ready["inactive_pending"])
        self.assertFalse((witness.case.directory / "iterations/0").exists())

    def test_current_child_witness_precedes_decision_and_later_parent_selection(self):
        witness = _Harness(self, iterations=2)
        witness.prepare()
        improve = witness.case.execute_improvement
        owner_path = witness.case.directory / "iterations/0/witness/proposal/owners/0"

        def stop_child_witness(spec, initial, handle, source):
            if handle.__self__.gateway.directory == owner_path:
                witness.witness_callbacks, witness.interrupt_once = 1, True
            return improve(spec, initial, handle, source)

        witness.case.execute_improvement = stop_child_witness
        witness.case.partial(witness.run())
        self.assertTrue((witness.case.directory / "iterations/0/screen/report.json").is_file())
        self.assertFalse((witness.case.directory / "iterations/0/decision.json").exists())
        result = self.inspect(witness.case)
        self.assertEqual((result["next_owner"], result["next_role"]), (str(owner_path), "proposal"))
        self.assertFalse((witness.case.directory / "iterations/1").exists())

    def test_failed_seed_witness_has_no_later_paid_hint_before_final_publication(self):
        witness = _Harness(self)
        witness.modes[witness.case.seed.candidate_id] = "agent_error"
        witness.prepare()
        publish = native_pipeline.publish_complete

        def before_publication(path, *args, **kwargs):
            if path == witness.case.directory / "report.json":
                raise KeyboardInterrupt("synthetic no-parent final publication stop")
            return publish(path, *args, **kwargs)

        with (
            patch("buddha.native_pipeline.publish_complete", side_effect=before_publication),
            self.assertRaises(KeyboardInterrupt),
        ):
            witness.run()
        self.assertTrue((witness.case.directory / "seed-witness/report.json").is_file())
        self.assertFalse((witness.case.directory / "report.json").exists())
        result = self.inspect(witness.case)
        self.assertEqual((result["next_owner"], result["next_role"]), (None, None))
        self.assertFalse(result["inactive_pending"])
        self.assertFalse((witness.case.directory / "iterations/0").exists())
        sends = witness.case.engine.physical_sends
        completed = witness.run()
        self.assertEqual(
            (completed["status"], completed["reason"]), ("complete", "no_parent_eligible")
        )
        ready = self.inspect(witness.case)
        self.assertEqual((ready["state"], ready["reason"]), ("complete", "no_parent_eligible"))
        self.assertEqual(witness.case.engine.physical_sends, sends)

    def test_retained_witness_owner_keeps_its_exact_allocation_and_funded_manifest(self):
        from buddha import candidate_improvement
        from buddha.source_search import SourceSearchInterrupted

        def check(mode):
            witness = _Harness(self)
            case = witness.case
            witness.prepare()
            proposal = case.directory / "seed-witness/proposal"
            owner_path = proposal / "owners/0"
            prepare = candidate_improvement.prepare_candidate_improvement
            prepared = []

            def pause_after_original_prepare(path, **kwargs):
                if path != proposal:
                    return prepare(path, **kwargs)
                if mode == "wrong_allocation":
                    kwargs["budget_microusd"] += 1
                result = prepare(path, **kwargs)
                prepared.append(result)
                raise KeyboardInterrupt("synthetic original witness preparation stop")

            with (
                patch(
                    "buddha.candidate_improvement.prepare_candidate_improvement",
                    side_effect=pause_after_original_prepare,
                ),
                self.assertRaises(SourceSearchInterrupted) as stopped,
            ):
                witness.run()
            self.assertEqual(prepared, [proposal])
            self.assertEqual(stopped.exception.partial["stage"], "witness_proposal")
            self.assertTrue((owner_path / "manifest.json").is_file())
            self.assertFalse((proposal / "report.json").exists())
            self.assertFalse((case.directory / "iterations/0").exists())
            self.assertEqual(witness.improvements, [])
            # The real lower helper created a coherent original owner and
            # funding binding; no financial record or manifest was edited.
            execution_identity(owner_path)
            manifest = json.loads((owner_path / "manifest.json").read_bytes())
            if mode == "wrong_allocation":
                self.assertEqual(
                    manifest["settings"]["budget_microusd"],
                    case.template["budget_microusd"] + 1,
                )
                reason = "prepared owner changes its original treatment"
            else:
                # Positive control: the correctly prepared original owner
                # is accepted before only its temporary files are moved.
                ready = self.inspect(case)
                self.assertEqual(
                    (ready["next_owner"], ready["next_role"]),
                    (str(owner_path), "proposal"),
                )
                backup = case.root / "original-witness-owner-preserved"
                owner_path.rename(backup)
                self.assertTrue((backup / "manifest.json").is_file())
                self.assertTrue(
                    any(
                        row["directory"] == str(owner_path)
                        for row in case.authority.summary()["runs"]
                    )
                )
                reason = "a retained funded search owner is missing or replaced"
            before = (
                case.h.files(case.directory),
                case.authority.path.read_bytes(),
                case.engine.physical_sends,
                case.engine.workers,
            )
            with self.assertRaisesRegex(SourceSearchError, reason):
                self.inspect(case)

            def forbidden_worker(*args, **kwargs):
                raise AssertionError("retained witness failure reached a worker")

            case.execute = forbidden_worker
            with (
                patch(
                    "buddha.gateway.RawHTTPTransport.send_prepared",
                    side_effect=AssertionError("retained witness failure reached a send"),
                ) as send,
                self.assertRaisesRegex(SourceSearchError, reason),
            ):
                case.run_search()
            send.assert_not_called()
            self.assertEqual(
                (
                    case.h.files(case.directory),
                    case.authority.path.read_bytes(),
                    case.engine.physical_sends,
                    case.engine.workers,
                ),
                before,
            )

        for mode in ("wrong_allocation", "missing_owner"):
            with self.subTest(mode=mode):
                check(mode)


if __name__ == "__main__":
    unittest.main()
