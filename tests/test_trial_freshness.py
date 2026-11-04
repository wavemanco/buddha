"""Synthetic writer-boundary freshness and operator identity; no provider calls."""

import os
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_unified_launch as launch_fixture
from test_unified_launch import sha

from buddha import baseline, launch_common, plain_comparison, unified_continuation
from buddha.doctor import _Capture
from buddha.releases import ReleaseError, _json


class TrialFreshnessTests(unittest.TestCase):
    def test_boundary_callback_is_explicit_and_resets_after_failure(self):
        root = Path(__file__).absolute().parent
        calls = []
        launch_common._phase_before_start(root)
        with (
            self.assertRaisesRegex(RuntimeError, "supplied"),
            launch_common._phase_continuation(
                lambda current, relative=False: dict(current),
                lambda trial, phase, current: dict(current),
                before_start=calls.append,
            ),
        ):
            launch_common._phase_before_start(root)
            raise RuntimeError("supplied")
        launch_common._phase_before_start(root)
        self.assertEqual(calls, [root])
        with (
            self.assertRaises(ReleaseError),
            launch_common._phase_continuation(
                lambda current, relative=False: dict(current),
                lambda trial, phase, current: dict(current),
                before_start=True,
            ),
        ):
            pass

    def fixture(self):
        case = launch_fixture.UnifiedLaunchLifecycleTests("runTest")
        self.addCleanup(case.doCleanups)
        case.setUp()
        trial = case.primary_root
        study = trial / "search/study"
        study.mkdir(parents=True)
        empty = trial / "validation"
        empty.mkdir()
        original = study / "original.json"
        original.write_bytes(b'{"synthetic":"original evidence"}')
        descriptor, cut = case.root / "continuation.json", case.root / "cut.json"
        descriptor.write_bytes(b'{"synthetic":"continuation"}')
        cut.write_bytes(b'{"synthetic":"cut"}')
        files = (descriptor, cut, original)
        checked = unified_continuation.CheckedTrialContinuation(
            path=descriptor,
            sha256=sha(descriptor.read_bytes()),
            study=study,
            witness=study / "cells/0/0/1/0/witness",
            _parent=study / "cells/0/0/1/0/screen",
            runtime_sha256="a" * 64,
            _before=(),
            _after=tuple((p, sha(p.read_bytes())) for p in (descriptor, cut)),
            _screen_sha256="b" * 64,
            _policy=_json(
                {
                    "format": "buddha.evidence-observation-policy.v1",
                    "max_total_bytes": 1024 * 1024,
                    "max_resident_bytes": 0,
                }
            ),
            _summary=b"{}",
            _pid=os.getpid(),
            _thread=threading.get_ident(),
            _old_owners=frozenset(),
            _cells=(),
            _screens=frozenset(),
            _authorization=case.shared.path,
            _profiles=("c" * 64, "d" * 64),
            _trial=trial,
            _launch=(case.path, case.digest),
            _roles=tuple(
                (Path(p).name, Path(p), digest, Path(p), digest)
                for p, digest in plain_comparison._source_hashes().items()
            ),
        )
        capture = _Capture(trial)
        _, grant_raw = launch_common._snapshot(case.shared.path)
        prepared = unified_continuation._CheckedState(
            checked=checked,
            trial=trial,
            search_grant=case.shared.path,
            action={},
            files=tuple((p, p.stat().st_size, sha(p.read_bytes())) for p in files),
            databases=frozenset(),
            components=frozenset(),
            entries=frozenset(capture.entries),
            directories=frozenset(name for name in capture.entries if (trial / name).is_dir()),
            grants=((case.shared.path, sha(grant_raw)),),
        )
        capture.finish()
        return case, prepared, cut, original, empty

    def test_cut_file_kind_and_grant_drift_stop_before_keys_or_first_phase(self):
        for boundary in ("lease", "keys"):
            for kind in ("cut", "file", "kind", "grant"):
                with self.subTest(boundary=boundary, kind=kind):
                    self.drift(boundary, kind)

    def drift(self, boundary, kind):
        case, prepared, cut, original, empty = self.fixture()
        target = cut if kind == "cut" else original
        raw = target.read_bytes()
        changed = [False]
        snapshot = launch_common._snapshot
        exclusive = baseline._exclusive

        def mutate():
            changed[0] = True
            if kind in {"cut", "file"}:
                target.write_bytes(raw + b" ")
            elif kind == "kind":
                empty.rmdir()
                empty.write_bytes(b"same name; wrong kind")

        def restore():
            if kind in {"cut", "file"}:
                target.write_bytes(raw)
            elif kind == "kind" and empty.is_file():
                empty.unlink()
                empty.mkdir()

        def changed_snapshot(path):
            value, observed = snapshot(path)
            if kind == "grant" and changed[0] and path == case.shared.path:
                observed += b"synthetic later funding observation"
            return value, observed

        @contextmanager
        def leased(path):
            with exclusive(path):
                if boundary == "lease":
                    mutate()
                yield

        if boundary == "keys":
            case.enter_change = mutate
        with case.seams():
            try:
                with (
                    patch.object(unified_continuation, "_checked_state", return_value=prepared),
                    patch.object(baseline, "_exclusive", side_effect=leased),
                    patch.object(launch_common, "_snapshot", side_effect=changed_snapshot),
                    self.assertRaises(unified_continuation.WitnessContinuationError),
                ):
                    unified_continuation.launch_trial_continuation(
                        prepared.checked.path,
                        expected_sha256=prepared.checked.sha256,
                        live=True,
                        prompt_keys=True,
                        confirm_project_keys=True,
                        notice=lambda text: None,
                    )
            finally:
                restore()
        self.assertNotIn(("primary",), case.events)
        self.assertFalse(case.prepared)
        if boundary == "lease":
            self.assertFalse(any(event[0] == "keys" for event in case.events))

    def test_initial_hooks_recheck_twice_under_workspace_lease_then_allow_payments(self):
        case, prepared, _, _, _ = self.fixture()
        observations = []
        original = prepared.after_locks

        def observed(state, **options):
            self.assertIs(state, prepared)
            self.assertTrue((case.workspace / "running.lock").is_file())
            self.assertNotIn(("primary",), case.events)
            observations.append(options)
            original(**options)

        with (
            case.seams(),
            patch.object(unified_continuation, "_checked_state", return_value=prepared) as checker,
            patch.object(
                unified_continuation._CheckedState,
                "after_locks",
                autospec=True,
                side_effect=observed,
            ),
        ):
            result = unified_continuation.launch_trial_continuation(
                prepared.checked.path,
                expected_sha256=prepared.checked.sha256,
                live=True,
                confirm_project_keys=True,
                notice=lambda text: None,
            )
        self.assertEqual(result["status"], "complete")
        checker.assert_called_once_with(
            prepared.checked.path, prepared.checked.sha256, trial_continuation=True
        )
        self.assertEqual(observations, [{"owned_locks": frozenset()}] * 2)


class TrialIdentityTests(unittest.TestCase):
    def test_cancelled_and_stopped_records_keep_only_validated_descriptor_digest(self):
        case = launch_fixture.UnifiedLaunchCliTests("runTest")
        case.setUp()
        for error, status, code in (
            (KeyboardInterrupt("SYNTHETIC-PRIVATE"), "cancelled", 130),
            (RuntimeError("SYNTHETIC-PRIVATE"), "stopped", 2),
        ):
            with (
                self.subTest(status=status),
                patch.object(unified_continuation, "launch_trial_continuation", side_effect=error),
            ):
                observed_code, record = case.invoke(["--continuation", "--live"])
                self.assertEqual((observed_code, record["status"]), (code, status))
                self.assertEqual(record.get("continuation_sha256"), "0" * 64)
                self.assertNotIn("SYNTHETIC-PRIVATE", str(record))
        case.args[-1] = "SYNTHETIC-PRIVATE-INVALID-HASH"
        with patch.object(unified_continuation, "launch_trial_continuation") as execute:
            code, record = case.invoke(["--continuation", "--live"])
        self.assertEqual((code, record["status"]), (2, "stopped"))
        self.assertNotIn("continuation_sha256", record)
        self.assertNotIn("SYNTHETIC-PRIVATE", str(record))
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
