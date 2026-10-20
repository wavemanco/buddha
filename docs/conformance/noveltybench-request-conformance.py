"""Offline pinned-upstream request/failure audit; never executes an API transport."""

import ast
import contextlib
import functools
import hashlib
import importlib.metadata
import io
import json
import random
import socket
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def forbidden(*args, **kwargs):
    raise AssertionError("offline audit forbids network/provider dispatch")


socket.socket.connect = forbidden
socket.create_connection = forbidden

from pydantic import BaseModel
from openai.lib._parsing._completions import type_to_response_format_param

from buddha import benchmark, run
from buddha.archive import Candidate
from buddha.policy import Policy, propose_call
from buddha.provider import BudgetBroker, HTTPTransport, ModelSpec, PreparedHTTP, Reply

HTTPTransport.send = forbidden
HTTPTransport.prepare = forbidden
BudgetBroker.execute = forbidden

COMMIT = "64a23be6b18ec1dacc298830aab276061b6e143c"
REFERENCE = ROOT / "runs/references/noveltybench-conformance" / COMMIT
RUNS = [ROOT / "runs/first-live-recovery", ROOT / "runs/first-live-continuation-v2"]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def record(path):
    value = read(path)
    expected = value.pop("record_sha256")
    assert run._sha(value) == expected, str(path)
    return value


def inventory():
    files = list(REFERENCE.rglob("*")) + list((ROOT / "buddha").glob("*.py"))
    for directory in RUNS:
        files += list(directory.rglob("*"))
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in files if p.is_file()}


def extract(name, names, namespace):
    path = REFERENCE / "src" / name
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        declared = getattr(node, "name", None)
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            declared = getattr(node.targets[0], "id", None)
        if declared in names:
            nodes.append(node)
    assert len(nodes) == len(names), (name, names)
    exec(compile(ast.Module(nodes, type_ignores=[]), str(path), "exec"), namespace)


async def local_gather(*coroutines):
    # Pure immediate fixture coroutines only; no event loop or Windows self-pipe socket.
    return [await coroutine for coroutine in coroutines]


def immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    raise AssertionError("offline fixture unexpectedly suspended")


def upstream():
    seals = read(REFERENCE / "download-seals.json")
    for name, expected in seals.items():
        assert sha((REFERENCE / name).read_bytes()) == expected, name
    ns = dict(__name__="pinned_upstream_probe", dataclass=dataclass, BaseModel=BaseModel, Stage=object,
              asyncio=SimpleNamespace(gather=local_gather), functools=functools, random=random)
    extract("common.py", {"render_responses", "DEFAULT_JUDGE"}, ns)
    extract("judge.py", {"Call", "DEFAULT_EFFORT", "JudgeRefusal", "shuffled_order",
                         "strict_schema", "anthropic_params", "parse_message", "judge",
                         "judge_call", "run_stage"}, ns)
    ns["judge_anthropic_params"] = ns.pop("anthropic_params")
    extract("partition.py", {"JUDGE_SYSTEM", "Partition", "partition_calls",
                             "canonical", "partition_fold"}, ns)
    extract("score.py", {"SCORE_SYSTEM", "Score", "heads", "score_calls", "spread",
                         "score_refused"}, ns)
    ns["InferenceService"] = object
    extract("inference.py", {"openai_params", "anthropic_params", "REFUSED", "EMPTY",
                             "openai_text", "anthropic_text", "run_generation",
                             "validate_generations", "AnthropicService"}, ns)
    ns["inference_anthropic_params"] = ns["anthropic_params"]
    ns["anthropic_params"] = ns["judge_anthropic_params"]
    return ns, seals


def operation_rows(directory):
    with contextlib.closing(sqlite3.connect(
            (directory / "operations.sqlite3").resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        return {r["operation_id"]: dict(r) for r in db.execute("SELECT * FROM operations")}


def audit_runs(ns):
    checks, differences = [], Counter()
    for directory in RUNS:
        manifest, report = record(directory / "manifest.json"), record(directory / "report.json")
        settings = run.RunSettings.from_record(manifest["settings"])
        operations = operation_rows(directory)
        inherited = {item["operation_id"]: item for item in
                     manifest.get("continuation", {}).get("inherited", [])}
        seen, counts = set(), Counter()
        policies, evidence, candidates, judge_details, generation_details = {}, {}, [], [], []

        def verify(stage, index, candidate_id, prompt_id, call):
            prefix = ([manifest["run_id"], "proposal", index] if stage == "proposal" else
                      [manifest["run_id"], "candidate", candidate_id])
            identity = run._sha([*prefix, prompt_id, stage, index])
            if identity in inherited:
                ref = inherited[identity]
                assert call.fingerprint() == ref["request_sha256"]
                return Reply.from_record(ref["reply"])
            saved = operations[identity]
            assert saved["request_sha256"] == call.fingerprint(), (directory, stage, identity)
            assert saved["status"] == "completed"
            reply = Reply.from_record(json.loads(saved["response_json"]))
            assert reply.model == call.spec.model
            assert reply.provider_request_id == saved["provider_request_id"]
            assert saved["reserve_microusd"] == call.spec.reserve_microusd()
            assert saved["actual_microusd"] == call.spec.cost_microusd(
                reply.input_tokens, reply.output_tokens)
            assert identity not in seen
            seen.add(identity)
            counts[stage] += 1
            return reply

        for candidate in report["candidates"]:
            identity = candidate["candidate_id"]
            folder = directory / "candidates" / identity
            policy = Policy.from_record(record(folder / "policy.json"))
            assert policy.fingerprint() == identity
            policies[identity] = policy
            rows = [json.loads(line) for line in
                    (folder / "evaluation/v1.1/scores.jsonl").read_bytes().splitlines()]
            evidence[identity] = rows
            candidates.append(Candidate(identity, candidate["parent_id"],
                              candidate["mean_utility"], candidate["mean_distinct"]))
            for row in rows:
                previous = []
                for index, text in enumerate(row["generations"]):
                    call = run._generation(settings.generation, row["prompt"],
                        instructions=policy.instructions,
                        history=previous if policy.sampling == "in-context" else ())
                    reply = verify("generation", index, identity, row["id"], call)
                    assert text == ("[refused]" if reply.refused else
                                    reply.text if reply.text.strip() else "[empty]")
                    local = json.loads(call.body_json)
                    messages = [{"role": "system", "content": policy.instructions}] if policy.instructions else []
                    messages.append({"role": "user", "content": row["prompt"]})
                    if policy.sampling == "in-context":
                        for earlier in previous:
                            messages.extend([{"role": "assistant", "content": earlier},
                                {"role": "user", "content": "Can you generate a different answer?"}])
                    native = ns["openai_params"](settings.generation.model, messages,
                        max_tokens=2048, reasoning_effort="low")
                    assert local == native | {"service_tier": "default"}
                    generation_details.append(dict(candidate_id=identity, index=index,
                        sampling=policy.sampling, policy_instructions_sha256=sha(policy.instructions.encode()),
                        request_sha256=call.fingerprint(), upstream_body_except_tier_matches=True,
                        finish_reason=reply.finish_reason, refused=reply.refused,
                        actual_output_tokens=reply.output_tokens,
                        inherited=run._sha([manifest["run_id"], "candidate", identity,
                            row["id"], "generation", index]) in inherited))
                    previous.append(text)

                native = ns["partition_calls"](row, {"seed": settings.ordering_seed})[0]
                order = benchmark.partition_order(row["prompt"], 10, settings.ordering_seed)
                call = run._judge(settings.partition, benchmark.PARTITION_SYSTEM,
                    benchmark.render_responses(row["prompt"], [row["generations"][i] for i in order]),
                    "Partition")
                reply = verify("partition", 0, identity, row["id"], call)
                local = json.loads(call.body_json)
                expected_format = type_to_response_format_param(native.schema)
                expected = {"model": settings.partition.model,
                    "messages": [{"role": "system", "content": native.system},
                                 {"role": "user", "content": native.user}],
                    "response_format": expected_format}
                assert local == expected | {"service_tier": "default", "max_completion_tokens": 16000}
                parsed = native.schema.model_validate_json(reply.text)
                assert ns["partition_fold"](row, [parsed], {"seed": settings.ordering_seed})[
                    "partition"] == row["partition"]
                differences["partition_extra_cap_and_tier"] += 1
                judge_details.append(dict(operation_stage="partition", candidate_id=identity,
                    request_sha256=call.fingerprint(), system_sha256=sha(native.system.encode()),
                    user_sha256=sha(native.user.encode()), full_response_texts_and_order_match=True,
                    sdk_response_format_matches=True, model=call.spec.model,
                    output_cap=16000, actual_output_tokens=reply.output_tokens,
                    finish_reason=reply.finish_reason, refused=reply.refused))

                native_calls = ns["score_calls"](row, {})
                heads = ns["heads"](row["partition"])
                assert heads == [i for i, value in enumerate(row["generation_scores"])
                                 if value is not None]
                for index, native in zip(heads, native_calls, strict=True):
                    user = f"<prompt>\n{row['prompt']}\n</prompt>\n\n<response>\n{row['generations'][index]}\n</response>"
                    call = run._judge(settings.quality, benchmark.SCORE_SYSTEM, user, "Score")
                    reply = verify("score", index, identity, row["id"], call)
                    local = json.loads(call.body_json)
                    expected = ns["judge_anthropic_params"](settings.quality.model, native, "high")
                    assert local == expected | {"service_tier": "standard_only"}
                    assert native.schema.model_validate_json(reply.text).score == row[
                        "generation_scores"][index]
                    differences["score_extra_tier"] += 1
                    judge_details.append(dict(operation_stage="score", index=index,
                        candidate_id=identity, request_sha256=call.fingerprint(),
                        system_sha256=sha(native.system.encode()), user_sha256=sha(native.user.encode()),
                        full_response_text_matches=True, strict_schema_matches=True,
                        model=call.spec.model, effort="high", thinking="adaptive", output_cap=16000,
                        actual_output_tokens=reply.output_tokens, finish_reason=reply.finish_reason,
                        refused=reply.refused, returned_service_tier=reply.service_tier))
        for decision in report["decisions"]:
            parent = policies[decision["parent_id"]]
            call = propose_call(settings.generation, parent=parent,
                feedback=[] if manifest["spec"]["method"] == "uninformed" else
                         evidence[decision["parent_id"]], method=manifest["spec"]["method"])
            reply = verify("proposal", decision["iteration"], None, "development", call)
            assert sha(reply.text.encode(errors="surrogatepass")) == decision["proposal_sha256"]
        assert seen == set(operations)
        checks.append(dict(directory=str(directory.relative_to(ROOT)), run_id=manifest["run_id"],
            physical_count=len(operations), inherited_count=len(inherited), stages=dict(counts),
            ordering_seed=settings.ordering_seed, configured_partition_model=settings.partition.model,
            configured_quality_model=settings.quality.model, judges=judge_details,
            generations=generation_details))
    return checks, dict(differences)


def failure_probes(ns):
    results = {}

    def anthropic_message(texts, stop="end_turn"):
        return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=t)
                                                        for t in texts])

    def envelope(texts, stop="end_turn"):
        return dict(model="claude-opus-5", content=[dict(type="text", text=t) for t in texts],
                    stop_reason=stop, usage=dict(input_tokens=1, output_tokens=1,
                                               service_tier="standard"))

    for label, texts in [("single_text", ['{"score":7}']),
                         ("two_text_blocks", ['{"score":7}', 'additional text'])]:
        native = ns["parse_message"](anthropic_message(texts), ns["Score"]).score
        reply = HTTPTransport._reply("anthropic", envelope(texts), "req_fixture123")
        try:
            local = run._judgment(reply)
        except Exception as error:
            local = type(error).__name__
        results[label] = dict(upstream=native, local=local)
    for name, payload in [("string", '{"score":"7"}'), ("boolean", '{"score":true}'),
                          ("integer_float", '{"score":7.0}'),
                          ("extra_property", '{"score":7,"extra":1}'),
                          ("duplicate_key", '{"score":6,"score":7}')]:
        native = ns["Score"].model_validate_json(payload).score
        try:
            manifest = record(RUNS[0] / "manifest.json")
            settings = run.RunSettings.from_record(manifest["settings"])
            prompt = benchmark.Prompt("fixture", "task")
            protocol = run._protocol(settings, "a" * 64, (prompt,))
            def execute(prompt_id, stage, index, call):
                text = (f"answer-{index}" if stage == "generation" else
                        json.dumps({"groups": [[i] for i in range(10)]})
                        if stage == "partition" else payload)
                return Reply(text, call.spec.model, "fixture-id", 1, 1,
                             "end_turn" if call.spec.provider == "anthropic" else "stop")
            run.evaluate_prompts((prompt,), settings=settings, protocol=protocol, execute=execute)
            accepted = True
        except Exception:
            accepted = False
        results["pydantic_" + name] = dict(upstream_score=native, local_accepts=accepted)
    for stop in ("refusal", "max_tokens"):
        try:
            ns["parse_message"](anthropic_message(['{"score":7}'], stop), ns["Score"])
        except Exception as error:
            native = type(error).__name__
        try:
            run._judgment(HTTPTransport._reply("anthropic", envelope(['{"score":7}'], stop),
                                             "req_fixture123"))
        except Exception as error:
            local = type(error).__name__
        results[stop] = dict(upstream=native, local=local)

    async def retry_fold():
        called = []
        async def fake_call(model, call, effort, fallback):
            called.append(model)
            return ns["Partition"](groups=[[0]]), model
        original = ns["judge_call"]
        ns["judge_call"] = fake_call
        try:
            stage = SimpleNamespace(name="partition", calls=ns["partition_calls"],
                fold=ns["partition_fold"], on_refusal=None)
            with contextlib.redirect_stdout(io.StringIO()):
                folded = await ns["run_stage"](stage,
                    dict(id="probe", prompt="p", generations=["a", "b"]),
                    dict(judge_model="fixture", seed=None))
            return dict(upstream_calls=len(called), upstream_partition=folded["partition"],
                        local_single_fold_raises=True)
        finally:
            ns["judge_call"] = original
    try:
        benchmark.fold_partition([[0]], prompt="p", n=2, seed=None)
        raise AssertionError("local malformed partition unexpectedly accepted")
    except benchmark.ValidationError:
        pass
    results["malformed_partition_fold_retry_leniency"] = immediate(retry_fold())

    async def fallback():
        called = []
        original = ns["judge"]
        async def fake_judge(model, call, effort):
            called.append(model)
            if model == "primary":
                raise ns["JudgeRefusal"]("fixture refusal")
            return ns["Score"](score=7)
        ns["judge"] = fake_judge
        try:
            score, used = await ns["judge_call"]("primary", None, "high", "fallback")
            return dict(upstream_models=called, upstream_used=used, score=score.score,
                        local_automatic_fallback=False)
        finally:
            ns["judge"] = original
    results["anthropic_refusal_fallback"] = immediate(fallback())
    class FixtureBadRequest(Exception):
        pass
    ns["BadRequestError"] = FixtureBadRequest
    async def content_filtered(**kwargs):
        raise FixtureBadRequest("HTTP400 content filtering")
    service = object.__new__(ns["AnthropicService"])
    service.client = SimpleNamespace(messages=SimpleNamespace(create=content_filtered))
    native = immediate(service.create({"model": "claude-fixture"}))
    assert native == "[refused]"
    class Connection:
        def __init__(self):
            self.requests = 0
        def request(self, *args, **kwargs):
            self.requests += 1
        def getresponse(self):
            return SimpleNamespace(status=400, read=lambda limit: b'{"error":{"message":"content filtering"}}')
    connection = Connection()
    prepared = PreparedHTTP("anthropic", "/v1/messages", b"{}", (), connection)
    try:
        HTTPTransport.send_prepared(object.__new__(HTTPTransport), prepared)
        raise AssertionError("local HTTP400 unexpectedly accepted")
    except benchmark.ValidationError as error:
        local = type(error).__name__
    results["anthropic_generation_http400_content_filter"] = dict(upstream=native,
        local=local, local_attempts=connection.requests,
        note="Fake in-memory HTTP object; no credentials or real network.")
    return results


def native_judge_probe(ns):
    requests, options = [], []
    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self.parse))
            self.messages = SimpleNamespace(create=self.create)

        def with_options(self, **kwargs):
            options.append(kwargs)
            return self

        async def parse(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                parsed=ns["Partition"](groups=[[0]])))])

        async def create(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(
                type="text", text='{"score":7}')])

    client = FakeClient()
    ns["anthropic"] = SimpleNamespace(AsyncAnthropic=lambda: client)
    ns["oai_client"] = lambda: client
    extract("judge.py", {"judge_client"}, ns)
    partition_call = ns["Call"]("system", "user", ns["Partition"])
    score_call = ns["Call"]("system", "user", ns["Score"])
    immediate(ns["judge"]("gpt-5.6-luna", partition_call, "high"))
    immediate(ns["judge"]("gpt-5.6-luna", partition_call, "low"))
    immediate(ns["judge"]("claude-opus-5", score_call, "high"))
    assert requests[0] == requests[1]
    converted = requests[0] | {"response_format": type_to_response_format_param(
        requests[0]["response_format"])}
    assert options == [{"max_retries": 8}, {"max_retries": 8}]
    return dict(openai_request=converted, anthropic_request=requests[2],
        changing_effort_high_to_low_does_not_change_openai_request=True,
        configured_sdk_retries=options,
        note="Fake clients capture native constructor kwargs; no SDK client/key or provider created.")


def generation_probes(ns):
    class Service:
        def __init__(self):
            self.calls, self.count = [], 0

        async def generate(self, *, model, messages, n=1, **kwargs):
            self.calls.extend(json.loads(json.dumps(messages)) for _ in range(n))
            outputs = [f"answer-{self.count + i}" for i in range(n)]
            self.count += n
            return outputs

    result = {}
    for mode in ("regenerate", "in-context"):
        service = Service()
        outputs = immediate(ns["run_generation"](service, "model", "task", None, 10, mode))
        previous = []
        for messages, answer in zip(service.calls, outputs, strict=True):
            spec = ModelSpec("openai", "model", 100000, 4096, 1, 1,
                             "https://example.org/offline")
            local = json.loads(run._generation(spec, "task", history=previous if mode == "in-context" else ()).body_json)
            assert local == ns["openai_params"]("model", messages, max_tokens=2048,
                                               reasoning_effort="low") | {"service_tier": "default"}
            previous.append(answer)
        result[mode] = dict(per_sample_body_count=len(service.calls), native_messages_match=True)
    anthropic_spec = ModelSpec("anthropic", "claude-fixture", 100000, 4096, 1, 1,
                              "https://example.org/offline")
    for instructions, previous in [("", ()), ("Candidate policy only", ("earlier", "[empty]", "[refused]"))]:
        messages = ([dict(role="system", content=instructions)] if instructions else []) + [dict(role="user", content="task")]
        for text in previous:
            messages.extend([dict(role="assistant", content=text), dict(role="user", content="Can you generate a different answer?")])
        native = ns["inference_anthropic_params"]("claude-fixture", messages,
                                                max_tokens=2048, reasoning_effort="low")
        local = json.loads(run._generation(anthropic_spec, "task", instructions=instructions,
                                          history=previous).body_json)
        assert local == native | {"service_tier": "standard_only"}
    result["anthropic_body_fixtures"] = "plain and instruction/history requests match except explicit tier"
    normalized = []
    for text, stop, refusal in [("text", "stop", None), ("", "stop", None),
                                 ("   ", "length", None), ("partial", "length", None),
                                 ("text", "content_filter", None), (None, "stop", "refusal")]:
        choice = SimpleNamespace(finish_reason=stop, message=SimpleNamespace(content=text, refusal=refusal))
        native = ns["openai_text"](SimpleNamespace(choices=[choice]))
        envelope = dict(model="model", usage=dict(prompt_tokens=1, completion_tokens=1),
            choices=[dict(finish_reason=stop, message=dict(content=text, refusal=refusal))])
        reply = HTTPTransport._reply("openai", envelope, "req_fixture123")
        local = "[refused]" if reply.refused else reply.text if reply.text.strip() else "[empty]"
        assert native == local
        normalized.append(dict(stop=stop, refusal=bool(refusal), output=native))
    result["openai_normalization"] = normalized
    return result


def main():
    before = inventory()
    ns, seals = upstream()
    checks, differences = audit_runs(ns)
    probes = failure_probes(ns)
    native = native_judge_probe(ns)
    generation = generation_probes(ns)
    assert before == inventory(), "audit changed an input"
    result = dict(format="buddha.noveltybench-request-conformance.v1", reference_commit=COMMIT,
        upstream_seals=seals, inputs_sha256=before, input_hashes_unchanged=True,
        sdk_probe_versions={name: importlib.metadata.version(name) for name in
                            ("pydantic", "openai", "anthropic", "numpy")},
        sdk_version_limit="Installed SDK schema probe is not a historical SDK version attestation.",
        upstream_cli_default_judge=ns["DEFAULT_JUDGE"], runs=checks,
        request_differences=differences, adversarial_probes=probes, native_judge_probe=native,
        generation_probes=generation,
        network_calls=0, api_keys_read=False)
    output = ROOT / "runs/reviews/noveltybench-request-conformance.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("format", "input_hashes_unchanged",
        "sdk_probe_versions", "upstream_cli_default_judge", "request_differences", "adversarial_probes")},
        sort_keys=True))


if __name__ == "__main__":
    main()
