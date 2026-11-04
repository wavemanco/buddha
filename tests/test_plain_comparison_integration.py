"""Original assessment and baseline custody, with supplied workers and HTTPS only.

One class-level synthetic publication set is reused for the passive comparison
and refusals. Original readers and the native numerical projector are never
replaced; selected source canaries never execute on the host.
"""

import base64
import copy
import hashlib
import json
import os
import sqlite3
import sys
import traceback
import unittest
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import test_baseline as baseline_fixtures
import test_improver_assessment as assessment_fixtures

from buddha import baseline, plain_comparison
from buddha.releases import Release, _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def progress(stage):
    print("[plain-comparison fixture] " + stage, file=sys.stderr, flush=True)


class PlainComparisonIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assessment = h = assessment_fixtures.ImproverAssessmentTests("runTest")
        cls.addClassCleanup(h.doCleanups)
        h.setUp()
        h.fixture()
        cls.baselines = {}
        for mode in ("regenerate", "in-context"):
            case = baseline_fixtures.BaselineTests("runTest")
            cls.addClassCleanup(case.doCleanups)
            case.setUp()
            cls.match_baseline(case, h, mode)
            cls.baselines[mode] = case

        cls.plan = h.root / "plain-comparison.json"
        cls.plan.write_bytes(
            _json(
                {
                    "format": "buddha.plain-comparison-plan.v1",
                    "method": "all_conditions_then_equal_prompts_descriptive.v1",
                    "trial": str(h.trial),
                    "definition_sha256": sha(h.declaration.read_bytes()),
                    "references": [
                        {
                            "name": mode,
                            "directory": str(case.directory),
                            "authorization": str(case.authority.path),
                            "definition": str(case.descriptor),
                            "sha256": sha(case.descriptor.read_bytes()),
                        }
                        for mode, case in cls.baselines.items()
                    ],
                    "consumer_sources": plain_comparison._source_hashes(),
                }
            )
        )
        cls.plan_hash = sha(cls.plan.read_bytes())
        progress("static plan frozen before original execution owners")
        h.api.prepare_improver_assessment_trial(
            h.trial,
            declaration=h.declaration,
            expected_sha256=sha(h.declaration.read_bytes()),
            expected_runtime_sha256=h.engine.candidate.expected_runtime,
            authorizations=h.authorities,
            development_review=h.engine.fixture.review,
            input_bindings={cls.plan: cls.plan_hash},
        )
        progress("synthetic improver trial prepared")
        h.develop()
        progress("synthetic development complete")
        h.freeze()
        progress("original descendant schedule confirmed")
        with h.supplied():
            cls.assessment_report = h.run_assessment()
        h.assertEqual(cls.assessment_report["status"], "complete")
        progress("all original synthetic final cells complete")
        cls.assessment_hash = sha((h.trial / "final/report.json").read_bytes())

        cls.reference_hashes = {}
        for mode, case in cls.baselines.items():
            baseline.prepare_baseline(
                case.directory,
                descriptor=case.descriptor,
                authorization=case.authority,
                review=case.fixture.review,
                input_files=[cls.plan],
                expected_input_hashes={cls.plan: cls.plan_hash},
            )
            h.assertEqual(case.run_pipeline()["status"], "complete")
            cls.reference_hashes[mode] = sha((case.directory / "report.json").read_bytes())
            progress("original synthetic plain reference complete: " + mode)

        before = cls.snapshot()
        progress("checking passive original-publication comparison")
        with cls.passive():
            cls.result = cls.compare(diagnostic=True)
        h.assertEqual(cls.snapshot(), before)
        progress("passive original-publication comparison complete")

    @staticmethod
    def match_baseline(case, assessment, mode):
        """Change fresh fixture configuration, preserving the ordinary fixed worker."""
        generation = assessment.definition["generation"]
        tasks = assessment.f.h.source.select(assessment.definition["final_ids"])
        release = Release.from_record(tasks.to_record()["release"])
        for name in ("official", "host", "environment"):
            case.generation_roots[name] = Path(generation["roots"][name])
        case.native_roots = {
            name: Path(path) for name, path in assessment.definition["native"]["roots"].items()
        } | {"agent": case.generation_roots["agent"]}
        case.agent.release, case.agent.tasks = release, tasks
        case.agent.tasks_path.write_bytes(tasks.to_bytes())
        case.agent.config = {
            **{
                key: generation["config"][key] for key in ("provider", "model", "max_output_tokens")
            },
            "instructions": "",
            "sampling": mode,
        }
        case.agent.record["config"] = case.agent.config
        case.agent.record["profile"] = copy.deepcopy(generation["profile"])
        case.agent.record["executor"]["mounts"] = [
            ["/agent", str(case.generation_roots["agent"])],
            ["/runner", str(case.generation_roots["runner"])],
        ]
        case.agent.descriptor.write_bytes(_json(case.agent.record))
        selected = [
            prepare_selection(release, roots, capabilities=generation["selection"]["capabilities"])
            for roots in (case.generation_roots, case.native_roots)
        ]
        case.agent_selection = selected[0]
        case.record["generation"].update(
            selection=selected[0].to_record(),
            roots={name: str(path) for name, path in case.generation_roots.items()},
        )
        case.record["native"] = copy.deepcopy(assessment.definition["native"])
        case.record["native"].update(
            selection=selected[1].to_record(),
            roots={name: str(path) for name, path in case.native_roots.items()},
        )
        case.record["stages"] = copy.deepcopy(assessment.definition["stages"])
        case.descriptor.write_bytes(_json(case.record))
        original_execute = case.execute

        def execute(spec, *, initial, handle, **kwargs):
            if spec.role == "agent":
                return original_execute(spec, initial=initial, handle=handle, **kwargs)

            def native_frame(frame):
                if frame["type"] == "file" and frame["path"] != "summary.json":
                    rows = [
                        json.loads(row)
                        for row in base64.b64decode(frame["data_base64"]).splitlines()
                    ]
                    for row in rows:
                        row.update(partition=[0, 1], distinct=2)
                        row.pop("score", None)
                        if frame["path"] == "scores.jsonl":
                            row.update(generation_scores=[4, 4], partition_scores=[4, 4], utility=4)
                    frame = frame | {
                        "data_base64": base64.b64encode(
                            b"".join(_json(row) + b"\n" for row in rows)
                        ).decode()
                    }
                return handle(frame)

            # Existing supplied-worker helpers inspect their receiving session.
            native_frame.__self__ = handle.__self__
            return replace(
                original_execute(spec, initial=initial, handle=native_frame, **kwargs),
                image_id=spec.image_id,
            )

        case.execute = execute

    @classmethod
    def compare(cls, *, plan=None, reference_hashes=None, diagnostic=False):
        try:
            return plain_comparison.compare_plain_references(
                cls.plan if plan is None else plan,
                expected_plan_sha256=cls.plan_hash,
                expected_assessment_report_sha256=cls.assessment_hash,
                expected_reference_report_sha256=cls.reference_hashes
                if reference_hashes is None
                else reference_hashes,
            )
        except plain_comparison.PlainComparisonError as error:
            if not diagnostic:
                raise
            # Locations only: never emit retained task, answer or request contents.
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
            print(json.dumps({"comparison_error_chain": chain}), file=sys.stderr, flush=True)
            raise

    @classmethod
    def snapshot(cls):
        roots = [cls.assessment.root, *(case.root for case in cls.baselines.values())]
        return (
            [
                (inventory(root), sorted(str(path.relative_to(root)) for path in root.rglob("*")))
                for root in roots
            ],
            cls.assessment.engine.physical_sends,
            [case.physical_sends for case in cls.baselines.values()],
        )

    @classmethod
    @contextmanager
    def passive(cls):
        real_connect, real_open = sqlite3.connect, Path.open

        def forbidden(*args, **kwargs):
            raise AssertionError(
                "passive comparison attempted a producer, key, SQL source or write"
            )

        def memory_only(path, *args, **kwargs):
            if path != ":memory:":
                forbidden()
            return real_connect(path, *args, **kwargs)

        def opened(path, mode="r", *args, **kwargs):
            if any(character in mode for character in "wax+"):
                forbidden()
            return real_open(path, mode, *args, **kwargs)

        with cls.assessment.f.h.readonly(), ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {}, clear=True))
            stack.enter_context(patch("sqlite3.connect", side_effect=memory_only))
            stack.enter_context(patch.object(Path, "open", opened))
            for target in (
                "buddha.baseline.run_baseline",
                "buddha.improver_assessment.run_improver_assessment",
                "buddha.improver_study.run_improver_study",
                "buddha.trial_fence.lease",
                "buddha.trial_fence.work",
                "buddha.native_pipeline._exclusive",
                "getpass.getpass",
                "socket.create_connection",
                "subprocess.Popen",
            ):
                stack.enter_context(patch(target, side_effect=forbidden))
            yield

    def check_original_complete_publications_produce_typed_paired_descriptive_outcomes(self):
        result, panel = self.result, self.result["analysis"]
        self.assertEqual(panel["status"], "complete")
        self.assertEqual(
            (
                panel["planned_buddha_sets"],
                panel["observed_buddha_sets"],
                panel["unique_reference_sets"],
            ),
            (6, 6, 4),
        )
        self.assertEqual([row["task_id"] for row in panel["prompts"]], [1, "final"])
        self.assertEqual([type(row["task_id"]) for row in panel["prompts"]], [int, str])
        self.assertNotIn("1", [row["task_id"] for row in panel["prompts"]])
        self.assertEqual(len(panel["buddha_measurements"]), 6)
        self.assertEqual(set(panel["reference_measurements"]), {"regenerate", "in-context"})
        for contrast in panel["contrasts"]:
            difference = {"starter": 1, "initial": 2, "evolved": 4}[contrast["role"]]
            self.assertEqual(
                contrast["metrics"]["utility"]["mean_difference"],
                {"numerator": difference, "denominator": 1},
            )
            self.assertEqual(
                contrast["metrics"]["distinct"]["mean_difference"],
                {"numerator": 0, "denominator": 1},
            )
        owners = result["actual_execution"]["owners"]
        self.assertEqual(len({owner["run_id"] for owner in owners}), len(owners))
        total = result["actual_execution"]["unique_original_execution"]
        expected_calls = self.assessment.authorities["final"].summary()["operation_count"] + sum(
            case.authority.summary()["operation_count"] for case in self.baselines.values()
        )
        self.assertEqual(total["operation_count"], expected_calls)
        self.assertEqual(total["tokens"]["known_operations"], expected_calls)
        development_calls = self.assessment_report["development_costs"]["totals"]["operation_count"]
        development = result["development_execution"]["summary"]
        self.assertEqual(development["operation_count"], development_calls)
        self.assertEqual(development["tokens"]["known_operations"], development_calls)
        self.assertEqual(
            result["combined_original_api_research"]["operation_count"],
            expected_calls + development_calls,
        )
        self.assertEqual(
            result["combined_original_api_research"]["tokens"]["known_operations"],
            expected_calls + development_calls,
        )
        self.assertIn("no significance", result["claim"])

    def check_sealed_native_output_corruption_is_refused_without_repair(self):
        case = self.baselines["regenerate"]
        seal = json.loads((case.directory / "completed/1.json").read_bytes())
        path = case.directory / seal["attempt"] / "artifacts/partitions.jsonl"
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"\n")
            before = self.snapshot()
            with self.passive(), self.assertRaises(plain_comparison.PlainComparisonError):
                self.compare()
            self.assertEqual(self.snapshot(), before)
        finally:
            path.write_bytes(original)

    def check_unbound_retrospective_plan_is_refused(self):
        retrospective = self.assessment.root / "retrospective-comparison.json"
        retrospective.write_bytes(self.plan.read_bytes())
        before = self.snapshot()
        try:
            with self.passive(), self.assertRaises(plain_comparison.PlainComparisonError):
                self.compare(plan=retrospective)
            self.assertEqual(self.snapshot(), before)
        finally:
            retrospective.unlink()

    def check_missing_original_publication_is_refused_without_continuation(self):
        path = self.baselines["in-context"].directory / "report.json"
        original = path.read_bytes()
        try:
            path.unlink()
            before = self.snapshot()
            with self.passive(), self.assertRaises(plain_comparison.PlainComparisonError):
                self.compare()
            self.assertEqual(self.snapshot(), before)
        finally:
            path.write_bytes(original)

    def test_original_comparison_and_passive_refusals(self):
        # One discovered method keeps hosted shards from rebuilding this fixture.
        for check in (
            self.check_original_complete_publications_produce_typed_paired_descriptive_outcomes,
            self.check_sealed_native_output_corruption_is_refused_without_repair,
            self.check_unbound_retrospective_plan_is_refused,
            self.check_missing_original_publication_is_refused_without_continuation,
        ):
            with self.subTest(check=check.__name__):
                check()


if __name__ == "__main__":
    unittest.main()
