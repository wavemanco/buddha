"""Finite v5 forward execution with original supplied-worker custody fixtures.

These cases retain the fixture's two literal answers, fake workers/HTTPS and
synthetic native results. No selected source, official scorer or model executes.
They do not establish realistic-size replay capacity or the scientific study.
"""

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_improver_study as fixtures

from buddha.releases import ReleaseError


class PrefixReached(Exception):
    pass


class ImproverStudyForwardTests(unittest.TestCase):
    def fixture(self, *, opportunities=1, **options):
        harness = fixtures.SettledProposalOpportunityTests("runTest")
        self.addCleanup(harness.doCleanups)
        f, record = harness.fixture(bootstrap=False, **options)
        record["descendant_opportunities"] = opportunities
        record["selection"]["finalist_iteration"] = opportunities
        f.recompute_limits(record)
        return f, record

    @contextmanager
    def tracked(self, f, *, before=None):
        restore, advance, plan = f.api._restore, f.api._advance_action, f.api._plan
        calls = {"restore_count": 0, "restores": [], "actions": [], "plans": []}
        cold = 0

        def restored(directory, authorization):
            nonlocal cold
            calls["restore_count"] += 1
            cold += 1
            try:
                reader, state = restore(directory, authorization)
                calls["restores"].append(state["action"]["kind"])
                return reader, state
            finally:
                cold -= 1

        def planned(reader, state, coordinate, pool, failures, previous):
            if not cold:
                calls["plans"].append(coordinate)
            return plan(reader, state, coordinate, pool, failures, previous)

        def advanced(reader, state, authority, transport):
            if before is not None:
                before(reader, state, authority, transport)
            calls["actions"].append(
                (state["action"]["kind"], copy.deepcopy(state["action"]["position"]))
            )
            return advance(reader, state, authority, transport)

        with (
            patch.object(f.api, "_restore", side_effect=restored),
            patch.object(f.api, "_plan", side_effect=planned),
            patch.object(f.api, "_advance_action", side_effect=advanced),
        ):
            yield calls

    @staticmethod
    def projection(state):
        action = state["action"]
        return copy.deepcopy(
            {
                "action": {name: action[name] for name in ("kind", "directory", "position")},
                **{
                    name: state[name]
                    for name in (
                        "coverage",
                        "decisions",
                        "cell_decisions",
                        "common",
                        "pools",
                        "failures",
                        "known",
                        "owner_paths",
                        "authorization",
                        "capacity_paths",
                    )
                },
            }
        )

    def test_scoped_screen_ignores_directory_clocks_through_next_action(self):
        from buddha import doctor, source_screen

        f, record = self.fixture()
        directory, _, authority = f.prepare_study("publication-touch", record, trial=True)
        screen = directory / "common/0/0/screen"
        touched = screen / "tasks/0/evaluation"
        notes = screen / "notes.txt"
        finalizations = []
        finish = doctor._Capture.finish

        def finish_after_touch(capture):
            if capture.root in (screen, directory) and touched.is_dir():
                info = touched.stat()
                os.utime(touched, ns=(info.st_atime_ns, info.st_mtime_ns - 2_000_000_000))
                if notes.is_file():
                    info = notes.stat()
                    os.utime(notes, ns=(info.st_atime_ns, info.st_mtime_ns - 2_000_000_000))
                finalizations.append(capture.root)
            return finish(capture)

        def stop(reader, state, original_authority, transport):
            if state["action"]["kind"] == "screen":
                notes.write_text("unconsumed prior observation", encoding="utf-8")
            if state["action"]["kind"] == "witness":
                raise PrefixReached

        with (
            patch.object(doctor._Capture, "finish", finish_after_touch),
            patch.object(source_screen, "_preflight", wraps=source_screen._preflight) as preflight,
            self.tracked(f, before=stop),
            self.assertRaises(PrefixReached),
        ):
            f.run_study(directory)
        self.assertIn(screen, finalizations)
        self.assertIn(directory, finalizations)
        self.assertEqual(preflight.call_count, 1)
        self.assertTrue((screen / "report.json").is_file())
        self.assertEqual(authority.summary()["operation_count"], f.engine.physical_sends)

    def test_scoped_study_rejects_a_compatible_substitute_for_the_returned_screen(self):
        from buddha import source_screen
        from buddha.releases import _json

        f, record = self.fixture()
        directory, _, authority = f.prepare_study("publication-pin", record, trial=True)
        screen = directory / "common/0/0/screen"
        run = source_screen.run_source_screen

        def substitute(location, **options):
            report = run(location, **options)
            replacement = copy.deepcopy(report)
            replacement["authorization"]["event_count"] -= 1
            raw = _json(replacement)
            (screen / "report.json").write_bytes(raw)
            self.assertEqual(
                source_screen.inspect_source_screen(
                    screen,
                    authorization=authority.path,
                    expected_report_sha256=f.api.pipeline._sha(replacement),
                ),
                replacement,
            )
            return report

        with (
            patch.object(source_screen, "run_source_screen", substitute),
            self.tracked(f) as calls,
            self.assertRaisesRegex(f.api.ImproverStudyError, "retained input differs"),
        ):
            f.run_study(directory)
        self.assertEqual([kind for kind, _ in calls["actions"]], ["screen"])
        self.assertEqual(authority.summary()["operation_count"], f.engine.physical_sends)

    def test_scoped_publication_checks_late_seals_after_staging(self):
        from buddha import doctor

        f, record = self.fixture()
        directory, _, authority = f.prepare_study("publication-extra-seal", record, trial=True)
        screen = directory / "common/0/0/screen"
        seal = screen / "tasks/0/generation/completed/9.json"
        tree = doctor._Capture._tree_entries
        injected = []

        def add_after_staging(capture, root=None, **options):
            entries = tree(capture, root, **options)
            if (
                root is not None
                and capture.root == screen
                and root in capture._watched_trees
                and not injected
            ):
                seal.write_bytes(b"{}")
                injected.append(True)
            return entries

        with (
            patch.object(doctor._Capture, "_tree_entries", add_after_staging),
            self.assertRaises(f.api.ImproverStudyError),
        ):
            f.run_study(directory)
        self.assertEqual(injected, [True])
        self.assertFalse((screen / "report.json").exists())
        self.assertEqual(authority.summary()["operation_count"], f.engine.physical_sends)

    def test_v5_complete_writer_uses_three_cold_restores_and_one_plan_per_coordinate(self):
        f, record = self.fixture()
        directory, _, authority = f.prepare_study("forward-complete", record)
        with self.tracked(f) as calls:
            report = f.run_study(directory)
        self.assertEqual(calls["restore_count"], 3)
        self.assertEqual(calls["restores"], ["screen", "freeze", "publish"])
        self.assertEqual(Counter(calls["plans"]), Counter({(0, 0, 0, 0): 1, (0, 0, 1, 0): 1}))
        self.assertTrue(
            {
                "screen",
                "witness",
                "plan",
                "prepare_proposal",
                "proposal",
                "proposal_capacity",
                "prepare_child",
                "decision",
                "freeze",
                "publish",
            }.issubset({kind for kind, _ in calls["actions"]})
        )
        self.assertEqual(report["status"], "complete")
        self.assertEqual(
            report["coverage"],
            {
                "expected_common": 1,
                "completed_common": 1,
                "expected_cells": 2,
                "completed_cells": 2,
                "expected_opportunities": 2,
                "attempted_opportunities": 2,
                "completed_opportunities": 2,
                "in_flight_opportunities": 0,
                "unattempted_opportunities": 0,
            },
        )
        self.assertEqual([row["status"] for row in report["decisions"]], ["admitted", "admitted"])
        self.assertEqual(len(list(directory.rglob("proposal-capacity.json"))), 5)
        for checkpoint in directory.rglob("proposal-capacity.json"):
            measured = json.loads(checkpoint.read_bytes())
            self.assertEqual(measured["decision"], "pass")
            self.assertGreaterEqual(measured["replacement_count"], 1)
        for witness in (
            directory / "common/0/0/witness",
            directory / "cells/0/0/0/0/witness",
            directory / "cells/0/0/1/0/witness",
        ):
            self.assertEqual(json.loads((witness / "report.json").read_bytes())["status"], "passed")
        for arm, decision in enumerate(report["decisions"]):
            cell = directory / "cells/0/0" / str(arm) / "0"
            packet = json.loads((cell / "feedback/feedback.json").read_bytes())
            provenance = json.loads((cell / "feedback/provenance.json").read_bytes())
            self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v8")
            note = json.loads(packet["records"][0]["note"])
            self.assertEqual(
                note["measurements"]["answers"],
                [{"position": index, "text": text} for index, text in enumerate(f.answer_values())],
            )
            self.assertEqual(note["measurements"]["omitted_answer_positions"], 0)
            proposal = json.loads((cell / "proposal/report.json").read_bytes())
            original = Path(proposal["child"]["directory"]) / "candidate.py"
            copied = cell / "agent/candidate.py"
            self.assertEqual(copied.read_bytes(), original.read_bytes())
            self.assertFalse(copied.samefile(original))
            child = json.loads((cell / "screen/screen.json").read_bytes())
            self.assertEqual(child["generation"]["roots"]["agent"], str(copied.parent))
            self.assertEqual(child["lineage"], proposal["child"]["lineage"])
            self.assertEqual(decision["screen"], f.h.reference(cell / "screen", authority))
        f.assert_accounting(directory, authority, report, record)
        self.assertEqual(authority.summary()["reserved_microusd"], 0)
        self.assertFalse(any(row["active"] for row in authority.summary()["runs"]))
        before = f.h.files(f.root), authority.summary(), f.engine.physical_sends, len(f.events)
        with f.h.readonly(), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(f.inspect(directory, authority), report)
        self.assertEqual(
            (f.h.files(f.root), authority.summary(), f.engine.physical_sends, len(f.events)), before
        )

    def test_v5_slot_one_full_parent_comparison_matches_independent_cold_prefix(self):
        f, record = self.fixture(opportunities=2)
        directory, _, authority = f.prepare_study("forward-comparison-prefix", record)
        retained = []

        def stop(reader, state, original_authority, transport):
            action = state["action"]
            if action["kind"] == "prepare_proposal" and action["position"]["slot"] == 1:
                reader.capture.finish()
                retained.append((self.projection(state), copy.deepcopy(action["position"])))
                raise PrefixReached

        with self.tracked(f, before=stop) as calls, self.assertRaises(PrefixReached):
            f.run_study(directory)
        self.assertEqual(calls["restore_count"], 1)
        self.assertEqual(calls["restores"], ["screen"])
        carried, position = retained[0]
        self.assertEqual(
            position, {"start": 0, "repetition": 0, "arm": 1, "slot": 1, "stage": "proposal"}
        )
        self.assertEqual(carried["coverage"]["completed_opportunities"], 2)
        self.assertEqual(carried["coverage"]["attempted_opportunities"], 3)
        self.assertEqual(
            Counter(calls["plans"]),
            Counter(
                {
                    (0, 0, 0, 0): 1,
                    (0, 0, 1, 0): 1,
                    (0, 0, 1, 1): 1,
                }
            ),
        )
        cell = directory / "cells/0/0/1/1"
        self.assertFalse((cell / "proposal").exists())
        provenance = json.loads((cell / "feedback/provenance.json").read_bytes())
        packet = json.loads((cell / "feedback/feedback.json").read_bytes())
        previous = next(row for row in carried["decisions"] if row["arm"] == 1)
        self.assertEqual(previous["status"], "admitted")
        self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v6")
        self.assertEqual(
            provenance["comparison"],
            {name: previous[name] for name in ("parent", "proposal", "screen")},
        )
        note = json.loads(packet["records"][0]["note"])
        self.assertEqual(note["comparison"]["parent_id"], f.base.candidate_id)
        self.assertEqual(note["comparison"]["current_id"], previous["candidate_id"])
        for layer in ("measurements", "parent_measurements"):
            self.assertEqual(
                note[layer]["answers"],
                [{"position": index, "text": text} for index, text in enumerate(f.answer_values())],
            )
            self.assertEqual(note[layer]["omitted_answer_positions"], 0)
        before = f.h.files(f.root), authority.summary(), f.engine.physical_sends, len(f.events)
        with f.h.readonly(), patch.dict(os.environ, {}, clear=True):
            reader, state = f.api._restore(directory, authority.path)
            self.assertEqual(self.projection(state), carried)
            reader.capture.finish()
        self.assertEqual(
            (f.h.files(f.root), authority.summary(), f.engine.physical_sends, len(f.events)), before
        )

    def test_v5_known_reply_reentry_reuses_owner_then_counts_bad_proposal_and_honors_fence(self):
        f, record = self.fixture()
        f.outcomes = {(0, 0, 0, 0): "rejected"}
        directory, _, authority = f.prepare_study("forward-known", record, trial=True)
        f.known_once = True
        with self.tracked(f) as first_calls:
            partial = f.run_study(directory)
        self.assertEqual(first_calls["restore_count"], 1)
        self.assertEqual(first_calls["restores"], ["screen"])
        self.assertEqual((partial["status"], partial["reason"]), ("incomplete", "protocol"))
        owner = f.known_owner
        self.assertEqual(owner, directory / "cells/0/0/0/0/proposal/owners/0")
        manifest = (owner / "manifest.json").read_bytes()
        observation = directory / partial["observation"]
        original_observation = observation.read_bytes()
        initial_run = next(
            row for row in authority.summary()["runs"] if row["directory"] == str(owner)
        )
        self.assertEqual((initial_run["operation_count"], initial_run["reserved_microusd"]), (1, 0))
        f.known_replay = True
        retained = []

        def stop(reader, state, original_authority, transport):
            if state["coverage"]["completed_opportunities"] == 1:
                retained.append(copy.deepcopy(state["decisions"][0]))
                raise PrefixReached

        with self.tracked(f, before=stop) as second_calls, self.assertRaises(PrefixReached):
            f.run_study(directory)
        self.assertEqual(second_calls["restore_count"], 1)
        self.assertEqual(second_calls["restores"], ["proposal"])
        self.assertEqual(second_calls["plans"], [])
        decision = retained[0]
        self.assertEqual(decision["status"], "rejected")
        self.assertIsNone(decision["candidate_id"])
        self.assertIsNone(decision["screen"])
        cell = directory / "cells/0/0/0/0"
        self.assertEqual(json.loads((cell / "decision.json").read_bytes()), decision)
        for name in ("agent", "screen", "witness"):
            self.assertFalse((cell / name).exists())
        replay_events = [event for event in f.improvements if event["owner"] == owner]
        self.assertEqual([event["physical_sends"] for event in replay_events], [1, 0])
        current_run = next(
            row for row in authority.summary()["runs"] if row["directory"] == str(owner)
        )
        self.assertEqual(current_run["operation_count"], 1)
        self.assertFalse(current_run["active"])
        self.assertEqual((owner / "manifest.json").read_bytes(), manifest)
        self.assertEqual(observation.read_bytes(), original_observation)
        self.assertEqual(authority.summary()["reserved_microusd"], 0)
        f.freeze_trial(directory, authority)
        before = f.h.files(f.root), authority.summary(), f.engine.physical_sends, len(f.events)
        with (
            patch(
                "buddha.native_pipeline._exclusive", side_effect=AssertionError("writer lock")
            ) as lock,
            self.assertRaises(ReleaseError),
        ):
            f.run_study(directory)
        lock.assert_not_called()
        self.assertEqual(
            (f.h.files(f.root), authority.summary(), f.engine.physical_sends, len(f.events)), before
        )

    def test_v5_unknown_witness_retains_hold_and_has_no_new_dispatch_on_reentry(self):
        f, record = self.fixture()
        directory, _, authority = f.prepare_study("forward-unknown", record)
        f.unknown_once, f.unknown_scope = True, directory / "common/0/0/witness"
        with self.tracked(f) as first_calls:
            partial = f.run_study(directory)
        self.assertEqual(first_calls["restore_count"], 1)
        self.assertEqual(first_calls["restores"], ["screen"])
        self.assertEqual((partial["status"], partial["reason"]), ("incomplete", "unknown"))
        self.assertGreater(authority.summary()["reserved_microusd"], 0)
        self.assertFalse((directory / "common/0/0/witness/proposal-capacity.json").exists())
        self.assertFalse((directory / "cells").exists())
        before = f.h.files(f.root), authority.summary(), f.engine.physical_sends, len(f.events)
        with (
            self.tracked(f) as second_calls,
            patch(
                "buddha.gateway.RawHTTPTransport.send_prepared", side_effect=AssertionError("retry")
            ),
        ):
            self.assertEqual(f.run_study(directory), partial)
        self.assertEqual(second_calls["restore_count"], 1)
        self.assertEqual(len(second_calls["restores"]), 1)
        self.assertEqual(second_calls["plans"], [])
        self.assertEqual(
            (f.h.files(f.root), authority.summary(), f.engine.physical_sends, len(f.events)), before
        )

    def test_v5_changed_fixed_improver_after_prepare_refuses_before_original_dispatch(self):
        f, record = self.fixture()
        directory, _, authority = f.prepare_study("forward-control-drift", record)
        prepare = f.lower.prepare_candidate_improvement
        injected = []
        fixed = f.root / "I0/candidate.py"
        original = fixed.read_bytes()

        def changed(stage, **values):
            result = prepare(stage, **values)
            if "cells" in stage.parts and "witness" not in stage.parts and not injected:
                injected.append(stage / "owners/0")
                fixed.write_bytes(original + b"# changed after original proposal preparation\n")
            return result

        with (
            self.tracked(f) as calls,
            patch.object(f.lower, "prepare_candidate_improvement", side_effect=changed),
            self.assertRaises(f.api.ImproverStudyError),
        ):
            f.run_study(directory)
        self.assertEqual(calls["restore_count"], 1)
        self.assertEqual(calls["restores"], ["screen"])
        self.assertEqual(len(injected), 1)
        self.assertFalse(any(owner == injected[0] for owner, _ in f.events))
        manifest = json.loads((injected[0] / "manifest.json").read_bytes())
        run = next(
            row for row in authority.summary()["runs"] if row["run_id"] == manifest["run_id"]
        )
        self.assertEqual(
            (run["operation_count"], run["spent_microusd"], run["reserved_microusd"]), (0, 0, 0)
        )
        self.assertFalse((directory / "cells/0/0/0/0/screen").exists())

    def test_prepared_census_reuses_only_identical_checked_owner_bytes(self):
        from buddha import native_evidence
        from buddha.doctor import _Busy

        f, record = self.fixture()
        directory, _, authority = f.prepare_study("forward-owner-decode", record)
        cold, state = f.api._restore(directory, authority.path)
        cold.finish()
        self.assertEqual(len(cold.owners), 1)
        owner_path, cached = next(iter(cold.owners.items()))
        original_manifest = copy.deepcopy(cached.manifest)
        original_accounting = cached.accounting()
        decode = native_evidence._owner

        def census():
            reader = native_evidence.NativeEvidence(
                directory, authority.path, error_type=f.api.ImproverStudyError
            )
            current = dict(state)
            f.api._census(reader, current, previous=cold)
            self.assertEqual(current["funding"], state["funding"])
            self.assertEqual(current["authorization"], state["authorization"])
            self.assertEqual(current["owner_paths"], state["owner_paths"])
            self.assertEqual(reader.owner(owner_path).accounting(), original_accounting)
            reader.finish()
            return reader

        with patch.object(native_evidence, "_owner", wraps=decode) as decoded:
            fresh = census()
        decoded.assert_not_called()
        self.assertIs(fresh.owner(owner_path), cached)

        cached.manifest["settings"]["max_calls"] += 1
        try:
            with patch.object(native_evidence, "_owner", wraps=decode) as decoded:
                fresh = census()
            decoded.assert_called_once()
            self.assertIsNot(fresh.owner(owner_path), cached)
            self.assertEqual(fresh.owner(owner_path).manifest, original_manifest)
        finally:
            cached.manifest.clear()
            cached.manifest.update(original_manifest)

        serialize = f.api._json
        cache_attempts = []

        def unavailable_cache_serialization(value):
            if isinstance(value, dict) and value.get("record_sha256") == cached.manifest_sha256:
                cache_attempts.append(True)
                raise RecursionError("supplied cached serialization failure")
            return serialize(value)

        with (
            patch.object(f.api, "_json", side_effect=unavailable_cache_serialization),
            patch.object(native_evidence, "_owner", wraps=decode) as decoded,
        ):
            fresh = census()
        self.assertEqual(cache_attempts, [True])
        decoded.assert_called_once()
        self.assertIsNot(fresh.owner(owner_path), cached)

        ledger = owner_path / "operations.sqlite3"
        original_ledger = ledger.read_bytes()
        ledger.write_bytes(b"not a sqlite file" + original_ledger[17:])
        try:
            fresh = native_evidence.NativeEvidence(directory, authority.path)
            with (
                patch.object(native_evidence, "_owner", wraps=decode) as decoded,
                self.assertRaises(sqlite3.DatabaseError),
            ):
                f.api._census(fresh, dict(state), previous=cold)
            decoded.assert_called_once()
            self.assertNotIn(owner_path, fresh.owners)
        finally:
            ledger.write_bytes(original_ledger)

        wal = ledger.with_name(ledger.name + "-wal")
        self.assertFalse(wal.exists())
        wal.write_bytes(b"live original-owner sidecar")
        try:
            fresh = native_evidence.NativeEvidence(directory, authority.path)
            with (
                patch.object(native_evidence, "_owner", wraps=decode) as decoded,
                self.assertRaises(_Busy),
            ):
                f.api._census(fresh, dict(state), previous=cold)
            decoded.assert_not_called()
            self.assertNotIn(owner_path, fresh.owners)
        finally:
            wal.unlink()
        census()

    def test_action_write_scope_uses_actual_tree_snapshots_and_exact_checkpoint(self):
        from buddha import improver_study
        from buddha.native_evidence import NativeEvidence

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / "tree"
            root.mkdir()
            old = root / "common/0/0/screen/report.json"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"original old report")
            location = root / "cells/0/0/0/0"

            def snapshot():
                reader = NativeEvidence(root, base / "unused-authorization.sqlite3")
                reader.finish()
                return reader

            previous = snapshot()
            (location / "agent").mkdir(parents=True)
            (location / "agent/candidate.py").write_bytes(b"supplied child source")
            (location / "screen").mkdir()
            (location / "screen/context.json").write_bytes(b"supplied screen bytes")
            action = {"kind": "prepare_child", "directory": location}
            current = snapshot()
            improver_study._check_action_writes(previous, current, action)
            current.finish()

            previous = snapshot()
            old.write_bytes(b"changed sibling report")
            current = snapshot()
            with self.assertRaisesRegex(improver_study.ImproverStudyError, "outside"):
                improver_study._check_action_writes(previous, current, action)
            current.finish()
            old.write_bytes(b"original old report")

            previous = snapshot()
            cells, retained = root / "cells", base / "retained-cells"
            self.assertTrue(cells.resolve().is_relative_to(base))
            self.assertTrue(retained.resolve().is_relative_to(base))
            cells.rename(retained)
            cells.mkdir()
            try:
                current = snapshot()
                with self.assertRaisesRegex(improver_study.ImproverStudyError, "ancestor"):
                    improver_study._check_action_writes(previous, current, action)
                current.finish()
            finally:
                cells.rmdir()
                retained.rename(cells)

            previous = snapshot()
            action = {"kind": "proposal_capacity", "directory": location}
            (location / "proposal-capacity.json").write_bytes(b"expected checkpoint bytes")
            current = snapshot()
            improver_study._check_action_writes(previous, current, action)
            current.finish()
            previous = snapshot()
            (location / "unexpected-capacity.json").write_bytes(b"outside checkpoint")
            current = snapshot()
            with self.assertRaisesRegex(improver_study.ImproverStudyError, "outside"):
                improver_study._check_action_writes(previous, current, action)
            current.finish()

    def test_keyboard_interrupt_survives_failed_forward_refresh_without_observation(self):
        from buddha import improver_study
        from buddha.gateway import RawHTTPTransport
        from buddha.native_evidence import NativeEvidence

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            reader = NativeEvidence(root, root / "unused-authorization.sqlite3")
            authority = SimpleNamespace(path=reader.authorization)
            state = {
                "action": {"kind": "proposal", "directory": root / "proposal"},
                "funding": {"auth_operations": []},
            }
            transport = RawHTTPTransport(allow_paid=False)
            for error in (
                sqlite3.OperationalError("read failed"),
                RecursionError(),
                OverflowError(),
            ):
                interrupt = KeyboardInterrupt("original worker interruption")
                with (
                    self.subTest(refresh_error=type(error).__name__),
                    patch.object(
                        improver_study.candidate_improvement,
                        "run_candidate_improvement",
                        side_effect=interrupt,
                    ) as candidate,
                    patch.object(improver_study, "_forward_read", side_effect=error) as refresh,
                    self.assertRaises(KeyboardInterrupt) as stopped,
                ):
                    improver_study._advance_action(reader, state, authority, transport)
                self.assertIs(stopped.exception, interrupt)
                candidate.assert_called_once_with(root / "proposal", transport=transport)
                refresh.assert_called_once_with(reader, state)
                self.assertEqual(list(root.iterdir()), [])
                reader.finish()


if __name__ == "__main__":
    unittest.main()
