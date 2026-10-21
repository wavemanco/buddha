"""Actual confined forty-target study composition; synthetic host HTTPS only.

Requires the reviewed CPU image, frozen study inputs and preserved local history.
This never judges semantics, uses real provider credentials, or changes history.
"""

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import sys
import traceback
import uuid
from collections import Counter
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

if not __debug__:
    raise RuntimeError("MEAS02_NATIVE_PROBE_OPTIMIZED_MODE_UNSUPPORTED")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.authorization import Authorization  # noqa: E402
from buddha.executor import Limits, _endpoint  # noqa: E402
from buddha.gateway import Gateway, RawHTTPTransport, ReceivedReply  # noqa: E402
from buddha.native_run import RUNNER_FILES, NativeSession  # noqa: E402
from buddha.provider import ModelSpec  # noqa: E402
from buddha.releases import Release, _json, inventory, prepare_selection  # noqa: E402

SCRIPT = Path(__file__).resolve()
HELPER = ROOT / "docs/conformance/nb02c3c3-baseline-probe.py"
HELPER_SHA = "d4eb66a332e6d54365cd30be0ea1189492e1742327dc828c5d60855b1fb4c1ea"
ENVIRONMENT = ROOT / "docs/conformance/nb02c3b-runtime-environment.json"
HEADER_EVIDENCE = ROOT / "docs/conformance/nb02c3b-funded-native-evidence.json"
PACK = ROOT / "docs/conformance/meas01-study/pack.json"
PROPOSAL = ROOT / "docs/conformance/meas02-target-proposal.json"
PROVENANCE = ROOT / "docs/conformance/meas01-adjudication-review.json"
OPERATOR = ROOT / "docs/conformance/meas02-run.py"
KEY = "offline-meas02-not-a-real-api-key"
OCCASIONS = ("baseline", "same-order-repeat", "order-seed-0", "order-seed-20261020")
STORAGE_SEALS = {
    "docs/conformance/nb01-preservation.json": (
        "29a0f3e272e6bd19b8b94c3a090c38b3403a95ef71a124b847cab3d8e90f46d4"
    ),
    "docs/conformance/rec05c-code-preservation.json": (
        "f6d89868c5a45c3bef2d91f7d5a7d0c7bac81dd7c69f8f7158dcc35a623af331"
    ),
    "docs/snapshots/pilot-runtime-2026-10-19.zip": (
        "bd32c4d50339e2f2e1cadf01f5872fa3c1cdf12c196e7676a18d6fe96bd534e0"
    ),
    "runs/first-live-authorization-v2.sqlite3": (
        "52d293f04921af5418a46a0ce33b1ffd296ae3753cbd3aee7da5130f3dd2c06a"
    ),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open("xb") as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def load_engineering(path, expected=None):
    raw = path.read_bytes()
    if expected is not None and sha(raw) != expected:
        raise ValueError("reviewed engineering source changed: " + str(path))
    module = ModuleType("_meas02_" + path.stem.replace("-", "_"))
    module.__file__ = str(path)
    # The checked engineering helper executes; official code stays in Docker.
    exec(compile(raw, str(path), "exec"), module.__dict__)  # nosec B102
    module.__consumed_source_sha256__ = sha(raw)
    return module


def preservation():
    result = dict(STORAGE_SEALS)
    for name, expected in STORAGE_SEALS.items():
        assert sha((ROOT / name).read_bytes()) == expected, name
    preserved = json.loads((ROOT / "docs/conformance/nb01-preservation.json").read_bytes())
    sources = json.loads((ROOT / "docs/conformance/rec05c-code-preservation.json").read_bytes())
    assert len(preserved["input_sha256"]) == 287
    assert len(sources["source_sha256"]) == 36
    result.update(preserved["input_sha256"])
    result.update(sources["source_sha256"])
    for name, expected in result.items():
        assert sha((ROOT / name).read_bytes()) == expected, name
    return result


def operations(directory):
    path = directory / "operations.sqlite3"
    with closing(sqlite3.connect(":memory:")) as database:
        database.deserialize(path.read_bytes())
        database.execute("PRAGMA query_only=ON")
        database.execute("PRAGMA trusted_schema=OFF")
        database.row_factory = sqlite3.Row
        return [dict(row) for row in database.execute("SELECT * FROM operations ORDER BY rowid")]


def arguments(seed):
    result = [
        "--eval-dir",
        "{artifacts}",
        "--version",
        "1.1",
        "--alg",
        "llm",
        "--judge-model",
        "test-model",
        "--concurrency",
        "1",
    ]
    return result if seed is None else result + ["--seed", str(seed)]


def setup(directory, helper, *, max_calls=80, budget=100_000_000, shared_budget=None):
    roots = {
        name: directory / name for name in ("official", "runner", "environment", "host", "agent")
    }
    for path in roots.values():
        path.mkdir(parents=True)
    helper.official_copy(roots["official"])
    helper.runner_copy(roots["runner"], RUNNER_FILES)
    env_raw = ENVIRONMENT.read_bytes()
    assert sha(env_raw) == helper.SEALED[ENVIRONMENT]
    env = json.loads(env_raw)
    (roots["environment"] / "environment.json").write_bytes(env_raw)
    (roots["agent"] / "identity.txt").write_bytes(
        b"supplied semantic audit controls; no agent execution or C1 derivation\n"
    )
    (roots["host"] / "engineering-probe.py").write_bytes(SCRIPT.read_bytes())
    spec = ModelSpec(
        "openai",
        "test-model",
        2_000_000,
        128_000,
        1_000_000,
        2_000_000,
        "https://example.org/synthetic-only-no-provider-access",
    )
    header_raw = HEADER_EVIDENCE.read_bytes()
    assert sha(header_raw) == helper.SEALED[HEADER_EVIDENCE]
    profile = {
        "spec": asdict(spec),
        "response_models": ["test-model"],
        "request_tiers": ["auto", "default"],
        "response_tiers": ["", "default"],
        "allow_omitted_tier": True,
        "headers": json.loads(header_raw)["observed_linux_sdk_headers"]["openai"],
        "account_headers": {},
    }
    (roots["host"] / "profiles.json").write_bytes(
        _json({"format": "buddha.gateway-profiles.v2", "profiles": {"judge": profile}})
    )
    release = Release.from_record(
        {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "noveltybench",
            "release": "1.1-supplied-study-partition",
            "upstream": {
                "url": "https://github.com/novelty-bench/novelty-bench",
                "revision": helper.PIN,
            },
            "source": inventory(roots["official"]),
            "dependency_lock": "uv.lock",
            "task": {
                "dataset": "data/curated.jsonl",
                "id_field": "id",
                "prompt_field": "prompt",
                "answers_field": "generations",
                "count": 10,
            },
            "commands": [
                {"module": "src.partition", "argv": arguments(seed)}
                for seed in (None, None, 0, 20261020)
            ],
            "artifacts": {
                "answers": "generations.jsonl",
                "results": ["v1.1/partitions.jsonl"],
                "summary": "v1.1/summary.json",
            },
            "requires": ["openai.chat-completions.v1"],
        }
    )
    selection = prepare_selection(
        release, roots, capabilities={"openai.chat-completions.v1": "profiles.json"}
    )
    docker = shutil.which("docker")
    assert docker
    recipe = directory / "recipe.json"
    recipe.write_bytes(
        _json(
            {
                "format": "buddha.meas02-native-audit.v1",
                "pack": str(PACK),
                "proposal": str(PROPOSAL),
                "provenance": str(PROVENANCE),
                "native": {
                    "selection": selection.to_record(),
                    "roots": {k: str(v) for k, v in roots.items()},
                    "environment": helper.installed_environment(env),
                    "hooks": helper.hooks(),
                    "executor": {
                        "image_id": env["image"].split("@")[-1],
                        "role": "evaluator",
                        "runner_entrypoint": "buddha/native_worker.py",
                        "image_environment": [x.split("=", 1) for x in env["config"]["Env"]],
                        "limits": asdict(Limits(wall_seconds=180, memory_mib=2048)),
                        "docker_endpoint": _endpoint(docker),
                    },
                    "profiles": {"openai": {"test-model": "judge"}},
                    "budget_microusd": budget,
                    "max_calls": max_calls,
                },
            }
        )
    )
    authority = Authorization.create(
        directory / "authorization.sqlite3",
        authorization_id="synthetic-" + directory.name,
        budget_microusd=budget if shared_budget is None else shared_budget,
        max_calls=max_calls,
        scope="offline MEAS02 engineering proof only; not live permission",
    )
    review = {
        "checked_on": datetime.now(UTC).date().isoformat(),
        "credential_sha256": {"openai": sha(KEY.encode())},
        "account_scope": "synthetic offline account only",
    }
    return recipe, authority, review, spec


class Server:
    def __init__(self, targets):
        self.sends = []
        self.mode = "valid"
        self.targets = targets
        self.failures = []
        self.observed = []
        self.requests = []
        self.current = None
        self.operator_launches = []

    def observe(self, frame, index):
        request = frame["request"]
        raw = base64.b64decode(request["body_base64"], validate=True)
        record = json.loads(raw)
        digest = scientific_hash(record)
        matches = [
            target
            for target in self.targets
            if target["occasion"] == OCCASIONS[index] and target["rendered_call_sha256"] == digest
        ]
        assert len(matches) == 1, "each frozen batch must identify one exact rendered input"
        self.current = matches[0]
        self.requests.append(
            {
                "batch": index,
                "target_id": self.current["target_id"],
                "logical_id": request["logical_id"],
                "attempt": request["attempt"],
                "body_sha256": sha(raw),
            }
        )

    def failed(self, error):
        self.failures.append(
            {
                "type": type(error).__name__,
                "frames": [
                    {"file": Path(frame.filename).name, "line": frame.lineno, "source": frame.line}
                    for frame in traceback.extract_tb(error.__traceback__)
                ],
            }
        )

    def connect(self, host, **options):
        try:
            return Connection(self, host, **options)
        except Exception as error:
            self.failed(error)
            raise


class Connection:
    def __init__(self, server, host, **options):
        assert host == "api.openai.com" and options == {"timeout": 2}
        self.server = server

    def request(self, method, path, *, body, headers):
        try:
            return self._request(method, path, body=body, headers=headers)
        except Exception as error:
            self.server.failed(error)
            raise

    def _request(self, method, path, *, body, headers):
        self.server.observed.append({"method": method, "path": path, "body": json.loads(body)})
        assert method == "POST" and path == "/v1/chat/completions"
        assert headers["Authorization"] == "Bearer " + KEY
        self.body = json.loads(body)
        assert self.body["model"] == "test-model"
        assert self.body["response_format"]["json_schema"]["name"] == "Partition"
        self.index = len(self.server.sends)
        self.target = self.server.current
        assert self.target is not None
        rendered = scientific_hash(self.body)
        assert rendered == self.target["rendered_call_sha256"]
        self.server.sends.append(
            {
                "target_id": self.target["target_id"],
                "body_sha256": sha(body),
                "body": self.body,
                "rendered_call_sha256": rendered,
            }
        )

    def getresponse(self):
        return self

    status = 200

    def read(self, maximum):
        n = self.target["answer_count"]
        assert n in {2, 4, 10}
        # Mechanical shown-index parity, never an independent semantic label.
        groups = [list(range(0, n, 2)), list(range(1, n, 2))]
        value = {
            "id": "cmpl-meas02-synthetic-" + str(self.index),
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "service_tier": "default",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"groups": groups}),
                        "refusal": None,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
        if self.server.mode == "unknown":
            value.pop("usage")
        raw = _json(value)
        assert len(raw) < maximum
        return raw

    def getheaders(self):
        return [
            ("content-type", "application/json"),
            ("x-request-id", "synthetic-" + str(self.index)),
        ]

    def close(self):
        pass


def scientific_hash(body):
    schema = dict(body["response_format"]["json_schema"]["schema"])
    assert schema.pop("additionalProperties") is False
    messages = body["messages"]
    assert len(messages) == 2
    assert [row["role"] for row in messages] == ["system", "user"]
    return sha(
        _json(
            {
                "system": messages[0]["content"],
                "user": messages[1]["content"],
                "schema": schema,
            }
        )
    )


class InterruptAfterReceipt(RawHTTPTransport):
    def __init__(self):
        super().__init__(allow_paid=True, timeout_seconds=2)
        self.interrupted = False

    def send_prepared(self, prepared):
        envelope = super().send_prepared(prepared)
        if not self.interrupted:
            self.interrupted = True
            raise ReceivedReply(envelope, KeyboardInterrupt())
        return envelope


def invoke(controller, directory, server, *, keyless=False, transport=None):
    operator = controller.__operator__
    actual_loader = operator._controller

    def observed_controller():
        # Each operator launch still invokes its actual source-pinned loader.
        actual = actual_loader()

        class ObservedSession(actual.NativeSession):
            def handle(self, frame):
                if frame.get("type") == "request":
                    server.observe(frame, self.command["index"])
                    try:
                        return super().handle(frame)
                    finally:
                        server.current = None
                return super().handle(frame)

        actual.NativeSession = ObservedSession
        return actual

    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}),
        patch(
            "http.client.HTTPSConnection",
            side_effect=(
                AssertionError("keyless completed replay must not prepare HTTPS")
                if keyless
                else server.connect
            ),
        ),
        patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")),
        patch.object(operator, "_controller", side_effect=observed_controller),
        patch("buddha.__main__.sys.stdin.isatty", return_value=True),
        patch("buddha.__main__.sys.stderr.isatty", return_value=True),
        patch("buddha.__main__.getpass.getpass", return_value=KEY) as hidden,
    ):
        try:
            return operator.execute(
                directory,
                live=not keyless,
                prompt_keys=not keyless,
                transport=transport or RawHTTPTransport(allow_paid=not keyless, timeout_seconds=2),
                heartbeat_seconds=1.0,
            )
        finally:
            assert os.environ["OPENAI_API_KEY"] == ""
            assert hidden.call_count == (0 if keyless else 1)
            server.operator_launches.append(
                {
                    "keyless": keyless,
                    "hidden_key_entries": hidden.call_count,
                    "temporary_environment_restored": True,
                }
            )


def native_rows(directory):
    result = []
    for index in range(4):
        seal = json.loads((directory / "completed" / (str(index) + ".json")).read_bytes())
        attempt = directory / seal["attempt"]
        result.extend(
            json.loads(line)
            for line in (attempt / "artifacts/v1.1/partitions.jsonl").read_bytes().splitlines()
        )
    return result


def parity_partition(target):
    result = [None] * target["answer_count"]
    for shown, original in enumerate(target["official_display_order"]):
        result[original] = shown % 2
    labels = {}
    return [labels.setdefault(value, len(labels)) for value in result]


def operation_summary(directory):
    return [
        {
            key: row[key]
            for key in (
                "operation_id",
                "request_sha256",
                "reserve_microusd",
                "status",
                "actual_microusd",
                "provider_request_id",
            )
        }
        | {"response_sha256": sha(row["response_json"].encode()) if row["response_json"] else None}
        for row in operations(directory)
    ]


def block_other_owner(directory, *, suffix):
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}),
        patch("http.client.HTTPSConnection", side_effect=AssertionError("funding stop sent HTTPS")),
        patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")),
    ):
        gateway = Gateway(directory / "owners/1", transport=RawHTTPTransport(allow_paid=False))
        report = NativeSession(
            gateway,
            descriptor=directory / "command-1.json",
            output=directory / "attempts" / ("blocked-" + suffix),
        ).run()
    assert report["status"] == "stopped" and report["worker"]["reason"] == "authority"
    assert report["execution"]["cleanup_status"] == "removed"
    assert operations(directory / "owners/1") == []
    return report


def main(target):
    if target.exists() or not target.parent.is_dir():
        raise ValueError("output must be a new file in an existing directory")
    protected = preservation()
    helper = load_engineering(HELPER, HELPER_SHA)
    controller_path = ROOT / "docs/conformance/meas02-native-audit.py"
    materializer_path = ROOT / "docs/conformance/meas02-materialize.py"
    materializer = load_engineering(
        materializer_path, "361ec95b56802eb018681113f012d0f4efaec48d587e556bc6df9993aae26c7d"
    )
    operator = load_engineering(OPERATOR)
    controller = operator._controller()
    controller.__consumed_source_sha256__ = operator.CONTROLLER_SHA256
    controller.__operator__ = operator
    sources = {
        path.relative_to(ROOT).as_posix(): sha(path.read_bytes())
        for path in (
            SCRIPT,
            OPERATOR,
            controller_path,
            materializer_path,
            HELPER,
            ENVIRONMENT,
            HEADER_EVIDENCE,
        )
    }
    assert (
        controller.__consumed_source_sha256__
        == sources[controller_path.relative_to(ROOT).as_posix()]
    )
    assert operator.__consumed_source_sha256__ == sources[OPERATOR.relative_to(ROOT).as_posix()]
    batches = materializer.materialize(PACK.read_bytes(), PROPOSAL.read_bytes())
    targets = [row for batch in batches for row in batch["targets"]]
    assert len(targets) == len({row["target_id"] for row in targets}) == 40
    assert [batch["occasion"] for batch in batches] == list(OCCASIONS)
    fixture = ROOT / "runs/reviews" / ("meas02-native-fixture-" + uuid.uuid4().hex)
    fixture.mkdir()
    print(json.dumps({"fixture": str(fixture), "status": "preparing"}), flush=True)
    recipe, authority, review, spec = setup(fixture / "ordinary", helper)
    directory = controller.prepare_native_audit(
        fixture / "ordinary/study", descriptor=recipe, authorization=authority, review=review
    )
    manifests = {
        index: (directory / "owners" / str(index) / "manifest.json").read_bytes()
        for index in range(4)
    }
    assert len(authority.summary()["runs"]) == 4 and authority.summary()["operation_count"] == 0
    native_inputs = {}
    for index, batch in enumerate(batches):
        staging = directory / "inputs" / str(index)
        assert inventory(staging) == {"generations.jsonl": sha(batch["native_bytes"])}
        assert (staging / "generations.jsonl").read_bytes() == batch["native_bytes"]
        native_inputs.update(
            {row["id"]: row for row in map(json.loads, batch["native_bytes"].splitlines())}
        )
    server = Server(targets)
    interrupted = False
    try:
        invoke(controller, directory, server, transport=InterruptAfterReceipt())
    except KeyboardInterrupt:
        interrupted = True
    if not interrupted or len(server.sends) != 1:
        save(
            fixture / "synthetic-failure.json",
            {
                "errors": server.failures,
                "observed": server.observed,
                "ordinary_owner0": operation_summary(directory / "owners/0"),
            },
        )
        raise AssertionError(
            "synthetic server did not deliver expected interrupt; evidence retained"
        )
    before_resume = operations(directory / "owners/0")
    assert len(before_resume) == 1 and before_resume[0]["status"] == "completed"
    assert authority.summary()["spent_microusd"] == spec.cost_microusd(1, 2)
    print(json.dumps({"status": "resuming", "known_receipts": 1}), flush=True)
    result = invoke(controller, directory, server)
    assert result["status"] == "complete" and result["target_count"] == 40
    assert len(server.sends) == 40
    assert operations(directory / "owners/0")[0] == before_resume[0]
    assert all(
        (directory / "owners" / str(index) / "manifest.json").read_bytes() == raw
        for index, raw in manifests.items()
    )
    counts = [len(operations(directory / "owners" / str(index))) for index in range(4)]
    assert counts == [22, 6, 6, 6]
    totals = authority.summary()
    assert totals["spent_microusd"] == 40 * spec.cost_microusd(1, 2)
    assert totals["reserved_microusd"] == 0 and totals["operation_count"] == 40
    assert all(not row["active"] for row in totals["runs"])
    rows = native_rows(directory)
    expected = {row["target_id"]: row for row in targets}
    assert len(rows) == 40 and {row["id"] for row in rows} == set(expected)
    for row in rows:
        assert row["partition"] == parity_partition(expected[row["id"]])
        assert row["prompt"] == native_inputs[row["id"]]["prompt"]
        assert row["generations"] == native_inputs[row["id"]]["generations"]
    assert Counter(len(row["generations"]) for row in rows) == {2: 14, 4: 2, 10: 24}
    bodies = {row["target_id"]: row["body_sha256"] for row in server.sends}
    baseline = {row["item_id"]: row for row in targets if row["occasion"] == "baseline"}
    repeats = [row for row in targets if row["occasion"] == "same-order-repeat"]
    assert len(repeats) == 6
    for row in repeats:
        original = baseline[row["item_id"]]
        assert row["target_id"] != original["target_id"]
        assert bodies[row["target_id"]] == bodies[original["target_id"]]
    all_operations = [
        row for index in range(4) for row in operations(directory / "owners" / str(index))
    ]
    assert len({row["operation_id"] for row in all_operations}) == 40
    saved_authority = authority.path.read_bytes()
    saved_ledgers = [
        (directory / "owners" / str(i) / "operations.sqlite3").read_bytes() for i in range(4)
    ]
    reused = invoke(controller, directory, server, keyless=True)
    assert reused == result and len(server.sends) == 40
    assert authority.path.read_bytes() == saved_authority
    assert saved_ledgers == [
        (directory / "owners" / str(i) / "operations.sqlite3").read_bytes() for i in range(4)
    ]
    controls = []
    for name, options in (
        (
            "shared-budget",
            {"shared_budget": spec.reserve_microusd() + spec.cost_microusd(1, 2) - 1},
        ),
        ("unknown", {}),
    ):
        recipe, control_authority, review, _ = setup(fixture / name, helper, **options)
        control = controller.prepare_native_audit(
            fixture / name / "study",
            descriptor=recipe,
            authorization=control_authority,
            review=review,
        )
        control_server = Server(targets)
        if name == "unknown":
            control_server.mode = "unknown"
        stopped = invoke(controller, control, control_server)
        assert stopped["status"] == "incomplete" and stopped["stopped_batch"] == 0
        assert len(control_server.sends) == 1
        control_totals = control_authority.summary()
        assert control_totals["operation_count"] == 1
        assert control_totals["reserved_microusd"] == (
            spec.reserve_microusd() if name == "unknown" else 0
        )
        blocked = block_other_owner(control, suffix=name)
        assert control_authority.summary() == control_totals
        controls.append(
            {
                "name": name,
                "report": stopped,
                "other_owner_block": blocked,
                "authorization": control_totals,
            }
        )
    assert preservation() == protected
    assert sources == {name: sha((ROOT / name).read_bytes()) for name in sources}
    evidence = {
        "format": "buddha.meas02-operator-native-proof.v1",
        "source_sha256": sources,
        "fixture": fixture.relative_to(ROOT).as_posix(),
        "actual_provider_calls": 0,
        "actual_keys_used": False,
        "host_official_execution": False,
        "selected_function_paid_shortcut": False,
        "target_count": 40,
        "mocked_physical_sends": 42,
        "ordinary_owner_operation_counts": counts,
        "same_owner_received_reply_interruption": "completed/charged once then resumed exact owner",
        "keyless_completed_reuse_new_sends": 0,
        "six_fresh_repeat_HTTP_bodies_equal": True,
        "all40_proposal_scientific_render_hashes_equal": True,
        "mixed_native_answer_counts": {"2": 14, "4": 2, "10": 24},
        "display_mapping": "mechanical shown-parity groups folded to exact original-order labels",
        "report": result,
        "authorization": totals,
        "requests": server.sends,
        "native_request_frames": server.requests,
        "operator_launches": server.operator_launches,
        "operations": [operation_summary(directory / "owners" / str(i)) for i in range(4)],
        "controls": controls,
        "protected_file_count": len(protected),
        "protected_historical_inputs": 287,
        "protected_source_files": 36,
        "all_prior_seals_unchanged": True,
        "limits": [
            "Synthetic responses measure no judge accuracy, agreement or order stability.",
            "Short controls are study inputs, not C1 generated Answers or population scores.",
            "No score, generation, optimizer, live allocation or provider route is enabled.",
            "Inputs are immutable; dynamic partial-native-cache adoption is not supported.",
        ],
    }
    save(target, evidence)
    print(
        json.dumps(
            {
                "output": str(target),
                "sha256": sha(target.read_bytes()),
                "targets": 40,
                "mocked_sends": 42,
                "actual_provider_calls": 0,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)
