"""Generic research oracle for the two declared compatibility implementations.

Original evaluator functions remain unwrapped. Only public SDK constructors
receive MockTransport. The pure server fixture is also used by mocked HTTPS;
it returns canned judgments and contains no evaluator formula or parser.
"""

import hashlib
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from buddha import native_worker  # noqa: E402
from buddha.channel import write_frame  # noqa: E402
from buddha.releases import _json, _load  # noqa: E402


def synthetic_reply(provider, body, counts):
    request = json.loads(body)
    content = json.loads(request["messages"][-1]["content"])
    control = content["row"]["control"]
    key = provider + hashlib.sha256(body).hexdigest()
    index = counts[key] = counts.get(key, 0) + 1
    refused = provider == "openai" and control == "refusal"
    truncated = provider == "openai" and control == "truncated" and index == 1
    text = (
        "{malformed"
        if control == "malformed" and index == 1
        else json.dumps({"value": 4 if content["judge_kind"] == "integer" else "useful"})
    )
    if provider == "openai":
        return {
            "id": "cmpl-compatible-fixture",
            "object": "chat.completion",
            "created": 0,
            "model": request["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None if refused else text,
                        "refusal": "synthetic refusal" if refused else None,
                    },
                    "finish_reason": "length" if truncated else "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
    return {
        "id": "msg-compatible-fixture",
        "type": "message",
        "role": "assistant",
        "model": request["model"],
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }


class DirectWorker(native_worker.NativeWorker):
    def __init__(self, config, reader, writer):
        config = _load(_json(config))
        if config["format"] != "buddha.compatible-direct.v1":
            raise native_worker.WorkerError("wrong direct fixture format")
        if (
            config["hooks"]["cache"] is not None
            or config["hooks"]["calls"]
            or config["hooks"]["sdk"]
        ):
            raise native_worker.WorkerError("direct fixture forbids scientific hooks")
        config["format"] = "buddha.native-worker.v1"
        super().__init__(config, reader, writer)
        self.counts, self.ordinal = {}, 0

    def prepare(self):
        if self.prepared:
            return
        super().prepare()
        for module in self.modules.values():
            for name in ("main", "map_rows", "judge"):
                function = getattr(module, name)
                if hasattr(function, "__wrapped__"):
                    raise native_worker.WorkerError("direct native function is wrapped")
            module.AsyncOpenAI = self.factory("openai")
            module.AsyncAnthropic = self.factory("anthropic")
        self.aliases = []
        self.ready_audit = self._audit_imports()

    def factory(self, provider):
        sdk = importlib.import_module("openai" if provider == "openai" else "anthropic")
        http = importlib.import_module("httpx" if provider == "openai" else "httpx2")
        original = getattr(sdk, "AsyncOpenAI" if provider == "openai" else "AsyncAnthropic")

        async def respond(request):
            write_frame(
                self.writer,
                {
                    "type": "capture",
                    "provider": provider,
                    "sequence": self.ordinal,
                    "body_sha256": hashlib.sha256(request.content).hexdigest(),
                    "headers": [
                        [name, value]
                        for name, value in request.headers.items()
                        if name.lower()
                        not in {
                            "authorization",
                            "x-api-key",
                            "host",
                            "content-length",
                            "connection",
                        }
                    ],
                },
            )
            self.ordinal += 1
            return http.Response(
                200,
                json=synthetic_reply(provider, request.content, self.counts),
                headers={
                    "x-request-id"
                    if provider == "openai"
                    else "request-id": "compatible-direct-fixture"
                },
                request=request,
            )

        def create(*args, **kwargs):
            if args or "http_client" in kwargs or "api_key" in kwargs:
                raise native_worker.WorkerError("unexpected direct SDK constructor")
            transport = http.AsyncClient(transport=http.MockTransport(respond), trust_env=False)
            self.clients.append(transport)
            if provider == "anthropic":
                kwargs.setdefault("webhook_key", native_worker.PLACEHOLDER)
            client = original(http_client=transport, api_key=native_worker.PLACEHOLDER, **kwargs)
            if client.max_retries != 8:
                raise native_worker.WorkerError("fixture SDK retries differ")
            self.clients.append(client)
            return client

        return create


if __name__ == "__main__":
    native_worker.NativeWorker = DirectWorker
    native_worker.main()
