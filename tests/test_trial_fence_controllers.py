"""Actual source controllers consume the trial fence before adaptive effects.

Existing fixtures supply synthetic worker/HTTP frames; custody and funding are real.
"""

import json
import unittest
from unittest.mock import patch

import test_source_mutation_witness as witness_fixtures
import test_source_search as search_fixtures
from test_trial_fence import MARKER, TrialFixture, file_bytes

from buddha import candidate_improvement, source_screen, trial_fence
from buddha.gateway import RawHTTPTransport
from buddha.releases import ReleaseError


class TrialFenceControllerTests(unittest.TestCase):
    def case(self):
        case = search_fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(case.doCleanups)
        return case

    def trial(self, case):
        trial = TrialFixture(
            self,
            purposes={
                "search": "source screen: " + case.seed.comparison_key(),
                "validation": "synthetic fixed validation comparison",
                "final": "synthetic reserved final confirmation",
            },
        )
        case.authority = trial.authorities["search"]
        case.directory = trial.root / "search" / "source-search"
        return trial

    def prepare(self, case, directory, kind):
        if kind == "search":
            case.directory = directory
            return case.prepare()
        return case.h.prepare(case.seed, directory=directory, authority=case.authority)

    def test_poisoned_trial_prepare_refuses_before_either_controller_destination(self):
        for kind in ("screen", "search"):
            with self.subTest(kind=kind):
                case = self.case()
                marked = case.root / "poisoned-trial"
                marked.mkdir()
                (marked / MARKER).write_bytes(b"{")
                destination = marked / kind
                before = file_bytes(case.root)
                with self.assertRaises(ReleaseError):
                    self.prepare(case, destination, kind)
                self.assertFalse(destination.exists())
                self.assertEqual(file_bytes(case.root), before)

    def test_poisoned_trial_run_refuses_before_either_controller_local_lock(self):
        for kind in ("screen", "search"):
            with self.subTest(kind=kind):
                case = self.case()
                marked = case.root / "later-poisoned-trial"
                marked.mkdir()
                destination = marked / kind
                self.prepare(case, destination, kind)
                (marked / MARKER).write_bytes(b"{")
                before = file_bytes(case.root)
                run = case.run_api if kind == "search" else source_screen.run_source_screen
                # A sentinel prevents lower execution while making lock order observable.
                with patch(
                    "buddha.native_pipeline._exclusive",
                    side_effect=trial_fence.TrialFenceError("local lock was reached"),
                ) as local_lock:
                    with self.assertRaises(ReleaseError):
                        run(destination, transport=RawHTTPTransport(allow_paid=False))
                local_lock.assert_not_called()
                self.assertEqual(file_bytes(case.root), before)

    def test_structured_trial_search_round_trip_and_closed_passive_completion(self):
        harness = witness_fixtures._Harness(self)
        case = harness.case
        trial = self.trial(case)
        harness.prepare()
        result = harness.run()
        self.assertEqual(result["status"], "complete")
        self.assertEqual([row["status"] for row in result["witnesses"]], ["passed", "passed"])
        self.assertEqual(result["decisions"][0]["status"], "admitted")
        manifest = json.loads((case.directory / "manifest.json").read_bytes())
        self.assertEqual(manifest["format"], "buddha.source-search-manifest.v3")
        owners = 0
        for path in case.directory.rglob("manifest.json"):
            record = json.loads(path.read_bytes())
            if record.get("format") != "buddha.gateway-run.v1":
                continue
            owners += 1
            bindings = {row["path"]: row["sha256"] for row in record["invocation"]["inputs"]}
            self.assertEqual(record["authorization_path"], str(case.authority.path))
            for control, digest in trial.pins.items():
                self.assertEqual(bindings.get(str(control)), digest)
        self.assertGreater(owners, 0)
        self.assertEqual(case.inspect(), result)
        seed = case.directory / "seed"
        seed_result = case.h.inspect(seed, case.authority)
        with trial_fence.lease(
            case.authority.path, case.authority._terms(), directory=case.directory
        ):
            trial.freeze()
        before = trial.bytes()
        sends, workers = case.engine.physical_sends, case.engine.workers
        with (
            case.h.readonly(),
            patch("buddha.gateway._credential", side_effect=AssertionError("key lookup")),
            patch(
                "buddha.native_pipeline._exclusive", side_effect=AssertionError("local writer lock")
            ),
        ):
            self.assertEqual(
                case.run_api(case.directory, transport=RawHTTPTransport(allow_paid=False)), result
            )
            self.assertEqual(
                source_screen.run_source_screen(seed, transport=RawHTTPTransport(allow_paid=False)),
                seed_result,
            )
        self.assertEqual(trial.bytes(), before)
        self.assertEqual((case.engine.physical_sends, case.engine.workers), (sends, workers))

    def test_freeze_blocks_retained_completed_proposal_before_new_decision(self):
        case = self.case()
        trial = self.trial(case)
        case.proposals = [search_fixtures.REPAIRED]
        case.prepare()
        original = candidate_improvement.run_candidate_improvement

        def complete_then_interrupt(*args, **kwargs):
            result = original(*args, **kwargs)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["disposition"], "materialized")
            raise KeyboardInterrupt("after original proposal completion")

        with patch.object(
            candidate_improvement, "run_candidate_improvement", side_effect=complete_then_interrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                case.run_search()
        iteration = case.directory / "iterations/0"
        proposal = iteration / "proposal"
        self.assertTrue((proposal / "completed/0.json").is_file())
        self.assertEqual(json.loads((proposal / "report.json").read_bytes())["status"], "complete")
        self.assertFalse((iteration / "decision.json").exists())
        self.assertFalse((iteration / "screen").exists())
        retained = file_bytes(proposal)
        with trial_fence.lease(
            case.authority.path, case.authority._terms(), directory=case.directory
        ):
            trial.freeze()
        before = trial.bytes()
        with patch(
            "buddha.native_pipeline._exclusive",
            side_effect=trial_fence.TrialFenceError("local lock was reached"),
        ) as local_lock:
            with self.assertRaises(ReleaseError):
                case.run_api(case.directory, transport=RawHTTPTransport(allow_paid=False))
        local_lock.assert_not_called()
        self.assertFalse((iteration / "decision.json").exists())
        self.assertFalse((iteration / "screen").exists())
        self.assertEqual(file_bytes(proposal), retained)
        self.assertEqual(trial.bytes(), before)

    def test_frozen_trial_prepare_refuses_before_either_controller_write(self):
        for kind in ("screen", "search"):
            with self.subTest(kind=kind):
                case = self.case()
                trial = self.trial(case)
                with trial_fence.lease(
                    case.authority.path, case.authority._terms(), directory=case.directory
                ):
                    trial.freeze()
                destination = trial.root / "search" / kind
                before = trial.bytes()
                with self.assertRaises(ReleaseError):
                    self.prepare(case, destination, kind)
                self.assertFalse(destination.exists())
                self.assertEqual(trial.bytes(), before)
