"""Prospective request settings reach real accounting/HTTP without real providers."""

import base64
import copy
import hashlib
import json
import os
import unittest
from dataclasses import asdict, replace
from unittest.mock import patch

import test_candidate_run as candidate_fixtures
import test_gateway as fixtures

from agents import frozen_seed
from buddha.answers import TaskSet
from buddha.gateway import GatewayError, _profile_file
from buddha.releases import Release, ReleaseError, _json, prepare_selection


class GatewayRequestSettingsTests(unittest.TestCase):
    def prepare(self, provider="openai", model="reasoner-a"):
        h = candidate_fixtures.CandidateSessionTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        f = h.fixture
        capability = (
            "openai.chat-completions.v1" if provider == "openai" else "anthropic.messages.v1"
        )
        cap = "max_completion_tokens" if provider == "openai" else "max_tokens"
        required = (
            {cap: 4096, "reasoning_effort": "low"}
            if provider == "openai"
            else {cap: 4096, "thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}
        )
        f.spec = replace(f.spec, provider=provider, model=model, max_output_tokens=4096)
        profile = copy.deepcopy(f.profiles["profiles"]["primary"])
        profile.update(
            spec=asdict(f.spec),
            response_models=[model],
            request_tiers=["default" if provider == "openai" else "standard_only"],
            response_tiers=["default" if provider == "openai" else "standard"],
            allow_omitted_tier=False,
            headers={},
            account_headers={},
            request_settings={"required": required, "forbidden": ["temperature", "top_p"]},
        )
        f.profiles = {"format": "buddha.gateway-profiles.v3", "profiles": {"primary": profile}}
        f.write("host", "profiles/openai.json", json.dumps(f.profiles))
        f.review["credential_sha256"] = {
            provider: hashlib.sha256(fixtures.KEY.encode()).hexdigest()
        }
        f.release_record["requires"] = [capability]
        h.release = Release.from_record(f.release_record)
        h.tasks = TaskSet.from_dataset(
            h.release, (f.roots["official"] / "data/tasks.jsonl").read_bytes()
        ).select(["a"])
        h.task_path.write_bytes(h.tasks.to_bytes())
        h.record["config"].update(provider=provider, model=model, max_output_tokens=4096)
        h.record["profile"]["capability"] = capability
        h.descriptor.write_bytes(_json(h.record))
        f.selection = prepare_selection(
            h.release,
            f.roots,
            capabilities={capability: "profiles/openai.json"},
        )
        h.directory = f.prepare("reasoning-contract", input_files=h.bound)
        h.gateway = f.gateway(directory=h.directory)
        h.output = f.root / "reasoning-output"
        # Only the checked-in trusted seed is used. No model-authored source runs.
        body = frozen_seed.request(h.record["config"], h.tasks.tasks[0].to_record())
        return h, body

    @staticmethod
    def frame(h, body):
        return {
            "type": "request",
            "sequence": 0,
            "provider": h.record["config"]["provider"],
            "body_base64": base64.b64encode(body).decode(),
        }

    @staticmethod
    def connection(h):
        f = h.fixture
        model = h.record["config"]["model"]
        response = f.response(model=model)
        if h.record["config"]["provider"] == "anthropic":
            response.read.return_value = _json(
                {
                    "model": model,
                    "usage": {"input_tokens": 5, "output_tokens": 3, "service_tier": "standard"},
                    "content": [{"type": "text", "text": "synthetic answer"}],
                }
            )
            response.getheaders.return_value = [("request-id", "req-anthropic-synthetic")]
        return f.connection(response)

    def test_configurable_reasoning_models_keep_low_effort_through_actual_http_and_replay(self):
        for provider in ("openai", "anthropic"):
            for model in ("reasoner-a", "reasoner-b"):
                with self.subTest(provider=provider, model=model):
                    h, raw = self.prepare(provider, model)
                    session = h.session()
                    session.handle(h.ready())
                    connection = self.connection(h)
                    env = {
                        "OPENAI_API_KEY"
                        if provider == "openai"
                        else "ANTHROPIC_API_KEY": fixtures.KEY
                    }
                    with (
                        patch.dict(os.environ, env, clear=True),
                        patch("http.client.HTTPSConnection", return_value=connection),
                        patch.object(h.gateway, "execute", wraps=h.gateway.execute) as execute,
                    ):
                        reply = session.handle(self.frame(h, raw))
                    self.assertEqual(reply["type"], "response")
                    call = execute.call_args.args[0]
                    self.assertEqual(connection.request.call_args.kwargs["body"], raw)
                    self.assertEqual(call.body, raw)
                    sent = json.loads(raw)
                    self.assertEqual(sent["model"], model)
                    self.assertNotIn("temperature", sent)
                    self.assertNotIn("top_p", sent)
                    if provider == "openai":
                        self.assertEqual(sent["reasoning_effort"], "low")
                        self.assertEqual(sent["max_completion_tokens"], 4096)
                    else:
                        self.assertEqual(sent["output_config"], {"effort": "low"})
                        self.assertEqual(sent["thinking"], {"type": "adaptive"})
                        self.assertEqual(sent["max_tokens"], 4096)
                    connection.request.assert_called_once()
                    operation = h.gateway.ledger.get(h.gateway.operation_id(call))
                    self.assertEqual(operation.status, "completed")
                    self.assertEqual(
                        base64.b64decode(operation.response["request"]["body_base64"]), raw
                    )
                    with (
                        patch.dict(os.environ, {}, clear=True),
                        patch("http.client.HTTPSConnection") as no_connection,
                    ):
                        self.assertEqual(h.gateway.execute(call).to_record(), reply["envelope"])
                    no_connection.assert_not_called()
                    self.assertEqual(h.gateway.ledger.totals()["operation_count"], 1)

    def test_missing_high_sampling_and_smaller_cap_stop_before_keys_or_reservation(self):
        for provider in ("openai", "anthropic"):
            h, raw = self.prepare(provider)
            original = json.loads(raw)
            effort = "reasoning_effort" if provider == "openai" else "output_config"
            cap = "max_completion_tokens" if provider == "openai" else "max_tokens"
            changes = [
                {effort: "high" if provider == "openai" else {"effort": "high"}},
                {"temperature": 1},
                {"top_p": 1},
                {cap: 2048},
            ]
            absent = dict(original)
            del absent[effort]
            bodies = [absent, *(original | change for change in changes)]
            for index, body in enumerate(bodies):
                with self.subTest(provider=provider, index=index):
                    session = h.session(output=h.fixture.root / ("invalid-" + str(index)))
                    session.handle(h.ready())
                    with (
                        patch(
                            "buddha.gateway._credential", side_effect=AssertionError("key access")
                        ),
                        patch("http.client.HTTPSConnection") as connection,
                    ):
                        reply = session.handle(self.frame(h, _json(body)))
                    self.assertEqual((reply["type"], reply["reason"]), ("stop", "protocol"))
                    connection.assert_not_called()
                    self.assertEqual(h.gateway.ledger.totals()["operation_count"], 0)
            for index, body in enumerate((original | {"model": "other"}, original | {cap: 4097})):
                session = h.session(output=h.fixture.root / ("invalid-host-" + str(index)))
                session.handle(h.ready())
                with (
                    patch.object(
                        h.gateway, "execute", side_effect=AssertionError("gateway reached")
                    ),
                    self.assertRaises(h.Error),
                ):
                    session.handle(self.frame(h, _json(body)))
            self.assertEqual(h.gateway.ledger.totals()["operation_count"], 0)

    def test_settings_reject_malformed_unknown_overlapping_and_nonfinite_contracts(self):
        h, _ = self.prepare()
        original = h.fixture.profiles
        invalid = [
            None,
            {},
            {"required": {}, "forbidden": [], "extra": True},
            {"required": [], "forbidden": []},
            {"required": {"unsupported": 1}, "forbidden": []},
            {"required": {"thinking": {}}, "forbidden": []},
            {"required": {"model": "contradictory-model"}, "forbidden": []},
            {"required": {"max_tokens": 4096, "max_completion_tokens": 4096}, "forbidden": []},
            {"required": {"reasoning_effort": "low"}, "forbidden": ["reasoning_effort"]},
            {"required": {}, "forbidden": "temperature"},
            {"required": {}, "forbidden": ["temperature", "temperature"]},
            {"required": {}, "forbidden": [True]},
            {"required": {}, "forbidden": ["unknown"]},
            {"required": {"temperature": float("nan")}, "forbidden": []},
        ]
        for settings in invalid:
            profile = copy.deepcopy(original)
            profile["profiles"]["primary"]["request_settings"] = settings
            with self.subTest(settings=settings), self.assertRaises(ReleaseError):
                _profile_file(profile)
        for version in ("v1", "v2"):
            profile = copy.deepcopy(original)
            profile["format"] = "buddha.gateway-profiles." + version
            if version == "v1":
                del profile["profiles"]["primary"]["headers"]
                del profile["profiles"]["primary"]["account_headers"]
            with self.subTest(version=version), self.assertRaises(ReleaseError):
                _profile_file(profile)
            del profile["profiles"]["primary"]["request_settings"]
            self.assertEqual(_profile_file(profile), profile)
        profile = copy.deepcopy(original)
        profile["profiles"]["primary"]["request_settings"] = {"required": {}, "forbidden": []}
        self.assertEqual(_profile_file(profile), profile)

    def test_literal_equality_distinguishes_boolean_integer_and_whole_nested_values(self):
        from buddha.gateway import _request_spec

        h, raw = self.prepare("anthropic")
        profile = copy.deepcopy(h.fixture.profiles["profiles"]["primary"])
        profile["request_settings"] = {"required": {"max_tokens": True}, "forbidden": []}
        call = fixtures.GatewayCall(
            "anthropic.messages.v1",
            "primary",
            "synthetic-equality",
            0,
            _json(json.loads(raw) | {"max_tokens": 1}),
        )
        with self.assertRaises(GatewayError):
            _request_spec(call, profile)
        profile["request_settings"] = {
            "required": {"output_config": {"effort": "low"}},
            "forbidden": [],
        }
        call = replace(
            call, body=_json(json.loads(raw) | {"output_config": {"effort": "low", "extra": True}})
        )
        with self.assertRaises(GatewayError):
            _request_spec(call, profile)

    def test_required_null_does_not_accept_omission_and_valid_model_constraint_is_allowed(self):
        from buddha.gateway import _request_spec

        h, raw = self.prepare()
        profile = copy.deepcopy(h.fixture.profiles["profiles"]["primary"])
        profile["request_settings"] = {
            "required": {"model": h.fixture.spec.model, "seed": None},
            "forbidden": [],
        }
        file = copy.deepcopy(h.fixture.profiles)
        file["profiles"]["primary"] = profile
        self.assertEqual(_profile_file(file), file)
        call = fixtures.GatewayCall(
            "openai.chat-completions.v1", "primary", "synthetic-null", 0, raw
        )
        with self.assertRaises(GatewayError):
            _request_spec(call, profile)
        self.assertEqual(
            _request_spec(replace(call, body=_json(json.loads(raw) | {"seed": None})), profile),
            h.fixture.spec,
        )


if __name__ == "__main__":
    unittest.main()
