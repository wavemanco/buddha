"""The study intent must reproduce its declared artifact before any live handoff."""

import copy
import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from buddha.answers import TaskSet
from buddha.policy_study import PolicyStudy
from buddha.releases import Release, ReleaseError, _json

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "docs/conformance/pol02-study-freeze.py"
build = runpy.run_path(str(HELPER))["build"]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PolicyIntentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.protocol = b"Frozen analysis: keep both native metrics and every occasion.\n"
        rows = [
            {"id": name, "prompt": "Literal task " + name}
            for name in ("d1", "d2", "v1", "v2", "f1", "f2")
        ]
        self.dataset = b"".join(_json(row) + b"\n" for row in rows)
        self.files = {
            "src/example.py": b"# Sealed data; this program must never execute.\n",
            "lock.txt": b"No external dependencies\n",
            "dataset.jsonl": self.dataset,
        }
        release = Release.from_record(
            {
                "format": "buddha.benchmark-release.v1",
                "benchmark": "synthetic",
                "release": "data-only-test",
                "upstream": {"url": "https://example.com/official", "revision": "a" * 40},
                "source": {name: sha(raw) for name, raw in self.files.items()},
                "dependency_lock": "lock.txt",
                "task": {
                    "dataset": "dataset.jsonl",
                    "id_field": "id",
                    "prompt_field": "prompt",
                    "answers_field": "generations",
                    "count": 10,
                },
                "commands": [{"module": "src.example", "argv": ["{artifacts}"]}],
                "artifacts": {
                    "answers": "generations.jsonl",
                    "results": ["scores.jsonl"],
                    "summary": "summary.json",
                },
                "requires": ["openai.chat-completions.v1"],
            }
        )
        source = TaskSet.from_dataset(release, self.dataset)
        self.study_record = {
            "format": "buddha.policy-study.v1",
            "split": {
                "release_sha256": release.fingerprint(),
                "dataset_sha256": sha(self.dataset),
                "partitions": {
                    "development": ["d1", "d2"],
                    "validation": ["v1", "v2"],
                    "final": ["f1", "f2"],
                },
                "families": [{"id": row["id"], "family": row["id"]} for row in rows],
            },
            "selected_ids": ["d2", "d1"],
            "child_policy": {
                "instructions": "Preserve the literal task.",
                "sampling": "regenerate",
            },
            "generation": {"provider": "openai", "model": "fixture", "max_output_tokens": 20},
            "generation_repeats": 2,
            "judge_occasions": 2,
            "execution_order": [
                {"arm": arm, "repeat": repeat}
                for repeat, arms in ((0, range(4)), (1, reversed(range(4))))
                for arm in arms
            ],
        }
        self.study = PolicyStudy.from_bytes(
            _json(self.study_record | {"source": source.to_record()})
        )
        self.intent = {
            "format": "buddha.policy-study-intent.v1",
            "protocol_sha256": sha(self.protocol),
            "release": release.to_record(),
            "study": self.study_record,
            "expected": {
                "release_sha256": release.fingerprint(),
                "source_tasks_sha256": source.fingerprint(),
                "selected_tasks_sha256": self.study.tasks.fingerprint(),
                "study_sha256": self.study.fingerprint(),
                "arm_ids": [arm["arm_id"] for arm in self.study.arms],
                "cell_ids": [cell["cell_id"] for cell in self.study.schedule()],
            },
        }

    def test_reconstructs_exact_full_source_study_without_mutating_inputs(self):
        original = _json(self.intent)
        actual = build(original, self.dataset, self.protocol)
        self.assertEqual(actual.to_bytes(), self.study.to_bytes())
        self.assertEqual(_json(self.intent), original)
        self.assertEqual([task.id for task in actual.tasks.tasks], ["d2", "d1"])
        self.assertEqual(len(actual.schedule()), 8)

    def test_rejects_changed_protocol_dataset_and_expected_artifact(self):
        for dataset, protocol in (
            (self.dataset + b" ", self.protocol),
            (self.dataset, self.protocol + b" "),
        ):
            with self.subTest(dataset=sha(dataset), protocol=sha(protocol)):
                with self.assertRaises(ReleaseError):
                    build(_json(self.intent), dataset, protocol)
        for field in self.intent["expected"]:
            changed = copy.deepcopy(self.intent)
            changed["expected"][field] = [] if field.endswith("ids") else "0" * 64
            with self.subTest(field=field), self.assertRaises(ReleaseError):
                build(_json(changed), self.dataset, self.protocol)

    def test_rejects_semantically_valid_but_unregistered_factors_order_and_population(self):
        for field, replacement in (
            ("child_policy", {"instructions": "A different policy.", "sampling": "regenerate"}),
            ("selected_ids", ["d1", "d2"]),
            ("judge_occasions", 3),
            ("execution_order", list(reversed(self.study_record["execution_order"]))),
            ("generation", {"provider": "openai", "model": "other", "max_output_tokens": 20}),
        ):
            changed = copy.deepcopy(self.intent)
            changed["study"][field] = replacement
            with self.subTest(field=field), self.assertRaises(ReleaseError):
                build(_json(changed), self.dataset, self.protocol)

    def test_closed_intent_schema_rejects_supplied_source_duplicate_keys_and_boolean_counts(self):
        records = []
        for key, value in (("source", {}), ("generation_repeats", True)):
            changed = copy.deepcopy(self.intent)
            changed["study"][key] = value
            records.append(_json(changed))
        changed = copy.deepcopy(self.intent)
        changed["grant"] = "not an allocation"
        records.append(_json(changed))
        records.append(_json(self.intent).replace(b'"format":', b'"format":null,"format":', 1))
        for raw in records:
            with self.subTest(raw=sha(raw)), self.assertRaises(ReleaseError):
                build(raw, self.dataset, self.protocol)

    def test_protocol_boundary_rejects_nonbytes(self):
        for value in (None, self.protocol.decode(), bytearray(self.protocol)):
            with self.subTest(type=type(value)), self.assertRaises(ReleaseError):
                build(_json(self.intent), self.dataset, value)

    def test_registered_study_keeps_reviewed_population_instrument_and_protocol_joins(self):
        intent = json.loads((ROOT / "docs/conformance/pol02-study-intent.json").read_bytes())
        review = json.loads((ROOT / "docs/conformance/pol02-study-source-review.json").read_bytes())
        protocol = (ROOT / "docs/POLICY-COMPARISON.md").read_bytes()
        self.assertEqual(intent["protocol_sha256"], sha(protocol))
        release = Release.from_record(intent["release"])
        self.assertEqual(release.fingerprint(), intent["expected"]["release_sha256"])
        self.assertEqual(release.to_record()["upstream"]["revision"], review["source"]["revision"])
        self.assertEqual(
            release.to_record()["source"]["data/curated.jsonl"],
            review["source"]["dataset_sha256"],
        )
        record = intent["study"]
        self.assertEqual(record["generation_repeats"], 2)
        self.assertEqual(record["judge_occasions"], 2)
        self.assertEqual(release.to_record()["task"]["count"], 10)
        self.assertEqual(record["generation"]["model"], "gpt-5.6-luna")
        self.assertEqual(record["generation"]["max_output_tokens"], 4096)
        self.assertEqual(sha(_json(record["child_policy"])), intent["expected"]["arm_ids"][2])
        self.assertEqual(
            record["selected_ids"],
            [f"curated-{n}" for n in (0, 47, 97, 15, 20, 26, 33, 30, 50, 71, 65, 86)],
        )
        rows = {row["id"]: row for row in review["rows"]}
        self.assertEqual(len(rows), 100)
        self.assertEqual(
            {row["id"]: row["family"] for row in record["split"]["families"]},
            {name: row["accepted_custody_block"] for name, row in rows.items()},
        )
        self.assertEqual(
            len({rows[name]["accepted_custody_block"] for name in record["selected_ids"]}), 12
        )
        for category in {row["category"] for row in rows.values()}:
            self.assertEqual(
                sum(rows[name]["category"] == category for name in record["selected_ids"]), 2
            )
        self.assertTrue(
            set(review["known_outcome_exposure"]["family_closure"])
            <= set(record["split"]["partitions"]["development"])
        )
        commands = release.to_record()["commands"]
        self.assertNotIn("--seed", commands[0]["argv"])
        self.assertEqual(
            commands[0]["argv"][commands[0]["argv"].index("--judge-model") + 1], "gpt-5.6-luna"
        )
        self.assertEqual(
            commands[1]["argv"][commands[1]["argv"].index("--judge-model") + 1], "claude-opus-5"
        )
        self.assertEqual(
            commands[1]["argv"][commands[1]["argv"].index("--fallback-judge") + 1],
            "claude-sonnet-5",
        )
        self.assertEqual(
            review["supplemental_panel"]["ids"],
            [f"curated-{n}" for n in (0, 20, 33, 47, 71, 97)],
        )

    def test_cli_checks_every_selected_source_and_refuses_to_overwrite_artifact(self):
        source = self.root / "official"
        for name, raw in self.files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        intent, protocol, output = (
            self.root / name for name in ("intent.json", "protocol.md", "study.json")
        )
        intent.write_bytes(_json(self.intent))
        protocol.write_bytes(self.protocol)
        command = [
            sys.executable,
            "-B",
            str(HELPER),
            "--intent",
            str(intent),
            "--protocol",
            str(protocol),
            "--source",
            str(source),
        ]
        checked = subprocess.run(command, capture_output=True, check=False, timeout=30)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["study_sha256"], self.study.fingerprint())
        self.assertFalse(output.exists())
        written = subprocess.run(
            [*command, "--output", str(output)], capture_output=True, check=False, timeout=30
        )
        self.assertEqual(written.returncode, 0, written.stderr)
        self.assertEqual(output.read_bytes(), self.study.to_bytes())
        refused = subprocess.run(
            [*command, "--output", str(output)], capture_output=True, check=False, timeout=30
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn(b"output", refused.stderr)
        self.assertEqual(output.read_bytes(), self.study.to_bytes())
        for name in ("hidden.txt:stream", "trailing.", "trailing ", "CON"):
            with self.subTest(output=name):
                unsafe = subprocess.run(
                    [*command, "--output", str(self.root / name)],
                    capture_output=True,
                    check=False,
                    timeout=30,
                )
                self.assertNotEqual(unsafe.returncode, 0)
                self.assertIn(b"output", unsafe.stderr)
                self.assertFalse((self.root / name.split(":")[0]).exists())
        (source / "src/example.py").write_bytes(b"changed source")
        changed = subprocess.run(command, capture_output=True, check=False, timeout=30)
        self.assertNotEqual(changed.returncode, 0)
        self.assertNotIn(b"checked", changed.stdout)


if __name__ == "__main__":
    unittest.main()
