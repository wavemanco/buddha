"""Reserved trial markers fence real legacy bind/preparation before mutation."""

import hashlib
import json
import unittest
from unittest.mock import patch

import test_authorization as authorization_fixtures
import test_gateway as gateway_fixtures

from buddha import trial_fence as fence
from buddha.authorization import Authorization, runtime_fingerprint
from buddha.common import ValidationError
from buddha.gateway import execution_identity, prepare_gateway
from buddha.provider import Reply

MARKER = ".buddha-evaluation-trial.json"
POISONED_MARKERS = (b"{", b'{"status":"poisoned"}')
SCOPE_PREFIX = "buddha.evaluation-trial.v1:"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_bytes(directory):
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


class TrialFixture:
    """Three actual new grants and opaque engineering metadata, not a scientific trial."""

    def __init__(self, testcase, *, purposes=None):
        self.h = gateway_fixtures.GatewayTests("runTest")
        self.h.setUp()
        testcase.addCleanup(self.h.doCleanups)
        self.root = self.h.root / "trial"
        self.root.mkdir()
        definition = self.root / "definition.json"
        definition.write_bytes(canonical({"fixture": "prospective fence only"}))
        self.definition_sha256 = digest(definition.read_bytes())
        self.authorities = {}
        self.scopes = {}
        self.purposes = (
            purposes
            if purposes is not None
            else {
                "search": "synthetic fixed search comparison",
                "validation": "synthetic fixed validation comparison",
                "final": "synthetic reserved final confirmation",
            }
        )
        phases = {}
        for phase in self.purposes:
            (self.root / phase).mkdir()
            binding = fence._TrialScope(self.root, self.definition_sha256, phase)
            scope = fence._scope_text(binding)
            authority = Authorization.create(
                self.h.root / (phase + "-authority.sqlite3"),
                authorization_id="synthetic-trial-" + phase,
                budget_microusd=10_000,
                max_calls=20,
                scope=scope,
            )
            summary = authority.summary()
            phases[phase] = {
                "authorization_path": str(authority.path),
                **{
                    key: summary[key]
                    for key in (
                        "authorization_id",
                        "terms_sha256",
                        "budget_microusd",
                        "max_calls",
                        "scope",
                    )
                },
                "purpose": self.purposes[phase],
            }
            self.authorities[phase] = authority
            self.scopes[phase] = scope
        funding = self.root / "funding.json"
        funding.write_bytes(
            canonical(
                {
                    "format": "buddha.evaluation-trial-funding.v1",
                    "root": str(self.root),
                    "definition_sha256": self.definition_sha256,
                    "total_budget_microusd": 30_000,
                    "total_max_calls": 60,
                    "phases": phases,
                }
            )
        )
        marker = self.root / MARKER
        marker.write_bytes(
            canonical(
                {
                    "format": "buddha.evaluation-trial-root.v1",
                    "root": str(self.root),
                    "definition_sha256": self.definition_sha256,
                    "funding_sha256": digest(funding.read_bytes()),
                }
            )
        )
        self.pins = {path: digest(path.read_bytes()) for path in (marker, definition, funding)}

    def prepare(self, name="owner", *, phase="search", authority=None, pins=None):
        controls = self.pins if pins is None else pins
        return prepare_gateway(
            self.root / phase / name,
            selection=self.h.selection,
            roots=self.h.roots,
            authorization=authority or self.authorities[phase],
            budget_microusd=10_000,
            max_calls=20,
            input_files=[self.h.input_file, *controls],
            expected_input_hashes={
                self.h.input_file: digest(self.h.input_file.read_bytes()),
                **controls,
            },
            review=self.h.review,
            run_id=name,
        )

    def terms(self, phase="search"):
        return self.authorities[phase]._terms()

    def freeze(self):
        (self.root / "freeze").mkdir()

    def bytes(self):
        return file_bytes(self.h.root)


class TrialFenceTests(unittest.TestCase):
    def test_legacy_bind_under_poisoned_trial_marker_is_readonly(self):
        for marker_raw in POISONED_MARKERS:
            with self.subTest(marker=marker_raw):
                fixture = authorization_fixtures.AuthorizationTests("runTest")
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                original_root = fixture.root

                # Positive control: the actual legacy manifest and Ledger bind outside a trial.
                outside, ledger, _ = fixture.prepare("outside")
                self.assertEqual(ledger.totals()["operation_count"], 0)
                self.assertEqual(fixture.authority.summary()["runs"][0]["directory"], str(outside))

                marked = original_root / "trial"
                marked.mkdir()
                (marked / MARKER).write_bytes(marker_raw)
                fixture.root = marked / "nested"
                fixture.root.mkdir()
                blocked, _, _ = fixture.prepare("blocked", bind=False)
                before = file_bytes(original_root)
                error = None
                try:
                    fixture.authority.bind_run(blocked, runtime_sha256=runtime_fingerprint())
                except ValidationError as caught:
                    error = caught

                # Includes both real databases and any unexpected journal/sidecar publication.
                self.assertEqual(file_bytes(original_root), before)
                self.assertIsInstance(error, ValidationError)

    def test_gateway_under_poisoned_trial_marker_refuses_before_destination(self):
        for marker_raw in POISONED_MARKERS:
            with self.subTest(marker=marker_raw):
                fixture = gateway_fixtures.GatewayTests("runTest")
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)

                # setUp prepares a real original Gateway outside the reserved tree.
                self.assertTrue((fixture.directory / "manifest.json").is_file())
                self.assertEqual(fixture.ledger.totals()["operation_count"], 0)
                self.assertEqual(len(fixture.authority.summary()["runs"]), 1)
                marked = fixture.root / "trial"
                marked.mkdir()
                (marked / MARKER).write_bytes(marker_raw)
                nested = marked / "nested"
                nested.mkdir()
                destination = nested / "blocked"
                before = file_bytes(fixture.root)
                error = None
                try:
                    prepare_gateway(
                        destination,
                        selection=fixture.selection,
                        roots=fixture.roots,
                        authorization=fixture.authority,
                        budget_microusd=10_000,
                        max_calls=20,
                        input_files=[fixture.input_file],
                        review=fixture.review,
                        run_id="blocked",
                    )
                except ValidationError as caught:
                    error = caught

                self.assertFalse(destination.exists())
                self.assertEqual(file_bytes(fixture.root), before)
                self.assertIsInstance(error, ValidationError)

    def test_phase_scope_controls_and_original_gateway_bindings(self):
        for phase in ("search", "validation"):
            with self.subTest(phase=phase):
                fixture = TrialFixture(self)
                authority = fixture.authorities[phase]
                destination = fixture.root / phase / "owner"
                expected_scope = (
                    SCOPE_PREFIX
                    + canonical(
                        {
                            "root": str(fixture.root),
                            "definition_sha256": fixture.definition_sha256,
                            "phase": phase,
                        }
                    ).decode()
                )
                self.assertEqual(fixture.scopes[phase], expected_scope)
                self.assertEqual(fence.required_controls(destination), fixture.pins)
                with fence.work(
                    authority.path, fixture.terms(phase), directory=destination, kind=phase
                ) as controls:
                    self.assertEqual(controls, fixture.pins)
                    # Actual nested public preparation must reuse this same-thread lease.
                    with fence.lease(authority.path, fixture.terms(phase), directory=destination):
                        fence.assert_work(
                            authority.path,
                            fixture.terms(phase),
                            directory=destination,
                            kind="gateway",
                        )
                        fence.require_purpose(
                            authority.path,
                            fixture.terms(phase),
                            directory=destination,
                            expected=fixture.purposes[phase],
                        )
                        directory = fixture.prepare(phase=phase)
                manifest = json.loads((directory / "manifest.json").read_bytes())
                bindings = {row["path"]: row["sha256"] for row in manifest["invocation"]["inputs"]}
                self.assertEqual(
                    bindings,
                    {
                        str(fixture.h.input_file): digest(fixture.h.input_file.read_bytes()),
                        **{str(path): pin for path, pin in fixture.pins.items()},
                    },
                )
                self.assertEqual(manifest["authorization_path"], str(authority.path))
                self.assertEqual(len(authority.summary()["runs"]), 1)

    def test_same_scope_imposter_and_identical_database_copy_cannot_prepare(self):
        for replacement in ("other-id", "identical-copy"):
            with self.subTest(replacement=replacement):
                fixture = TrialFixture(self)
                original = fixture.authorities["search"]
                path = fixture.h.root / "replacement.sqlite3"
                if replacement == "other-id":
                    imposter = Authorization.create(
                        path,
                        authorization_id="not-the-original-phase-grant",
                        budget_microusd=10_000,
                        max_calls=20,
                        scope=fixture.scopes["search"],
                    )
                else:
                    path.write_bytes(original.path.read_bytes())
                    imposter = Authorization(path)
                before = fixture.bytes()
                with self.assertRaises(ValidationError):
                    fixture.prepare(authority=imposter)
                self.assertFalse((fixture.root / "search/owner").exists())
                self.assertEqual(fixture.bytes(), before)
                self.assertEqual(original.summary()["runs"], [])
                self.assertEqual(imposter.summary()["runs"], [])

    def test_missing_trial_input_is_refused_before_gateway_destination(self):
        for omitted in (MARKER, "definition.json", "funding.json"):
            with self.subTest(omitted=omitted):
                fixture = TrialFixture(self)
                pins = {path: pin for path, pin in fixture.pins.items() if path.name != omitted}
                before = fixture.bytes()
                with self.assertRaises(ValidationError):
                    fixture.prepare(pins=pins)
                self.assertFalse((fixture.root / "search/owner").exists())
                self.assertEqual(fixture.bytes(), before)

    def test_original_phase_grant_cannot_bind_legacy_manifest_without_trial_inputs(self):
        fixture = TrialFixture(self)
        legacy = authorization_fixtures.AuthorizationTests("runTest")
        legacy.root = fixture.root / "search"
        legacy.authority = fixture.authorities["search"]
        directory, _, _ = legacy.prepare("unbound", bind=False)
        before = fixture.bytes()
        with self.assertRaises(ValidationError):
            legacy.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())
        self.assertEqual(fixture.bytes(), before)
        self.assertEqual(legacy.authority.summary()["runs"], [])

    def test_closed_phase_denies_bind_reserve_dispatch_but_records_known_result(self):
        fixture = TrialFixture(self)
        authority = fixture.authorities["search"]
        directory = fixture.prepare()
        ledger = authority.for_run(directory)
        # Delay just the original bind in setup, retaining a genuine Gateway manifest/Ledger.
        with patch.object(authority, "bind_run") as delayed:
            unbound = fixture.prepare("unbound")
        delayed.assert_called_once()
        ledger.reserve("received", digest(b"received request"), 100)
        ledger.reserve("waiting", digest(b"waiting request"), 100)
        self.assertTrue(ledger.dispatch("received"))
        fixture.freeze()
        before = fixture.bytes()
        for action in (
            lambda: ledger.reserve("new", digest(b"new request"), 100),
            lambda: ledger.dispatch("waiting"),
            lambda: authority.bind_run(unbound, runtime_sha256=execution_identity(unbound)),
            lambda: fixture.prepare("after-freeze"),
        ):
            with self.subTest(action=action), self.assertRaises(ValidationError):
                action()
            self.assertEqual(fixture.bytes(), before)
        self.assertFalse((fixture.root / "search/after-freeze").exists())
        self.assertEqual(authority.summary()["reserved_microusd"], 200)
        reply = Reply("known answer", "test-model", "known-receipt", 1, 1, "stop")
        completed = ledger.complete(
            "received",
            response=reply.to_record(),
            actual_microusd=60,
            provider_request_id=reply.provider_request_id,
        )
        self.assertEqual(completed.status, "completed")
        self.assertEqual(ledger.get("waiting").status, "reserved")
        self.assertEqual(authority.summary()["spent_microusd"], 60)
        self.assertEqual(authority.summary()["reserved_microusd"], 100)

    def test_poisoned_freeze_does_not_erase_unknown_or_prevent_received_truth(self):
        fixture = TrialFixture(self)
        authority = fixture.authorities["validation"]
        directory = fixture.prepare(phase="validation")
        ledger = authority.for_run(directory)
        ledger.reserve("in-flight", digest(b"in-flight request"), 100)
        self.assertTrue(ledger.dispatch("in-flight"))
        # Any freeze entry closes work; settlement cannot require valid ready JSON.
        (fixture.root / "freeze").write_bytes(b"incomplete freeze")
        ledger.mark_unknown("in-flight")
        self.assertEqual(ledger.get("in-flight").status, "unknown")
        self.assertEqual(authority.summary()["reserved_microusd"], 100)
        before = fixture.bytes()
        with self.assertRaises(ValidationError):
            ledger.reserve("another", digest(b"another request"), 100)
        self.assertEqual(fixture.bytes(), before)
        reply = Reply("late answer", "test-model", "late-receipt", 1, 1, "stop")
        ledger.complete(
            "in-flight",
            response=reply.to_record(),
            actual_microusd=60,
            provider_request_id=reply.provider_request_id,
        )
        self.assertEqual(ledger.get("in-flight").status, "completed")
        self.assertEqual(authority.summary()["spent_microusd"], 60)
        self.assertEqual(authority.summary()["reserved_microusd"], 0)

    def test_original_completion_deactivation_works_with_grant_outside_closed_tree(self):
        fixture = TrialFixture(self)
        authority = fixture.authorities["search"]
        self.assertFalse(authority.path.is_relative_to(fixture.root))
        directory = fixture.prepare()
        ledger = authority.for_run(directory)
        ledger.reserve("received", digest(b"received request"), 100)
        self.assertTrue(ledger.dispatch("received"))
        fixture.freeze()
        reply = Reply("known answer", "test-model", "known-receipt", 1, 1, "stop")
        ledger.complete(
            "received",
            response=reply.to_record(),
            actual_microusd=60,
            provider_request_id=reply.provider_request_id,
        )
        # Same public deactivation used by execute_stage; no native worker is claimed here.
        reason = "synthetic completion: " + digest(b"retained synthetic completion")
        authority.deactivate("owner", reason)
        summary = authority.summary()
        self.assertFalse(summary["runs"][0]["active"])
        self.assertEqual(summary["spent_microusd"], 60)
        self.assertEqual(summary["reserved_microusd"], 0)
        before = fixture.bytes()
        authority.deactivate("owner", reason)
        with self.assertRaises(ValidationError):
            authority.deactivate("owner", "changed completion anchor")
        self.assertEqual(fixture.bytes(), before)

    def test_cached_raw_reply_after_freeze_needs_no_key_transport_or_new_accounting(self):
        fixture = TrialFixture(self)
        authority = fixture.authorities["search"]
        directory = fixture.prepare()
        gateway = fixture.h.gateway(directory=directory)
        expected = fixture.h.send(gateway=gateway)
        self.assertEqual(authority.summary()["operation_count"], 1)
        self.assertEqual(authority.summary()["spent_microusd"], 11)
        fixture.freeze()
        before = fixture.bytes()
        # Cached reads use existing writable ledger transactions, not a read-only SQL API.
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("buddha.gateway._credential", side_effect=AssertionError("no key read")),
            patch("http.client.HTTPSConnection") as connection,
        ):
            cached = fixture.h.gateway(live=False, directory=directory)
            self.assertEqual(cached.execute(fixture.h.call), expected)
        connection.assert_not_called()
        self.assertEqual(fixture.bytes(), before)
        self.assertEqual(authority.summary()["operation_count"], 1)
        self.assertEqual(authority.summary()["spent_microusd"], 11)

    def test_final_grant_stays_disabled_even_with_caller_written_ready(self):
        for ready in (False, True):
            with self.subTest(ready=ready):
                fixture = TrialFixture(self)
                if ready:
                    fixture.freeze()
                    (fixture.root / "freeze/ready.json").write_bytes(canonical({"status": "ready"}))
                before = fixture.bytes()
                with self.assertRaises(ValidationError):
                    fixture.prepare(phase="final")
                self.assertFalse((fixture.root / "final/owner").exists())
                self.assertEqual(fixture.bytes(), before)
                self.assertEqual(fixture.authorities["final"].summary()["runs"], [])

    def test_trial_historical_routes_refuse_before_evidence_or_acceptance_reads(self):
        fixture = TrialFixture(self)
        authority = fixture.authorities["search"]
        missing = fixture.root / "search/never-written"
        actions = (
            (
                "read_history",
                lambda: authority.import_history(
                    missing, manifest_sha256="a" * 64, ledger_sha256="b" * 64
                ),
            ),
            (
                "_manifest_record",
                lambda: authority.bind_continuation(
                    missing,
                    runtime_sha256=runtime_fingerprint(),
                    source_run_id="old",
                    operation_id="unknown",
                    evidence_sha256="b" * 64,
                    reason="synthetic rejected bypass",
                ),
            ),
            (
                "_accept_unknown",
                lambda: authority.accept_historical_unknown(
                    "old",
                    "unknown",
                    continuation_run_id="replacement",
                    evidence_sha256="b" * 64,
                    reason="synthetic rejected bypass",
                ),
            ),
        )
        before = fixture.bytes()
        for name, action in actions:
            with self.subTest(route=name):
                with patch(
                    "buddha.authorization." + name,
                    side_effect=AssertionError("trial rejection must precede evidence"),
                ) as evidence:
                    with self.assertRaises(ValidationError):
                        action()
                    evidence.assert_not_called()
                self.assertEqual(fixture.bytes(), before)

    def test_original_purpose_and_work_kind_are_not_caller_permissions(self):
        fixture = TrialFixture(self)
        destination = fixture.root / "validation/owner"
        authority = fixture.authorities["validation"]
        before = fixture.bytes()
        with self.assertRaises(ValidationError):
            fence.require_purpose(
                authority.path,
                fixture.terms("validation"),
                directory=destination,
                expected="a different approved purpose",
            )
        for kind in ("improvement", "screen", "search", "feedback", "unknown-kind"):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                with fence.work(
                    authority.path,
                    fixture.terms("validation"),
                    directory=destination,
                    kind=kind,
                ):
                    self.fail("validation grant cannot authorize adaptive work")
        self.assertEqual(fixture.bytes(), before)

    def test_scope_codec_rejects_invalid_identity_and_public_reserved_scope_adoption(self):
        fixture = TrialFixture(self)
        for phase in ("development", "FINAL", "", True):
            with self.subTest(phase=phase), self.assertRaises(ValidationError):
                fence._scope_text(fence._TrialScope(fixture.root, fixture.definition_sha256, phase))
        alias = fixture.root / ".." / fixture.root.name
        with self.assertRaises(ValidationError):
            fence._scope_text(fence._TrialScope(alias, fixture.definition_sha256, "search"))
        original = {
            "root": str(fixture.root),
            "definition_sha256": fixture.definition_sha256,
            "phase": "search",
        }
        malformed = (
            SCOPE_PREFIX + "{",
            SCOPE_PREFIX + canonical(original | {"unexpected": True}).decode(),
            SCOPE_PREFIX + '{"phase":"search","phase":"final"}',
            SCOPE_PREFIX + canonical(original | {"root": str(alias)}).decode(),
        )
        for index, scope in enumerate(malformed):
            with self.subTest(scope=scope):
                authority = Authorization.create(
                    fixture.h.root / ("malformed-" + str(index) + ".sqlite3"),
                    authorization_id="synthetic-malformed-" + str(index),
                    budget_microusd=10_000,
                    max_calls=20,
                    scope=scope,
                )
                before = fixture.bytes()
                with self.assertRaises(ValidationError):
                    fixture.prepare("malformed-" + str(index), authority=authority)
                self.assertFalse((fixture.root / "search" / ("malformed-" + str(index))).exists())
                self.assertEqual(fixture.bytes(), before)


if __name__ == "__main__":
    unittest.main()
