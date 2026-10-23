"""Bounded inherited source search: real custody with mocked worker channels."""

import copy
import hashlib
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import test_gateway as gateway_fixtures
import test_source_screen_outcome as screen_fixtures

from buddha.executor import ExecutorError
from buddha.gateway import RawHTTPTransport
from buddha.releases import _json, prepare_selection

IMPROVER = """\ndef propose_improvement(parent, feedback, config, complete):
    return json.loads(request(config, complete, {"parent": parent, "feedback": feedback}))
"""
REQUEST = """import json
def request(config, complete, payload):
    body = json.dumps({"model": config["model"],
        "max_completion_tokens": config["max_output_tokens"],
        "messages": [{"role": "user", "content": json.dumps(payload)}]}).encode()
    return complete(config["provider"], body)["choices"][0]["message"]["content"]
"""
SEED = (
    REQUEST
    + """\ndef generate(task, config, complete):
    return [request(config, complete, {"prompt": task["prompt"], "index": i})
            for i in range(task["count"])]
"""
    + IMPROVER
)
BROKEN = "def generate(:\n"
REPAIRED = (
    REQUEST
    + """\ndef generate(task, config, complete):
    return json.loads(request(config, complete, {"prompt": task["prompt"], "count": task["count"]}))
"""
    + IMPROVER
)
GRANDCHILD = (
    REQUEST
    + """\ndef generate(task, config, complete):
    plan = request(config, complete, {"plan": task["prompt"]})
    return [request(config, complete, {"plan": plan, "draft": i}) for i in range(task["count"])]
"""
    + IMPROVER
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceSearchTests(unittest.TestCase):
    def api(self):
        # A missing API is one import error before any fixture or behavior runs.
        from buddha.source_search import (
            SourceSearchError,
            SourceSearchSpec,
            inspect_source_search,
            prepare_source_search,
            run_source_search,
        )

        self.Error, self.Spec = SourceSearchError, SourceSearchSpec
        self.prepare_api, self.run_api, self.inspect_api = (
            prepare_source_search,
            run_source_search,
            inspect_source_search,
        )

    def fixture(self, *, iterations=3):
        self.api()
        if hasattr(self, "h"):
            return self
        outcome = screen_fixtures.SourceScreenOutcomeTests("runTest")
        self.h = h = outcome.fixture()
        self.addCleanup(outcome.doCleanups)
        self.root, self.engine = h.root, h.engine
        f = h.engine.fixture
        (f.roots["agent"] / "candidate.py").write_bytes(SEED.encode())
        record = copy.deepcopy(h.record)
        record["format"] = "buddha.source-screen.v2"
        record["generation"]["selection"] = prepare_selection(
            h.engine.candidate.release,
            f.roots,
            capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
        ).to_record()
        self.seed = h.screen(record)
        self.authority = h.authority(self.seed)
        self.directory = self.root / "source-search"
        generation = self.seed.to_record()["generation"]
        self.template = {
            key: copy.deepcopy(generation[key])
            for key in ("config", "profile", "max_callbacks", "budget_microusd", "max_calls")
        }
        self.spec = self.Spec.from_bytes(_json(self.specification(iterations=iterations)))
        self.proposals = [BROKEN, REPAIRED, GRANDCHILD]
        self.proposal_owner_ordinals = {}
        self.proposal_events, self.worker_events = [], []
        self.proposal_timeout_once = False
        self.proposal_interrupt_once = False
        self.reject_ordinals = set()
        self.unscored_sources = set()
        self.programs = {
            sha(SEED.encode()): ("independent", 2),
            sha(BROKEN.encode()): ("checked-failure", 0),
            sha(REPAIRED.encode()): ("batch", 1),
            sha(GRANDCHILD.encode()): ("plan-and-draft", 3),
        }
        return self

    def prepare(self, **changes):
        self.fixture()
        values = {
            "seed_screen": self.seed,
            "proposal_template": self.template,
            "spec": self.spec,
            "authorization": self.authority,
            "review": self.engine.fixture.review,
            "expected_runtime_sha256": self.engine.candidate.expected_runtime,
        }
        return self.prepare_api(self.directory, **(values | changes))

    def execute(self, spec, *, initial, handle, **kwargs):
        session = handle.__self__
        self.worker_events.append((spec.role, initial["format"]))
        if spec.role != "agent":
            return self.h.execute(spec, initial=initial, handle=handle, **kwargs)
        self.assertEqual({name for name, _ in spec.mounts}, {"/agent", "/runner"})
        self.assertNotIn(b"VALIDATION-ONLY-SENTINEL", _json(initial))
        self.assertNotIn(b"FINAL-ONLY-SENTINEL", _json(initial))
        self.assertNotIn(b"dataset_base64", _json(initial))
        source = (dict(spec.mounts)["/agent"] / "candidate.py").read_bytes()
        self.assertEqual(initial["agent_sha256"], sha(_json({"candidate.py": sha(source)})))
        if initial["format"] in {
            "buddha.candidate-improvement-worker.v1",
            "buddha.candidate-improvement-worker.v2",
        }:
            return self.execute_improvement(spec, initial, handle, source)
        label, callbacks = self.programs[sha(source)]
        if label == "checked-failure":
            self.engine.workers += 1
            self.h.generation_events.append((initial["agent_sha256"], initial["task"]))
            handle({"type": "done", "status": "failed", "reason": "agent_error", "answers": []})
            return self.engine.execution(spec)
        manifest = json.loads((session.gateway.directory / "manifest.json").read_bytes())
        record = self.seed.to_record()
        record["generation"]["selection"] = manifest["selection"]
        self.h.programs[initial["agent_sha256"]] = {
            "record": record,
            "callbacks": callbacks,
            "answers": ["  unchanged weak text  ", ""],
            "distinct": 2,
            "utility": 7,
        }
        self.h.unusable_task = "1" if sha(source) in self.unscored_sources else None
        self.engine.request_text = "literal fixture procedure: " + label
        return self.h.execute(spec, initial=initial, handle=handle, **kwargs)

    def execute_improvement(self, spec, initial, handle, source):
        owner = handle.__self__.gateway.directory
        if owner not in self.proposal_owner_ordinals:
            self.proposal_owner_ordinals[owner] = len(self.proposal_owner_ordinals)
        ordinal = self.proposal_owner_ordinals[owner]
        self.assertLess(ordinal, len(self.proposals))
        value = {
            "source": self.proposals[ordinal],
            "hypothesis": "Change the generation procedure.",
        }
        self.proposal_events.append(
            {
                "ordinal": ordinal,
                "parent_id": initial["agent_sha256"],
                "parent_source": source.decode(),
                "feedback": copy.deepcopy(initial["feedback"]),
            }
        )
        handle(
            {
                "type": "ready",
                "agent_sha256": initial["agent_sha256"],
                "feedback_sha256": sha(_json(initial["feedback"])),
                "runtime_sha256": self.engine.candidate.expected_runtime,
            }
        )
        payload = _json({"source": source.decode(), "feedback": initial["feedback"]}).decode()
        request = self.engine.candidate.request(text=payload)
        f = self.engine.fixture
        response = f.response(choices=[{"message": {"content": _json(value).decode()}}])
        connection = f.connection(response)
        if self.proposal_timeout_once:
            self.proposal_timeout_once = False
            connection.getresponse.side_effect = TimeoutError("synthetic unknown")
        with patch("http.client.HTTPSConnection", return_value=connection):
            reply = handle(request)
        self.engine.physical_sends += connection.request.call_count
        if reply["type"] == "stop":
            handle(
                {
                    "type": "done",
                    "status": "stopped",
                    "reason": reply["reason"],
                    "proposal": {
                        "status": "unavailable",
                        "value": None,
                        "sha256": None,
                        "bytes": None,
                    },
                }
            )
            return self.engine.execution(spec)
        if self.proposal_interrupt_once:
            self.proposal_interrupt_once = False
            raise ExecutorError(
                "synthetic known reply stop", cleanup_status="removed", container_id="f" * 64
            )
        if ordinal in self.reject_ordinals:
            capture = {"status": "captured", "value": {}, "sha256": sha(_json({})), "bytes": 2}
            status, reason = "failed", "invalid_proposal"
        else:
            capture = {
                "status": "captured",
                "value": value,
                "sha256": sha(_json(value)),
                "bytes": len(_json(value)),
            }
            status, reason = "complete", "complete"
        handle({"type": "done", "status": status, "reason": reason, "proposal": capture})
        return self.engine.execution(spec)

    def run_search(self, *, paid=True):
        with (
            patch.dict(
                os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY} if paid else {}, clear=True
            ),
            patch("buddha.executor.run_container", side_effect=self.execute),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("unexpected HTTPS")),
            patch(
                "buddha.agent_run.AgentSession", side_effect=AssertionError("fixed seed forbidden")
            ),
        ):
            return self.run_api(self.directory, transport=RawHTTPTransport(allow_paid=paid))

    def reference(self):
        return {
            "authorization": self.authority.path,
            "expected_report_sha256": sha((self.directory / "report.json").read_bytes()),
        }

    def inspect(self):
        before = (
            self.h.files(self.directory),
            sha(self.authority.path.read_bytes()),
            self.engine.physical_sends,
        )
        with (
            self.h.readonly(),
            patch("socket.socket", side_effect=AssertionError("passive socket")),
        ):
            result = self.inspect_api(self.directory, **self.reference())
        self.assertEqual(
            (
                self.h.files(self.directory),
                sha(self.authority.path.read_bytes()),
                self.engine.physical_sends,
            ),
            before,
        )
        return result

    def partial(self, result):
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse((self.directory / "report.json").exists())
        self.assertEqual(json.loads((self.directory / result["observation"]).read_bytes()), result)

    def specification(self, **changes):
        value = {
            "format": "buddha.source-search.v1",
            "iterations": 3,
            "method": "latest",
            "seed": 17,
            "max_active": 4,
        }
        return value | changes

    def test_specification_is_closed_bounded_typed_and_uses_existing_parent_methods(self):
        self.api()
        record = self.specification()
        spec = self.Spec.from_bytes(_json(record))
        self.assertEqual(spec.to_record(), record)
        self.assertEqual(self.Spec.from_bytes(spec.to_bytes()).fingerprint(), spec.fingerprint())
        for method in ("archive", "latest", "uninformed"):
            self.assertEqual(
                self.Spec.from_bytes(_json(record | {"method": method})).to_record()["method"],
                method,
            )
        cases = [
            {"iterations": False},
            {"iterations": 0},
            {"iterations": 9},
            {"iterations": 1.0},
            {"method": "chain"},
            {"seed": True},
            {"seed": -1},
            {"max_active": True},
            {"max_active": 1},
            {"max_active": 65},
            {"format": "buddha.policy-search.v1"},
            {"extra": "undeclared"},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(self.Error):
                self.Spec.from_bytes(_json(record | changes))
        for key in record:
            missing = copy.deepcopy(record)
            del missing[key]
            with self.subTest(missing=key), self.assertRaises(self.Error):
                self.Spec.from_bytes(_json(missing))

    def test_prepare_rejects_wrong_scope_template_old_mode_and_original_pin_before_owner(self):
        self.fixture()
        old = self.seed.to_record()
        old["format"] = "buddha.source-screen.v1"
        bad_template = copy.deepcopy(self.template)
        bad_template["config"]["model"] = "unapproved-model"
        control = self.root / "original-control.json"
        control.write_bytes(b"{}")
        for changes in [
            {"authorization": self.engine.fixture.authority},
            {"seed_screen": self.h.Screen.from_bytes(_json(old))},
            {"proposal_template": bad_template},
            {"proposal_template": self.template | {"feedback": "not a template control"}},
            {"expected_runtime_sha256": "0" * 64},
            {"input_bindings": {control: "0" * 64}},
        ]:
            with self.subTest(changes=list(changes)), self.assertRaises(self.Error):
                self.prepare(**changes)
            self.assertFalse(self.directory.exists())
        self.assertEqual(self.authority.summary()["runs"], [])
        self.assertEqual(self.engine.physical_sends, 0)

    def test_failed_child_feedback_repairs_source_then_executes_the_inherited_child_improver(self):
        self.prepare()
        original_seed = (self.engine.fixture.roots["agent"] / "candidate.py").read_bytes()
        result = self.run_search()
        self.assertEqual(
            (result["format"], result["status"]), ("buddha.source-search-report.v1", "complete")
        )
        self.assertEqual(
            [row["status"] for row in result["decisions"]],
            ["candidate_execution_failed", "admitted", "admitted"],
        )
        ids = [
            sha(_json({"candidate.py": sha(text.encode())}))
            for text in (BROKEN, REPAIRED, GRANDCHILD)
        ]
        self.assertEqual([row["child_id"] for row in result["decisions"]], ids)
        self.assertEqual(
            [event["parent_id"] for event in self.proposal_events],
            [self.seed.candidate_id, self.seed.candidate_id, ids[1]],
        )
        self.assertEqual(self.proposal_events[2]["parent_source"], REPAIRED)
        self.assertIn(IMPROVER, self.proposal_events[2]["parent_source"])
        for event in self.proposal_events[1:]:
            self.assertEqual([row["task"]["id"] for row in event["feedback"]], ["1", 1])
            for record in event["feedback"]:
                note = json.loads(record["note"])
                self.assertEqual(note["kind"], "saved_native_measurements_and_failed_children")
                self.assertEqual(
                    note["measurements"]["answers"],
                    [
                        {"position": 0, "text": "  unchanged weak text  "},
                        {"position": 1, "text": ""},
                    ],
                )
                self.assertEqual(note["measurements"]["omitted_answer_positions"], 0)
                failure = note["failures"][0]
                self.assertEqual(
                    (failure["parent_id"], failure["child_id"], failure["task_id"]),
                    (self.seed.candidate_id, ids[0], "1"),
                )
                self.assertEqual(
                    (failure["reason"], failure["ready_seen"], failure["completed_callbacks"]),
                    ("agent_error", False, 0),
                )
                self.assertEqual(note["newest_failure"]["source"], BROKEN)
                self.assertEqual(note["newest_failure"]["source_sha256"], sha(BROKEN.encode()))
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(len(result["screens"]), 4)
        self.assertEqual(result["selection"]["selected_id"], ids[2])
        self.assertNotIn(ids[0], result["selection"]["active_ids"])
        self.assertEqual((self.engine.physical_sends, len(self.worker_events)), (27, 28))
        summary = self.authority.summary()
        self.assertEqual(
            (summary["operation_count"], summary["spent_microusd"], summary["reserved_microusd"]),
            (27, 297, 0),
        )
        self.assertEqual(len(summary["runs"]), 28)
        self.assertFalse(any(row["active"] for row in summary["runs"]))
        self.assertEqual(result["provenance"]["scoped_totals"]["spent_microusd"], 297)
        self.assertEqual(
            (self.engine.fixture.roots["agent"] / "candidate.py").read_bytes(), original_seed
        )
        self.assertEqual(self.inspect(), result)

    def test_rejected_duplicate_unscored_children_consume_iterations_without_parent_admission(
        self,
    ):
        self.fixture(iterations=4)
        # Establish a distinct eligible parent before proposing its known ancestor.
        # Returning the current parent's identical source is a protocol rejection.
        self.proposals = [REPAIRED, BROKEN, SEED, GRANDCHILD]
        self.reject_ordinals = {1}
        self.unscored_sources = {sha(GRANDCHILD.encode())}
        self.prepare()
        result = self.run_search()
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual(
            [row["status"] for row in result["decisions"]],
            ["admitted", "rejected", "duplicate", "ineligible"],
        )
        repaired_id = sha(_json({"candidate.py": sha(REPAIRED.encode())}))
        self.assertIsNone(result["decisions"][1]["child_id"])
        self.assertEqual(result["decisions"][2]["child_id"], self.seed.candidate_id)
        self.assertFalse((self.directory / "iterations/1/screen").exists())
        self.assertFalse((self.directory / "iterations/2/screen").exists())
        self.assertEqual(result["selection"]["selected_id"], repaired_id)
        self.assertEqual(
            [row["parent_id"] for row in result["decisions"]],
            [self.seed.candidate_id, repaired_id, repaired_id, repaired_id],
        )
        self.assertEqual(result["failures"], [])
        self.assertEqual(len(result["screens"]), 3)
        self.assertEqual((self.engine.physical_sends, len(self.worker_events)), (28, 28))
        summary = self.authority.summary()
        self.assertEqual(
            (summary["operation_count"], summary["spent_microusd"], summary["reserved_microusd"]),
            (28, 308, 0),
        )
        self.assertEqual(len(summary["runs"]), 28)
        self.assertFalse(any(row["active"] for row in summary["runs"]))
        self.assertEqual(self.inspect(), result)

    def test_known_reply_incomplete_resumes_original_plan_packet_and_owner_without_rebilling(self):
        self.fixture(iterations=1)
        self.prepare()
        self.proposal_interrupt_once = True
        first = self.run_search()
        self.partial(first)
        self.assertEqual((first["iteration"], first["stage"]), (0, "proposal"))
        location = self.directory / "iterations/0"
        retained = self.h.files(location / "proposal/attempts")
        manifest = (location / "proposal/owners/0/manifest.json").read_bytes()
        plan = (location / "plan.json").read_bytes()
        packet = self.h.files(location / "feedback")
        before = self.engine.physical_sends
        self.assertFalse((location / "decision.json").exists())
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared", side_effect=AssertionError("new send")
        ):
            result = self.run_search()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["decisions"][0]["status"], "candidate_execution_failed")
        self.assertEqual(self.engine.physical_sends, before)
        self.assertEqual((location / "proposal/owners/0/manifest.json").read_bytes(), manifest)
        self.assertEqual((location / "plan.json").read_bytes(), plan)
        self.assertEqual(self.h.files(location / "feedback"), packet)
        for path, expected in retained.items():
            self.assertEqual(sha((location / "proposal/attempts" / path).read_bytes()), expected)
        self.assertEqual(len(list((location / "proposal/owners").iterdir())), 1)

    def test_unknown_stops_same_iteration_and_all_future_work_while_original_hold_remains(self):
        self.fixture(iterations=2)
        self.prepare()
        self.proposal_timeout_once = True
        first = self.run_search()
        self.partial(first)
        self.assertEqual((first["iteration"], first["stage"]), (0, "proposal"))
        summary = self.authority.summary()
        self.assertGreater(summary["reserved_microusd"], 0)
        owners = {row["directory"]: row["run_id"] for row in summary["runs"]}
        sends = self.engine.physical_sends
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared",
            side_effect=AssertionError("unknown resend"),
        ):
            resumed = self.run_search()
        self.partial(resumed)
        self.assertEqual(self.engine.physical_sends, sends)
        self.assertEqual(
            {row["directory"]: row["run_id"] for row in self.authority.summary()["runs"]}, owners
        )
        self.assertEqual(
            self.authority.summary()["reserved_microusd"], summary["reserved_microusd"]
        )
        self.assertFalse((self.directory / "iterations/0/decision.json").exists())
        self.assertFalse((self.directory / "iterations/1").exists())

    def test_late_common_control_drift_cannot_be_adopted_at_new_proposal_owner(self):
        from buddha import candidate_improvement

        self.fixture(iterations=1)
        control = self.root / "control.json"
        original = b'{"original":true}'
        control.write_bytes(original)
        self.prepare(input_bindings={control: sha(original)})
        actual = candidate_improvement.prepare_gateway

        def changed(*args, **kwargs):
            control.write_bytes(original + b"\n")
            return actual(*args, **kwargs)

        try:
            with (
                patch.object(candidate_improvement, "prepare_gateway", side_effect=changed),
                self.assertRaises(self.Error),
            ):
                self.run_search()
            self.assertEqual(self.engine.physical_sends, 8)
            self.assertFalse(
                (self.directory / "iterations/0/proposal/owners/0/manifest.json").exists()
            )
            self.assertFalse((self.directory / "iterations/0/decision.json").exists())
        finally:
            control.write_bytes(original)

    def test_returned_proposal_must_match_saved_typed_publication_before_child_screening(self):
        from buddha import candidate_improvement

        self.fixture(iterations=1)
        self.proposals = [REPAIRED]
        self.prepare()
        actual = candidate_improvement.run_candidate_improvement

        def forged(*args, **kwargs):
            result = copy.deepcopy(actual(*args, **kwargs))
            result["child"]["source_sha256"] = False
            return result

        with (
            patch.object(candidate_improvement, "run_candidate_improvement", side_effect=forged),
            self.assertRaises(self.Error),
        ):
            self.run_search()
        self.assertEqual(self.engine.physical_sends, 9)
        self.assertFalse((self.directory / "iterations/0/screen").exists())
        self.assertFalse((self.directory / "iterations/0/decision.json").exists())

    def test_changed_proposal_owner_ceiling_cannot_replace_the_original_template_before_dispatch(
        self,
    ):
        from buddha import candidate_improvement

        self.fixture(iterations=1)
        self.prepare()
        actual = candidate_improvement.prepare_candidate_improvement

        def changed(*args, **kwargs):
            return actual(
                *args, **(kwargs | {"budget_microusd": self.template["budget_microusd"] + 1})
            )

        rejected = False
        with patch.object(
            candidate_improvement, "prepare_candidate_improvement", side_effect=changed
        ):
            try:
                self.run_search()
            except self.Error:
                rejected = True
        self.assertEqual(self.engine.physical_sends, 8)
        self.assertTrue(rejected)
        self.assertFalse((self.directory / "iterations/0/decision.json").exists())

    def test_returned_seed_metrics_must_match_saved_typed_publication_before_proposal(self):
        from buddha import source_screen

        self.fixture(iterations=1)
        self.prepare()
        actual = source_screen.run_source_screen

        def changed(*args, **kwargs):
            value = copy.deepcopy(actual(*args, **kwargs))
            if args[0] == self.directory / "seed":
                value["admission"]["mean_utility"] = False
            return value

        rejected = False
        with patch.object(source_screen, "run_source_screen", side_effect=changed):
            try:
                self.run_search()
            except self.Error:
                rejected = True
        self.assertEqual(self.engine.physical_sends, 8)
        self.assertTrue(rejected)
        self.assertFalse((self.directory / "iterations/0/proposal").exists())

    def test_invalid_review_is_rejected_before_persisting_caller_fields(self):
        self.fixture(iterations=1)
        review = self.engine.fixture.review | {"raw_key": "fixture-redaction-canary-only"}
        with self.assertRaises(self.Error):
            self.prepare(review=review)
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.authority.summary()["runs"], [])
        self.assertEqual(self.engine.physical_sends, 0)

    def test_returned_child_screen_mismatch_cannot_publish_decision_or_start_next_iteration(self):
        from buddha import source_screen

        self.fixture(iterations=2)
        self.proposals = [REPAIRED, GRANDCHILD]
        self.prepare()
        actual = source_screen.run_source_screen

        def changed(*args, **kwargs):
            value = copy.deepcopy(actual(*args, **kwargs))
            if args[0] == self.directory / "iterations/0/screen":
                value["admission"]["mean_utility"] = False
            return value

        with (
            patch.object(source_screen, "run_source_screen", side_effect=changed),
            self.assertRaises(self.Error),
        ):
            self.run_search()
        self.assertEqual(self.engine.physical_sends, 15)
        self.assertFalse((self.directory / "iterations/0/decision.json").exists())
        self.assertFalse((self.directory / "iterations/1").exists())

    def test_prepared_future_original_owner_cannot_be_adopted_after_an_unfinished_prefix(self):
        from buddha import candidate_improvement
        from buddha.releases import Selection

        self.fixture(iterations=2)
        self.prepare()
        self.proposal_interrupt_once = True
        self.partial(self.run_search())
        future = self.directory / "iterations/1"
        future.mkdir()
        generation = self.seed.to_record()["generation"]
        packet = self.directory / "iterations/0/feedback/provenance.json"
        candidate_improvement.prepare_candidate_improvement(
            future / "proposal",
            descriptor=self.directory / "iterations/0/proposal.json",
            selection=Selection.from_bytes(_json(generation["selection"])),
            roots={name: Path(path) for name, path in generation["roots"].items()},
            authorization=self.authority,
            review=self.engine.fixture.review,
            budget_microusd=self.template["budget_microusd"],
            max_calls=self.template["max_calls"],
            expected_runtime_sha256=self.engine.candidate.expected_runtime,
            expected_feedback_provenance_sha256=sha(packet.read_bytes()),
        )
        before = self.engine.physical_sends
        with self.assertRaises(self.Error):
            self.run_search()
        self.assertEqual(self.engine.physical_sends, before)
        self.assertFalse((self.directory / "iterations/0/decision.json").exists())

    def test_completed_replay_and_retired_producer_passive_read_preserve_original_snapshot(self):
        self.fixture(iterations=1)
        self.proposals = [REPAIRED]
        self.prepare()
        result = self.run_search()
        original = (self.directory / "report.json").read_bytes()
        # A legitimate later owner outside this search advances the shared observation.
        self.h.prepare(self.seed, self.root / "outside-screen", self.authority)
        before = (
            self.h.files(self.directory),
            sha(self.authority.path.read_bytes()),
            self.engine.physical_sends,
        )
        with (
            patch(
                "buddha.candidate_run.CandidateSession", side_effect=AssertionError("new session")
            ),
            patch("buddha.executor.run_container", side_effect=AssertionError("new worker")),
        ):
            self.assertEqual(
                self.run_api(self.directory, transport=RawHTTPTransport(allow_paid=False)), result
            )
        self.assertEqual(
            (
                self.h.files(self.directory),
                sha(self.authority.path.read_bytes()),
                self.engine.physical_sends,
            ),
            before,
        )
        retired = self.root / "retired-producer"
        retired.mkdir()
        for role in ("agent", "runner"):
            source = self.engine.fixture.roots[role].resolve(strict=True)
            destination = (retired / role).resolve(strict=False)
            self.assertTrue(source.is_relative_to(self.root.resolve(strict=True)))
            self.assertTrue(destination.is_relative_to(retired.resolve(strict=True)))
            self.assertFalse(destination.exists())
            shutil.move(str(source), str(destination))
        self.assertEqual(self.inspect(), result)
        self.assertEqual((self.directory / "report.json").read_bytes(), original)

    def test_new_caller_hash_cannot_legitimize_changed_decision_or_scientific_publication(self):
        self.fixture(iterations=1)
        self.proposals = [REPAIRED]
        self.prepare()
        result = self.run_search()
        report_path = self.directory / "report.json"
        decision_path = self.directory / "iterations/0/decision.json"
        original_report, original_decision = report_path.read_bytes(), decision_path.read_bytes()
        before = self.engine.physical_sends
        try:
            changed = json.loads(original_report)
            changed["decisions"][0]["parent_id"] = False
            report_path.write_bytes(_json(changed))
            with self.h.readonly(), self.assertRaises(self.Error):
                self.inspect_api(self.directory, **self.reference())
            report_path.write_bytes(original_report)
            changed = json.loads(original_decision)
            changed["status"] = "rejected"
            decision_path.write_bytes(_json(changed))
            with self.h.readonly(), self.assertRaises(self.Error):
                self.inspect_api(self.directory, **self.reference())
        finally:
            report_path.write_bytes(original_report)
            decision_path.write_bytes(original_decision)
        self.assertEqual(self.engine.physical_sends, before)
        self.assertEqual(self.inspect(), result)

    def test_passive_final_capture_rejects_manifest_drift_after_real_result_derivation(self):
        from buddha import source_search

        self.fixture(iterations=1)
        self.prepare()
        result = self.run_search()
        self.assertEqual(self.inspect(), result)
        path = self.directory / "manifest.json"
        original = path.read_bytes()
        actual = source_search._result
        reached = False

        def changed(state):
            nonlocal reached
            value = actual(state)
            reached = True
            path.write_bytes(original + b"\n")
            return value

        before = self.engine.physical_sends
        try:
            with (
                self.h.readonly(),
                patch.object(source_search, "_result", side_effect=changed),
                self.assertRaises(self.Error),
            ):
                self.inspect_api(self.directory, **self.reference())
            self.assertTrue(reached)
        finally:
            path.write_bytes(original)
        self.assertEqual(self.engine.physical_sends, before)
        self.assertEqual(self.inspect(), result)

    def test_changed_proposal_authority_cannot_spend_from_another_same_scope_grant(self):
        from buddha import candidate_improvement

        self.fixture(iterations=1)
        self.prepare()
        other = self.h.authority(self.seed)
        actual = candidate_improvement.prepare_candidate_improvement

        def changed(*args, **kwargs):
            return actual(*args, **(kwargs | {"authorization": other}))

        rejected = False
        with patch.object(
            candidate_improvement, "prepare_candidate_improvement", side_effect=changed
        ):
            try:
                self.run_search()
            except self.Error:
                rejected = True
        self.assertEqual(other.summary()["operation_count"], 0)
        self.assertEqual(self.engine.physical_sends, 8)
        self.assertEqual(self.authority.summary()["operation_count"], 8)
        self.assertEqual(self.proposal_events, [])
        self.assertTrue(rejected)
        self.assertFalse((self.directory / "iterations/0/decision.json").exists())

    def test_prepared_screen_must_match_original_search_treatment_before_dispatch(self):
        from buddha import source_screen

        for stage, prefix in (("seed", 0), ("child", 9)):
            with self.subTest(stage=stage):
                case = SourceSearchTests("runTest")
                self.addCleanup(case.doCleanups)
                case.fixture(iterations=1)
                case.proposals = [REPAIRED]
                target = case.directory / ("seed" if stage == "seed" else "iterations/0/screen")
                replacement = case.seed
                if stage == "seed":
                    record = case.seed.to_record()
                    generation = record["generation"]
                    roots = {name: Path(path) for name, path in generation["roots"].items()}
                    agent = case.root / "alternate-seed"
                    agent.mkdir()
                    (agent / "candidate.py").write_bytes(REPAIRED.encode())
                    roots["agent"] = agent
                    generation["roots"] = {name: str(path) for name, path in roots.items()}
                    generation["selection"] = prepare_selection(
                        case.engine.candidate.release,
                        roots,
                        capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
                    ).to_record()
                    generation["executor"]["mounts"] = [
                        ["/agent", str(agent)],
                        ["/runner", str(roots["runner"])],
                    ]
                    replacement = case.h.screen(record)
                self.assertEqual(replacement.comparison_key(), case.seed.comparison_key())
                actual = source_screen.prepare_source_screen
                reached = []

                def changed(
                    *args,
                    target=target,
                    reached=reached,
                    case=case,
                    replacement=replacement,
                    actual=actual,
                    **kwargs,
                ):
                    if args[0] == target:
                        reached.append(case.engine.physical_sends)
                        kwargs = kwargs | {"screen": replacement}
                    return actual(*args, **kwargs)

                rejected = False
                with patch.object(source_screen, "prepare_source_screen", side_effect=changed):
                    case.prepare()
                    try:
                        case.run_search()
                    except case.Error:
                        rejected = True
                self.assertEqual(reached, [prefix])
                self.assertEqual(case.engine.physical_sends, prefix)
                self.assertEqual(len(case.worker_events), prefix)
                self.assertEqual(case.authority.summary()["operation_count"], prefix)
                self.assertTrue(rejected)
                self.assertFalse((case.directory / "iterations/0/decision.json").exists())

    def test_seed_lineage_cannot_also_be_declared_as_a_common_control_before_writes(self):
        from buddha import source_screen

        self.fixture(iterations=1)
        path = self.root / "declared-seed-lineage.json"
        raw = _json({"engineering_declaration_only": True})
        path.write_bytes(raw)
        record = self.seed.to_record()
        record["lineage"] = {"path": str(path), "sha256": sha(raw)}
        self.seed = self.h.screen(record)
        # This is a prewrite declaration contract, not a valid ancestry fixture
        # or evidence of the inferred later paid comparison mismatch.
        with (
            patch.object(
                source_screen,
                "prepare_source_screen",
                wraps=source_screen.prepare_source_screen,
            ) as prepare,
            self.assertRaises(self.Error),
        ):
            self.prepare(input_bindings={path: sha(raw)})
        self.assertFalse(self.directory.exists())
        prepare.assert_not_called()
        self.assertEqual(self.authority.summary()["runs"], [])
        self.assertEqual(self.engine.physical_sends, 0)


if __name__ == "__main__":
    unittest.main()
