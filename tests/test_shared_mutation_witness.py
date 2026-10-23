"""Shared bounded witnesses use real non-search scope and original stage owners.

Compose existing measured-screen and frozen-improver fixtures, not their tests.
The small caller below checks its declared controls and literal retained owner
grid; it is not the future finite-study controller or its complete schedule
validator. Workers and HTTPS are supplied fixtures, not confinement/model proof.
"""

import copy
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

LONG_ANSWER = "  BEGIN counted output\n" + "雪α full text  \n" * 500 + "END counted output  "
COUNTED_CHILD = (
    "# counted descendant authored by frozen I\n"
    "def generate(task, config, complete): return ['literal' for _ in range(task['count'])]\n"
    "def propose_improvement(parent, feedback, config, complete):\n"
    "    raise RuntimeError('supplied worker fixture only; never execute on host')\n"
)
WITNESS_CHILD = (
    "# validity grandchild, never a counted descendant\n"
    "def generate(task, config, complete): return ['witness' for _ in range(task['count'])]\n"
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SharedMutationWitnessTests(unittest.TestCase):
    def fixture(self, *, source_copy, callbacks=0):
        import test_frozen_improver
        import test_source_feedback
        import test_source_screen_outcome

        from buddha import source_search
        from buddha.releases import Release, _json, prepare_selection
        from buddha.source_feedback import (
            SourceFeedbackError,
            build_source_feedback,
            write_source_feedback,
        )

        self.api, self.Error = source_search, source_search.SourceSearchError
        self.outcome = test_source_screen_outcome.SourceScreenOutcomeTests("runTest")
        self.addCleanup(self.outcome.doCleanups)
        self.h = h = self.outcome.fixture()
        h.record["format"] = "buddha.source-screen.v2"
        self.scope = h.root / "finite-study"
        self.scope.mkdir()
        self.cell = self.scope / "cells" / "frozen-I" / "0"
        self.cell.mkdir(parents=True)
        self.location = self.cell / "capability-check"
        actor = h.root / "fixed-improver"
        actor.mkdir()
        self.improver_raw = test_frozen_improver.FrozenImproverTests.operator_source("fixed-I")
        self.improver_path = actor / "candidate.py"
        self.improver_path.write_bytes(self.improver_raw)
        self.improver_id = sha(_json({"candidate.py": sha(self.improver_raw)}))
        self.declaration = self.scope / "study.json"
        self.declaration.write_bytes(
            _json(
                {
                    "format": "test.finite-improver-study.v1",
                    "common": str(self.scope / "common"),
                    "cells": [str(self.cell)],
                    "fixed_improver_agent_sha256": self.improver_id,
                    "counted_applications": 1,
                    "mutation_witness": dict(source_search.MUTATION_WITNESS_POLICY),
                    "source_copy": source_copy,
                }
            )
        )
        runtime = h.engine.candidate.expected_runtime
        generation = h.record["generation"]
        parent_path = Path(generation["roots"]["agent"]) / generation["entrypoint"]
        self.controls = {
            path: sha(path.read_bytes())
            for path in [
                *source_search._sources(),
                Path(generation["runtime"]["path"]),
                self.declaration,
                self.improver_path,
                parent_path,
            ]
        }

        def reuse_measured_fixture(feedback):
            feedback.Error = SourceFeedbackError
            feedback.build_api, feedback.write_api = build_source_feedback, write_source_feedback
            feedback.h = h

        original_prepare = h.prepare

        def prepare_original_common(screen, directory=None, authority=None, **changes):
            self.assertIsNone(directory)
            return original_prepare(
                screen,
                self.scope / "common",
                authority,
                input_bindings=self.controls,
                **changes,
            )

        self.seam = test_frozen_improver.FrozenImproverTests("runTest")
        self.addCleanup(self.seam.doCleanups)
        # Create original evidence at its genuine common location. No completed
        # publication is relocated, and no SourceSearch record/state is made.
        with (
            patch.object(test_source_feedback.SourceFeedbackTests, "setUp", reuse_measured_fixture),
            patch.object(h, "prepare", side_effect=prepare_original_common),
        ):
            self.f = f = self.seam.fixture()
        self.base_screen = h.Screen.from_bytes((self.scope / "common/screen.json").read_bytes())
        self.authority = h.authorities[0]
        f.f.authority = self.authority
        self.common_reference = json.loads((f.packet / "provenance.json").read_bytes())["reference"]
        self.assertEqual(self.common_reference["directory"], str(self.scope / "common"))
        self.assertEqual(self.common_reference["authorization"], str(self.authority.path))

        # Configure the existing real detached-I stage with an I file that was
        # already bound before common measurement; reuse its worker/role checks.
        f.roots = self.seam.parent_roots | {"agent": actor}
        f.selection = prepare_selection(
            Release.from_record(self.seam.parent_selection["release"]),
            f.roots,
            capabilities=self.seam.parent_selection["capabilities"],
        )
        self.seam.operator_raw, self.seam.operator_id = self.improver_raw, self.improver_id
        self.seam.target_path = self.seam.parent_path
        f.record = copy.deepcopy(self.seam.base_recipe)
        f.record.update(
            format="buddha.candidate-improvement.v2",
            entrypoint="candidate.py",
            parent_agent_sha256=self.seam.parent_id,
            task_parent={"path": str(self.seam.parent_path), "sha256": sha(self.seam.parent_raw)},
        )
        f.record["executor"]["mounts"] = [
            ["/agent", str(actor)],
            ["/runner", str(f.roots["runner"])],
        ]
        f.directory, f.descriptor = self.cell / "proposal", self.cell / "proposal.json"
        f.descriptor.write_bytes(_json(f.record))
        f.prepare(input_files=list(self.controls), expected_input_hashes=self.controls)
        self.counted_proposal = self.seam.run_stage(
            {"source": COUNTED_CHILD, "hypothesis": "One supplied counted descendant."},
            callbacks=1,
        )
        self.assertEqual(self.counted_proposal["disposition"], "materialized")
        self.seam.assert_roles(self.counted_proposal)
        self.counted_stage = f.directory

        record = self.base_screen.to_record()
        generation = record["generation"]
        roots = {name: Path(path) for name, path in generation["roots"].items()}
        roots["agent"] = Path(self.counted_proposal["child"]["directory"])
        generation["selection"] = prepare_selection(
            h.engine.candidate.release,
            roots,
            capabilities=generation["selection"]["capabilities"],
        ).to_record()
        generation["roots"] = {name: str(path) for name, path in roots.items()}
        generation["entrypoint"] = "candidate.py"
        generation["executor"]["mounts"] = [
            ["/agent", str(roots["agent"])],
            ["/runner", str(roots["runner"])],
        ]
        record["lineage"] = self.counted_proposal["child"]["lineage"]
        self.counted_screen = h.screen(record)
        h.programs[self.counted_screen.candidate_id]["answers"] = [LONG_ANSWER, ""]
        directory, _ = h.prepare(
            self.counted_screen,
            self.cell / "screen",
            self.authority,
            input_bindings=self.controls,
        )
        self.assertEqual(h.run_screen(directory)["status"], "complete")
        self.parent = h.reference(directory, self.authority)
        self.assertNotEqual(self.counted_screen.candidate_id, self.improver_id)
        self.common_bytes = (self.scope / "common/report.json").read_bytes()
        self.counted_bytes = (directory / "report.json").read_bytes()
        base_generation = self.base_screen.to_record()["generation"]
        self.template = {
            name: copy.deepcopy(base_generation[name])
            for name in ("config", "profile", "max_callbacks", "budget_microusd", "max_calls")
        }
        self.values = {
            "scope": self.scope,
            "directory": self.location,
            "parent": self.parent,
            "base_screen": self.base_screen,
            "proposal_template": self.template,
            "review": f.f.review,
            "expected_runtime_sha256": runtime,
            "controls": self.controls,
            "source_copy": source_copy,
        }
        # Future seam is first accessed only after genuine measured evidence and
        # a real detached-I counted application exist on the unchanged RED cut.
        self.treatment = source_search._witness_declaration(**self.values)
        self.callbacks, self.interrupt_once = callbacks, False
        self.events, self.censuses = [], 0
        self.original_owners = {self.counted_stage / "owners/0"}
        for screen_directory in (self.scope / "common", directory):
            for ordinal in range(len(self.base_screen.tasks.tasks)):
                task = screen_directory / "tasks" / str(ordinal)
                self.original_owners.add(task / "generation/owners/0")
                for index in range(1, len(self.base_screen.to_record()["stages"]) + 1):
                    self.original_owners.add(task / "evaluation" / "owners" / str(index))
        return self

    def reader(self):
        from buddha.doctor import _authority
        from buddha.native_evidence import NativeEvidence

        self.censuses += 1
        reader = NativeEvidence(self.scope, self.authority.path, error_type=self.Error)
        for path, digest in self.controls.items():
            reader.raw(path, digest)
        actual = {path.parent for path in self.scope.rglob("owners/*/manifest.json")}
        allowed = self.original_owners | {
            self.location / "proposal/owners/0",
            self.location / "generation/owners/0",
        }
        if not self.original_owners <= actual or not actual <= allowed:
            raise self.Error("fixture caller's original owner grid differs")
        funding = _authority(
            reader.capture, reader.authorization, [reader.owner(path) for path in sorted(actual)]
        )
        if funding is None:
            raise self.Error("fixture caller lacks its original funding")
        funded = {
            Path(row["directory"])
            for row in funding["auth_runs"]
            if Path(row["directory"]).is_relative_to(self.scope)
        }
        if funded != actual:
            raise self.Error("fixture caller's funded owner is absent or replaced")
        reader.capture.finish()
        return reader

    def snapshot(self):
        return (
            self.h.files(self.h.root),
            self.authority.summary(),
            self.h.engine.physical_sends,
            len(self.events),
        )

    def execute(self, spec, *, initial, handle, **kwargs):
        from buddha.executor import ExecutorError
        from buddha.releases import _json

        h, e = self.h, self.h.engine
        owner = handle.__self__.gateway.directory
        self.events.append((owner, initial["format"], copy.deepcopy(initial)))
        if initial["format"] in {
            "buddha.candidate-improvement-worker.v1",
            "buddha.candidate-improvement-worker.v2",
        }:
            self.assertEqual(owner, self.location / "proposal/owners/0")
            self.assertEqual(initial["format"], "buddha.candidate-improvement-worker.v2")
            self.assertEqual(initial["agent_sha256"], self.counted_screen.candidate_id)
            self.assertNotEqual(initial["agent_sha256"], self.improver_id)
            self.assertEqual(
                (dict(spec.mounts)["/agent"] / "candidate.py").read_bytes(), COUNTED_CHILD.encode()
            )
            self.assertEqual([row["task"]["id"] for row in initial["feedback"]], ["1", 1])
            for row in initial["feedback"]:
                note = json.loads(row["note"])
                self.assertEqual(
                    note["answers"],
                    [{"position": 0, "text": LONG_ANSWER}, {"position": 1, "text": ""}],
                )
                self.assertEqual(note["omitted_answer_positions"], 0)
                self.assertGreater(len(row["note"].encode()), 4096)
            e.workers += 1
            handle(
                {
                    "type": "ready",
                    "agent_sha256": initial["agent_sha256"],
                    "feedback_sha256": sha(_json(initial["feedback"])),
                    "runtime_sha256": e.candidate.expected_runtime,
                }
            )
            value = {"source": WITNESS_CHILD, "hypothesis": "Only a bounded validity grandchild."}
            for sequence in range(self.callbacks):
                response = e.fixture.response(
                    choices=[{"message": {"content": _json(value).decode()}}]
                )
                connection = e.fixture.connection(response)
                with patch("http.client.HTTPSConnection", return_value=connection):
                    reply = handle(e.candidate.request(sequence, text="supplied witness callback"))
                e.physical_sends += connection.request.call_count
                self.assertEqual(reply["type"], "response")
                if self.interrupt_once:
                    self.interrupt_once = False
                    raise ExecutorError(
                        "known witness reply interruption",
                        cleanup_status="removed",
                        container_id="f" * 64,
                    )
            handle(
                {
                    "type": "done",
                    "status": "complete",
                    "reason": "complete",
                    "proposal": {
                        "status": "captured",
                        "value": value,
                        "sha256": sha(_json(value)),
                        "bytes": len(_json(value)),
                    },
                }
            )
            return e.execution(spec)
        self.assertEqual(owner, self.location / "generation/owners/0")
        self.assertEqual(initial["task"], self.base_screen.tasks.tasks[0].to_record())
        self.assertIs(type(initial["task"]["id"]), str)
        self.assertEqual(initial["task"]["count"], 2)
        self.assertEqual(
            (dict(spec.mounts)["/agent"] / "candidate.py").read_bytes(), WITNESS_CHILD.encode()
        )
        manifest = json.loads((owner / "manifest.json").read_bytes())
        record = self.base_screen.to_record()
        record["generation"]["selection"] = manifest["selection"]
        h.programs[initial["agent_sha256"]] = {
            "record": record,
            "callbacks": 0,
            "answers": ["literal witness", ""],
            "distinct": 2,
            "utility": 7,
        }
        return h.execute(spec, initial=initial, handle=handle, **kwargs)

    def advance(self):
        import test_gateway

        from buddha import native_pipeline as pipeline
        from buddha.gateway import RawHTTPTransport

        with (
            pipeline._exclusive(self.scope),
            patch.dict(os.environ, {"OPENAI_API_KEY": test_gateway.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=self.execute),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("unexpected HTTPS")),
            patch.object(
                self.api, "_restore", side_effect=AssertionError("SourceSearch restore forbidden")
            ),
            patch.object(
                self.api,
                "_witness_location",
                side_effect=AssertionError("SourceSearch layout forbidden"),
            ),
        ):
            return self.api._advance_witness(
                self.reader(),
                self.treatment,
                authorization=self.authority,
                transport=RawHTTPTransport(allow_paid=True),
            )

    def progress(self):
        before = self.snapshot()
        with (
            self.h.readonly(),
            patch.object(
                self.api, "_restore", side_effect=AssertionError("SourceSearch restore forbidden")
            ),
            patch.object(
                self.api,
                "_witness_location",
                side_effect=AssertionError("SourceSearch layout forbidden"),
            ),
        ):
            reader = self.reader()
            result = self.api._witness_progress_at(reader, self.treatment)
            reader.capture.finish()
        self.assertEqual(
            set(result),
            {
                "result",
                "publication",
                "next_owner",
                "next_role",
                "inactive_pending",
                "lower_role",
                "needs_prepare",
                "owner_treatments",
            },
        )
        self.assertEqual(self.snapshot(), before)
        return result

    def step(self, action, role):
        before = len(self.events)
        result = self.advance()
        self.assertEqual(set(result), {"action", "role", "result"})
        self.assertEqual((result["action"], result["role"]), (action, role))
        if action == "prepared":
            self.assertIsNone(result["result"])
            self.assertEqual(len(self.events), before)
        return result["result"]

    def refuse_work(self):
        before = self.snapshot()
        with patch("buddha.trial_fence.work", side_effect=self.Error("supplied freeze refusal")):
            with self.assertRaises(self.Error):
                self.advance()
        self.assertEqual(self.snapshot(), before)

    def complete(self):
        before = self.snapshot()
        with (
            patch.dict(os.environ, {}, clear=True),
            self.h.readonly(),
            patch(
                "buddha.trial_fence.work",
                side_effect=AssertionError("active work after completion"),
            ),
            patch.object(
                self.api, "_restore", side_effect=AssertionError("SourceSearch restore forbidden")
            ),
            patch.object(
                self.api,
                "_witness_location",
                side_effect=AssertionError("SourceSearch layout forbidden"),
            ),
        ):
            reader = self.reader()
            result = self.api._advance_witness(reader, self.treatment)
            reader.capture.finish()
        self.assertEqual(set(result), {"action", "role", "result"})
        self.assertEqual((result["action"], result["role"]), ("complete", None))
        self.assertEqual(self.snapshot(), before)
        return result["result"]

    def finish(self, *, source_copy):
        self.assertFalse((self.location / "generation").exists())
        progress = self.progress()
        self.assertEqual(progress["lower_role"], "generation")
        self.assertIs(progress["needs_prepare"], True)
        self.refuse_work()
        self.assertFalse((self.location / "agent").exists())
        self.step("prepared", "generation")
        self.assertEqual(len(self.progress()["owner_treatments"]), 2)
        self.assertEqual((self.location / "agent").exists(), source_copy)
        if source_copy:
            self.assertEqual(
                (self.location / "agent/candidate.py").read_bytes(), WITNESS_CHILD.encode()
            )
        generated = self.step("executed", "generation")
        self.assertEqual(generated["disposition"], "generated")
        self.assertFalse((self.location / "report.json").exists())
        self.refuse_work()
        result = self.step("published", None)
        self.assertEqual((result["status"], result["reason"]), ("passed", "complete"))
        self.assertEqual(result["candidate_id"], self.counted_screen.candidate_id)
        self.assertEqual(result["screen"], self.parent)
        self.assertEqual(self.complete(), result)
        self.assertEqual((self.scope / "common/report.json").read_bytes(), self.common_bytes)
        self.assertEqual((self.cell / "screen/report.json").read_bytes(), self.counted_bytes)
        self.assertFalse((self.location / "screen").exists())
        self.assertFalse((self.scope / "manifest.json").exists())
        self.assertFalse((self.scope / "seed").exists())
        return result

    def test_non_search_scope_prepares_and_executes_one_role_then_replays_passively(self):
        from buddha.releases import _json

        self.fixture(source_copy=True)
        before = self.snapshot()
        record = self.treatment.to_record()
        self.assertEqual(
            set(record),
            {
                "format",
                "scope",
                "directory",
                "parent",
                "base_screen",
                "proposal_template",
                "review",
                "expected_runtime_sha256",
                "controls",
                "source_copy",
                "policy",
            },
        )
        self.assertEqual(record["format"], "buddha.source-mutation-witness-treatment.v1")
        self.assertEqual(record["policy"], self.api.MUTATION_WITNESS_POLICY)
        self.assertEqual(
            self.api._WitnessTreatment.from_bytes(json.dumps(record, indent=2).encode()).to_bytes(),
            self.treatment.to_bytes(),
        )
        record["proposal_template"]["config"]["instructions"] = "changed copy"
        self.assertNotEqual(record, self.treatment.to_record())
        for source_copy in (None, 0, "yes"):
            with self.subTest(source_copy=source_copy), self.assertRaises(self.Error):
                self.api._witness_declaration(**(self.values | {"source_copy": source_copy}))
        for key, value in (
            ("provider", "unsupported-provider"),
            ("sampling", "unsupported-sampling"),
        ):
            template = copy.deepcopy(self.template)
            template["config"][key] = value
            with self.subTest(template_key=key), self.assertRaises(self.Error):
                self.api._witness_declaration(**(self.values | {"proposal_template": template}))
        for mutation in ("extra", "policy"):
            malformed = self.treatment.to_record()
            if mutation == "extra":
                malformed["extra"] = True
            else:
                malformed["policy"]["depth"] = 2
            with self.subTest(mutation=mutation), self.assertRaises(self.Error):
                self.api._WitnessTreatment.from_bytes(_json(malformed))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.location.exists())
        self.refuse_work()
        self.assertFalse(self.location.exists())
        progress = self.progress()
        self.assertEqual((progress["lower_role"], progress["needs_prepare"]), ("proposal", True))
        self.step("prepared", "proposal")
        self.assertEqual(len(self.progress()["owner_treatments"]), 1)
        # An empty foreign owner is still an orphan, even without a manifest.
        before = self.snapshot()
        foreign = self.location / "foreign" / "owners" / "0"
        foreign.mkdir(parents=True)
        try:
            with self.assertRaises(self.Error):
                self.progress()
        finally:
            foreign.rmdir()
            foreign.parent.rmdir()
            foreign.parent.parent.rmdir()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.location / "generation").exists())
        calls = self.censuses
        proposal = self.step("executed", "proposal")
        self.assertGreater(self.censuses, calls)
        self.assertEqual(proposal["disposition"], "materialized")
        self.assertEqual(proposal["parent_agent_sha256"], self.counted_screen.candidate_id)
        self.assertEqual(len(self.events), 1)
        self.assertFalse((self.location / "generation").exists())
        self.finish(source_copy=True)
        self.assertEqual(len(self.events), 2)

    def test_unplanned_shared_progress_is_lazy_and_capacity_keeps_the_typed_exception(self):
        from buddha.source_feedback import SourceFeedbackTooLarge

        self.fixture(source_copy=False)
        before = self.snapshot()
        with patch.object(
            self.api, "_bundle", side_effect=AssertionError("passive packet build")
        ) as building:
            progress = self.progress()
        building.assert_not_called()
        self.assertEqual((progress["lower_role"], progress["needs_prepare"]), ("proposal", True))
        self.assertEqual(progress["owner_treatments"], {})
        self.assertFalse(self.location.exists())
        self.assertEqual(self.snapshot(), before)
        capacity = SourceFeedbackTooLarge("supplied complete-feedback capacity boundary")
        attempts = []

        def too_large(directory, reference, failures, *, full_answers):
            attempts.append((directory, reference, failures, full_answers, self.location.is_dir()))
            raise capacity

        with patch.object(self.api, "_bundle", side_effect=too_large):
            for ordinal in range(2):
                with (
                    self.subTest(ordinal=ordinal),
                    self.assertRaises(SourceFeedbackTooLarge) as stopped,
                ):
                    self.advance()
                self.assertIs(stopped.exception, capacity)
                self.assertEqual(len(attempts), ordinal + 1)
                self.assertEqual(
                    attempts[-1], (self.location / "feedback", self.parent, [], True, True)
                )
                self.assertTrue(self.location.is_dir())
                self.assertEqual(list(self.location.iterdir()), [])
                self.assertEqual(self.snapshot(), before)
                # The retained empty location is still an unplanned prefix. No
                # capacity computation or owner repair belongs in passive read.
                with patch.object(
                    self.api, "_bundle", side_effect=AssertionError("passive retry")
                ) as building:
                    progress = self.progress()
                building.assert_not_called()
                self.assertIs(progress["needs_prepare"], True)
                self.assertEqual(progress["owner_treatments"], {})

    def test_caller_change_refuses_before_dispatch_and_known_reply_keeps_original_owner(self):
        self.fixture(source_copy=False, callbacks=1)
        self.step("prepared", "proposal")
        owner = self.location / "proposal/owners/0"
        original_manifest = (owner / "manifest.json").read_bytes()
        declaration = self.declaration.read_bytes()
        before = self.snapshot()
        self.declaration.write_bytes(declaration + b" ")
        try:
            with patch.object(
                self.api, "_advance_witness", wraps=self.api._advance_witness
            ) as advancing:
                with self.assertRaises(self.Error):
                    self.advance()
                advancing.assert_not_called()
        finally:
            self.declaration.write_bytes(declaration)
        self.assertEqual(self.snapshot(), before)
        self.refuse_work()
        self.interrupt_once = True
        calls = self.h.engine.physical_sends
        partial = self.step("incomplete", "proposal")
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["owner"], str(owner))
        self.assertEqual(
            json.loads((self.location / "proposal" / partial["observation"]).read_bytes()), partial
        )
        self.assertEqual(self.h.engine.physical_sends, calls + 1)
        self.assertEqual((owner / "manifest.json").read_bytes(), original_manifest)
        self.assertFalse((self.location / "generation").exists())
        retained = self.h.files(self.location / "proposal/attempts")
        calls = self.h.engine.physical_sends
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared",
            side_effect=AssertionError("known reply resent"),
        ):
            proposal = self.step("executed", "proposal")
        self.assertEqual(proposal["disposition"], "materialized")
        self.assertEqual(self.h.engine.physical_sends, calls)
        self.assertEqual((owner / "manifest.json").read_bytes(), original_manifest)
        for name, digest in retained.items():
            self.assertEqual(sha((self.location / "proposal/attempts" / name).read_bytes()), digest)
        self.assertEqual(
            {path.name for path in (self.location / "proposal/owners").iterdir()}, {"0"}
        )
        self.finish(source_copy=False)


class WitnessFacadeCapacityTests(unittest.TestCase):
    def test_unplanned_search_read_is_lazy_and_active_capacity_retains_phase_and_empty_prefix(self):
        import test_gateway
        import test_source_mutation_witness

        from buddha import source_screen, source_search
        from buddha.gateway import RawHTTPTransport
        from buddha.native_evidence import NativeEvidence
        from buddha.source_feedback import SourceFeedbackTooLarge

        harness = test_source_mutation_witness._Harness(self)
        harness.prepare()
        case = harness.case
        # Complete only the actual original seed through the existing lower API;
        # do not ask SourceSearch to pass the new witness boundary during setup.
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": test_gateway.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=case.execute),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("unexpected HTTPS")),
        ):
            seed = source_screen.run_source_screen(
                case.directory / "seed", transport=RawHTTPTransport(allow_paid=True)
            )
        self.assertEqual(seed["status"], "complete")
        self.assertIs(seed["admission"]["eligible"], True)
        location = case.directory / "seed-witness"
        self.assertFalse(location.exists())
        before = (
            case.h.files(case.directory),
            case.authority.summary(),
            case.engine.physical_sends,
            case.engine.workers,
            case.engine.native_workers,
        )
        with (
            case.h.readonly(),
            patch.object(
                source_search, "_bundle", side_effect=AssertionError("passive packet build")
            ) as building,
        ):
            reader = NativeEvidence(
                case.directory, case.authority.path, error_type=source_search.SourceSearchError
            )
            state = source_search._restore(case.directory, case.authority.path, reader=reader)
            current = state["mutation_progress"][str(case.directory / "seed")]
            self.assertEqual(
                set(current),
                {"result", "publication", "next_owner", "next_role", "inactive_pending"},
            )
            self.assertIsNone(current["result"])
            self.assertEqual(current["next_owner"], location / "proposal/owners/0")
            reader.capture.finish()
        building.assert_not_called()
        self.assertFalse(location.exists())
        self.assertEqual(
            (
                case.h.files(case.directory),
                case.authority.summary(),
                case.engine.physical_sends,
                case.engine.workers,
                case.engine.native_workers,
            ),
            before,
        )
        calls = []

        def too_large(directory, reference, failures, *, full_answers):
            calls.append(
                (directory, reference["directory"], failures, full_answers, location.is_dir())
            )
            raise SourceFeedbackTooLarge("supplied first-active witness capacity boundary")

        original_observations = []
        with patch.object(source_search, "_bundle", side_effect=too_large):
            for ordinal in range(2):
                with (
                    self.subTest(ordinal=ordinal),
                    self.assertRaises(source_search.SourceSearchStopped) as stopped,
                ):
                    harness.run()
                partial = stopped.exception.partial
                case.partial(partial)
                self.assertEqual(
                    (partial["reason"], partial["stage"]), ("feedback_capacity", "witness_feedback")
                )
                self.assertIsNone(partial["child"])
                self.assertEqual(partial["observation"], "observations/" + str(ordinal) + ".json")
                self.assertEqual(len(calls), ordinal + 1)
                self.assertEqual(
                    calls[-1], (location / "feedback", str(case.directory / "seed"), [], True, True)
                )
                self.assertTrue(location.is_dir())
                self.assertEqual(list(location.iterdir()), [])
                self.assertFalse((case.directory / "iterations/0").exists())
                self.assertEqual(
                    (
                        case.authority.summary(),
                        case.engine.physical_sends,
                        case.engine.workers,
                        case.engine.native_workers,
                    ),
                    before[1:],
                )
                self.assertEqual(harness.improvements, [])
                for name, digest in before[0].items():
                    self.assertEqual(sha((case.directory / name).read_bytes()), digest)
                observation = case.directory / partial["observation"]
                original_observations.append((observation, observation.read_bytes()))
                for path, raw in original_observations:
                    self.assertEqual(path.read_bytes(), raw)
                # Empty prior capacity attempts do not authorize passive packet
                # rebuilding or a replacement owner on the next invocation.
                with (
                    case.h.readonly(),
                    patch.object(
                        source_search, "_bundle", side_effect=AssertionError("passive empty prefix")
                    ) as building,
                ):
                    source_search._restore(case.directory, case.authority.path)
                building.assert_not_called()


if __name__ == "__main__":
    unittest.main()
