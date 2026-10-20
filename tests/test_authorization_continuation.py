"""A continuation binding and its one historical-unknown claim commit together."""

import hashlib
import multiprocessing
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from buddha.authorization import Authorization, runtime_fingerprint
from buddha.benchmark import _canonical
from buddha.evaluation import ValidationError
from buddha.ledger import BudgetExceeded, Ledger
from buddha.provider import Reply


def sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def bind_in_process(authority_path, directory, claim, ready, start, results):
    ready.put(directory.name)
    start.wait(10)
    try:
        Authorization(authority_path).bind_continuation(
            directory, runtime_sha256=runtime_fingerprint(), **claim
        )
        results.put((directory.name, "bound"))
    except ValidationError:
        results.put((directory.name, "denied"))


class AuthorizationContinuationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "authority.sqlite3"
        self.authority = Authorization.create(
            self.path,
            authorization_id="experiment",
            budget_microusd=1_000_000,
            max_calls=50,
            scope="one source and its one linked continuation",
        )
        self.source = self.root / "source"
        self.source.mkdir()
        record = {
            "format": "buddha.policy-search.v1",
            "run_id": "source",
            "settings": {"budget_microusd": 1_000_000, "max_calls": 50},
        }
        digest = sha(record)
        (self.source / "manifest.json").write_bytes(_canonical(record | {"record_sha256": digest}))
        self.original = Ledger(
            self.source / "operations.sqlite3",
            run_id="source",
            manifest_sha256=digest,
            budget_microusd=1_000_000,
            max_calls=50,
        )
        for index in range(10):
            operation_id = "slot-" + str(index)
            self.original.reserve(operation_id, sha(operation_id), 100)
            self.original.dispatch(operation_id)
            if index < 9:
                reply = Reply("saved answer", "model", "receipt-" + str(index), 10, 5, "stop")
                self.original.complete(
                    operation_id,
                    response=reply.to_record(),
                    actual_microusd=15,
                    provider_request_id=reply.provider_request_id,
                )
            else:
                self.original.mark_unknown(operation_id)
        self.source_seal = hashlib.sha256(
            (self.source / "operations.sqlite3").read_bytes()
        ).hexdigest()
        self.source_bytes = (self.source / "operations.sqlite3").read_bytes()
        self.authority.import_history(
            self.source, manifest_sha256=digest, ledger_sha256=self.source_seal
        )
        self.claim = dict(
            source_run_id="source",
            operation_id="slot-9",
            evidence_sha256=self.source_seal,
            reason="reviewed receiptless uncertainty remains held",
        )

    def prepare(self, name, *, format="buddha.policy-search-continuation.v1", changes=None):
        directory = self.root / name
        directory.mkdir()
        continuation = {
            "format": "buddha.linked-continuation.v1",
            "source_run_id": "source",
            "source_ledger_sha256": self.source_seal,
            "authorization_path": str(self.authority.path),
            "runtime_sha256": runtime_fingerprint(),
            "acceptance_reason": self.claim["reason"],
            "replacement": {"source_operation_id": "slot-9"},
        }
        if changes:
            continuation.update(changes)
        record = {
            "format": format,
            "run_id": name,
            "settings": {"budget_microusd": 1_000_000, "max_calls": 40},
            "continuation": continuation,
        }
        digest = sha(record)
        (directory / "manifest.json").write_bytes(_canonical(record | {"record_sha256": digest}))
        Ledger(
            directory / "operations.sqlite3",
            run_id=name,
            manifest_sha256=digest,
            budget_microusd=1_000_000,
            max_calls=40,
        )
        return directory

    def bind(self, directory, **changes):
        self.authority.bind_continuation(
            directory, runtime_sha256=runtime_fingerprint(), **(self.claim | changes)
        )

    def assert_unbound(self, directory):
        with closing(sqlite3.connect(directory / "operations.sqlite3")) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='authorization_binding'"
                ).fetchone()
            )
        self.assertFalse(
            any(row["run_id"] == directory.name for row in self.authority.summary()["runs"])
        )

    def test_binding_claim_is_atomic_idempotent_and_adds_no_operations(self):
        directory = self.prepare("continuation")
        self.bind(directory)
        summary = self.authority.summary()
        self.assertEqual(summary["operation_count"], 10)
        self.assertEqual(summary["spent_microusd"], 135)
        self.assertEqual(summary["reserved_microusd"], 100)
        self.assertEqual(self.authority.for_run(directory).totals()["operation_count"], 0)
        self.bind(directory)
        self.assertEqual(self.authority.summary(), summary)
        self.assertEqual((self.source / "operations.sqlite3").read_bytes(), self.source_bytes)
        ledger = self.authority.for_run(directory)
        ledger.reserve("replacement", sha("replacement"), 100)

    def test_canonical_authority_identity_accepts_an_equivalent_input_path(self):
        (self.root / "alias").mkdir()
        self.path = self.root / "alias" / ".." / "authority.sqlite3"
        canonical = self.authority.path
        self.authority = Authorization(self.path)
        self.assertEqual(self.authority.path, canonical)
        directory = self.prepare("canonical-continuation")
        self.bind(directory)
        self.assertEqual(self.authority.for_run(directory).totals()["operation_count"], 0)

    def test_generic_bind_cannot_skip_the_continuation_claim(self):
        directory = self.prepare("continuation")
        with self.assertRaises(ValidationError):
            self.authority.bind_run(directory, runtime_sha256=runtime_fingerprint())
        self.assert_unbound(directory)

    def test_new_method_rejects_regular_run_format(self):
        directory = self.prepare("regular", format="buddha.policy-search.v1")
        with self.assertRaises(ValidationError):
            self.bind(directory)
        self.assert_unbound(directory)

    def test_non_text_manifest_format_is_rejected_without_any_binding(self):
        directory = self.prepare("malformed-format", format=["untrusted-format"])
        before = self.authority.summary()
        with self.assertRaises(ValidationError):
            self.bind(directory)
        self.assert_unbound(directory)
        self.assertEqual(self.authority.summary(), before)

    def test_manifest_claim_must_match_source_operation_evidence_reason_and_authority(self):
        for index, changes in enumerate(
            [
                {"source_run_id": "other-source"},
                {"source_ledger_sha256": "a" * 64},
                {"replacement": {"source_operation_id": "other-operation"}},
                {"acceptance_reason": "different review"},
                {"authorization_path": str(self.root / "other-authority.sqlite3")},
                {"runtime_sha256": "a" * 64},
            ]
        ):
            directory = self.prepare("mismatch-" + str(index), changes=changes)
            before = self.authority.summary()
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.bind(directory)
            self.assert_unbound(directory)
            self.assertEqual(self.authority.summary(), before)

    def test_competing_claim_rolls_back_local_binding_registration_and_events(self):
        first, second = self.prepare("first"), self.prepare("second")
        self.bind(first)
        before = self.authority.summary()
        with self.assertRaises(ValidationError):
            self.bind(second)
        self.assert_unbound(second)
        self.assertEqual(self.authority.summary(), before)

    def test_existing_binding_requires_its_original_atomic_claim(self):
        directory = self.prepare("incomplete")
        # Simulate a preexisting inconsistent binding; retry must not grant the
        # missing spending exception while silently repairing unrelated state.
        with patch("buddha.authorization._accept_unknown", return_value=None):
            self.bind(directory)
        before = self.authority.summary()
        with self.assertRaises(ValidationError):
            self.bind(directory)
        self.assertEqual(self.authority.summary(), before)
        with self.assertRaises(BudgetExceeded):
            self.authority.for_run(directory).reserve("work", sha("work"), 100)

    def test_injected_failure_after_acceptance_rolls_back_both_databases(self):
        import buddha.authorization as module

        directory = self.prepare("faulted")
        before = self.authority.summary()
        original = module._event

        def interrupt_after_acceptance(connection, schema, kind, *args, **kwargs):
            original(connection, schema, kind, *args, **kwargs)
            if kind == "historical_unknown_accepted":
                raise RuntimeError("injected interruption after claim and binding writes")

        with patch.object(module, "_event", side_effect=interrupt_after_acceptance):
            with self.assertRaises(RuntimeError):
                self.bind(directory)
        self.assert_unbound(directory)
        self.assertEqual(self.authority.summary(), before)
        self.bind(directory)

    def test_separate_processes_can_claim_only_one_continuation(self):
        directories = [self.prepare(name) for name in ("first", "second")]
        context = multiprocessing.get_context("spawn")
        ready, results, start = context.Queue(), context.Queue(), context.Event()
        processes = [
            context.Process(
                target=bind_in_process,
                args=(self.path, directory, self.claim, ready, start, results),
            )
            for directory in directories
        ]
        try:
            for process in processes:
                process.start()
            for _ in processes:
                ready.get(timeout=15)
            start.set()
            outcomes = dict(results.get(timeout=15) for _ in processes)
            self.assertCountEqual(outcomes.values(), ["bound", "denied"])
            for process in processes:
                process.join(15)
                self.assertEqual(process.exitcode, 0)
            loser = next(
                directory for directory in directories if outcomes[directory.name] == "denied"
            )
            self.assert_unbound(loser)
            self.assertEqual(len(self.authority.summary()["runs"]), 2)
            self.assertEqual(self.authority.summary()["operation_count"], 10)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(10)
            ready.close()
            results.close()

    def test_inactive_continuation_cannot_be_reclaimed_or_receive_another_acceptance(self):
        directory = self.prepare("inactive")
        self.bind(directory)
        self.authority.deactivate("inactive", "closed by operator")
        before = self.authority.summary()
        with self.assertRaises(ValidationError):
            self.bind(directory)
        with self.assertRaises(ValidationError):
            self.authority.accept_historical_unknown(**self.claim, continuation_run_id="inactive")
        self.assertEqual(self.authority.summary(), before)

    def test_historical_source_cannot_be_its_own_continuation(self):
        before = self.authority.summary()
        with self.assertRaises(ValidationError):
            self.bind(self.source)
        with self.assertRaises(ValidationError):
            self.authority.accept_historical_unknown(**self.claim, continuation_run_id="source")
        self.assertEqual(self.authority.summary(), before)
        self.assertEqual((self.source / "operations.sqlite3").read_bytes(), self.source_bytes)

    def test_accepted_old_unknown_does_not_whitelist_new_uncertain_work(self):
        directory = self.prepare("continuation")
        self.bind(directory)
        ledger = self.authority.for_run(directory)
        ledger.reserve("new-uncertain", sha("new-uncertain"), 100)
        ledger.dispatch("new-uncertain")
        ledger.mark_unknown("new-uncertain")
        with self.assertRaises(BudgetExceeded):
            ledger.reserve("new-work", sha("new-work"), 100)
        self.assertEqual(self.authority.summary()["reserved_microusd"], 200)


if __name__ == "__main__":
    unittest.main()
