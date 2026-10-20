"""Funded version-neutral requests through real attached accounting; no network."""

import hashlib
import http.client
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from buddha.authorization import Authorization, runtime_fingerprint
from buddha.benchmark import _canonical
from buddha.evaluation import ValidationError
from buddha.gateway import (
    Gateway,
    GatewayCall,
    RawHTTPTransport,
    execution_identity,
    prepare_gateway,
)
from buddha.ledger import BudgetExceeded, Ledger, OperationConflict
from buddha.provider import BoundBreach, ModelSpec, ProviderUncertain, Reply
from buddha.releases import Release, inventory, prepare_selection
from buddha.wire import RawEnvelope

KEY = "offline-test-key-never-a-real-credential"
CAPABILITY = "openai.chat-completions.v1"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class GatewayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.roots = {
            name: self.root / name
            for name in ("official", "environment", "runner", "host", "agent")
        }
        for name, directory in self.roots.items():
            directory.mkdir()
            (directory / "identity.txt").write_text(name, encoding="utf-8")
        self.write("official", "src/evaluate.py", "raise RuntimeError('never execute')\n")
        self.write("official", "uv.lock", "frozen official dependencies")
        self.write("official", "data/tasks.jsonl", '{"id":"a","prompt":"say one digit"}\n')
        self.write("environment", "nested/dependency.py", "VALUE = 'locked'\n")
        self.spec = ModelSpec(
            provider="openai",
            model="test-model",
            input_token_ceiling=100,
            max_output_tokens=100,
            input_microusd_per_million=1_000_000,
            output_microusd_per_million=2_000_000,
            bounds_source="https://example.org/documented-synthetic-model-maximum",
        )
        self.profiles = {
            "format": "buddha.gateway-profiles.v1",
            "profiles": {
                "primary": {
                    "spec": asdict(self.spec),
                    "response_models": ["test-model"],
                    "request_tiers": ["auto", "default"],
                    "response_tiers": ["", "default"],
                    "allow_omitted_tier": True,
                }
            },
        }
        self.write("host", "profiles/openai.json", json.dumps(self.profiles))
        self.release_record = {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "fixture",
            "release": "first",
            "upstream": {"url": "https://example.org/official", "revision": "a" * 40},
            "source": inventory(self.roots["official"]),
            "dependency_lock": "uv.lock",
            "task": {
                "dataset": "data/tasks.jsonl",
                "id_field": "id",
                "prompt_field": "prompt",
                "answers_field": "generations",
                "count": 10,
            },
            "commands": [{"module": "src.evaluate", "argv": ["--eval-dir", "{artifacts}"]}],
            "artifacts": {
                "answers": "generations.jsonl",
                "results": ["results.jsonl"],
                "summary": "summary.json",
            },
            "requires": [CAPABILITY],
        }
        self.selection = prepare_selection(
            Release.from_record(self.release_record),
            self.roots,
            capabilities={CAPABILITY: "profiles/openai.json"},
        )
        self.input_file = self.root / "answers.jsonl"
        self.input_file.write_bytes(b'{"id":"a","generations":["poor answer"]}\n')
        self.review = {
            "checked_on": datetime.now(UTC).date().isoformat(),
            "credential_sha256": {"openai": hashlib.sha256(KEY.encode()).hexdigest()},
            "account_scope": "offline synthetic account review",
        }
        self.authority = Authorization.create(
            self.root / "authority.sqlite3",
            authorization_id="gateway-synthetic-scope",
            budget_microusd=10_000,
            max_calls=20,
            scope="offline synthetic gateway checks only",
        )
        self.directory = self.prepare("run")
        self.ledger = self.authority.for_run(self.directory)
        self.body = (
            b'{\n "model":"test-model", '
            b'"messages":[{"role":"user","content":"literal"}], "stream":false\n}'
        )
        self.call = GatewayCall(CAPABILITY, "primary", "task-a/partition", 0, self.body)

    def write(self, role, relative, value):
        destination = self.roots[role] / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(value, encoding="utf-8")

    def prepare(self, name, **changes):
        values = {
            "selection": self.selection,
            "roots": self.roots,
            "authorization": self.authority,
            "budget_microusd": 10_000,
            "max_calls": 20,
            "input_files": [self.input_file],
            "review": self.review,
            "run_id": name,
        }
        return prepare_gateway(self.root / name, **(values | changes))

    def gateway(self, *, live=True, directory=None):
        return Gateway(
            directory or self.directory,
            transport=RawHTTPTransport(allow_paid=live, timeout_seconds=2),
        )

    def response(self, *, status=200, headers=None, **changes):
        body = {
            "model": "test-model",
            "service_tier": "default",
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            "choices": [{"message": {"content": "{malformed assistant JSON"}}],
        } | changes
        response = Mock(status=status)
        response.read.return_value = encoded(body)
        response.getheaders.return_value = headers or [("x-request-id", "req-synthetic")]
        return response

    def connection(self, response=None):
        connection = Mock()
        connection.getresponse.return_value = response or self.response()
        return connection

    def operation(self, gateway, call=None):
        return self.ledger.get(gateway.operation_id(call or self.call))

    def envelope(self, operation):
        return RawEnvelope.from_record(operation.response["envelope"])

    def send(self, gateway=None, call=None, connection=None):
        gateway = gateway or self.gateway()
        connection = connection or self.connection()
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": KEY}, clear=True),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            return gateway.execute(call or self.call)

    def legacy_ledger(self):
        directory = self.root / "legacy-run"
        directory.mkdir()
        manifest = {
            "format": "buddha.policy-search.v1",
            "run_id": "legacy-run",
            "settings": {"budget_microusd": 10_000, "max_calls": 20},
        }
        digest = hashlib.sha256(_canonical(manifest)).hexdigest()
        (directory / "manifest.json").write_bytes(
            _canonical(manifest | {"record_sha256": digest}) + b"\n"
        )
        Ledger(
            directory / "operations.sqlite3",
            run_id="legacy-run",
            manifest_sha256=digest,
            budget_microusd=10_000,
            max_calls=20,
        )
        self.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())
        return self.authority.for_run(directory)

    def test_real_authority_and_actual_core_are_frozen_separately_from_host_profiles(self):
        manifest = json.loads((self.directory / "manifest.json").read_bytes())
        self.assertEqual(manifest["format"], "buddha.gateway-run.v1")
        self.assertEqual(len(execution_identity(self.directory)), 64)
        self.assertEqual(self.authority.summary()["operation_count"], 0)
        self.assertEqual(self.authority.summary()["runs"][0]["run_id"], "run")
        self.assertNotIn(KEY, json.dumps(manifest))
        with self.assertRaises(FrozenInstanceError):
            self.call.body = b"changed"

    def test_cap_omission_reserves_documented_maximum_and_wire_bytes_are_unchanged(self):
        gateway = self.gateway()
        connection = self.connection()
        envelope = self.send(gateway, connection=connection)
        operation = self.operation(gateway)
        self.assertEqual(operation.reserve_microusd, 300)
        self.assertEqual(operation.actual_microusd, 11)
        self.assertEqual(operation.status, "completed")
        self.assertEqual(envelope, self.envelope(operation))
        args, kwargs = connection.request.call_args
        self.assertEqual(args[:2], ("POST", "/v1/chat/completions"))
        self.assertEqual(kwargs.get("body", args[2] if len(args) > 2 else None), self.body)
        self.assertNotIn("max_tokens", self.body.decode())
        connection.request.assert_called_once()

    def test_bad_assistant_json_is_billed_without_benchmark_parsing(self):
        gateway = self.gateway()
        received = self.send(gateway)
        self.assertIn(b"{malformed assistant JSON", received.body)
        self.assertEqual(self.operation(gateway).actual_microusd, 11)
        self.assertEqual(self.authority.summary()["spent_microusd"], 11)

    def test_raw_receipt_is_durable_before_billing_extraction(self):
        import buddha.gateway as module

        gateway = self.gateway()
        original = module.extract_usage

        def inspect_received(envelope):
            operation = self.operation(gateway)
            self.assertEqual(operation.status, "unknown")
            self.assertEqual(self.envelope(operation), envelope)
            self.assertEqual(self.authority.summary()["reserved_microusd"], 300)
            return original(envelope)

        with patch.object(module, "extract_usage", side_effect=inspect_received) as extract:
            self.send(gateway)
        extract.assert_called_once()

    def test_cached_completed_reply_needs_no_key_live_permission_or_active_run(self):
        gateway = self.gateway()
        expected = self.send(gateway)
        self.authority.deactivate("run", "synthetic complete run")
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("http.client.HTTPSConnection") as connection,
        ):
            self.assertEqual(self.gateway(live=False).execute(self.call), expected)
        connection.assert_not_called()
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_selected_dependency_profile_and_input_drift_fail_before_reservation(self):
        candidates = [
            self.roots["environment"] / "nested/dependency.py",
            self.roots["host"] / "profiles/openai.json",
            self.input_file,
        ]
        for path in candidates:
            with self.subTest(path=path):
                gateway = self.gateway()
                before = path.read_bytes()
                path.write_bytes(before + b"changed")
                try:
                    with (
                        patch.dict("os.environ", {}, clear=True),
                        patch("http.client.HTTPSConnection") as connection,
                        self.assertRaises(ValidationError),
                    ):
                        gateway.execute(self.call)
                    connection.assert_not_called()
                    self.assertEqual(self.ledger.totals()["operation_count"], 0)
                finally:
                    path.write_bytes(before)

    def test_actual_executing_core_drift_is_rejected_before_reservation(self):
        import buddha.gateway as module

        gateway = self.gateway()
        original = module._core_sources()
        changed = dict(original)
        first = next(iter(changed))
        changed[first] = "f" * 64
        with (
            patch.object(module, "_core_sources", return_value=changed),
            patch.dict("os.environ", {}, clear=True),
            patch("http.client.HTTPSConnection") as connection,
            self.assertRaises(ValidationError),
        ):
            gateway.execute(self.call)
        connection.assert_not_called()
        self.assertEqual(self.ledger.totals()["operation_count"], 0)

    def test_credential_failure_leaves_reusable_reserved_unsent_attempt(self):
        gateway = self.gateway()
        operation_id = gateway.operation_id(self.call)
        for value in (None, KEY + "-different"):
            with self.subTest(credential_present=value is not None):
                values = {} if value is None else {"OPENAI_API_KEY": value}
                with (
                    patch.dict("os.environ", values, clear=True),
                    patch("http.client.HTTPSConnection") as connection,
                    self.assertRaises(ValidationError),
                ):
                    gateway.execute(self.call)
                connection.assert_not_called()
                operation = self.operation(gateway)
                self.assertEqual(operation.status, "reserved")
                self.assertEqual(operation.reserve_microusd, 300)
                self.assertIsNone(operation.response)
                self.assertEqual(operation.operation_id, operation_id)
                self.assertEqual(self.ledger.totals()["operation_count"], 1)
        self.send(gateway)
        self.assertEqual(self.operation(gateway).operation_id, operation_id)
        self.assertEqual(self.operation(gateway).status, "completed")
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_unknown_capability_profile_model_or_paid_feature_fails_unsent(self):
        changes = [
            {"capability": "new-unsupported.v1"},
            {"profile_id": "unreviewed"},
            {"body": encoded({"model": "unreviewed", "messages": []})},
            {"body": encoded({"model": "test-model", "messages": [], "n": 2})},
            {"body": encoded({"model": "test-model", "messages": [], "stream": True})},
        ]
        for values in changes:
            with self.subTest(changes=values):
                with (
                    patch.dict("os.environ", {}, clear=True),
                    patch("http.client.HTTPSConnection") as connection,
                    self.assertRaises(ValidationError),
                ):
                    self.gateway().execute(replace(self.call, **values))
                connection.assert_not_called()
                self.assertEqual(self.ledger.totals()["operation_count"], 0)

    def test_same_logical_attempt_conflicts_for_changed_body(self):
        gateway = self.gateway()
        self.send(gateway)
        changed = replace(self.call, body=self.body.replace(b"literal", b"changed"))
        with self.assertRaises(OperationConflict):
            gateway.execute(changed)
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_input_inventory_is_bounded_before_files_or_allocation_are_created(self):
        for inputs in (None, [], [self.input_file] * 1025, iter([self.input_file])):
            with self.subTest(inputs=type(inputs).__name__), self.assertRaises(ValidationError):
                self.prepare("invalid-input-list", input_files=inputs)
            self.assertFalse((self.root / "invalid-input-list").exists())

    def test_invalid_request_types_and_unicode_fail_before_reservation(self):
        base = json.loads(self.body)
        changes = [
            {"n": True},
            {"n": None},
            {"service_tier": {}},
            {"messages": [{"role": [], "content": "literal"}]},
            {"messages": [{"role": "user", "content": "\ud800"}]},
        ]
        gateway = self.gateway()
        for change in changes:
            call = replace(self.call, body=json.dumps(base | change).encode())
            with self.subTest(change=tuple(change)), self.assertRaises(ValidationError):
                gateway.execute(call)
        self.assertEqual(self.ledger.totals()["operation_count"], 0)

    def test_identical_bodies_with_different_attempts_or_slots_are_independent_calls(self):
        gateway = self.gateway()
        calls = [self.call, replace(self.call, attempt=1), replace(self.call, logical_id="other")]
        self.assertEqual(len({gateway.operation_id(call) for call in calls}), 3)
        for call in calls:
            self.send(gateway, call)
        self.assertEqual(self.authority.summary()["operation_count"], 3)
        self.assertEqual(self.authority.summary()["spent_microusd"], 33)

    def test_timeout_is_one_dispatch_unknown_and_stops_shared_authority(self):
        gateway = self.gateway()
        connection = self.connection()
        connection.getresponse.side_effect = TimeoutError("synthetic timeout")
        with self.assertRaises(ProviderUncertain):
            self.send(gateway, connection=connection)
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "unknown")
        self.assertEqual(operation.reserve_microusd, 300)
        connection.request.assert_called_once()
        with self.assertRaises(ValidationError):
            self.send(gateway, replace(self.call, logical_id="after-timeout"))
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_missing_usage_keeps_raw_reply_and_full_unknown_hold(self):
        gateway = self.gateway()
        response = self.response(usage={})
        with self.assertRaises(ProviderUncertain):
            self.send(gateway, connection=self.connection(response))
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "unknown")
        self.assertEqual(self.envelope(operation).body, response.read.return_value)
        self.assertEqual(self.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.authority.summary()["spent_microusd"], 0)

    def test_unexpected_response_model_keeps_raw_unknown_and_stops_shared_spending(self):
        self.assert_unexpected_billing_response(model="unreviewed-response-model")

    def test_unexpected_response_tier_keeps_raw_unknown_and_stops_shared_spending(self):
        self.assert_unexpected_billing_response(service_tier="unreviewed-response-tier")

    def assert_unexpected_billing_response(self, **changes):
        gateway = self.gateway()
        response = self.response(**changes)
        with self.assertRaises(ProviderUncertain):
            self.send(gateway, connection=self.connection(response))
        self.assertEqual(self.operation(gateway).status, "unknown")
        self.assertEqual(self.envelope(self.operation(gateway)).body, response.read.return_value)
        self.assertEqual(self.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.authority.summary()["spent_microusd"], 0)
        with self.assertRaises(BudgetExceeded):
            self.send(gateway, replace(self.call, logical_id="after-unreviewed-billing"))
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_expired_review_blocks_new_spend_before_keys_but_keeps_cached_replay(self):
        gateway = self.gateway()
        expected = self.send(gateway)
        with (
            patch("buddha.gateway.datetime") as clock,
            patch("os.environ.get", side_effect=AssertionError("credential lookup forbidden")),
            patch("http.client.HTTPSConnection") as connection,
        ):
            clock.now.return_value = datetime.now(UTC) + timedelta(days=9)
            self.assertEqual(gateway.execute(self.call), expected)
            with self.assertRaises(ValidationError):
                gateway.execute(replace(self.call, logical_id="after-review-expiry"))
        connection.assert_not_called()
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_consistent_local_profile_and_manifest_rewrite_cannot_replace_authority_owner(self):
        from buddha.gateway import _sha

        path = self.directory / "manifest.json"
        record = json.loads(path.read_bytes())
        self.profiles["profiles"]["primary"]["response_models"] = ["rewritten-response-model"]
        self.write("host", "profiles/openai.json", json.dumps(self.profiles))
        selection = prepare_selection(
            Release.from_record(self.release_record),
            self.roots,
            capabilities={CAPABILITY: "profiles/openai.json"},
        )
        record["selection"] = selection.to_record()
        record["selection_sha256"] = selection.fingerprint()
        record["profiles"][CAPABILITY] = self.profiles
        record["invocation"]["id"] = "consistently-rewritten-invocation"
        record["execution_sha256"] = _sha(
            {key: record[key] for key in ("selection_sha256", "core", "runtime", "invocation")}
        )
        record.pop("record_sha256")
        record["record_sha256"] = _sha(record)
        path.write_bytes(encoded(record))
        with (
            patch("os.environ.get", side_effect=AssertionError("credential lookup forbidden")),
            patch("http.client.HTTPSConnection") as connection,
            self.assertRaises(OperationConflict),
        ):
            self.gateway()
        connection.assert_not_called()
        self.assertEqual(self.authority.summary()["operation_count"], 0)

    def test_http_error_and_retry_headers_are_preserved_without_automatic_retry(self):
        gateway = self.gateway()
        response = self.response(
            status=429,
            headers=[
                ("x-request-id", "req-rate-limit"),
                ("retry-after", "12"),
                ("x-should-retry", "true"),
                ("set-cookie", "private-data-must-not-persist"),
            ],
        )
        connection = self.connection(response)
        with self.assertRaises(ProviderUncertain):
            self.send(gateway, connection=connection)
        envelope = self.envelope(self.operation(gateway))
        self.assertEqual(envelope.status, 429)
        self.assertIn(("retry-after", "12"), envelope.headers)
        self.assertNotIn("set-cookie", dict(envelope.headers))
        connection.request.assert_called_once()

    def test_known_cost_overrun_records_true_charge_before_stopping_every_run(self):
        gateway = self.gateway()
        response = self.response(usage={"prompt_tokens": 400, "completion_tokens": 3})
        with self.assertRaises(BudgetExceeded):
            self.send(gateway, connection=self.connection(response))
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "completed")
        self.assertEqual(operation.actual_microusd, 406)
        self.assertEqual(self.authority.summary()["spent_microusd"], 406)
        with self.assertRaises(ValidationError):
            self.send(gateway, replace(self.call, logical_id="after-overrun"))
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_unsent_connection_preparation_failure_can_reuse_reserved_identity(self):
        gateway = self.gateway()
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": KEY}, clear=True),
            patch("http.client.HTTPSConnection", side_effect=OSError("local unsent failure")),
            self.assertRaises(ValidationError),
        ):
            gateway.execute(self.call)
        first = self.operation(gateway)
        self.assertEqual(first.status, "reserved")
        self.send(gateway)
        self.assertEqual(self.operation(gateway).operation_id, first.operation_id)
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_two_runners_have_one_physical_dispatch_winner(self):
        started = threading.Event()
        release = threading.Event()
        first = self.gateway()
        second = self.gateway()
        connection = self.connection()

        def receive():
            started.set()
            if not release.wait(10):
                raise RuntimeError("synthetic test synchronization timeout")
            return self.response()

        connection.getresponse.side_effect = receive
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": KEY}, clear=True),
            patch("http.client.HTTPSConnection", return_value=connection),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            work = executor.submit(first.execute, self.call)
            try:
                self.assertTrue(started.wait(10))
                with self.assertRaises(ValidationError):
                    second.execute(self.call)
            finally:
                release.set()
            work.result(timeout=10)
        connection.request.assert_called_once()
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_keyboard_interrupt_during_usage_keeps_received_raw_evidence(self):
        gateway = self.gateway()
        with (
            patch("buddha.gateway.extract_usage", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.send(gateway)
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "unknown")
        self.assertEqual(self.envelope(operation).provider_request_id, "req-synthetic")
        self.assertEqual(self.authority.summary()["reserved_microusd"], 300)

    def test_interrupt_after_full_body_read_retains_received_bytes(self):
        gateway = self.gateway()
        response = self.response()
        response.getheaders.side_effect = KeyboardInterrupt("synthetic after full body read")
        with self.assertRaises(KeyboardInterrupt):
            self.send(gateway, connection=self.connection(response))
        response.read.assert_called_once()
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "unknown")
        envelope = self.envelope(operation)
        self.assertEqual(envelope.body, response.read.return_value)
        self.assertFalse(envelope.headers_complete)
        self.assertEqual(self.authority.summary()["reserved_microusd"], 300)

    def test_interrupted_secret_screen_still_filters_received_credentials(self):
        import buddha.gateway as module

        gateway = self.gateway()
        response = self.response(error={"message": KEY})
        original = module._contains_secret
        interrupted = False

        def interrupt_once(raw, key):
            nonlocal interrupted
            if raw == response.read.return_value and not interrupted:
                interrupted = True
                raise KeyboardInterrupt("synthetic during received-body screening")
            return original(raw, key)

        with (
            patch.object(module, "_contains_secret", side_effect=interrupt_once),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.send(gateway, connection=self.connection(response))
        self.assertTrue(interrupted)
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "unknown")
        envelope = self.envelope(operation)
        self.assertTrue(envelope.withheld)
        self.assertEqual(envelope.body, b"")
        self.assertEqual(
            envelope.received_sha256, hashlib.sha256(response.read.return_value).hexdigest()
        )
        self.assertEqual(self.authority.summary()["reserved_microusd"], 300)

    def test_incomplete_http_read_retains_partial_body_and_unknown_hold(self):
        gateway = self.gateway()
        response = self.response()
        partial = b'{"model":"test-model","usage":'
        response.read.side_effect = http.client.IncompleteRead(partial, 100)
        with self.assertRaises(ProviderUncertain):
            self.send(gateway, connection=self.connection(response))
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "unknown")
        envelope = self.envelope(operation)
        self.assertEqual(envelope.body, partial)
        self.assertTrue(envelope.truncated)
        self.assertEqual(envelope.received_sha256, hashlib.sha256(partial).hexdigest())
        self.assertEqual(self.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.authority.summary()["spent_microusd"], 0)

    def test_raw_serialization_interrupt_records_and_bills_before_reraising(self):
        gateway = self.gateway()
        response = self.response()
        original = RawEnvelope.to_record
        interrupted = False

        def interrupt_once(envelope):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt("synthetic raw receipt serialization interruption")
            return original(envelope)

        with (
            patch.object(RawEnvelope, "to_record", new=interrupt_once),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.send(gateway, connection=self.connection(response))
        self.assertTrue(interrupted)
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "completed")
        self.assertEqual(self.envelope(operation).body, response.read.return_value)
        self.assertEqual(operation.actual_microusd, 11)
        self.assertEqual(self.authority.summary()["reserved_microusd"], 0)
        self.assertEqual(self.authority.summary()["spent_microusd"], 11)

    def test_local_checkpoint_interruptions_before_and_after_commit_preserve_one_charge(self):
        for method in ("mark_unknown", "complete"):
            for after_commit in (False, True):
                with self.subTest(method=method, after_commit=after_commit):
                    gateway = self.gateway(directory=self.prepare(f"{method}-{after_commit}"))
                    original = getattr(gateway.ledger, method)
                    count = 0

                    def interrupt_once(*args, _original=original, _after=after_commit, **kwargs):
                        nonlocal count
                        count += 1
                        if count == 1:
                            if _after:
                                _original(*args, **kwargs)
                            raise KeyboardInterrupt("synthetic local checkpoint interruption")
                        return _original(*args, **kwargs)

                    with (
                        patch.object(gateway.ledger, method, side_effect=interrupt_once),
                        self.assertRaises(KeyboardInterrupt),
                    ):
                        self.send(gateway)
                    operation = gateway.ledger.get(gateway.operation_id(self.call))
                    self.assertEqual(operation.status, "completed")
                    self.assertEqual(operation.actual_microusd, 11)
                    self.assertEqual(self.envelope(operation).provider_request_id, "req-synthetic")
        self.assertEqual(self.authority.summary()["operation_count"], 4)
        self.assertEqual(self.authority.summary()["spent_microusd"], 44)

    def test_run_budget_and_call_caps_fail_before_credential_access(self):
        for name, changes in (
            ("dollar-cap", {"budget_microusd": 300}),
            ("call-cap", {"max_calls": 1}),
        ):
            with self.subTest(cap=name):
                gateway = self.gateway(directory=self.prepare(name, **changes))
                self.send(gateway)
                original = os.environ.get

                def reject_credential_access(key, *args, _get=original):
                    if key in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}:
                        self.fail("exhausted funding accessed a provider credential")
                    return _get(key, *args)

                with (
                    patch.object(os.environ, "get", side_effect=reject_credential_access),
                    patch("http.client.HTTPSConnection") as connection,
                    self.assertRaises(BudgetExceeded),
                ):
                    gateway.execute(replace(self.call, logical_id="after-exhausted-cap"))
                connection.assert_not_called()

    def test_legacy_hold_and_gateway_share_one_dollar_envelope(self):
        gateway = self.gateway()
        legacy = self.legacy_ledger()
        legacy.reserve("legacy-attempt", "a" * 64, 9900)
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("http.client.HTTPSConnection") as connection,
            self.assertRaises(BudgetExceeded),
        ):
            gateway.execute(self.call)
        connection.assert_not_called()
        self.assertEqual(self.ledger.totals()["operation_count"], 0)
        self.assertEqual(self.authority.summary()["reserved_microusd"], 9900)
        self.assertTrue(legacy.dispatch("legacy-attempt"))
        legacy.complete(
            "legacy-attempt",
            response=Reply("legacy", "model", "legacy-receipt", 1, 1, "stop").to_record(),
            actual_microusd=1,
            provider_request_id="legacy-receipt",
        )
        self.send(gateway)
        self.assertEqual(self.authority.summary()["operation_count"], 2)
        self.assertEqual(self.authority.summary()["spent_microusd"], 12)

    def test_legacy_and_gateway_share_the_last_call_slot(self):
        gateway = self.gateway()
        legacy = self.legacy_ledger()
        for index in range(19):
            legacy.reserve("legacy-attempt-" + str(index), "a" * 64, 0)
        self.send(gateway)
        self.assertEqual(self.authority.summary()["operation_count"], 20)
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("http.client.HTTPSConnection") as connection,
            self.assertRaises(BudgetExceeded),
        ):
            gateway.execute(replace(self.call, logical_id="after-shared-last-call"))
        connection.assert_not_called()
        self.assertEqual(self.authority.summary()["operation_count"], 20)
        with self.assertRaises(BudgetExceeded):
            legacy.reserve("legacy-after-shared-last-call", "b" * 64, 0)

    def test_invalid_selected_header_keeps_body_and_marks_incomplete_headers(self):
        gateway = self.gateway()
        response = self.response(headers=[("x-request-id", "x" * 1025)])
        with self.assertRaises(ProviderUncertain):
            self.send(gateway, connection=self.connection(response))
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "unknown")
        envelope = self.envelope(operation)
        self.assertEqual(envelope.body, response.read.return_value)
        self.assertFalse(envelope.headers_complete)
        self.assertEqual(self.authority.summary()["reserved_microusd"], 300)

    def test_dependency_drift_after_send_does_not_block_terminal_receipt(self):
        gateway = self.gateway()
        response = self.response()
        original = response.read.return_value
        path = self.roots["environment"] / "nested/dependency.py"

        def receive_then_drift(*args):
            path.write_text("CHANGED = 'after paid dispatch'\n", encoding="utf-8")
            return original

        response.read.side_effect = receive_then_drift
        envelope = self.send(gateway, connection=self.connection(response))
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "completed")
        self.assertEqual(envelope.body, original)
        self.assertEqual(self.envelope(operation).body, original)
        self.assertEqual(self.authority.summary()["spent_microusd"], 11)
        with self.assertRaises(ValidationError):
            self.send(gateway, replace(self.call, logical_id="after-source-drift"))
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_known_overrun_cached_replay_raises_without_key_or_another_send(self):
        gateway = self.gateway()
        response = self.response(usage={"prompt_tokens": 400, "completion_tokens": 3})
        with self.assertRaises(BudgetExceeded):
            self.send(gateway, connection=self.connection(response))
        self.authority.deactivate("run", "synthetic overrun closed")
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("http.client.HTTPSConnection") as connection,
            self.assertRaises(BoundBreach),
        ):
            self.gateway(live=False).execute(self.call)
        connection.assert_not_called()
        self.assertEqual(self.authority.summary()["operation_count"], 1)
        self.assertEqual(self.authority.summary()["spent_microusd"], 406)

    def test_token_bound_breach_below_reserve_retains_raw_unknown_and_stops_all_runs(self):
        gateway = self.gateway()
        other = self.gateway(directory=self.prepare("other-run"))
        response = self.response(usage={"prompt_tokens": 101, "completion_tokens": 0})
        with self.assertRaises(BoundBreach):
            self.send(gateway, connection=self.connection(response))
        operation = self.operation(gateway)
        self.assertEqual(operation.status, "unknown")
        self.assertEqual(self.envelope(operation).body, response.read.return_value)
        self.assertEqual(self.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.authority.summary()["spent_microusd"], 0)
        with self.assertRaises(ValidationError):
            self.send(other, replace(self.call, logical_id="other-run-after-bound-breach"))
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_other_configured_provider_key_is_never_sent_or_saved(self):
        other_key = "different-provider-offline-test-key"
        gateway = self.gateway()
        secret_call = replace(self.call, body=self.body.replace(b"literal", other_key.encode()))
        connection = self.connection()
        with (
            patch.dict(
                "os.environ", {"OPENAI_API_KEY": KEY, "ANTHROPIC_API_KEY": other_key}, clear=True
            ),
            patch("http.client.HTTPSConnection", return_value=connection),
            self.assertRaises(ValidationError),
        ):
            gateway.execute(secret_call)
        connection.request.assert_not_called()
        self.assertEqual(self.operation(gateway, secret_call).status, "reserved")
        self.assertIsNone(self.operation(gateway, secret_call).response)
        echo_call = replace(self.call, logical_id="other-provider-key-echo")
        response = self.response(error={"message": other_key})
        with (
            patch.dict(
                "os.environ", {"OPENAI_API_KEY": KEY, "ANTHROPIC_API_KEY": other_key}, clear=True
            ),
            patch("http.client.HTTPSConnection", return_value=self.connection(response)),
            self.assertRaises(ProviderUncertain),
        ):
            gateway.execute(echo_call)
        operation = self.operation(gateway, echo_call)
        self.assertEqual(operation.status, "unknown")
        envelope = self.envelope(operation)
        self.assertTrue(envelope.withheld)
        self.assertEqual(envelope.body, b"")
        self.assertEqual(
            envelope.received_sha256, hashlib.sha256(response.read.return_value).hexdigest()
        )

    def test_escaped_credentials_are_withheld_despite_malformed_envelope_or_header(self):
        quoted = json.dumps(KEY).replace(KEY[0], f"\\u{ord(KEY[0]):04x}", 1)
        cases = (
            ("trailing-data", ('{"echo":' + quoted + "} trailing malformed envelope").encode()),
            ("unclosed-object", ('{"echo":' + quoted).encode()),
            ("prefix-quote", ('"malformed prefix ' + quoted + " trailing").encode()),
            ("invalid-prefix-escape", ('"malformed\\q prefix ' + quoted + " trailing").encode()),
            ("request-id-header", None),
        )
        for index, (name, raw) in enumerate(cases):
            with self.subTest(envelope=name):
                authority = Authorization.create(
                    self.root / ("escaped-" + str(index) + ".sqlite3"),
                    authorization_id="escaped-" + str(index),
                    budget_microusd=10_000,
                    max_calls=20,
                    scope="offline independent escaped-key capture case",
                )
                directory = self.prepare("escaped-" + str(index), authorization=authority)
                gateway = self.gateway(directory=directory)
                response = self.response(
                    headers=[("x-request-id", "prefix " + quoted + " suffix")]
                    if raw is None
                    else None
                )
                if raw is not None:
                    response.read.return_value = raw
                with self.assertRaises(ProviderUncertain):
                    self.send(gateway, connection=self.connection(response))
                operation = gateway.ledger.get(gateway.operation_id(self.call))
                self.assertEqual(operation.status, "unknown")
                envelope = self.envelope(operation)
                self.assertTrue(envelope.withheld)
                self.assertEqual(envelope.body, b"")
                self.assertEqual(envelope.headers, ())
                self.assertEqual(
                    envelope.received_sha256,
                    hashlib.sha256(response.read.return_value).hexdigest(),
                )
                self.assertEqual(authority.summary()["reserved_microusd"], 300)
                self.assertEqual(authority.summary()["spent_microusd"], 0)

    def test_anthropic_cache_inclusive_usage_through_real_funded_gateway(self):
        capability = "anthropic.messages.v1"
        key = "anthropic-offline-test-key-never-real"
        spec = replace(self.spec, provider="anthropic", model="test-claude")
        profiles = {
            "format": "buddha.gateway-profiles.v1",
            "profiles": {
                "primary": {
                    "spec": asdict(spec),
                    "response_models": ["test-claude"],
                    "request_tiers": ["auto", "standard_only"],
                    "response_tiers": ["", "standard"],
                    "allow_omitted_tier": True,
                }
            },
        }
        self.write("host", "profiles/anthropic.json", json.dumps(profiles))
        release = Release.from_record(self.release_record | {"requires": [capability]})
        selection = prepare_selection(
            release, self.roots, capabilities={capability: "profiles/anthropic.json"}
        )
        review = self.review | {
            "credential_sha256": {"anthropic": hashlib.sha256(key.encode()).hexdigest()}
        }
        gateway = self.gateway(
            directory=self.prepare("anthropic-run", selection=selection, review=review)
        )
        body = encoded(
            {
                "model": "test-claude",
                "system": [
                    {
                        "type": "text",
                        "text": "literal system instruction",
                        "cache_control": {"type": "ephemeral", "ttl": "1h"},
                    }
                ],
                "messages": [{"role": "user", "content": [{"type": "text", "text": "literal"}]}],
                "max_tokens": 10,
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": "high"},
            }
        )
        call = GatewayCall(capability, "primary", "task-a/quality", 0, body)
        response = Mock(status=200)
        response.read.return_value = encoded(
            {
                "model": "test-claude",
                "usage": {
                    "input_tokens": 5,
                    "cache_creation_input_tokens": 7,
                    "cache_read_input_tokens": 11,
                    "output_tokens": 3,
                    "service_tier": "standard",
                },
                "content": [{"type": "text", "text": "{malformed assistant JSON"}],
            }
        )
        response.getheaders.return_value = [("request-id", "req-anthropic-synthetic")]
        connection = self.connection(response)
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": key}, clear=True),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            envelope = gateway.execute(call)
        operation = gateway.ledger.get(gateway.operation_id(call))
        self.assertEqual(operation.status, "completed")
        self.assertEqual(operation.reserve_microusd, 120)
        self.assertEqual(operation.actual_microusd, 29)
        self.assertEqual(envelope.body, response.read.return_value)
        self.assertEqual(operation.provider_request_id, "req-anthropic-synthetic")
        args, kwargs = connection.request.call_args
        self.assertEqual(args[:2], ("POST", "/v1/messages"))
        self.assertEqual(kwargs["body"], body)
        self.assertEqual(kwargs["headers"]["anthropic-version"], "2023-06-01")
        connection.request.assert_called_once()

    def test_secret_echo_is_withheld_and_secret_in_request_is_denied_unsent(self):
        gateway = self.gateway()
        secret_call = replace(self.call, body=self.body.replace(b"literal", KEY.encode()))
        connection = self.connection()
        with self.assertRaises(ValidationError):
            self.send(gateway, secret_call, connection=connection)
        connection.request.assert_not_called()
        operation = self.operation(gateway, secret_call)
        self.assertEqual(operation.status, "reserved")
        self.assertEqual(operation.reserve_microusd, 300)
        self.assertIsNone(operation.response)
        self.assertEqual(self.ledger.totals()["operation_count"], 1)
        echo_call = replace(self.call, logical_id="independent-response-echo-check")
        response = self.response(error={"message": KEY})
        with self.assertRaises(ProviderUncertain):
            self.send(gateway, echo_call, connection=self.connection(response))
        operation = self.operation(gateway, echo_call)
        envelope = self.envelope(operation)
        self.assertTrue(envelope.withheld)
        self.assertEqual(envelope.body, b"")
        self.assertEqual(
            envelope.received_sha256, hashlib.sha256(response.read.return_value).hexdigest()
        )
        for path in (self.directory / "operations.sqlite3", self.authority.path):
            self.assertNotIn(KEY.encode(), path.read_bytes())

    def test_failure_after_both_reservation_mirrors_rolls_back_both(self):
        import buddha.authorization as module

        gateway = self.gateway()
        original = module._mirror_operation

        def fault(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic fault after attached writes")

        with (
            patch.object(module, "_mirror_operation", side_effect=fault),
            self.assertRaises(RuntimeError),
        ):
            self.send(gateway)
        self.assertEqual(self.ledger.totals()["operation_count"], 0)
        self.assertEqual(self.authority.summary()["operation_count"], 0)
        self.send(gateway)
        self.assertEqual(self.authority.summary()["operation_count"], 1)


if __name__ == "__main__":
    unittest.main()
