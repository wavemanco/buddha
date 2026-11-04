"""Tagged keyed reviews through real Gateway accounting and synthetic HTTPS."""

import copy
import hashlib
import hmac
import json
import os
import unittest
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import test_gateway as fixtures
import test_source_search as search_fixtures

from buddha import gateway
from buddha.releases import Release, ReleaseError, _json, prepare_selection

CONTEXT = "a" * 64


def fingerprint(provider, key=fixtures.KEY, context=CONTEXT):
    message = b"buddha.account-review.v2\0" + provider.encode() + b"\0" + context.encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


def review(provider="openai", *, context=CONTEXT):
    return {
        "format": "buddha.account-review.v2",
        "checked_on": datetime.now(UTC).date().isoformat(),
        "account_scope": "Synthetic standard/default account; no real model access",
        "credential_context": context,
        "credential_fingerprints": {provider: fingerprint(provider, context=context)},
    }


class KeyedReviewTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.GatewayTests("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def owner(self, provider="openai", *, record=None):
        f = self.f
        if provider == "anthropic":
            f.spec = replace(f.spec, provider=provider, model="synthetic-claude")
            f.profiles["profiles"]["primary"].update(
                spec=asdict(f.spec),
                response_models=["synthetic-claude"],
                request_tiers=["standard_only"],
                response_tiers=["", "standard"],
            )
            f.write("host", "profiles/openai.json", json.dumps(f.profiles))
            capability = "anthropic.messages.v1"
            release = copy.deepcopy(f.release_record)
            release["requires"] = [capability]
            f.selection = prepare_selection(
                Release.from_record(release),
                f.roots,
                capabilities={capability: "profiles/openai.json"},
            )
            body = _json(
                {
                    "model": "synthetic-claude",
                    "max_tokens": 100,
                    "service_tier": "standard_only",
                    "messages": [{"role": "user", "content": "literal"}],
                }
            )
        else:
            capability, body = fixtures.CAPABILITY, f.body
        directory = f.prepare(
            "keyed-" + provider, review=review(provider) if record is None else record
        )
        call = gateway.GatewayCall(capability, "primary", "keyed-synthetic-call", 0, body)
        return f.gateway(directory=directory), call

    def connection(self, provider):
        if provider == "openai":
            return self.f.connection()
        response = Mock(status=200)
        response.read.return_value = _json(
            {
                "model": "synthetic-claude",
                "service_tier": "standard",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "synthetic literal reply"}],
                "usage": {"input_tokens": 5, "output_tokens": 3},
            }
        )
        response.getheaders.return_value = [("request-id", "synthetic-keyed-anthropic")]
        return self.f.connection(response)

    def test_tagged_review_validates_without_reading_a_key(self):
        value = review()
        with patch("os.environ.get", side_effect=AssertionError("review parser read a key")):
            self.assertEqual(gateway._review(value, fresh=True), value)

    def test_fingerprints_use_existing_keys_and_separate_context_and_provider(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": fixtures.KEY, "ANTHROPIC_API_KEY": fixtures.KEY},
            clear=True,
        ):
            result = gateway.credential_fingerprints(["openai", "anthropic"], context=CONTEXT)
            self.assertEqual(result, {name: fingerprint(name) for name in ("openai", "anthropic")})
            again = gateway.credential_fingerprints(["openai"], context="b" * 64)
        self.assertNotEqual(result["openai"], result["anthropic"])
        self.assertNotEqual(result["openai"], again["openai"])
        self.assertNotEqual(result["openai"], hashlib.sha256(fixtures.KEY.encode()).hexdigest())
        self.assertNotIn(fixtures.KEY, json.dumps(result))

    def test_invalid_provider_or_context_refuses_before_reading_credentials(self):
        with patch("os.environ.get", side_effect=AssertionError("invalid input read a key")):
            for providers, context in (
                ([], CONTEXT),
                (["openai", "openai"], CONTEXT),
                (["openai", "replay"], CONTEXT),
                (["OPENAI"], CONTEXT),
                ("openai", CONTEXT),
                (["openai"], "g" * 64),
                (["openai"], True),
            ):
                with self.subTest(providers=providers, context=context):
                    with self.assertRaises(gateway.GatewayError):
                        gateway.credential_fingerprints(providers, context=context)

    def test_invalid_or_missing_keys_never_leave_a_fingerprint(self):
        for value in (None, "", "contains space", "x" * 4097, "é"):
            with self.subTest(
                kind=type(value).__name__, length=None if value is None else len(value)
            ):
                environment = {} if value is None else {"OPENAI_API_KEY": value}
                with patch.dict(os.environ, environment, clear=True):
                    with self.assertRaises(gateway.GatewayError):
                        gateway.credential_fingerprints(["openai"], context=CONTEXT)

    def test_v2_rejects_mixed_unknown_and_incomplete_formats(self):
        changes = [
            {"format": "buddha.account-review.v3"},
            {"credential_context": "0" * 63},
            {"credential_fingerprints": {}},
            {"credential_fingerprints": {"replay": "0" * 64}},
            {"credential_fingerprints": {"openai": "g" * 64}},
            {"credential_sha256": {"openai": "0" * 64}},
            {"algorithm": "sha256"},
        ]
        for changed in changes:
            with self.subTest(changed=changed):
                with self.assertRaises(ReleaseError):
                    gateway._review(review() | changed)
        for name in review():
            value = review()
            del value[name]
            with self.subTest(missing=name), self.assertRaises(ReleaseError):
                gateway._review(value)

    def test_v2_freshness_matches_original_review_rule(self):
        value = review()
        value["checked_on"] = (datetime.now(UTC).date() - timedelta(days=9)).isoformat()
        self.assertEqual(gateway._review(value), value)
        with self.assertRaises(ReleaseError):
            gateway._review(value, fresh=True)

    def test_format_requires_literal_version_text(self):
        class Version(str):
            pass

        value = review() | {"format": Version("buddha.account-review.v2")}
        with self.assertRaises(ReleaseError):
            gateway._review(value)

    def test_both_providers_dispatch_once_and_replay_keylessly_from_original_owner(self):
        for provider in ("openai", "anthropic"):
            with self.subTest(provider=provider):
                actor, call = self.owner(provider)
                connection = self.connection(provider)
                environment = {
                    "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY": fixtures.KEY
                }
                with (
                    patch.dict(os.environ, environment, clear=True),
                    patch("http.client.HTTPSConnection", return_value=connection),
                ):
                    first = actor.execute(call)
                self.assertEqual(connection.request.call_count, 1)
                totals = actor.ledger.totals()
                self.assertEqual(totals["operation_count"], 1)
                self.assertEqual(totals["reserved_microusd"], 0)
                keyless = self.f.gateway(directory=actor.directory, live=False)
                with (
                    patch.dict(os.environ, {}, clear=True),
                    patch("os.environ.get", side_effect=AssertionError("replay read a key")),
                    patch("http.client.HTTPSConnection", side_effect=AssertionError("replay sent")),
                ):
                    self.assertEqual(keyless.execute(call), first)
                self.assertEqual(actor.ledger.totals(), totals)
                for path in actor.directory.rglob("*"):
                    if path.is_file():
                        raw = path.read_bytes()
                        self.assertNotIn(fixtures.KEY.encode(), raw)
                        self.assertNotIn(
                            hashlib.sha256(fixtures.KEY.encode()).hexdigest().encode(), raw
                        )

    def test_wrong_key_keeps_unsent_original_reservation_and_correct_key_recovers(self):
        actor, call = self.owner()
        connection = self.connection("openai")
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-wrong-key"}, clear=True),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            with self.assertRaises(gateway.GatewayError):
                actor.execute(call)
        connection.request.assert_not_called()
        operation = actor.ledger.get(actor.operation_id(call))
        self.assertEqual(operation.status, "reserved")
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            actor.execute(call)
        self.assertEqual(actor.ledger.totals()["operation_count"], 1)
        self.assertEqual(connection.request.call_count, 1)

    def test_wrong_context_or_plain_sha_cannot_downgrade_the_keyed_binding(self):
        for i, changed in enumerate(
            (
                {"credential_context": "b" * 64},
                {
                    "credential_fingerprints": {
                        "openai": hashlib.sha256(fixtures.KEY.encode()).hexdigest()
                    }
                },
            )
        ):
            record = review() | changed
            directory = self.f.prepare("wrong-keyed-" + str(i), review=record)
            actor = self.f.gateway(directory=directory)
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
                patch(
                    "http.client.HTTPSConnection", side_effect=AssertionError("wrong binding sent")
                ),
            ):
                with self.assertRaises(gateway.GatewayError):
                    actor.execute(self.f.call)
            self.assertEqual(actor.ledger.get(actor.operation_id(self.f.call)).status, "reserved")

    def test_source_search_carries_keyed_review_through_descendants_native_evidence_and_replay(
        self,
    ):
        search = search_fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(search.doCleanups)
        search.proposals = [search_fixtures.REPAIRED]
        binding = review()
        search.prepare(review=binding)
        result = search.run_search()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["decisions"][0]["status"], "admitted")
        summary = search.authority.summary()
        self.assertGreater(search.engine.physical_sends, 0)
        self.assertEqual(summary["reserved_microusd"], 0)
        self.assertFalse(any(row["active"] for row in summary["runs"]))
        for owner in summary["runs"]:
            manifest = json.loads(
                (search.directory / owner["directory"] / "manifest.json").read_bytes()
            )
            self.assertEqual(manifest["review"], binding)
        self.assertEqual(search.inspect(), result)
        sends = search.engine.physical_sends
        with patch("os.environ.get", side_effect=AssertionError("completed search read a key")):
            self.assertEqual(search.run_search(paid=False), result)
        self.assertEqual(search.engine.physical_sends, sends)
        self.assertEqual(search.authority.summary(), summary)


if __name__ == "__main__":
    unittest.main()
