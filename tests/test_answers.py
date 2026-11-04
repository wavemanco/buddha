"""Release-driven text artifacts preserve poor answers without running an agent."""

import copy
import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from buddha.answers import Answers, Task, TaskSet
from buddha.releases import Release, ReleaseError


def encoded(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()


def jsonl(rows):
    return b"".join(encoded(row) + b"\n" for row in rows)


class AnswerArtifactTests(unittest.TestCase):
    def setUp(self):
        self.dataset = jsonl(
            [
                {"id": "b", "prompt": "Reply with one digit.", "category": "control"},
                {"id": "a", "prompt": "Write five sentences.", "category": "creative"},
            ]
        )
        self.release = self.make_release(self.dataset)
        self.tasks = TaskSet.from_dataset(self.release, self.dataset)
        self.outputs = [
            {"task_id": "b", "answers": ["", "[refused]", "{malformed JSON"]},
            {"task_id": "a", "answers": ["same plot", "same plot", " one sentence\n"]},
        ]
        self.metadata = {"model": "frozen-generator", "settings": {"values": [1, True, None]}}

    def make_release(self, dataset, *, second=False, **changes):
        dataset_path = "population/new.jsonl" if second else "data/tasks.jsonl"
        record = {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "fixture",
            "release": "second" if second else "first",
            "upstream": {"url": "https://example.org/official", "revision": "a" * 40},
            "source": {
                "src/evaluate.py": "b" * 64,
                "uv.lock": "c" * 64,
                dataset_path: hashlib.sha256(dataset).hexdigest(),
            },
            "dependency_lock": "uv.lock",
            "task": {
                "dataset": dataset_path,
                "id_field": "task_id" if second else "id",
                "prompt_field": "text" if second else "prompt",
                "answers_field": "responses" if second else "generations",
                "count": 2 if second else 3,
            },
            "commands": [{"module": "src.evaluate", "argv": ["--eval-dir", "{artifacts}"]}],
            "artifacts": {
                "answers": "new/answers.jsonl" if second else "generations.jsonl",
                "results": ["new/rows.jsonl" if second else "v1/rows.jsonl"],
                "summary": "new/summary.json" if second else "v1/summary.json",
            },
            "requires": ["ordered-text.v1"],
        }
        return Release.from_record(record | changes)

    def answers(self, **changes):
        values = {
            "agent_sha256": "d" * 64,
            "metadata": self.metadata,
        }
        return Answers.from_results(self.release, self.tasks, self.outputs, **(values | changes))

    def test_tasks_are_literal_ordered_and_bound_to_exact_source(self):
        self.assertEqual([task.id for task in self.tasks.tasks], ["b", "a"])
        self.assertEqual(self.tasks.tasks[0], Task("b", "Reply with one digit.", 3))
        self.assertEqual(self.tasks.release_sha256, self.release.fingerprint())
        self.assertEqual(self.tasks.dataset_sha256, hashlib.sha256(self.dataset).hexdigest())
        self.assertEqual(TaskSet.from_bytes(self.tasks.to_bytes()), self.tasks)
        with self.assertRaises(FrozenInstanceError):
            self.tasks.tasks[0].prompt = "altered"

    def test_poor_duplicate_empty_refused_and_malformed_answers_reach_native_payload(self):
        answers = self.answers()
        rows = [json.loads(line) for line in answers.native_bytes().splitlines()]
        self.assertEqual([row["id"] for row in rows], ["b", "a"])
        self.assertEqual(rows[0]["generations"], self.outputs[0]["answers"])
        self.assertEqual(rows[1]["generations"], self.outputs[1]["answers"])
        self.assertEqual(rows[0]["prompt"], "Reply with one digit.")
        self.assertEqual(rows[1]["prompt"], "Write five sentences.")
        self.assertEqual(rows[0]["model"], "frozen-generator")
        self.assertEqual(rows[0]["category"], "control")
        self.assertEqual(rows[1]["category"], "creative")
        self.assertEqual(rows[1]["settings"], self.metadata["settings"])
        self.assertTrue(answers.native_bytes().endswith(b"\n"))

    def test_same_code_supports_new_count_schema_and_artifact_paths(self):
        dataset = jsonl([{"task_id": "new", "text": "Return a word."}])
        release = self.make_release(dataset, second=True)
        tasks = TaskSet.from_dataset(release, dataset)
        answers = Answers.from_results(
            release,
            tasks,
            [{"task_id": "new", "answers": ["first", "first"]}],
            agent_sha256="d" * 64,
            metadata={"model": "frozen-generator"},
        )
        self.assertEqual(tasks.tasks[0].count, 2)
        self.assertEqual(
            json.loads(answers.native_bytes()),
            {
                "task_id": "new",
                "text": "Return a word.",
                "responses": ["first", "first"],
                "model": "frozen-generator",
            },
        )
        self.assertEqual(
            answers.to_record()["agent_sha256"], self.answers().to_record()["agent_sha256"]
        )

    def test_selected_population_keeps_full_official_source_identity(self):
        selected = self.tasks.select(["a"])
        self.assertEqual([task.id for task in selected.tasks], ["a"])
        self.assertEqual(selected.dataset_sha256, self.tasks.dataset_sha256)
        self.assertEqual(selected.release_sha256, self.tasks.release_sha256)
        self.assertEqual(
            selected.to_record()["dataset_base64"], self.tasks.to_record()["dataset_base64"]
        )
        self.assertEqual(selected.to_record()["selection"], ["a"])
        self.assertNotEqual(selected.fingerprint(), self.tasks.fingerprint())
        self.assertEqual(TaskSet.from_bytes(selected.to_bytes()), selected)
        self.assertEqual(set(selected.tasks[0].to_record()), {"id", "prompt", "count"})
        answers = Answers.from_results(
            self.release,
            selected,
            [self.outputs[1]],
            agent_sha256="d" * 64,
            metadata={"model": "frozen-generator"},
        )
        self.assertEqual(json.loads(answers.native_bytes())["id"], "a")
        with self.assertRaises(ReleaseError):
            Answers.from_results(
                self.release,
                selected,
                self.outputs,
                agent_sha256="d" * 64,
                metadata={},
            )

    def test_explicit_selection_order_is_part_of_identity(self):
        reversed_tasks = self.tasks.select(["a", "b"])
        self.assertEqual([task.id for task in reversed_tasks.tasks], ["a", "b"])
        self.assertEqual(reversed_tasks.dataset_sha256, self.tasks.dataset_sha256)
        self.assertNotEqual(reversed_tasks.fingerprint(), self.tasks.fingerprint())
        outputs = list(reversed(self.outputs))
        answers = Answers.from_results(
            self.release, reversed_tasks, outputs, agent_sha256="d" * 64, metadata={}
        )
        self.assertEqual(
            [json.loads(line)["id"] for line in answers.native_bytes().splitlines()], ["a", "b"]
        )

    def test_empty_unknown_duplicate_and_invalid_selected_ids_are_rejected(self):
        for selected in ([], ["missing"], ["a", "a"], "a", [True], [None], [1.0], [1]):
            with self.subTest(selected=selected), self.assertRaises(ReleaseError):
                self.tasks.select(selected)

    def test_integer_and_string_ids_remain_distinct_without_boolean_aliases(self):
        dataset = jsonl([{"id": 1, "prompt": "numeric"}, {"id": "1", "prompt": "string"}])
        release = self.make_release(dataset)
        tasks = TaskSet.from_dataset(release, dataset).select(["1", 1])
        self.assertEqual([task.id for task in tasks.tasks], ["1", 1])
        outputs = [
            {"task_id": "1", "answers": ["s"] * 3},
            {"task_id": 1, "answers": ["n"] * 3},
        ]
        answers = Answers.from_results(release, tasks, outputs, agent_sha256="d" * 64, metadata={})
        rows = [json.loads(line) for line in answers.native_bytes().splitlines()]
        self.assertEqual([type(row["id"]) for row in rows], [str, int])
        outputs[1]["task_id"] = True
        with self.assertRaises(ReleaseError):
            Answers.from_results(release, tasks, outputs, agent_sha256="d" * 64, metadata={})

    def test_original_row_metadata_and_paraphrases_survive_selected_native_export(self):
        rows = [json.loads(line) for line in self.dataset.splitlines()]
        rows[0]["prompt_paraphrases"] = ["one alternative", "another alternative"]
        rows[1]["prompt_paraphrases"] = ["a different prompt"]
        rows[1]["nested"] = {"unchanged": [None, False, {"literal": "value"}]}
        dataset = jsonl(rows)
        release = self.make_release(dataset)
        tasks = TaskSet.from_dataset(release, dataset).select(["a", "b"])
        answers = Answers.from_results(
            release,
            tasks,
            list(reversed(self.outputs)),
            agent_sha256="d" * 64,
            metadata={"model": "frozen-generator"},
        )
        native = [json.loads(line) for line in answers.native_bytes().splitlines()]
        for original, exported in zip(reversed(rows), native, strict=True):
            for name, value in original.items():
                self.assertEqual(exported[name], value)
        with self.assertRaises(ReleaseError):
            Answers.from_results(
                release,
                tasks,
                list(reversed(self.outputs)),
                agent_sha256="d" * 64,
                metadata={"prompt_paraphrases": ["silently replaced"]},
            )

    def test_artifacts_are_deeply_immutable_canonical_and_repeatable(self):
        answers = self.answers()
        before = answers.to_bytes()
        native = answers.native_bytes()
        self.metadata["settings"]["values"].append("mutated")
        self.outputs[0]["answers"][0] = "mutated"
        exposed = answers.to_record()
        exposed["metadata"]["settings"]["values"].clear()
        exposed["outputs"][0]["answers"].clear()
        exposed_tasks = self.tasks.to_record()
        exposed_tasks["tasks"][0]["prompt"] = "mutated"
        self.assertEqual(answers.to_bytes(), before)
        self.assertEqual(answers.native_bytes(), native)
        self.assertEqual(Answers.from_bytes(before), answers)
        self.assertEqual(TaskSet.from_bytes(self.tasks.to_bytes()), self.tasks)
        with self.assertRaises(FrozenInstanceError):
            answers.data = b"changed"

    def test_native_bytes_reuses_the_validated_immutable_conversion(self):
        from buddha.answers import _native

        original = self.answers()
        expected = original.native_bytes()
        noncanonical = json.dumps(original.to_record(), indent=2).encode()
        self.assertNotEqual(noncanonical, original.to_bytes())
        with (
            patch("buddha.answers._native", wraps=_native) as convert,
            patch.object(TaskSet, "from_bytes", wraps=TaskSet.from_bytes) as parse_tasks,
        ):
            answers = Answers.from_bytes(noncanonical)
            self.assertEqual(answers.native_bytes(), expected)
            exposed = answers.to_record()
            exposed["outputs"][0]["answers"].clear()
            exposed["tasks"]["tasks"][0]["prompt"] = "mutated"
            exposed["metadata"]["settings"]["values"].clear()
            self.assertEqual(answers.native_bytes(), expected)
            self.assertEqual(answers.to_bytes(), original.to_bytes())
            self.assertEqual(answers.fingerprint(), original.fingerprint())
            self.assertEqual(answers.to_record(), original.to_record())
            self.assertEqual(convert.call_count, 1)
            self.assertEqual(parse_tasks.call_count, 1)

    def test_population_order_source_agent_metadata_and_answer_changes_change_identity(self):
        baseline = self.answers().fingerprint()
        self.assertNotEqual(self.answers(agent_sha256="e" * 64).fingerprint(), baseline)
        self.assertNotEqual(self.answers(metadata={"model": "different"}).fingerprint(), baseline)
        changed_outputs = copy.deepcopy(self.outputs)
        changed_outputs[0]["answers"][0] = "changed"
        changed = Answers.from_results(
            self.release, self.tasks, changed_outputs, agent_sha256="d" * 64, metadata=self.metadata
        )
        self.assertNotEqual(changed.fingerprint(), baseline)
        reordered = jsonl(list(reversed([json.loads(line) for line in self.dataset.splitlines()])))
        changed_source = self.dataset.replace(b"control", b"new-category")
        for dataset in (reordered, changed_source, self.dataset.rstrip(b"\n")):
            with self.subTest(dataset=dataset):
                tasks = TaskSet.from_dataset(self.make_release(dataset), dataset)
                self.assertNotEqual(tasks.fingerprint(), self.tasks.fingerprint())
                self.assertNotEqual(tasks.dataset_sha256, self.tasks.dataset_sha256)

    def test_dataset_loader_reads_verified_file_without_writes_keys_or_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tasks.jsonl"
            path.write_bytes(self.dataset)
            before = path.read_bytes()
            original = Path.open

            def readonly_open(file, mode="r", *args, **kwargs):
                if any(flag in mode for flag in ("w", "a", "x", "+")):
                    self.fail("artifact API attempted a file write")
                return original(file, mode, *args, **kwargs)

            with (
                patch.object(Path, "open", new=readonly_open),
                patch.object(os.environ, "get", side_effect=AssertionError("credential lookup")),
                patch("socket.socket", side_effect=AssertionError("network")),
                patch("subprocess.Popen", side_effect=AssertionError("execution")),
            ):
                tasks = TaskSet.from_file(self.release, path)
                self.assertEqual(tasks, self.tasks)
                self.assertTrue(self.answers().native_bytes())
            self.assertEqual(path.read_bytes(), before)

    def test_dataset_hash_mismatch_and_mutation_between_reads_are_rejected(self):
        with self.assertRaises(ReleaseError):
            TaskSet.from_dataset(self.release, self.dataset + b"\n")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tasks.jsonl"
            path.write_bytes(self.dataset + b"changed")
            with (
                patch(
                    "buddha.answers.file_hash",
                    return_value=hashlib.sha256(self.dataset).hexdigest(),
                ),
                self.assertRaises(ReleaseError),
            ):
                TaskSet.from_file(self.release, path)

    def test_bad_dataset_shapes_duplicate_ids_invalid_utf8_and_unknown_keys(self):
        datasets = [
            b"",
            b"[]\n",
            b"{}\n",
            b'{"id":"x","id":"y","prompt":"p"}\n',
            b'{"id":"x","prompt":"p"}\n\n',
            b'{"id":"x","prompt":"\xff"}\n',
            jsonl([{"id": "x", "prompt": "\ud800"}]),
            jsonl([{"id": "x", "prompt": "p", "extra": "\ud800"}]),
            jsonl([{"id": "x", "prompt": "p"}, {"id": "x", "prompt": "other"}]),
            jsonl([{"id": True, "prompt": "p"}]),
            jsonl([{"id": "x", "prompt": ["p"]}]),
        ]
        for dataset in datasets:
            with self.subTest(dataset=dataset), self.assertRaises(ReleaseError):
                TaskSet.from_dataset(self.make_release(dataset), dataset)
        record = self.tasks.to_record()
        record["unknown"] = True
        with self.assertRaises(ReleaseError):
            TaskSet.from_bytes(encoded(record))

    def test_task_constructor_checks_only_literal_outer_contract(self):
        self.assertEqual(Task("x", "", 1).prompt, "")
        self.assertEqual(Task("x", " \n\x00", 2).prompt, " \n\x00")
        for values in (
            ("", "p", 1),
            (True, "p", 1),
            (1.0, "p", 1),
            (2**63, "p", 1),
            ("x", 1, 1),
            ("x", "\ud800", 1),
            ("x", "p", True),
            ("x", "p", 0),
            ("x", "p", 1001),
        ):
            with self.subTest(values=values), self.assertRaises(ReleaseError):
                Task(*values)

    def test_tampered_derived_tasks_cannot_replace_verified_source(self):
        record = self.tasks.to_record()
        record["tasks"][0]["prompt"] = "tampered"
        with self.assertRaises(ReleaseError):
            TaskSet.from_bytes(encoded(record))
        record = self.tasks.to_record()
        record["dataset_sha256"] = "f" * 64
        with self.assertRaises(ReleaseError):
            TaskSet.from_bytes(encoded(record))

    def test_outer_population_count_order_and_text_failures_are_rejected(self):
        variants = [
            self.outputs[:-1],
            list(reversed(self.outputs)),
            [self.outputs[0], self.outputs[0]],
            [self.outputs[0] | {"answers": ["short"]}, self.outputs[1]],
            [self.outputs[0] | {"answers": ["", None, ""]}, self.outputs[1]],
            [self.outputs[0] | {"answers": ["", "\ud800", ""]}, self.outputs[1]],
            [self.outputs[0] | {"extra": True}, self.outputs[1]],
            {"b": ["", "", ""]},
        ]
        for outputs in variants:
            with self.subTest(outputs=outputs), self.assertRaises(ReleaseError):
                Answers.from_results(
                    self.release, self.tasks, outputs, agent_sha256="d" * 64, metadata={}
                )

    def test_metadata_cannot_override_any_mapped_field(self):
        for name in ("id", "prompt", "generations", "category"):
            with self.subTest(field=name), self.assertRaises(ReleaseError):
                self.answers(metadata={name: "override"})

    def test_non_json_non_utf8_metadata_and_bad_provenance_are_rejected(self):
        cycle = {}
        cycle["self"] = cycle
        for metadata in (
            {"nan": float("nan")},
            {"bytes": b"no"},
            {"tuple": (1, 2)},
            {"nested": {1: "key"}},
            {"text": "\ud800"},
            cycle,
            [],
        ):
            with self.subTest(metadata=type(metadata)), self.assertRaises(ReleaseError):
                self.answers(metadata=metadata)
        for digest in ("", "A" * 64, True, "d" * 63):
            with self.subTest(digest=digest), self.assertRaises(ReleaseError):
                self.answers(agent_sha256=digest)

    def test_release_mismatch_and_tampered_answer_artifact_are_rejected(self):
        changed = self.make_release(self.dataset, release="changed")
        with self.assertRaises(ReleaseError):
            Answers.from_results(
                changed, self.tasks, self.outputs, agent_sha256="d" * 64, metadata={}
            )
        record = self.answers().to_record()
        record["outputs"][0]["task_id"] = "changed"
        with self.assertRaises(ReleaseError):
            Answers.from_bytes(encoded(record))
        record = self.answers().to_record()
        record["tasks_sha256"] = "f" * 64
        with self.assertRaises(ReleaseError):
            Answers.from_bytes(encoded(record))


class TaskPopulationReuseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = AnswerArtifactTests("runTest")
        self.rows = [
            {
                "id": 1,
                "prompt": "Synthetic numeric prompt \u00e9",
                "prompt_paraphrases": ["alternate numeric prompt"],
                "nested": {"values": [None, False, {"snow": "\u2603", "zero": -0.0, "tiny": 1e-7}]},
            },
            {"id": "1", "prompt": "Synthetic string prompt", "nested": {"values": [1, True]}},
            {"id": "outside", "prompt": "Synthetic unselected prompt", "category": "retained"},
        ]
        self.dataset = jsonl(self.rows)
        self.release = self.fixture.make_release(self.dataset)
        self.tasks = TaskSet.from_dataset(self.release, self.dataset)

    @staticmethod
    def canonical(value):
        return json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()

    def original_row(self, task_id):
        return next(
            row for row in self.rows if (type(row["id"]), row["id"]) == (type(task_id), task_id)
        )

    def task_record(self, ids, *, dataset=None):
        import base64

        dataset = self.dataset if dataset is None else dataset
        release = self.release if dataset == self.dataset else self.fixture.make_release(dataset)
        return {
            "format": "buddha.tasks.v1",
            "release": release.to_record(),
            "release_sha256": release.fingerprint(),
            "dataset_sha256": hashlib.sha256(dataset).hexdigest(),
            "dataset_base64": base64.b64encode(dataset).decode("ascii"),
            "selection": list(ids),
            "tasks": [
                {"id": task_id, "prompt": self.original_row(task_id)["prompt"], "count": 3}
                for task_id in ids
            ],
        }

    def answer_record(self, ids):
        tasks = self.task_record(ids)
        return {
            "format": "buddha.answers.v1",
            "tasks": tasks,
            "tasks_sha256": hashlib.sha256(self.canonical(tasks)).hexdigest(),
            "agent_sha256": "d" * 64,
            "metadata": {"model": "synthetic"},
            "outputs": [{"task_id": task_id, "answers": ["", "same", "same"]} for task_id in ids],
        }

    def expected_native(self, ids):
        return b"".join(
            self.canonical(
                self.original_row(task_id)
                | {"model": "synthetic", "generations": ["", "same", "same"]}
            )
            + b"\n"
            for task_id in ids
        )

    def test_exact_taskset_selection_uses_no_population_validation(self):
        from buddha import answers as module

        with patch.object(module, "_population", wraps=module._population) as population:
            selected = self.tasks.select(["1", 1])
        self.assertEqual(selected.to_record(), self.task_record(["1", 1]))
        self.assertEqual(
            [(type(task.id), task.id, task.count) for task in selected.tasks],
            [(str, "1", 3), (int, 1, 3)],
        )
        self.assertEqual(population.call_count, 0)

    def test_saved_answers_validate_population_once_and_preserve_native_rows(self):
        from buddha import answers as module

        record = self.answer_record(["1", 1])
        noncanonical = json.dumps(record, ensure_ascii=False, indent=2).encode()
        expected_bytes = self.canonical(record)
        self.assertNotEqual(noncanonical, expected_bytes)
        with patch.object(module, "_population", wraps=module._population) as population:
            answers = Answers.from_bytes(noncanonical)
        self.assertEqual(answers.to_bytes(), expected_bytes)
        self.assertEqual(answers.fingerprint(), hashlib.sha256(expected_bytes).hexdigest())
        self.assertEqual(answers.native_bytes(), self.expected_native(["1", 1]))
        self.assertEqual(population.call_count, 1)

    def test_new_tasksets_validate_every_unselected_source_row(self):
        from buddha import answers as module

        valid = json.dumps(self.task_record([1]), indent=2).encode()
        with patch.object(module, "_population", wraps=module._population) as population:
            for _ in range(2):
                self.assertEqual(TaskSet.from_bytes(valid).to_record(), self.task_record([1]))
        self.assertEqual(population.call_count, 2)
        for mutation in ({"nested": {"bad": "\ud800"}}, {"id": 1}, {"prompt": []}):
            rows = copy.deepcopy(self.rows)
            rows[-1].update(mutation)
            record = self.task_record([1], dataset=jsonl(rows))
            with self.subTest(mutation=mutation):
                with patch.object(module, "_population", wraps=module._population) as population:
                    with self.assertRaises(ReleaseError):
                        TaskSet.from_bytes(self.canonical(record))
                self.assertEqual(population.call_count, 1)

    def test_selection_chains_and_defensive_views_preserve_full_typed_source(self):
        selected = self.tasks.select([1])
        exposed = selected.to_record()
        exposed["tasks"][0]["prompt"] = "changed"
        exposed["release"]["task"]["count"] = 1
        exposed["selection"].clear()
        derived = selected.select(["outside", "1", 1])
        self.assertEqual(derived.to_record(), self.task_record(["outside", "1", 1]))
        self.assertEqual(derived.select(["1"]).to_record(), self.task_record(["1"]))
        self.assertEqual(self.tasks.to_record(), self.task_record([1, "1", "outside"]))
        answers = Answers.from_bytes(self.canonical(self.answer_record(["outside", "1", 1])))
        view = answers.to_record()
        view["outputs"][0]["answers"].clear()
        view["metadata"]["model"] = "changed"
        view["tasks"]["tasks"][0]["prompt"] = "changed"
        self.assertEqual(answers.native_bytes(), self.expected_native(["outside", "1", 1]))
        self.assertEqual(derived.select([1]).to_record(), self.task_record([1]))

    def test_copy_and_pickle_roundtrips_keep_derived_artifacts(self):
        import pickle

        tasks = self.tasks.select(["1"])
        answers = Answers.from_bytes(self.canonical(self.answer_record(["1"])))
        for name, operation in (
            ("shallow", copy.copy),
            ("deep", copy.deepcopy),
            ("pickle", lambda value: pickle.loads(pickle.dumps(value))),
        ):
            with self.subTest(operation=name):
                restored_tasks, restored_answers = operation(tasks), operation(answers)
                self.assertEqual(restored_tasks, tasks)
                self.assertEqual(
                    restored_tasks.select(["outside"]).to_record(), self.task_record(["outside"])
                )
                self.assertEqual(
                    restored_answers.to_bytes(), self.canonical(self.answer_record(["1"]))
                )
                self.assertEqual(restored_answers.native_bytes(), self.expected_native(["1"]))

    def test_subclass_constructor_and_selection_guards_are_not_bypassed(self):
        from buddha import answers as module

        class GuardedTasks(TaskSet):
            def __post_init__(self):
                super().__post_init__()
                if self.to_record()["selection"] == ["outside"]:
                    raise ReleaseError("synthetic subclass selection guard")

        with patch.object(module, "_population", wraps=module._population) as population:
            tasks = GuardedTasks.from_bytes(self.canonical(self.task_record([1])))
        self.assertGreaterEqual(population.call_count, 1)
        with patch.object(module, "_population", wraps=module._population) as population:
            selected = tasks.select(["1"])
        self.assertIs(type(selected), GuardedTasks)
        self.assertEqual(selected.to_record(), self.task_record(["1"]))
        self.assertGreaterEqual(population.call_count, 1)
        with self.assertRaises(ReleaseError):
            tasks.select(["outside"])

    def test_native_subclass_fallback_revalidates_population(self):
        from buddha import answers as module

        class DerivedTasks(TaskSet):
            pass

        tasks = DerivedTasks.from_bytes(self.canonical(self.task_record(["1", 1])))
        with patch.object(module, "_population", wraps=module._population) as population:
            native = module._native(self.answer_record(["1", 1]), tasks)
        self.assertEqual(native, self.expected_native(["1", 1]))
        self.assertGreaterEqual(population.call_count, 1)
        rows = copy.deepcopy(self.rows)
        rows[-1]["nested"] = {"bad": "\ud800"}
        forged = self.task_record([1], dataset=jsonl(rows))

        class InvalidViewTasks(TaskSet):
            def to_record(self):
                return copy.deepcopy(forged)

        invalid_view = InvalidViewTasks.from_bytes(self.canonical(self.task_record([1])))
        with self.assertRaises(ReleaseError):
            module._native(self.answer_record([1]), invalid_view)


class SelectedTaskViewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = TaskPopulationReuseTests("runTest")
        self.fixture.setUp()

    def test_first_and_repeated_selected_views_do_not_decode_or_rebuild_tasks(self):
        from buddha import answers as module

        fixture = self.fixture
        record = fixture.task_record(["1", 1])
        tasks = TaskSet.from_bytes(json.dumps(record, indent=2).encode())
        expected = tuple(Task(**row) for row in record["tasks"])
        before = tasks.to_bytes(), tasks.fingerprint(), tasks.to_record()
        with (
            patch.object(module.json, "loads", wraps=json.loads) as decode,
            patch.object(module, "Task", wraps=Task) as construct,
        ):
            views = [tasks.tasks for _ in range(5)]
        self.assertEqual(views, [expected] * 5)
        self.assertEqual(decode.call_count, 0)
        self.assertEqual(construct.call_count, 0)
        exposed = tasks.to_record()
        exposed["tasks"][0]["prompt"] = "changed"
        exposed["selection"].clear()
        self.assertEqual(tasks.tasks, expected)
        self.assertEqual((tasks.to_bytes(), tasks.fingerprint(), tasks.to_record()), before)
        self.assertEqual(tasks, TaskSet.from_bytes(fixture.canonical(record)))
        self.assertEqual(repr(tasks), "TaskSet()")
        with self.assertRaises(FrozenInstanceError):
            tasks.tasks[0].prompt = "changed"

    def test_primed_views_and_copied_selections_reselect_full_typed_source(self):
        import pickle

        fixture = self.fixture
        parent = fixture.tasks
        self.assertEqual([task.id for task in parent.tasks], [1, "1", "outside"])
        selected = parent.select(["1", 1])
        self.assertEqual([task.id for task in selected.tasks], ["1", 1])
        for name, operation in (
            ("original", lambda value: value),
            ("shallow", copy.copy),
            ("deep", copy.deepcopy),
            ("pickle", lambda value: pickle.loads(pickle.dumps(value))),
        ):
            with self.subTest(operation=name):
                restored = operation(selected)
                self.assertEqual(restored.tasks, selected.tasks)
                derived = restored.select(["outside", "1"])
                self.assertEqual([task.id for task in derived.tasks], ["outside", "1"])
                self.assertEqual(derived.to_record(), fixture.task_record(["outside", "1"]))
                reselected = derived.select([1])
                self.assertEqual(reselected.tasks, (Task(**fixture.task_record([1])["tasks"][0]),))
                raw = fixture.canonical(fixture.task_record([1]))
                self.assertEqual(reselected.to_bytes(), raw)
                self.assertEqual(reselected.fingerprint(), hashlib.sha256(raw).hexdigest())
                answers = Answers.from_results(
                    fixture.release,
                    derived,
                    fixture.answer_record(["outside", "1"])["outputs"],
                    agent_sha256="d" * 64,
                    metadata={"model": "synthetic"},
                )
                self.assertEqual(answers.native_bytes(), fixture.expected_native(["outside", "1"]))
        self.assertEqual([task.id for task in parent.tasks], [1, "1", "outside"])
        self.assertEqual([task.id for task in selected.tasks], ["1", 1])

    def test_subclass_task_views_still_decode_dynamic_records(self):
        view = [{"id": "dynamic", "prompt": "literal dynamic view", "count": 2}]

        class DynamicTasks(TaskSet):
            def to_record(self):
                return super().to_record() | {"tasks": copy.deepcopy(view)}

        fixture = self.fixture
        tasks = DynamicTasks.from_bytes(fixture.canonical(fixture.task_record([1])))
        self.assertEqual(tasks.tasks, (Task("dynamic", "literal dynamic view", 2),))
        view[0] = {"id": 2, "prompt": "changed dynamic view", "count": 1}
        self.assertEqual(tasks.tasks, (Task(2, "changed dynamic view", 1),))
        view[0]["id"] = True
        with self.assertRaises(ReleaseError):
            _ = tasks.tasks


if __name__ == "__main__":
    unittest.main()
