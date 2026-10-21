"""Saved anchored generation, rather than judging success, controls panel custody."""

import copy
import hashlib
import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_agent_run as agent_fixtures
import test_policy_results as result_fixtures

from buddha import baseline, search_evidence
from buddha.answers import TaskSet
from buddha.policy_panel import plan_panel
from buddha.policy_panel_read import PolicyPanelReadError, materialize_panel
from buddha.policy_run import PolicyRunError
from buddha.releases import _json, inventory


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PolicyPanelReadTests(unittest.TestCase):
    def setUp(self):
        original = agent_fixtures.AgentSessionTests.configure_tasks

        def categorized(agent, count=2):
            rows = [json.loads(line) for line in agent.dataset.splitlines()]
            for row in rows:
                row["category"] = "writing" if row["qid"] == "1" else "control"
            agent.dataset = b"".join(_json(row) + b"\n" for row in rows)
            (agent.fixture.roots["official"] / "data/tasks.jsonl").write_bytes(agent.dataset)
            agent.fixture.release_record["source"] = inventory(agent.fixture.roots["official"])
            original(agent, count)

        self.saved = result_fixtures.PolicyResultsTests("runTest")
        with patch.object(agent_fixtures.AgentSessionTests, "configure_tasks", categorized):
            self.saved.setUp()
        self.addCleanup(self.saved.doCleanups)
        self.f = self.saved.fixture
        self.root = self.saved.root
        self.f.prepare()
        study = self.f.study
        source = TaskSet.from_bytes(_json(study.to_record()["source"]))
        self.review = {
            "format": "buddha.policy-study-source-review.v1",
            "source": {"dataset_sha256": source.dataset_sha256},
            "selected": [
                {
                    "id": task.id,
                    "category": "writing" if task.id == "1" else "control",
                    "prompt_sha256": sha(task.prompt.encode()),
                }
                for task in study.tasks.tasks
            ],
            "supplemental_panel": {
                "ids": [1, "1"],
                "generation_repeats": [0, 1],
                "conditions": 4,
                "complete_answer_sets": 8,
                "answers": 16,
            },
        }
        self.review_path = self.root / "source-review.json"
        self.review_path.write_bytes(_json(self.review))
        self.plan = plan_panel(
            study,
            intent_raw=self.saved.intent.read_bytes(),
            expected_intent_sha256=self.saved.expected_intent,
            source_review_raw=self.review_path.read_bytes(),
            expected_source_review_sha256=sha(self.review_path.read_bytes()),
            expected_protocol_sha256=self.saved.expected_protocol,
        )
        rule = "SYNTHETIC official equivalence rule; no benchmark semantic claim."
        rubric = self.saved.protocol.read_text(encoding="utf-8")
        self.materials = {
            "format": "buddha.policy-panel-review.v1",
            "release_sha256": source.release_sha256,
            "protocol_sha256": self.saved.expected_protocol,
            "rule": {
                "text": rule,
                "sha256": sha(rule.encode()),
                "upstream_revision": source.to_record()["release"]["upstream"]["revision"],
            },
            "rubric": {"text": rubric, "protocol_start": 0, "protocol_end": len(rubric.encode())},
        }

    @contextmanager
    def source_only(self):
        with self.saved.readonly():
            original, binary = Path.open, search_evidence._open_binary

            def guard(path):
                if path.name in {
                    "partitions.jsonl",
                    "scores.jsonl",
                    "summary.json",
                    "native-answers.jsonl",
                }:
                    raise AssertionError("panel opened an official judging outcome")

            def opened(path, *args, **kwargs):
                guard(path)
                return original(path, *args, **kwargs)

            @contextmanager
            def opened_binary(path):
                guard(path)
                with binary(path) as stream:
                    yield stream

            with (
                patch.object(Path, "open", opened),
                patch.object(search_evidence, "_open_binary", opened_binary),
            ):
                yield

    def read(self, **changes):
        plan_raw, materials_raw = _json(self.plan), _json(self.materials)
        arguments = {
            "intent": self.saved.intent,
            "protocol": self.saved.protocol,
            "source_review": self.review_path,
            "expected_intent_sha256": self.saved.expected_intent,
            "expected_protocol_sha256": self.saved.expected_protocol,
            "expected_source_review_sha256": sha(self.review_path.read_bytes()),
            "authorization": self.f.authority.path,
            "plan_raw": plan_raw,
            "expected_plan_sha256": sha(plan_raw),
            "review_materials_raw": materials_raw,
            "expected_review_materials_sha256": sha(materials_raw),
        }
        arguments.update(changes)
        before = self.saved.files()
        sends = self.f.fixture.physical_sends
        try:
            with self.source_only():
                return materialize_panel(self.f.directory, **arguments)
        finally:
            self.assertEqual(self.saved.files(), before)
            self.assertEqual(self.f.fixture.physical_sends, sends)

    def stop_after_generation(self, *, unknown=False):
        self.f.fixture.timeout_native_once = unknown
        self.f.fixture.fail_native_once = not unknown
        result = self.f.run_study()
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse((self.f.directory / "report.json").exists())
        self.assertTrue((self.f.directory / "cells/0/baseline/completed/0.json").is_file())
        return result

    def test_anchored_generation_survives_judge_failure_without_final_publication(self):
        self.stop_after_generation()
        result = self.read()
        packet, private = result["packet"], result["private"]
        self.assertEqual(packet["format"], "buddha.policy-panel-packet.v1")
        self.assertEqual(set(packet), {"format", "rule", "rubric", "items"})
        self.assertEqual(len(packet["items"]), 1)
        self.assertEqual(private["status"], "incomplete")
        self.assertEqual(
            private["coverage"],
            {
                "planned_sets": 8,
                "available_sets": 1,
                "unavailable_sets": 7,
                "planned_positions": 16,
                "available_positions": 2,
                "unavailable_positions": 14,
            },
        )
        self.assertEqual(private["packet_sha256"], sha(_json(packet)))
        self.assertEqual(len(private["sets"]), 8)
        self.assertEqual(sum(len(row["answers"]) for row in private["sets"]), 16)
        item = packet["items"][0]
        self.assertEqual(set(item), {"id", "prompt", "answers"})
        self.assertTrue(all(set(answer) == {"id", "text"} for answer in item["answers"]))
        planned = next(row for row in self.plan["sets"] if row["id"] == item["id"])
        base = self.f.directory / "cells/0/baseline"
        seal = json.loads((base / "completed/0.json").read_bytes())
        answers_path = base / seal["attempt"] / "answers.json"
        source = json.loads(answers_path.read_bytes())
        outputs = {row["task_id"]: row["answers"] for row in source["outputs"]}
        self.assertEqual(
            item["answers"],
            [
                {"id": answer["id"], "text": outputs[planned["task_id"]][answer["position"]]}
                for answer in planned["answers"]
            ],
        )
        binding = next(row for row in private["sets"] if row["id"] == item["id"])["binding"]
        self.assertEqual(binding["answers_file_sha256"], sha(answers_path.read_bytes()))

    def test_unknown_native_liability_does_not_hide_complete_generation_or_mutate_holds(self):
        self.stop_after_generation(unknown=True)
        self.assertGreater(self.f.authority.summary()["reserved_microusd"], 0)
        self.assertEqual(len(self.read()["packet"]["items"]), 1)

    def test_prepared_unsealed_generation_stays_private_missing_without_padding(self):
        result = self.read()
        self.assertEqual(result["packet"]["items"], [])
        self.assertEqual(result["private"]["coverage"]["available_sets"], 0)
        self.assertTrue(all(row["binding"] is None for row in result["private"]["sets"]))

    def test_original_plan_and_materials_pins_reject_tampering(self):
        for name in (
            "expected_plan_sha256",
            "expected_review_materials_sha256",
            "expected_intent_sha256",
            "expected_protocol_sha256",
            "expected_source_review_sha256",
        ):
            with self.subTest(name=name), self.assertRaises(PolicyPanelReadError):
                self.read(**{name: "0" * 64})
        changed = copy.deepcopy(self.plan)
        changed["sets"][0]["answers"][0]["position"] = 1
        raw = _json(changed)
        with self.assertRaises(PolicyPanelReadError):
            self.read(plan_raw=raw, expected_plan_sha256=sha(raw))

    def test_rule_release_rubric_slice_and_protocol_bindings_cannot_drift(self):
        for field in ("release_sha256", "protocol_sha256"):
            changed = copy.deepcopy(self.materials)
            changed[field] = "0" * 64
            raw = _json(changed)
            with self.subTest(field=field), self.assertRaises(PolicyPanelReadError):
                self.read(review_materials_raw=raw, expected_review_materials_sha256=sha(raw))
        for part, field, value in (
            ("rule", "sha256", "0" * 64),
            ("rule", "upstream_revision", "different"),
            ("rubric", "protocol_end", True),
            ("rubric", "protocol_start", 1),
            ("rubric", "text", "Unregistered rule"),
        ):
            changed = copy.deepcopy(self.materials)
            changed[part][field] = value
            raw = _json(changed)
            with self.subTest(part=part, field=field), self.assertRaises(PolicyPanelReadError):
                self.read(review_materials_raw=raw, expected_review_materials_sha256=sha(raw))

    def test_anchored_missing_or_corrupt_seal_is_invalid_not_missing_generation(self):
        self.stop_after_generation()
        path = self.f.directory / "cells/0/baseline/completed/0.json"
        raw = path.read_bytes()
        for changed in (b"{}", None):
            with self.subTest(changed=changed):
                if changed is None:
                    path.unlink()
                else:
                    path.write_bytes(changed)
                try:
                    with self.assertRaises(PolicyPanelReadError):
                        self.read()
                finally:
                    path.write_bytes(raw)

    def test_source_control_tampering_and_foreign_authority_reject(self):
        self.stop_after_generation()
        path = self.f.directory / "cells/0/generation.json"
        raw = path.read_bytes()
        changed = json.loads(raw)
        changed["config"]["instructions"] = "different treatment"
        path.write_bytes(_json(changed))
        try:
            with self.assertRaises(PolicyPanelReadError):
                self.read()
        finally:
            path.write_bytes(raw)
        with self.assertRaises(PolicyPanelReadError):
            self.read(authorization=self.root / "baseline-authorization.sqlite3")

    def test_valid_c1_is_available_even_before_native_cache_export_or_any_judging_owner(self):
        original = baseline._same_or_write

        def fail_export(path, raw):
            if path.name == "native-answers.jsonl":
                raise OSError("synthetic export stop after anchored stage0")
            return original(path, raw)

        with (
            patch.object(baseline, "_same_or_write", side_effect=fail_export),
            self.assertRaises(PolicyRunError),
        ):
            self.f.run_study()
        base = self.f.directory / "cells/0/baseline"
        self.assertTrue((base / "completed/0.json").exists())
        self.assertFalse((base / "native-answers.jsonl").exists())
        self.assertFalse((base / "owners/1").exists())
        self.assertEqual(len(self.read()["packet"]["items"]), 1)

    def test_private_missing_reason_changes_do_not_change_empty_reviewer_bytes(self):
        before = self.read()
        self.f.fixture.fail_generation_once = True
        stopped = self.f.run_study()
        self.assertEqual(stopped["status"], "incomplete")
        after = self.read()
        self.assertEqual(_json(before["packet"]), _json(after["packet"]))
        self.assertNotEqual(
            [row["reason"] for row in before["private"]["sets"]],
            [row["reason"] for row in after["private"]["sets"]],
        )
        self.assertTrue(all(row["binding"] is None for row in after["private"]["sets"]))

    def test_literal_effective_placeholders_and_truncation_survive(self):
        original = self.f.fixture.agent.response
        literals = iter(
            [
                original("  snow 雪\r\n"),
                original("[refused]"),
                original("[empty]"),
                original("unfinished", finish="length"),
            ]
        )
        with patch.object(
            self.f.fixture.agent, "response", side_effect=lambda: next(literals, original())
        ):
            self.stop_after_generation()
        item = self.read()["packet"]["items"][0]
        self.assertEqual({answer["text"] for answer in item["answers"]}, {"[empty]", "unfinished"})

    def test_literal_effective_whitespace_and_unicode_are_not_changed_by_materialization(self):
        original = self.f.fixture.agent.response
        with patch.object(self.f.fixture.agent, "response", return_value=original("  snow 雪\r\n")):
            self.stop_after_generation()
        base = self.f.directory / "cells/0/baseline"
        seal = json.loads((base / "completed/0.json").read_bytes())
        raw = json.loads((base / seal["attempt"] / "answers.json").read_bytes())
        effective = {text for row in raw["outputs"] for text in row["answers"]}
        actual = {answer["text"] for answer in self.read()["packet"]["items"][0]["answers"]}
        self.assertEqual(actual, effective)
        self.assertEqual(actual, {"  snow 雪\r\n"})
        self.assertTrue(all("雪" in text for text in actual))

    def test_complete_panel_uses_all_precommitted_sets_and_unchanged_labels(self):
        self.assertEqual(self.f.run_study()["status"], "complete")
        result = self.read()
        self.assertEqual(result["private"]["status"], "complete")
        self.assertEqual(result["private"]["coverage"]["available_sets"], 8)
        self.assertEqual(result["private"]["coverage"]["available_positions"], 16)
        self.assertEqual(
            [row["id"] for row in result["packet"]["items"]],
            [row["id"] for row in self.plan["sets"]],
        )
        self.assertTrue(all(len(row["answers"]) == 2 for row in result["packet"]["items"]))


if __name__ == "__main__":
    unittest.main()
