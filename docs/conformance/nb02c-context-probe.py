"""Offline selected-native-function/context oracle using the pinned real SDKs.

Execute with the isolated reference interpreter; no application dependencies are
added. Original MIT NoveltyBench bodies are loaded only after fixed digest checks;
they are not vendored here. This is neither the official CLI nor a live sandbox.
"""

import ast
import asyncio
import functools
import hashlib
import http.client
import importlib.metadata
import json
import os
import random
import socket
import sys
import tempfile
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import anthropic  # noqa: E402
import httpx  # noqa: E402
import httpx2  # noqa: E402
import openai  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from buddha.answers import Answers, TaskSet  # noqa: E402
from buddha.native_context import Contexts, NativeStop  # noqa: E402
from buddha.releases import Release  # noqa: E402

PIN = "64a23be6b18ec1dacc298830aab276061b6e143c"
SOURCE = ROOT / "runs/references/noveltybench-conformance" / PIN
EXPECTED = {
    "src/judge.py": "4decf04790b90a03368eb792dfe29045435914a73ab83a52185d9dd0d1613902",
    "src/score.py": "418985a40e9e159cfeffe9a43ab2c727010d7a7a29407f4e14cab3c81b77cbae",
    "src/partition.py": "263970891ff3ee1cc8df369a33beefe5cb5de618b5dd146a5234536d97954aca",
    "src/common.py": "ba60bf0f2a409c3774d75880f305325a28ed34320610667542a4596c41f424af",
    "src/evaluation_io.py": "8a34e01308677469d984dd59e36412c2994baf2554fd3a5f026be9ef98a3a5c7",
    "LICENSE": "14e69e7fbb2f8fd0aa8ccf17d7d4ddd54665555c613a0336767f7a5fa477895c",
}
NAMES = {
    "common": {"render_responses"},
    "judge": {
        "DEFAULT_EFFORT",
        "Call",
        "Stage",
        "JudgeRefusal",
        "shuffled_order",
        "strict_schema",
        "anthropic_params",
        "parse_message",
        "judge_client",
        "judge",
        "judge_call",
        "run_stage",
    },
    "partition": {"JUDGE_SYSTEM", "Partition", "partition_calls", "partition_fold", "canonical"},
    "score": {"SCORE_SYSTEM", "Score", "heads", "score_calls", "spread", "score_llm"},
    "evaluation_io": {
        "evaluation_key",
        "cached_rows",
        "write_rows",
        "plan",
        "stamp",
        "finalize",
        "run_cached",
    },
}
SAFE_HEADERS = {"content-type", "accept-encoding", "anthropic-version", "x-stainless-helper-method"}
ROW = ContextVar("probe_row", default="single")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def forbidden(*args, **kwargs):
    raise AssertionError("offline context oracle forbids external network")


def namespace():
    for relative, expected in EXPECTED.items():
        assert sha((SOURCE / relative).read_bytes()) == expected, relative
    assert (SOURCE / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    result = {
        "__name__": "selected_nb02c_upstream",
        "asyncio": asyncio,
        "functools": functools,
        "random": random,
        "dataclass": dataclass,
        "BaseModel": BaseModel,
        "Callable": Callable,
        "hashlib": hashlib,
        "json": json,
        "os": os,
        "tempfile": tempfile,
        "tqdm": lambda values, **kwargs: values,
    }
    for module, names in NAMES.items():
        path = SOURCE / "src" / (module + ".py")
        tree = ast.parse(path.read_bytes())
        nodes = []
        for node in tree.body:
            name = getattr(node, "name", None)
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                name = getattr(node.targets[0], "id", None)
            if name in names:
                nodes.append(node)
        assert len(nodes) == len(names), module
        # Only the explicitly named inspected, digest-pinned bodies execute unchanged.
        exec(compile(ast.Module(nodes, type_ignores=[]), str(path), "exec"), result)
    return result


def normalized(value):
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, (tuple, list)):
        return [normalized(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()}
    return value


def fixture_answers(*, one_row=False):
    """Explicit synthetic artifact fixture, separate from pinned upstream source."""
    dataset = b"".join(
        json.dumps({"id": name, "prompt": "identical"}, separators=(",", ":")).encode() + b"\n"
        for name in ("a", "b", "c")
    )
    release = Release.from_record(
        {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "context-fixture",
            "release": "canned-artifact-fixture",
            "upstream": {"url": "https://example.org/context-fixture", "revision": "0" * 40},
            "source": {
                "fixture/evaluate.py": sha(b"# metadata-only synthetic entry; never executed\n"),
                "fixture.lock": sha(b"context-fixture: no executable environment\n"),
                "dataset.jsonl": sha(dataset),
            },
            "dependency_lock": "fixture.lock",
            "task": {
                "dataset": "dataset.jsonl",
                "id_field": "id",
                "prompt_field": "prompt",
                "answers_field": "generations",
                "count": 2,
            },
            "commands": [{"module": "fixture.evaluate", "argv": ["{artifacts}"]}],
            "artifacts": {
                "answers": "generations.jsonl",
                "results": ["scores.jsonl"],
                "summary": "summary.json",
            },
            "requires": ["ordered-text.v1"],
        }
    )
    tasks = TaskSet.from_dataset(release, dataset)
    if one_row:
        tasks = tasks.select(["a"])
    answers = Answers.from_results(
        release,
        tasks,
        [{"task_id": task.id, "answers": ["same"] * task.count} for task in tasks.tasks],
        agent_sha256=sha(b"scripted answer fixture: two literal same strings"),
        metadata={},
    )
    return release, tasks, answers


async def no_sleep(self, **kwargs):
    """Only retry delay is replaced; retry decisions and parsing remain SDK code."""


class Oracle:
    def __init__(self, mode, *, wrapped, reverse=False):
        self.mode, self.wrapped, self.reverse = mode, wrapped, reverse
        self.contexts = Contexts()
        self.ns = namespace()
        self.requests = []
        self.artifact_fixture = None
        if wrapped:
            for name in ("judge", "judge_call"):
                self.ns[name] = self.contexts.wrap(self.ns[name], name)

    async def exchange(self, provider, request):
        logical, physical = self.contexts.attempt() if self.wrapped else (None, None)
        body = json.loads(request.content)
        model = body["model"]
        if self.mode == "rows":
            slow = (int(logical[:2], 16) % 2 == 0) if logical else True
            await asyncio.sleep(0.002 if slow != self.reverse else 0)
        self.requests.append(
            {
                "row": ROW.get(),
                "logical_id": logical,
                "physical": physical,
                "sdk_retry": int(request.headers["x-stainless-retry-count"]),
                "provider": provider,
                "model": model,
                "body_sha256": sha(request.content),
                "headers": {
                    name: value for name, value in request.headers.items() if name in SAFE_HEADERS
                },
            }
        )
        if self.mode == "exception":
            raise RuntimeError("sanitized synthetic transport failure")
        if self.mode in {"stop", "rows_stop"}:
            raise NativeStop("unknown")
        text = '{"groups":[[0,0]]}' if self.mode == "fold" else '{"score":7}'
        if self.mode == "bad":
            text = "{malformed judgment"
        if self.mode == "duplicate":
            text = '{"score":1,"score":7}'
        refused = self.mode == "refusal" or (self.mode == "fallback" and model == "claude-primary")
        if provider == "openai":
            payload = {
                "id": "cmpl-offline",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None if refused else text,
                            "refusal": "synthetic refusal" if refused else None,
                        },
                        "finish_reason": "length" if self.mode == "length" else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }
            return httpx.Response(
                200, json=payload, headers={"x-request-id": "offline-oai"}, request=request
            )
        content = [{"type": "text", "text": text}]
        if self.mode == "multiblock":
            content = [
                {"type": "thinking", "thinking": "offline", "signature": "offline"},
                *content,
                {"type": "text", "text": '{"score":1}'},
            ]
        payload = {
            "id": "msg-offline",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_sequence": None,
            "stop_reason": "refusal"
            if refused
            else "max_tokens"
            if self.mode == "length"
            else "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 2},
        }
        return httpx2.Response(
            200, json=payload, headers={"request-id": "offline-anthropic"}, request=request
        )

    async def run(self, provider, output=None):
        async def oai(request):
            return await self.exchange("openai", request)

        async def claude(request):
            return await self.exchange("anthropic", request)

        async with (
            httpx.AsyncClient(transport=httpx.MockTransport(oai), trust_env=False) as oh,
            httpx2.AsyncClient(transport=httpx2.MockTransport(claude), trust_env=False) as ah,
            openai.AsyncOpenAI(
                api_key="offline-placeholder", base_url="https://api.openai.com/v1", http_client=oh
            ) as oc,
            anthropic.AsyncAnthropic(
                api_key="offline-placeholder",
                webhook_key="offline-placeholder",
                base_url="https://api.anthropic.com",
                http_client=ah,
            ) as ac,
        ):
            self.ns["oai_client"] = lambda: oc
            self.ns["anthropic"] = SimpleNamespace(AsyncAnthropic=lambda: ac)
            try:
                if self.mode in {"rows", "rows_stop"}:
                    value = await self.rows(output)
                else:
                    with self.contexts.row("immutable-offline-row"):
                        if self.mode == "fold":
                            stage = self.ns["Stage"](
                                "partition",
                                "partition_key",
                                self.ns["partition_calls"],
                                self.ns["partition_fold"],
                            )
                            value = await self.ns["run_stage"](
                                stage,
                                {"id": "r", "prompt": "p", "generations": ["same", "same"]},
                                {"judge_model": "test-model"},
                            )
                        else:
                            model = "test-model" if provider == "openai" else "claude-primary"
                            call = self.ns["Call"]("system", "user", self.ns["Score"])
                            value = await self.ns["judge_call"](
                                model, call, "high", "claude-fallback"
                            )
                result = {"value": normalized(value)}
            except BaseException as error:
                result = {"error": type(error).__name__}
                if isinstance(error, NativeStop):
                    result["reason"] = error.reason
        result = {
            "mode": self.mode,
            "provider": provider,
            "outcome": result,
            "requests": self.requests,
        }
        if self.artifact_fixture is not None:
            result["artifact_fixture"] = self.artifact_fixture
        return result

    async def rows(self, output):
        release, tasks, answers = fixture_answers(one_row=self.mode == "rows_stop")
        native = answers.native_bytes()
        self.artifact_fixture = {
            "benchmark": "context-fixture",
            "upstream_release_claim": False,
            "release_sha256": release.fingerprint(),
            "dataset_sha256": tasks.dataset_sha256,
            "tasks_sha256": tasks.fingerprint(),
            "answers_sha256": answers.fingerprint(),
            "native_payload_sha256": sha(native),
            "partition_source": "declared canned fixture",
        }
        partition = [0, 0] if self.mode == "rows_stop" else [0, 1]
        instances = [json.loads(line) | {"partition": partition} for line in native.splitlines()]
        config = {"judge_model": "claude-primary"}

        async def compute(instance):
            token = ROW.set(instance["id"])
            try:
                identity = sha(
                    json.dumps(
                        [
                            "context-fixture-command",
                            0,
                            release.fingerprint(),
                            answers.fingerprint(),
                            self.ns["evaluation_key"](instance, config),
                            type(instance["id"]).__name__,
                            instance["id"],
                        ],
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode()
                )
                with self.contexts.row(identity):
                    scores = await self.ns["score_llm"](instance, "claude-primary")
                    return {"generation_scores": scores}
            finally:
                ROW.reset(token)

        await self.ns["run_cached"](
            instances,
            str(output),
            "score_key",
            config,
            compute,
            concurrency=2,
        )
        return [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]


def request_identity(request):
    return (
        request["row"],
        request["logical_id"],
        request["physical"],
        request["model"],
        request["body_sha256"],
    )


async def main(temporary):
    context_before = sha((ROOT / "buddha/native_context.py").read_bytes())
    answers_before = sha((ROOT / "buddha/answers.py").read_bytes())
    probe_before = sha(Path(__file__).read_bytes())
    assert importlib.metadata.version("openai") == "1.107.0"
    assert importlib.metadata.version("anthropic") == "1.4.0"
    scenarios = []
    for provider in ("openai", "anthropic"):
        modes = ("valid", "bad", "refusal", "length", "exception", "stop")
        if provider == "anthropic":
            modes += ("fallback", "duplicate", "multiblock")
        for mode in modes:
            direct = await Oracle(mode, wrapped=False).run(provider)
            observed = await Oracle(mode, wrapped=True).run(provider)
            assert direct["outcome"] == observed["outcome"], (provider, mode)
            assert len(direct["requests"]) == len(observed["requests"]), (provider, mode)
            assert [r["body_sha256"] for r in direct["requests"]] == [
                r["body_sha256"] for r in observed["requests"]
            ]
            assert [r["headers"] for r in direct["requests"]] == [
                r["headers"] for r in observed["requests"]
            ]
            expected_error = {
                "bad": "ValidationError",
                "exception": "APIConnectionError",
                "stop": "NativeStop",
                "refusal": "ValueError" if provider == "openai" else "JudgeRefusal",
                "length": "LengthFinishReasonError" if provider == "openai" else "ValueError",
            }.get(mode)
            if expected_error:
                assert observed["outcome"]["error"] == expected_error
            else:
                assert observed["outcome"]["value"][0] == {"score": 7}
            for request in observed["requests"]:
                assert request["physical"] == request["sdk_retry"]
            if mode == "exception":
                assert len(observed["requests"]) == 9
                assert len({r["logical_id"] for r in observed["requests"]}) == 1
            if mode == "stop":
                assert len(observed["requests"]) == 1 and observed["outcome"]["reason"] == "unknown"
            if mode == "fallback":
                assert len({r["logical_id"] for r in observed["requests"]}) == 2
                assert observed["outcome"]["value"][1] == "claude-fallback"
            scenarios.append(observed)
    direct = await Oracle("fold", wrapped=False).run("openai")
    folded = await Oracle("fold", wrapped=True).run("openai")
    assert direct["outcome"] == folded["outcome"] == {"value": {"partition": [0, 1], "distinct": 2}}
    assert len(folded["requests"]) == 3
    assert len({r["logical_id"] for r in folded["requests"]}) == 3
    scenarios.append(folded)

    direct_rows = await Oracle("rows", wrapped=False).run(
        "anthropic", temporary / "rows-direct.jsonl"
    )
    first = await Oracle("rows", wrapped=True).run("anthropic", temporary / "rows-a.jsonl")
    second = await Oracle("rows", wrapped=True, reverse=True).run(
        "anthropic", temporary / "rows-b.jsonl"
    )
    assert direct_rows["outcome"] == first["outcome"] == second["outcome"]
    assert (
        direct_rows["artifact_fixture"] == first["artifact_fixture"] == second["artifact_fixture"]
    )
    assert sorted(map(request_identity, first["requests"])) == sorted(
        map(request_identity, second["requests"])
    )
    assert len(first["requests"]) == len({r["logical_id"] for r in first["requests"]}) == 6
    assert len({r["body_sha256"] for r in first["requests"]}) == 1
    # Preserve one genuine native row; remaining rows must retain their original IDs.
    saved = first["outcome"]["value"]
    partial = temporary / "rows-partial.jsonl"
    partial.write_text(json.dumps(saved[0]) + "\n", encoding="utf-8")
    resumed = await Oracle("rows", wrapped=True, reverse=True).run("anthropic", partial)
    assert resumed["outcome"] == first["outcome"]
    expected = [r for r in first["requests"] if r["row"] != saved[0]["id"]]
    assert sorted(map(request_identity, resumed["requests"])) == sorted(
        map(request_identity, expected)
    )
    cached = await Oracle("rows", wrapped=True).run("anthropic", partial)
    assert cached["requests"] == [] and cached["outcome"] == first["outcome"]
    row_stop = await Oracle("rows_stop", wrapped=True).run("anthropic", temporary / "stopped.jsonl")
    assert row_stop["outcome"] == {"error": "NativeStop", "reason": "unknown"}
    assert len(row_stop["requests"]) == 1
    scenarios += [direct_rows, first, second, resumed, cached, row_stop]
    assert sha((ROOT / "buddha/native_context.py").read_bytes()) == context_before
    assert sha((ROOT / "buddha/answers.py").read_bytes()) == answers_before
    assert sha(Path(__file__).read_bytes()) == probe_before
    result = {
        "format": "buddha.review.nb02c-selected-context-sdk.v1",
        "commit": PIN,
        "upstream_source_sha256": EXPECTED,
        "application_context_sha256": context_before,
        "application_answers_sha256": answers_before,
        "probe_sha256": probe_before,
        "sdk_versions": {
            name: importlib.metadata.version(name)
            for name in ("openai", "anthropic", "pydantic", "httpx", "httpx2")
        },
        "selected_functions": {name: sorted(names) for name, names in NAMES.items()},
        "provider_network_calls": 0,
        "actual_api_keys_used": False,
        "limits": [
            "selected native functions, not CLI",
            "no Gateway/accounting adapter exercised",
            "retry sleep stubbed; no timing claim",
            "fixed fixtures and explicit hooks, not declarative runner proof",
            "Python socket guard, not OS confinement",
            "headers observed, not funded-forwarding/compression parity",
        ],
        "scenarios": scenarios,
    }
    output = ROOT / "runs/reviews/nb02c-context-probe.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "scenarios": len(scenarios),
                "provider_network_calls": 0,
                "source_checks": len(EXPECTED),
                "evidence": str(output),
            }
        )
    )


if __name__ == "__main__":
    # Windows constructs its local loop wakeup pair before the Python network guard.
    loop = asyncio.new_event_loop()
    try:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            with (
                patch.dict(
                    os.environ,
                    {"ANTHROPIC_CONFIG_DIR": str(temporary / "empty-credentials")},
                    clear=True,
                ),
                patch.object(socket.socket, "connect", forbidden),
                patch.object(socket.socket, "connect_ex", forbidden),
                patch.object(socket, "create_connection", forbidden),
                patch.object(socket, "getaddrinfo", forbidden),
                patch.object(http.client.HTTPSConnection, "connect", forbidden),
                patch.object(openai.AsyncOpenAI, "_sleep_for_retry", no_sleep),
                patch.object(anthropic.AsyncAnthropic, "_sleep_for_retry", no_sleep),
            ):
                loop.run_until_complete(main(temporary))
    finally:
        loop.close()
