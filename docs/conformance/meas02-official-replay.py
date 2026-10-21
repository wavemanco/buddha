"""Source-sealed selected-function replay, never native CLI or live judging.

Assertions are mandatory acceptance checks in this research probe.
"""

import argparse
import ast
import hashlib
import importlib.metadata
import io
import json
import random
import sqlite3
import sys
from collections.abc import Callable
from contextlib import ExitStack, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

if not __debug__:
    raise RuntimeError("MEAS02_REPLAY_OPTIMIZED_MODE_UNSUPPORTED: assertions are required")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.dont_write_bytecode = True

from pydantic import BaseModel  # noqa: E402
from search_verify_helpers import readonly_boundary  # noqa: E402

from buddha.benchmark import import_evaluation_bytes  # noqa: E402
from buddha.evaluation import EvaluationProtocol  # noqa: E402
from buddha.run import RunSettings, _judge, _sha  # noqa: E402
from buddha.search_evidence import read_authority, read_search_evidence  # noqa: E402
from buddha.search_verify import _financial  # noqa: E402

PIN = "64a23be6b18ec1dacc298830aab276061b6e143c"
SOURCE = ROOT / "runs/references/noveltybench-conformance" / PIN / "src"
DECLARATION = "docs/conformance/rec05b-pilot-verification-input.json"
DECLARATION_SHA = "5ae91c22fed21b60f2fae94d651c4f6034f5b1f342ba8122b5135d5510b249d5"
INVENTORY = "runs/reviews/meas01-source-inventory.json"
INVENTORY_SHA = "a5a429d22adade574639c315dc36f908834d6f87b215aa878db70381d75bf0ef"
EXPECTED = {
    "common.py": "ba60bf0f2a409c3774d75880f305325a28ed34320610667542a4596c41f424af",
    "judge.py": "4decf04790b90a03368eb792dfe29045435914a73ab83a52185d9dd0d1613902",
    "partition.py": "263970891ff3ee1cc8df369a33beefe5cb5de618b5dd146a5234536d97954aca",
}
SELECTED = {
    "common.py": {"render_responses"},
    "judge.py": {
        "DEFAULT_EFFORT",
        "Call",
        "Stage",
        "JudgeRefusal",
        "shuffled_order",
        "judge_call",
        "run_stage",
    },
    "partition.py": {
        "JUDGE_SYSTEM",
        "Partition",
        "partition_calls",
        "partition_fold",
        "canonical",
    },
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def record(raw):
    return json.loads(raw)


def forbidden(*args, **kwargs):
    raise AssertionError("replay crossed a network, write, credential or execution boundary")


def pinned(path, expected):
    raw = path.read_bytes()
    assert sha(raw) == expected, str(path)
    return raw


def protected_inputs(expected):
    result = {name: sha((ROOT / name).read_bytes()) for name in expected}
    assert result == expected
    return result


def protected_sources(expected):
    result = {
        str(path.relative_to(ROOT)).replace("\\", "/"): sha(path.read_bytes())
        for path in sorted((ROOT / "buddha").glob("*.py"))
    }
    assert len(result) == 36 and result == expected
    return result


async def immediate_gather(*coroutines):
    # Exactly one partition call per fixture; no concurrency claim or event loop.
    return [await coroutine for coroutine in coroutines]


def immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    finally:
        coroutine.close()
    raise AssertionError("scripted official coroutine unexpectedly suspended")


def official_namespace():
    namespace = {
        "__name__": "meas02_selected_official",
        "BaseModel": BaseModel,
        "Callable": Callable,
        "dataclass": dataclass,
        "random": random,
        "asyncio": SimpleNamespace(gather=immediate_gather),
        "judge": forbidden,
    }
    extraction = {}
    for filename, names in SELECTED.items():
        raw = pinned(SOURCE / filename, EXPECTED[filename])
        tree = ast.parse(raw)
        selected = []
        for node in tree.body:
            name = getattr(node, "name", None)
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                name = getattr(node.targets[0], "id", None)
            if name in names:
                selected.append(node)
        assert len(selected) == len(names)
        module = ast.Module(body=selected, type_ignores=[])
        extraction[filename] = {
            "file_sha256": sha(raw),
            "selected_names": sorted(names),
            "selected_ast_sha256": sha(ast.dump(module, include_attributes=False).encode()),
        }
        # Exact inspected selected AST nodes only; upstream imports are excluded.
        exec(  # nosec B102: pinned selected AST; optimized execution is rejected above.
            compile(module, str(SOURCE / filename), "exec"), namespace
        )
    namespace["Partition"].model_validate_json('{"groups":[[0]]}')
    return namespace, extraction


def fold_result(namespace, instance, raw_text, config):
    try:
        parsed = namespace["Partition"].model_validate_json(raw_text)
        value = namespace["partition_fold"](instance, [parsed], config)
        return {"status": "success", **value}
    except ValueError as error:
        return {"status": "invalid", "error_type": type(error).__name__}


def controlled_oracle(namespace):
    original_judge_call = namespace["judge_call"]
    instance = {"id": "scripted", "prompt": "Fixture task", "generations": list("ABCD")}
    folds = []
    for name, groups, expected, valid in (
        ("valid", [[0, 2], [1, 3]], [0, 1, 0, 1], True),
        ("omission", [[0, 1], [3]], [0, 0, 1, 2], False),
        ("repeat_within_group", [[0, 0], [1, 2, 3]], [0, 1, 1, 1], False),
        ("repeat_across_groups_first_kept", [[0, 1], [1, 2], [3]], [0, 0, 1, 2], False),
        ("first_group_precedence", [[1, 2], [0, 1], [3]], [0, 1, 1, 2], False),
        ("out_of_range_removed", [[-1, 0, 4], [1, 2, 3]], [0, 1, 1, 1], False),
        ("all_omitted", [], [0, 1, 2, 3], False),
        ("empty_group", [[], [0, 1]], [0, 0, 1, 2], False),
        ("all_indices_invalid", [[-1, 4]], [0, 1, 2, 3], False),
    ):
        raw = json.dumps({"groups": groups}, separators=(",", ":"))
        strict = fold_result(namespace, instance, raw, {"seed": None})
        lenient = fold_result(namespace, instance, raw, {"seed": None, "lenient": True})
        assert (strict["status"] == "success") == valid
        assert lenient["partition"] == expected
        if valid:
            assert strict == lenient
        folds.append({"case": name, "raw_reply_text": raw, "strict": strict, "lenient": lenient})

    mappings = []
    original = [0, 0, 1, 2, 1]
    for seed in (None, 0, 7, 20261020):
        item = {"prompt": "A prompt", "generations": list("ABCDE")}
        order = namespace["shuffled_order"](item["prompt"], 5, seed)
        groups = [
            [shown for shown, actual in enumerate(order) if original[actual] == label]
            for label in (2, 1, 0)
        ]
        raw = json.dumps({"groups": groups})
        folded = fold_result(namespace, item, raw, {"seed": seed})
        call = namespace["partition_calls"](item, {"seed": seed})[0]
        assert folded["partition"] == original
        mappings.append(
            {
                "seed": seed,
                "display_order": order,
                "displayed_groups": groups,
                "partition_original_order": folded["partition"],
                "rendered_user_sha256": sha(call.user.encode()),
            }
        )

    stages = []
    stage = namespace["Stage"](
        "partition", "partition_key", namespace["partition_calls"], namespace["partition_fold"]
    )
    for mode, expected_calls, expected_partition in (
        ("strict_success", 1, [0, 0, 1, 1]),
        ("repair_second_attempt", 2, [0, 0, 1, 1]),
        ("persistent_invalid_last_fold", 3, [0, 0, 1, 2]),
        ("last_attempt_only", 3, [0, 0, 1, 2]),
        ("refusal_is_not_leniency", 1, None),
        ("schema_failure_is_not_fold_retry", 1, None),
    ):
        calls = []

        async def scripted(model, call, effort, fallback, mode=mode, calls=calls):
            if mode == "refusal_is_not_leniency":
                calls.append({"error": "JudgeRefusal"})
                raise namespace["JudgeRefusal"]("scripted refusal")
            raw = (
                "{invalid"
                if mode == "schema_failure_is_not_fold_retry"
                else json.dumps(
                    {
                        "groups": (
                            [[0, 1], [2, 3]]
                            if mode == "strict_success"
                            or mode == "repair_second_attempt"
                            and len(calls) == 1
                            else []
                            if mode == "last_attempt_only" and len(calls) < 2
                            else [[0, 1]]
                        )
                    }
                )
            )
            calls.append({"raw_reply_text": raw, "raw_reply_sha256": sha(raw.encode())})
            return namespace["Partition"].model_validate_json(raw), model

        namespace["judge_call"] = scripted
        diagnostics = io.StringIO()
        try:
            with redirect_stdout(diagnostics):
                value = immediate(
                    namespace["run_stage"](stage, instance, {"judge_model": "fixture"})
                )
            outcome = {"status": "success", **value}
            assert outcome["partition"] == expected_partition
        except ValueError as error:
            assert expected_partition is None
            outcome = {"status": "failed", "error_type": type(error).__name__}
        assert len(calls) == expected_calls
        strict_last = (
            fold_result(namespace, instance, calls[-1]["raw_reply_text"], {"seed": None})
            if "raw_reply_text" in calls[-1]
            else None
        )
        stages.append(
            {
                "case": mode,
                "calls": calls,
                "call_count": len(calls),
                "outcome": outcome,
                "strict_last": strict_last,
                "lenient_required": expected_partition is not None
                and strict_last["status"] == "invalid",
            }
        )

    namespace["judge_call"] = original_judge_call
    fallbacks = []
    for mode, expected_calls, succeeds in (
        ("primary_success", 1, True),
        ("refusal_with_fallback", 2, True),
        ("refusal_without_fallback", 1, False),
        ("invalid_primary_no_refusal_fallback", 1, False),
    ):
        called = []

        async def judge(model, call, effort, mode=mode, called=called):
            called.append(model)
            if mode == "invalid_primary_no_refusal_fallback":
                raise ValueError("scripted parse failure")
            if mode != "primary_success" and model == "fixture-primary":
                raise namespace["JudgeRefusal"]("scripted refusal")
            return namespace["Partition"](groups=[[0, 1], [2, 3]])

        namespace["judge"] = judge
        fallback = None if mode == "refusal_without_fallback" else "fixture-fallback"
        call = namespace["partition_calls"](instance, {})[0]
        try:
            parsed, used = immediate(
                namespace["judge_call"]("fixture-primary", call, "high", fallback)
            )
            assert succeeds
            outcome = {"status": "success", "used": used, "groups": parsed.groups}
        except ValueError as error:
            assert not succeeds
            outcome = {"status": "failed", "error_type": type(error).__name__}
        assert len(called) == expected_calls
        fallbacks.append({"case": mode, "models_called": called, "outcome": outcome})
    namespace["judge"] = forbidden
    return {
        "fold_cases": folds,
        "mapping_cases": mappings,
        "stage_cases": stages,
        "generic_judge_fallback_cases": fallbacks,
        "scope": (
            "Scripted selected-function control flow; partition CLI supplies no fallback model."
        ),
    }


def main(target):
    versions = {name: importlib.metadata.version(name) for name in ("pydantic", "pydantic-core")}
    assert versions == {"pydantic": "2.11.7", "pydantic-core": "2.33.2"}
    namespace, extraction = official_namespace()
    # Controlled selected source is prepared before the strict no-exec read window.
    with readonly_boundary():
        oracle = controlled_oracle(namespace)
    expected_inputs = record((ROOT / "docs/conformance/nb01-preservation.json").read_bytes())[
        "input_sha256"
    ]
    expected_sources = record(
        pinned(
            ROOT / "docs/conformance/rec05c-code-preservation.json",
            "f6d89868c5a45c3bef2d91f7d5a7d0c7bac81dd7c69f8f7158dcc35a623af331",
        )
    )["source_sha256"]
    source_before = protected_sources(expected_sources)
    before = protected_inputs(expected_inputs)
    archive = ROOT / "docs/snapshots/pilot-runtime-2026-10-19.zip"
    archive_sha = "bd32c4d50339e2f2e1cadf01f5872fa3c1cdf12c196e7676a18d6fe96bd534e0"
    pinned(archive, archive_sha)
    declaration = record(pinned(ROOT / DECLARATION, DECLARATION_SHA))
    audit_inventory = record(pinned(ROOT / INVENTORY, INVENTORY_SHA))
    rows, connections = [], []
    connect = sqlite3.connect

    def memory_only(database, *args, **kwargs):
        assert database == ":memory:"
        connections.append(database)
        return connect(database, *args, **kwargs)

    with ExitStack() as stack:
        for guard_target in (
            "buddha.authorization.runtime_fingerprint",
            "buddha.authorization.Authorization.create",
            "buddha.authorization.Authorization.bind_run",
            "buddha.authorization.Authorization.deactivate",
            "buddha.run.load_run",
            "buddha.gateway.Gateway.__init__",
            "buddha.gateway.execution_identity",
            "buddha.native_run.NativeSession.__init__",
            "buddha.agent_run.AgentSession.__init__",
            "buddha.executor.run_container",
            "zipfile.ZipFile.__init__",
        ):
            stack.enter_context(patch(guard_target, side_effect=forbidden))
        stack.enter_context(readonly_boundary())
        stack.enter_context(patch("sqlite3.connect", side_effect=memory_only))
        snapshot = read_search_evidence(
            Path(declaration["runs"][0]["directory"]), evidence=declaration
        )
        authority = read_authority(snapshot.authorization)
        for run_name in ("first-live-recovery", "first-live-continuation-v2"):
            run = snapshot.run(ROOT / "runs" / run_name)
            history = _financial(run)
            manifest = history.manifest
            settings = RunSettings.from_record(manifest["settings"])
            operations = {item.operation_id: item for item in history.operations}
            report = record(run.blob("report.json"))
            for candidate in report["candidates"]:
                candidate_id = candidate["candidate_id"]
                base = "candidates/" + candidate_id + "/evaluation/"
                blobs = {
                    name: run.blob(base + name)
                    for name in (
                        "generations.jsonl",
                        "v1.1/partitions.jsonl",
                        "v1.1/scores.jsonl",
                        "v1.1/summary.json",
                        "provenance.json",
                    )
                }
                generation_rows = [record(line) for line in blobs["generations.jsonl"].splitlines()]
                partition_rows = [
                    record(line) for line in blobs["v1.1/partitions.jsonl"].splitlines()
                ]
                assert len(generation_rows) == len(partition_rows) == 1
                generation, partition_row = generation_rows[0], partition_rows[0]
                protocol = EvaluationProtocol(**record(blobs["provenance.json"])["protocol"])
                prompt_id, prompt = generation["id"], generation["prompt"]
                import_evaluation_bytes(
                    blobs,
                    protocol=protocol,
                    expected_prompt_hashes={prompt_id: sha(prompt.encode())},
                )
                operation_id = _sha(
                    [history.run_id, "candidate", candidate_id, prompt_id, "partition", 0]
                )
                operation = operations[operation_id]
                reply = operation.reply
                assert operation.status == "completed" and reply is not None
                assert not reply.refused and reply.finish_reason == "stop"
                assert reply.model == settings.partition.model
                instance = {
                    "id": prompt_id,
                    "prompt": prompt,
                    "generations": generation["generations"],
                }
                config = {"seed": protocol.ordering_seed}
                calls = namespace["partition_calls"](instance, config)
                assert len(calls) == 1
                legacy_call = _judge(
                    settings.partition, calls[0].system, calls[0].user, "Partition"
                )
                assert legacy_call.fingerprint() == operation.request_sha256
                strict = fold_result(namespace, instance, reply.text, config)
                lenient = fold_result(namespace, instance, reply.text, config | {"lenient": True})
                assert strict["status"] == "success" and strict == lenient
                assert strict["partition"] == partition_row["partition"]
                assert strict["distinct"] == partition_row["distinct"]
                assert protocol.upstream_commit == PIN and protocol.metric_version == "1.1"
                matching = [
                    item
                    for item in audit_inventory["candidates"].values()
                    if item["run_id"] == history.run_id and item["candidate_id"] == candidate_id
                ]
                assert len(matching) == 1
                reference_ids = matching[0]["answer_references"]
                answer_sha = [sha(text.encode()) for text in instance["generations"]]
                assert len(reference_ids) == len(answer_sha) == 10
                for index, reference_id in enumerate(reference_ids):
                    source = audit_inventory["answers"][reference_id]
                    assert source["answer_index_0based"] == index
                    assert source["answer_utf8_sha256"] == answer_sha[index]
                    assert source["answer_source"]["file_sha256"] == sha(blobs["generations.jsonl"])
                    assert source["answer_source"]["json_pointer"] == "/generations/" + str(index)
                rows.append(
                    {
                        "run_id": history.run_id,
                        "candidate_id": candidate_id,
                        "prompt_id": prompt_id,
                        "reference_ids": reference_ids,
                        "answer_sha256": answer_sha,
                        "prompt_sha256": sha(prompt.encode()),
                        "partition": strict["partition"],
                        "recorded_partition": partition_row["partition"],
                        "distinct": strict["distinct"],
                        "protocol": record(blobs["provenance.json"])["protocol"],
                        "protocol_fingerprint": protocol.fingerprint(),
                        "operation_id": operation_id,
                        "request_sha256": operation.request_sha256,
                        "reply_text": reply.text,
                        "reply_text_utf8_sha256": sha(reply.text.encode()),
                        "reply_finish_reason": reply.finish_reason,
                        "reply_refused": reply.refused,
                        "parsed_groups": namespace["Partition"]
                        .model_validate_json(reply.text)
                        .groups,
                        "display_order": namespace["shuffled_order"](
                            prompt, 10, protocol.ordering_seed
                        ),
                        "strict_replay": strict,
                        "lenient_replay": lenient,
                        "historical_leniency_required": False,
                        "historical_profile": {
                            "repair": "disabled",
                            "partition_attempts": 1,
                            "native_full_cli_attestation": False,
                            "explicit_output_cap": settings.partition.max_output_tokens,
                        },
                        "receipt_source": {
                            "ledger_sha256": history.ledger_sha256,
                            "operation_id": operation_id,
                            "field": "response_json.text",
                            "scope": (
                                "Parsed legacy Reply.text; full raw HTTP wire/block boundaries "
                                "were not retained."
                            ),
                        },
                        "source_sha256": {
                            "manifest_content": history.manifest_sha256,
                            **{base + name: sha(raw) for name, raw in blobs.items()},
                        },
                    }
                )
        snapshot.finish()
    assert len(rows) == len({(r["run_id"], r["candidate_id"], r["prompt_id"]) for r in rows}) == 6
    assert protected_inputs(expected_inputs) == before
    assert protected_sources(expected_sources) == source_before
    pinned(archive, archive_sha)
    assert connections
    result = {
        "format": "buddha.meas02-official-replay.v1",
        "execution": (
            "Exact hash-pinned official selected AST functions/classes and locked Pydantic; "
            "not full-module/native CLI execution."
        ),
        "upstream_commit": PIN,
        "metric_version": "1.1",
        "probe_sha256": sha(Path(__file__).read_bytes()),
        "source": extraction,
        "pydantic_versions": versions,
        "python": sys.version,
        "rows": sorted(rows, key=lambda r: (r["run_id"], r["candidate_id"], r["prompt_id"])),
        "controlled_oracle": oracle,
        "integrity": {
            "preserved_input_files": len(before),
            "prior_287_expected_seals_match_before_after": True,
            "pilot_zip_sha256": archive_sha,
            "pilot_zip_unchanged": True,
            "package_sources": source_before,
            "all_36_prior_source_seals_match_before_after": True,
            "v2_authority_sha256": expected_inputs["runs\\first-live-authorization-v2.sqlite3"],
            "authority_totals": authority["totals"],
            "memory_only_sqlite_connections": len(connections),
            "declaration_sha256": DECLARATION_SHA,
            "source_inventory_sha256": INVENTORY_SHA,
        },
        "guards": {
            "source_database_connections": 0,
            "provider_calls": 0,
            "credentials_read": 0,
            "historical_writes": 0,
            "runtime_reconstruction": 0,
            "archived_code_execution": 0,
        },
        "limits": [
            "No new judge accuracy ratings, human validation, fresh official judging "
            "or display-order stability measurement.",
            "Controlled order cases verify source mapping only; they do not measure "
            "a model's response to reordered answers.",
            "Scripted gather evaluates immediate single-call fixture coroutines; "
            "concurrent scheduling is not measured.",
            "Native generic refusal fallback controls are not a partition CLI fallback claim; "
            "that CLI supplies none.",
            "Saved legacy text and seals establish local evidence consistency, "
            "not full raw HTTP preservation or provider authenticity.",
            "The historical adapter used one attempt and disabled repair; selected official "
            "replay does not retroactively make it a native run.",
            "No quality rescore, changed official partition/utility/ranking, "
            "semantic holdout access or new spending allocation.",
            "Complete sealed dataset files were buffered as integrity inputs, "
            "but no unseen prompt text was decoded for assessment.",
        ],
    }
    with target.open("xb") as stream:
        stream.write((json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(
        json.dumps(
            {
                "status": "passed",
                "rows": len(rows),
                "strict_successes": len(rows),
                "fold_cases": len(oracle["fold_cases"]),
                "mapping_cases": len(oracle["mapping_cases"]),
                "stage_cases": len(oracle["stage_cases"]),
                "fallback_cases": len(oracle["generic_judge_fallback_cases"]),
                "evidence_sha256": sha(target.read_bytes()),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)
