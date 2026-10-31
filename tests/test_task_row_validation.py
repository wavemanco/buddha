"""Strict JSONL row guards and artifact parity without a mutable-metadata walk."""

import base64
import hashlib
import json
import unittest
from unittest.mock import patch

import test_answers as fixtures

from buddha import answers, releases
from buddha.releases import ReleaseError, _json, _load


class TaskRowValidationTests(unittest.TestCase):
    @staticmethod
    def release(raw):
        return fixtures.AnswerArtifactTests("runTest").make_release(raw)

    def test_population_does_not_revalidate_decoded_rows_as_mutable_metadata(self):
        rows = [
            {"id": str(index), "prompt": "Synthetic task", "extra": [None, {"values": [True, 1]}]}
            for index in range(1000)
        ]
        raw = fixtures.jsonl(rows)
        release = self.release(raw)
        with patch.object(answers, "_metadata", wraps=answers._metadata) as metadata:
            population = answers._population(release, raw)
        self.assertEqual(len(population), 1000)
        self.assertEqual(population["999"][1], rows[-1])
        self.assertEqual(metadata.call_count, 0)

    def test_raw_duplicate_nonfinite_nonobject_and_surrogate_rows_are_refused(self):
        rows = [
            b'{"id":"x","id":"y","prompt":"p"}',
            b'{"id":"x","\\u0069d":"y","prompt":"p"}',
            b'{"id":"x","prompt":"p","extra":{"key":1,"key":2}}',
            b'{"id":"x","prompt":"p","extra":[{"key":1,"\\u006bey":2}]}',
            *(
                b'{"id":"x","prompt":"p","extra":' + value + b"}"
                for value in (b"NaN", b"Infinity", b"-Infinity", b"1e999", b'[1,{"n":NaN}]')
            ),
            b"[]",
            b"null",
            b'{"id":"x","prompt":"p","extra":"\xff"}',
            b'{"id":"x","prompt":"\\ud800"}',
            b'{"id":"\\udc00","prompt":"p"}',
            b'{"id":"x","prompt":"p","\\ud800":"value"}',
            b'{"id":"x","prompt":"p","extra":{"\\udc00":"value"}}',
            b'{"id":"x","prompt":"p","extra":[{"key":"\\ud800"}]}',
            b'{"id":"x","prompt":"p","extra":{"key":["ok","\\udc00"]}}',
        ]
        for index, line in enumerate(rows):
            raw = line + b"\n"
            with self.subTest(index=index), self.assertRaises(ReleaseError):
                answers.TaskSet.from_dataset(self.release(raw), raw)

    def test_strict_decoded_nested_rows_match_the_existing_metadata_contract(self):
        atoms = [None, True, False, 0, -0.0, 1.25, "", "\n\t\x00", "caf\u00e9", "\U0001f642"]
        values = atoms + [[value, {"nested": value}] for value in atoms]
        values += [{"\u03bb": [value, {"\U0001f642": value}]} for value in values[:]]
        for index, value in enumerate(values):
            row = {"id": str(index), "prompt": "p", "extra": value}
            line = _json(row)
            expected = answers._metadata(_load(line), set())
            raw = line + b"\n"
            with self.subTest(index=index):
                population = answers._population(self.release(raw), raw)
                self.assertEqual(population[str(index)][1], expected)
        pair = b'{"id":"pair","prompt":"\\ud83d\\ude42","extra":{"\\ud83d\\ude42":"ok"}}\n'
        row = answers._population(self.release(pair), pair)["pair"][1]
        self.assertEqual(row["prompt"], "\U0001f642")
        self.assertEqual(row["extra"], {"\U0001f642": "ok"})

    def test_typed_order_metadata_native_bytes_and_source_provenance_are_exact(self):
        rows = [
            {"id": 1, "prompt": "numeric", "extra": {"\u03bb": [None, True, 1.5]}},
            {"id": "1", "prompt": "string \U0001f642", "extra": ["\u00e9", "\x00"]},
            {"id": -(2**63), "prompt": "minimum", "extra": {"a": []}},
            {"id": 2**63 - 1, "prompt": "maximum", "extra": {}},
        ]
        raw = fixtures.jsonl(rows)
        release = self.release(raw)
        tasks = answers.TaskSet.from_dataset(release, raw)
        expected = {
            "format": "buddha.tasks.v1",
            "release": release.to_record(),
            "release_sha256": release.fingerprint(),
            "dataset_sha256": hashlib.sha256(raw).hexdigest(),
            "dataset_base64": base64.b64encode(raw).decode("ascii"),
            "selection": [row["id"] for row in rows],
            "tasks": [{"id": row["id"], "prompt": row["prompt"], "count": 3} for row in rows],
        }
        self.assertEqual(tasks.to_bytes(), _json(expected))
        selected = tasks.select(["1", 1, 2**63 - 1, -(2**63)])
        self.assertEqual([type(task.id) for task in selected.tasks], [str, int, int, int])
        source = {row["id"]: row for row in rows}
        outputs = [
            {"task_id": task.id, "answers": ["", " repeated ", "\u00e9\U0001f642"]}
            for task in selected.tasks
        ]
        metadata = {"model": "synthetic", "settings": {"list": [False, -0.0]}}
        artifact = answers.Answers.from_results(
            release, selected, outputs, agent_sha256="d" * 64, metadata=metadata
        )
        native = b"".join(
            _json(source[output["task_id"]] | metadata | {"generations": output["answers"]}) + b"\n"
            for output in outputs
        )
        self.assertEqual(artifact.native_bytes(), native)
        self.assertEqual(artifact.to_record()["tasks_sha256"], selected.fingerprint())
        self.assertEqual(selected.dataset_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(selected.release_sha256, release.fingerprint())
        self.assertEqual(base64.b64decode(selected.to_record()["dataset_base64"]), raw)
        self.assertEqual(
            answers.Answers.from_bytes(artifact.to_bytes()).fingerprint(), artifact.fingerprint()
        )

        # Equivalent decoded Unicode is not permission to normalize original
        # dataset bytes or their release/task identities.
        alternate = b"".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            for row in rows
        )
        alternative = answers.TaskSet.from_dataset(self.release(alternate), alternate)
        self.assertEqual([task.to_record() for task in alternative.tasks], expected["tasks"])
        self.assertNotEqual(alternative.dataset_sha256, tasks.dataset_sha256)
        self.assertNotEqual(alternative.release_sha256, tasks.release_sha256)
        self.assertNotEqual(alternative.fingerprint(), tasks.fingerprint())

    def test_raw_and_ascii_canonical_caps_still_apply_before_row_use(self):
        line = json.dumps(
            {"id": "x", "prompt": "p", "extra": "\u00e9" * 20},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        raw = line + b"\n"
        release = self.release(raw)
        with patch.object(answers, "MAX_JSON_BYTES", len(raw) - 1), self.assertRaises(ReleaseError):
            answers._population(release, raw)
        self.assertGreater(len(_json(_load(line))), len(line))
        with patch.object(releases, "MAX_JSON_BYTES", len(line)), self.assertRaises(ReleaseError):
            answers._population(release, raw)

    def test_unused_rows_and_invalid_typed_ids_cannot_escape_validation(self):
        for index, bad in enumerate(
            [
                b'{"id":"unused","prompt":"p","extra":{"key":"\\ud800"}}',
                b'{"id":true,"prompt":"p"}',
                b'{"id":1.0,"prompt":"p"}',
                b'{"id":9223372036854775808,"prompt":"p"}',
                b'{"id":-9223372036854775809,"prompt":"p"}',
            ]
        ):
            raw = b'{"id":"selected","prompt":"p"}\n' + bad + b"\n"
            with self.subTest(index=index), self.assertRaises(ReleaseError):
                answers.TaskSet.from_dataset(self.release(raw), raw).select(["selected"])
