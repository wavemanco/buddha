"""Actual unified controllers with supplied workers and fake HTTPS, never OS containers.

One small v4 fixture has failed counted children and two starter final cells.
The same original roots survive raw-generation interruption, resume and passive
complete replay. This is engineering integration evidence, not a live study.
"""

import copy
import json
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_improver_launch_state import files, passive_only, sha
from test_unified_launch import grant_record, reference

from buddha import (
    baseline,
    improver_handoff,
    improver_launch,
    plain_comparison,
    unified_funding,
    unified_launch,
)
from buddha.authorization import Authorization
from buddha.gateway import RawHTTPTransport
from buddha.releases import _json

AMOUNTS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")


def checkpoint(label, **metadata):
    print("[unified-rehearsal] " + json.dumps({"label": label, **metadata}), flush=True)


def diagnostic(error):
    chain = []
    cause = error
    while cause is not None:
        chain.append(
            {
                "type": type(cause).__name__,
                "locations": [
                    [Path(frame.filename).name, frame.name, frame.lineno]
                    for frame in traceback.extract_tb(cause.__traceback__)
                ],
            }
        )
        cause = cause.__context__
    checkpoint("unexpected_error_locations", chain=chain)


class UnifiedLaunchIntegrationTests(unittest.TestCase):
    def test_original_controllers_raw_frontier_resume_and_keyless_complete_replay(self):
        import test_baseline as raw_fixtures
        import test_improver_assessment as assessment_fixtures
        import test_improver_launch as primary_fixtures
        import test_improver_study as finite_fixtures
        from test_plain_comparison_integration import PlainComparisonIntegrationTests

        fixture = assessment_fixtures.ImproverAssessmentTests("runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.fixture(proposal_capacity=True)
        harness = finite_fixtures.ImproverStudyCapacityTests("runTest")
        _, development = harness.fixture(finite_fixture=fixture.f)
        fixture.f.outcomes = {(0, 0, arm, 0): "failed" for arm in range(2)}
        definition = copy.deepcopy(fixture.definition)
        definition.update(
            format="buddha.improver-assessment-trial.v4",
            development=fixture.write("unified-rehearsal-development.json", development),
        )
        definition["phase_limits"]["search"] = copy.deepcopy(development["limits"]["study"])
        builder = primary_fixtures.ImproverLaunchTests("runTest")
        builder.f, builder.definition, builder.root = fixture, definition, fixture.root
        builder.api, builder.handoff = improver_launch, improver_handoff
        builder.setUp()
        bundle = builder.bundle()

        compatible = SimpleNamespace(definition=definition, f=fixture.f)
        raw = {}
        for mode in ("regenerate", "in-context"):
            case = raw_fixtures.BaselineTests("runTest")
            self.addCleanup(case.doCleanups)
            case.setUp()
            PlainComparisonIntegrationTests.match_baseline(case, compatible, mode)
            raw[mode] = case
        plan_path = bundle["folder"] / "plain-comparison.json"
        shared_path = bundle["folder"] / "shared-raw.sqlite3"
        plan = {
            "format": "buddha.plain-comparison-plan.v1",
            "method": "all_conditions_then_equal_prompts_descriptive.v1",
            "trial": str(bundle["directory"]),
            "definition_sha256": sha(bundle["declaration"].read_bytes()),
            "references": [
                {
                    "name": mode,
                    "directory": str(case.directory),
                    "authorization": str(shared_path),
                    "definition": str(case.descriptor),
                    "sha256": sha(case.descriptor.read_bytes()),
                }
                for mode, case in raw.items()
            ],
            "consumer_sources": plain_comparison._source_hashes(),
        }
        plan_path.write_bytes(_json(plan))
        shared = Authorization.create(
            shared_path,
            authorization_id="synthetic-unified-rehearsal-shared",
            scope=unified_funding.reference_scope(sha(plan_path.read_bytes())),
            budget_microusd=100_000,
            max_calls=100,
        )
        for case in raw.values():
            case.authority = shared
        sources = {
            str(path): sha(path.read_bytes()) for path in (*unified_launch._sources(), plan_path)
        }
        bundle["proposal"]["source_sha256"].update(sources)
        bundle["proposal_path"].write_bytes(_json(bundle["proposal"]))
        bundle["approval"]["proposal_sha256"] = sha(bundle["proposal_path"].read_bytes())
        bundle["record"]["proposal"] = reference(bundle["proposal_path"])
        bundle["record"]["source_sha256"].update(sources)
        builder.save(bundle)
        limits = {
            key: sum(phase[key] for phase in definition["phase_limits"].values()) + value
            for key, value in (("budget_microusd", 100_000), ("max_calls", 100))
        }
        workspace = bundle["folder"] / "unified-workspace"
        outer = {
            "format": "buddha.unified-launch.v1",
            "primary_launch": reference(bundle["path"]),
            "comparison_plan": reference(plan_path),
            "reference_grant": grant_record(shared),
            "total_limits": limits,
            "directory": str(workspace),
            "source_sha256": sources,
        }
        path = bundle["folder"] / "unified-launch.json"
        path.write_bytes(_json(outer))
        digest = sha(path.read_bytes())
        static = {
            source: Path(source).read_bytes()
            for source in (
                str(path),
                str(plan_path),
                str(bundle["path"]),
                str(bundle["proposal_path"]),
                str(bundle["approval_path"]),
            )
        }
        grants = dict(bundle["authorities"]) | {"shared_plain_references": shared}
        terms = {name: grant_record(authority) for name, authority in grants.items()}
        self.assertTrue(all(not case.directory.exists() for case in raw.values()))
        self.assertFalse(bundle["directory"].exists())
        self.assertFalse(workspace.exists())
        worker_groups, worker_counts = [], {}
        primary_execute = fixture.execute

        def routed_execute(spec, *, initial, handle, **options):
            owner = handle.__self__.gateway.directory
            for mode, case in raw.items():
                if owner.is_relative_to(case.directory):
                    group, execute = "plain-" + mode, case.execute
                    break
            else:
                self.assertTrue(owner.is_relative_to(bundle["directory"]))
                if owner.is_relative_to(fixture.trial / "final"):
                    fixture.schedule = json.loads(
                        (fixture.trial / "freeze/schedule.json").read_bytes()
                    )
                    group = "primary-final"
                else:
                    group = "primary-development"
                execute = primary_execute
            if not worker_groups or worker_groups[-1] != group:
                checkpoint("original_worker_group", group=group)
            worker_groups.append(group)
            worker_counts[group] = worker_counts.get(group, 0) + 1
            return execute(spec, initial=initial, handle=handle, **options)

        native_owner = raw["regenerate"].directory / "owners/1"
        prepare_gateway = baseline.prepare_gateway
        interrupted = []

        def interrupt_native_owner(directory, **options):
            if directory == native_owner and not interrupted:
                root = raw["regenerate"].directory
                self.assertTrue((root / "completed/0.json").is_file())
                self.assertTrue((root / "command-1.json").is_file())
                self.assertTrue((root / "staging/1/0.bin").is_file())
                self.assertFalse(directory.exists())
                interrupted.append(directory)
                checkpoint("raw_generation_sealed_before_native_owner", owner_index=1)
                raise KeyboardInterrupt("synthetic retained raw frontier")
            return prepare_gateway(directory, **options)

        def launch():
            try:
                result = unified_launch.launch(
                    path,
                    expected_sha256=digest,
                    live=True,
                    prompt_keys=True,
                    confirm_project_keys=True,
                    transport=RawHTTPTransport(
                        allow_paid=True, timeout_seconds=bundle["record"]["timeout_seconds"]
                    ),
                    notice=lambda text: print("[unified-rehearsal-notice] " + text, flush=True),
                )
            except Exception as error:
                diagnostic(error)
                raise
            checkpoint(
                "original_launch_returned",
                status=result["status"],
                phase=result.get("phase"),
                reason=result.get("reason"),
            )
            return result

        checkpoint("fresh_scope_bound", raw_modes=2, maximum_final_cells=6)
        with (
            fixture.supplied(),
            patch("buddha.executor.run_container", side_effect=routed_execute),
            patch("buddha.baseline.prepare_gateway", side_effect=interrupt_native_owner),
            patch("getpass.getpass", side_effect=AssertionError("dummy key was not reused")),
            self.assertRaises(KeyboardInterrupt),
        ):
            launch()
        self.assertEqual(interrupted, [native_owner])
        self.assertFalse((workspace / "running.lock").exists())
        self.assertFalse((raw["regenerate"].directory / "running.lock").exists())
        self.assertFalse(raw["in-context"].directory.exists())
        self.assertEqual(fixture.schedule["counts"]["maximum_cells"], 6)
        self.assertEqual(fixture.schedule["counts"]["cells"], 2)
        self.assertEqual(fixture.schedule["counts"]["no_valid_descendant_slots"], 2)
        self.assertTrue(all(arm["role"] == "starter" for arm in fixture.schedule["arms"]))
        observations = list((workspace / "observations").glob("*.json"))
        self.assertEqual(len(observations), 1)
        observation_raw = observations[0].read_bytes()
        observation = json.loads(observation_raw)
        self.assertEqual(
            (observation["status"], observation["stop"]["phase"], observation["stop"]["reason"]),
            ("incomplete", "plain-regenerate", "cancelled"),
        )
        self.assertTrue(observation["stop"]["cancelled"])
        self.assertEqual(observation["primary"]["value"]["state"], "complete")
        self.assertEqual(observation["references"]["status"], "observed")
        positions = {row["name"]: row for row in observation["references"]["value"]["references"]}
        self.assertEqual(
            tuple(positions["regenerate"][key] for key in ("state", "next_stage", "owner_count")),
            ("prepared", 1, 1),
        )
        self.assertEqual(positions["in-context"]["state"], "fresh")
        self.assertEqual(observation["funding"]["status"], "observed")
        first_raw = shared.summary()
        generation_calls = sum(
            task.to_record()["count"] for task in raw["regenerate"].agent.tasks.tasks
        )
        self.assertEqual(first_raw["operation_count"], generation_calls)
        self.assertEqual(first_raw["reserved_microusd"], 0)
        self.assertEqual(
            observation["funding"]["phases"]["shared_plain_references"]["totals"],
            {key: first_raw[key] for key in AMOUNTS},
        )
        primary_before = files(bundle["directory"])
        generation_before = files(raw["regenerate"].directory)
        primary_sends = fixture.engine.physical_sends
        primary_workers = sum(
            value for name, value in worker_counts.items() if name.startswith("primary")
        )
        original_owner = json.loads(
            (raw["regenerate"].directory / "owners/0/manifest.json").read_bytes()
        )
        first_owner_id = original_owner["run_id"]
        checkpoint(
            "cancelled_original_frontier",
            primary_final_cells=fixture.schedule["counts"]["cells"],
            raw_operations=first_raw["operation_count"],
            workers=worker_counts,
        )

        with (
            fixture.supplied(),
            patch("buddha.executor.run_container", side_effect=routed_execute),
            patch("getpass.getpass", side_effect=AssertionError("dummy key was not reused")),
        ):
            complete = launch()
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(complete["review_status"], "pending_separate_review")
        self.assertEqual(json.loads((workspace / "comparison.json").read_bytes()), complete)
        self.assertEqual(files(bundle["directory"]), primary_before)
        self.assertEqual(fixture.engine.physical_sends, primary_sends)
        self.assertEqual(
            sum(value for name, value in worker_counts.items() if name.startswith("primary")),
            primary_workers,
        )
        self.assertTrue(
            all(sha(Path(p).read_bytes()) == digest for p, digest in generation_before.items())
        )
        self.assertEqual(observations[0].read_bytes(), observation_raw)
        self.assertEqual(
            json.loads((raw["regenerate"].directory / "owners/0/manifest.json").read_bytes())[
                "run_id"
            ],
            first_owner_id,
        )
        self.assertEqual(len(list((raw["regenerate"].directory / "attempts").glob("0-*"))), 1)
        for case in raw.values():
            self.assertEqual(
                {path.name for path in (case.directory / "owners").iterdir()}, {"0", "1", "2", "3"}
            )
            self.assertTrue((case.directory / "report.json").is_file())
            self.assertFalse((case.directory / "running.lock").exists())
        final_raw = shared.summary()
        self.assertEqual(final_raw["operation_count"], 2 * (generation_calls + 2))
        self.assertEqual(final_raw["reserved_microusd"], 0)
        self.assertEqual(len(final_raw["runs"]), 8)
        self.assertEqual(
            final_raw["operation_count"], sum(case.physical_sends for case in raw.values())
        )
        observed_total = complete["comparison"]["combined_original_api_research"]
        totals = {
            key: sum(authority.summary()[key] for authority in grants.values()) for key in AMOUNTS
        }
        self.assertEqual({key: observed_total[key] for key in AMOUNTS}, totals)
        self.assertEqual(
            {name: grant_record(authority) for name, authority in grants.items()}, terms
        )
        self.assertTrue(all(Path(source).read_bytes() == data for source, data in static.items()))
        self.assertNotIn("publication_sha256", complete)
        checkpoint(
            "original_comparison_complete",
            totals=totals,
            raw_operations=final_raw["operation_count"],
            workers=worker_counts,
        )

        roots = [fixture.root, *(case.root for case in raw.values())]
        before = [files(root) for root in roots]
        counts = copy.deepcopy(worker_counts), sum(case.physical_sends for case in raw.values())
        with (
            passive_only(self),
            patch("os.getenv", side_effect=AssertionError("credential read")),
            patch("os.environ.get", side_effect=AssertionError("credential read")),
            patch("buddha.credentials.key_environment", side_effect=AssertionError("key entry")),
            patch(
                "buddha.gateway.credential_fingerprints",
                side_effect=AssertionError("credential read"),
            ),
            patch("buddha.improver_launch.launch", side_effect=AssertionError("primary rerun")),
            patch(
                "buddha.baseline.prepare_baseline", side_effect=AssertionError("replacement owner")
            ),
            patch("buddha.baseline.run_baseline", side_effect=AssertionError("reference rerun")),
        ):
            replay = unified_launch.launch(path, expected_sha256=digest, notice=lambda text: None)
        self.assertEqual(replay, complete)
        self.assertEqual([files(root) for root in roots], before)
        self.assertEqual((worker_counts, sum(case.physical_sends for case in raw.values())), counts)
        self.assertEqual(observations[0].read_bytes(), observation_raw)
        checkpoint(
            "keyless_complete_replay_verified",
            publication_sha256=sha((workspace / "comparison.json").read_bytes()),
            totals=totals,
        )
