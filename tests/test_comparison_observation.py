"""Write-once diagnostics from pinned synthetic inputs and fresh real grant bytes.

The focused class mocks only primary context interpretation. Raw reference
metadata/readers and all four grant snapshots are real synthetic fixtures.
"""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_baseline_state as raw_fixtures
from test_improver_launch_state import files, passive_only, sha

from buddha import comparison_observation, launch_common, trial_fence
from buddha.authorization import Authorization
from buddha.releases import _json

AMOUNTS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")


def reference(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def grant_record(authority):
    terms = authority.summary()
    return {
        "path": str(authority.path),
        "id": terms["authorization_id"],
        **{key: terms[key] for key in ("terms_sha256", "scope", "budget_microusd", "max_calls")},
    }


def bind_plan(case, *, trial, definition, nested=False):
    from buddha.unified_funding import reference_scope

    case.plan.update(trial=str(trial), definition_sha256=definition)
    if nested:
        case.directories["in-context"] = case.root / "future-parent/in-context"
        case.plan["references"][1]["directory"] = str(case.directories["in-context"])
    case.plan_path.write_bytes(_json(case.plan))
    case.digest = sha(case.plan_path.read_bytes())
    path = case.authority.path
    preserved = case.root / "preserved-initial-reference-grant.db"
    assert path.resolve().is_relative_to(case.root) and preserved.resolve().is_relative_to(
        case.root
    )
    assert not preserved.exists()
    path.rename(preserved)
    case.authority = Authorization.create(
        path,
        authorization_id="synthetic-shared-references",
        budget_microusd=100_000,
        max_calls=100,
        scope=reference_scope(case.digest),
    )
    case.case.authority = case.authority
    case.controls[case.plan_path] = case.digest


class ComparisonObservationTests(unittest.TestCase):
    def setUp(self):
        self.fixture()

    def fixture(self, *, nested=False):
        self.raw = raw_fixtures.BaselineStateTests("runTest")
        self.raw.setUp()
        self.addCleanup(self.raw.doCleanups)
        self.root, self.serial = self.raw.root, 0
        self.primary_root = self.root / "not-created-primary"
        source_root = self.root / "synthetic-primary-source"
        source_root.mkdir()
        self.source = source_root / "driver.py"
        self.source.write_bytes(b"# Synthetic metadata only; never executed.\n")
        metadata = {}
        for name in ("development", "tasks", "custody", "analysis_plan", "improvement_rule"):
            path = self.root / ("primary-" + name + ".json")
            path.write_bytes(_json({"format": "synthetic.metadata.v1"}))
            metadata[name] = reference(path)
        self.assessment = self.root / "primary-assessment.json"
        self.assessment.write_bytes(
            _json(
                {
                    "format": "buddha.improver-assessment-trial.v4",
                    **metadata,
                    "generation": {
                        "roots": {k: str(v) for k, v in self.raw.case.generation_roots.items()}
                    },
                    "native": {"roots": {k: str(v) for k, v in self.raw.case.native_roots.items()}},
                }
            )
        )
        identity = sha(self.assessment.read_bytes())
        bind_plan(self.raw, trial=self.primary_root, definition=identity, nested=nested)
        self.authorities = {}
        for name, budget, calls in (("search", 40, 4), ("validation", 0, 0), ("final", 85, 10)):
            self.authorities[name] = Authorization.create(
                self.root / (name + ".db"),
                authorization_id="synthetic-" + name,
                budget_microusd=budget,
                max_calls=calls,
                scope=trial_fence._scope_text(
                    trial_fence._TrialScope(self.primary_root, identity, name, version=2)
                ),
            )
        self.proposal_path = self.root / "primary-proposal.json"
        self.proposal_path.write_bytes(
            _json(
                {
                    "format": "buddha.improver-handoff.v1",
                    "assessment": reference(self.assessment),
                    "expected_runtime_sha256": "0" * 64,
                    "directory": str(self.primary_root),
                    "source_sha256": {str(self.source): sha(self.source.read_bytes())},
                }
            )
        )
        self.approval_path = self.root / "primary-approval.json"
        self.approval = {
            "format": "buddha.improver-approval.v1",
            "proposal_sha256": sha(self.proposal_path.read_bytes()),
            "definition_sha256": identity,
            "directory": str(self.primary_root),
            "review": str(self.root / "not-created-review.json"),
            "account_scope": "synthetic-only",
            "authorizations": {name: grant_record(a) for name, a in self.authorities.items()},
        }
        self.launch_path = self.root / "primary-launch.json"
        self.launch = {
            "format": "buddha.improver-launch.v1",
            "proposal": reference(self.proposal_path),
            "approval": {},
            "directory": str(self.primary_root),
            "review": self.approval["review"],
            "source_sha256": {str(self.source): sha(self.source.read_bytes())},
            "timeout_seconds": 300,
        }
        self.save_launch()
        self.primary = {
            "state": "fresh",
            "phase": "search",
            "stop_code": None,
            "next_position": {"stage": "preparation"},
            "state_sha256": "0" * 64,
            "unpublished_report": {"secret": "SYNTHETIC-PRIVATE-ERROR-TEXT"},
        }
        self.options = {
            "primary_launch": self.launch_path,
            "expected_launch_sha256": sha(self.launch_path.read_bytes()),
            "comparison_plan": self.raw.plan_path,
            "expected_plan_sha256": self.raw.digest,
            "reference_grant": grant_record(self.raw.authority),
            "total_limits": {"budget_microusd": 100_125, "max_calls": 114},
            "phase": "checking",
            "reason": "preflight_stop",
            "input_bindings": self.raw.extra,
        }
        self.marker = self.root / "older-observation.json"
        self.marker.write_bytes(b"Original synthetic evidence must remain unchanged.\n")

    def save_launch(self):
        self.approval_path.write_bytes(_json(self.approval))
        self.launch["approval"] = reference(self.approval_path)
        self.launch_path.write_bytes(_json(self.launch))
        if hasattr(self, "options"):
            self.options["expected_launch_sha256"] = sha(self.launch_path.read_bytes())

    def destination(self):
        self.serial += 1
        return self.root / ("observation-" + str(self.serial) + ".json")

    def save(self, *, output=None, primary_effect=None, **changes):
        output = output or self.destination()
        before = files(self.root)
        counts = self.raw.case.physical_sends, len(self.raw.case.events)
        primary = (
            patch("buddha.improver_launch.check_launch", side_effect=primary_effect)
            if primary_effect
            else patch(
                "buddha.improver_launch.check_launch", return_value=copy.deepcopy(self.primary)
            )
        )
        try:
            with (
                passive_only(self),
                primary,
                patch("os.getenv", side_effect=AssertionError("credential read")),
                patch("os.environ.get", side_effect=AssertionError("credential read")),
            ):
                return comparison_observation.save_observation(output, **(self.options | changes))
        finally:
            after = files(self.root)
            if str(output) not in before:
                after.pop(str(output), None)
            self.assertEqual(after, before)
            self.assertEqual((self.raw.case.physical_sends, len(self.raw.case.events)), counts)

    def read(self, saved):
        with (
            passive_only(self),
            patch(
                "buddha.launch_common._snapshot", side_effect=AssertionError("live grant reopened")
            ),
            patch(
                "buddha.improver_launch.check_launch",
                side_effect=AssertionError("live primary reopened"),
            ),
            patch(
                "buddha.baseline_state.inspect_references",
                side_effect=AssertionError("live raw roots reopened"),
            ),
        ):
            return comparison_observation.read_observation(
                Path(saved["path"]), expected_sha256=saved["sha256"]
            )

    def test_write_once_incomplete_readback_is_detached_and_summary_only(self):
        saved = self.save()
        self.assertEqual(set(saved), {"path", "sha256", "observation"})
        result = saved["observation"]
        self.assertEqual(result["format"], "buddha.comparison-observation.v1")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(
            result["stop"],
            {
                "phase": "checking",
                "reason": "preflight_stop",
                "cancelled": False,
                "source": "launcher_reported",
            },
        )
        self.assertEqual(result["funding"]["status"], "observed")
        self.assertEqual(result["funding"]["totals"], dict.fromkeys(AMOUNTS, 0))
        self.assertEqual(result["funding"]["known_subtotal"], result["funding"]["totals"])
        self.assertEqual(result["primary"]["status"], "observed")
        self.assertEqual(result["references"]["status"], "observed")
        self.assertNotIn("funding", result["references"]["value"])
        self.assertNotIn(
            "SYNTHETIC-PRIVATE-ERROR-TEXT", Path(saved["path"]).read_text(encoding="utf-8")
        )
        result["funding"]["phases"].clear()
        self.assertEqual(len(self.read(saved)["funding"]["phases"]), 4)
        original = Path(saved["path"]).read_bytes()
        with self.assertRaises(comparison_observation.ComparisonObservationError):
            self.save(output=Path(saved["path"]))
        self.assertEqual(Path(saved["path"]).read_bytes(), original)

    def test_cancellation_has_reported_phase_and_unavailable_states_without_fake_report(self):
        for phase in ("keys", "primary", "plain-regenerate", "plain-in-context", "comparison"):
            with (
                self.subTest(phase=phase),
                patch(
                    "buddha.baseline_state.inspect_references",
                    side_effect=ValueError("SYNTHETIC-PRIVATE-ERROR-TEXT"),
                ),
            ):
                saved = self.save(
                    phase=phase,
                    reason="cancelled",
                    cancelled=True,
                    primary_effect=lambda *a, **k: (_ for _ in ()).throw(
                        ValueError("SYNTHETIC-PRIVATE-ERROR-TEXT")
                    ),
                )
            result = saved["observation"]
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["stop"]["phase"], phase)
            self.assertTrue(result["stop"]["cancelled"])
            for key in ("primary", "references"):
                self.assertEqual(result[key]["status"], "unavailable")
                self.assertIsNone(result[key]["value"])
            self.assertEqual(result["funding"]["status"], "observed")
            self.assertNotIn("report", result)
            self.assertNotIn(
                "SYNTHETIC-PRIVATE-ERROR-TEXT", Path(saved["path"]).read_text(encoding="utf-8")
            )

    def test_invalid_stop_metadata_and_untrusted_pins_never_arm_output(self):
        cases = (
            {"phase": "complete"},
            {"reason": "exception: private text"},
            {"reason": "UPPER"},
            {"reason": "x" * 65},
            {"cancelled": 1},
            {"expected_launch_sha256": "f" * 64},
            {"expected_plan_sha256": "f" * 64},
        )
        for changes in cases:
            output = self.destination()
            with (
                self.subTest(changes=changes),
                self.assertRaises(comparison_observation.ComparisonObservationError),
            ):
                self.save(output=output, **changes)
            self.assertFalse(output.exists())

    def test_protected_controls_grants_components_and_raw_artifact_roots_refuse(self):
        raw_root = self.raw.directories["regenerate"]
        (raw_root / "attempts").mkdir(parents=True)
        definition = json.loads(self.raw.definitions["regenerate"].read_bytes())
        destinations = [
            self.launch_path,
            self.proposal_path,
            self.approval_path,
            self.authorities["search"].path,
            self.raw.authority.path,
            self.raw.definitions["regenerate"],
            Path(definition["tasks"]),
            Path(definition["generation"]["descriptor"]),
            self.source,
            self.raw.extra_path,
            self.raw.case.generation_roots["agent"] / "new-observation.json",
            raw_root / "attempts/new-observation.json",
            self.primary_root,
        ]
        for output in destinations:
            existed = output.exists()
            with (
                self.subTest(output=output),
                self.assertRaises(comparison_observation.ComparisonObservationError),
            ):
                self.save(output=output)
            self.assertEqual(output.exists(), existed)

    def test_output_cannot_be_ancestor_of_a_declared_missing_raw_root(self):
        self.fixture(nested=True)
        output = self.root / "future-parent"
        with self.assertRaises(comparison_observation.ComparisonObservationError):
            self.save(output=output)
        self.assertFalse(output.exists())

    def test_unknown_shared_raw_hold_counts_once_and_does_not_become_completion(self):
        self.raw.prepare()
        owner = self.raw.directories["in-context"] / "owners/0"
        ledger = self.raw.authority.for_run(owner)
        operation = sha(b"synthetic retained observation request")
        ledger.reserve(operation, sha(b"synthetic observation request"), 17)
        ledger.dispatch(operation)
        ledger.mark_unknown(operation)
        saved = self.save(phase="plain-in-context", reason="authority")
        result = saved["observation"]
        self.assertEqual(
            result["funding"]["totals"],
            {
                "spent_microusd": 0,
                "reserved_microusd": 17,
                "committed_microusd": 17,
                "operation_count": 1,
            },
        )
        self.assertEqual(result["references"]["value"]["blocked_reasons"], ["unknown_operations"])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["stop"]["reason"], "authority")

    def test_one_unreadable_grant_has_known_subtotal_but_no_combined_total(self):
        snapshot = launch_common._snapshot
        missing = self.authorities["final"].path

        def partial(path):
            if path == missing:
                raise OSError("SYNTHETIC-PRIVATE-ERROR-TEXT")
            return snapshot(path)

        with patch("buddha.launch_common._snapshot", side_effect=partial):
            result = self.save()["observation"]
        self.assertEqual(result["funding"]["status"], "partial")
        self.assertIsNone(result["funding"]["totals"])
        self.assertEqual(result["funding"]["known_subtotal"], dict.fromkeys(AMOUNTS, 0))
        self.assertIsNone(result["funding"]["phases"]["final"]["totals"])
        self.assertEqual(result["funding"]["phases"]["final"]["status"], "unavailable")
        with patch(
            "buddha.launch_common._snapshot", side_effect=OSError("SYNTHETIC-PRIVATE-ERROR-TEXT")
        ):
            result = self.save()["observation"]
        self.assertEqual(result["funding"]["status"], "unavailable")
        self.assertIsNone(result["funding"]["known_subtotal"])
        self.assertIsNone(result["funding"]["totals"])

    def test_mismatched_identity_and_ambiguous_declarations_never_guess_costs(self):
        result = self.save(reference_grant=self.options["reference_grant"] | {"id": "foreign"})[
            "observation"
        ]
        self.assertEqual(
            result["funding"]["phases"]["shared_plain_references"]["reason"], "funding_mismatch"
        )
        self.assertIsNone(result["funding"]["totals"])
        for key in ("id", "path"):
            original = copy.deepcopy(self.approval)
            self.approval["authorizations"]["final"][key] = self.approval["authorizations"][
                "search"
            ][key]
            self.save_launch()
            result = self.save()["observation"]
            self.assertEqual(result["funding"]["status"], "unavailable")
            self.assertIsNone(result["funding"]["known_subtotal"])
            self.assertIsNone(result["funding"]["totals"])
            self.approval = original
            self.save_launch()

    def test_late_grant_drift_cannot_commit_an_observed_stale_row(self):
        finish = launch_common._finish_snapshot
        target = self.authorities["final"].path
        original = target.read_bytes()
        changed = False

        def drift(path, raw, **options):
            nonlocal changed
            if path == target and not changed:
                target.write_bytes(original + b" ")
                changed = True
            return finish(path, raw, **options)

        before = files(self.root)
        try:
            with (
                passive_only(self),
                patch("buddha.improver_launch.check_launch", return_value=self.primary),
                patch("buddha.launch_common._finish_snapshot", side_effect=drift),
            ):
                saved = comparison_observation.save_observation(self.destination(), **self.options)
            self.assertTrue(changed)
            result = saved["observation"]
            self.assertEqual(result["funding"]["phases"]["final"]["reason"], "funding_changed")
            self.assertIsNone(result["funding"]["phases"]["final"]["totals"])
            self.assertIsNone(result["funding"]["totals"])
        finally:
            target.write_bytes(original)
        after = files(self.root)
        after.pop(saved["path"])
        self.assertEqual(after, before)

    def test_mutated_caller_grant_cannot_relabel_captured_rows(self):
        output = self.destination()
        original = self.options["reference_grant"]["id"]

        def changed(*args, **options):
            self.options["reference_grant"]["id"] = "mutated-after-capture"
            return self.primary

        try:
            with self.assertRaises(comparison_observation.ComparisonObservationError):
                self.save(output=output, primary_effect=changed)
        finally:
            self.options["reference_grant"]["id"] = original
        self.assertFalse(output.exists())

    def test_archival_readback_survives_advancement_and_retired_live_inputs(self):
        saved = self.save(phase="keys", reason="cancelled", cancelled=True)
        original = Path(saved["path"]).read_bytes()
        self.raw.prepare()
        ledger = self.raw.authority.for_run(self.raw.directories["regenerate"] / "owners/0")
        operation = sha(b"later synthetic archive operation")
        ledger.reserve(operation, sha(b"later synthetic request"), 17)
        ledger.dispatch(operation)
        ledger.mark_unknown(operation)
        for index, path in enumerate(
            (
                self.launch_path,
                self.raw.plan_path,
                self.raw.extra_path,
                self.raw.authority.path,
                self.authorities["final"].path,
            )
        ):
            destination = self.root / ("retired-" + str(index))
            self.assertTrue(path.resolve().is_relative_to(self.root))
            self.assertTrue(destination.resolve().is_relative_to(self.root))
            path.rename(destination)
        observed = self.read(saved)
        self.assertEqual(observed, saved["observation"])
        self.assertEqual(observed["funding"]["totals"], dict.fromkeys(AMOUNTS, 0))
        self.assertEqual(Path(saved["path"]).read_bytes(), original)

    def test_archival_reader_requires_hash_exact_schema_and_incomplete_status(self):
        saved = self.save()
        with self.assertRaises(comparison_observation.ComparisonObservationError):
            comparison_observation.read_observation(Path(saved["path"]), expected_sha256="f" * 64)
        for kind in ("complete", "extra", "negative", "unknown_zero"):
            record = copy.deepcopy(saved["observation"])
            if kind == "complete":
                record["status"] = "complete"
            elif kind == "extra":
                record["primary"]["value"]["raw_secret"] = "SYNTHETIC-PRIVATE-ERROR-TEXT"
            elif kind == "negative":
                record["funding"]["phases"]["search"]["totals"]["spent_microusd"] = -1
            else:
                record["funding"]["phases"]["search"].update(
                    status="unavailable", reason="funding_unavailable"
                )
            path = self.destination()
            path.write_bytes(_json(record))
            with (
                self.subTest(kind=kind),
                self.assertRaises(comparison_observation.ComparisonObservationError),
            ):
                comparison_observation.read_observation(
                    path, expected_sha256=sha(path.read_bytes())
                )

    def test_write_fsync_and_readback_errors_preserve_all_original_evidence(self):
        write, read = comparison_observation.pipeline._write, comparison_observation.pipeline._read
        for stage in ("write", "fsync", "readback"):
            output = self.destination()
            if stage == "write":

                def failure(path, raw, *, output=output):
                    if path == output:
                        raise OSError("synthetic receipt write error")
                    return write(path, raw)

                instrument = patch("buddha.native_pipeline._write", side_effect=failure)
            elif stage == "fsync":
                instrument = patch(
                    "buddha.native_pipeline.os.fsync",
                    side_effect=OSError("synthetic receipt fsync error"),
                )
            else:

                def wrong(path, *args, output=output, **options):
                    return b"{}" if path == output else read(path, *args, **options)

                instrument = patch("buddha.native_pipeline._read", side_effect=wrong)
            with (
                self.subTest(stage=stage),
                instrument,
                self.assertRaises(comparison_observation.ComparisonObservationError),
            ):
                self.save(output=output)
            self.assertEqual(output.exists(), stage != "write")


class ComparisonObservationComposedTests(unittest.TestCase):
    def test_real_original_primary_and_real_raw_state_compose_without_execution(self):
        import test_improver_launch as primary_fixtures

        primary_fixtures.ImproverLaunchTests.setUpClass()
        self.addCleanup(primary_fixtures.ImproverLaunchTests.doClassCleanups)
        primary = primary_fixtures.ImproverLaunchTests("runTest")
        self.addCleanup(primary.doCleanups)
        primary.setUp()
        bundle = primary.bundle()
        raw = raw_fixtures.BaselineStateTests("runTest")
        raw.setUp()
        self.addCleanup(raw.doCleanups)
        bind_plan(raw, trial=bundle["directory"], definition=sha(_json(primary.definition)))
        bundle["record"]["source_sha256"].update(
            {str(path): digest for path, digest in raw.controls.items()}
        )
        bundle["record"]["source_sha256"][str(Path(comparison_observation.__file__).absolute())] = (
            sha(Path(comparison_observation.__file__).read_bytes())
        )
        launch_hash = primary.save(bundle)
        output = bundle["folder"] / "comparison-diagnostic.json"
        before_primary, before_raw = files(primary.root), files(raw.root)
        phases = primary.definition["phase_limits"]
        limits = {
            key: sum(row[key] for row in phases.values()) + extra
            for key, extra in (("budget_microusd", 100_000), ("max_calls", 100))
        }
        with (
            passive_only(self),
            patch("os.getenv", side_effect=AssertionError("credential read")),
            patch("os.environ.get", side_effect=AssertionError("credential read")),
        ):
            saved = comparison_observation.save_observation(
                output,
                primary_launch=bundle["path"],
                expected_launch_sha256=launch_hash,
                comparison_plan=raw.plan_path,
                expected_plan_sha256=raw.digest,
                reference_grant=grant_record_from_bytes(raw.authority.path),
                total_limits=limits,
                phase="checking",
                reason="preflight_stop",
                input_bindings=raw.extra,
            )
        after = files(primary.root)
        after.pop(str(output))
        self.assertEqual(after, before_primary)
        self.assertEqual(files(raw.root), before_raw)
        result = saved["observation"]
        self.assertEqual(result["primary"]["status"], "observed")
        self.assertEqual(result["primary"]["value"]["state"], "fresh")
        self.assertEqual(result["references"]["status"], "observed")
        self.assertEqual(result["references"]["value"]["state"], "fresh")
        self.assertEqual(result["funding"]["status"], "observed")
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(bundle["directory"].exists())
        self.assertFalse(bundle["review_path"].exists())


def grant_record_from_bytes(path):
    terms = launch_common._snapshot(path)[0]["config"]
    return {
        "path": str(path),
        "id": terms["authorization_id"],
        **{key: terms[key] for key in ("terms_sha256", "scope", "budget_microusd", "max_calls")},
    }
