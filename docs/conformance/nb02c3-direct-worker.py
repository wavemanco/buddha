# SPDX-License-Identifier: MIT
"""Research-only confined direct oracle for the pinned complete native modules.

Use the host's image-attesting executor, never a host interpreter with untrusted
source. Generic input/audit/file lifecycle is shared; scientific functions are
original, unwrapped imports. Only public SDK constructors use canned transports.
There is no provider sender, financial authority, context hook or source AST copy.
"""

import base64
import hashlib
import importlib
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
script_root = Path(__file__).resolve().parent
sys.path.insert(
    0, str(script_root if (script_root / "buddha").is_dir() else script_root.parents[1])
)

from buddha import native_worker  # noqa: E402
from buddha.channel import write_frame  # noqa: E402
from buddha.releases import _json, _load, _object, _text, file_hash  # noqa: E402

PIN = "64a23be6b18ec1dacc298830aab276061b6e143c"
EXPECTED = {
    "src/judge.py": "4decf04790b90a03368eb792dfe29045435914a73ab83a52185d9dd0d1613902",
    "src/score.py": "418985a40e9e159cfeffe9a43ab2c727010d7a7a29407f4e14cab3c81b77cbae",
    "src/common.py": "ba60bf0f2a409c3774d75880f305325a28ed34320610667542a4596c41f424af",
    "src/evaluation_io.py": "8a34e01308677469d984dd59e36412c2994baf2554fd3a5f026be9ef98a3a5c7",
    "src/summarize.py": "0a8bd1eb7f317584f579eaa827e580f9cefe4177a1abdc35b2cb06ef96eeea9e",
    "LICENSE": "14e69e7fbb2f8fd0aa8ccf17d7d4ddd54665555c613a0336767f7a5fa477895c",
}
MODES = {"valid", "bad", "refusal", "length", "duplicate", "multiblock", "range"}
PUBLIC_HEADERS = frozenset({"authorization", "x-api-key", "host", "content-length", "connection"})


class DirectWorker(native_worker.NativeWorker):
    def __init__(self, config, reader, writer):
        config = _load(_json(config))
        if config.get("format") != "buddha.direct-native-worker.v1":
            raise native_worker.WorkerError("direct oracle requires its research-only format")
        fixture = _object(config.pop("fixture"), {"mode", "primary_model"})
        self.mode = _text(fixture["mode"])
        self.primary = _text(fixture["primary_model"])
        if self.mode not in MODES:
            raise native_worker.WorkerError("unsupported direct oracle fixture")
        hooks = _object(config["hooks"], {"modules", "cache", "calls", "sdk"})
        if hooks["cache"] is not None or hooks["calls"] != [] or hooks["sdk"] != []:
            raise native_worker.WorkerError("direct oracle forbids native function instrumentation")
        if set(hooks["modules"]) != {
            "src.score",
            "src.summarize",
            "src.common",
            "src.judge",
            "src.evaluation_io",
        }:
            raise native_worker.WorkerError("direct oracle requires the complete pinned module set")
        if config["command"]["module"] not in {"src.score", "src.summarize"}:
            raise native_worker.WorkerError("direct oracle supports score and summary only")
        config["format"] = "buddha.native-worker.v1"
        super().__init__(config, reader, writer)
        self.capture_sequence = 0

    def prepare(self):
        if self.prepared:
            return
        for relative, expected in EXPECTED.items():
            if file_hash(self.roots["official"] / relative) != expected:
                raise native_worker.WorkerError("direct oracle official source differs from pin")
        super().prepare()
        score, judge, evaluation_io = (
            self.modules[name] for name in ("src.score", "src.judge", "src.evaluation_io")
        )
        assert score.run_cached is evaluation_io.run_cached
        assert score.judge_call is judge.judge_call
        for function in (
            score.main,
            score.process_instances,
            score.score_llm,
            evaluation_io.run_cached,
            judge.judge_call,
            judge.judge,
        ):
            assert inspect.iscoroutinefunction(function)
            assert not hasattr(function, "__wrapped__")
        assert not hasattr(self.modules["src.summarize"].main, "__wrapped__")
        common = self.modules["src.common"]
        common.AsyncOpenAI = self.factory("openai")
        # Only the official module's public constructor reference is replaced.
        # The actual SDK module/class and all native judge functions stay intact.
        judge.anthropic = SimpleNamespace(AsyncAnthropic=self.factory("anthropic"))
        self.aliases = [
            {"path": "src.common:AsyncOpenAI", "label": "fixture-sdk:openai"},
            {"path": "src.judge:anthropic", "label": "fixture-sdk:anthropic"},
        ]
        self.ready_audit = self._audit_imports()

    def factory(self, provider):
        sdk = importlib.import_module(provider)
        http = importlib.import_module("httpx" if provider == "openai" else "httpx2")
        constructor = getattr(sdk, "AsyncOpenAI" if provider == "openai" else "AsyncAnthropic")

        async def respond(request):
            return self.respond(provider, http, request)

        def create(*args, **kwargs):
            if args or "http_client" in kwargs or "api_key" in kwargs:
                raise native_worker.WorkerError("direct fixture constructor options differ")
            http_client = http.AsyncClient(transport=http.MockTransport(respond), trust_env=False)
            self.clients.append(http_client)
            kwargs["api_key"] = native_worker.PLACEHOLDER
            if provider == "anthropic":
                kwargs["webhook_key"] = native_worker.PLACEHOLDER
            client = constructor(http_client=http_client, **kwargs)
            self.clients.append(client)
            return client

        return create

    def respond(self, provider, http, request):
        body = json.loads(request.content)
        model = body["model"]
        assert self.modules["src.judge"].judge_client(model).max_retries == 8
        # Capture is observational only; no financial request frame is emitted.
        write_frame(
            self.writer,
            {
                "type": "capture",
                "seq": self.capture_sequence,
                "provider": provider,
                "model": model,
                "sdk_max_retries": 8,
                "method": request.method,
                "url": str(request.url),
                "body_sha256": hashlib.sha256(request.content).hexdigest(),
                "body_base64": base64.b64encode(request.content).decode("ascii"),
                "headers": [
                    [name, value]
                    for name, value in request.headers.items()
                    if name.lower() not in PUBLIC_HEADERS
                ],
            },
        )
        self.capture_sequence += 1
        text = '{"score":7}'
        if self.mode == "bad":
            text = "{malformed judgment"
        elif self.mode == "duplicate":
            text = '{"score":1,"score":7}'
        elif self.mode == "range":
            text = '{"score":11}'
        refused = self.mode == "refusal" and model == self.primary
        if provider == "openai":
            payload = {
                "id": "cmpl-direct-fixture",
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
        else:
            content = [{"type": "text", "text": text}]
            if self.mode == "multiblock":
                content = [
                    {"type": "thinking", "thinking": "fixture", "signature": "fixture"},
                    *content,
                    {"type": "text", "text": '{"score":1}'},
                ]
            payload = {
                "id": "msg-direct-fixture",
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
        return http.Response(
            200,
            json=payload,
            headers={"x-request-id" if provider == "openai" else "request-id": "direct-fixture"},
            request=request,
        )


if __name__ == "__main__":
    # This replacement is confined to this research helper process. Production
    # native_worker.py never imports it and has no fixture transport switch.
    native_worker.NativeWorker = DirectWorker
    native_worker.main()
