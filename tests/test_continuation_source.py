"""REC-04a: sealed source receipts and scientific compatibility, without spending."""

import hashlib
import json
import sqlite3
import stat
import tempfile
import unittest
import zipfile
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from buddha.benchmark import _canonical
from buddha.continuation import read_source
from buddha.evaluation import ValidationError
from buddha.ledger import Ledger
from buddha.policy import Policy
from buddha.provider import ModelSpec, Reply
from buddha.run import RunSettings, _generation, _sha
from buddha.search import SearchSpec, _contracts, prepare_search

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs/snapshots/pilot-runtime-2026-10-19.zip"
ARCHIVE_SHA = "bd32c4d50339e2f2e1cadf01f5872fa3c1cdf12c196e7676a18d6fe96bd534e0"


def settings():
    profiles = [
        ModelSpec("replay", model, 100000, cap, 1000000, 1000000, "offline fixture")
        for model, cap in [("generator", 4096), ("partition", 16000), ("quality", 16000)]
    ]
    return RunSettings(*profiles, budget_microusd=50_000_000, max_calls=128, bounds_verified=False)


def old_contracts():
    with zipfile.ZipFile(ARCHIVE) as bundle:
        index = json.loads(bundle.read("source-index.json"))["files_sha256"]
    current = _contracts()
    result = {
        key: current[key]
        for key in (
            "system_sha256",
            "proposal_schema_sha256",
            "parent_rule",
            "proposal_role",
            "feedback",
            "feedback_max_canonical_bytes",
            "seed_policies",
        )
    }
    result["controller_sha256"] = index["buddha/search.py"]
    result["source_sha256"] = {
        "buddha." + name: index["buddha/" + name + ".py"]
        for name in (
            "archive",
            "benchmark",
            "evaluation",
            "ledger",
            "policy",
            "provider",
            "run",
            "splits",
        )
    }
    return result


class ContinuationSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "original"
        dataset = self.root / "dataset.jsonl"
        dataset.write_text(
            "".join(
                json.dumps({"id": name, "prompt": text}) + "\n"
                for name, text in [
                    ("dev-a", "Give one short idea."),
                    ("dev-b", "Choose a useful action."),
                    ("validation", "VALIDATION_CANARY"),
                    ("final", "FINAL_CANARY"),
                ]
            ),
            encoding="utf-8",
        )
        digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
        self.selected = settings()
        with patch("buddha.search._contracts", return_value=old_contracts()):
            prepare_search(
                self.directory,
                dataset_path=dataset,
                expected_dataset_sha256=digest,
                settings=self.selected,
                spec=SearchSpec(iterations=1, screen_size=1, seed=7),
                splits={
                    "development": ["dev-a", "dev-b"],
                    "validation": ["validation"],
                    "final": ["final"],
                },
                synthetic=True,
            )
        self.manifest = json.loads((self.directory / "manifest.json").read_bytes())
        self.manifest_hash = self.manifest["record_sha256"]
        self.database = self.directory / "operations.sqlite3"
        self.ledger = Ledger(
            self.database,
            run_id=self.manifest["run_id"],
            manifest_sha256=self.manifest_hash,
            budget_microusd=50_000_000,
            max_calls=128,
        )
        self.call = _generation(self.selected.generation, "Give one short idea.")
        self.receipts = []
        for index in range(10):
            operation_id = self.operation(index)
            self.ledger.reserve(
                operation_id, self.call.fingerprint(), self.call.spec.reserve_microusd()
            )
            self.ledger.dispatch(operation_id)
            if index < 9:
                reply = Reply(
                    "Saved answer " + str(index),
                    "generator",
                    "request-" + str(index),
                    10,
                    5,
                    "stop",
                )
                self.ledger.complete(
                    operation_id,
                    response=reply.to_record(),
                    actual_microusd=15,
                    provider_request_id=reply.provider_request_id,
                )
                self.receipts.append(reply)
            else:
                self.ledger.mark_unknown(operation_id)

    def operation(self, index):
        return _sha(
            [
                self.manifest["run_id"],
                "candidate",
                Policy().fingerprint(),
                "dev-a",
                "generation",
                index,
            ]
        )

    def read(self, **changes):
        arguments = {
            "manifest_sha256": self.manifest_hash,
            "ledger_sha256": hashlib.sha256(self.database.read_bytes()).hexdigest(),
            "archived_runtime_zip": ARCHIVE,
            "archived_runtime_sha256": ARCHIVE_SHA,
        }
        arguments.update(changes)
        return read_source(self.directory, **arguments)

    def files(self):
        return {
            str(path.relative_to(self.directory)): path.read_bytes()
            for path in self.directory.rglob("*")
            if path.is_file()
        }

    def corrupt(self, query, parameters=()):
        with closing(sqlite3.connect(self.database)) as connection:
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall():
                connection.execute(f'DROP TRIGGER "{name}"')
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute(query, parameters)
            connection.commit()

    def reseal_manifest(self):
        self.manifest.pop("record_sha256", None)
        self.manifest_hash = _sha(self.manifest)
        self.manifest["record_sha256"] = self.manifest_hash
        (self.directory / "manifest.json").write_bytes(_canonical(self.manifest))
        self.corrupt("UPDATE run_config SET manifest_sha256=?", (self.manifest_hash,))

    def test_reads_nine_ordered_receipts_and_one_unknown_without_mutation(self):
        before = self.files()
        source = self.read()
        self.assertEqual(source.settings, self.selected)
        self.assertEqual(source.spec, SearchSpec(iterations=1, screen_size=1, seed=7))
        self.assertEqual(source.prompt.id, "dev-a")
        self.assertEqual([op.reply for op in source.completed], self.receipts)
        self.assertEqual(
            [op.operation_id for op in source.completed],
            [self.operation(index) for index in range(9)],
        )
        self.assertEqual(source.unknown.operation_id, self.operation(9))
        self.assertEqual(source.unknown.status, "unknown")
        self.assertEqual(source.history.totals()["spent_microusd"], 135)
        self.assertEqual(self.files(), before)

    def test_references_have_new_semantic_identity_and_preserved_provider_evidence(self):
        source = self.read()
        references = source.references("new-run")
        self.assertEqual(len(references), 9)
        for index in range(9):
            new_id = _sha(
                ["new-run", "candidate", Policy().fingerprint(), "dev-a", "generation", index]
            )
            ref = references[new_id]
            self.assertEqual(ref.operation_id, new_id)
            self.assertEqual(ref.source_operation_id, self.operation(index))
            self.assertEqual(ref.reply, self.receipts[index])
            self.assertEqual(ref.request_sha256, self.call.fingerprint())
            self.assertEqual(ref.actual_microusd, 15)
            self.assertEqual(
                (ref.candidate_id, ref.prompt_id, ref.stage, ref.index),
                (Policy().fingerprint(), "dev-a", "generation", index),
            )
            self.assertEqual(ref.source_manifest_sha256, self.manifest_hash)
        replacement = source.replacement("new-run")
        self.assertEqual(replacement.source_operation_id, self.operation(9))
        self.assertEqual(replacement.index, 9)
        self.assertNotEqual(replacement.operation_id, replacement.source_operation_id)
        self.assertEqual(replacement.request_sha256, self.call.fingerprint())

    def test_source_and_references_are_deeply_immutable(self):
        source = self.read()
        with self.assertRaises(FrozenInstanceError):
            source.prompt = None
        references = source.references("new-run")
        first = next(iter(references.values()))
        with self.assertRaises(TypeError):
            references[first.operation_id] = first
        with self.assertRaises(FrozenInstanceError):
            first.reply.text = "changed"
        source.history.manifest["settings"]["max_calls"] = 999
        self.assertEqual(source.settings.max_calls, 128)

    def test_old_or_blank_identity_cannot_masquerade_as_a_new_attempt(self):
        source = self.read()
        for value in ("", " ", source.history.run_id):
            for method in (source.references, source.replacement):
                with self.subTest(value=value), self.assertRaises(ValidationError):
                    method(value)

    def test_mismatched_cost_request_reservation_or_slot_is_rejected_even_if_resealed(self):
        original = self.database.read_bytes()
        for field, value in [
            ("actual_microusd", 14),
            ("request_sha256", "a" * 64),
            ("reserve_microusd", 100),
            ("operation_id", "wrong-slot"),
        ]:
            self.corrupt(
                f"UPDATE operations SET {field}=? WHERE operation_id=?", (value, self.operation(0))
            )
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.read()
            self.database.write_bytes(original)

    def test_mismatched_received_model_tier_or_token_bound_is_rejected(self):
        original = self.database.read_bytes()
        for change in (
            {"model": "different"},
            {"service_tier": "priority"},
            {"input_tokens": 100001},
            {"output_tokens": 4097},
            {"finish_reason": "unsupported-status"},
        ):
            reply = replace(self.receipts[0], **change)
            self.corrupt(
                "UPDATE operations SET response_json=? WHERE operation_id=?",
                (json.dumps(reply.to_record()), self.operation(0)),
            )
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.read()
            self.database.write_bytes(original)

    def test_tenth_received_evidence_cannot_be_treated_as_receiptless_unknown(self):
        self.ledger.mark_unknown(self.operation(9), provider_request_id="known-id")
        with self.assertRaises(ValidationError):
            self.read()

    def test_extra_or_missing_source_operations_are_rejected(self):
        original = self.database.read_bytes()
        self.ledger.reserve("extra-operation", self.call.fingerprint(), 1)
        with self.assertRaises(ValidationError):
            self.read()
        self.database.write_bytes(original)
        self.corrupt("DELETE FROM operations WHERE operation_id=?", (self.operation(0),))
        with self.assertRaises(ValidationError):
            self.read()

    def test_wrong_external_seals_and_changed_dataset_are_rejected(self):
        for key in ("manifest_sha256", "ledger_sha256", "archived_runtime_sha256"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.read(**{key: "0" * 64})
        (self.directory / "dataset.jsonl").write_text('{"id":"dev-a","prompt":"changed"}\n')
        with self.assertRaises(ValidationError):
            self.read()

    def test_old_contract_code_and_protected_control_drift_are_rejected(self):
        self.manifest["contracts"]["source_sha256"]["buddha.run"] = "a" * 64
        self.reseal_manifest()
        with self.assertRaises(ValidationError):
            self.read()
        self.manifest["contracts"] = old_contracts()
        self.manifest["contracts"]["parent_rule"] = "different selection"
        self.reseal_manifest()
        with self.assertRaises(ValidationError):
            self.read()

    def test_unsupported_search_shape_or_inconsistent_screen_is_rejected(self):
        self.manifest["spec"]["iterations"] = 2
        self.reseal_manifest()
        with self.assertRaises(ValidationError):
            self.read()
        self.manifest["spec"]["iterations"] = 1
        self.manifest["screen_ids"] = ["dev-b"]
        self.reseal_manifest()
        with self.assertRaises(ValidationError):
            self.read()

    def test_archive_entries_index_and_contents_are_checked_without_extracting(self):
        with zipfile.ZipFile(ARCHIVE) as original:
            files = {name: original.read(name) for name in original.namelist()}
        for change in ("extra", "traversal", "duplicate", "index", "content"):
            archive = self.root / (change + ".zip")
            with zipfile.ZipFile(archive, "w") as bundle:
                for name, raw in files.items():
                    if change == "index" and name == "source-index.json":
                        raw = b"{}"
                    if change == "content" and name == "buddha/run.py":
                        raw += b"\n# changed\n"
                    bundle.writestr(name, raw)
                if change in {"extra", "traversal"}:
                    bundle.writestr("extra.py" if change == "extra" else "../escape.py", b"bad")
                if change == "duplicate":
                    with self.assertWarns(UserWarning):
                        bundle.writestr("buddha/run.py", files["buddha/run.py"])
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            before = self.files()
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.read(archived_runtime_zip=archive, archived_runtime_sha256=digest)
            self.assertEqual(self.files(), before)
            self.assertFalse((self.root / "escape.py").exists())

    def test_archived_special_files_and_resource_boundaries_are_rejected(self):
        for mode in (stat.S_IFLNK, stat.S_IFIFO):
            archive = self.root / ("special-" + str(mode) + ".zip")
            with zipfile.ZipFile(ARCHIVE) as original, zipfile.ZipFile(archive, "w") as changed:
                for entry in original.infolist():
                    if entry.filename == "buddha/run.py":
                        entry.create_system = 3
                        entry.external_attr = (mode | 0o600) << 16
                    changed.writestr(entry, original.read(entry.filename))
            with self.subTest(mode=mode), self.assertRaises(ValidationError):
                self.read(
                    archived_runtime_zip=archive,
                    archived_runtime_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                )
        for bound in ("_MAX_ARCHIVE", "_MAX_MEMBER"):
            with patch("buddha.continuation." + bound, 1), self.assertRaises(ValidationError):
                self.read()

    def test_invalid_zip_has_a_typed_error_and_never_changes_the_source(self):
        archive = self.root / "broken.zip"
        archive.write_bytes(b"not a ZIP")
        before = self.files()
        with self.assertRaises(ValidationError):
            self.read(
                archived_runtime_zip=archive,
                archived_runtime_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            )
        self.assertEqual(self.files(), before)

    def test_current_scientific_code_drift_is_rejected(self):
        altered = self.root / "altered.py"
        altered.write_text("# altered science\n")
        with patch("buddha.run.__file__", str(altered)), self.assertRaises(ValidationError):
            self.read()

    def test_later_rebinding_cannot_hide_changed_child_request_semantics(self):
        import buddha.run as run_module

        altered = self.root / "rebound.py"
        altered.write_bytes(
            Path(run_module.__file__).read_bytes()
            + b"""
_initial_generation = _generation
def _changed_generation(spec, prompt, *, instructions="", history=()):
    if instructions:
        instructions += " altered only for later children"
    return _initial_generation(spec, prompt, instructions=instructions, history=history)
_generation = _changed_generation
"""
        )
        with patch("buddha.run.__file__", str(altered)), self.assertRaises(ValidationError):
            self.read()

    def test_response_normalization_is_protected_inside_the_changed_host_transport(self):
        import buddha.provider as provider_module

        altered = self.root / "reply.py"
        raw = Path(provider_module.__file__).read_bytes()
        before = b'text = message.get("content") or ""'
        self.assertIn(before, raw)
        altered.write_bytes(
            raw.replace(before, b'text = (message.get("content") or "") + "changed"')
        )
        with patch("buddha.provider.__file__", str(altered)), self.assertRaises(ValidationError):
            self.read()

    def test_class_scope_rebinding_cannot_replace_the_scientific_reply_normalizer(self):
        import buddha.provider as provider_module

        altered = self.root / "class-rebound.py"
        raw = Path(provider_module.__file__).read_bytes()
        marker = b"\n\nclass BudgetBroker:"
        self.assertIn(marker, raw)
        altered.write_bytes(
            raw.replace(marker, b"\n    _reply = staticmethod(lambda *args: None)\n" + marker)
        )
        with patch("buddha.provider.__file__", str(altered)), self.assertRaises(ValidationError):
            self.read()

    def test_actual_original_nine_receipts_validate_read_only(self):
        directory = ROOT / "runs/first-live-search"
        if not directory.is_dir():
            self.skipTest("local incident evidence is not distributed in repository checkouts")
        evidence = json.loads((ROOT / "docs/first-live-request-10.json").read_bytes())
        before = {
            name: (directory / name).read_bytes()
            for name in ("manifest.json", "operations.sqlite3", "dataset.jsonl")
        }
        source = read_source(
            directory,
            manifest_sha256=evidence["manifest_sha256"],
            ledger_sha256=evidence["ledger_sha256"],
            archived_runtime_zip=ARCHIVE,
            archived_runtime_sha256=ARCHIVE_SHA,
        )
        self.assertEqual(len(source.completed), 9)
        self.assertEqual(source.history.totals()["spent_microusd"], 1709)
        self.assertEqual(source.history.totals()["reserved_microusd"], 532373)
        self.assertEqual(before, {name: (directory / name).read_bytes() for name in before})


if __name__ == "__main__":
    unittest.main()
