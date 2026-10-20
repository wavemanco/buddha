# SPDX-License-Identifier: MIT
"""Confined complete-partition oracle; reuses C3A's public SDK fixture transport.

No upstream scientific function is copied, wrapped or replaced. The production
worker never imports this research helper. Run only through the owned executor.
"""

import hashlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

script_root = Path(__file__).resolve().parent
sys.path.insert(
    0, str(script_root if (script_root / "buddha").is_dir() else script_root.parents[1])
)
helper = script_root / "direct_score.py"
if not helper.is_file():
    helper = script_root / "nb02c3-direct-worker.py"
spec = importlib.util.spec_from_file_location("_buddha_direct_score_oracle", helper)
assert spec is not None and spec.loader is not None
score_oracle = importlib.util.module_from_spec(spec)
raw_helper = helper.read_bytes()
if hashlib.sha256(raw_helper).hexdigest() != (
    "286b1b564f4095532b95c509aedd85001275b54b0da8a57dd72a506a23b96c63"
):
    raise ValueError("C3A direct engineering helper differs from its preserved source")
# Execute the exact checked engineering bytes, never an adjacent bytecode cache.
exec(compile(raw_helper, str(helper), "exec"), score_oracle.__dict__)  # nosec B102
native_worker = score_oracle.native_worker
BaseWorker = native_worker.NativeWorker
EXPECTED = score_oracle.EXPECTED | {
    "src/partition.py": "263970891ff3ee1cc8df369a33beefe5cb5de618b5dd146a5234536d97954aca",
    "uv.lock": "ff6d5b15b77e4ca46a33604586eb7d99666d2802752ab962af9baa2924a50758",
}
MODES = {
    "valid",
    "repair",
    "persistent",
    "bad",
    "refusal",
    "length",
    "multiblock",
    "status",
    "mixed",
}


class DirectPartitionWorker(score_oracle.DirectWorker):
    def __init__(self, config, reader, writer):
        config = score_oracle._load(score_oracle._json(config))
        if config.get("format") != "buddha.direct-partition-worker.v1":
            raise native_worker.WorkerError("unsupported direct partition format")
        fixture = score_oracle._object(config.pop("fixture"), {"mode", "primary_model"})
        self.mode = score_oracle._text(fixture["mode"])
        self.primary = score_oracle._text(fixture["primary_model"])
        if self.mode not in MODES or config["command"]["module"] != "src.partition":
            raise native_worker.WorkerError("unsupported direct partition fixture")
        hooks = score_oracle._object(config["hooks"], {"modules", "cache", "calls", "sdk"})
        if hooks["cache"] is not None or hooks["calls"] != [] or hooks["sdk"] != []:
            raise native_worker.WorkerError("direct partition oracle forbids native hooks")
        if set(hooks["modules"]) != {
            "src.partition",
            "src.score",
            "src.summarize",
            "src.common",
            "src.judge",
            "src.evaluation_io",
        }:
            raise native_worker.WorkerError("direct partition module set differs")
        config["format"] = "buddha.native-worker.v1"
        BaseWorker.__init__(self, config, reader, writer)
        self.capture_sequence = 0
        self.response_counts = {}

    def prepare(self):
        if self.prepared:
            return
        for relative, expected in EXPECTED.items():
            if score_oracle.file_hash(self.roots["official"] / relative) != expected:
                raise native_worker.WorkerError("direct partition source differs from pin")
        BaseWorker.prepare(self)
        partition, judge, evaluation_io = (
            self.modules[name] for name in ("src.partition", "src.judge", "src.evaluation_io")
        )
        assert partition.run_cached is evaluation_io.run_cached
        assert partition.run_stage is judge.run_stage
        assert partition.STAGE.calls is partition.partition_calls
        assert partition.STAGE.fold is partition.partition_fold
        for function in (
            partition.main,
            partition.process_instances,
            partition.partition_llm,
            evaluation_io.run_cached,
            judge.run_stage,
            judge.judge_call,
            judge.judge,
        ):
            assert inspect.iscoroutinefunction(function) and not hasattr(function, "__wrapped__")
        assert not hasattr(partition.partition_fold, "__wrapped__")
        self.modules["src.common"].AsyncOpenAI = self.factory("openai")
        judge.anthropic = SimpleNamespace(AsyncAnthropic=self.factory("anthropic"))
        self.aliases = [
            {"path": "src.common:AsyncOpenAI", "label": "fixture-sdk:openai"},
            {"path": "src.judge:anthropic", "label": "fixture-sdk:anthropic"},
        ]
        self.ready_audit = self._audit_imports()

    def respond(self, provider, http, request):
        # C3A handles observational body/header capture and verifies actual SDK
        # max_retries=8. Only these synthetic server JSON values differ here.
        response = score_oracle.DirectWorker.respond(self, provider, http, request)
        if self.mode == "status":
            return http.Response(
                503,
                json={"error": {"type": "overloaded_error", "message": "fixture"}},
                headers={"retry-after": "0.001"},
                request=request,
            )
        payload = response.json()
        key = hashlib.sha256(request.content).hexdigest()
        count = self.response_counts[key] = self.response_counts.get(key, 0) + 1
        if self.mode not in {"bad", "refusal", "length"}:
            invalid = self.mode == "persistent" or self.mode == "repair" and count == 1
            groups = [[0, 0], [1, 2]] if invalid else [[0, 2, 4, 6, 8], [1, 3, 5, 7, 9]]
            text = json.dumps({"groups": groups}, separators=(",", ":"))
            if self.mode == "mixed" and b"task with text identifier" in request.content:
                text = "{malformed judgment"
            if provider == "openai":
                payload["choices"][0]["message"]["content"] = text
            else:
                next(block for block in payload["content"] if block["type"] == "text")["text"] = (
                    text
                )
        return http.Response(
            response.status_code, json=payload, headers=response.headers, request=request
        )


if __name__ == "__main__":
    native_worker.NativeWorker = DirectPartitionWorker
    native_worker.main()
