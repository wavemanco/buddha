"""Complete source membership reuses strict immutable task validation."""

import base64
import copy
import hashlib
import unittest
from unittest.mock import patch

import test_source_screen as fixtures

from buddha import answers, source_screen
from buddha.releases import Release, _json


class ScreenCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SourceScreenTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def record(self, raw, *, rows=None, selected=None):
        rows = self.fixture.rows if rows is None else rows
        selected = [row["id"] for row in rows] if selected is None else selected
        record = copy.deepcopy(self.fixture.record)
        source = record["source"]
        release = source["release"]
        release["source"][release["task"]["dataset"]] = hashlib.sha256(raw).hexdigest()
        release = Release.from_record(release)
        source.update(
            release=release.to_record(),
            release_sha256=release.fingerprint(),
            dataset_sha256=hashlib.sha256(raw).hexdigest(),
            dataset_base64=base64.b64encode(raw).decode("ascii"),
            selection=selected,
            tasks=[
                {
                    "id": row["id"],
                    "prompt": row["prompt"],
                    "count": release.to_record()["task"]["count"],
                }
                for identifier in selected
                for row in rows
                if type(row["id"]) is type(identifier) and row["id"] == identifier
            ],
        )
        record["split"].update(
            release_sha256=release.fingerprint(), dataset_sha256=source["dataset_sha256"]
        )
        for section in ("generation", "native"):
            record[section]["selection"]["release"] = release.to_record()
            record[section]["selection"]["components"]["official"] = release.to_record()["source"]
        return record

    def test_complete_source_is_validated_once_without_rebuilding_population(self):
        with (
            patch.object(answers, "_population", wraps=answers._population) as population,
            patch.object(answers.TaskSet, "from_bytes", wraps=answers.TaskSet.from_bytes) as strict,
        ):
            screen = source_screen.SourceScreen.from_bytes(_json(self.fixture.record))
        self.assertEqual(strict.call_count, 1)
        self.assertEqual(population.call_count, 1)
        self.assertEqual(screen.to_bytes(), _json(self.fixture.record))

    def test_full_reordering_preserves_typed_development_order_and_source_bytes(self):
        record = copy.deepcopy(self.fixture.record)
        record["source"] = self.fixture.source.select(["final", "private", "1", 1]).to_record()
        screen = source_screen.SourceScreen.from_bytes(_json(record))
        self.assertEqual(screen.to_bytes(), _json(record))
        self.assertEqual(screen.to_record()["source"], record["source"])
        self.assertEqual(
            [(type(task.id), task.id) for task in screen.tasks.tasks], [(str, "1"), (int, 1)]
        )

    def test_exact_lf_count_accepts_newline_spellings_without_normalizing_source(self):
        lines = [_json(row) for row in self.fixture.rows]
        variants = [
            b"\n".join(lines) + b"\n",
            b"\n".join(lines),
            b"\r\n".join(lines) + b"\r\n",
            b"\r\n".join(lines) + b"\r",
            b"\n".join(line.replace(b",", b",\r", 1) for line in lines) + b"\n",
        ]
        for index, raw in enumerate(variants):
            record = self.record(raw)
            with self.subTest(index=index):
                screen = source_screen.SourceScreen.from_bytes(_json(record))
                self.assertEqual(screen.to_bytes(), _json(record))
                self.assertEqual(
                    base64.b64decode(screen.to_record()["source"]["dataset_base64"]), raw
                )
        rows = copy.deepcopy(self.fixture.rows)
        rows[0]["prompt"] = "First line\nSecond line"
        raw = b"".join(_json(row) + b"\n" for row in rows)
        screen = source_screen.SourceScreen.from_bytes(_json(self.record(raw, rows=rows)))
        self.assertEqual(screen.tasks.tasks[1].prompt, rows[0]["prompt"])

    def test_proper_subset_remains_incomplete_with_distinct_integer_and_string_ids(self):
        record = copy.deepcopy(self.fixture.record)
        record["source"] = self.fixture.source.select([1, "1"]).to_record()
        with patch.object(source_screen, "_split", wraps=source_screen._split) as split:
            with self.assertRaises(source_screen.SourceScreenError):
                source_screen.SourceScreen.from_bytes(_json(record))
        self.assertEqual(split.call_count, 0)

    def test_bad_unused_rows_fail_strict_construction_before_completeness(self):
        good = b"".join(_json(row) + b"\n" for row in self.fixture.rows[:-1])
        invalid = [
            b"\n",
            b'{"id":',
            b'{"id":"final","id":"other","prompt":"p"}\n',
            b'{"id":1,"prompt":"duplicate ID"}\n',
            b'{"id":"final","prompt":"p","unused":{"key":"\\ud800"}}\n',
            b'{"id":"final","prompt":"p","unused":NaN}\n',
            b'{"id":true,"prompt":"p"}\n',
            b'{"id":1.0,"prompt":"p"}\n',
        ]
        for index, row in enumerate(invalid):
            record = self.record(good + row, selected=[1, "1"])
            with self.subTest(index=index), patch.object(source_screen, "_split") as split:
                with self.assertRaises(source_screen.SourceScreenError):
                    source_screen.SourceScreen.from_bytes(_json(record))
                self.assertEqual(split.call_count, 0)
