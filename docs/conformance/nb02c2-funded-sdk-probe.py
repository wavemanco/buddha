"""Offline pinned-SDK/funded-Gateway composition; selected native functions only.

Run with runs/reference-env/Scripts/python.exe. All HTTPS is mocked, environment
credentials are synthetic, and Python network guards reject external access.
This is not a CLI, configured hook installer, process sandbox or live-readiness proof.
"""

import asyncio
import gzip
import http.client
import importlib.metadata
import importlib.util
import json
import os
import platform
import socket
import sys
import tempfile
import zlib
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HELPER = ROOT / "docs/conformance/nb02c-context-probe.py"
loader = importlib.util.spec_from_file_location("context_oracle", HELPER)
assert loader is not None and loader.loader is not None
c1 = importlib.util.module_from_spec(loader)
loader.loader.exec_module(c1)

from buddha.authorization import Authorization  # noqa: E402
from buddha.gateway import (  # noqa: E402
    Gateway,
    GatewayCall,
    GatewayError,
    RawHTTPTransport,
    prepare_gateway,
)
from buddha.ledger import BudgetExceeded  # noqa: E402
from buddha.native_context import NativeStop  # noqa: E402
from buddha.native_transport import make_transport  # noqa: E402
from buddha.provider import (  # noqa: E402
    BoundBreach,
    ModelSpec,
    PendingOperation,
    ProviderUncertain,
)
from buddha.releases import Release, inventory, prepare_selection  # noqa: E402
from buddha.wire import RawEnvelope  # noqa: E402

CAPS = {"openai": "openai.chat-completions.v1", "anthropic": "anthropic.messages.v1"}
KEYS = {name: "offline-host-" + name + "-not-a-real-key" for name in CAPS}
WORKER_KEY = "offline-worker-placeholder-never-forwarded"
ENV_BASE = {"PROCESSOR_ARCHITECTURE": "AMD64"}


def encoded(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def native_headers(provider):
    """Explicit synthetic-profile values from the pinned actual SDK capture."""
    version = "1.107.0" if provider == "openai" else "1.4.0"
    result = {
        "accept": ["application/json"],
        "accept-encoding": ["gzip, deflate"],
        "content-type": ["application/json"],
        "user-agent": [
            f"Async{'OpenAI' if provider == 'openai' else 'Anthropic'}/Python {version}"
        ],
        "x-stainless-arch": ["other:amd64"],
        "x-stainless-async": ["async:asyncio"],
        "x-stainless-lang": ["python"],
        "x-stainless-os": ["Windows"],
        "x-stainless-package-version": [version],
        "x-stainless-read-timeout": ["600"],
        "x-stainless-retry-count": [str(index) for index in range(9)],
        "x-stainless-runtime": ["CPython"],
        "x-stainless-runtime-version": [platform.python_version()],
    }
    if provider == "openai":
        result["x-stainless-helper-method"] = ["chat.completions.parse"]
    else:
        result["anthropic-version"] = ["2023-06-01"]
        result["x-stainless-timeout"] = ["600"]
    return result


def payload(provider, model, mode):
    text = '{"groups":[[0,0]]}' if mode == "fold" else '{"score":7}'
    if mode == "bad":
        text = "{malformed judgment"
    elif mode == "duplicate":
        text = '{"score":1,"score":7}'
    refused = mode == "refusal" or (mode == "fallback" and model == "claude-primary")
    if provider == "openai":
        return {
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
                    "finish_reason": "length" if mode == "length" else "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
    content = [{"type": "text", "text": text}]
    if mode == "multiblock":
        content = [
            {"type": "thinking", "thinking": "offline", "signature": "offline"},
            *content,
            {"type": "text", "text": '{"score":1}'},
        ]
    return {
        "id": "msg-offline",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_sequence": None,
        "stop_reason": "refusal" if refused else "max_tokens" if mode == "length" else "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }


class Connection:
    """Mock HTTPS only; Gateway's real preparation/receipt/accounting code runs."""

    def __init__(self, oracle, host, **kwargs):
        self.oracle, self.host = oracle, host

    def request(self, method, path, *, body, headers):
        provider = "openai" if self.host == "api.openai.com" else "anthropic"
        assert method == "POST"
        assert path == ("/v1/chat/completions" if provider == "openai" else "/v1/messages")
        assert WORKER_KEY not in str(headers)
        assert (
            headers.get("Authorization") == "Bearer " + KEYS[provider]
            if provider == "openai"
            else headers.get("x-api-key") == KEYS[provider]
        )
        self.oracle.sent.append(
            {
                "provider": provider,
                "body_sha256": c1.sha(body),
                "headers": {
                    name.lower(): value
                    for name, value in headers.items()
                    if name.lower() not in {"authorization", "x-api-key"}
                },
            }
        )
        self.provider, self.model = provider, json.loads(body)["model"]

    def getresponse(self):
        if self.oracle.mode == "timeout":
            raise TimeoutError("synthetic host HTTPS timeout")
        return self

    @property
    def status(self):
        return 503 if self.oracle.mode == "status" else 200

    def read(self, limit):
        self.raw = encoded(payload(self.provider, self.model, self.oracle.mode))
        if self.oracle.mode in {"unknown", "rows_stop"}:
            self.raw = b'{"model":"' + self.model.encode() + b'","missing_usage":true}'
        if self.oracle.mode == "partial":
            self.raw = self.raw[:47]
            raise http.client.IncompleteRead(self.raw, 100)
        if self.oracle.mode == "gzip":
            self.raw = gzip.compress(self.raw, mtime=0)
        elif self.oracle.mode == "deflate":
            self.raw = zlib.compress(self.raw)
        assert len(self.raw) < limit
        return self.raw

    def getheaders(self):
        if self.oracle.mode == "interrupted":
            raise KeyboardInterrupt
        pairs = [
            ("content-type", "application/json"),
            ("x-request-id" if self.provider == "openai" else "request-id", "offline-receipt"),
        ]
        if self.oracle.mode in {"gzip", "deflate"}:
            pairs.append(("content-encoding", self.oracle.mode))
        if self.oracle.mode == "status":
            pairs += [("retry-after-ms", "0"), ("x-should-retry", "true")]
        return pairs

    def close(self):
        pass


class Funded(c1.Oracle):
    def __init__(self, directory, mode, *, authority_empty=False):
        super().__init__(mode, wrapped=True)
        self.root = directory
        self.sent, self.calls = [], []
        self.lock = asyncio.Lock()
        roots = {
            name: directory / name
            for name in ("official", "environment", "runner", "host", "agent")
        }
        for name, path in roots.items():
            path.mkdir(parents=True)
            (path / "identity.txt").write_text(
                "explicit offline " + name + " fixture\n", encoding="utf-8"
            )
        (roots["official"] / "evaluate.py").write_text(
            "# fixture metadata; never executed\n", encoding="utf-8"
        )
        (roots["official"] / "fixture.lock").write_text(
            "synthetic; not an installed lock claim\n", encoding="utf-8"
        )
        (roots["official"] / "dataset.jsonl").write_text(
            '{"id":"a","prompt":"p"}\n', encoding="utf-8"
        )
        profiles = {}
        for model, provider in (
            ("test-model", "openai"),
            ("claude-primary", "anthropic"),
            ("claude-fallback", "anthropic"),
        ):
            spec = ModelSpec(
                provider,
                model,
                2_000_000,
                128_000,
                1_000_000,
                2_000_000,
                "https://example.org/synthetic-oracle-bounds-not-live-profile",
            )
            profiles[model] = {
                "spec": asdict(spec),
                "response_models": [model],
                "request_tiers": ["auto", "default"],
                "response_tiers": ["", "default"],
                "allow_omitted_tier": True,
                "headers": native_headers(provider),
                "account_headers": {"openai-project": "offline-owner-project"}
                if provider == "openai"
                else {"anthropic-workspace-id": "offline-owner-workspace"},
            }
        (roots["host"] / "profiles.json").write_bytes(
            encoded({"format": "buddha.gateway-profiles.v2", "profiles": profiles})
        )
        release = Release.from_record(
            {
                "format": "buddha.benchmark-release.v1",
                "benchmark": "funded-sdk-fixture",
                "release": "synthetic-selection-not-official-cli",
                "upstream": {"url": "https://example.org/offline-fixture", "revision": "0" * 40},
                "source": inventory(roots["official"]),
                "dependency_lock": "fixture.lock",
                "task": {
                    "dataset": "dataset.jsonl",
                    "id_field": "id",
                    "prompt_field": "prompt",
                    "answers_field": "generations",
                    "count": 2,
                },
                "commands": [{"module": "evaluate", "argv": []}],
                "artifacts": {
                    "answers": "answers.jsonl",
                    "results": ["results.jsonl"],
                    "summary": "summary.json",
                },
                "requires": sorted(CAPS.values()),
            }
        )
        selection = prepare_selection(
            release, roots, capabilities={cap: "profiles.json" for cap in CAPS.values()}
        )
        budget = 1 if authority_empty else 100_000_000
        authority = Authorization.create(
            directory / "authority.sqlite3",
            authorization_id="offline-funded-sdk",
            budget_microusd=budget,
            max_calls=40,
            scope="synthetic offline oracle; no live permission",
        )
        inputs = [
            HELPER,
            Path(__file__).resolve(),
            ROOT / "buddha/native_context.py",
            ROOT / "buddha/native_transport.py",
            ROOT / "buddha/answers.py",
        ]
        inputs += [c1.SOURCE / relative for relative in sorted(c1.EXPECTED)]
        run = prepare_gateway(
            directory / "run",
            selection=selection,
            roots=roots,
            authorization=authority,
            budget_microusd=budget,
            max_calls=40,
            input_files=inputs,
            review={
                "checked_on": datetime.now(UTC).date().isoformat(),
                "credential_sha256": {name: c1.sha(key.encode()) for name, key in KEYS.items()},
                "account_scope": "synthetic offline provider accounts",
            },
            run_id="offline-funded-sdk-run",
        )
        self.gateway = Gateway(run, transport=RawHTTPTransport(allow_paid=True, timeout_seconds=2))

    async def exchange(self, request):
        await asyncio.sleep(0)  # Exercise one shared admission queue across native tasks.
        async with self.lock:
            body = json.loads(request.body)
            call = GatewayCall(
                CAPS[request.provider],
                body["model"],
                request.logical_id,
                request.attempt,
                request.body,
                request.headers,
            )
            self.calls.append(call)
            try:
                with patch(
                    "http.client.HTTPSConnection",
                    side_effect=lambda host, **kwargs: Connection(self, host, **kwargs),
                ):
                    # Offline synchronous mock only. Production owned RPC/cleanup is C3.
                    result = self.gateway.execute(call)
            except (ProviderUncertain, PendingOperation):
                raise NativeStop("unknown") from None
            except (BudgetExceeded, BoundBreach):
                raise NativeStop("authority") from None
            except GatewayError:
                raise NativeStop("protocol") from None
            except (KeyboardInterrupt, SystemExit):
                raise NativeStop("cancelled") from None
            self.requests.append(
                {
                    "logical_id": request.logical_id,
                    "physical": request.attempt,
                    "provider": request.provider,
                    "model": body["model"],
                    "body_sha256": c1.sha(request.body),
                    "headers": dict(request.headers),
                }
            )
            return result

    async def run(self, provider, output=None):
        # A new native invocation must not reuse judge_client's cached closed SDK
        # clients. Rebuild the sealed selected namespace, as a fresh worker will.
        self.ns = c1.namespace()
        self.contexts = c1.Contexts()
        for name in ("judge", "judge_call"):
            self.ns[name] = self.contexts.wrap(self.ns[name], name)
        async with (
            c1.httpx.AsyncClient(
                transport=make_transport("openai", contexts=self.contexts, exchange=self.exchange),
                trust_env=False,
            ) as oh,
            c1.httpx2.AsyncClient(
                transport=make_transport(
                    "anthropic", contexts=self.contexts, exchange=self.exchange
                ),
                trust_env=False,
            ) as ah,
            c1.openai.AsyncOpenAI(
                api_key=WORKER_KEY, base_url="https://api.openai.com/v1", http_client=oh
            ) as oc,
            c1.anthropic.AsyncAnthropic(
                api_key=WORKER_KEY,
                webhook_key=WORKER_KEY,
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
                            value = await self.ns["judge_call"](
                                model,
                                self.ns["Call"]("system", "user", self.ns["Score"]),
                                "high",
                                "claude-fallback",
                            )
                outcome = {"value": c1.normalized(value)}
            except BaseException as error:
                outcome = {"error": type(error).__name__}
                if isinstance(error, NativeStop):
                    outcome["reason"] = error.reason
            sdk_max_retries = self.ns["judge_client"](
                "test-model" if provider == "openai" else "claude-primary"
            ).max_retries
            assert sdk_max_retries == 8
        operations = {
            self.gateway.operation_id(call): self.gateway.ledger.get(
                self.gateway.operation_id(call)
            )
            for call in self.calls
        }
        return {
            "mode": self.mode,
            "provider": provider,
            "outcome": outcome,
            "sdk_max_retries": sdk_max_retries,
            "sdk_transport_calls": len(self.calls),
            "mock_https_sends": len(self.sent),
            "requests": self.requests,
            "sent": self.sent,
            "totals": self.gateway.ledger.totals(),
            "operations": [
                {
                    "operation_id": identity,
                    "status": operation.status,
                    "reserve_microusd": operation.reserve_microusd,
                    "actual_microusd": operation.actual_microusd,
                    "receipt_sha256": c1.sha(encoded(operation.response))
                    if operation.response
                    else None,
                    "raw_body_sha256": RawEnvelope.from_record(
                        operation.response["envelope"]
                    ).received_sha256
                    if operation.response
                    else None,
                }
                for identity, operation in operations.items()
                if operation is not None
            ],
        }


async def main(temporary):
    assert platform.system() == "Windows", "explicit profile fixtures are Windows SDK headers"
    assert importlib.metadata.version("openai") == "1.107.0"
    assert importlib.metadata.version("anthropic") == "1.4.0"
    frozen = {
        str(path.relative_to(ROOT)): c1.sha(path.read_bytes())
        for path in (
            Path(__file__).resolve(),
            HELPER,
            ROOT / "buddha/native_transport.py",
            ROOT / "buddha/native_context.py",
            ROOT / "buddha/answers.py",
        )
    }
    results = []
    for provider in CAPS:
        modes = (
            "valid",
            "bad",
            "refusal",
            "length",
            "gzip",
            "deflate",
            "unknown",
            "status",
            "partial",
            "timeout",
            "interrupted",
        )
        if provider == "anthropic":
            modes += ("fallback", "duplicate", "multiblock")
        for mode in modes:
            oracle = Funded(temporary / (provider + "-" + mode), mode)
            result = await oracle.run(provider)
            if mode in {"unknown", "status", "partial", "timeout", "interrupted"}:
                assert result["outcome"] == {
                    "error": "NativeStop",
                    "reason": "cancelled" if mode == "interrupted" else "unknown",
                }, result
                assert result["sdk_transport_calls"] == result["mock_https_sends"] == 1
                assert (
                    len(result["operations"]) == 1
                    and result["operations"][0]["status"] == "unknown"
                )
                assert (
                    result["totals"]["spent_microusd"] == 0
                    and result["totals"]["reserved_microusd"] > 0
                )
                assert (result["operations"][0]["receipt_sha256"] is None) == (mode == "timeout")
                replay = await oracle.run(provider)
                assert replay["mock_https_sends"] == 1 and replay["totals"] == result["totals"]
            else:
                direct = await c1.Oracle(
                    "valid" if mode in {"gzip", "deflate"} else mode, wrapped=True
                ).run(provider)
                assert result["outcome"] == direct["outcome"], (
                    mode,
                    result["outcome"],
                    direct["outcome"],
                )
                assert result["totals"]["spent_microusd"] == 5 * result["mock_https_sends"]
                assert result["totals"]["reserved_microusd"] == 0
                assert all(operation["status"] == "completed" for operation in result["operations"])
                with patch.dict(
                    os.environ,
                    ENV_BASE | {"ANTHROPIC_CONFIG_DIR": str(temporary / "empty-credentials")},
                    clear=True,
                ):
                    replay = await oracle.run(provider)
                assert (
                    replay["outcome"] == result["outcome"] and replay["totals"] == result["totals"]
                ), (
                    provider,
                    mode,
                    result["outcome"],
                    replay["outcome"],
                    result["totals"],
                    replay["totals"],
                )
                assert replay["mock_https_sends"] == result["mock_https_sends"], mode
            result["replay"] = {
                "additional_mock_https_sends": replay["mock_https_sends"]
                - result["mock_https_sends"],
                "totals_unchanged": replay["totals"] == result["totals"],
                "outcome": replay["outcome"],
            }
            results.append(result)
        empty = Funded(temporary / (provider + "-authority"), "valid", authority_empty=True)
        stopped = await empty.run(provider)
        assert stopped["outcome"] == {"error": "NativeStop", "reason": "authority"}
        assert stopped["mock_https_sends"] == stopped["totals"]["operation_count"] == 0
        results.append(stopped)
    fold = Funded(temporary / "native-fold", "fold")
    folded = await fold.run("openai")
    direct = await c1.Oracle("fold", wrapped=True).run("openai")
    assert folded["outcome"] == direct["outcome"] and folded["mock_https_sends"] == 3
    assert len({call.logical_id for call in fold.calls}) == 3
    results.append(folded)
    rows = Funded(temporary / "native-rows", "rows")
    observed = await rows.run("anthropic", temporary / "rows.jsonl")
    direct = await c1.Oracle("rows", wrapped=True).run("anthropic", temporary / "direct-rows.jsonl")
    assert sorted(observed["outcome"]["value"], key=lambda row: row["id"]) == sorted(
        direct["outcome"]["value"], key=lambda row: row["id"]
    )
    assert observed["mock_https_sends"] == 6 and len({call.logical_id for call in rows.calls}) == 6
    with patch.dict(
        os.environ,
        ENV_BASE | {"ANTHROPIC_CONFIG_DIR": str(temporary / "empty-credentials")},
        clear=True,
    ):
        replay = await rows.run("anthropic", temporary / "fresh-native-cache.jsonl")
    assert replay["mock_https_sends"] == 6 and replay["totals"] == observed["totals"]
    assert sorted(replay["outcome"]["value"], key=lambda row: row["id"]) == sorted(
        observed["outcome"]["value"], key=lambda row: row["id"]
    )
    observed["fresh_native_cache_replay"] = {
        "additional_mock_https_sends": 0,
        "totals_unchanged": True,
    }
    results.append(observed)
    row_stop = Funded(temporary / "native-rows-stop", "rows_stop")
    stopped = await row_stop.run("anthropic", temporary / "stopped-native-rows.jsonl")
    assert stopped["outcome"] == {"error": "NativeStop", "reason": "unknown"}
    assert stopped["sdk_transport_calls"] == stopped["mock_https_sends"] == 1
    assert (
        stopped["operations"][0]["status"] == "unknown"
        and stopped["totals"]["reserved_microusd"] > 0
    )
    results.append(stopped)
    assert frozen == {name: c1.sha((ROOT / name).read_bytes()) for name in frozen}
    evidence = {
        "format": "buddha.review.nb02c2-funded-sdk.v1",
        "commit": c1.PIN,
        "upstream_source_sha256": c1.EXPECTED,
        "invocation_source_sha256": frozen,
        "sdk_versions": {
            name: importlib.metadata.version(name)
            for name in ("openai", "anthropic", "pydantic", "httpx", "httpx2")
        },
        "provider_network_calls": 0,
        "actual_api_keys_used": False,
        "sdk_private_methods_patched": False,
        "native_header_profiles": {name: native_headers(name) for name in CAPS},
        "limits": [
            "selected pinned functions and explicit hooks, not complete official CLI",
            "synthetic release/profile fixtures; no live maximum-price attestation",
            "in-process offline shared queue; no production IPC/cancellation cleanup",
            "Python network guard, not OS confinement or worker credential isolation",
            "raw replay preserves policy headers, not historical wall-clock timing",
        ],
        "scenarios": results,
    }
    output = ROOT / "runs/reviews/nb02c2-funded-sdk-probe.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "scenarios": len(results),
                "mock_https_sends": sum(result["mock_https_sends"] for result in results),
                "provider_network_calls": 0,
                "evidence": str(output),
            }
        )
    )


if __name__ == "__main__":
    loop = asyncio.new_event_loop()  # Windows self-pipe before Python network guard.
    try:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            with (
                patch.dict(
                    os.environ,
                    ENV_BASE
                    | {
                        "OPENAI_API_KEY": KEYS["openai"],
                        "ANTHROPIC_API_KEY": KEYS["anthropic"],
                        "ANTHROPIC_CONFIG_DIR": str(temporary / "empty-credentials"),
                    },
                    clear=True,
                ),
                patch.object(socket.socket, "connect", c1.forbidden),
                patch.object(socket.socket, "connect_ex", c1.forbidden),
                patch.object(socket, "create_connection", c1.forbidden),
                patch.object(socket, "getaddrinfo", c1.forbidden),
                patch.object(http.client.HTTPSConnection, "connect", c1.forbidden),
            ):
                loop.run_until_complete(main(temporary))
    finally:
        loop.close()
