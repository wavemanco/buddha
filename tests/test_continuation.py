"""REC-04b linked-continuation acceptance using complete synthetic execution.

API assumptions for review:
* prepare_continuation(out, source=..., source_manifest_sha256=...,
  source_ledger_sha256=..., authorization=..., archived_runtime_zip=...,
  archived_runtime_sha256=...) returns the new directory.
* load_continuation(directory, manifest, settings, spec, prompts) returns an
  immutable evidence object: .replies maps new semantic IDs to objects with
  .reply/.source_operation_id/.request_sha256/.actual_microusd; .replacement has
  .operation_id/.source_operation_id/.request_sha256.
* The new manifest has continuation.inherited and continuation.replacement.
  Report v2 keeps costs for NEW physical operations, and adds inherited_costs,
  evidence_costs and authorization (the shared accounting snapshot).

Fixtures use real preparation/evaluation/SQLite paths, synthetic-only model
profiles, sealed history and an actual shared authorization. No model APIs run.
"""

import hashlib
import json
import multiprocessing
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from buddha.authorization import Authorization, runtime_fingerprint
from buddha.benchmark import _canonical
from buddha.continuation import load_continuation, prepare_continuation
from buddha.evaluation import ValidationError
from buddha.ledger import Ledger
from buddha.policy import Policy
from buddha.provider import BudgetBroker, ModelSpec, Reply
from buddha.run import RunSettings, _generation, _sha
from buddha.search import SearchSpec, _contracts, load_search, prepare_search, run_search

REPOSITORY = Path(__file__).resolve().parents[1]
ARCHIVE = REPOSITORY / "docs/snapshots/pilot-runtime-2026-10-19.zip"
ARCHIVE_SHA = "bd32c4d50339e2f2e1cadf01f5872fa3c1cdf12c196e7676a18d6fe96bd534e0"


def settings():
    profiles = [
        ModelSpec("replay", model, 100000, cap, 1000000, 1000000, "offline fixture")
        for model, cap in [("generator", 4096), ("partition", 16000), ("quality", 16000)]
    ]
    return RunSettings(*profiles, budget_microusd=50_000_000, max_calls=128, bounds_verified=False)


def archived_contracts():
    """Create an old-version fixture contract using the preserved source index."""
    with zipfile.ZipFile(ARCHIVE) as bundle:
        index = json.loads(bundle.read("source-index.json"))["files_sha256"]
    current = _contracts()
    result = {
        name: current[name]
        for name in (
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


class SyntheticTransport:
    def __init__(self, *, merge_first_pair=False):
        self.sent = []
        self.merge_first_pair = merge_first_pair
        self.partitions = 0

    def send(self, call):
        if call.spec.provider != "replay":
            raise AssertionError("draft fixture must never call a live model")
        body = json.loads(call.body_json)
        self.sent.append(body)
        kind = body.get("response_format", {}).get("json_schema", {}).get("name")
        if kind == "Partition":
            groups = [[index] for index in range(10)]
            if self.merge_first_pair and self.partitions == 0:
                groups = [[0, 1]] + [[index] for index in range(2, 10)]
            self.partitions += 1
            text = json.dumps({"groups": groups})
        elif kind == "Score":
            text = '{"score":8}'
        elif kind == "Policy":
            text = json.dumps({"instructions": "A declared new policy", "sampling": "regenerate"})
        else:
            text = "A synthetic new answer " + str(len(self.sent))
        return Reply(text, call.spec.model, "synthetic-" + str(len(self.sent)), 10, 5, "stop")


class NoSend:
    def send(self, call):
        raise AssertionError("stored evidence must not dispatch")


def prepare_in_process(arguments, ready, start, results):
    ready.put(arguments["out"].name)
    start.wait(15)
    try:
        arguments["authorization"] = Authorization(arguments.pop("authority_path"))
        output = arguments.pop("out")
        prepare_continuation(output, **arguments)
        results.put((output.name, "prepared"))
    except ValidationError:
        results.put((output.name, "denied"))


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "interrupted"
        self.out = self.root / "continuation"
        self.dataset = self.root / "data.jsonl"
        self.dataset.write_text(
            "".join(
                json.dumps(row) + "\n"
                for row in [
                    {"id": "dev-a", "prompt": "Give one short idea."},
                    {"id": "dev-b", "prompt": "Choose a useful action."},
                    {"id": "validation", "prompt": "VALIDATION_CANARY"},
                    {"id": "final", "prompt": "FINAL_CANARY"},
                ]
            ),
            encoding="utf-8",
        )
        self.dataset_sha = hashlib.sha256(self.dataset.read_bytes()).hexdigest()
        self.splits = {
            "development": ["dev-a", "dev-b"],
            "validation": ["validation"],
            "final": ["final"],
        }
        with patch("buddha.search._contracts", return_value=archived_contracts()):
            self.prepare_search(self.source)
        self.source_manifest = json.loads((self.source / "manifest.json").read_bytes())
        self.source_manifest_sha = self.source_manifest["record_sha256"]
        self.original = Ledger(
            self.source / "operations.sqlite3",
            run_id=self.source_manifest["run_id"],
            manifest_sha256=self.source_manifest_sha,
            budget_microusd=50_000_000,
            max_calls=128,
        )
        self.call = _generation(settings().generation, "Give one short idea.")
        self.receipts = []
        for index in range(10):
            operation_id = self.source_operation(index)
            self.original.reserve(
                operation_id, self.call.fingerprint(), self.call.spec.reserve_microusd()
            )
            self.original.dispatch(operation_id)
            if index < 9:
                reply = Reply(
                    "Original answer " + str(index),
                    "generator",
                    "original-" + str(index),
                    10,
                    5,
                    "stop",
                )
                self.original.complete(
                    operation_id,
                    response=reply.to_record(),
                    actual_microusd=15,
                    provider_request_id=reply.provider_request_id,
                )
                self.receipts.append(reply)
            else:
                self.original.mark_unknown(operation_id)
        self.source_ledger_sha = hashlib.sha256(
            (self.source / "operations.sqlite3").read_bytes()
        ).hexdigest()
        recovery = self.root / "completed-recovery"
        self.prepare_search(recovery)
        self.recovery_report = run_search(
            recovery, transport=SyntheticTransport(merge_first_pair=True)
        )
        self.assertEqual(self.recovery_report["costs"]["operation_count"], 63)
        self.authority_path = self.root / "authority.sqlite3"
        self.authority = Authorization.create(
            self.authority_path,
            authorization_id="experiment",
            budget_microusd=50_000_000,
            max_calls=128,
            scope="One interrupted pilot, completed fresh recovery and its declared continuation",
        )
        for directory, manifest_sha in [
            (self.source, self.source_manifest_sha),
            (recovery, json.loads((recovery / "manifest.json").read_bytes())["record_sha256"]),
        ]:
            self.authority.import_history(
                directory,
                manifest_sha256=manifest_sha,
                ledger_sha256=hashlib.sha256(
                    (directory / "operations.sqlite3").read_bytes()
                ).hexdigest(),
            )
        self.source_bytes = {
            name: (self.source / name).read_bytes()
            for name in ("manifest.json", "operations.sqlite3", "dataset.jsonl")
        }

    def prepare_search(self, destination):
        prepare_search(
            destination,
            dataset_path=self.dataset,
            expected_dataset_sha256=self.dataset_sha,
            settings=settings(),
            spec=SearchSpec(iterations=1, screen_size=1, seed=7),
            splits=self.splits,
            synthetic=True,
        )

    def source_operation(self, index):
        return _sha(
            [
                self.source_manifest["run_id"],
                "candidate",
                Policy().fingerprint(),
                "dev-a",
                "generation",
                index,
            ]
        )

    def arguments(self):
        return {
            "source": self.source,
            "source_manifest_sha256": self.source_manifest_sha,
            "source_ledger_sha256": self.source_ledger_sha,
            "authorization": self.authority,
            "archived_runtime_zip": ARCHIVE,
            "archived_runtime_sha256": ARCHIVE_SHA,
        }

    def prepare(self, output=None):
        return prepare_continuation(self.out if output is None else output, **self.arguments())

    def load(self):
        return load_continuation(self.out, *load_search(self.out))

    def assert_source_unchanged(self):
        self.assertEqual(
            self.source_bytes,
            {name: (self.source / name).read_bytes() for name in self.source_bytes},
        )

    def test_all_nine_original_receipts_are_referenced_without_new_operations(self):
        self.prepare()
        evidence = self.load()
        self.assertEqual(len(evidence.replies), 9)
        manifest = load_search(self.out)[0]
        for index in range(9):
            operation_id = _sha(
                [
                    manifest["run_id"],
                    "candidate",
                    Policy().fingerprint(),
                    "dev-a",
                    "generation",
                    index,
                ]
            )
            inherited = evidence.replies[operation_id]
            self.assertEqual(inherited.reply, self.receipts[index])
            self.assertEqual(inherited.source_operation_id, self.source_operation(index))
            self.assertEqual(inherited.request_sha256, self.call.fingerprint())
            self.assertEqual(inherited.actual_microusd, 15)
        self.assertEqual(self.authority.for_run(self.out).totals()["operation_count"], 0)
        self.assertEqual(self.authority.summary()["operation_count"], 73)
        self.assert_source_unchanged()

    def test_tenth_answer_has_new_identity_and_explicit_replacement_lineage(self):
        self.prepare()
        evidence = self.load()
        manifest = load_search(self.out)[0]
        expected = _sha(
            [manifest["run_id"], "candidate", Policy().fingerprint(), "dev-a", "generation", 9]
        )
        self.assertEqual(evidence.replacement.operation_id, expected)
        self.assertEqual(evidence.replacement.source_operation_id, self.source_operation(9))
        self.assertEqual(evidence.replacement.request_sha256, self.call.fingerprint())
        self.assertNotEqual(expected, self.source_operation(9))
        self.assertEqual(self.original.get(self.source_operation(9)).status, "unknown")
        self.assertNotEqual(manifest["run_id"], self.source_manifest["run_id"])
        self.assertEqual(manifest["format"], "buddha.policy-search-continuation.v1")
        self.assertEqual(load_search(self.out)[1].max_calls, 55)
        self.assert_source_unchanged()

    def test_complete_existing_search_uses_exactly_55_new_calls_and_reconciles(self):
        self.prepare()
        transport = SyntheticTransport()
        report = run_search(self.out, transport=transport, authorization=self.authority)
        self.assertEqual(report["status"], "complete")
        self.assertTrue(report["synthetic"])
        self.assertEqual(len(report["candidates"]), 3)
        self.assertEqual(len(transport.sent), 55)
        self.assertEqual(report["costs"]["operation_count"], 55)
        self.assertEqual(report["inherited_costs"]["operation_count"], 9)
        self.assertEqual(report["inherited_costs"]["spent_microusd"], 135)
        self.assertEqual(report["evidence_costs"]["spent_microusd"], 55 * 15 + 135)
        self.assertEqual(report["authorization"]["operation_count"], 128)
        self.assertEqual(report["authorization"]["spent_microusd"], (9 + 63 + 55) * 15)
        self.assertEqual(
            report["authorization"]["reserved_microusd"], self.call.spec.reserve_microusd()
        )
        self.assertEqual(report["authorization"]["remaining_calls"], 0)
        self.assertEqual(
            report["costs"]["by_stage_microusd"],
            {"generation": 315, "partition": 45, "score": 450, "proposal": 15},
        )
        self.assertEqual(
            sum(report["costs"]["by_stage_microusd"].values()), report["costs"]["spent_microusd"]
        )
        independent = (
            self.out / "candidates" / Policy().fingerprint() / "evaluation/generations.jsonl"
        )
        outputs = json.loads(independent.read_text())["generations"]
        self.assertEqual(outputs[:9], [reply.text for reply in self.receipts])
        self.assertEqual(
            run_search(self.out, transport=NoSend(), authorization=self.authority), report
        )
        self.assertEqual(len(transport.sent), 55)
        before = self.authority.summary()
        self.prepare()
        self.assertEqual(self.authority.summary(), before)
        self.assert_source_unchanged()

    def test_current_runtime_archive_preserves_every_actual_package_source(self):
        self.prepare()
        metadata = load_search(self.out)[0]["continuation"]
        self.assertEqual(metadata["runtime_sha256"], runtime_fingerprint())
        archive = self.out / "runtime-source.zip"
        self.assertEqual(
            hashlib.sha256(archive.read_bytes()).hexdigest(), metadata["runtime_archive_sha256"]
        )
        with zipfile.ZipFile(archive) as bundle:
            files = json.loads(bundle.read("source-index.json"))["files_sha256"]
            expected = {
                "buddha/" + path.name: path.read_bytes()
                for path in (REPOSITORY / "buddha").glob("*.py")
            }
            expected["THIRD_PARTY_NOTICES.md"] = (
                REPOSITORY / "THIRD_PARTY_NOTICES.md"
            ).read_bytes()
            self.assertEqual(set(files), set(expected))
            for name, raw in expected.items():
                self.assertEqual(bundle.read(name), raw)
                self.assertEqual(files[name], hashlib.sha256(raw).hexdigest())

    def test_loaded_context_and_receipt_map_are_defensive_or_immutable(self):
        self.prepare()
        evidence = self.load()
        expected = evidence.authorization_context["runs"][0]["run_id"]
        evidence.authorization_context["runs"][0]["run_id"] = "changed"
        self.assertEqual(evidence.authorization_context["runs"][0]["run_id"], expected)
        with self.assertRaises(TypeError):
            evidence.replies["extra"] = next(iter(evidence.replies.values()))

    def test_partial_unbound_directory_is_preserved_without_claim_or_repair(self):
        self.out.mkdir()
        marker = self.out / "partial"
        marker.write_bytes(b"review this unbound preparation")
        before = self.authority.summary()
        with self.assertRaises(ValidationError):
            self.prepare()
        self.assertEqual(marker.read_bytes(), b"review this unbound preparation")
        self.assertEqual(list(self.out.iterdir()), [marker])
        self.assertEqual(self.authority.summary(), before)

    def test_source_must_already_be_sealed_into_this_authority(self):
        other = Authorization.create(
            self.root / "other.sqlite3",
            authorization_id="other",
            budget_microusd=50_000_000,
            max_calls=128,
            scope="No history was imported",
        )
        before = other.summary()
        with self.assertRaises(ValidationError):
            prepare_continuation(self.out, **(self.arguments() | {"authorization": other}))
        self.assertFalse(self.out.exists())
        self.assertEqual(other.summary(), before)

    def test_changed_preserved_runtime_archive_stops_before_provider_calls(self):
        self.prepare()
        path = self.out / "runtime-source.zip"
        with path.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(ValidationError):
            run_search(self.out, transport=NoSend(), authorization=self.authority)
        self.assertEqual(self.authority.summary()["operation_count"], 73)

    def test_restart_after_durable_replacement_does_not_send_it_again(self):
        self.prepare()
        transport = SyntheticTransport()
        original = BudgetBroker.execute
        interrupted = False

        def stop_after_first_receipt(broker, operation_id, call):
            nonlocal interrupted
            reply = original(broker, operation_id, call)
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return reply

        with patch.object(BudgetBroker, "execute", stop_after_first_receipt):
            with self.assertRaises(KeyboardInterrupt):
                run_search(self.out, transport=transport, authorization=self.authority)
        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(self.authority.for_run(self.out).totals()["operation_count"], 1)
        run_search(self.out, transport=transport, authorization=self.authority)
        self.assertEqual(len(transport.sent), 55)
        self.assert_source_unchanged()

    def test_repeated_preparation_uses_one_allocation_and_identity(self):
        self.prepare()
        before = self.authority.summary()
        run_id = load_search(self.out)[0]["run_id"]
        self.prepare()
        self.assertEqual(load_search(self.out)[0]["run_id"], run_id)
        self.assertEqual(self.authority.summary(), before)
        with self.assertRaises(ValidationError):
            self.prepare(self.root / "competing-continuation")
        self.assertEqual(self.authority.summary(), before)

    def test_competing_processes_publish_only_one_continuation_allocation(self):
        context = multiprocessing.get_context("spawn")
        ready, results, start = context.Queue(), context.Queue(), context.Event()
        outputs = [self.root / name for name in ("cont-a", "cont-b")]
        processes = []
        for output in outputs:
            arguments = self.arguments()
            arguments.pop("authorization")
            arguments.update(out=output, authority_path=self.authority_path)
            processes.append(
                context.Process(target=prepare_in_process, args=(arguments, ready, start, results))
            )
        try:
            for process in processes:
                process.start()
            for _ in processes:
                ready.get(timeout=20)
            start.set()
            outcomes = dict(results.get(timeout=20) for _ in processes)
            self.assertCountEqual(outcomes.values(), ["prepared", "denied"])
            for process in processes:
                process.join(20)
                self.assertEqual(process.exitcode, 0)
            registered = self.authority.summary()["runs"]
            self.assertEqual(len(registered), 3)
            self.assertEqual(sum(bool(row["active"]) for row in registered), 1)
            loser = next(path for path in outputs if outcomes[path.name] == "denied")
            ledger = loser / "operations.sqlite3"
            if ledger.exists():
                with closing(sqlite3.connect(ledger)) as connection:
                    self.assertIsNone(
                        connection.execute(
                            "SELECT 1 FROM sqlite_master WHERE name='authorization_binding'"
                        ).fetchone()
                    )
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(10)
            ready.close()
            results.close()
        self.assert_source_unchanged()

    def test_changed_source_seal_fails_before_any_new_operation(self):
        self.prepare()
        with (self.source / "operations.sqlite3").open("ab") as stream:
            stream.write(b"changed source")
        with self.assertRaises(ValidationError):
            run_search(self.out, transport=NoSend(), authorization=self.authority)
        self.assertEqual(self.authority.summary()["operation_count"], 73)

    def test_rehashed_duplicate_or_missing_receipt_reference_never_falls_back_to_generation(self):
        self.prepare()
        manifest_path = self.out / "manifest.json"
        original = manifest_path.read_bytes()
        for change in ("missing", "duplicate", "wrong-source-operation"):
            manifest = json.loads(original)
            inherited = manifest["continuation"]["inherited"]
            if change == "missing":
                inherited.pop()
            elif change == "duplicate":
                inherited[1] = inherited[0]
            else:
                inherited[0]["source_operation_id"] = self.source_operation(9)
            manifest.pop("record_sha256")
            manifest["record_sha256"] = _sha(manifest)
            manifest_path.write_bytes(_canonical(manifest))
            with self.subTest(change=change), self.assertRaises(ValidationError):
                run_search(self.out, transport=NoSend(), authorization=self.authority)
            self.assertEqual(self.authority.summary()["operation_count"], 73)
        manifest_path.write_bytes(original)

    def test_archive_mismatch_is_rejected_before_allocation(self):
        arguments = self.arguments() | {"archived_runtime_sha256": "0" * 64}
        before = self.authority.summary()
        with self.assertRaises(ValidationError):
            prepare_continuation(self.out, **arguments)
        self.assertEqual(self.authority.summary(), before)


if __name__ == "__main__":
    unittest.main()
