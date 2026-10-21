"""Passive cost descriptions retain saved money, attempts and uncertainty."""

import base64
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

import test_gateway as gateway_fixtures
import test_policy_results as reader_fixtures

from buddha import native_evaluation, policy_results
from buddha.doctor import _Capture, _owner
from buddha.provider import ProviderUncertain
from buddha.releases import _json
from buddha.wire import RawEnvelope


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PolicyCostsTests(unittest.TestCase):
    def gateway_fixture(self):
        fixture = gateway_fixtures.GatewayTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def study_fixture(self):
        # Composition deliberately does not inherit/rerun the eight reader tests.
        reader = reader_fixtures.PolicyResultsTests("runTest")
        reader.setUp()
        self.addCleanup(reader.doCleanups)
        return reader

    def owner(self, fixture):
        capture = _Capture(fixture.directory)
        owner = _owner(capture, fixture.directory)
        capture.finish()
        return owner

    def coordinates(self, *, role="quality"):
        return {
            "cell_id": "c" * 64,
            "arm_id": "a" * 64,
            "arm_index": 0,
            "generation_repeat": 0,
            "judge_occasion": 1,
            "stage_index": 2,
            "stage_role": role,
        }

    def evidence(self, owner, *, fallback=None, role="quality"):
        return policy_results._operation_evidence(owner, self.coordinates(role=role), fallback)

    def costs(self, owner, rows, *, fallback=None):
        owner_row = {
            "directory": str(owner.directory),
            "run_id": owner.run_id,
            "accounting": owner.accounting(),
            **self.coordinates(),
        }
        return policy_results._cost_report([owner_row], rows, ["a" * 64], 1, fallback)

    def test_terminal_and_checkpoint_are_retained_but_usage_and_charge_count_once(self):
        fixture = self.gateway_fixture()
        gateway = fixture.gateway()
        with self.assertRaises(ProviderUncertain):
            fixture.send(gateway, connection=fixture.connection(fixture.response(usage={})))
        raw = fixture.response(
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "prompt_tokens_details": {"cached_tokens": 4},
                "completion_tokens_details": {"reasoning_tokens": 7},
            }
        ).read.return_value
        terminal = {
            "format": "buddha.gateway-receipt.v1",
            "request": fixture.call.to_record(),
            "envelope": RawEnvelope(
                "openai", 200, raw, (("x-request-id", "different-terminal-id"),)
            ).to_record(),
        }
        gateway.ledger.complete(
            gateway.operation_id(fixture.call),
            response=terminal,
            actual_microusd=17,
            provider_request_id="different-terminal-id",
        )
        owner = self.owner(fixture)
        rows = self.evidence(owner, fallback="test-model")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["evidence_source"], "receipt")
        self.assertTrue(row["checkpoint_present"])
        self.assertEqual(
            row["checkpoint_sha256"], sha(owner.operations[0].checkpoint_json.encode())
        )
        self.assertEqual((row["actual_microusd"], row["held_microusd"]), (17, 0))
        self.assertEqual(row["committed_microusd"], 17)
        self.assertEqual(row["usage"]["input_tokens"], 10)
        self.assertEqual(row["usage"]["output_tokens"], 20)
        self.assertEqual(row["usage"]["service_tier"], "default")
        self.assertTrue(row["fallback_model_requested"])
        self.assertEqual((row["causal_fallback"], row["row_attribution"]), ("unknown", "unknown"))
        summary = self.costs(owner, rows, fallback="test-model")["current_study"]
        self.assertEqual((summary["spent_microusd"], summary["operation_count"]), (17, 1))
        self.assertEqual((summary["receipt_count"], summary["checkpoint_count"]), (1, 0))
        self.assertEqual(summary["tokens"]["input_tokens"], 10)
        self.assertEqual(summary["tokens"]["output_tokens"], 20)
        exported = _json(rows)
        self.assertNotIn(b"body_base64", exported)
        self.assertNotIn(b"{malformed assistant JSON", exported)
        self.assertNotIn(gateway_fixtures.KEY.encode(), exported)

    def test_usage_decoder_preserves_anthropic_inclusive_cache_and_missing_counters(self):
        fixture = self.gateway_fixture()
        fixture.send()
        owner = self.owner(fixture)
        operation = owner.operations[0]
        # Unit input to the metadata projector; monetary facts stay independently
        # recorded. These replacement envelopes do not claim a new funded call.
        for usage, expected in (
            (
                {
                    "input_tokens": 3,
                    "cache_creation_input_tokens": 4,
                    "cache_read_input_tokens": 5,
                    "output_tokens": 6,
                },
                (12, 6),
            ),
            ({"input_tokens": True, "output_tokens": 6}, None),
            ({}, None),
        ):
            with self.subTest(usage=usage):
                receipt = operation.receipt
                receipt["envelope"] = RawEnvelope(
                    "anthropic",
                    200,
                    _json({"model": "anthropic-fixture", "usage": usage}),
                    (("request-id", "anthropic-unit-id"),),
                ).to_record()
                changed = replace(operation, receipt_json=_json(receipt).decode())
                rows = self.evidence(replace(owner, operations=(changed,)))
                self.assertEqual(rows[0]["actual_microusd"], 11)
                if expected is None:
                    self.assertIsNone(rows[0]["usage"])
                    self.assertTrue(rows[0]["usage_reason"])
                    tokens = self.costs(owner, rows)["current_study"]["tokens"]
                    self.assertEqual(
                        (tokens["known_operations"], tokens["unknown_operations"]), (0, 1)
                    )
                    self.assertIsNone(tokens["input_tokens"])
                    self.assertIsNone(tokens["output_tokens"])
                else:
                    self.assertEqual(
                        (rows[0]["usage"]["input_tokens"], rows[0]["usage"]["output_tokens"]),
                        expected,
                    )

    def test_reserved_dispatched_and_unknown_keep_holds_and_distinct_evidence_states(self):
        for state in ("reserved", "dispatched", "unknown-no-reply", "unknown-reply"):
            with self.subTest(state=state):
                fixture = self.gateway_fixture()
                gateway = fixture.gateway(live=state not in {"reserved", "dispatched"})
                if state in {"reserved", "dispatched"}:
                    with self.assertRaises(ValueError):
                        fixture.send(gateway)
                    if state == "dispatched":
                        gateway.ledger.dispatch(gateway.operation_id(fixture.call))
                else:
                    connection = fixture.connection(fixture.response(usage={}))
                    if state == "unknown-no-reply":
                        connection.getresponse.side_effect = TimeoutError("synthetic timeout")
                    with self.assertRaises(ProviderUncertain):
                        fixture.send(gateway, connection=connection)
                owner = self.owner(fixture)
                rows = self.evidence(owner)
                row = rows[0]
                self.assertEqual(row["status"], state.split("-")[0])
                self.assertIsNone(row["actual_microusd"])
                self.assertEqual((row["held_microusd"], row["committed_microusd"]), (300, 300))
                source = "checkpoint" if state == "unknown-reply" else "missing"
                self.assertEqual(row["evidence_source"], source)
                self.assertIsNone(row["usage"])
                summary = self.costs(owner, rows)["current_study"]
                self.assertEqual(
                    (summary["spent_microusd"], summary["reserved_microusd"]), (0, 300)
                )
                self.assertEqual(summary["response_count"], int(source == "checkpoint"))
                self.assertEqual(summary["missing_evidence_count"], int(source == "missing"))
                self.assertIsNone(summary["tokens"]["input_tokens"])

    def test_retry_is_saved_attempt_metadata_not_equal_body_or_fallback_cause(self):
        fixture = self.gateway_fixture()
        calls = [
            fixture.call,
            replace(fixture.call, logical_id="independent-same-body"),
            replace(fixture.call, attempt=1),
        ]
        for call in calls:
            fixture.send(call=call)
        owner = self.owner(fixture)
        rows = self.evidence(owner, fallback="test-model")
        self.assertEqual(len({row["operation_id"] for row in rows}), 3)
        self.assertEqual(sorted(row["attempt"] for row in rows), [0, 0, 1])
        self.assertEqual(sum(row["physical_retry"] is True for row in rows), 1)
        self.assertEqual(sum(row["physical_retry"] is False for row in rows), 2)
        self.assertTrue(all(row["fallback_model_requested"] is True for row in rows))
        self.assertTrue(all(row["causal_fallback"] == "unknown" for row in rows))
        cost = self.costs(owner, rows, fallback="test-model")
        self.assertEqual(cost["physical_retry"]["known"]["operation_count"], 1)
        self.assertEqual(cost["physical_retry"]["not_retry"]["operation_count"], 2)
        self.assertEqual(cost["quality_fallback"]["requested_fallback"]["operation_count"], 3)
        self.assertTrue(
            all(row["fallback_model_requested"] is None for row in self.evidence(owner))
        )
        self.assertTrue(
            all(
                row["fallback_model_requested"] is None
                for row in self.evidence(owner, fallback="test-model", role="grouping")
            )
        )

    def test_mixed_known_and_unknown_usage_has_lower_bounds_but_no_invented_total(self):
        fixture = self.gateway_fixture()
        gateway = fixture.gateway()
        fixture.send(gateway)
        with self.assertRaises(ProviderUncertain):
            fixture.send(
                gateway,
                call=replace(fixture.call, logical_id="uncertain-second-operation"),
                connection=fixture.connection(fixture.response(usage={})),
            )
        owner = self.owner(fixture)
        rows = self.evidence(owner)
        summary = self.costs(owner, rows)["current_study"]
        self.assertEqual(
            {
                name: summary[name]
                for name in (
                    "committed_microusd",
                    "spent_microusd",
                    "reserved_microusd",
                    "operation_count",
                )
            },
            {
                "committed_microusd": 311,
                "spent_microusd": 11,
                "reserved_microusd": 300,
                "operation_count": 2,
            },
        )
        self.assertEqual(summary["receipt_count"], 1)
        self.assertEqual(summary["checkpoint_count"], 1)
        self.assertEqual(summary["response_count"], 2)
        self.assertEqual(summary["tokens"]["known_operations"], 1)
        self.assertEqual(summary["tokens"]["unknown_operations"], 1)
        self.assertEqual(summary["tokens"]["known_input_tokens"], 5)
        self.assertEqual(summary["tokens"]["known_output_tokens"], 3)
        self.assertIsNone(summary["tokens"]["input_tokens"])
        self.assertIsNone(summary["tokens"]["output_tokens"])

    def test_missing_request_metadata_never_erases_money_or_invents_retry(self):
        fixture = self.gateway_fixture()
        fixture.send()
        owner = self.owner(fixture)
        operation = owner.operations[0]
        for model in (False, {}, ""):
            with self.subTest(model=model):
                receipt = operation.receipt
                request = receipt["request"]
                request["body_base64"] = base64.b64encode(_json({"model": model})).decode()
                changed = replace(operation, receipt_json=_json(receipt).decode())
                row = self.evidence(replace(owner, operations=(changed,)))[0]
                self.assertIsNone(row["requested_model"])
                self.assertTrue(row["metadata_reason"])
                self.assertEqual(row["actual_microusd"], 11)
                self.assertFalse(row["physical_retry"])

    def metadata_envelope(self, owner, envelope):
        # A metadata-only unit variant of a real retained operation. No assertion
        # here claims this replacement response was dispatched or authenticated.
        operation = owner.operations[0]
        receipt = operation.receipt
        receipt["envelope"] = envelope.to_record()
        changed = replace(operation, receipt_json=_json(receipt).decode())
        return self.evidence(replace(owner, operations=(changed,)))[0]

    def test_openai_reply_status_keeps_all_choices_refusal_shapes_and_no_text(self):
        fixture = self.gateway_fixture()
        fixture.send()
        owner = self.owner(fixture)
        refusal = "DO-NOT-EXPORT-REFUSAL-é"
        content = "DO-NOT-EXPORT-CONTENT"
        choices = [
            {"finish_reason": "stop", "message": {"content": content}},
            {"finish_reason": "length", "message": {"refusal": None}},
            {"finish_reason": "content_filter", "message": {"refusal": ""}},
            {"finish_reason": "tool_calls", "message": {"refusal": refusal}},
        ]
        raw = _json(
            {
                "model": "test-model",
                "service_tier": "default",
                "choices": choices,
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }
        )
        plain = RawEnvelope("openai", 200, raw, (("x-request-id", "reply-unit"),))
        row = self.metadata_envelope(owner, plain)
        status = row["reply_status"]
        self.assertEqual(status["availability"], "available")
        self.assertEqual(
            status["finish_reasons"], ["stop", "length", "content_filter", "tool_calls"]
        )
        self.assertIsNone(status["stop_reason"])
        self.assertEqual(status["refusal_applicability"], "message_field")
        self.assertEqual(
            status["refusals"],
            [
                {"present": False, "is_null": None, "nonempty": None, "sha256": None},
                {"present": True, "is_null": True, "nonempty": False, "sha256": None},
                {"present": True, "is_null": False, "nonempty": False, "sha256": sha(b"")},
                {
                    "present": True,
                    "is_null": False,
                    "nonempty": True,
                    "sha256": sha(refusal.encode("utf-8")),
                },
            ],
        )
        compressed = RawEnvelope(
            "openai",
            200,
            gzip.compress(raw, mtime=0),
            (("content-encoding", "gzip"), ("x-request-id", "reply-unit")),
        )
        zipped = self.metadata_envelope(owner, compressed)
        self.assertEqual(zipped["reply_status"], status)
        self.assertEqual(zipped["usage"], row["usage"])
        exported = json.dumps(row, ensure_ascii=False)
        self.assertNotIn(refusal, exported)
        self.assertNotIn(content, exported)
        for choice in (
            {"message": {}},
            {"finish_reason": False, "message": {}},
            {"finish_reason": "stop", "message": []},
            {"finish_reason": "length", "message": {"refusal": False}},
        ):
            with self.subTest(choice=choice):
                response = fixture.response(choices=[choice]).read.return_value
                variant = self.metadata_envelope(
                    owner, RawEnvelope("openai", 200, response, (("x-request-id", "partial-unit"),))
                )
                observed = variant["reply_status"]
                self.assertEqual(observed["availability"], "partial")
                expected = choice.get("finish_reason")
                self.assertEqual(
                    observed["finish_reasons"], [expected if type(expected) is str else None]
                )
                if "refusal" in choice.get("message", {}):
                    self.assertIsNone(observed["refusals"][0]["nonempty"])
                self.assertEqual(
                    (variant["actual_microusd"], variant["usage"]["input_tokens"]), (11, 5)
                )

    def test_reply_status_unavailable_and_anthropic_stop_do_not_change_recorded_money(self):
        fixture = self.gateway_fixture()
        fixture.send()
        owner = self.owner(fixture)
        for stop in ("end_turn", "max_tokens", "refusal"):
            with self.subTest(stop=stop):
                raw = _json(
                    {
                        "model": "anthropic-fixture",
                        "stop_reason": stop,
                        "content": [{"type": "thinking", "thinking": "PRIVATE-THINKING"}],
                        "usage": {"input_tokens": 3, "output_tokens": 4},
                    }
                )
                row = self.metadata_envelope(
                    owner, RawEnvelope("anthropic", 200, raw, (("request-id", "stop-unit"),))
                )
                status = row["reply_status"]
                self.assertEqual(status["availability"], "available")
                self.assertEqual(status["stop_reason"], stop)
                self.assertIsNone(status["finish_reasons"])
                self.assertIsNone(status["refusals"])
                self.assertEqual(status["refusal_applicability"], "stop_reason")
                self.assertNotIn("PRIVATE-THINKING", json.dumps(row))
                self.assertEqual((row["actual_microusd"], row["usage"]["output_tokens"]), (11, 4))
        valid = fixture.response().read.return_value
        envelopes = [
            RawEnvelope("openai", 403, valid),
            RawEnvelope("openai", 200, valid, truncated=True),
            RawEnvelope("openai", 200, valid, headers_complete=False),
            RawEnvelope("openai", 200, b"", withheld=True, received_sha256="d" * 64),
            RawEnvelope("openai", 200, b"{"),
            RawEnvelope("openai", 200, fixture.response(choices=[]).read.return_value),
            RawEnvelope("openai", 200, fixture.response(choices=[{}] * 129).read.return_value),
        ]
        for index, envelope in enumerate(envelopes):
            with self.subTest(envelope_case=index):
                row = self.metadata_envelope(owner, envelope)
                self.assertEqual(row["reply_status"]["availability"], "unavailable")
                self.assertRegex(row["reply_status"]["reason"], r"^[a-z0-9_]+$")
                self.assertEqual(row["actual_microusd"], 11)
                if index in {5, 6}:
                    self.assertEqual(row["usage"]["input_tokens"], 5)
        missing = replace(
            owner.operations[0],
            status="unknown",
            actual_microusd=None,
            receipt_json=None,
            checkpoint_json=None,
            provider_request_id=None,
            checkpoint_request_id=None,
        )
        status = self.evidence(replace(owner, operations=(missing,)))[0]["reply_status"]
        self.assertEqual(
            (status["availability"], status["reason"]), ("unavailable", "missing_evidence")
        )

    def test_operation_ceiling_precedes_private_and_aggregate_metadata_expansion(self):
        fixture = self.gateway_fixture()
        for index in range(3):
            fixture.send(call=replace(fixture.call, logical_id="bounded-" + str(index)))
        owner = self.owner(fixture)
        with (
            patch.object(policy_results, "MAX_OPERATIONS", 2),
            patch.object(policy_results, "extract_usage", side_effect=AssertionError("expanded")),
            self.assertRaises(policy_results.PolicyResultsError),
        ):
            self.evidence(owner)
        rows = self.evidence(owner)
        with (
            patch.object(policy_results, "MAX_OPERATIONS", 2),
            self.assertRaises(policy_results.PolicyResultsError),
        ):
            self.costs(owner, rows)

        reader = self.study_fixture()
        reader.fixture.prepare()
        reader.fixture.fixture.timeout_native_once = True
        stopped = reader.fixture.run_study()
        self.assertEqual(reader.fixture.fixture.physical_sends, 5)
        with (
            patch.object(policy_results, "MAX_OPERATIONS", 4),
            patch.object(
                policy_results, "_operation_evidence", side_effect=AssertionError("expanded owner")
            ),
            self.assertRaises(policy_results.PolicyResultsError),
        ):
            # Neither owner exceeds four operations. The combined population does,
            # so the root must reject before expanding even the first owner's rows.
            reader.read(observation=reader.fixture.directory / stopped["observation"])

    def test_complete_public_reader_reconciles_real_coordinates_and_inclusive_usage_passively(self):
        reader = self.study_fixture()
        agent = reader.fixture.fixture.agent
        original = agent.response

        def response(*args, **kwargs):
            return original(*args, **kwargs) | {
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 4},
                    "completion_tokens_details": {"reasoning_tokens": 7},
                }
            }

        with patch.object(agent, "response", side_effect=response):
            reader.complete()
        self.assertEqual(reader.fixture.fixture.physical_sends, 64)
        result = reader.read()
        cost = result["registered"]["accounting"]
        rows = cost["operations"]
        self.assertEqual(len(rows), 64)
        self.assertEqual(len({row["operation_id"] for row in rows}), 64)
        self.assertEqual(cost["owner_coverage"], {"planned": 56, "present": 56})
        self.assertEqual(cost["current_study"]["spent_microusd"], 3200)
        self.assertEqual(cost["current_study"]["reserved_microusd"], 0)
        self.assertEqual(cost["current_study"]["tokens"]["input_tokens"], 640)
        self.assertEqual(cost["current_study"]["tokens"]["output_tokens"], 1280)
        self.assertEqual(result["accounting"]["current_study"]["spent_microusd"], 3200)
        for arm in cost["by_arm"]:
            self.assertEqual(arm["summary"]["operation_count"], 16)
            self.assertEqual(arm["summary"]["spent_microusd"], 800)
        stages = {row["stage_role"]: row["summary"] for row in cost["by_stage"]}
        self.assertEqual(
            {key: row["operation_count"] for key, row in stages.items()},
            {"generation": 32, "grouping": 16, "quality": 16, "summary": 0},
        )
        self.assertEqual(
            {key: row["spent_microusd"] for key, row in stages.items()},
            {"generation": 1600, "grouping": 800, "quality": 800, "summary": 0},
        )
        schedule = {cell["cell_id"]: cell for cell in reader.fixture.study.schedule()}
        for row in rows:
            cell = schedule[row["cell_id"]]
            self.assertEqual(row["arm_id"], cell["arm_id"])
            self.assertEqual(row["arm_index"], cell["arm_index"])
            self.assertEqual(row["generation_repeat"], cell["generation_repeat"])
            if row["stage_role"] == "generation":
                self.assertIsNone(row["judge_occasion"])
                self.assertEqual(row["stage_index"], 0)
            else:
                self.assertIn(row["judge_occasion"], (0, 1))
                self.assertEqual(
                    row["stage_index"], {"grouping": 1, "quality": 2}[row["stage_role"]]
                )
            self.assertEqual(row["causal_fallback"], "unknown")
            self.assertEqual(row["row_attribution"], "unknown")
        self.assertEqual(
            sum(row["summary"]["spent_microusd"] for row in cost["by_arm_stage"]), 3200
        )
        self.assertNotIn(gateway_fixtures.KEY, json.dumps(result))

    def test_old_partial_coverage_stays_frozen_while_current_costs_include_recovery(self):
        reader = self.study_fixture()
        fixture = reader.fixture
        fixture.prepare()
        run_evaluation = native_evaluation.run_evaluation

        def stopped_judging(*args, **kwargs):
            fixture.fixture.fail_native_once = True
            return run_evaluation(*args, **kwargs)

        with patch.object(native_evaluation, "run_evaluation", side_effect=stopped_judging):
            stopped = fixture.run_study()
        self.assertEqual((stopped["cell_index"], stopped["occasion_index"]), (0, 1))
        self.assertEqual(fixture.fixture.physical_sends, 7)
        observation = fixture.directory / stopped["observation"]
        original = observation.read_bytes()
        early = reader.read(observation=observation)
        self.assertEqual(early["registered"]["accounting"]["current_study"]["operation_count"], 7)
        self.assertEqual(early["analysis"]["coverage"]["observed"], 2)
        self.assertEqual(fixture.run_study()["status"], "complete")
        self.assertEqual(fixture.fixture.physical_sends, 64)
        older = reader.read(observation=observation)
        self.assertEqual(observation.read_bytes(), original)
        self.assertEqual(older["analysis"]["coverage"], early["analysis"]["coverage"])
        self.assertIsNone(older["analysis"]["mean_contrasts"])
        self.assertEqual(older["registered"]["accounting"]["current_study"]["operation_count"], 64)
        self.assertEqual(older["registered"]["accounting"]["current_study"]["spent_microusd"], 704)
        self.assertEqual(older["accounting"]["historical_observation"]["operation_count"], 7)

    def test_unknown_public_reader_retains_current_hold_and_missing_response_usage(self):
        reader = self.study_fixture()
        fixture = reader.fixture
        fixture.prepare()
        fixture.fixture.timeout_native_once = True
        stopped = fixture.run_study()
        self.assertEqual(stopped["reason"], "unknown")
        self.assertEqual(fixture.fixture.physical_sends, 5)
        result = reader.read(observation=fixture.directory / stopped["observation"])
        self.assertIsNone(result["analysis"]["mean_contrasts"])
        cost = result["registered"]["accounting"]
        summary = cost["current_study"]
        self.assertEqual(summary["operation_count"], 5)
        self.assertEqual(summary["spent_microusd"], 44)
        self.assertEqual(summary["reserved_microusd"], 300)
        self.assertEqual(summary["committed_microusd"], 344)
        self.assertEqual(summary["tokens"]["known_operations"], 4)
        self.assertEqual(summary["tokens"]["unknown_operations"], 1)
        self.assertIsNone(summary["tokens"]["input_tokens"])
        missing = [row for row in cost["operations"] if row["status"] == "unknown"]
        self.assertEqual(len(missing), 1)
        row = missing[0]
        self.assertEqual(
            (row["stage_role"], row["stage_index"], row["judge_occasion"]), ("grouping", 1, 0)
        )
        self.assertEqual(row["evidence_source"], "missing")
        self.assertIsNone(row["attempt"])
        self.assertIsNone(row["physical_retry"])
        self.assertIsNone(row["usage"])


if __name__ == "__main__":
    unittest.main()
