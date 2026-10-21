"""The frozen forty-target reader never resumes or changes the supplied study."""

import copy
import ctypes
import hashlib
import io
import json
import math
import os
import sqlite3
import unittest
from contextlib import closing, contextmanager, redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import test_meas02_native_audit as fixtures
import test_meas02_partial as partials

from buddha.authorization import Authorization
from buddha.gateway import Gateway, RawHTTPTransport
from buddha.releases import _json, inventory

SOURCE = Path(__file__).resolve().parents[1] / "docs/conformance/meas02-results.py"
namespace = {"__name__": "meas02_results_test", "__file__": str(SOURCE)}
exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), namespace)  # nosec B102
analyze_results = namespace["analyze_results"]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture = fixtures.NativeAuditTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture.output_mutation = self.correct_relations
        fixture.prepare()
        batches = fixtures.audit.materializer.materialize(
            Path(fixture.record["pack"]).read_bytes(), Path(fixture.record["proposal"]).read_bytes()
        )
        self.targets = {
            target["target_id"]: target for batch in batches for target in batch["targets"]
        }
        expectations = json.loads(
            (SOURCE.parents[2] / "tests/fixtures/meas01-expectations.json").read_bytes()
        )
        self.cases = {case["item"]["id"]: case for case in expectations["cases"]}
        # Synthetic official sources are explicit fixtures; only the actual
        # confined engineering smoke uses the unchanged upstream reference.
        self.reference = patch.object(namespace["C"], "_reference", return_value=None)
        self.reference.start()
        self.addCleanup(self.reference.stop)

    def correct_relations(self, rows):
        for row in rows:
            target = self.targets[row["id"]]
            case = self.cases.get(target["item_id"])
            if case:
                groups = {
                    identity: i
                    for i, group in enumerate(case["assessment"]["groups"])
                    for identity in group
                }
                row["partition"] = [
                    groups[identity] for identity in target["answer_ids_in_pack_order"]
                ]
                row["distinct"] = len(set(row["partition"]))

    @contextmanager
    def readonly(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("reader executed or wrote")

        real_connect, real_open = sqlite3.connect, Path.open

        def connect(path, *args, **kwargs):
            if path != ":memory:":
                forbidden()
            return real_connect(path, *args, **kwargs)

        def opened(path, mode="r", *args, **kwargs):
            if any(char in mode for char in "wax+"):
                forbidden()
            return real_open(path, mode, *args, **kwargs)

        with (
            patch.object(Authorization, "__init__", side_effect=forbidden),
            patch.object(Gateway, "__init__", side_effect=forbidden),
            patch.object(namespace["C"], "check_native_audit", side_effect=forbidden),
            patch.object(namespace["C"], "_state", side_effect=forbidden),
            patch.object(namespace["C"], "_exclusive", side_effect=forbidden),
            patch("getpass.getpass", side_effect=forbidden),
            patch("os.environ.get", side_effect=forbidden),
            patch("http.client.HTTPSConnection", side_effect=forbidden),
            patch("socket.create_connection", side_effect=forbidden),
            patch("sqlite3.connect", side_effect=connect),
            patch.object(Path, "open", opened),
        ):
            yield

    def read(self, observation=None):
        before = inventory(self.fixture.directory)
        authority = self.fixture.authority.path.read_bytes()
        with self.readonly():
            result = analyze_results(
                self.fixture.directory,
                authorization=self.fixture.authority.path,
                observation=observation,
            )
        self.assertEqual(inventory(self.fixture.directory), before)
        self.assertEqual(self.fixture.authority.path.read_bytes(), authority)
        return result

    def complete(self):
        return self.fixture.run_study()

    def partial(self, rows=1):
        helper = partials.NativeAuditPartialTests("runTest")
        helper.fixture = self.fixture
        self.fixture.container = helper.stopped_container(partial_rows=rows, reason="protocol")
        result = self.fixture.run_study()
        return self.fixture.directory / result["observation"]

    def change_authority(self, sql, values):
        # Intentionally corrupt fixture data while preserving the native DDL.
        with closing(sqlite3.connect(self.fixture.authority.path)) as db, db:
            triggers = db.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
            for name, _ in triggers:
                db.execute('DROP TRIGGER "' + name + '"')
            db.execute(sql, values)
            for _, statement in triggers:
                db.execute(statement)

    def reseal_batch(self, index, mutate, mutate_report=None):
        directory = self.fixture.directory
        seal_path = directory / f"completed/{index}.json"
        seal = json.loads(seal_path.read_bytes())
        attempt = directory / seal["attempt"]
        output = attempt / "artifacts/v1.1/partitions.jsonl"
        rows = [json.loads(line) for line in output.read_bytes().splitlines()]
        mutate(rows)
        output.write_bytes(b"".join(_json(row) + b"\n" for row in rows))
        report_path = attempt / "report.json"
        report = json.loads(report_path.read_bytes())
        report["artifacts"]["v1.1/partitions.jsonl"] = sha(output.read_bytes())
        if mutate_report:
            mutate_report(report)
        report_path.write_bytes(_json(report) + b"\n")
        seal["files"] = inventory(attempt)
        seal_path.write_bytes(_json(seal))
        digest = sha(seal_path.read_bytes())
        manifest = json.loads((directory / f"owners/{index}/manifest.json").read_bytes())
        self.change_authority(
            "UPDATE auth_deactivations SET reason=? WHERE run_id=?",
            ("MEAS02 completed: " + digest, manifest["run_id"]),
        )
        final_path = directory / "report.json"
        final = json.loads(final_path.read_bytes())
        final["batches"][index] = report
        final["batch_seals"][str(index)] = digest
        final_path.write_bytes(_json(final))

    def test_complete_all_targets_use_resolved_groups_and_preserve_uncertainty(self):
        self.complete()
        result = self.read()
        self.assertEqual(result["format"], "buddha.meas02-target-results.v1")
        self.assertEqual(result["scope"], "complete")
        self.assertEqual(len(result["targets"]), 40)
        self.assertEqual(sum(row["expectation"] == "resolved" for row in result["targets"]), 23)
        self.assertEqual(sum(row["expectation"] == "uncertain" for row in result["targets"]), 17)
        self.assertTrue(all(row["measurement"] == "measured" for row in result["targets"]))
        for row in result["targets"]:
            self.assertEqual(
                sum(row["counts"].values()), math.comb(len(row["answer_ids_in_pack_order"]), 2)
            )
        self.assertEqual([row["target_count"] for row in result["occasions"]], [22, 6, 6, 6])
        self.assertTrue(all(row["disagreeing_relations"] == 0 for row in result["occasions"]))
        self.assertNotIn("accuracy", result)
        self.assertNotIn("utility", result)
        self.assertTrue(result["limits"])

    def test_real_equivalence_and_distinctness_errors_are_both_visible(self):
        def mistaken(rows):
            self.correct_relations(rows)
            for row in rows:
                target = self.targets[row["id"]]
                if target["item_id"] in self.cases:
                    row["partition"] = (
                        [0] * len(row["generations"])
                        if len(set(row["partition"])) > 1
                        else list(range(len(row["generations"])))
                    )
                    row["distinct"] = len(set(row["partition"]))

        self.fixture.output_mutation = mistaken
        self.complete()
        result = self.read()
        errors = [
            pair
            for row in result["targets"]
            for pair in row["relations"]
            if pair["outcome"] == "disagree"
        ]
        self.assertEqual({pair["expected"] for pair in errors}, {"equivalent", "distinct"})

    def test_numeric_class_renumbering_and_seeded_rows_use_original_pack_order(self):
        def renumber(rows):
            self.correct_relations(rows)
            for row in rows:
                row["partition"] = [100 + 7 * value for value in row["partition"]]

        self.fixture.output_mutation = renumber
        self.complete()
        result = self.read()
        for target in result["targets"]:
            if target["expectation"] == "resolved":
                self.assertTrue(all(pair["outcome"] == "agree" for pair in target["relations"]))
        self.assertEqual(
            {row["occasion"] for row in result["targets"]},
            {"baseline", "same-order-repeat", "order-seed-0", "order-seed-20261020"},
        )
        original = copy.deepcopy(result["targets"][0]["partition"])
        result["targets"][0]["partition"].clear()
        self.assertEqual(self.read()["targets"][0]["partition"], original)

    def test_partial_requires_explicit_selection_and_never_adopts_other_observations(self):
        first = self.partial(1)
        second = self.partial(2)
        with self.assertRaises(ValueError):
            self.read()
        a, b = self.read(first), self.read(second)
        self.assertEqual(sum(row["measurement"] == "measured" for row in a["targets"]), 1)
        self.assertEqual(sum(row["measurement"] == "measured" for row in b["targets"]), 2)
        self.assertEqual(a["scope"], "partial")
        self.assertEqual(
            a["selected_observation"], first.relative_to(self.fixture.directory).as_posix()
        )
        self.assertTrue(any(row["measurement"] == "missing" for row in a["targets"]))

    def test_selected_older_partial_does_not_adopt_later_complete_batches(self):
        first = self.partial(1)
        self.fixture.container = fixtures.NativeAuditTests.container.__get__(self.fixture)
        self.complete()
        result = self.read(first)
        self.assertEqual(sum(row["measurement"] == "measured" for row in result["targets"]), 1)
        self.assertNotEqual(result["captured_accounting"], result["current_accounting"])

    def test_all40_rows_in_late_exit_observation_still_remain_partial(self):
        original = self.fixture.container

        def late_exit(spec, **kwargs):
            result = original(spec, **kwargs)
            return (
                replace(result, exit_code=9)
                if kwargs["initial"]["command"]["index"] == 3
                else result
            )

        self.fixture.container = late_exit
        stopped = self.fixture.run_study()
        selected = self.fixture.directory / stopped["observation"]
        result = self.read(selected)
        self.assertEqual(result["scope"], "partial")
        self.assertEqual(result["study_status"], "incomplete")
        self.assertEqual(sum(row["measurement"] == "measured" for row in result["targets"]), 40)
        self.assertFalse((self.fixture.directory / "report.json").exists())

    def test_literal_source_artifact_and_bound_input_hash_drift_are_rejected(self):
        self.complete()
        output = next(self.fixture.directory.glob("attempts/0-*/artifacts/v1.1/partitions.jsonl"))
        original = output.read_bytes()
        output.write_bytes(original + b"\n")
        with self.assertRaises(ValueError):
            self.read()
        output.write_bytes(original)
        data = self.fixture.directory / "inputs/0/generations.jsonl"
        data.write_bytes(data.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            self.read()

    def test_resealed_wrong_text_ids_duplicate_rows_and_bool_classes_are_rejected(self):
        self.complete()
        pristine = {
            path: path.read_bytes() for path in self.fixture.directory.rglob("*") if path.is_file()
        }
        authority = self.fixture.authority.path.read_bytes()
        for mutate in (
            lambda rows: rows[0].update(prompt="changed"),
            lambda rows: rows[0]["generations"].__setitem__(0, "changed"),
            lambda rows: rows[0].update(id="foreign"),
            lambda rows: rows.append(copy.deepcopy(rows[0])),
            lambda rows: rows[0].update(partition=[False] * len(rows[0]["generations"])),
        ):
            for path, raw in pristine.items():
                path.write_bytes(raw)
            self.fixture.authority.path.write_bytes(authority)
            self.reseal_batch(0, mutate)
            with self.assertRaises(ValueError):
                self.read()

    def test_unanchored_complete_and_different_authority_are_rejected(self):
        self.complete()
        manifest = json.loads((self.fixture.directory / "owners/0/manifest.json").read_bytes())
        self.change_authority(
            "DELETE FROM auth_deactivations WHERE run_id=?", (manifest["run_id"],)
        )
        with self.assertRaises(ValueError):
            self.read()
        other = Authorization.create(
            self.fixture.root / "foreign.sqlite3",
            authorization_id="foreign",
            budget_microusd=100_000,
            max_calls=20,
            scope="synthetic other grant",
        )
        with self.readonly(), self.assertRaises(ValueError):
            analyze_results(self.fixture.directory, authorization=other.path)

    def test_partial_pointer_escape_and_resealed_wrong_declared_coverage_are_rejected(self):
        selected = self.partial(1)
        original = selected.read_bytes()
        record = json.loads(original)
        record["coverage"]["partial_target_ids"] = []
        selected.write_bytes(_json(record))
        with self.assertRaises(ValueError):
            self.read(selected)
        selected.write_bytes(original)
        outside = self.fixture.root / "outside.json"
        outside.write_bytes(original)
        with self.assertRaises(ValueError):
            self.read(outside)

    def test_busy_sidecars_and_changed_pinned_engineering_source_fail_without_writes(self):
        self.complete()
        sidecar = self.fixture.authority.path.with_name(
            self.fixture.authority.path.name + "-journal"
        )
        sidecar.write_bytes(b"busy")
        with self.assertRaises(ValueError):
            self.read()
        sidecar.unlink()
        with patch.dict(namespace, {"CONTROLLER_SHA256": "0" * 64}), self.assertRaises(ValueError):
            self.read()

    def test_captured_totals_and_row_amounts_reject_boolean_integer_aliases(self):
        selected = self.partial(1)
        original = selected.read_bytes()
        for field in namespace["FINANCIALS"]:
            record = json.loads(original)
            record["authorization"][field] = False
            selected.write_bytes(_json(record))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.read(selected)
        selected.write_bytes(original)
        ledger = Gateway(
            self.fixture.directory / "owners/0", transport=RawHTTPTransport(allow_paid=False)
        ).ledger
        ledger.reserve("e" * 64, "0" * 64, 1)
        ledger.dispatch("e" * 64)
        ledger.mark_unknown("e" * 64)
        captured = fixtures.audit.record_stopped_audit(self.fixture.directory)
        selected = self.fixture.directory / captured["observation"]
        captured["evidence"]["operations"][0]["reserve_microusd"] = True
        captured["authorization"]["operation_count"] = True
        selected.write_bytes(_json(captured))
        with self.assertRaises(ValueError):
            self.read(selected)

    def test_resealed_false_exit_code_cannot_claim_successful_native_execution(self):
        self.complete()
        self.reseal_batch(
            0,
            lambda rows: None,
            lambda report: report["execution"].update(exit_code=False),
        )
        with self.assertRaises(ValueError):
            self.read()

    def test_cli_only_writes_new_report_and_rejects_output_under_protected_roots(self):
        self.complete()
        output = self.fixture.root / "diagnostic.json"
        args = [
            "--run",
            str(self.fixture.directory),
            "--authorization",
            str(self.fixture.authority.path),
            "--out",
            str(output),
        ]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(namespace["main"](args), 0)
            self.assertEqual(namespace["main"](args), 2)
            self.assertEqual(namespace["main"](["--pasted-offline-canary"]), 2)
        self.assertNotIn("pasted-offline-canary", err.getvalue())
        self.assertEqual(json.loads(output.read_bytes())["scope"], "complete")
        for path in (
            self.fixture.directory / "report-new.json",
            self.fixture.fixture.roots["host"] / "report-new.json",
            self.fixture.authority.path,
        ):
            args[-1] = str(path)
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(namespace["main"](args), 2)
        if os.name == "nt":
            host = self.fixture.fixture.roots["host"]
            short = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetShortPathNameW(str(host), short, len(short))
            if length and short.value.casefold() != str(host).casefold():
                args[-1] = str(Path(short.value) / "short-path-report.json")
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(namespace["main"](args), 2)
                self.assertFalse((host / "short-path-report.json").exists())


if __name__ == "__main__":
    unittest.main()
