"""Documented direct sessions fence real scoped owners, with mocked execution only."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_agent_run as agent_fixtures
import test_candidate_improvement as improvement_fixtures
import test_candidate_run as candidate_fixtures
import test_native_run as native_fixtures
from test_trial_fence import TrialFixture, digest

from buddha import trial_fence
from buddha.executor import ExecutionResult
from buddha.gateway import Gateway, RawHTTPTransport, prepare_gateway
from buddha.releases import ReleaseError, _json

KINDS = ("candidate", "improvement", "native", "agent")


def snapshot(directory):
    """Keep directory names as well as file bytes; do not infer metadata immutability."""
    return {
        path.relative_to(directory).as_posix(): path.read_bytes() if path.is_file() else None
        for path in directory.rglob("*")
    }


class TrialFenceSessionTests(unittest.TestCase):
    def case(self, kind):
        factory = {
            "candidate": candidate_fixtures.CandidateSessionTests,
            "improvement": improvement_fixtures.ImprovementTests,
            "native": native_fixtures.NativeSessionTests,
            "agent": agent_fixtures.AgentSessionTests,
        }[kind]
        fixture = factory("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        engine = fixture.h if kind == "improvement" else fixture
        original = json.loads((engine.directory / "manifest.json").read_bytes())
        inputs = [Path(row["path"]) for row in original["invocation"]["inputs"]]
        trial = TrialFixture(self)
        authority = trial.authorities["search"]
        controls = {path: digest(path.read_bytes()) for path in inputs} | trial.pins
        directory = trial.root / "search" / (kind + "-owner")
        # Create a fresh original owner with the three controls. Existing legacy
        # fixture owners are never rebound, moved or edited into scoped owners.
        prepare_gateway(
            directory,
            selection=engine.fixture.selection,
            roots=engine.fixture.roots,
            authorization=authority,
            review=engine.fixture.review,
            budget_microusd=10_000,
            max_calls=20,
            input_files=list(controls),
            expected_input_hashes=controls,
            run_id=kind + "-scoped-owner",
        )
        gateway = Gateway(directory, transport=RawHTTPTransport(allow_paid=True))
        engine.gateway = gateway
        engine.output = trial.root / "search" / (kind + "-output")
        return SimpleNamespace(
            kind=kind,
            fixture=fixture,
            engine=engine,
            trial=trial,
            authority=authority,
            gateway=gateway,
            directory=directory,
            output=engine.output,
            work_kind=kind if kind in {"native", "improvement"} else "generation",
        )

    def construct(self, case, *, output=None):
        output = case.output if output is None else output
        if case.kind == "native":
            session = native_fixtures.NativeSession(
                case.gateway, descriptor=case.engine.descriptor, output=output
            )
        elif case.kind == "agent":
            session = agent_fixtures.AgentSession(
                case.gateway, descriptor=case.engine.descriptor, output=output
            )
        else:
            session = case.engine.Session(
                case.gateway,
                descriptor=case.engine.descriptor,
                output=output,
                expected_runtime_sha256=case.engine.expected_runtime,
            )
        if hasattr(session, "close"):
            # Close streams before TrialFixture's Windows directory cleanup.
            self.addCleanup(session.close)
        return session

    def ready(self, case, session):
        if case.kind == "native":
            return {"type": "ready", "aliases": [], "audit": case.engine.audit()}
        if case.kind == "improvement":
            return {
                "type": "ready",
                "agent_sha256": session.agent_sha256,
                "feedback_sha256": session.feedback_sha256,
                "runtime_sha256": session.runtime_sha256,
            }
        return case.engine.ready()

    def work(self, case):
        return trial_fence.work(
            case.authority.path,
            case.authority._terms(),
            directory=case.output,
            kind=case.work_kind,
        )

    def freeze(self, case):
        with trial_fence.lease(
            case.authority.path, case.authority._terms(), directory=case.directory
        ):
            case.trial.freeze()

    def execution(self, case):
        return ExecutionResult(
            0,
            "f" * 64,
            case.engine.record["executor"]["image_id"],
            0,
            0,
            digest(b""),
            0,
            0.01,
            _json({"fixture": "mock executor only; no confinement evidence"}),
            "removed",
        )

    def test_frozen_before_constructor_refuses_before_any_output(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = self.case(kind)
                self.freeze(case)
                before = snapshot(case.trial.root)
                with self.assertRaises(ReleaseError):
                    self.construct(case)
                self.assertFalse(case.output.exists())
                self.assertEqual(snapshot(case.trial.root), before)
                self.assertEqual(case.authority.summary()["operation_count"], 0)

    def test_freeze_after_constructor_refuses_run_before_executor_or_publication(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = self.case(kind)
                session = self.construct(case)
                self.freeze(case)
                before = snapshot(case.trial.root)
                with patch(
                    "buddha.executor.run_container", return_value=self.execution(case)
                ) as worker:
                    with self.assertRaises(ReleaseError):
                        session.run()
                worker.assert_not_called()
                self.assertEqual(snapshot(case.trial.root), before)
                self.assertEqual(case.authority.summary()["operation_count"], 0)

    def test_constructor_joins_original_owner_to_output_phase_and_root(self):
        for kind in KINDS:
            case = self.case(kind)
            outputs = (
                case.trial.root / "validation" / (kind + "-wrong-phase"),
                case.trial.root / "final" / (kind + "-disabled-final"),
                case.trial.h.root / (kind + "-outside-trial"),
            )
            for output in outputs:
                with self.subTest(kind=kind, output=output.name):
                    before = snapshot(case.trial.h.root)
                    with self.assertRaises(ReleaseError):
                        self.construct(case, output=output)
                    self.assertFalse(output.exists())
                    self.assertEqual(snapshot(case.trial.h.root), before)

    def test_direct_ready_callback_requires_already_held_scoped_lease(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = self.case(kind)
                session = self.construct(case)
                before = snapshot(case.trial.root)
                with self.assertRaises(ReleaseError):
                    session.handle(self.ready(case, session))
                self.assertFalse(session.ready)
                self.assertEqual(snapshot(case.trial.root), before)

    def test_freeze_blocks_direct_terminal_or_artifact_callback(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = self.case(kind)
                session = self.construct(case)
                # A real protocol-positive control uses the original root lease.
                with self.work(case):
                    self.assertIsNone(session.handle(self.ready(case, session)))
                self.assertTrue(session.ready)
                self.freeze(case)
                before = snapshot(case.trial.root)
                if kind == "native":
                    frame = case.engine.file("late.json", b"must never be published")
                elif kind == "improvement":
                    frame = {
                        "type": "done",
                        "status": "complete",
                        "reason": "complete",
                        "proposal": case.fixture.capture(case.fixture.child()),
                    }
                else:
                    frame = {
                        "type": "done",
                        "status": "failed",
                        "reason": "agent_error",
                        "answers": [],
                    }
                with self.assertRaises(ReleaseError):
                    session.handle(frame)
                self.assertIsNone(session.done)
                if kind == "improvement":
                    self.assertIsNone(session.proposal_frame)
                self.assertEqual(snapshot(case.trial.root), before)
                self.assertEqual(case.authority.summary()["operation_count"], 0)

    def test_unfrozen_scoped_run_owns_lease_through_actual_mocked_callbacks(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                case = self.case(kind)
                session = self.construct(case)
                if kind == "agent":
                    # This fixture uses four ordinary mocked HTTPS replies and
                    # real shared accounting; no provider or worker is contacted.
                    report = case.engine.run_worker(session)
                    self.assertEqual(case.gateway.ledger.totals()["operation_count"], 4)
                else:

                    def worker(_spec, *, handle, case=case, session=session, kind=kind, **_kwargs):
                        trial_fence.assert_work(
                            case.authority.path,
                            case.authority._terms(),
                            directory=case.output,
                            kind=case.work_kind,
                        )
                        handle(self.ready(case, session))
                        if kind == "native":
                            handle(case.engine.file("result.json", b"literal native artifact"))
                            handle(case.engine.done())
                        elif kind == "improvement":
                            handle(
                                {
                                    "type": "done",
                                    "status": "complete",
                                    "reason": "complete",
                                    "proposal": case.fixture.capture(case.fixture.child()),
                                }
                            )
                        else:
                            handle(case.engine.done(["poor literal", ""]))
                        return self.execution(case)

                    with patch("buddha.executor.run_container", side_effect=worker):
                        report = session.run()
                    self.assertEqual(case.gateway.ledger.totals()["operation_count"], 0)
                reason = report["worker"]["reason"] if kind == "native" else report["reason"]
                self.assertEqual((report["status"], reason), ("complete", "complete"))
                self.assertTrue((case.output / "report.json").is_file())
                if kind == "improvement":
                    self.assertEqual(
                        (case.output / "child/candidate.py").read_text(),
                        case.fixture.child()["source"],
                    )
                elif kind == "native":
                    self.assertEqual(
                        (case.output / "artifacts/result.json").read_bytes(),
                        b"literal native artifact",
                    )


if __name__ == "__main__":
    unittest.main()
