"""Keyless original matched-state observations; synthetic evidence only."""

import copy
import hashlib
import json
import os
import sqlite3
import unittest
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from unittest.mock import patch

from buddha.releases import Selection, _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def files(root):
    return {str(path): sha(path.read_bytes()) for path in root.rglob("*") if path.is_file()}


@contextmanager
def passive_only(observer):
    connect = sqlite3.connect

    def memory_only(database, *args, **kwargs):
        observer.assertEqual(database, ":memory:", "passive reader connected an original database")
        return connect(database, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {}, clear=True))
        stack.enter_context(patch("sqlite3.connect", side_effect=memory_only))
        for target in (
            "getpass.getpass",
            "socket.socket",
            "ast.parse",
            "buddha.authorization.Authorization.__init__",
            "buddha.gateway.Gateway.__init__",
            "buddha.executor.run_container",
            "buddha.gateway.RawHTTPTransport.prepare",
            "buddha.trial_fence.lease",
        ):
            stack.enter_context(patch(target, side_effect=AssertionError("passive execution")))
        yield


def inspect_keylessly(observer, fixture, directory, expected):
    from buddha.improver_launch_state import inspect_prepared_improver_trial

    before = files(fixture.root), fixture.engine.physical_sends, fixture.engine.workers
    try:
        with passive_only(observer):
            return inspect_prepared_improver_trial(directory, **expected)
    finally:
        observer.assertEqual(
            (files(fixture.root), fixture.engine.physical_sends, fixture.engine.workers), before
        )


def expected_inputs(fixture, bindings):
    return {
        "declaration": fixture.declaration,
        "expected_sha256": sha(fixture.declaration.read_bytes()),
        "expected_runtime_sha256": fixture.engine.candidate.expected_runtime,
        "authorizations": {phase: value.path for phase, value in fixture.authorities.items()},
        "development_review": copy.deepcopy(fixture.engine.fixture.review),
        "input_bindings": dict(bindings),
    }


class ImproverLaunchStatePreparedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_improver_assessment as fixtures

        from buddha import improver_assessment

        cls.f = fixtures.ImproverAssessmentTests("runTest")
        cls.addClassCleanup(cls.f.doCleanups)
        cls.f.setUp()
        development, definition = cls.f.capacity_definition()
        cls.f.f.recompute_limits(development)
        definition["development"] = cls.f.write("launch-state-development.json", development)
        definition["phase_limits"]["search"] = copy.deepcopy(development["limits"]["study"])
        definition["phase_limits"]["final"] = copy.deepcopy(
            cls.f.definition["phase_limits"]["final"]
        )
        cls.definition = definition
        cls.assessment = improver_assessment
        cls.Error = improver_assessment.ImproverAssessmentError
        cls.root = cls.f.root

    def setUp(self):
        self.serial = 0
        self.case = self.root / ("state-" + self._testMethodName)
        self.case.mkdir()

    def prepare(self):
        self.serial += 1
        self.f.bind(self.case.name + "-" + str(self.serial), definition=self.definition)
        outer = self.case / ("input-" + str(self.serial) + ".json")
        outer.write_bytes(b"Synthetic original launch input.\n")
        bindings = {outer: sha(outer.read_bytes())}
        self.assessment.prepare_improver_assessment_trial(
            self.f.trial,
            declaration=self.f.declaration,
            expected_sha256=sha(self.f.declaration.read_bytes()),
            expected_runtime_sha256=self.f.engine.candidate.expected_runtime,
            authorizations=self.f.authorities,
            development_review=self.f.engine.fixture.review,
            input_bindings=bindings,
        )
        return self.f.trial, expected_inputs(self.f, bindings)

    def inspect(self, directory, expected, **changes):
        return inspect_keylessly(self, self.f, directory, expected | changes)

    def test_first_owner_locks_detached_summary_and_stable_state_seal(self):
        directory, expected = self.prepare()
        report = self.inspect(directory, expected)
        self.assertEqual(report["format"], "buddha.improver-launch-state.v1")
        self.assertEqual((report["phase"], report["state"]), ("search", "prepared"))
        self.assertTrue(report["ready"])
        self.assertFalse(report["busy"])
        self.assertFalse(report["inactive_pending"])
        self.assertEqual(report["blocked_reasons"], [])
        self.assertEqual(report["next_position"]["stage"], "common_screen")
        self.assertEqual(set(report["phases"]), {"search", "validation", "final"})
        self.assertEqual(report["phases"]["search"]["owner_count"], 1)
        self.assertEqual(report["phases"]["validation"]["owner_count"], 0)
        self.assertEqual(report["phases"]["final"]["owner_count"], 0)
        self.assertEqual(
            report["totals"],
            dict.fromkeys(
                ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count"), 0
            ),
        )
        self.assertRegex(report["state_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(report["limitations"])
        self.assertEqual(self.inspect(directory, expected), report)
        for lock, raw in (
            (directory / ".trial-running.lock", b"synthetic outer lock"),
            (directory / "search/study/.search.lock", b""),
            (
                directory / "search/study/common/0/0/screen/tasks/0/generation/running.lock",
                b"1234567",
            ),
        ):
            try:
                lock.write_bytes(raw)
                blocked = self.inspect(directory, expected)
                self.assertTrue(blocked["busy"])
                self.assertFalse(blocked["ready"])
                self.assertIn("execution_lock_present", blocked["blocked_reasons"])
                self.assertNotEqual(blocked["state_sha256"], report["state_sha256"])
                self.assertEqual(lock.read_bytes(), raw)
            finally:
                lock.unlink()
        clean = self.inspect(directory, expected)
        saved = copy.deepcopy(clean)
        clean["phases"]["search"]["owner_count"] = 99
        clean["blocked_reasons"].append("caller mutation")
        self.assertEqual(self.inspect(directory, expected), saved)
        for sentinel in (b"VALIDATION-ONLY-SENTINEL", b"FINAL-ONLY-SENTINEL", b"def generate"):
            self.assertNotIn(sentinel, _json(saved))

    def test_caller_expectations_and_coordinated_context_rewrite_require_first_owner_join(self):
        directory, expected = self.prepare()
        changed_review = copy.deepcopy(expected["development_review"])
        changed_review["account_scope"] += "; different scope"
        foreign = dict(expected["authorizations"])
        foreign["search"] = foreign["final"]
        for changes in (
            {"expected_sha256": "0" * 64},
            {"expected_runtime_sha256": "0" * 64},
            {"authorizations": foreign},
            {"development_review": changed_review},
            {"input_bindings": {}},
        ):
            with self.subTest(changes=tuple(changes)), self.assertRaises(self.Error):
                self.inspect(directory, expected, **changes)
        context_path = directory / "context.json"
        original = context_path.read_bytes()
        context = json.loads(original)
        extra = next(iter(expected["input_bindings"]))
        context["input_bindings"] = {}
        del context["controls"][str(extra)]
        try:
            context_path.write_bytes(_json(context))
            # The private outer parser alone accepts this coordinated rewrite.
            self.assessment._state(directory, active=False)
            with self.assertRaises(self.Error):
                self.inspect(directory, expected, input_bindings={})
        finally:
            context_path.write_bytes(original)
        self.inspect(directory, expected)

    def test_whole_phase_owner_custody_and_inactive_original_owner_are_not_bypassed(self):
        from buddha.gateway import prepare_gateway

        directory, expected = self.prepare()
        for phase in ("search", "validation", "final"):
            orphan = directory / phase / "foreign/owners/0"
            orphan.mkdir(parents=True)
            try:
                with self.subTest(phase=phase), self.assertRaises(self.Error):
                    self.inspect(directory, expected)
            finally:
                orphan.rmdir()
                orphan.parent.rmdir()
                orphan.parent.parent.rmdir()
        first = directory / "search/study/common/0/0/screen/tasks/0/generation/owners/0"
        manifest = json.loads((first / "manifest.json").read_bytes())
        inputs = {Path(row["path"]): row["sha256"] for row in manifest["invocation"]["inputs"]}
        foreign = directory / "search/funded-outside-study"
        prepare_gateway(
            foreign,
            selection=Selection.from_bytes(_json(manifest["selection"])),
            roots={key: Path(value) for key, value in manifest["roots"].items()},
            authorization=self.f.authorities["search"],
            budget_microusd=manifest["settings"]["budget_microusd"],
            max_calls=manifest["settings"]["max_calls"],
            input_files=list(inputs),
            expected_input_hashes=inputs,
            review=self.f.engine.fixture.review,
        )
        self.assertEqual(len(self.f.authorities["search"].summary()["runs"]), 2)
        with self.assertRaises(self.Error):
            self.inspect(directory, expected)

        directory, expected = self.prepare()
        first = directory / "search/study/common/0/0/screen/tasks/0/generation/owners/0"
        run_id = json.loads((first / "manifest.json").read_bytes())["run_id"]
        self.f.authorities["search"].deactivate(run_id, "synthetic unfinished owner stop")
        with self.assertRaises(self.Error):
            self.inspect(directory, expected)

    def test_original_reserved_dispatched_unknown_costs_and_status_counts_are_retained(self):
        from buddha import trial_fence

        for status in ("reserved", "dispatched", "unknown"):
            with self.subTest(status=status):
                directory, expected = self.prepare()
                first = directory / "search/study/common/0/0/screen/tasks/0/generation/owners/0"
                authority = self.f.authorities["search"]
                ledger = authority.for_run(first)
                # A valid pending-row identity, without asserting that this
                # synthetic request can be resumed by a worker.
                operation_id = sha(b"synthetic original pending attempt")
                with trial_fence.work(
                    authority.path, authority._terms(), directory=first, kind="gateway"
                ):
                    ledger.reserve(operation_id, sha(b"synthetic request"), 17)
                    if status != "reserved":
                        ledger.dispatch(operation_id)
                    if status == "unknown":
                        ledger.mark_unknown(operation_id)
                report = self.inspect(directory, expected)
                counts = dict.fromkeys(("reserved", "dispatched", "unknown", "completed"), 0)
                counts[status] = 1
                self.assertEqual(report["phases"]["search"]["status_counts"], counts)
                self.assertEqual(report["phases"]["search"]["owner_count"], 1)
                self.assertEqual(
                    report["totals"],
                    {
                        "spent_microusd": 0,
                        "reserved_microusd": 17,
                        "committed_microusd": 17,
                        "operation_count": 1,
                    },
                )
                if status != "reserved":
                    self.assertFalse(report["ready"])
                    self.assertIn(status + "_operations", report["blocked_reasons"])

    def test_late_outer_input_drift_after_real_development_restore_is_refused(self):
        from buddha import improver_study
        from buddha.improver_launch_state import inspect_prepared_improver_trial

        directory, expected = self.prepare()
        extra = next(iter(expected["input_bindings"]))
        original = extra.read_bytes()
        before = files(self.root), self.f.engine.physical_sends, self.f.engine.workers
        restore = improver_study._restore
        mutated = []

        def restore_then_change(*args, **kwargs):
            result = restore(*args, **kwargs)
            if not mutated:
                extra.write_bytes(original + b"Test-induced late drift.\n")
                mutated.append(True)
            return result

        try:
            with (
                passive_only(self),
                patch.object(improver_study, "_restore", side_effect=restore_then_change),
                self.assertRaises(self.Error),
            ):
                inspect_prepared_improver_trial(directory, **expected)
            self.assertEqual(mutated, [True])
        finally:
            extra.write_bytes(original)
            self.assertEqual(
                (files(self.root), self.f.engine.physical_sends, self.f.engine.workers), before
            )

    def test_state_seal_binds_each_original_grant_and_ignores_caller_mapping_order(self):
        directory, expected = self.prepare()
        baseline = self.inspect(directory, expected)
        reversed_grants = dict(reversed(list(expected["authorizations"].items())))
        with self.subTest(case="mapping_order"):
            self.assertEqual(
                self.inspect(directory, expected, authorizations=reversed_grants), baseline
            )
        for phase in ("search", "validation", "final"):
            with self.subTest(phase=phase):
                grant = expected["authorizations"][phase]
                before_raw = grant.read_bytes()
                before_terms = self.f.authorities[phase].summary()
                before = self.inspect(directory, expected)
                # Legal SQLite compaction changes retained bytes, while all
                # original grant terms, rows and accounting remain unchanged.
                with closing(sqlite3.connect(grant)) as connection:
                    connection.execute("VACUUM")
                self.assertNotEqual(grant.read_bytes(), before_raw)
                self.assertEqual(self.f.authorities[phase].summary(), before_terms)
                after = self.inspect(directory, expected)
                self.assertEqual(after["phases"], before["phases"])
                self.assertEqual(after["totals"], before["totals"])
                self.assertNotEqual(after["state_sha256"], before["state_sha256"])

    def test_real_gateway_known_overrun_blocks_further_dispatch_and_passive_readiness(self):
        from buddha.gateway import GatewayCall
        from buddha.ledger import BudgetExceeded

        directory, expected = self.prepare()
        first = directory / "search/study/common/0/0/screen/tasks/0/generation/owners/0"
        fixture = self.f.engine.fixture
        gateway = fixture.gateway(directory=first)
        manifest = json.loads((first / "manifest.json").read_bytes())
        capability = next(iter(manifest["profiles"]))
        profile = manifest["profiles"][capability]["profiles"]["primary"]["spec"]
        body = _json(
            {
                "model": profile["model"],
                "max_completion_tokens": profile["max_output_tokens"],
                "messages": [{"role": "user", "content": "Synthetic retained overrun."}],
            }
        )
        call = GatewayCall(capability, "primary", "synthetic-known-overrun", 0, body)
        response = fixture.response(
            usage={"prompt_tokens": profile["input_token_ceiling"] * 2, "completion_tokens": 3}
        )
        connection = fixture.connection(response)
        # Real gateway/AuthorizedLedger receipt creation and settlement; the
        # existing fixture supplies HTTP bytes, never a network connection.
        with self.assertRaises(BudgetExceeded):
            fixture.send(gateway, call, connection)
        operation = gateway.ledger.get(gateway.operation_id(call))
        self.assertEqual(operation.status, "completed")
        self.assertGreater(operation.actual_microusd, operation.reserve_microusd)
        with gateway.work(directory=first, kind="gateway"), self.assertRaises(BudgetExceeded):
            gateway.ledger.authorize_dispatch()
        report = self.inspect(directory, expected)
        self.assertEqual(report["phases"]["search"]["status_counts"]["completed"], 1)
        self.assertEqual(report["totals"]["spent_microusd"], operation.actual_microusd)
        self.assertFalse(report["ready"])
        self.assertIn("reservation_overrun", report["blocked_reasons"])


class ImproverLaunchStateInterfaceTests(unittest.TestCase):
    def test_original_prepared_trial_reader_is_available(self):
        # Missing-module RED is independent of fixtures, SQL and supplied workers.
        from buddha.improver_launch_state import inspect_prepared_improver_trial

        self.assertTrue(callable(inspect_prepared_improver_trial))


if __name__ == "__main__":
    unittest.main()
