"""Local immutable reuse retains strict inputs and passive saved-screen custody."""

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import test_gateway as gateway_fixtures
import test_source_screen as fixtures

from buddha import answers, source_screen
from buddha.answers import Answers, TaskSet
from buddha.releases import Release, _json, inventory, prepare_selection


class SourceScreenLocalReuseTests(unittest.TestCase):
    def fixture(self, *, thousand=False):
        fixture = fixtures.SourceScreenTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        if thousand:
            fixture.rows += [
                {
                    "id": "synthetic-" + str(index),
                    "prompt": "Synthetic task " + str(index),
                    "details": {"tags": ["opaque", {"values": [index, True, None]}]},
                }
                for index in range(996)
            ]
            engine = fixture.engine
            supplied = engine.fixture
            dataset = b"".join(_json(row) + b"\n" for row in fixture.rows)
            (supplied.roots["official"] / "data/tasks.jsonl").write_bytes(dataset)
            supplied.release_record["source"] = inventory(supplied.roots["official"])
            release = Release.from_record(supplied.release_record)
            fixture.source = TaskSet.from_dataset(release, dataset)
            engine.candidate.release = release
            engine.candidate.tasks = fixture.source.select(["1"])
            engine.candidate.task_path.write_bytes(engine.candidate.tasks.to_bytes())
            supplied.selection = prepare_selection(
                release,
                supplied.roots,
                capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
            )
            native_roots = {name: Path(path) for name, path in engine.native["roots"].items()}
            engine.native["selection"] = prepare_selection(
                release,
                native_roots,
                capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
            ).to_record()
            fixture.record["source"] = fixture.source.to_record()
            fixture.record["generation"]["selection"] = supplied.selection.to_record()
            fixture.record["native"] = copy.deepcopy(engine.native)
            split = fixture.record["split"]
            split["release_sha256"] = fixture.source.release_sha256
            split["dataset_sha256"] = fixture.source.dataset_sha256
            split["partitions"]["final"] += [row["id"] for row in fixture.rows[4:]]
            split["families"] = [
                {"id": task.id, "family": "family-" + str(index)}
                for index, task in enumerate(fixture.source.tasks)
            ]
        return fixture

    def test_thousand_row_controls_materialization_and_preflight_reuse_local_population(self):
        fixture = self.fixture(thousand=True)
        screen = fixture.screen()
        directory = fixture.root / "local-only"
        directory.mkdir()
        (directory / "tasks").mkdir()
        expected = [fixture.source.select([identifier]) for identifier in ["1", 1]]
        counts = {}
        with patch.object(answers, "_population", wraps=answers._population) as population:
            for index, task in enumerate(expected):
                location = directory / "tasks" / str(index)
                controls = source_screen._task_controls(location, screen, index)
                self.assertEqual(controls[location / "task.json"], task.fingerprint())
            counts["controls"] = population.call_count
            population.reset_mock()
            for index, task in enumerate(expected):
                location, descriptor = source_screen._materialize(directory, screen, index)
                self.assertEqual((location / "task.json").read_bytes(), task.to_bytes())
                self.assertEqual(
                    descriptor.read_bytes(),
                    _json(source_screen._generation_recipe(location, screen)),
                )
            counts["materialize"] = population.call_count
            population.reset_mock()
            self.assertEqual(
                source_screen._preflight(
                    directory, screen, SimpleNamespace(summary=lambda: {"runs": []}), {}, {}
                ),
                set(),
            )
            counts["preflight"] = population.call_count
        selected = screen.tasks
        release = Release.from_record(selected.to_record()["release"])
        outputs = [
            {"task_id": identifier, "answers": ["  unchanged weak text  ", ""]}
            for identifier in ["1", 1]
        ]
        artifact = Answers.from_results(
            release, selected, outputs, agent_sha256=screen.candidate_id, metadata={}
        )
        expected_native = b"".join(
            _json(row | {"generations": output["answers"]}) + b"\n"
            for row, output in zip([fixture.rows[1], fixture.rows[0]], outputs, strict=True)
        )
        self.assertEqual(artifact.native_bytes(), expected_native)
        before = screen.to_bytes(), selected.to_bytes(), artifact.to_bytes()
        exposed = screen.to_record()
        exposed["source"]["tasks"][0]["prompt"] = "changed exposed copy"
        exposed["selected_ids"].reverse()
        selected.to_record()["tasks"].clear()
        artifact.to_record()["outputs"][0]["answers"].clear()
        self.assertEqual((screen.to_bytes(), selected.to_bytes(), artifact.to_bytes()), before)
        self.assertEqual(artifact.native_bytes(), expected_native)
        self.assertEqual(counts, {"controls": 10, "materialize": 10, "preflight": 7})

    def test_passive_screen_reuses_one_validated_declaration_and_preserves_saved_bytes(self):
        fixture = self.fixture()
        directory, authority = fixture.prepare(fixture.screen())
        self.assertEqual(fixture.run_screen(directory)["status"], "complete")
        raw = (directory / "report.json").read_bytes()
        before = (
            fixture.files(directory),
            authority.path.read_bytes(),
            fixture.engine.physical_sends,
        )
        with (
            fixture.readonly(),
            patch.object(
                source_screen.SourceScreen,
                "from_bytes",
                wraps=source_screen.SourceScreen.from_bytes,
            ) as constructors,
        ):
            checked = fixture.inspect_api(
                directory,
                authorization=authority.path,
                expected_report_sha256=fixtures.sha(raw),
            )
        self.assertEqual(_json(checked), raw)
        self.assertEqual(
            (fixture.files(directory), authority.path.read_bytes(), fixture.engine.physical_sends),
            before,
        )
        self.assertEqual(constructors.call_count, 1)

    def test_invalid_directory_rejects_before_population_or_authority_access(self):
        fixture = self.fixture()
        screen = fixture.screen()
        directory = fixture.root / "invalid-local"
        directory.mkdir()
        (directory / "tasks").mkdir()
        authority = SimpleNamespace(summary=lambda: self.fail("authority accessed before schedule"))
        with patch.object(
            source_screen.SourceScreen,
            "tasks",
            new_callable=PropertyMock,
            side_effect=AssertionError("population accessed before schedule"),
        ):
            for foreign in (False, True):
                if foreign:
                    (directory / "tasks/foreign").mkdir()
                with (
                    self.subTest(foreign=foreign),
                    self.assertRaisesRegex(
                        source_screen.SourceScreenError, "foreign or missing entries"
                    ),
                ):
                    source_screen._preflight(directory, screen, authority, {}, {})

    def test_changed_task_recipe_selection_and_source_hash_remain_rejected(self):
        fixture = self.fixture()
        screen = fixture.screen()
        directory = fixture.root / "changed-local"
        directory.mkdir()
        (directory / "tasks").mkdir()
        location, descriptor = source_screen._materialize(directory, screen, 0)
        task_path = location / "task.json"
        for path in (task_path, descriptor):
            original = path.read_bytes()
            path.write_bytes(b"{}")
            with (
                self.subTest(evidence=path.name),
                self.assertRaisesRegex(
                    source_screen.SourceScreenError, "original (task input|source recipe)"
                ),
            ):
                source_screen._preflight(
                    directory, screen, SimpleNamespace(summary=lambda: {"runs": []}), {}, {}
                )
            path.write_bytes(original)
        for change in ("selection", "source", "hash"):
            record = screen.to_record()
            if change == "selection":
                record["selected_ids"] = ["final"]
            elif change == "source":
                record["source"]["tasks"][0]["prompt"] = "not the frozen source"
            else:
                record["source"]["dataset_sha256"] = "0" * 64
            with self.subTest(input=change), self.assertRaises(source_screen.SourceScreenError):
                source_screen.SourceScreen.from_bytes(_json(record))
        self.assertEqual(json.loads(task_path.read_bytes()), screen.tasks.select(["1"]).to_record())


if __name__ == "__main__":
    unittest.main()
