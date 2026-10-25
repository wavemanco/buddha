"""Pinned, keyless observation of an original P/C improver consuming v8/v6 feedback.

Review and pin this driver before execution. The selected actor defaults to C;
only its two counted proposal workers use the real minimal container. Every other
worker and every provider reply is supplied. Original sources are data on the
host; nothing here establishes model context capacity, useful diversity,
authorship or an improvement in performance.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess  # nosec B404
import sys
import time
import traceback
from contextlib import ExitStack
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

SCRIPT = Path(__file__).resolve()
ORIGINAL = Path(r"C:\Users\arvik\code\buddha\runs")
PARENT = ORIGINAL / "src02-current-live-20261024-proposal-v3/components/source-agent/candidate.py"
EVOLVED = ORIGINAL / "src02-current-live-20261024-run-v1/iterations/0/agent/candidate.py"
ENVIRONMENT = ORIGINAL / "src02-current-live-20261024-proposal-v3/components/source-environment"
PARENT_SHA = "77cfa68f6b3c6996fd503e1ce6f7a964eb57abdb8bde98f6761de5f6e298ff4f"
EVOLVED_SHA = "4196cd29ffa76c6959e6f678a8286b1fde5b56e6a34a97dcf68787e1f22b3a43"
RUNTIME_SHA = "a7311f68ab4deb2eed770d0454ddd2877250a86b8a72716abac45b4ff6d43951"
IMAGE = "sha256:757f5ffd3125ae10a83a7fb7eed05afe5e047442e4063d21bf995c03db1d0f04"
ENDPOINT = "npipe:////./pipe/dockerDesktopLinuxEngine"
SAFE_OS = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "COMSPEC",
    "PATHEXT",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PROGRAMW6432",
    "LOCALAPPDATA",
    "APPDATA",
    "USERPROFILE",
)


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()


def read(path, maximum=32 * 1024**2):
    require(path.is_file() and not path.is_symlink(), "input is not an ordinary file")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, "input exceeds its bound")
    return raw


def pairs(items):
    value = dict(items)
    require(len(value) == len(items), "duplicate JSON keys")
    return value


def decode(raw):
    return json.loads(
        raw, object_pairs_hook=pairs, parse_constant=lambda value: require(False, "nonfinite JSON")
    )


def save(path, value):
    with path.open("xb") as stream:
        stream.write(encoded(value) + b"\n")


def trusted_module(path, name):
    specification = importlib.util.spec_from_file_location(name, path)
    require(specification is not None and specification.loader is not None, "no trusted loader")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def preflight(args):
    for path in (args.repo, args.directory, args.out, args.sources):
        require(path.is_absolute() and ".." not in path.parts, "paths must be absolute")
        require(path.resolve() == path, "path alias or link refused")
    require(
        args.repo.is_dir() and args.directory.parent.is_dir() and args.out.parent.is_dir(),
        "existing ordinary parent folders required",
    )
    require(
        SCRIPT == args.repo / "docs/conformance/imp01-comparison-consumer-rehearsal.py",
        "driver does not belong to explicit trusted checkout",
    )
    require(not args.directory.exists() and not args.out.exists(), "outputs must be new")
    require(not args.out.is_relative_to(args.directory), "receipt must be outside fixture")
    protected = (PARENT.parents[2], EVOLVED.parents[3], args.repo)
    require(
        all(
            not args.directory.is_relative_to(path) and not args.out.is_relative_to(path)
            for path in protected
        ),
        "outputs overlap code or original evidence",
    )
    require(sha(read(SCRIPT)) == args.script_sha256, "driver pin differs")
    map_raw = read(args.sources)
    require(sha(map_raw) == args.sources_sha256, "source map pin differs")
    pins = decode(map_raw)
    require(type(pins) is dict and 1 <= len(pins) <= 4096, "invalid source map")
    helper = args.repo / "docs/conformance/src02-current-rehearsal.py"
    required = {SCRIPT, PARENT, EVOLVED, ENVIRONMENT / "runtime.json", helper}
    required.update(args.repo.glob("buddha/*.py"))
    required.update(args.repo.glob("tests/*.py"))
    require({str(path) for path in required} <= pins.keys(), "source map omits executed helpers")
    for name, digest in pins.items():
        require(
            type(name) is str and type(digest) is str and re.fullmatch("[0-9a-f]{64}", digest),
            "invalid source pin",
        )
        path = Path(name)
        require(path.is_absolute() and path.resolve() == path, "source alias refused")
        require(sha(read(path)) == digest, "pinned input differs")
    require(
        sha(read(PARENT)) == PARENT_SHA and sha(read(EVOLVED)) == EVOLVED_SHA,
        "original P/C source differs",
    )
    runtime_raw = read(ENVIRONMENT / "runtime.json")
    require(sha(runtime_raw) == RUNTIME_SHA, "original minimal runtime differs")
    runtime = decode(runtime_raw)
    require(
        runtime["image_id"] == IMAGE and sha(ENDPOINT.encode()) == runtime["endpoint_sha256"],
        "pinned image or local endpoint differs",
    )
    docker = shutil.which("docker")
    require(docker is not None and Path(docker).is_absolute(), "Docker unavailable")
    require(
        sha(read(Path(docker), 128 * 1024**2)) == runtime["docker_sha256"],
        "Docker executable differs from minimal runtime",
    )
    return pins, helper, docker


def main(args):
    actor_role = getattr(args, "actor", "evolved")
    require(actor_role in ("initial", "evolved"), "unsupported original actor")
    actor_arm = ("initial", "evolved").index(actor_role)
    # Enumerate key names only, retaining safe OS values before any app import.
    ordinary = {name: os.environ[name] for name in SAFE_OS if name in os.environ}
    for name in list(os.environ):
        del os.environ[name]
    os.environ.update(ordinary)
    sys.dont_write_bytecode = True
    pins, helper_path, docker = preflight(args)
    helper = trusted_module(helper_path, "_comparison_reviewed_docker_guard")
    runtime = {"passive": False, "active": None}
    evidence = {
        "format": "buddha.improver-comparison-consumer-rehearsal.v2",
        "status": "running",
        "started_utc": datetime.now(UTC).isoformat(),
        "directory": str(args.directory),
        "source_sha256": pins,
        "script_sha256": args.script_sha256,
        "source_map_sha256": args.sources_sha256,
        "original_sources": {str(PARENT): PARENT_SHA, str(EVOLVED): EVOLVED_SHA},
        "actor": {
            "role": actor_role,
            "arm": actor_arm,
            "source_sha256": (PARENT_SHA, EVOLVED_SHA)[actor_arm],
        },
        "runtime_sha256": RUNTIME_SHA,
        "image_id": IMAGE,
        "real_provider_calls": 0,
        "real_keys_read": False,
        "host_selected_execution": False,
        "actual_workers": [],
        "requests": [],
        "docker_commands": [],
        "phase": "guarded_preparation",
        "limitations": [
            "Synthetic benchmark/tasks, outcomes, replies, usage and charges; no model authorship.",
            "Only the selected frozen actor's two counted proposals run in isolated workers; "
            "all other roles supplied.",
            "Bounded consumer compatibility, not provider token fit/output headroom "
            "or full-grid feasibility.",
            "Original C flat index is observed, not rewritten; no effectiveness claim."
            if actor_role == "evolved"
            else "Original P has no derived measurement index; no effectiveness claim.",
            "The selected actor's escaped-feedback guard is observed on the accepting path only; "
            "this is not an oversized-feedback boundary test.",
        ],
    }
    original_popen = subprocess.Popen
    guarded_popen, audited_popen, guarded_control, owned = helper.docker_process_guard(
        docker, ENDPOINT, evidence["docker_commands"], original_popen, runtime, {IMAGE}
    )

    class CapturedPipe:
        def __init__(self, stream, destination, ceiling):
            self.stream, self.destination, self.ceiling = stream, destination, ceiling
            self.count = 0

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def capture(self, raw):
            self.count += len(raw)
            require(self.count <= self.ceiling, "actual pipe capture exceeds configured ceiling")
            self.destination.write(raw)
            self.destination.flush()
            return raw

        def readline(self, size):
            return self.capture(self.stream.readline(size))

        def read1(self, size):
            return self.capture(self.stream.read1(size))

        def close(self):
            try:
                self.stream.close()
            finally:
                self.destination.close()

    def observed_popen(command, *positional, **options):
        process = guarded_popen(command, *positional, **options)
        if list(command[1:5]) == ["--host", ENDPOINT, "start", "-ai"]:
            active = runtime["active"]
            require(active is not None, "unregistered actual pipes")
            for name, operation, ceiling in (
                ("stdout", "readline", active["limits"].max_stdout_bytes),
                ("stderr", "read1", active["limits"].max_stderr_bytes),
            ):
                stream = getattr(process, name)
                require(stream is not None and callable(getattr(stream, operation)), "missing pipe")
                target = args.directory / ("worker-" + str(active["slot"]) + "-" + name + ".bin")
                setattr(process, name, CapturedPipe(stream, target.open("xb"), ceiling))
        return process

    def writable(value, *, unlink=False):
        if isinstance(value, int):
            return False
        path = helper.checked_write_target(value, unlink=unlink)
        return path is not None and (path == args.out or path.is_relative_to(args.directory))

    def sql_path(value):
        if str(value) == ":memory:":
            return True
        text = os.fsdecode(value)
        if text.startswith("file:"):
            parsed = urlsplit(text)
            require(not parsed.netloc and parsed.query in ("mode=ro", "mode=rw"), "SQL URI differs")
            text = url2pathname(unquote(parsed.path))
        return writable(text) and Path(text).is_relative_to(args.directory)

    def audit(event, values):
        if event.startswith(("os.system", "os.posix_spawn", "os.exec", "os.spawn")):
            raise RuntimeError("unregistered host process forbidden")
        if event.startswith("socket.") and event != "socket.gethostname":
            raise RuntimeError("real host network forbidden")
        if event == "subprocess.Popen":
            audited_popen(*values[:2])
        if event == "sqlite3.connect":
            require(sql_path(values[0]), "SQL outside new fixture")
        if event == "compile" and isinstance(values[0], (bytes, str)):
            raw = values[0] if isinstance(values[0], bytes) else values[0].encode()
            require(
                sha(raw) not in (PARENT_SHA, EVOLVED_SHA), "selected-source host compile forbidden"
            )
        if event == "exec":
            name = values[0].co_filename
            if name and not name.startswith("<"):
                path = Path(name).absolute()
                require(
                    not path.is_relative_to(args.directory) and path not in (PARENT, EVOLVED),
                    "selected-source host exec forbidden",
                )
        if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            mode, flags = values[1:3]
            writing = isinstance(mode, str) and any(char in mode for char in "wax+")
            writing |= bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            require(not writing or writable(values[0]), "write outside new fixture/receipt")
        if event == "os.remove":
            require(writable(values[0], unlink=True), "unlink outside new fixture")
        if event in {"os.mkdir", "os.rmdir", "os.chmod", "os.utime"}:
            require(writable(values[0]), "mutation outside new fixture")
        if event in {"os.rename", "os.link", "os.symlink"}:
            require(writable(values[0]) and writable(values[1]), "move/link outside new fixture")

    original_connect = sqlite3.connect

    def guarded_connect(database, *positional, **options):
        require("factory" not in options and sql_path(database), "unapproved SQL/factory")

        class Connection(sqlite3.Connection):
            attaching, deserializing = None, False

            def execute(self, sql, parameters=(), /):
                if sql.strip().upper().startswith("ATTACH"):
                    require(
                        sql.strip().upper() == "ATTACH DATABASE ? AS FUNDING"
                        and type(parameters) in (list, tuple)
                        and len(parameters) == 1
                        and str(parameters[0]) != ":memory:"
                        and sql_path(parameters[0]),
                        "unapproved funding attachment",
                    )
                    self.attaching = parameters[0]
                try:
                    return super().execute(sql, parameters)
                finally:
                    self.attaching = None

            def deserialize(self, data, /, *, name="main"):
                require(database == ":memory:" and name == "main", "deserialize requires memory")
                self.deserializing = True
                try:
                    return super().deserialize(data, name=name)
                finally:
                    self.deserializing = False

        connection = original_connect(database, *positional, factory=Connection, **options)

        def authorizer(action, first, _second, _database, _trigger):
            if action == sqlite3.SQLITE_ATTACH:
                if connection.deserializing or (
                    connection.attaching is not None and first in (None, connection.attaching)
                ):
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorizer)
        return connection

    sys.addaudithook(audit)
    started = time.monotonic()
    try:
        with ExitStack() as stack:
            stack.enter_context(patch("subprocess.Popen", side_effect=observed_popen))
            stack.enter_context(patch("sqlite3.connect", side_effect=guarded_connect))
            sys.path[:0] = [str(args.repo), str(args.repo / "tests")]
            import test_gateway
            import test_improver_study as fixtures

            from buddha import executor, improver_study
            from buddha.gateway import RawHTTPTransport
            from buddha.releases import _json, prepare_selection

            runtime.update(executor=executor, original_control=executor._control)
            stack.enter_context(patch("buddha.executor._control", side_effect=guarded_control))
            require(executor._endpoint(docker) == ENDPOINT, "current local endpoint differs")
            actual_image = decode(
                executor._control(docker, ["--host", ENDPOINT, "image", "inspect", IMAGE])
            )
            require(
                type(actual_image) is list
                and len(actual_image) == 1
                and actual_image[0]["Id"] == IMAGE,
                "pinned minimal image unavailable",
            )
            os.environ["OPENAI_API_KEY"] = test_gateway.KEY
            args.directory.mkdir()
            fixture_root = args.directory / "fixture"

            def retained_temporary():
                require(not fixture_root.exists(), "unexpected additional fixture")
                fixture_root.mkdir()
                return SimpleNamespace(name=str(fixture_root), cleanup=lambda: None)

            f = fixtures.FiniteImproverStudyTests("runTest")
            stack.enter_context(
                patch("tempfile.TemporaryDirectory", side_effect=retained_temporary)
            )
            f.fixture_before_new_api()
            f.api = improver_study
            require(f.engine.candidate.expected_runtime == RUNTIME_SHA, "fixture runtime differs")
            p_raw, c_raw = read(PARENT), read(EVOLVED)
            base = f.base.to_record()
            base_roots = {name: Path(path) for name, path in base["generation"]["roots"].items()}
            actors = []
            for name, role, raw in (
                ("original-P", "initial", p_raw),
                ("original-C", "evolved", c_raw),
            ):
                agent = fixture_root / name
                agent.mkdir()
                (agent / "candidate.py").write_bytes(raw)
                roots = base_roots | {"agent": agent}
                selection = prepare_selection(
                    f.engine.candidate.release, roots, capabilities=f.capabilities
                )
                actors.append(
                    {
                        "name": role,
                        "selection": selection.to_record(),
                        "roots": {key: str(value) for key, value in roots.items()},
                        "entrypoint": "candidate.py",
                    }
                )
            f.fixed = actors
            base["generation"].update(selection=actors[0]["selection"], roots=actors[0]["roots"])
            base["generation"]["executor"]["docker_endpoint"] = ENDPOINT
            base["generation"]["executor"]["mounts"] = [
                ["/agent", actors[0]["roots"]["agent"]],
                ["/runner", actors[0]["roots"]["runner"]],
            ]
            f.base = f.h.screen(base)
            f.starts = [{"name": "common-original-P", "screen": f.base.to_record()}]
            record = f.declaration(improver_study)
            record.update(
                format="buddha.improver-study.v3",
                repetitions=1,
                descendant_opportunities=2,
                feedback_comparison=dict(improver_study.FEEDBACK_COMPARISON_POLICY),
            )
            f.recompute_limits(record)
            directory, declaration, authority = f.prepare_study("consumer-study", record)
            actor = actors[actor_arm]
            actor_raw = (p_raw, c_raw)[actor_arm]
            actor_cell = directory / "cells/0/0" / str(actor_arm)
            child_location = actor_cell / "0"
            allowed_owners = {
                actor_cell / str(slot) / "proposal/owners/0": slot for slot in range(2)
            }
            mock_counted_owners = {
                directory / "cells/0/0" / str(1 - actor_arm) / str(slot) / "proposal/owners/0"
                for slot in range(2)
            }
            mock_proposals = mock_counted_owners | {
                directory / "common/0/0/witness/proposal/owners/0",
                child_location / "witness/proposal/owners/0",
            }
            mock_screens = [directory / "common/0/0/screen", child_location / "screen"]
            mock_generations = {root / "tasks/0/generation/owners/0" for root in mock_screens} | {
                directory / "common/0/0/witness/generation/owners/0",
                child_location / "witness/generation/owners/0",
            }
            mock_native = {
                root / "tasks/0/evaluation/owners" / str(index)
                for root in mock_screens
                for index in (1, 2, 3)
            }
            actual_run, supplied_generation = executor.run_container, f.execute
            active, seen = {}, set()
            evidence["config"] = copy.deepcopy(record["proposal_template"])
            evidence["declaration"] = {"path": str(declaration), "sha256": sha(read(declaration))}
            evidence["fixed_actor_sha256"] = f.actor_id(actor)
            evidence["profile"] = copy.deepcopy(f.engine.fixture.profiles)

            class Connection:
                status = 200

                def __init__(self, host, **options):
                    require(
                        host == "api.openai.com" and options == {"timeout": 30},
                        "unexpected synthetic provider connection",
                    )
                    require(active and len(evidence["requests"]) < 2, "unexpected callback")

                def request(self, method, path, *, body, headers):
                    require(method == "POST" and path == "/v1/chat/completions", "endpoint differs")
                    require(
                        headers.get("Authorization") == "Bearer " + test_gateway.KEY,
                        "only the synthetic key may be used",
                    )
                    require(test_gateway.KEY.encode() not in body, "key in request body")
                    slot = active["slot"]
                    require(slot == len(evidence["requests"]), "duplicate or out-of-order callback")
                    saved = args.directory / ("request-" + str(slot) + ".json")
                    with saved.open("xb") as stream:
                        stream.write(body)
                    payload = decode(body)
                    prompt = payload["messages"][-1]["content"]
                    packet = decode(prompt.split("\nINPUT_JSON\n", 1)[1])
                    fields = {"format", "parent", "development_feedback"}
                    if actor_role == "evolved":
                        fields.add("measurement_index")
                    require(
                        type(packet) is dict
                        and set(packet) == fields
                        and packet["format"] == "buddha.source-seed-improver.v2",
                        "original actor packet fields differ",
                    )
                    expected = active["initial"]
                    require(
                        packet["development_feedback"] == expected["feedback"],
                        "emitted complete feedback differs",
                    )
                    require(packet["parent"] == expected["parent_bundle"], "emitted parent differs")
                    if actor_role == "evolved":
                        require(
                            packet["measurement_index"] == [{"task_id": fixtures.TASK_ID}],
                            "original C flat-index observation differs",
                        )
                        escaped = len(json.dumps(expected["feedback"], ensure_ascii=True).encode())
                    else:
                        escaped = len(
                            json.dumps(
                                expected["feedback"],
                                sort_keys=True,
                                separators=(",", ":"),
                                ensure_ascii=True,
                                allow_nan=False,
                            ).encode("utf-8")
                        )
                    require(escaped <= 1024**2, "fixture exceeds selected actor's feedback ceiling")
                    evidence["requests"].append(
                        {
                            "slot": slot,
                            "owner": str(active["owner"]),
                            "path": str(saved),
                            "sha256": sha(body),
                            "bytes": len(body),
                            "feedback_sha256": sha(_json(expected["feedback"])),
                            "feedback_escaped_bytes": escaped,
                            "feedback_escaped_encoding": "default_separators_ascii"
                            if actor_role == "evolved"
                            else "compact_sorted_ascii",
                            "measurement_index_present": actor_role == "evolved",
                            **(
                                {"measurement_index": packet["measurement_index"]}
                                if actor_role == "evolved"
                                else {}
                            ),
                            "parent_source_sha256": sha(packet["parent"]["source"].encode()),
                            "notes": [
                                {
                                    "task_id": row["task"]["id"],
                                    "sha256": sha(row["note"].encode()),
                                    "bytes": len(row["note"].encode()),
                                }
                                for row in expected["feedback"]
                            ],
                        }
                    )
                    self.text = (
                        _json(
                            {
                                "source": c_raw.decode(),
                                "hypothesis": "Supplied retained C text; no model authorship.",
                            }
                        ).decode()
                        if slot == 0
                        else "{malformed supplied proposal JSON"
                    )

                def getresponse(self):
                    return self

                def read(self, maximum):
                    raw = _json(
                        {
                            "model": "test-model",
                            "service_tier": "default",
                            "choices": [
                                {
                                    "message": {"content": self.text, "refusal": None},
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                        }
                    )
                    require(len(raw) <= maximum, "synthetic reply exceeds raw capture")
                    return raw

                def getheaders(self):
                    return [
                        ("content-type", "application/json"),
                        ("x-request-id", "offline-C-capture"),
                    ]

                def close(self):
                    pass

            def supplied_improvement(spec, initial, handle):
                owner = handle.__self__.gateway.directory
                require(owner in mock_proposals, "unexpected supplied improvement owner")
                detached = initial["format"] == "buddha.candidate-improvement-worker.v3"
                counted = owner in mock_counted_owners
                value = (
                    {}
                    if counted
                    else {
                        "source": fixtures.source(
                            "validity-only-" + initial["agent_sha256"]
                        ).decode(),
                        "hypothesis": "Supplied validity control; never executed on host.",
                    }
                )
                f.engine.workers += 1
                ready = {
                    "type": "ready",
                    "agent_sha256": initial["agent_sha256"],
                    "feedback_sha256": sha(_json(initial["feedback"])),
                    "runtime_sha256": RUNTIME_SHA,
                }
                if detached:
                    ready["parent_agent_sha256"] = initial["parent_bundle"]["agent_sha256"]
                handle(ready)
                handle(
                    {
                        "type": "done",
                        "status": "failed" if counted else "complete",
                        "reason": "invalid_proposal" if counted else "complete",
                        "proposal": {
                            "status": "captured",
                            "value": value,
                            "sha256": sha(_json(value)),
                            "bytes": len(_json(value)),
                        },
                    }
                )
                return f.engine.execution(spec)

            def dispatch(spec, *, initial, handle, **kwargs):
                owner = handle.__self__.gateway.directory
                if owner in allowed_owners:
                    slot = allowed_owners[owner]
                    require(
                        owner not in seen and len(seen) < 2, "extra actual selected actor worker"
                    )
                    require(
                        initial["format"] == "buddha.candidate-improvement-worker.v3"
                        and initial["agent_sha256"] == f.actor_id(actor),
                        "actual worker identity differs",
                    )
                    require(
                        read(dict(spec.mounts)["/agent"] / "candidate.py") == actor_raw,
                        "actual selected actor bytes differ",
                    )
                    require(
                        spec.role == "agent"
                        and spec.image_id == IMAGE
                        and kwargs["docker_endpoint"] == ENDPOINT,
                        "actual executor differs",
                    )
                    require(
                        dict(spec.mounts)
                        == {
                            "/agent": Path(actor["roots"]["agent"]),
                            "/runner": base_roots["runner"],
                        },
                        "actual mounts differ",
                    )
                    note = decode(initial["feedback"][0]["note"])
                    require(
                        initial["parent_bundle"]["source"]
                        == (p_raw if slot == 0 else c_raw).decode(),
                        "actual task-parent literal source differs",
                    )
                    require(
                        [row["task"]["id"] for row in initial["feedback"]] == [fixtures.TASK_ID],
                        "actual feedback task order differs",
                    )
                    kind = (
                        "saved_native_measurements_and_root_comparison"
                        if slot == 0
                        else "saved_native_measurements_and_parent_comparison"
                    )
                    require(note["kind"] == kind, "actual actor receives wrong comparison kind")
                    if slot == 0:
                        require(
                            note["comparison"]["reason"] == "no_counted_parent_in_this_cell",
                            "root scope differs",
                        )
                    else:
                        require(
                            note["comparison"]["utility_delta"] == -3
                            and note["comparison"]["distinct_delta"] == -1,
                            "actual own-edge deltas differ",
                        )
                    for measured in (
                        [note["measurements"]]
                        if slot == 0
                        else [note["measurements"], note["parent_measurements"]]
                    ):
                        require(
                            measured["answers"]
                            == [
                                {"position": 0, "text": fixtures.LITERAL},
                                {"position": 1, "text": ""},
                            ]
                            and measured["omitted_answer_positions"] == 0,
                            "actual note omitted or changed literal outputs",
                        )
                    provenance_path = owner.parents[2] / "feedback/provenance.json"
                    provenance = decode(read(provenance_path))
                    require(
                        provenance["format"]
                        == "buddha.source-screen-feedback.v" + str(8 if slot == 0 else 6)
                        and provenance["improver_agent_sha256"] == f.actor_id(actor),
                        "actual packet version or fixed actor differs",
                    )
                    seen.add(owner)
                    active.update(slot=slot, owner=owner, initial=copy.deepcopy(initial))
                    runtime["active"] = {"spec": spec, "limits": kwargs["limits"], "slot": slot}
                    save(args.directory / ("worker-" + str(slot) + "-initial.json"), initial)
                    try:
                        result = actual_run(spec, initial=initial, handle=handle, **kwargs)
                    finally:
                        runtime["active"] = None
                        active.clear()
                    stdout_path = args.directory / ("worker-" + str(slot) + "-stdout.bin")
                    stderr_path = args.directory / ("worker-" + str(slot) + "-stderr.bin")
                    stdout_raw, stderr_raw = read(stdout_path), read(stderr_path)
                    require(
                        len(stdout_raw) == result.stdout_bytes
                        and len(stderr_raw) == result.stderr_bytes
                        and sha(stderr_raw) == result.stderr_sha256,
                        "actual pipe captures differ from executor accounting",
                    )
                    evidence["actual_workers"].append(
                        {
                            key: value
                            for key, value in asdict(result).items()
                            if key != "_configuration"
                        }
                        | {
                            "configuration": result.configuration,
                            "provenance_sha256": sha(read(provenance_path)),
                            "stdout": {"path": str(stdout_path), "sha256": sha(stdout_raw)},
                            "stderr": {"path": str(stderr_path), "sha256": sha(stderr_raw)},
                        }
                    )
                    require(result.cleanup_status == "removed", "actual worker cleanup incomplete")
                    return result
                if "candidate-improvement-worker" in initial["format"]:
                    return supplied_improvement(spec, initial, handle)
                require(
                    owner in (mock_generations if spec.role == "agent" else mock_native),
                    "unexpected supplied generation/native owner",
                )
                result = supplied_generation(spec, initial=initial, handle=handle, **kwargs)
                if spec.role == "agent":
                    # The supplied child remains original C for either fixed improver.
                    f.h.programs[initial["agent_sha256"]].update(
                        distinct=1 if initial["agent_sha256"] == f.actor_id(actors[1]) else 2,
                        utility=4 if initial["agent_sha256"] == f.actor_id(actors[1]) else 7,
                    )
                return result

            evidence["phase"] = "actual_consumer"
            with (
                patch("buddha.executor.run_container", side_effect=dispatch),
                patch("http.client.HTTPSConnection", side_effect=Connection),
            ):
                report = improver_study.run_improver_study(
                    directory, transport=RawHTTPTransport(allow_paid=True, timeout_seconds=30)
                )
            evidence["study_report"] = report
            require(report["status"] == "complete", "study incomplete; retain original reason")
            require(
                len(seen) == len(evidence["actual_workers"]) == len(evidence["requests"]) == 2,
                "actual population differs from two workers/two supplied callbacks",
            )
            decisions = {(row["arm"], row["slot"]): row["status"] for row in report["decisions"]}
            require(
                decisions
                == {
                    (arm, slot): "admitted" if (arm, slot) == (actor_arm, 0) else "rejected"
                    for arm in range(2)
                    for slot in range(2)
                },
                "decisions differ",
            )
            before = f.h.files(args.directory)
            runtime["passive"] = True
            os.environ.pop("OPENAI_API_KEY")
            with (
                patch("buddha.executor.run_container", side_effect=RuntimeError("passive worker")),
                patch("http.client.HTTPSConnection", side_effect=RuntimeError("passive HTTPS")),
            ):
                repeated = improver_study.run_improver_study(
                    directory, transport=RawHTTPTransport(allow_paid=False)
                )
            require(
                repeated == report and f.h.files(args.directory) == before,
                "keyless replay changed original evidence",
            )
            require(
                all(sha(read(Path(name))) == digest for name, digest in pins.items()),
                "pinned original/trusted inputs changed",
            )
            evidence.update(
                status="complete",
                phase="complete",
                keyless_replay_unchanged=True,
                inputs_unchanged=True,
                owned_container_count=len(owned),
            )
    except BaseException as error:
        evidence.update(
            status="incomplete",
            reason=type(error).__name__,
            error=str(error),
            traceback=traceback.format_exc(),
        )
    evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
    save(args.out, evidence)
    print(
        json.dumps(
            {
                "format": evidence["format"],
                "status": evidence["status"],
                "phase": evidence["phase"],
                "receipt": str(args.out),
            }
        ),
        flush=True,
    )
    return 0 if evidence["status"] == "complete" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor", choices=("initial", "evolved"), default="evolved")
    for name in ("repo", "directory", "out", "sources"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("script-sha256", "sources-sha256"):
        parser.add_argument("--" + name, required=True)
    raise SystemExit(main(parser.parse_args()))
