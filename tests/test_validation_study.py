"""Validation reservation reaches real original owners; workers and HTTP are mocked."""

import copy
import hashlib
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_candidate_generation as generation_fixtures
import test_gateway as gateway_fixtures

from buddha.answers import Answers, TaskSet
from buddha.authorization import Authorization
from buddha.gateway import RawHTTPTransport
from buddha.gateway_history import read_gateway_history
from buddha.releases import Release, Selection, _json, inventory, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ValidationStudyTests(unittest.TestCase):
    def setUp(self):
        # Missing API is an honest import/setup RED, before any synthetic fixture or SQL.
        from buddha.validation_study import (
            ValidationStudyError,
            prepare_validation_study,
            run_validation_occasion,
        )

        self.Error = ValidationStudyError
        self.prepare_api, self.run_api = prepare_validation_study, run_validation_occasion
        for target in (
            "subprocess.Popen",
            "socket.create_connection",
            "socket.socket.connect",
            "socket.getaddrinfo",
        ):
            self.enterContext(patch(target, side_effect=AssertionError("real I/O forbidden")))
        self.engine = e = generation_fixtures.CandidateGenerationTests("runTest")
        e.setUp()
        self.addCleanup(e.doCleanups)
        self.root = e.root
        self.rows = [
            {"id": 1, "prompt": "A synthetic validation task."},
            {"id": "1", "prompt": "A different synthetic development task."},
            {"id": "final", "prompt": "FINAL-ONLY-SENTINEL"},
        ]
        dataset = b"".join(_json(row) + b"\n" for row in self.rows)
        fixture = e.fixture
        (fixture.roots["official"] / "data/tasks.jsonl").write_bytes(dataset)
        fixture.release_record["source"] = inventory(fixture.roots["official"])
        release = Release.from_record(fixture.release_record)
        self.tasks = TaskSet.from_dataset(release, dataset)
        e.candidate.release = release
        e.candidate.tasks = self.tasks.select([1])
        e.candidate.task_path.write_bytes(e.candidate.tasks.to_bytes())
        fixture.selection = prepare_selection(
            release,
            fixture.roots,
            capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
        )
        native_roots = {name: Path(path) for name, path in e.native["roots"].items()}
        e.native["selection"] = prepare_selection(
            release,
            native_roots,
            capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"},
        ).to_record()
        generation = {
            name: copy.deepcopy(value)
            for name, value in e.candidate.record.items()
            if name not in {"format", "tasks"}
        }
        generation.update(
            selection=fixture.selection.to_record(),
            roots={name: str(path) for name, path in fixture.roots.items()},
            budget_microusd=10_000,
            max_calls=20,
        )
        self.evidence = self.write("custody-evidence.json", {"basis": "synthetic fixture only"})
        self.custody = {
            "format": "buddha.validation-custody.v1",
            "process_id": "offline-validation-fixture",
            "custodian": "synthetic test",
            "basis": "constructed synthetic tasks, not real holdout certification",
            "evidence": [self.reference(self.evidence)],
            "disclosures": [],
            "population": [
                {
                    "task_id": task.id,
                    "task_sha256": sha(_json(task.to_record())),
                    "family_id": "family-" + str(index),
                    "source": "synthetic",
                    "task_type": "fixture",
                    "phase": ["validation", "development", "final"][index],
                    "exposure": ["eligible", "exposed", "unknown"][index],
                }
                for index, task in enumerate(self.tasks.tasks)
            ],
        }
        self.rule = {
            "format": "buddha.improvement-rule.v1",
            "primary_metric": "distinct",
            "minimum_gain": 0.375,
            "max_other_loss": 0.125,
        }
        self.source_ref = self.reference(fixture.roots["agent"] / "candidate.py")
        self.record = {
            "format": "buddha.validation-study.v1",
            "experiment_id": "offline-validation-fixture",
            "tasks": self.reference(self.write("all-tasks.json", self.tasks.to_record())),
            "selected_ids": [1],
            "custody": self.reference(self.write("custody.json", self.custody)),
            "improvement_rule": self.reference(self.write("rule.json", self.rule)),
            "analysis_plan": self.reference(
                self.write("analysis-plan.json", {"method": "synthetic prospective binding only"})
            ),
            "comparators": [self.source_ref],
            "max_candidates": 1,
            "max_looks": 1,
            "repetitions": 2,
            "comparator_policy": "fresh-each-occasion",
            "repetition_unit": "complete-task-answer-set",
            "bound_axes": ["utility", "distinct"],
            "generation": generation,
            "native": copy.deepcopy(e.native),
            "stages": copy.deepcopy(e.stages),
        }
        self.declaration = self.write("declaration.json", self.record)
        self.directory = self.root / "validation-study"
        self.generation_events = []
        self.native_events = []
        e.callbacks = 1
        e.summary = b'{"synthetic":true}\n'

        def answers():
            return Answers.from_bytes((e.attempt() / "session/answers.json").read_bytes())

        e.answers = answers

    def write(self, name, record):
        path = self.root / name
        path.write_bytes(_json(record))
        return path

    @staticmethod
    def reference(path):
        return {"path": str(path), "sha256": sha(path.read_bytes())}

    def prepare(self, **changes):
        values = {
            "declaration": self.declaration,
            "expected_sha256": sha(self.declaration.read_bytes()),
            "expected_runtime_sha256": self.engine.candidate.expected_runtime,
        }
        self.prepare_api(self.directory, **(values | changes))

    def authority(self):
        return Authorization.create(
            self.root / "validation-authorization.sqlite3",
            authorization_id="offline-validation-fixture",
            budget_microusd=1_000_000,
            max_calls=1000,
            scope="validation study: " + sha(self.declaration.read_bytes()),
        )

    def execute(self, spec, *, initial, handle, **kwargs):
        e = self.engine
        session = handle.__self__
        if spec.role == "agent":
            self.assertEqual(type(initial["task"]["id"]), int)
            self.assertEqual(initial["task"], self.tasks.select([1]).tasks[0].to_record())
            self.assertNotIn(b"FINAL-ONLY-SENTINEL", _json(initial))
            self.assertNotIn(b"dataset_base64", _json(initial))
            self.assertEqual(initial["config"], self.record["generation"]["config"])
            self.assertEqual(dict(spec.mounts)["/runner"], e.fixture.roots["runner"])
            copied = Path(dict(spec.mounts)["/agent"]) / "candidate.py"
            self.assertNotEqual(copied, Path(self.source_ref["path"]))
            self.assertEqual(sha(copied.read_bytes()), self.source_ref["sha256"])
            self.generation_events.append((str(session.gateway.directory), initial["agent_sha256"]))
            e.candidate.tasks = session.tasks
            manifest = json.loads((session.gateway.directory / "manifest.json").read_bytes())
            e.fixture.selection = Selection.from_bytes(_json(manifest["selection"]))
            e.directory = session.output.parents[2]
            return e.execute(spec, initial=initial, handle=handle, **kwargs)
        e.directory = session.gateway.directory.parents[2] / "generation"
        self.native_events.append((str(session.gateway.directory), initial["command"]["index"]))
        return e.execute(spec, initial=initial, handle=handle, **kwargs)

    @contextmanager
    def offline(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=self.execute),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("real HTTP forbidden")),
            patch(
                "buddha.agent_run.AgentSession", side_effect=AssertionError("fixed seed forbidden")
            ),
        ):
            yield

    def run_occasion(self, authority, **changes):
        values = {
            "ordinal": 0,
            "candidate_refs": [self.source_ref],
            "authorization": authority,
            "review": self.engine.fixture.review,
            "transport": RawHTTPTransport(allow_paid=True),
        }
        return self.run_api(self.directory, **(values | changes))

    def test_reserved_occasion_is_consumed_by_every_original_generation_and_native_owner(self):
        from buddha import candidate_generation, native_evaluation

        self.prepare()
        authority = self.authority()
        occasion = self.directory / "validation/0/occasion.json"
        controls = {
            self.directory / name: sha((self.directory / name).read_bytes())
            for name in (
                "declaration.json",
                "context.json",
                "improvement-rule.json",
                "custody.json",
                "analysis-plan",
            )
        }
        self.assertEqual((self.directory / "improvement-rule.json").read_bytes(), _json(self.rule))
        original_generation = candidate_generation.prepare_candidate_generation
        original_native = native_evaluation.prepare_evaluation
        original_fsync = os.fsync
        synced = set()
        prepared = []

        def synced_identity(status):
            return status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns

        def tracked_fsync(descriptor):
            original_fsync(descriptor)
            synced.add(synced_identity(os.fstat(descriptor)))

        def checked_prepare(function, kind, directory, **kwargs):
            raw = occasion.read_bytes()
            self.assertEqual(raw, _json(json.loads(raw)))
            self.assertIn(synced_identity(occasion.stat()), synced)
            self.assertEqual([path.name for path in occasion.parent.parent.iterdir()], ["0"])
            reservation = occasion.parent / "reservation.json"
            ready = reservation.read_bytes()
            self.assertEqual(
                ready,
                _json({"format": "buddha.validation-reservation.v1", "occasion_sha256": sha(raw)}),
            )
            self.assertIn(synced_identity(reservation.stat()), synced)
            expected = controls | {occasion: sha(raw), reservation: sha(ready)}
            for path, digest in expected.items():
                self.assertIn(path, kwargs["input_files"])
                self.assertEqual(kwargs["expected_input_hashes"][path], digest)
            prepared.append((kind, directory, expected))
            if kind == "generation":
                selected = kwargs["selection"].to_record()
                template = self.record["generation"]["selection"]
                self.assertEqual(selected["capabilities"], template["capabilities"])
                for role in ("official", "runner", "host", "environment"):
                    self.assertEqual(selected["components"][role], template["components"][role])
                    self.assertEqual(
                        str(kwargs["roots"][role]), self.record["generation"]["roots"][role]
                    )
                self.assertEqual(
                    selected["components"]["agent"], {"candidate.py": self.source_ref["sha256"]}
                )
                self.assertEqual(
                    kwargs["expected_runtime_sha256"], self.engine.candidate.expected_runtime
                )
            else:
                native = json.loads(kwargs["descriptor"].read_bytes())
                generated = json.loads((directory.parent / "generation/report.json").read_bytes())
                self.assertEqual(generated["disposition"], "generated")
                self.assertEqual(native["source_generation"], generated["source_generation"])
                self.assertEqual(native["native"], self.record["native"])
                self.assertEqual(native["stages"], self.record["stages"])
            return function(directory, **kwargs)

        with (
            self.offline(),
            patch("os.fsync", side_effect=tracked_fsync),
            patch.object(
                candidate_generation,
                "prepare_candidate_generation",
                side_effect=lambda directory, **kw: checked_prepare(
                    original_generation, "generation", directory, **kw
                ),
            ),
            patch.object(
                native_evaluation,
                "prepare_evaluation",
                side_effect=lambda directory, **kw: checked_prepare(
                    original_native, "native", directory, **kw
                ),
            ),
        ):
            result = self.run_occasion(authority)
        self.assertEqual(result["status"], "complete")
        self.assertEqual([kind for kind, _, _ in prepared].count("generation"), 4)
        self.assertEqual([kind for kind, _, _ in prepared].count("native"), 4)
        self.assertEqual(len(self.generation_events), 4)
        self.assertEqual(len({owner for owner, _ in self.generation_events}), 4)
        self.assertEqual(len({identity for _, identity in self.generation_events}), 1)
        self.assertEqual(len(self.native_events), 12)
        self.assertEqual(self.engine.physical_sends, 12)
        self.actual_owner_input_evidence = []
        for kind, directory, expected in prepared:
            projected = self.projected_owner_paths(cell=directory.parent)
            for index in [0] if kind == "generation" else [1, 2, 3]:
                manifest = json.loads((directory / f"owners/{index}/manifest.json").read_bytes())
                inputs = {item["path"]: item["sha256"] for item in manifest["invocation"]["inputs"]}
                for path, digest in expected.items():
                    self.assertEqual(inputs[str(path)], digest)
                self.assertEqual({Path(path) for path in inputs}, projected[index])
                self.actual_owner_input_evidence.append(
                    {
                        "kind": kind,
                        "index": index,
                        "run_id": manifest["run_id"],
                        "paths": len(inputs),
                    }
                )
        before = inventory(self.directory)
        totals = authority.summary()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.executor.run_container", side_effect=AssertionError("replay ran worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("replay sent request")),
        ):
            with (
                patch(
                    "buddha.gateway.Gateway.__init__", side_effect=AssertionError("active gateway")
                ),
                patch(
                    "buddha.authorization.Authorization.__init__",
                    side_effect=AssertionError("active authorization"),
                ),
                patch(
                    "buddha.native_pipeline._exclusive", side_effect=AssertionError("active lock")
                ),
            ):
                replay = self.run_occasion(authority, transport=RawHTTPTransport(allow_paid=False))
            with self.assertRaises(self.Error):
                self.run_occasion(
                    authority, ordinal=1, transport=RawHTTPTransport(allow_paid=False)
                )
        self.assertEqual(replay, result)
        self.assertEqual(inventory(self.directory), before)
        self.assertEqual(authority.summary(), totals)

    def test_created_slot_without_original_occasion_is_poisoned_and_never_recreated(self):
        self.prepare()
        authority = self.authority()
        slot = self.directory / "validation/0"
        slot.mkdir()
        before = inventory(self.directory)
        with self.offline(), self.assertRaises(self.Error):
            self.run_occasion(authority)
        self.assertFalse((slot / "occasion.json").exists())
        self.assertEqual(list(slot.iterdir()), [])
        self.assertEqual(inventory(self.directory), before)
        self.assertEqual(self.engine.workers, 0)
        self.assertEqual(authority.summary()["operation_count"], 0)

    def test_independent_runtime_mismatch_rejects_before_study_creation(self):
        with self.assertRaises(self.Error):
            self.prepare(expected_runtime_sha256="0" * 64)
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.engine.workers, 0)

    def test_complete_occasion_without_successful_sync_and_reread_stays_poisoned(self):
        from buddha import native_pipeline

        authority = self.authority()
        original_fsync, original_read = os.fsync, native_pipeline._read
        for boundary in ("fsync", "reread"):
            with self.subTest(boundary=boundary):
                self.directory = self.root / ("validation-" + boundary)
                self.prepare()
                occasion = self.directory / "validation/0/occasion.json"

                def fail_sync(descriptor, *, reserved=occasion):
                    if reserved.exists():
                        status, expected = os.fstat(descriptor), reserved.stat()
                        if (status.st_dev, status.st_ino) == (expected.st_dev, expected.st_ino):
                            raise OSError("synthetic reservation fsync failure after full write")
                    return original_fsync(descriptor)

                def fail_reread(path, *args, reserved=occasion, **kwargs):
                    raw = original_read(path, *args, **kwargs)
                    if path == reserved:
                        raise OSError("synthetic reservation reread failure after full write")
                    return raw

                injected = (
                    patch("os.fsync", side_effect=fail_sync)
                    if boundary == "fsync"
                    else patch.object(native_pipeline, "_read", side_effect=fail_reread)
                )
                with (
                    self.offline(),
                    injected,
                    patch(
                        "buddha.candidate_generation.prepare_candidate_generation",
                        side_effect=AssertionError("unconfirmed reservation prepared generation"),
                    ) as preparing,
                    self.assertRaises(self.Error),
                ):
                    self.run_occasion(authority)
                preparing.assert_not_called()
                raw = occasion.read_bytes()
                self.assertEqual(raw, _json(json.loads(raw)))
                before = inventory(self.directory)
                with (
                    self.offline(),
                    patch(
                        "buddha.candidate_generation.prepare_candidate_generation",
                        side_effect=AssertionError("unconfirmed reservation resumed generation"),
                    ) as resumed,
                    self.assertRaises(self.Error),
                ):
                    self.run_occasion(authority)
                resumed.assert_not_called()
                self.assertEqual(inventory(self.directory), before)
                self.assertEqual(self.engine.workers, 0)
                self.assertEqual(authority.summary()["operation_count"], 0)

    def test_prospective_population_custody_and_numeric_limits_reject_before_creation(self):
        original = copy.deepcopy(self.record)
        subset = self.write("subset-tasks.json", self.tasks.select([1]).to_record())
        trimmed = copy.deepcopy(self.custody)
        trimmed["population"] = trimmed["population"][:1]
        subset_custody = self.write("subset-custody.json", trimmed)
        cases = [
            (
                "subset-source-valid-custody",
                {"tasks": self.reference(subset), "custody": self.reference(subset_custody)},
            ),
            ("typed-phase", {"selected_ids": ["1"]}),
            ("boolean-id", {"selected_ids": [True]}),
            ("zero-candidates", {"max_candidates": 0}),
            ("boolean-candidates", {"max_candidates": True}),
            ("zero-looks", {"max_looks": 0}),
            ("zero-repetitions", {"repetitions": 0}),
            ("missing-bound-axis", {"bound_axes": ["utility"]}),
        ]
        for name, field, value in (
            ("exposed", "exposure", "exposed"),
            ("unknown", "exposure", "unknown"),
            ("changed-content", "task_sha256", "0" * 64),
            ("cross-phase-family", "family_id", self.custody["population"][1]["family_id"]),
        ):
            custody = copy.deepcopy(self.custody)
            custody["population"][0][field] = value
            path = self.write("bad-custody-" + name + ".json", custody)
            cases.append((name, {"custody": self.reference(path)}))
        disclosed = copy.deepcopy(self.custody)
        disclosed["disclosures"] = [
            {
                "task_id": 1,
                "process_id": disclosed["process_id"],
                "recipient": "synthetic optimizer",
                "channel": "synthetic disclosure",
                "basis": "explicit test metadata",
            }
        ]
        cases.append(
            (
                "named-process-disclosure",
                {"custody": self.reference(self.write("disclosed-custody.json", disclosed))},
            )
        )
        for name, changes in cases:
            with self.subTest(case=name):
                self.record = copy.deepcopy(original)
                self.record.update(changes)
                self.declaration = self.write("declaration-" + name + ".json", self.record)
                self.directory = self.root / ("rejected-" + name)
                with self.assertRaises(self.Error):
                    self.prepare()
                self.assertFalse(self.directory.exists())
        self.assertEqual(self.engine.workers, 0)

    def test_normalized_prompt_duplicates_crossing_phases_reject_with_valid_source_pins(self):
        e = self.engine
        rows = copy.deepcopy(self.rows)
        rows[1]["prompt"] = "  A SYNTHETIC\n VALIDATION TASK.  "
        dataset = b"".join(_json(row) + b"\n" for row in rows)
        (e.fixture.roots["official"] / "data/tasks.jsonl").write_bytes(dataset)
        e.fixture.release_record["source"] = inventory(e.fixture.roots["official"])
        release = Release.from_record(e.fixture.release_record)
        self.tasks = TaskSet.from_dataset(release, dataset)
        for section in ("generation", "native"):
            roots = {key: Path(value) for key, value in self.record[section]["roots"].items()}
            self.record[section]["selection"] = prepare_selection(
                release, roots, capabilities={gateway_fixtures.CAPABILITY: "profiles/openai.json"}
            ).to_record()
        for row, task in zip(self.custody["population"], self.tasks.tasks, strict=True):
            row["task_sha256"] = sha(_json(task.to_record()))
        self.record["tasks"] = self.reference(
            self.write("duplicate-tasks.json", self.tasks.to_record())
        )
        self.record["custody"] = self.reference(self.write("duplicate-custody.json", self.custody))
        self.declaration = self.write("declaration.json", self.record)
        with self.assertRaises(self.Error):
            self.prepare()
        self.assertFalse(self.directory.exists())

    def test_actual_candidate_ceiling_and_duplicate_content_ignore_path_aliases(self):
        self.record["max_candidates"] = 2
        self.declaration = self.write("declaration.json", self.record)
        self.prepare()
        authority = self.authority()
        refs = [self.source_ref]
        for index in (1, 2):
            source = self.root / ("distinct-source-" + str(index) + ".py")
            source.write_text(
                "# distinct synthetic identity " + str(index) + "\n", encoding="utf-8"
            )
            refs.append(self.reference(source))
        alias = self.root / "same-source-another-path.py"
        alias.write_bytes(Path(self.source_ref["path"]).read_bytes())
        before = inventory(self.directory)
        for candidates in (refs, [self.source_ref, self.reference(alias)]):
            with self.subTest(candidates=candidates), self.offline(), self.assertRaises(self.Error):
                self.run_occasion(authority, candidate_refs=candidates)
            self.assertFalse((self.directory / "validation/0").exists())
            self.assertEqual(inventory(self.directory), before)
        self.assertEqual(authority.summary()["operation_count"], 0)

    def unfinished_without_operations(self, authority):
        with (
            self.offline(),
            patch(
                "buddha.candidate_generation.prepare_candidate_generation",
                side_effect=OSError("synthetic pre-owner preparation interruption"),
            ),
            self.assertRaises(self.Error),
        ):
            self.run_occasion(authority)
        self.assertTrue((self.directory / "validation/0/reservation.json").is_file())
        self.assertEqual(authority.summary()["operation_count"], 0)

    def reject_next_look(self, authority):
        before, totals = inventory(self.directory), authority.summary()
        with (
            self.offline(),
            patch(
                "buddha.candidate_generation.prepare_candidate_generation",
                side_effect=AssertionError("unfinished look was bypassed"),
            ) as preparing,
            self.assertRaises(self.Error),
        ):
            self.run_occasion(authority, ordinal=1)
        preparing.assert_not_called()
        self.assertFalse((self.directory / "validation/1").exists())
        self.assertEqual(inventory(self.directory), before)
        self.assertEqual(authority.summary(), totals)

    def test_unfinished_look_without_operations_cannot_buy_another_look(self):
        self.record["max_looks"] = 2
        self.declaration = self.write("declaration.json", self.record)
        self.prepare()
        authority = self.authority()
        self.unfinished_without_operations(authority)
        self.reject_next_look(authority)

    def test_unknown_original_generation_retains_hold_and_blocks_new_look_before_mkdir(self):
        self.record.update(max_looks=2, repetitions=1)
        self.declaration = self.write("declaration.json", self.record)
        self.prepare()
        authority = self.authority()
        self.engine.generation_timeout_once = True
        with self.offline():
            partial = self.run_occasion(authority)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["reason"], "unknown")
        self.assertGreater(authority.summary()["reserved_microusd"], 0)
        self.assertEqual(self.engine.physical_sends, 1)
        self.assertEqual(self.engine.native_workers, 0)
        self.reject_next_look(authority)

    def test_existing_occasion_cannot_adopt_another_grant_before_preparation(self):
        self.prepare()
        authority = self.authority()
        self.unfinished_without_operations(authority)
        replacement = Authorization.create(
            self.root / "other-grant.sqlite3",
            authorization_id="different-offline-grant",
            budget_microusd=1_000_000,
            max_calls=1000,
            scope="validation study: " + sha(self.declaration.read_bytes()),
        )
        before = inventory(self.directory)
        with (
            self.offline(),
            patch(
                "buddha.candidate_generation.prepare_candidate_generation",
                side_effect=AssertionError("changed grant reached preparation"),
            ) as preparing,
            self.assertRaises(self.Error),
        ):
            self.run_occasion(replacement)
        preparing.assert_not_called()
        self.assertEqual(inventory(self.directory), before)
        self.assertEqual(authority.summary()["operation_count"], 0)
        self.assertEqual(replacement.summary()["operation_count"], 0)

    def test_checked_generation_failure_is_terminal_partial_without_native_or_replacement(self):
        self.prepare()
        authority = self.authority()
        with (
            self.offline(),
            patch("buddha.executor.run_container", side_effect=self.failed_generation_worker),
            patch(
                "buddha.native_evaluation.prepare_evaluation",
                side_effect=AssertionError("failed source prepared native"),
            ) as native,
        ):
            partial = self.run_occasion(authority)
        native.assert_not_called()
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["reason"], "candidate_execution_failed")
        terminal = Path(partial["child"]["path"])
        self.assertEqual(sha(terminal.read_bytes()), partial["child"]["sha256"])
        self.assertEqual(
            json.loads(terminal.read_bytes())["disposition"], "candidate_execution_failed"
        )
        self.assertEqual(self.engine.workers, 1)
        self.assertEqual(self.engine.physical_sends, 0)
        before, totals = inventory(self.directory), authority.summary()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "buddha.executor.run_container", side_effect=AssertionError("replacement worker")
            ),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("replacement request")),
            patch(
                "buddha.candidate_generation.prepare_candidate_generation",
                side_effect=AssertionError("replacement preparation"),
            ),
            patch(
                "buddha.candidate_generation.run_candidate_generation",
                side_effect=AssertionError("replacement generation"),
            ),
            patch(
                "buddha.native_evaluation.run_evaluation",
                side_effect=AssertionError("failed source rejudged"),
            ),
        ):
            replay = self.run_occasion(authority, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(replay, partial)
        self.assertEqual(inventory(self.directory), before)
        self.assertEqual(authority.summary(), totals)

    def failed_generation_worker(self, spec, *, initial, handle, **kwargs):
        self.assertEqual(spec.role, "agent")
        self.engine.workers += 1
        handle({"type": "done", "status": "failed", "reason": "agent_error", "answers": []})
        return self.engine.execution(spec)

    def test_anchored_terminal_failure_permits_next_declared_look_without_native(self):
        self.record["max_looks"] = 2
        self.declaration = self.write("declaration.json", self.record)
        self.prepare()
        authority = self.authority()
        with (
            self.offline(),
            patch("buddha.executor.run_container", side_effect=self.failed_generation_worker),
            patch(
                "buddha.native_evaluation.prepare_evaluation",
                side_effect=AssertionError("failed source reached native"),
            ),
        ):
            first = self.run_occasion(authority)
            second = self.run_occasion(authority, ordinal=1)
        self.assertEqual([first["reason"], second["reason"]], ["candidate_execution_failed"] * 2)
        self.assertEqual(self.engine.workers, 2)
        self.assertEqual(self.engine.physical_sends, 0)
        self.assertTrue((self.directory / "validation/1/reservation.json").is_file())

    def assert_uncompleted_original_owner(self, directory, index, authority):
        owner = directory / "owners" / str(index)
        manifest = json.loads((owner / "manifest.json").read_bytes())
        registered = [
            row for row in authority.summary()["runs"] if row["run_id"] == manifest["run_id"]
        ]
        self.assertEqual(len(registered), 1)
        self.assertEqual(registered[0]["manifest_sha256"], manifest["record_sha256"])
        self.assertEqual(registered[0]["runtime_sha256"], manifest["execution_sha256"])
        self.assertFalse((directory / "completed" / (str(index) + ".json")).exists())
        self.assertFalse((directory / "report.json").exists())
        return manifest

    def reject_before_lower_run(self, authority):
        before, totals = inventory(self.directory), authority.summary()
        funding_sha256 = sha(authority.path.read_bytes())
        with (
            self.offline(),
            patch(
                "buddha.candidate_generation.prepare_candidate_generation",
                side_effect=AssertionError("replacement generation owner"),
            ),
            patch(
                "buddha.native_evaluation.prepare_evaluation",
                side_effect=AssertionError("replacement native owner"),
            ),
            patch(
                "buddha.candidate_generation.run_candidate_generation",
                side_effect=AssertionError("preflight entered generation run/replay"),
            ),
            patch(
                "buddha.native_evaluation.run_evaluation",
                side_effect=AssertionError("preflight entered native run"),
            ),
            patch.object(
                RawHTTPTransport, "send_prepared", side_effect=AssertionError("provider dispatch")
            ),
            self.assertRaises(self.Error),
        ):
            self.run_occasion(authority)
        self.assertEqual(inventory(self.directory), before)
        self.assertEqual(authority.summary(), totals)
        self.assertEqual(sha(authority.path.read_bytes()), funding_sha256)

    def test_real_uncompleted_generation_owner_cannot_adopt_a_changed_legal_budget(self):
        from buddha import candidate_generation

        self.prepare()
        authority = self.authority()
        original = candidate_generation.prepare_candidate_generation
        created = []

        def changed_then_interrupt(directory, **kwargs):
            kwargs["budget_microusd"] += 1
            result = original(directory, **kwargs)
            created.append(Path(result))
            raise KeyboardInterrupt

        with (
            self.offline(),
            patch.object(
                candidate_generation,
                "prepare_candidate_generation",
                side_effect=changed_then_interrupt,
            ),
            self.assertRaises((KeyboardInterrupt, self.Error)),
        ):
            self.run_occasion(authority)
        self.assertEqual(len(created), 1)
        manifest = self.assert_uncompleted_original_owner(created[0], 0, authority)
        self.assertEqual(
            manifest["settings"]["budget_microusd"],
            self.record["generation"]["budget_microusd"] + 1,
        )
        self.assertEqual(self.engine.workers, 0)
        self.reject_before_lower_run(authority)

    def test_real_uncompleted_native_owner_cannot_adopt_alternate_bound_definition(self):
        from buddha import native_evaluation

        self.prepare()
        authority = self.authority()
        original = native_evaluation.prepare_evaluation
        created = []

        def changed_then_interrupt(directory, **kwargs):
            definition = json.loads(kwargs["descriptor"].read_bytes())
            definition["native"]["budget_microusd"] += 1
            alternate = self.write("alternate-native-definition.json", definition)
            result = original(directory, **(kwargs | {"descriptor": alternate}))
            created.append(Path(result))
            raise KeyboardInterrupt

        with (
            self.offline(),
            patch.object(
                native_evaluation, "prepare_evaluation", side_effect=changed_then_interrupt
            ),
            self.assertRaises((KeyboardInterrupt, self.Error)),
        ):
            self.run_occasion(authority)
        self.assertEqual(len(created), 1)
        self.assert_uncompleted_original_owner(created[0], 1, authority)
        context = json.loads((created[0] / "context.json").read_bytes())
        self.assertEqual(context["descriptor"], str(self.root / "alternate-native-definition.json"))
        original_definition = created[0].parent / "evaluation.json"
        self.assertNotEqual(context["descriptor"], str(original_definition))
        expected = json.loads(original_definition.read_bytes())
        alternate = json.loads(Path(context["descriptor"]).read_bytes())
        self.assertEqual(alternate["source_generation"], expected["source_generation"])
        self.assertEqual(self.engine.workers, 1)
        self.assertEqual(self.engine.physical_sends, 1)
        alternate_sha256 = sha(Path(context["descriptor"]).read_bytes())
        self.reject_before_lower_run(authority)
        self.assertEqual(sha(Path(context["descriptor"]).read_bytes()), alternate_sha256)

    def test_canonical_partial_corruption_cannot_replace_original_event_evidence(self):
        self.prepare()
        authority = self.authority()
        self.unfinished_without_operations(authority)
        observation = self.directory / "validation/0/observations/0.json"
        original = observation.read_bytes()
        baseline = json.loads(original)
        self.assertEqual(baseline["coverage"]["generated_cells"], 0)
        self.assertEqual(baseline["coverage"]["native_cells"], 0)
        self.assertIsNone(baseline["child"])
        with (
            self.offline(),
            patch(
                "buddha.candidate_generation.prepare_candidate_generation",
                side_effect=AssertionError("valid partial reached original preparation"),
            ) as preparing,
            self.assertRaisesRegex(AssertionError, "valid partial reached original preparation"),
        ):
            self.run_occasion(authority)
        preparing.assert_called_once()
        self.assertEqual(observation.read_bytes(), original)
        occasion = self.directory / "validation/0/occasion.json"
        mutations = []
        for field, value in (
            ("reason", "candidate_execution_failed"),
            ("claim", "an altered retained claim"),
            ("child", {"path": str(occasion), "sha256": sha(occasion.read_bytes())}),
        ):
            changed = copy.deepcopy(baseline)
            changed[field] = value
            mutations.append((field, changed))
        changed = copy.deepcopy(baseline)
        changed["position"]["repetition"] = 1
        mutations.append(("valid-range-wrong-frontier", changed))
        changed = copy.deepcopy(baseline)
        changed["coverage"]["generated_cells"] = 1
        changed["coverage"]["unattempted_generations"] -= 1
        mutations.append(("plausible-but-unbacked-coverage", changed))
        for name, changed in mutations:
            with self.subTest(mutation=name):
                observation.write_bytes(_json(changed))
                before, totals = inventory(self.directory), authority.summary()
                try:
                    with (
                        self.offline(),
                        patch(
                            "buddha.candidate_generation.prepare_candidate_generation",
                            side_effect=AssertionError("corrupted partial reached preparation"),
                        ) as preparing,
                        patch.object(
                            RawHTTPTransport,
                            "send_prepared",
                            side_effect=AssertionError("provider dispatch"),
                        ),
                        self.assertRaises(self.Error),
                    ):
                        self.run_occasion(authority)
                    preparing.assert_not_called()
                    self.assertEqual(inventory(self.directory), before)
                    self.assertEqual(authority.summary(), totals)
                finally:
                    observation.write_bytes(original)
        self.assertEqual(self.engine.workers, 0)
        self.assertEqual(self.engine.physical_sends, 0)

    def test_real_ordinary_native_unknown_partial_repeats_without_losing_original_evidence(self):
        self.record["repetitions"] = 1
        self.declaration = self.write("declaration.json", self.record)
        self.prepare()
        authority = self.authority()
        self.engine.native_timeout_once = True
        with self.offline():
            partial = self.run_occasion(authority)
        self.assertEqual(partial["reason"], "unknown")
        self.assertEqual(partial["position"]["stage"], "native")
        self.assertEqual(partial["coverage"]["generated_cells"], 1)
        self.assertEqual(partial["coverage"]["native_cells"], 0)
        child = Path(partial["child"]["path"])
        child_raw = child.read_bytes()
        lower = json.loads(child_raw)
        self.assertEqual(sha(child_raw), partial["child"]["sha256"])
        self.assertEqual(lower["reason"], "unknown")
        self.assertEqual(len(lower["stages"]), 1)
        report_path = child.parent.parent / lower["attempt"] / "report.json"
        report_raw = report_path.read_bytes()
        self.assertEqual(lower["stages"][-1], json.loads(report_raw))
        outer = self.directory / "validation/0" / partial["observation"]
        outer_raw = outer.read_bytes()
        totals = authority.summary()
        self.assertGreater(totals["reserved_microusd"], 0)
        self.assertEqual(self.engine.physical_sends, 2)
        self.native_partial_evidence = {
            "outer": partial,
            "outer_sha256": sha(outer_raw),
            "actual_lower_observation": lower,
            "lower_sha256": sha(child_raw),
            "actual_attempt_report": json.loads(report_raw),
            "attempt_report_sha256": sha(report_raw),
        }
        with (
            self.offline(),
            patch.object(
                RawHTTPTransport,
                "send_prepared",
                side_effect=AssertionError("unknown redispatched"),
            ),
        ):
            repeated = self.run_occasion(authority)
        self.assertEqual(repeated["status"], "incomplete")
        # The original unknown holds shared spending closed before another dispatch.
        self.assertEqual(repeated["reason"], "authority")
        self.assertEqual(self.engine.physical_sends, 2)
        for field in ("operation_count", "spent_microusd", "reserved_microusd"):
            self.assertEqual(authority.summary()[field], totals[field])
        self.assertEqual(outer.read_bytes(), outer_raw)
        self.assertEqual(child.read_bytes(), child_raw)
        self.assertEqual(report_path.read_bytes(), report_raw)

    def test_known_native_reply_resumes_original_owner_and_preserves_historical_partials(self):
        self.record["repetitions"] = 1
        self.declaration = self.write("declaration.json", self.record)
        self.prepare()
        authority = self.authority()
        worker, interrupted = self.execute, False

        def interrupt_after_native_frames(spec, **kwargs):
            nonlocal interrupted
            result = worker(spec, **kwargs)
            if spec.role == "evaluator" and not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return result

        with (
            self.offline(),
            patch("buddha.executor.run_container", side_effect=interrupt_after_native_frames),
            self.assertRaises(KeyboardInterrupt) as stopped,
        ):
            self.run_occasion(authority)
        self.assertTrue(interrupted)
        partial = stopped.exception.partial
        self.assertEqual(partial["reason"], "cancelled")
        self.assertEqual(partial["position"]["stage"], "native")
        self.assertEqual(partial["coverage"]["generated_cells"], 1)
        self.assertEqual(partial["coverage"]["native_cells"], 0)
        outer = self.directory / "validation/0" / partial["observation"]
        outer_raw = outer.read_bytes()
        child = Path(partial["child"]["path"])
        child_raw = child.read_bytes()
        self.assertEqual(sha(child_raw), partial["child"]["sha256"])
        lower = json.loads(child_raw)
        evaluation = child.parent.parent
        self.assertEqual(lower["stages"], [])
        self.assertFalse((evaluation / lower["attempt"] / "report.json").exists())
        self.assertTrue((evaluation / lower["attempt"] / "artifacts/partitions.jsonl").is_file())
        owner = evaluation / "owners/1"
        manifest_raw = (owner / "manifest.json").read_bytes()

        def history():
            return read_gateway_history(
                owner,
                manifest_sha256=json.loads(manifest_raw)["record_sha256"],
                ledger_sha256=sha((owner / "operations.sqlite3").read_bytes()),
            )

        original_history = history()
        self.assertEqual(len(original_history.operations), 1)
        operation = original_history.operations[0]
        self.assertEqual(operation.status, "completed")
        self.assertEqual(self.engine.physical_sends, 2)
        generated = evaluation.parent / "generation/report.json"
        for name in ("wrong-stage-child", "wrong-cell"):
            with self.subTest(corruption=name):
                altered = copy.deepcopy(partial)
                if name == "wrong-stage-child":
                    altered["child"] = self.reference(generated)
                else:
                    altered["position"]["arm_index"] = 1
                outer.write_bytes(_json(altered))
                try:
                    self.reject_before_lower_run(authority)
                finally:
                    outer.write_bytes(outer_raw)
        with self.offline():
            complete = self.run_occasion(authority)
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(self.engine.physical_sends, 6)
        self.assertEqual(history().operations, original_history.operations)
        self.assertEqual((owner / "manifest.json").read_bytes(), manifest_raw)
        self.assertEqual(outer.read_bytes(), outer_raw)
        self.assertEqual(child.read_bytes(), child_raw)
        self.known_reply_evidence = {
            "operation_id": operation.operation_id,
            "request_sha256": operation.request_sha256,
            "provider_request_id": operation.provider_request_id,
            "actual_microusd": operation.actual_microusd,
            "original_outer_coverage": partial["coverage"],
            "outer_sha256": sha(outer_raw),
            "lower_sha256": sha(child_raw),
            "final_physical_sends": self.engine.physical_sends,
        }
        before = inventory(self.directory)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.gateway.Gateway.__init__", side_effect=AssertionError("active gateway")),
            patch(
                "buddha.authorization.Authorization.__init__",
                side_effect=AssertionError("active authority"),
            ),
            patch("buddha.native_pipeline._exclusive", side_effect=AssertionError("active lock")),
            patch("buddha.executor.run_container", side_effect=AssertionError("replay worker")),
            patch.object(
                RawHTTPTransport, "send_prepared", side_effect=AssertionError("replay send")
            ),
        ):
            replay = self.run_occasion(authority, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(replay, complete)
        self.assertEqual(inventory(self.directory), before)

    @classmethod
    def capacity_metadata_pool(cls):
        if not hasattr(cls, "_capacity_pool"):
            temporary = tempfile.TemporaryDirectory()
            cls.addClassCleanup(temporary.cleanup)
            cls.addClassCleanup(lambda: delattr(cls, "_capacity_pool"))
            cls._capacity_pool = []
            for index in range(1024):
                path = Path(temporary.name).resolve() / (str(index) + ".json")
                path.write_bytes(_json({"synthetic_metadata": index}))
                cls._capacity_pool.append(cls.reference(path))
        return cls._capacity_pool

    def projected_owner_paths(self, *, cell=None):
        from buddha import candidate_generation, native_evaluation

        context = json.loads((self.directory / "context.json").read_bytes())
        common = {Path(path) for path in context["original_controls"]}
        common.update(self.directory / name for name in context["internal_controls"])
        common.update({self.directory / "context.json", Path(self.source_ref["path"])})
        slot = self.directory / "validation/0"
        cell = cell or slot / "arms/0/tasks/0/repetitions/0"
        generation, evaluation = cell / "generation", cell / "evaluation"
        reservation = {slot / "occasion.json", slot / "reservation.json"}
        runtime = Path(self.record["generation"]["runtime"]["path"])
        task, recipe = cell / "task.json", cell / "generation.json"
        generated_attempt = generation / "attempts/0-0"
        generated_source = {
            generation / "owners/0/manifest.json",
            generation / "owners/0/operations.sqlite3",
            generation / "completed/0.json",
            generated_attempt / "report.json",
            generated_attempt / "session/report.json",
            generated_attempt / "session/done.json",
            generated_attempt / "session/answers.json",
            generation / "context.json",
            recipe,
            task,
            runtime,
        }
        self.assertEqual(len(generated_source), 11)
        planned = [
            common
            | reservation
            | {task, recipe, generation / "context.json", runtime}
            | set(candidate_generation._sources("buddha.candidate-generation.v2"))
        ]
        native_common = common | reservation | {task, recipe, cell / "evaluation.json"}
        available, seals, first = {evaluation / "native-answers.jsonl"}, set(), set()
        for index, stage in enumerate(self.record["stages"], 1):
            current = (
                native_common
                | generated_source
                | {evaluation / "context.json", evaluation / ("command-" + str(index) + ".json")}
                | available
                | seals
                | {
                    evaluation / "staging" / str(index) / (str(ordinal) + ".bin")
                    for ordinal in range(len(stage["inputs"]))
                }
                | set(native_evaluation._sources())
            )
            if index == 1:
                first = set(current)
            else:
                current |= first | {evaluation / "owners/1/manifest.json"}
            planned.append(current)
            seals.add(evaluation / "completed" / (str(index) + ".json"))
            available.update(
                evaluation / "attempts" / (str(index) + "-0") / "artifacts" / output["path"]
                for output in stage["outputs"]
            )
        return planned

    def prepare_capacity_case(self, *, native_edge):
        self.directory = self.root / "capacity-counting-study"
        self.prepare()
        baseline = [len(paths) for paths in self.projected_owner_paths()]
        filler_count = 1024 - (max(baseline) if native_edge else baseline[0])
        self.assertGreaterEqual(filler_count, 0)
        custody = copy.deepcopy(self.custody)
        custody["evidence"].extend(self.capacity_metadata_pool()[:filler_count])
        self.record["custody"] = self.reference(self.write("capacity-custody.json", custody))
        self.declaration = self.write("capacity-declaration.json", self.record)
        self.directory = self.root / "capacity-final-study"
        self.prepare()
        actual = [len(paths) for paths in self.projected_owner_paths()]
        self.assertEqual(actual, [value + filler_count for value in baseline])
        self.capacity_evidence = {
            "baseline": baseline,
            "filler_files": filler_count,
            "final": actual,
        }
        return self.authority(), actual

    def test_generation_fits_but_native_input_union_overflows_before_look_reservation(self):
        authority, counts = self.prepare_capacity_case(native_edge=False)
        self.assertEqual(counts[0], 1024)
        self.assertGreater(max(counts[1:]), 1024)
        before, totals = inventory(self.directory), authority.summary()
        with (
            self.offline(),
            patch(
                "buddha.candidate_generation.prepare_candidate_generation",
                side_effect=AssertionError("native capacity was checked after look consumption"),
            ) as preparing,
            patch(
                "buddha.native_evaluation.prepare_evaluation",
                side_effect=AssertionError("native capacity overflow reached prepare"),
            ),
            self.assertRaises(self.Error),
        ):
            self.run_occasion(authority)
        preparing.assert_not_called()
        self.assertFalse((self.directory / "validation/0").exists())
        self.assertEqual(inventory(self.directory), before)
        self.assertEqual(authority.summary(), totals)

    def test_exact_native_input_capacity_edge_reaches_original_prepare_without_work(self):
        authority, counts = self.prepare_capacity_case(native_edge=True)
        self.assertEqual(max(counts), 1024)
        with (
            self.offline(),
            patch(
                "buddha.candidate_generation.prepare_candidate_generation",
                side_effect=AssertionError("exact input edge reached prepare"),
            ) as preparing,
            self.assertRaisesRegex(AssertionError, "exact input edge reached prepare"),
        ):
            self.run_occasion(authority)
        preparing.assert_called_once()
        self.assertEqual(self.engine.workers, 0)
        self.assertEqual(authority.summary()["operation_count"], 0)


if __name__ == "__main__":
    unittest.main()
