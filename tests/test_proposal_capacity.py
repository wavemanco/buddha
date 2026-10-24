"""Original proposal calls establish capacity before any returned child runs."""

import base64
import copy
import hashlib
import json
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_source_mutation_witness as witnesses

from buddha.gateway import GatewayCall
from buddha.gateway_history import HistoricalGatewayOperation
from buddha.provider import ModelSpec
from buddha.releases import _json, prepare_selection
from buddha.wire import RawEnvelope


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ProposalCapacityNumbersTests(unittest.TestCase):
    def setUp(self):
        from buddha import source_capacity

        self.api = source_capacity
        self.source = "def generate(task, config, complete):\n    return []\n"
        self.spec = ModelSpec(
            "openai", "test-model", 1_050_000, 32_768, 1, 1, "https://example.org/synthetic-bounds"
        )

    def call(self, *, cap=32_768):
        return GatewayCall(
            "openai.chat-completions.v1",
            "primary",
            "fixed",
            0,
            _json(
                {
                    "model": "test-model",
                    "max_completion_tokens": cap,
                    "messages": [{"role": "user", "content": "Complete original feedback"}],
                }
            ),
        )

    def reply(self, *, inputs=100, outputs=200, content=None, finish="stop"):
        return RawEnvelope(
            "openai",
            200,
            _json(
                {
                    "model": "test-model",
                    "service_tier": "default",
                    "usage": {
                        "prompt_tokens": inputs,
                        "completion_tokens": outputs,
                        "completion_tokens_details": {"reasoning_tokens": outputs // 2},
                    },
                    "choices": [
                        {
                            "finish_reason": finish,
                            "message": {
                                "content": _json(
                                    {"source": self.source, "hypothesis": "Change"}
                                ).decode()
                                if content is None
                                else content,
                                "refusal": None,
                            },
                        }
                    ],
                }
            ),
            (("x-request-id", "offline-capacity"),),
        )

    def assess(self, call=None, reply=None):
        return self.api.assess_proposal_call(
            self.call() if call is None else call,
            self.reply() if reply is None else reply,
            spec=self.spec,
            child_source_sha256=sha(self.source.encode()),
            policy=self.api.proposal_capacity_policy(),
        )

    def test_actual_inclusive_boundary_not_short_visible_text_or_profile_cap(self):
        for inputs, outputs, decision, context, output in (
            (1_009_040, 24_576, "pass", 8192, 8192),
            (1_009_041, 24_576, "fail", 8191, 8192),
            (1_009_040, 24_577, "fail", 8192, 8191),
        ):
            with self.subTest(inputs=inputs, outputs=outputs):
                observed = self.assess(reply=self.reply(inputs=inputs, outputs=outputs))
                self.assertEqual(observed["decision"], decision)
                self.assertEqual(
                    (observed["context_slack"], observed["output_slack"]), (context, output)
                )
                self.assertTrue(observed["replacement_source"])
        observed = self.assess(self.call(cap=9000), self.reply(outputs=809))
        self.assertEqual(observed["output_slack"], 8191)
        self.assertEqual(observed["decision"], "fail")

    def test_tiny_complete_planning_output_is_not_a_replacement_source_margin(self):
        observed = self.assess(self.call(cap=64), self.reply(outputs=32, content="A full plan"))
        self.assertEqual(observed["decision"], "pass")
        self.assertFalse(observed["replacement_source"])
        self.assertEqual(observed["output_slack"], 32)
        observed = self.assess(
            self.call(cap=64), self.reply(outputs=32, content="plan", finish="length")
        )
        self.assertEqual(
            (observed["measurement_status"], observed["decision"]), ("partial", "unavailable")
        )

    def test_policy_is_closed_detached_and_context_is_original_selected_bound(self):
        policy = self.api.proposal_capacity_policy()
        policy["min_context_slack_tokens"] = 0
        self.assertEqual(self.api.proposal_capacity_policy()["min_context_slack_tokens"], 8192)
        for bad in (policy, None, {}, self.api.proposal_capacity_policy() | {"extra": 1}):
            with self.subTest(bad=bad), self.assertRaises(self.api.SourceCapacityError):
                self.api.assess_proposal_call(
                    self.call(),
                    self.reply(),
                    spec=self.spec,
                    child_source_sha256=sha(self.source.encode()),
                    policy=bad,
                )
        with self.assertRaises(self.api.SourceCapacityError):
            self.api.assess_proposal_call(
                self.call(),
                self.reply(),
                spec=replace(self.spec, input_token_ceiling=100),
                child_source_sha256=sha(self.source.encode()),
                policy=self.api.proposal_capacity_policy(),
            )

    def test_enabled_helper_closure_preserves_legacy_defaults(self):
        from buddha import source_handoff, source_launch, source_search

        helper = Path(self.api.__file__).absolute()
        for module in (source_handoff, source_launch):
            with self.subTest(module=module.__name__):
                self.assertNotIn(helper, module._sources())
                self.assertIn(helper, module._sources(proposal_capacity=True))
        self.assertNotIn(helper, source_search._sources())

    def test_completed_raw_receipt_needs_exact_original_reserve_and_usage_charge(self):
        from buddha import source_search

        self.spec = replace(self.spec, output_microusd_per_million=1_000_000)
        root = Path.cwd().absolute() / "offline-capacity"
        location = root / "iterations/0"
        call, envelope = self.call(), self.reply()
        identity = {
            "directory": str(location / "proposal/owners/0"),
            "run_id": "offline-original",
            "manifest_sha256": "1" * 64,
            "ledger_sha256": "2" * 64,
        }
        profile = {
            "spec": asdict(self.spec),
            "response_models": [self.spec.model],
            "response_tiers": ["", "default"],
            "request_tiers": ["default"],
            "allow_omitted_tier": True,
        }
        operation = HistoricalGatewayOperation(
            "3" * 64,
            "4" * 64,
            self.spec.reserve_microusd(),
            "completed",
            self.spec.cost_microusd(100, 200),
            "offline-capacity",
            _json({"request": call.to_record(), "envelope": envelope.to_record()}).decode(),
            None,
            None,
        )

        def read(selected):
            owner = SimpleNamespace(
                directory=Path(identity["directory"]),
                run_id=identity["run_id"],
                manifest_sha256=identity["manifest_sha256"],
                ledger_sha256=identity["ledger_sha256"],
                manifest={"profiles": {call.capability: {"profiles": {"primary": profile}}}},
                operations=(selected,),
                accounting=lambda: {},
            )
            reader = SimpleNamespace(
                root=root, owner=lambda path: owner, capture=SimpleNamespace(entries={})
            )
            return source_search._capacity_progress(
                reader,
                {
                    "provenance": {"owner": identity},
                    "child": {"source_sha256": sha(self.source.encode())},
                },
                {"directory": str(location / "proposal"), "report_sha256": "5" * 64},
                self.api.proposal_capacity_policy(),
                location,
                child_directory=location / "screen",
            )

        self.assertEqual(read(operation)["record"]["decision"], "pass")
        contradictions = {
            "reserve": replace(operation, reserve_microusd=operation.reserve_microusd + 1),
            "charge": replace(operation, actual_microusd=operation.actual_microusd + 1),
            "request-id": replace(operation, provider_request_id="contradictory-id"),
        }
        for label, selected in contradictions.items():
            with (
                self.subTest(contradiction=label),
                self.assertRaises(source_search.SourceSearchError),
            ):
                read(selected)
        for label, changed in (
            ("missing-usage", {"usage": None}),
            ("model", {"model": "wrong-model"}),
            ("tier", {"service_tier": "priority"}),
            ("usage-bound", {"usage": {"prompt_tokens": 100, "completion_tokens": 32_769}}),
        ):
            raw = json.loads(envelope.body) | changed
            bad = replace(envelope, body=_json(raw), received_sha256=None)
            selected = replace(
                operation,
                receipt_json=_json(
                    {"request": call.to_record(), "envelope": bad.to_record()}
                ).decode(),
            )
            with (
                self.subTest(contradiction=label),
                self.assertRaises(source_search.SourceSearchError),
            ):
                read(selected)
        # A normally billed length-limited reply remains an unavailable observation.
        raw = json.loads(envelope.body)
        raw["choices"][0]["finish_reason"] = "length"
        selected = replace(
            operation,
            receipt_json=_json(
                {
                    "request": call.to_record(),
                    "envelope": replace(
                        envelope, body=_json(raw), received_sha256=None
                    ).to_record(),
                }
            ).decode(),
        )
        self.assertEqual(read(selected)["record"]["decision"], "unavailable")
        small = self.call(cap=64)
        small_reply = self.reply(outputs=32, content="A complete tiny plan")
        selected = replace(
            operation,
            receipt_json=_json(
                {"request": small.to_record(), "envelope": small_reply.to_record()}
            ).decode(),
            actual_microusd=self.spec.cost_microusd(100, 32),
        )
        with self.assertRaises(source_search.SourceSearchError):
            read(selected)  # The larger profile's reservation cannot stand in for this request.
        selected = replace(
            selected, reserve_microusd=replace(self.spec, max_output_tokens=64).reserve_microusd()
        )
        self.assertEqual(read(selected)["record"]["decision"], "unavailable")


class ProposalCapacityTransitionsTests(unittest.TestCase):
    def fixture(self, *, fail_role=None, planning=False, unobserved=False):
        from buddha import source_capacity

        harness = witnesses._Harness(self)
        case, engine = harness.case, harness.case.engine
        f = engine.fixture
        profile = f.profiles["profiles"]["primary"]["spec"]
        profile.update(
            input_token_ceiling=1_050_000,
            max_output_tokens=32_768,
            input_microusd_per_million=1,
            output_microusd_per_million=1,
        )
        f.write("host", "profiles/openai.json", json.dumps(f.profiles))
        record = case.seed.to_record()
        record["selected_ids"] = ["1"]
        record["generation"]["config"]["max_output_tokens"] = 32_768
        record["generation"]["selection"] = prepare_selection(
            engine.candidate.release,
            f.roots,
            capabilities={"openai.chat-completions.v1": "profiles/openai.json"},
        ).to_record()
        native = record["native"]
        native["selection"] = prepare_selection(
            engine.candidate.release,
            {k: Path(v) for k, v in native["roots"].items()},
            capabilities=native["selection"]["capabilities"],
        ).to_record()
        engine.native["selection"] = copy.deepcopy(native["selection"])
        case.seed = case.h.screen(record)
        case.authority = case.h.authority(case.seed)
        case.template["config"]["max_output_tokens"] = 32_768
        harness.witness_callbacks = 2 if planning else 1
        original = case.execute_improvement

        def improve(spec, initial, handle, source):
            owner = handle.__self__.gateway.directory
            witness = harness.witness_root(owner)
            role = (
                "counted"
                if witness is None
                else ("seed-witness" if witness.name == "seed-witness" else "child-witness")
            )
            request = engine.candidate.request
            response = f.response
            ordinal = [0]

            def requested(sequence=0, **kwargs):
                frame = request(sequence, **kwargs)
                body = json.loads(base64.b64decode(frame["body_base64"]))
                body["max_completion_tokens"] = (
                    64 if planning and witness and sequence == 0 else 32_768
                )
                frame["body_base64"] = base64.b64encode(_json(body)).decode()
                return frame

            def responded(**kwargs):
                selected = copy.deepcopy(kwargs)
                plan = planning and witness and ordinal[0] == 0
                selected["choices"][0]["finish_reason"] = "stop"
                if plan:
                    selected["choices"][0]["message"]["content"] = "A complete tiny plan"
                if unobserved and role == "seed-witness":
                    selected["choices"][0]["message"]["content"] = "Complete procedural advice"
                selected["usage"] = {
                    "prompt_tokens": 5,
                    "completion_tokens": 24_577 if role == fail_role and not plan else 3,
                }
                ordinal[0] += 1
                return response(**selected)

            with (
                patch.object(engine.candidate, "request", side_effect=requested),
                patch.object(f, "response", side_effect=responded),
            ):
                return original(spec, initial, handle, source)

        case.execute_improvement = improve
        case.prepare(source_copy=True, proposal_capacity=source_capacity.proposal_capacity_policy())
        return harness

    def test_each_capacity_failure_stops_before_that_child_and_reuses_settled_proposal(self):
        for role in ("seed-witness", "counted", "child-witness"):
            with self.subTest(role=role):
                h = self.fixture(fail_role=role)
                c = h.case
                result = h.run()
                c.partial(result)
                self.assertEqual(result["reason"], "proposal_capacity")
                location = (
                    c.directory
                    / (
                        {
                            "seed-witness": "seed-witness",
                            "counted": "iterations/0",
                            "child-witness": "iterations/0/witness",
                        }[role]
                    )
                )
                self.assertFalse(
                    (location / ("screen" if role == "counted" else "generation")).exists()
                )
                saved = json.loads((location / "proposal-capacity.json").read_bytes())
                self.assertEqual(
                    (saved["measurement_status"], saved["decision"]), ("complete", "fail")
                )
                before = c.engine.physical_sends, c.authority.summary()["spent_microusd"]
                resumed = h.run()
                self.assertEqual(resumed["reason"], "proposal_capacity")
                self.assertEqual(
                    (c.engine.physical_sends, c.authority.summary()["spent_microusd"]), before
                )
                self.assertEqual(c.authority.summary()["reserved_microusd"], 0)

    def test_small_planning_caps_complete_and_replay_with_common_comparison_unchanged(self):
        h = self.fixture(planning=True)
        c = h.case
        report = h.run()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(len(report["proposal_capacity"]["checkpoints"]), 3)
        for path in c.directory.rglob("proposal-capacity.json"):
            observed = json.loads(path.read_bytes())
            self.assertEqual(observed["decision"], "pass")
            self.assertGreaterEqual(observed["replacement_count"], 1)
        controls = {
            json.loads(p.read_bytes())["controls_sha256"]
            for p in (
                c.directory / "seed/report.json",
                c.directory / "iterations/0/screen/report.json",
            )
        }
        self.assertEqual(len(controls), 1)
        self.assertEqual(c.inspect(), report)
        # Neither a rewritten scalar nor a deleted checkpoint can certify history.
        for path in c.directory.rglob("proposal-capacity.json"):
            original = path.read_bytes()
            try:
                changed = json.loads(original)
                changed["operations"][0]["measurement"]["context_slack"] += 1
                path.write_bytes(_json(changed))
                with self.assertRaises(c.Error):
                    c.inspect()
                path.unlink()
                with self.assertRaises(c.Error):
                    c.inspect()
            finally:
                path.write_bytes(original)
        before = c.engine.physical_sends
        self.assertEqual(h.run(paid=False), report)
        self.assertEqual(c.engine.physical_sends, before)

    def test_capacity_needs_observed_replacement_and_keeps_unknown_liability(self):
        h = self.fixture(unobserved=True)
        result = h.run()
        self.assertEqual(result["reason"], "proposal_capacity")
        saved = json.loads((h.case.directory / "seed-witness/proposal-capacity.json").read_bytes())
        self.assertEqual((saved["decision"], saved["replacement_count"]), ("unavailable", 0))
        self.assertFalse((h.case.directory / "seed-witness/generation").exists())
        other = self.fixture()
        other.unknown_once = True
        result = other.run()
        self.assertEqual(result["reason"], "unknown")
        self.assertGreater(other.case.authority.summary()["reserved_microusd"], 0)
        self.assertFalse((other.case.directory / "seed-witness/proposal-capacity.json").exists())
        self.assertFalse((other.case.directory / "seed-witness/generation").exists())

    def test_original_proposal_resumes_both_sides_of_checkpoint_publication(self):
        from buddha import source_capacity, source_launch_state, source_search

        h = self.fixture(planning=True)
        c = h.case
        publish = source_search._publish_capacity
        publish_complete = source_search.pipeline.publish_complete
        prepare = source_search.candidate_improvement.prepare_candidate_improvement
        stopped = [False] * 6
        refused_copies = []

        def inspect():
            return source_launch_state.inspect_prepared_search(
                c.directory,
                c.authority.path,
                seed_screen=c.seed,
                proposal_template=c.template,
                spec=c.spec,
                review=c.engine.fixture.review,
                expected_runtime_sha256=c.engine.candidate.expected_runtime,
                input_bindings={},
                mutation_witness=True,
                source_copy=True,
                proposal_capacity=source_capacity.proposal_capacity_policy(),
            )

        def stop_before_prepare(directory, *args, **kwargs):
            if directory == c.directory / "seed-witness/proposal" and not stopped[0]:
                stopped[0] = True
                raise KeyboardInterrupt
            if directory == c.directory / "iterations/0/proposal" and not stopped[3]:
                stopped[3] = True
                raise KeyboardInterrupt
            return prepare(directory, *args, **kwargs)

        def interrupted(root, authorization, location, policy, **kwargs):
            if location.name == "seed-witness" and not stopped[2]:
                stopped[2] = True
                raise KeyboardInterrupt
            result = publish(root, authorization, location, policy, **kwargs)
            if location.name == "0" and not stopped[5]:
                stopped[5] = True
                raise KeyboardInterrupt
            return result

        def stop_before_report(path, *args, **kwargs):
            if path == c.directory / "seed-witness/proposal/report.json" and not stopped[1]:
                stopped[1] = True
                raise KeyboardInterrupt
            if path == c.directory / "iterations/0/proposal/report.json" and not stopped[4]:
                stopped[4] = True
                raise KeyboardInterrupt
            return publish_complete(path, *args, **kwargs)

        for index in range(6):
            with (
                patch.object(source_search, "_publish_capacity", side_effect=interrupted),
                patch.object(
                    source_search.candidate_improvement,
                    "prepare_candidate_improvement",
                    side_effect=stop_before_prepare,
                ),
                patch.object(
                    source_search.pipeline, "publish_complete", side_effect=stop_before_report
                ),
            ):
                with self.assertRaises(source_search.SourceSearchInterrupted) as error:
                    h.run()
            self.assertEqual(error.exception.partial["reason"], "cancelled")
            if index in {0, 1, 3, 4}:
                location = c.directory / ("seed-witness" if index < 2 else "iterations/0")
                copied = location / "agent"
                copied.mkdir()
                parent = Path(c.seed.to_record()["generation"]["roots"]["agent"])
                (copied / "candidate.py").write_bytes((parent / "candidate.py").read_bytes())
                try:
                    inspect()
                except c.Error as error:
                    self.assertIn("proposal", str(error))
                    refused_copies.append(index)
                finally:
                    (copied / "candidate.py").unlink()
                    copied.rmdir()
            state = inspect()
            if index == 0:
                self.assertEqual(state["next_role"], "proposal")
                self.assertFalse((c.directory / "seed-witness/proposal").exists())
            elif index in {1, 2}:
                self.assertIsNone(state["next_owner"])
                self.assertFalse((c.directory / "seed-witness/proposal-capacity.json").exists())
                self.assertEqual(
                    (c.directory / "seed-witness/proposal/report.json").exists(), index == 2
                )
            elif index == 3:
                self.assertEqual(state["next_role"], "proposal")
                self.assertFalse((c.directory / "iterations/0/proposal").exists())
            elif index == 4:
                self.assertIsNone(state["next_owner"])
                self.assertTrue((c.directory / "iterations/0/proposal/completed/0.json").exists())
                self.assertFalse((c.directory / "iterations/0/proposal/report.json").exists())
                self.assertFalse((c.directory / "iterations/0/proposal-capacity.json").exists())
                self.assertFalse((c.directory / "iterations/0/screen").exists())
            else:
                self.assertTrue((c.directory / "iterations/0/proposal-capacity.json").exists())
                self.assertFalse((c.directory / "iterations/0/screen").exists())
        self.assertEqual(refused_copies, [0, 1, 3, 4], "premature private copies must be refused")
        report = h.run()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(len(report["proposal_capacity"]["checkpoints"]), 3)
        self.assertEqual(len(h.improvements), 3)
        self.assertEqual(len({event["owner"] for event in h.improvements}), 3)
        self.assertEqual(c.authority.summary()["reserved_microusd"], 0)
        self.assertEqual(c.inspect(), report)


if __name__ == "__main__":
    unittest.main()
