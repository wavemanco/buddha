"""Fresh views reuse immutable validation; external bytes keep strict checks."""

import json
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import test_answers as fixtures

from buddha import answers, releases
from buddha.answers import Answers, TaskSet, _Artifact
from buddha.improvement_rule import ImprovementRule
from buddha.improver_analysis import ImproverAnalysisPlan
from buddha.policy_study import PolicyStudy
from buddha.source_screen import SourceScreen
from buddha.source_search import SourceSearchSpec, _WitnessTreatment
from buddha.validation_analysis import ValidationAnalysisPlan


class ValidatedArtifactViewTests(unittest.TestCase):
    def population(self):
        rows = [
            {
                "id": index,
                "prompt": "Synthetic task " + str(index),
                "details": {"tags": ["opaque", {"values": [index, True, None]}]},
            }
            for index in range(1000)
        ]
        dataset = fixtures.jsonl(rows)
        release = fixtures.AnswerArtifactTests("runTest").make_release(dataset)
        tasks = TaskSet.from_dataset(release, dataset)
        outputs = [{"task_id": row["id"], "answers": ["one", "two", "three"]} for row in rows]
        result = Answers.from_results(
            release,
            tasks,
            outputs,
            agent_sha256="d" * 64,
            metadata={"settings": {"values": ["original", {"nested": [1, 2]}]}},
        )
        return tasks, result

    def test_thousand_task_views_do_not_repeat_strict_input_validation(self):
        artifacts = self.population()
        self.assertEqual(len(artifacts[0].tasks), 1000)
        expected = [json.loads(artifact.to_bytes()) for artifact in artifacts]
        with (
            patch.object(answers, "_load", wraps=answers._load) as validation,
            patch.object(releases, "_json", wraps=releases._json) as serialization,
        ):
            views = [[artifact.to_record() for _ in range(10)] for artifact in artifacts]
        self.assertEqual(views, [[record] * 10 for record in expected])
        with self.subTest(work="strict decode"):
            self.assertEqual(validation.call_count, 0)
        with self.subTest(work="validation serialization"):
            self.assertEqual(serialization.call_count, 0)

    def test_nested_record_copies_preserve_native_bytes_and_frozen_identities(self):
        tasks, result = self.population()
        original = [(artifact.to_bytes(), artifact.fingerprint()) for artifact in (tasks, result)]
        native = result.native_bytes()
        first, second = result.to_record(), result.to_record()
        self.assertIsNot(first, second)
        self.assertIsNot(first["metadata"], second["metadata"])
        first["metadata"]["settings"]["values"][1]["nested"].clear()
        first["outputs"][0]["answers"].clear()
        first["tasks"]["tasks"][0]["prompt"] = "changed exposed prompt"
        task_view = tasks.to_record()
        task_view["selection"].reverse()
        task_view["tasks"][0]["prompt"] = "changed separate view"
        self.assertEqual(second, json.loads(result.to_bytes()))
        self.assertEqual(result.to_record(), second)
        self.assertEqual(result.native_bytes(), native)
        for artifact, (raw, fingerprint) in zip((tasks, result), original, strict=True):
            self.assertEqual(artifact.to_bytes(), raw)
            self.assertEqual(artifact.fingerprint(), fingerprint)
            self.assertEqual(type(artifact).from_bytes(raw), artifact)
            with self.assertRaises(FrozenInstanceError):
                artifact.data = b"{}"

    def test_every_artifact_constructor_rejects_untrusted_json_before_views_exist(self):
        classes = (
            _Artifact,
            TaskSet,
            Answers,
            PolicyStudy,
            SourceScreen,
            SourceSearchSpec,
            _WitnessTreatment,
            ImprovementRule,
            ImproverAnalysisPlan,
            ValidationAnalysisPlan,
        )
        invalid = {
            "duplicate key": b'{"value":1,"value":2}',
            "nonfinite": b'{"value":NaN}',
            "invalid UTF-8": b'{"value":"\xff"}',
            "nonobject": b"[]",
            "nonliteral bytes": bytearray(b"{}"),
            "oversized": b'{"value":"' + b"x" * releases.MAX_JSON_BYTES + b'"}',
        }
        for cls in classes:
            for reason, raw in invalid.items():
                with self.subTest(artifact=cls.__name__, reason=reason):
                    with self.assertRaises(releases.ReleaseError):
                        cls.from_bytes(raw)

    def test_derived_task_and_answer_tampering_still_rejects_new_construction(self):
        tasks, result = self.population()
        changed_tasks = tasks.to_record()
        changed_tasks["tasks"][0]["prompt"] = "not its frozen dataset"
        with self.assertRaises(releases.ReleaseError):
            TaskSet.from_bytes(releases._json(changed_tasks))
        for field, value in (("tasks_sha256", "0" * 64), ("outputs", [])):
            record = result.to_record()
            record[field] = value
            with self.subTest(field=field):
                with self.assertRaises(releases.ReleaseError):
                    Answers.from_bytes(releases._json(record))

    def test_base_artifact_views_preserve_already_validated_literal_bytes(self):
        raw = b' {"nested": [1, {"text": "literal"}]} '
        artifact = _Artifact.from_bytes(raw)
        before = artifact.fingerprint()
        first, second = artifact.to_record(), artifact.to_record()
        first["nested"][1]["text"] = "changed exposed text"
        self.assertEqual(second, {"nested": [1, {"text": "literal"}]})
        self.assertEqual(artifact.to_bytes(), raw)
        self.assertEqual(artifact.fingerprint(), before)


if __name__ == "__main__":
    unittest.main()
