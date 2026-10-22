"""Verified saved development measurements become bounded existing-format feedback."""

import copy
import hashlib
import json
import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_source_screen as screen_fixtures

from buddha.answers import TaskSet
from buddha.releases import Release, Selection, _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceFeedbackTests(unittest.TestCase):
    def setUp(self):
        # Missing-module evidence is one setup error, before a fixture or body runs.
        from buddha.source_feedback import (
            SourceFeedbackError,
            build_source_feedback,
            write_source_feedback,
        )

        self.Error = SourceFeedbackError
        self.build_api, self.write_api = build_source_feedback, write_source_feedback
        self.h = screen_fixtures.SourceScreenTests("runTest")
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)

    def completed(self):
        directory, authority = self.h.prepare(self.h.screen())
        self.assertEqual(self.h.run_screen(directory)["status"], "complete")
        return directory, authority, self.h.reference(directory, authority)

    @contextmanager
    def passive(self):
        with (
            self.h.readonly(),
            patch("socket.socket", side_effect=AssertionError("passive socket")),
            patch("socket.create_connection", side_effect=AssertionError("passive network")),
        ):
            yield

    def source(self, *, count=2, rows=None):
        h, e = self.h, self.h.engine
        f = e.fixture
        h.rows = copy.deepcopy(h.rows if rows is None else rows)
        dataset = b"".join(_json(row) + b"\n" for row in h.rows)
        (f.roots["official"] / "data/tasks.jsonl").write_bytes(dataset)
        f.release_record["source"] = inventory(f.roots["official"])
        f.release_record["task"]["count"] = count
        release = Release.from_record(f.release_record)
        h.source = TaskSet.from_dataset(release, dataset)
        e.candidate.release = release
        h.record["source"] = h.source.to_record()
        h.record["split"].update(
            release_sha256=h.source.release_sha256, dataset_sha256=h.source.dataset_sha256
        )
        for role in ("generation", "native"):
            section = h.record[role]
            roots = {name: Path(path) for name, path in section["roots"].items()}
            section["selection"] = prepare_selection(
                release, roots, capabilities=section["selection"]["capabilities"]
            ).to_record()
        f.selection = Selection.from_bytes(_json(h.record["generation"]["selection"]))

    def notes(self, bundle):
        return [json.loads(row["note"]) for row in bundle["feedback"]["records"]]

    def test_verified_multitask_report_builds_existing_feedback_without_writes(self):
        directory, authority, reference = self.completed()
        destination = self.h.root / "measured-feedback"
        before = self.h.files(self.h.root), authority.summary(), self.h.engine.physical_sends
        with self.passive():
            result = self.build_api(destination, reference=reference)
            again = self.build_api(destination, reference=reference)
        self.assertEqual(set(result), {"source", "split", "feedback", "provenance"})
        self.assertEqual(result, again)
        self.assertEqual(result["source"], self.h.source.to_record())
        self.assertEqual(result["split"], self.h.record["split"])
        self.assertEqual(result["feedback"]["format"], "buddha.candidate-development-feedback.v1")
        rows = result["feedback"]["records"]
        self.assertEqual([row["task_id"] for row in rows], ["1", 1])
        self.assertEqual(
            result["feedback"]["source"],
            {"path": str(destination / "source.json"), "sha256": sha(_json(result["source"]))},
        )
        notes = self.notes(result)
        expected_keys = {
            "kind",
            "status",
            "distinct",
            "utility",
            "invalid_metrics",
            "quality_status",
            "partition",
            "generation_scores",
            "answers",
            "omitted_answer_positions",
            "omitted_partition_positions",
            "omitted_score_positions",
            "recorded_cost_microusd",
            "cost_scope",
        }
        for index, (row, note) in enumerate(zip(rows, notes, strict=True)):
            self.assertEqual(set(note), expected_keys)
            self.assertEqual(note["kind"], "saved_native_measurements")
            self.assertEqual(note["status"], "complete")
            self.assertEqual((note["distinct"], note["utility"]), (2, 7))
            self.assertEqual(note["partition"], [0, 1])
            self.assertEqual(note["generation_scores"], [7, 7])
            self.assertEqual(
                note["answers"],
                [{"position": 0, "text": "  unchanged weak text  "}, {"position": 1, "text": ""}],
            )
            self.assertEqual(note["cost_scope"], "original_task_generation_and_native_owners")
            self.assertEqual(row["note"], _json(note).decode())
            provenance = result["provenance"]["tasks"][index]
            self.assertEqual(provenance["task_id"], row["task_id"])
            self.assertEqual(provenance["note_sha256"], sha(row["note"].encode()))
            self.assertEqual(provenance["note_utf8_bytes"], len(row["note"].encode()))
        self.assertEqual(result["provenance"]["reference"], reference)
        self.assertEqual(result["provenance"]["feedback_sha256"], sha(_json(result["feedback"])))
        result["feedback"]["records"][0]["note"] = "caller mutation"
        with self.passive():
            self.assertEqual(self.build_api(destination, reference=reference), again)
        self.assertFalse(destination.exists())
        self.assertEqual(
            (self.h.files(self.h.root), authority.summary(), self.h.engine.physical_sends), before
        )

    def test_literal_prefixes_and_all_original_positions_have_explicit_omissions(self):
        self.source(count=12)
        screen = self.h.screen()
        answers = [
            "é雪" * 60,
            "\x01" * 60,
            "",
            " \n",
            "[refused]",
            "same",
            "same",
            "é",
            "plain",
            "  last shown  ",
            "not shown ten",
            "not shown eleven",
        ]
        self.h.programs[screen.candidate_id]["answers"] = answers
        original = self.h.execute

        def execute(spec, *, initial, handle, **arguments):
            if spec.role != "agent":
                session = handle.__self__
                original_file = session._file

                def extend(frame):
                    if frame["path"] in {"partitions.jsonl", "scores.jsonl"}:
                        import base64

                        frame = copy.deepcopy(frame)
                        rows = [
                            json.loads(line)
                            for line in base64.b64decode(frame["data_base64"]).splitlines()
                        ]
                        for row in rows:
                            row["partition"] = [0, 1] + [0] * 10
                            if frame["path"] == "scores.jsonl":
                                row["generation_scores"] = [7, 7] + [None] * 10
                        frame["data_base64"] = base64.b64encode(
                            b"".join(_json(row) + b"\n" for row in rows)
                        ).decode()
                    return original_file(frame)

                session._file = extend
            return original(spec, initial=initial, handle=handle, **arguments)

        directory, authority = self.h.prepare(screen)
        with patch.object(self.h, "execute", side_effect=execute):
            self.assertEqual(self.h.run_screen(directory)["status"], "complete")
        reference = self.h.reference(directory, authority)
        bundle = self.build_api(self.h.root / "excerpts", reference=reference)
        for note, provenance in zip(self.notes(bundle), bundle["provenance"]["tasks"], strict=True):
            self.assertEqual([item["position"] for item in note["answers"]], list(range(10)))
            self.assertEqual(note["omitted_answer_positions"], 2)
            self.assertEqual(note["omitted_partition_positions"], 2)
            self.assertEqual(note["omitted_score_positions"], 2)
            self.assertEqual(len(provenance["answers"]), 12)
            for index, value in enumerate(answers):
                raw = value.encode()
                retained = provenance["answers"][index]
                self.assertEqual(retained["position"], index)
                self.assertEqual(
                    (retained["utf8_sha256"], retained["utf8_bytes"]), (sha(raw), len(raw))
                )
                prefix = note["answers"][index]["text"] if index < 10 else ""
                self.assertTrue(value.startswith(prefix))
                self.assertEqual(retained["excerpt_utf8_bytes"], len(prefix.encode()))
                self.assertEqual(retained["omitted_utf8_bytes"], len(raw) - len(prefix.encode()))
                expected = (
                    "answer_positions"
                    if index >= 10
                    else "excerpt_bytes"
                    if prefix != value
                    else None
                )
                self.assertEqual(retained["omission"], expected)
                if index < 10:
                    self.assertLessEqual(len(prefix.encode()), 64)
                    self.assertLessEqual(len(_json(prefix)), 128)
                    if prefix != value:
                        extended = value[: len(prefix) + 1]
                        self.assertTrue(len(extended.encode()) > 64 or len(_json(extended)) > 128)
            self.assertEqual(
                note["answers"][2:7], [{"position": i, "text": answers[i]} for i in range(2, 7)]
            )

    def test_complete_invalid_metrics_remain_visible_without_fabricated_zeroes(self):
        self.h.unusable_task = "1"
        directory, _, reference = self.completed()
        bundle = self.build_api(self.h.root / "invalid-measurements", reference=reference)
        note = self.notes(bundle)[0]
        self.assertIsNone(note["utility"])
        self.assertIn("utility", note["invalid_metrics"])
        self.assertEqual(note["distinct"], 2)
        self.assertEqual(note["status"], "complete")
        self.assertNotIn(b"NaN", _json(bundle))
        self.assertFalse(
            json.loads((directory / "report.json").read_bytes())["admission"]["eligible"]
        )

    def test_complete_opaque_projection_is_refused_without_writing(self):
        self.h.record["projection"] = None
        _, _, reference = self.completed()
        destination = self.h.root / "opaque-notes"
        before = self.h.files(self.h.root)
        with self.passive(), self.assertRaises(self.Error):
            self.write_api(destination, reference=reference)
        self.assertFalse(destination.exists())
        self.assertEqual(self.h.files(self.h.root), before)

    def test_report_authority_split_and_literal_source_custody_are_required(self):
        directory, _, reference = self.completed()
        destination = self.h.root / "rejected-notes"
        with self.passive():
            self.build_api(destination, reference=reference)
        bad = [
            reference | {"report_sha256": "0" * 64},
            reference | {"authorization": str(self.h.engine.fixture.authority.path)},
        ]
        for value in bad:
            with self.subTest(reference=value), self.passive(), self.assertRaises(self.Error):
                self.build_api(destination, reference=value)
        screen_path = directory / "screen.json"
        before = screen_path.read_bytes()
        record = json.loads(before)
        record["split"]["partitions"]["development"].remove(1)
        record["split"]["partitions"]["final"].append(1)
        try:
            screen_path.write_bytes(_json(record))
            with self.passive(), self.assertRaises(self.Error):
                self.build_api(destination, reference=reference)
        finally:
            screen_path.write_bytes(before)
        generation = directory / "tasks/0/generation"
        seal = json.loads((generation / "completed/0.json").read_bytes())
        answers = generation / seal["attempt"] / "answers.json"
        before = answers.read_bytes()
        try:
            answers.write_bytes(before + b" ")
            with self.passive(), self.assertRaises(self.Error):
                self.build_api(destination, reference=reference)
        finally:
            answers.write_bytes(before)
        self.assertFalse(destination.exists())

    def test_writer_emits_existing_packet_and_never_overwrites_original_files(self):
        _, _, reference = self.completed()
        destination = self.h.root / "written-feedback"
        with self.passive():
            bundle = self.build_api(destination, reference=reference)
            result = self.write_api(destination, reference=reference)
        self.assertEqual(set(result), {"feedback", "provenance"})
        self.assertEqual(
            set(self.h.files(destination)),
            {"source.json", "split.json", "feedback.json", "provenance.json"},
        )
        for name in bundle:
            self.assertEqual((destination / (name + ".json")).read_bytes(), _json(bundle[name]))
        for name, ref in result.items():
            self.assertEqual(
                ref,
                {
                    "path": str(destination / (name + ".json")),
                    "sha256": sha((destination / (name + ".json")).read_bytes()),
                },
            )
        before = self.h.files(destination)
        with self.assertRaises(self.Error):
            self.write_api(destination, reference=reference)
        self.assertEqual(self.h.files(destination), before)

    def test_output_overlap_refuses_while_authority_parent_sibling_is_valid(self):
        directory, authority, reference = self.completed()
        roots = [
            Path(path)
            for role in ("generation", "native")
            for path in self.h.record[role]["roots"].values()
        ]
        for index, parent in enumerate([directory, *dict.fromkeys(roots)]):
            destination = parent / ("feedback-overlap-" + str(index))
            with self.subTest(parent=parent), self.passive(), self.assertRaises(self.Error):
                self.write_api(destination, reference=reference)
            self.assertFalse(destination.exists())
        with self.assertRaises(self.Error):
            self.write_api(self.h.root / "feedback:stream", reference=reference)
        destination = authority.path.parent / "allowed-sibling-feedback"
        with self.passive():
            written = self.write_api(destination, reference=reference)
        self.assertEqual(Path(written["feedback"]["path"]).parent, destination)

    def test_third_write_failure_retains_partial_directory_without_retry_overwrite(self):
        _, _, reference = self.completed()
        destination = self.h.root / "partial-write"
        original = Path.open
        writes = []

        def opened(path, mode="r", *arguments, **keywords):
            if path.parent == destination and "x" in mode:
                writes.append(path.name)
                if len(writes) == 3:
                    raise OSError("controlled third exclusive write failure")
            return original(path, mode, *arguments, **keywords)

        with patch.object(Path, "open", opened), self.assertRaises(self.Error):
            self.write_api(destination, reference=reference)
        self.assertEqual(len(writes), 3)
        before = self.h.files(destination)
        self.assertEqual(len(before), 2)
        with self.assertRaises(self.Error):
            self.write_api(destination, reference=reference)
        self.assertEqual(self.h.files(destination), before)

    def test_existing_candidate_session_accepts_packet_and_only_projects_development_notes(self):
        from buddha.candidate_run import CandidateSession

        _, _, reference = self.completed()
        destination = self.h.root / "consumer-packet"
        written = self.write_api(destination, reference=reference)
        h, f = self.h.engine.candidate, self.h.engine.fixture
        generation = self.h.record["generation"]
        record = {
            name: generation[name]
            for name in ("config", "entrypoint", "executor", "profile", "runtime", "max_callbacks")
        }
        record.update(
            format="buddha.candidate-improvement.v1",
            parent_agent_sha256=f.selection.agent_sha256,
            feedback=written["feedback"],
        )
        descriptor = self.h.root / "measured-improver.json"
        descriptor.write_bytes(_json(record))
        bound = [
            descriptor,
            h.runtime_path,
            *[
                destination / name
                for name in ("source.json", "split.json", "feedback.json", "provenance.json")
            ],
            *[
                h.package / (name + ".py")
                for name in (*h.host_names, "policy_study", "source_feedback")
            ],
        ]
        expected = {path: sha(path.read_bytes()) for path in bound}
        owner = f.prepare(
            "measured-feedback-consumer", input_files=bound, expected_input_hashes=expected
        )
        gateway = f.gateway(directory=owner)
        before = self.h.engine.physical_sends
        with (
            patch("buddha.executor.run_container", side_effect=AssertionError("no worker needed")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("no model call")),
        ):
            session = CandidateSession(
                gateway,
                descriptor=descriptor,
                output=self.h.root / "unused-consumer-output",
                expected_runtime_sha256=h.expected_runtime,
            )
        packet = json.loads(Path(written["feedback"]["path"]).read_bytes())
        projected = session.worker["feedback"]
        self.assertEqual([row["task"]["id"] for row in projected], ["1", 1])
        for row, source_row, task in zip(
            projected, packet["records"], self.h.source.select(["1", 1]).tasks, strict=True
        ):
            self.assertEqual(row, {"task": task.to_record(), "note": source_row["note"]})
        encoded = _json(projected)
        for private in (
            b"VALIDATION-ONLY-SENTINEL",
            b"FINAL-ONLY-SENTINEL",
            b"dataset_base64",
            b"operations.sqlite3",
        ):
            self.assertNotIn(private, encoded)
        manifest = json.loads((owner / "manifest.json").read_bytes())
        bindings = {row["path"]: row["sha256"] for row in manifest["invocation"]["inputs"]}
        for path, digest in expected.items():
            self.assertEqual(bindings[str(path)], digest)
        self.assertEqual(self.h.engine.physical_sends, before)
        self.assertEqual(gateway.ledger.totals()["operation_count"], 0)

    def test_worker_projection_bound_includes_genuine_escaped_task_text_before_mkdir(self):
        rows = copy.deepcopy(self.h.rows)
        rows[0]["prompt"], rows[1]["prompt"] = "A" + "\x01" * 100_000, "B" + "\x02" * 100_000
        self.source(rows=rows)
        _, _, reference = self.completed()
        tasks = self.h.source.select(["1", 1]).tasks
        projected_without_notes = _json([{"task": task.to_record(), "note": ""} for task in tasks])
        self.assertGreater(len(projected_without_notes), 1 << 20)
        destination = self.h.root / "oversized-worker-projection"
        # Two bounded notes and short file refs fit comfortably; task text is not in the packet.
        self.assertLess(2 * 4096 + 4 * len(str(destination)) + 4096, 1 << 20)
        before = self.h.files(self.h.root)
        with self.passive(), self.assertRaises(self.Error):
            self.write_api(destination, reference=reference)
        self.assertFalse(destination.exists())
        self.assertEqual(self.h.files(self.h.root), before)

    def test_passive_build_survives_retirement_of_original_producer_programs(self):
        directory, _, reference = self.completed()
        destination = self.h.root / "retired-source-notes"
        expected = self.build_api(destination, reference=reference)
        for role in ("agent", "runner"):
            source = Path(self.h.record["generation"]["roots"][role]).resolve(strict=True)
            retained = (self.h.root / ("retired-feedback-" + role)).resolve()
            self.assertTrue(
                source.is_relative_to(self.h.root.resolve()) and source != self.h.root.resolve()
            )
            self.assertTrue(
                retained.is_relative_to(self.h.root.resolve()) and retained != self.h.root.resolve()
            )
            shutil.move(str(source), str(retained))
        before = self.h.files(self.h.root)
        with self.passive():
            self.assertEqual(self.build_api(destination, reference=reference), expected)
        self.assertEqual(self.h.files(self.h.root), before)
        self.assertTrue((directory / "report.json").is_file())

    def test_original_task_costs_ignore_later_shared_grant_growth(self):
        first, authority, reference = self.completed()
        destination = self.h.root / "original-cost-notes"
        expected = self.build_api(destination, reference=reference)
        second = self.h.screen(self.h.second_source())
        other, _ = self.h.prepare(second, self.h.root / "later-same-grant", authority)
        self.assertEqual(self.h.run_screen(other)["status"], "complete")
        with self.passive():
            actual = self.build_api(destination, reference=reference)
        self.assertEqual(actual, expected)
        original = json.loads((first / "report.json").read_bytes())["authorization"]
        self.assertGreater(authority.summary()["spent_microusd"], original["spent_microusd"])
        costs = [note["recorded_cost_microusd"] for note in self.notes(actual)]
        self.assertTrue(all(type(cost) is int and cost > 0 for cost in costs))
        self.assertEqual(sum(costs), original["spent_microusd"])

    def test_source_capture_drift_errors_keep_public_and_bridge_error_types(self):
        from buddha import candidate_generation
        from buddha.doctor import _Unsupported

        directory, authority, reference = self.completed()
        report = json.loads((directory / "report.json").read_bytes())
        source = report["tasks"][0]["source_generation"]
        reader = candidate_generation.read_candidate_generation_source
        destination = self.h.root / "capture-drift-notes"
        before = self.h.files(self.h.root), self.h.engine.physical_sends
        with self.passive():
            reader(source, authority.path)
        with self.subTest(boundary="public-source-reader"), self.passive():
            with patch.object(
                candidate_generation,
                "_owner",
                side_effect=_Unsupported("controlled second-capture schema drift"),
            ):
                with self.assertRaises(candidate_generation.CandidateGenerationError):
                    reader(source, authority.path)
        original, calls = candidate_generation._owner, []

        def after_inspection(*arguments, **keywords):
            calls.append(True)
            if len(calls) == len(report["tasks"]) + 1:
                raise _Unsupported("controlled bridge source-capture drift")
            return original(*arguments, **keywords)

        with self.subTest(boundary="bridge-after-genuine-inspection"), self.passive():
            with patch.object(candidate_generation, "_owner", side_effect=after_inspection):
                with self.assertRaises(self.Error):
                    self.build_api(destination, reference=reference)
        self.assertEqual(len(calls), len(report["tasks"]) + 1)
        self.assertEqual((self.h.files(self.h.root), self.h.engine.physical_sends), before)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
