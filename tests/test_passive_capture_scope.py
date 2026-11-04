"""Constructor-only passive sharing; all byte/tree/sidecar guards stay fresh.

The nullcontext fallback makes the old duplicate-constructor work observable,
without turning absence of the new private context into the RED result.
"""

import json
import os
import tempfile
import threading
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from contextvars import copy_context
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from buddha import doctor
from buddha.search_evidence import EvidencePathLimitError


def scope():
    return getattr(doctor, "_passive_tree_observation", nullcontext)()


def policy(*, entries=4, paths=3):
    return {
        "format": "buddha.evidence-observation-policy.v2",
        "max_total_bytes": 1024,
        "max_tree_entries": entries,
        "max_consumed_paths": paths,
        "max_resident_bytes": 0,
    }


class PassiveCaptureScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "observed"
        self.root.mkdir()
        self.data = self.root / "data.bin"
        self.data.write_bytes(b"original")

    def test_constructor_views_are_independent_and_finish_remains_fresh(self):
        with patch.object(doctor, "_entries", wraps=doctor._entries) as scans:
            with scope():
                first = doctor._Capture(self.root)
                original = dict(first.entries)
                first.entries.clear()
                second = doctor._Capture(self.root)
                third = doctor._Capture(self.root)
                self.assertEqual(scans.call_count, 1)
                self.assertIsNot(first.entries, second.entries)
                self.assertIsNot(second.entries, third.entries)
                self.assertEqual(second.entries, original)
                self.assertEqual(third.entries, original)
                first.entries.update(original)
                for capture in (first, second, third):
                    capture.read(self.data)
                    before = scans.call_count
                    capture.finish()
                    self.assertEqual(scans.call_count, before + 1)
                before_exit = scans.call_count
            self.assertGreater(scans.call_count, before_exit)
            before_outside = scans.call_count
            doctor._Capture(self.root)
            self.assertEqual(scans.call_count, before_outside + 1)

    def test_stricter_policy_does_not_reuse_a_more_generous_snapshot(self):
        (self.root / "second.bin").write_bytes(b"second")
        with doctor._observation_policy(policy()), scope():
            first = doctor._Capture(self.root)
            doctor._Capture(self.root)
            with doctor._observation_policy(policy(entries=1)):
                with self.assertRaises(EvidencePathLimitError):
                    doctor._Capture(self.root)
            self.assertEqual(first._maximum_entries, 4)
            self.assertEqual(first._maximum_paths, 3)
        # Its selected bound is still frozen after both contexts have reset.
        with doctor._observation_policy(policy(entries=9, paths=9)):
            self.assertEqual(first._maximum_entries, 4)
            first.finish()

    def test_registry_entry_budget_falls_back_without_rejecting_valid_roots(self):
        first_root, second_root = self.base / "first", self.base / "second"
        first_root.mkdir()
        second_root.mkdir()
        for root, count in ((first_root, 3), (second_root, 2)):
            for index in range(count):
                (root / str(index)).write_bytes(b"data")
        with (
            doctor._observation_policy(policy()),
            patch.object(doctor, "_entries", wraps=doctor._entries) as scans,
            scope(),
        ):
            for root in (first_root, first_root, second_root, second_root):
                self.assertEqual(len(doctor._Capture(root).entries), 3 if root == first_root else 2)
            counts = Counter(call.args[0] for call in scans.call_args_list)
            self.assertEqual(counts[first_root], 1)
            self.assertEqual(counts[second_root], 2)

    def test_registry_root_budget_falls_back_without_rejecting_valid_roots(self):
        other = self.base / "other"
        other.mkdir()
        (other / "other.bin").write_bytes(b"other")
        with (
            doctor._observation_policy(policy(paths=1)),
            patch.object(doctor, "_entries", wraps=doctor._entries) as scans,
            scope(),
        ):
            for root in (self.root, self.root, other, other):
                self.assertEqual(len(doctor._Capture(root).entries), 1)
            counts = Counter(call.args[0] for call in scans.call_args_list)
            self.assertEqual(counts[self.root], 1)
            self.assertEqual(counts[other], 2)

    def test_copied_context_cannot_share_constructor_snapshot_across_threads(self):
        with patch.object(doctor, "_entries", wraps=doctor._entries) as scans, scope():
            expected = doctor._Capture(self.root).entries
            doctor._Capture(self.root)
            before = scans.call_count
            with ThreadPoolExecutor(max_workers=1) as workers:
                capture = workers.submit(copy_context().run, doctor._Capture, self.root).result()
            self.assertEqual(capture.entries, expected)
            self.assertEqual(scans.call_count, before + 1)

    def check_changed_lease(self, lease):
        lease.write_text("123", encoding="ascii")
        after = None
        before = None
        fresh = None
        rejected = False
        try:
            with patch.object(doctor, "_entries", wraps=doctor._entries) as scans, scope():
                doctor._Capture(self.root)
                doctor._Capture(self.root)
                before = scans.call_count
                lease.write_text("456", encoding="ascii")
                try:
                    fresh = doctor._Capture(self.root)
                except doctor._Busy:
                    rejected = True
                after = scans.call_count
        except doctor._Busy:
            pass  # A changed shared binding may also fail closed at scope exit.
        self.assertIsNotNone(before)
        self.assertTrue(rejected or fresh is not None)
        if not rejected:
            self.assertEqual(after, before + 1)
            if lease.parent == self.root:
                self.assertEqual(fresh.entries[lease.name], doctor._signature(lease.lstat()))

    def test_changed_existing_root_lease_requires_a_fresh_constructor(self):
        self.check_changed_lease(self.root / "running.lock")

    def test_changed_lease_with_colliding_metadata_requires_a_fresh_constructor(self):
        signature = doctor._signature
        for name in ("running.lock", ".search.lock", ".trial-running.lock"):
            with self.subTest(lease=name):
                lease = self.root / name
                lease.write_bytes(b"123")
                information = lease.lstat()
                fixed = signature(information)

                def colliding_metadata(value, information=information, fixed=fixed):
                    if (value.st_dev, value.st_ino) == (
                        information.st_dev,
                        information.st_ino,
                    ):
                        return fixed
                    return signature(value)

                # Deterministic metadata collision, without sleeping or changing
                # the checked evidence reader's independent file guards.
                with patch.object(doctor, "_signature", side_effect=colliding_metadata):
                    self.check_changed_lease(lease)
                lease.unlink()

    def test_oversized_lease_uses_strict_construction_without_reading_it(self):
        (self.root / "running.lock").write_bytes(b"x" * 129)
        with (
            patch.object(doctor, "_entries", wraps=doctor._entries) as scans,
            patch.object(doctor, "_read", side_effect=AssertionError("oversized lease read")),
            scope(),
        ):
            first, second = doctor._Capture(self.root), doctor._Capture(self.root)
            self.assertEqual(first.entries, second.entries)
            self.assertEqual(scans.call_count, 2)

    def test_unreadable_lease_uses_strict_construction(self):
        (self.root / "running.lock").write_bytes(b"123")
        for error in (OSError, doctor.ValidationError):
            with (
                self.subTest(error=error),
                patch.object(doctor, "_entries", wraps=doctor._entries) as scans,
                patch.object(doctor, "_read", side_effect=error("unavailable lease")),
                scope(),
            ):
                first, second = doctor._Capture(self.root), doctor._Capture(self.root)
                self.assertEqual(first.entries, second.entries)
                self.assertEqual(scans.call_count, 2)

    @contextmanager
    def held_trial(self, label):
        from buddha import trial_fence

        trial = self.base / label
        trial.mkdir()
        observed = trial / "study"
        observed.mkdir()
        (observed / "data.bin").write_bytes(b"data")
        lock = trial / ".trial-running.lock"
        lock.write_bytes(b"")
        information = lock.stat()
        binding = trial_fence._TrialScope(trial, "a" * 64, "search")
        held = trial_fence._Held(
            binding,
            os.getpid(),
            threading.get_ident(),
            information.st_dev,
            information.st_ino,
        )
        token = trial_fence._HELD.set(held)
        try:
            trial_fence._assert_held(binding)
            yield observed, binding, held, lock
        finally:
            trial_fence._HELD.reset(token)

    def test_valid_actual_held_trial_identity_can_share_constructor_views(self):
        with (
            self.held_trial("valid-held") as (root, _, _, _),
            patch.object(doctor, "_entries", wraps=doctor._entries) as scans,
            scope(),
        ):
            first, second = doctor._Capture(root), doctor._Capture(root)
            self.assertEqual(scans.call_count, 1)
            self.assertEqual(first.entries, second.entries)
            self.assertIsNot(first.entries, second.entries)

    def test_changed_actual_held_identity_state_or_inode_uses_strict_construction(self):
        from buddha import trial_fence

        for mutation in ("inactive", "pid", "copy", "inode"):
            with (
                self.subTest(mutation=mutation),
                self.held_trial(mutation) as (
                    root,
                    binding,
                    held,
                    lock,
                ),
            ):
                override = None
                after = None
                try:
                    with self.assertRaises(doctor._Busy):
                        with (
                            patch.object(doctor, "_entries", wraps=doctor._entries) as scans,
                            scope(),
                        ):
                            doctor._Capture(root)
                            doctor._Capture(root)
                            if mutation == "inactive":
                                held.active = False
                            elif mutation == "pid":
                                held.pid += 1
                            elif mutation == "copy":
                                override = trial_fence._HELD.set(replace(held))
                                trial_fence._assert_held(binding)  # Equal fields, different token.
                            else:
                                lock.rename(lock.with_name("previous-lock"))
                                lock.write_bytes(b"")
                            if mutation != "copy":
                                with self.assertRaises(trial_fence.TrialFenceError):
                                    trial_fence._assert_held(binding)
                            doctor._Capture(root)
                            after = scans.call_count
                    self.assertEqual(after, 2)
                finally:
                    if override is not None:
                        trial_fence._HELD.reset(override)

    def test_actual_held_token_copied_to_another_thread_cannot_enable_sharing(self):
        from buddha import trial_fence

        with (
            self.held_trial("copied-held-thread") as (root, binding, _, _),
            patch.object(doctor, "_entries", wraps=doctor._entries) as scans,
            scope(),
        ):
            doctor._Capture(root)
            doctor._Capture(root)

            def copied_thread():
                with self.assertRaises(trial_fence.TrialFenceError):
                    trial_fence._assert_held(binding)
                return doctor._Capture(root)

            with ThreadPoolExecutor(max_workers=1) as workers:
                capture = workers.submit(copy_context().run, copied_thread).result()
            self.assertEqual(len(capture.entries), 1)
            self.assertEqual(scans.call_count, 2)

    def test_namespace_drift_is_rejected_even_without_an_explicit_finish(self):
        nested = self.root / "nested"
        nested.mkdir()
        with self.assertRaises(doctor._Busy):
            with scope():
                doctor._Capture(self.root)
                (nested / "late.bin").write_bytes(b"late")

    def test_add_remove_and_entry_type_changes_keep_existing_finish_guards(self):
        for mutation in ("add", "remove", "type"):
            with self.subTest(mutation=mutation):
                root = self.base / mutation
                root.mkdir()
                data = root / "data.bin"
                data.write_bytes(b"original")
                with self.assertRaises((doctor._Busy, doctor.ValidationError, OSError)):
                    with scope():
                        capture = doctor._Capture(root)
                        doctor._Capture(root)
                        capture.read(data)
                        if mutation == "add":
                            (root / "late.bin").write_bytes(b"late")
                        elif mutation == "remove":
                            data.unlink()
                        else:
                            data.unlink()
                            data.mkdir()
                        capture.finish()

    def test_changed_content_with_restored_metadata_still_fails_byte_verification(self):
        information = self.data.stat()
        with self.assertRaises(doctor._Busy):
            with scope():
                capture = doctor._Capture(self.root)
                doctor._Capture(self.root)
                capture.read(self.data)
                self.data.write_bytes(b"modified")
                os.utime(self.data, ns=(information.st_atime_ns, information.st_mtime_ns))
                capture.finish()

    def test_external_sqlite_sidecar_guard_remains_fresh(self):
        database = self.base / "external.sqlite3"
        database.write_bytes(b"opaque original ledger")
        with self.assertRaises(doctor._Busy):
            with scope():
                capture = doctor._Capture(self.root)
                doctor._Capture(self.root)
                capture.database(database)
                database.with_name(database.name + "-wal").write_bytes(b"writer")
                capture.finish()

    def test_link_aliases_are_not_admitted_from_a_cached_root(self):
        alias = self.base / "linked-root"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest("symlink creation unavailable: " + type(error).__name__)
        with scope():
            doctor._Capture(self.root)
            doctor._Capture(self.root)
            with self.assertRaises(doctor.ValidationError):
                doctor._Capture(alias)

    def test_late_external_hardlink_cannot_bypass_existing_file_guard(self):
        with self.assertRaises((doctor._Busy, doctor.ValidationError)):
            with scope():
                capture = doctor._Capture(self.root)
                doctor._Capture(self.root)
                capture.read(self.data)
                os.link(self.data, self.base / "alias.bin")
                capture.finish()


class MockedStudyCaptureScopeTests(unittest.TestCase):
    def test_real_restore_parity_and_natural_repeated_constructor_work(self):
        """Natural initial and first-counted-plan phases; no injected captures.

        Workers/HTTPS are supplied. Declaration, owners, funding, seals and
        passive readers remain real. This stops before the first counted child.
        """
        from test_improver_study import ImproverStudyCapacityTests, observe_fixture_workers

        from buddha import improver_study
        from buddha.releases import _json

        capacity = ImproverStudyCapacityTests("runTest")
        self.addCleanup(capacity.doCleanups)
        fixture, record = capacity.fixture()
        observe_fixture_workers(fixture, self)
        directory, _, authority = fixture.prepare_study("passive-constructor-probe", record)
        original_init, original_finish, original_entries = (
            doctor._Capture.__init__,
            doctor._Capture.finish,
            doctor._entries,
        )

        def measured(restore):
            depths, counts, returned_entries = Counter(), Counter(), Counter()
            per_root = {}

            def construct(capture, root):
                depths["constructor"] += 1
                try:
                    return original_init(capture, root)
                finally:
                    depths["constructor"] -= 1

            def finish(capture):
                counts["finish_calls"] += 1
                depths["finish"] += 1
                try:
                    return original_finish(capture)
                finally:
                    depths["finish"] -= 1

            def entries(root, **kwargs):
                bucket = (
                    "constructor"
                    if depths["constructor"]
                    else "finish"
                    if depths["finish"]
                    else "exit"
                )
                result = original_entries(root, **kwargs)
                counts[bucket] += 1
                returned_entries[bucket] += len(result)
                values = per_root.setdefault(str(root), Counter())
                values[bucket] += 1
                values[bucket + "_entries"] += len(result)
                return result

            with (
                patch.object(doctor._Capture, "__init__", construct),
                patch.object(doctor._Capture, "finish", finish),
                patch.object(doctor, "_entries", entries),
            ):
                reader, state = restore(directory, authority.path)
            signature = {
                "action": {
                    "kind": state["action"]["kind"],
                    "directory": str(state["action"]["directory"]),
                    "position": state["action"]["position"],
                },
                "declaration": _json(state["record"]).decode(),
                "coverage": state["coverage"],
                "authorization": state["authorization"],
                "owners": {
                    str(path): reader.owner(path).accounting() for path in state["owner_paths"]
                },
                # Additional explicit verification is outside the counted interval.
                "files": reader.fingerprints(),
            }
            return signature, {
                "counts": dict(counts),
                "returned_entries": dict(returned_entries),
                "per_root": {root: dict(values) for root, values in per_root.items()},
            }

        strict = getattr(improver_study, "_restore_observed", improver_study._restore)
        before_files = fixture.h.files(fixture.root)
        before_activity = fixture.engine.physical_sends, len(fixture.events)
        initial_strict, initial_strict_work = measured(strict)
        initial_shared, initial_shared_work = measured(improver_study._restore)
        self.assertEqual(initial_shared, initial_strict)
        self.assertEqual(
            initial_shared_work["counts"]["finish_calls"],
            initial_strict_work["counts"]["finish_calls"],
        )
        self.assertEqual(fixture.h.files(fixture.root), before_files)
        self.assertEqual((fixture.engine.physical_sends, len(fixture.events)), before_activity)

        class ReachedFirstCountedProposal(BaseException):
            pass

        def stop_before_counted_proposal(state, action, authorization):
            self.assertEqual(action["directory"], directory / "cells/0/0/0/0")
            self.assertEqual(action["kind"], "prepare_proposal")
            raise ReachedFirstCountedProposal

        with (
            fixture.supplied(),
            patch.object(improver_study, "_prepare_proposal", stop_before_counted_proposal),
            self.assertRaises(ReachedFirstCountedProposal),
        ):
            improver_study.run_improver_study(directory, transport=fixture.transport())
        self.assertTrue((directory / "common/0/0/witness/report.json").is_file())
        self.assertTrue((directory / "cells/0/0/0/0/plan.json").is_file())
        self.assertFalse((directory / "cells/0/0/0/0/proposal").exists())
        before_files = fixture.h.files(fixture.root)
        before_activity = fixture.engine.physical_sends, len(fixture.events)
        repeated_strict, repeated_strict_work = measured(strict)
        repeated_shared, repeated_shared_work = measured(improver_study._restore)
        self.assertEqual(repeated_shared, repeated_strict)
        self.assertEqual(repeated_shared["action"]["kind"], "prepare_proposal")
        study_root = str(directory)
        self.assertLess(
            repeated_shared_work["per_root"][study_root]["constructor"],
            repeated_strict_work["per_root"][study_root]["constructor"],
        )
        self.assertEqual(
            repeated_shared_work["counts"]["finish_calls"],
            repeated_strict_work["counts"]["finish_calls"],
        )
        self.assertGreater(repeated_shared_work["counts"]["exit"], 0)
        self.assertEqual(fixture.h.files(fixture.root), before_files)
        self.assertEqual((fixture.engine.physical_sends, len(fixture.events)), before_activity)
        print(
            json.dumps(
                {
                    "initial_strict": initial_strict_work,
                    "initial_shared": initial_shared_work,
                    "repeated_strict": repeated_strict_work,
                    "repeated_shared": repeated_shared_work,
                },
                sort_keys=True,
            ),
            flush=True,
        )


if __name__ == "__main__":
    unittest.main()
