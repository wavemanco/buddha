"""Captured official judge bodies cross the current funded session unchanged."""

import base64
import hashlib
import json
import unittest
from contextlib import nullcontext
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import test_gateway as gateway_fixture
import test_native_run as native_fixture

from buddha.gateway import _request_fields
from buddha.reference import judge_body
from buddha.releases import Release, prepare_selection


class OfficialJudgeWireTests(unittest.TestCase):
    def _send_judge(self, kind, *, fallback=False, bad_settings=None):
        captured = json.loads((Path(__file__).parent / "fixtures/native_judges.json").read_bytes())[
            "captured_bodies"
        ][kind == "Score"]
        provider = captured["provider"]
        expected = captured["body"]
        if fallback:
            expected = expected | {"model": "claude-sonnet-5"}
        body = judge_body(kind, expected["messages"][-1]["content"], fallback=fallback)
        self.assertEqual(body, expected)
        raw = gateway_fixture.encoded(body)
        model = body["model"]
        capability = provider + (".chat-completions.v1" if provider == "openai" else ".messages.v1")

        case = native_fixture.NativeSessionTests("runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        fixture = case.fixture
        fixture.spec = replace(
            fixture.spec,
            provider=provider,
            model=model,
            max_output_tokens=128000 if provider == "openai" else 16000,
            input_microusd_per_million=1,
            output_microusd_per_million=1,
        )
        profile = fixture.profiles["profiles"]["primary"]
        profile.update(
            spec=asdict(fixture.spec),
            response_models=[model],
            headers={"user-agent": ["synthetic-host-session/1.0"]},
            account_headers={},
            request_settings={
                "required": {
                    key: value
                    for key, value in body.items()
                    if key not in {"model", "messages", "system"}
                },
                "forbidden": sorted(_request_fields(provider) - set(body)),
            },
        )
        fixture.profiles["format"] = "buddha.gateway-profiles.v3"
        fixture.write("host", "profiles/openai.json", json.dumps(fixture.profiles))
        fixture.release_record["requires"] = [capability]
        release = Release.from_record(fixture.release_record)
        case.worker["release_sha256"] = release.fingerprint()
        case.record["profiles"] = {provider: {model: "primary"}}
        case.descriptor.write_text(json.dumps(case.record), encoding="utf-8")
        fixture.selection = prepare_selection(
            release, fixture.roots, capabilities={capability: "profiles/openai.json"}
        )
        fixture.review["credential_sha256"] = {
            provider: hashlib.sha256(gateway_fixture.KEY.encode()).hexdigest()
        }
        case.directory = fixture.prepare(
            "official-judge", input_files=[case.descriptor, case.answer_file, *case.host_sources]
        )
        case.gateway = fixture.gateway(directory=case.directory)
        session = case.session()
        case.ready(session)
        if bad_settings is not None:
            raw = gateway_fixture.encoded(body | bad_settings)
        frame = case.request(body=raw)
        frame["request"].update(
            provider=provider,
            url="https://api." + provider + ".com" + captured["path"],
        )
        usage = (
            {"prompt_tokens": 5, "completion_tokens": 3}
            if provider == "openai"
            else {"input_tokens": 5, "output_tokens": 3}
        )
        header = "x-request-id" if provider == "openai" else "request-id"
        connection = fixture.connection(
            fixture.response(model=model, usage=usage, headers=[(header, "offline-judge")])
        )
        environment_key = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        with (
            patch.dict("os.environ", {environment_key: gateway_fixture.KEY}, clear=True),
            patch("http.client.HTTPSConnection", return_value=connection) as https,
            patch("buddha.gateway._credential", side_effect=AssertionError("key access"))
            if bad_settings is not None
            else nullcontext(),
        ):
            result = session.handle(frame)
        if bad_settings is not None:
            self.assertEqual((result["type"], result["reason"]), ("stop", "protocol"))
            https.assert_not_called()
            self.assertEqual(session.gateway.ledger.totals()["operation_count"], 0)
            return
        self.assertEqual(result["type"], "response")
        https.assert_called_once_with("api." + provider + ".com", timeout=2)
        connection.request.assert_called_once()
        self.assertEqual(connection.request.call_args.args, ("POST", captured["path"]))
        self.assertEqual(connection.request.call_args.kwargs["body"], raw)
        self.assertEqual(json.loads(connection.request.call_args.kwargs["body"]), expected)
        ledger = fixture.authority.for_run(case.directory)
        self.assertEqual(ledger.totals()["operation_count"], 1)
        self.assertEqual(ledger.totals()["reserved_microusd"], 0)
        manifest = json.loads((case.directory / "manifest.json").read_bytes())
        self.assertEqual(
            manifest["profiles"][capability]["profiles"]["primary"]["spec"]["model"], model
        )
        self.assertEqual(base64.b64decode(frame["request"]["body_base64"]), raw)
        return json.loads(connection.request.call_args.kwargs["body"])

    def test_luna_partition_omits_reasoning_token_and_temperature_overrides_at_https(self):
        body = self._send_judge("Partition")
        self.assertEqual(body["model"], "gpt-5.6-luna")
        self.assertEqual(set(body), {"model", "messages", "response_format", "stream"})
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertIs(body["stream"], False)

    def test_opus_utility_keeps_high_adaptive_effort_and_16000_tokens_at_https(self):
        body = self._send_judge("Score")
        self.assertEqual(body["model"], "claude-opus-5")
        self.assertEqual(body["max_tokens"], 16000)
        self.assertEqual(body["thinking"], {"type": "adaptive"})
        self.assertEqual(body["output_config"]["effort"], "high")
        self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
        self.assertNotIn("temperature", body)

    def test_sonnet_refusal_fallback_changes_only_the_model_at_https(self):
        body = self._send_judge("Score", fallback=True)
        self.assertEqual(body["model"], "claude-sonnet-5")
        self.assertEqual(body, judge_body("Score", "one full response") | {"model": body["model"]})

    def test_luna_judge_overrides_stop_before_key_access_or_reservation(self):
        for settings in (
            {"reasoning_effort": "low"},
            {"reasoning_effort": None},
            {"max_completion_tokens": 4096},
            {"temperature": 0},
        ):
            with self.subTest(settings=settings):
                self._send_judge("Partition", bad_settings=settings)

    def test_utility_cannot_inherit_the_generators_low_effort_or_allowance(self):
        for settings in (
            {"output_config": {"effort": "low"}},
            {"max_tokens": 4096},
            {"thinking": {"type": "disabled"}},
        ):
            with self.subTest(settings=settings):
                self._send_judge("Score", bad_settings=settings)


if __name__ == "__main__":
    unittest.main()
