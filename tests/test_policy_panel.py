"""Pre-answer masks bind reviewed typed coordinates, never generated outcomes."""

import copy
import hashlib
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_policy_study as study_fixtures

from buddha.answers import TaskSet
from buddha.policy_panel import PolicyPanelError, plan_panel
from buddha.policy_study import PolicyStudy
from buddha.releases import Release, _json

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "d" * 64


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture(categories=2, count=2):
    base = study_fixtures.PolicyStudyTests("runTest")
    base.setUp()
    for index, row in enumerate(base.rows):
        row["category"] = "Category-" + str(index % categories)
    base.reset_source()
    release = base.release.to_record()
    release["task"]["count"] = count
    release = Release.from_record(release)
    source = TaskSet.from_dataset(release, base.dataset)
    record = base.record
    record["source"] = source.to_record()
    record["split"]["release_sha256"] = source.release_sha256
    record["split"]["dataset_sha256"] = source.dataset_sha256
    selected = [row["key"] for row in base.rows[:categories]]
    record["split"]["partitions"] = {
        "development": [row["key"] for row in base.rows[:-2]],
        "validation": [base.rows[-2]["key"]],
        "final": [base.rows[-1]["key"]],
    }
    record["selected_ids"] = list(reversed(selected))
    study = PolicyStudy.from_bytes(_json(record))
    source_rows = {row["key"]: row for row in base.rows}
    review = {
        "format": "buddha.policy-study-source-review.v1",
        "source": {"dataset_sha256": source.dataset_sha256},
        "selected": [
            {
                "id": task.id,
                "category": source_rows[task.id]["category"],
                "prompt_sha256": sha(task.prompt.encode()),
            }
            for task in study.tasks.tasks
        ],
        "supplemental_panel": {
            "ids": selected,
            "generation_repeats": [index % 2 for index in range(categories)],
            "conditions": 4,
            "complete_answer_sets": 4 * categories,
            "answers": 4 * categories * count,
        },
    }
    return study, review


def intent_for(study):
    declaration = study.to_record()
    source = TaskSet.from_bytes(_json(declaration.pop("source")))
    return {
        "format": "buddha.policy-study-intent.v1",
        "protocol_sha256": PROTOCOL,
        "release": source.to_record()["release"],
        "study": declaration,
        "expected": {
            "release_sha256": source.release_sha256,
            "source_tasks_sha256": source.fingerprint(),
            "selected_tasks_sha256": study.tasks.fingerprint(),
            "study_sha256": study.fingerprint(),
            "arm_ids": [arm["arm_id"] for arm in study.arms],
            "cell_ids": [cell["cell_id"] for cell in study.schedule()],
        },
    }


class PolicyPanelTests(unittest.TestCase):
    def setUp(self):
        self.study, self.review = fixture()
        self.intent = intent_for(self.study)

    def plan(self, *, study=None, intent=None, review=None, **overrides):
        study = self.study if study is None else study
        intent_raw = _json(self.intent if intent is None else intent)
        review_raw = _json(self.review if review is None else review)
        arguments = {
            "intent_raw": intent_raw,
            "expected_intent_sha256": sha(intent_raw),
            "source_review_raw": review_raw,
            "expected_source_review_sha256": sha(review_raw),
            "expected_protocol_sha256": PROTOCOL,
        }
        arguments.update(overrides)
        return plan_panel(study, **arguments)

    def test_exact_vectors_sorted_full_labels_typed_ids_and_all_positions(self):
        result = self.plan()
        self.assertEqual(result["format"], "buddha.policy-panel-plan.v1")
        self.assertEqual(result["study_sha256"], self.study.fingerprint())
        self.assertEqual(result["tasks_sha256"], self.study.tasks.fingerprint())
        self.assertEqual(result["counts"], {"tasks": 2, "sets": 8, "positions": 16})
        self.assertEqual(
            result["input_sha256"],
            {
                "intent": sha(_json(self.intent)),
                "source_review": sha(_json(self.review)),
                "protocol": PROTOCOL,
            },
        )
        sets = result["sets"]
        self.assertEqual([row["id"] for row in sets], sorted(row["id"] for row in sets))
        expected = {
            (identifier, arm, repeat)
            for identifier, repeat in [(1, 0), ("1", 1)]
            for arm in range(4)
        }
        self.assertEqual(
            {(row["task_id"], row["arm_index"], row["generation_repeat"]) for row in sets},
            expected,
        )
        cells = {
            (c["arm_index"], c["generation_repeat"]): c["cell_id"] for c in self.study.schedule()
        }
        labels = set()
        for row in sets:
            vector = ["pol02-panel-v1", row["task_id"], row["arm_index"], row["generation_repeat"]]
            self.assertEqual(row["id"], sha(_json(vector)))
            self.assertRegex(row["id"], r"^[0-9a-f]{64}$")
            self.assertEqual(row["cell_id"], cells[row["arm_index"], row["generation_repeat"]])
            self.assertEqual({answer["position"] for answer in row["answers"]}, {0, 1})
            self.assertEqual(
                [a["id"] for a in row["answers"]], sorted(a["id"] for a in row["answers"])
            )
            labels.add(row["id"])
            for answer in row["answers"]:
                self.assertEqual(answer["id"], sha(_json([*vector, answer["position"]])))
                labels.add(answer["id"])
        self.assertEqual(len(labels), 24)
        self.assertEqual(
            result["rules"],
            {
                "hash_domain": "pol02-panel-v1",
                "labels": "full_lowercase_sha256",
                "set_order": "ascending_digest",
                "answer_order": "ascending_digest",
                "position_index_base": 0,
                "collision": "error",
            },
        )

    def test_six_category_ten_answer_fixture_has_24_sets_and_240_positions(self):
        study, review = fixture(categories=6, count=10)
        result = self.plan(study=study, intent=intent_for(study), review=review)
        self.assertEqual(result["counts"], {"tasks": 6, "sets": 24, "positions": 240})
        self.assertEqual(sum(len(row["answers"]) for row in result["sets"]), 240)
        self.assertNotIn(b"question", _json(result))
        self.assertNotIn(b"FINAL-SENTINEL", _json(result))

    def test_raw_byte_pins_are_external_and_checked_before_semantic_adoption(self):
        for overrides in (
            {"expected_intent_sha256": "0" * 64},
            {"expected_source_review_sha256": "0" * 64},
            {"expected_protocol_sha256": "0" * 64},
            {"intent_raw": _json(self.intent) + b"\n"},
            {"source_review_raw": _json(self.review) + b"\n"},
            {"expected_intent_sha256": "F" * 64},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(PolicyPanelError):
                self.plan(**overrides)

    def test_resealed_intent_must_match_complete_study_and_all_derived_identities(self):
        for key in (
            "study_sha256",
            "source_tasks_sha256",
            "selected_tasks_sha256",
            "arm_ids",
            "cell_ids",
        ):
            intent = copy.deepcopy(self.intent)
            intent["expected"][key] = [] if isinstance(intent["expected"][key], list) else "0" * 64
            with self.subTest(key=key), self.assertRaises(PolicyPanelError):
                self.plan(intent=intent)
        intent = copy.deepcopy(self.intent)
        intent["study"]["child_policy"]["instructions"] = "Changed treatment."
        with self.assertRaises(PolicyPanelError):
            self.plan(intent=intent)

    def test_resealed_review_cannot_change_dataset_selected_ids_category_or_prompt(self):
        variants = []
        review = copy.deepcopy(self.review)
        review["source"]["dataset_sha256"] = "0" * 64
        variants.append(review)
        for key, value in (
            ("id", "foreign"),
            ("category", "invented"),
            ("prompt_sha256", "0" * 64),
        ):
            review = copy.deepcopy(self.review)
            review["selected"][0][key] = value
            variants.append(review)
        review = copy.deepcopy(self.review)
        review["selected"].reverse()
        variants.append(review)
        for review in variants:
            with self.subTest(review=review), self.assertRaises(PolicyPanelError):
                self.plan(review=review)

    def test_panel_population_category_order_repeats_and_declared_counts_are_not_claims(self):
        variants = {
            "ids": [[1, 1], ["1", 1], [True, "1"], [1], [1, "f0"]],
            "generation_repeats": [[1, 0], [0, True], [0], [0, 2]],
            "conditions": [True, 3, 5],
            "complete_answer_sets": [True, 7, 9],
            "answers": [True, 15, 17],
        }
        for key, values in variants.items():
            for value in values:
                review = copy.deepcopy(self.review)
                review["supplemental_panel"][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(PolicyPanelError):
                    self.plan(review=review)

    def test_category_order_comes_from_literal_dataset_not_selected_or_source_view(self):
        record = self.study.to_record()
        source = TaskSet.from_bytes(_json(record["source"]))
        record["source"] = source.select([t.id for t in reversed(source.tasks)]).to_record()
        study = PolicyStudy.from_bytes(_json(record))
        other = self.plan(study=study, intent=intent_for(study))
        self.assertEqual(
            [(r["id"], r["task_id"], r["generation_repeat"]) for r in other["sets"]],
            [(r["id"], r["task_id"], r["generation_repeat"]) for r in self.plan()["sets"]],
        )

    def test_missing_or_invalid_literal_categories_fail_instead_of_inferred_groups(self):
        for value in (None, "", False):
            base = study_fixtures.PolicyStudyTests("runTest")
            base.setUp()
            for row in base.rows:
                row["category"] = value
            base.reset_source()
            study = base.study()
            with self.subTest(category=value), self.assertRaises(PolicyPanelError):
                self.plan(study=study, intent=intent_for(study))

    def test_collision_and_planned_position_ceiling_fail_before_expansion(self):
        with patch("buddha.policy_panel._label", return_value="a" * 64):
            with self.assertRaises(PolicyPanelError):
                self.plan()
        with (
            patch("buddha.policy_panel.MAX_PANEL_POSITIONS", 15),
            patch("buddha.policy_panel._label", side_effect=AssertionError("expanded")),
            self.assertRaises(PolicyPanelError),
        ):
            self.plan()

    def test_malformed_bounded_json_inputs_raise_only_typed_errors(self):
        malformed = [
            None,
            "{}",
            b"\xff",
            b"[]",
            b'{"x":1,"x":2}',
            b'{"x":NaN}',
            b'{"x":1e999}',
            b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}",
        ]
        for raw in malformed:
            for field in ("intent_raw", "source_review_raw"):
                with self.subTest(raw=type(raw), field=field), self.assertRaises(PolicyPanelError):
                    overrides = {field: raw}
                    if type(raw) is bytes:
                        overrides[
                            "expected_intent_sha256"
                            if field == "intent_raw"
                            else "expected_source_review_sha256"
                        ] = sha(raw)
                    self.plan(**overrides)
        with patch("buddha.policy_panel.MAX_JSON_BYTES", 1), self.assertRaises(PolicyPanelError):
            self.plan()
        with self.assertRaises(PolicyPanelError):
            self.plan(study={})

    def test_pure_result_is_fresh_and_contains_no_text_or_future_observation_claim(self):
        before = self.study.to_bytes(), copy.deepcopy(self.intent), copy.deepcopy(self.review)
        with (
            patch("builtins.open", side_effect=AssertionError("I/O")),
            patch.object(Path, "open", side_effect=AssertionError("I/O")),
            patch("socket.socket", side_effect=AssertionError("network")),
            patch("os.getenv", side_effect=AssertionError("environment")),
        ):
            first = self.plan()
        expected = copy.deepcopy(first)
        first["sets"][0]["answers"][0]["position"] = 99
        first["rules"]["collision"] = "invented"
        self.assertEqual(self.plan(), expected)
        self.assertEqual((self.study.to_bytes(), self.intent, self.review), before)
        for forbidden in ("prompt", "text", "missing", "available", "answers_sha256", "reviewer"):
            self.assertNotIn('"' + forbidden + '"', _json(expected).decode())

    def test_fresh_import_has_no_reader_execution_finance_or_legacy_dependency(self):
        script = """
import importlib.abc, sys
sys.path.insert(0, sys.argv[1])
blocked = {'buddha.policy_results', 'buddha.native_evaluation', 'buddha.doctor',
           'buddha.authorization', 'buddha.gateway', 'buddha.ledger', 'buddha.provider',
           'buddha.benchmark', 'buddha.evaluation', 'buddha.policy', 'buddha.splits',
           'openai', 'anthropic'}
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in blocked:
            raise AssertionError('forbidden dependency: ' + fullname)
sys.meta_path.insert(0, Block())
from buddha.policy_panel import plan_panel
assert callable(plan_panel)
"""
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, str(ROOT)],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
