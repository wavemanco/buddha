"""Review before execution: actual agent Python, request-free simulated native stages.

Requires NEW scratch/receipt paths and caller-approved script/source-map pins.
Supplied sources are data on the host. No model, key, original run or live grant.
"""

import os
import sys

# This dedicated process never restores its inherited environment. Read only
# approved ordinary OS values; enumerate/delete every other NAME before imports.
SAFE_OS = {
    "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "LOCALAPPDATA",
    "APPDATA", "USERPROFILE",
}
ordinary = {name: os.environ[name] for name in SAFE_OS if name in os.environ}
for name in list(os.environ):
    del os.environ[name]
os.environ.update(ordinary)
sys.dont_write_bytecode = True

import argparse
import base64
import copy
import hashlib
import http.client
import json
import re
import shutil
import sqlite3
import stat
import subprocess  # nosec B404
import tempfile
import threading
import time
import traceback
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
IMAGE = "sha256:757f5ffd3125ae10a83a7fb7eed05afe5e047442e4063d21bf995c03db1d0f04"
ENVIRONMENT = ROOT / "docs/conformance/src01-runtime-environment.json"
ENVIRONMENT_SHA = "a7311f68ab4deb2eed770d0454ddd2877250a86b8a72716abac45b4ff6d43951"
ORIGINAL_RUNS = Path(r"C:\Users\arvik\code\buddha\runs").resolve()

GENERATOR = '''def generate(task, config, complete):
    if type(task["id"]) is str and task["id"] == "1":
        return ["hello", "goodbye"]
    if type(task["id"]) is int and task["id"] == 1:
        return ["0", "1"]
    raise ValueError("unexpected fixture task")
'''
CHILD = GENERATOR + "\n# Literal further-child generation control.\n"
MISSING = GENERATOR
RAISING = GENERATOR + '''
def propose_improvement(parent_bundle, development_feedback, config, complete):
    raise RuntimeError("controlled bounded fixture improver failure")
'''
VALID = "import json\n\n" + GENERATOR + '''
def propose_improvement(parent_bundle, development_feedback, config, complete):
    expected = [(str, "1", ["hello", "goodbye"]), (int, 1, ["0", "1"])]
    if type(development_feedback) is not list or len(development_feedback) != 2:
        raise ValueError("complete measured feedback is required")
    for row, (kind, identifier, answers) in zip(development_feedback, expected, strict=True):
        task = row["task"]
        if type(task["id"]) is not kind or task["id"] != identifier or task["count"] != 2:
            raise ValueError("first ordered typed task or count changed")
        note = json.loads(row["note"])
        if note["answers"] != [{"position": i, "text": text} for i, text in enumerate(answers)]:
            raise ValueError("full measured literal outputs were not consumed")
        if note["omitted_answer_positions"] != 0:
            raise ValueError("measured answers were omitted")
    child = CHILD_LITERAL
    if child == parent_bundle["source"]:
        raise ValueError("fixture mutation did not change source")
    return {"source": child, "hypothesis": "Supplied zero-callback further-child witness."}
'''.replace("CHILD_LITERAL", repr(CHILD))
PROGRAMS = {"missing": MISSING, "raising": RAISING, "valid": VALID}
PROTECTED_CODE = {hashlib.sha256(value.encode()).hexdigest() for value in (*PROGRAMS.values(), CHILD)}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def decode(raw):
    def pairs(items):
        result = dict(items)
        require(len(items) == len(result), "duplicate JSON key")
        return result

    def constant(_value):
        raise ValueError("finite JSON required")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def failure_chain(error):
    """Bounded controlled-proof diagnostics; never capture locals/environment."""
    result, seen = [], set()
    while error is not None and id(error) not in seen and len(result) < 8:
        seen.add(id(error))
        text = "".join(traceback.format_exception(type(error), error, error.__traceback__, limit=16, chain=False))
        raw = text.encode("utf-8", errors="replace")
        result.append({"type": type(error).__name__, "traceback": raw[:16384].decode("utf-8", errors="ignore"), "truncated": len(raw) > 16384})
        # Public stage wrappers intentionally suppress display of their context.
        # Retain that bounded underlying diagnostic for this controlled proof.
        error = error.__cause__ if error.__cause__ is not None else error.__context__
    return result


def absolute(path):
    require(isinstance(path, Path) and path.is_absolute() and ".." not in path.parts,
            "absolute nontraversing paths required")
    require(not str(path).startswith(("//", "\\\\")) and path.resolve(strict=False) == path,
            "canonical local paths required")
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
        prefix + number for prefix in ("COM", "LPT") for number in "123456789¹²³"
    }
    for name in path.parts[1:]:
        require(name and name == name.rstrip(" .")
                and not any(c in '<>:"/\\|?*' or ord(c) < 32 for c in name)
                and name.split(".", 1)[0].upper() not in reserved,
                "Windows filename/stream/device alias forbidden")
    for parent in reversed(path.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and not parent.is_symlink()
                and not getattr(info, "st_file_attributes", 0) & 0x400,
                "linked or absent path parent")
    return path


def read(path, maximum=256 * 1024**2):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not path.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & 0x400 and info.st_size <= maximum,
            "bounded ordinary input required")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    after = path.lstat()
    require(len(raw) == info.st_size and len(raw) <= maximum
            and all(getattr(info, key) == getattr(after, key)
                    for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns")),
            "input changed during read")
    return raw


def tree(directory):
    files = {}
    for path in sorted(directory.rglob("*")):
        info = path.lstat()
        require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & 0x400,
                "linked fixture entry")
        if path.is_file():
            raw = read(path)
            files[path.relative_to(directory).as_posix()] = {"sha256": sha(raw), "bytes": len(raw)}
    return files


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--sources-sha256", required=True)
    parser.add_argument("--script-sha256", required=True)
    return parser.parse_args()


def preflight(args):
    for path in (args.directory, args.out, args.sources):
        absolute(path)
        require(path.is_relative_to(ROOT / "runs/reviews"), "proof paths must stay in this checkout's ignored reviews")
    require(args.directory.parent.is_dir() and args.out.parent.is_dir(), "output parents absent")
    require(not args.directory.exists() and not args.directory.is_symlink()
            and not args.out.exists() and not args.out.is_symlink(), "all outputs must be NEW")
    require(not args.out.is_relative_to(args.directory)
            and not args.sources.is_relative_to(args.directory)
            and args.out != args.sources and args.out != SCRIPT, "input/output overlap")
    require(re.fullmatch("[0-9a-f]{64}", args.script_sha256)
            and re.fullmatch("[0-9a-f]{64}", args.sources_sha256), "invalid caller hash")
    require(sha(read(SCRIPT)) == args.script_sha256, "script pin differs")
    raw = read(args.sources, 32 * 1024**2)
    require(sha(raw) == args.sources_sha256, "source-map pin differs")
    pins = decode(raw)
    require(type(pins) is dict and 1 <= len(pins) <= 4096, "bounded source map required")
    allowed_config = {ROOT / name for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt", ".github/workflows/ci.yml")}
    for name, digest in pins.items():
        path = absolute(Path(name))
        require(type(name) is str and str(path) == name and path.is_relative_to(ROOT)
                and (path.suffix == ".py" or path in allowed_config or path == ENVIRONMENT)
                and not path.is_relative_to(args.directory)
                and not args.directory.is_relative_to(path)
                and path not in {args.out, args.sources}, "source-map path outside bounded inputs")
        require(type(digest) is str and re.fullmatch("[0-9a-f]{64}", digest)
                and sha(read(path)) == digest, "source input differs")
    required = {SCRIPT, ENVIRONMENT, *ROOT.joinpath("buddha").glob("*.py"),
                *ROOT.joinpath("tests").glob("*.py")}
    require(all(str(path) in pins for path in required), "source map omits Python/runtime inputs")
    require(pins[str(SCRIPT)] == args.script_sha256
            and pins[str(ENVIRONMENT)] == ENVIRONMENT_SHA, "runtime/script map identity differs")
    return raw, pins


class Guards:
    def __init__(self, args, evidence):
        self.args, self.evidence = args, evidence
        self.phase = "preparation"
        self.active = None
        self.docker = shutil.which("docker")
        require(self.docker is not None, "Docker CLI unavailable")
        require(Path(self.docker).is_absolute() and Path(self.docker).is_file(), "absolute Docker CLI required")
        self.endpoint = None
        self.owned = set()
        self.registration = threading.local()
        self.original_popen = subprocess.Popen
        self.original_connect = sqlite3.connect
        self.executor = self.original_control = None

    def deny(self, reason):
        self.evidence["denied_events"].append(reason)
        raise RuntimeError(reason)

    def writable(self, value):
        if isinstance(value, int):
            return self.phase != "passive"
        path = Path(os.fsdecode(value)).absolute()
        return path == self.args.out or (self.phase != "passive" and path.is_relative_to(self.args.directory))

    def database(self, value):
        if value == ":memory:":
            return True
        if self.phase == "passive":
            return False
        try:
            path = Path.from_uri(value.split("?", 1)[0]) if value.startswith("file:") else Path(value)
            return path.is_absolute() and ".." not in path.parts and path.resolve().is_relative_to(self.args.directory)
        except (TypeError, ValueError, OSError):
            return False

    def audit(self, event, values):
        if event.startswith("socket.") and event != "socket.gethostname":
            self.deny("host_socket")
        if event.startswith(("os.system", "os.posix_spawn", "os.exec", "os.spawn")):
            self.deny("unregistered_process")
        if event == "subprocess.Popen":
            registration = getattr(self.registration, "value", None)
            if not registration or values[0] != self.docker or not (
                type(values[1]) is str and values[1] == registration[1]
                or type(values[1]) in (list, tuple) and tuple(values[1]) == registration[0]
            ):
                self.deny("process_audit_registration")
        if event == "sqlite3.connect" and not self.database(str(values[0])):
            self.deny("outside_or_active_passive_sql")
        if event == "compile" and isinstance(values[0], (bytes, str)):
            raw = values[0].encode() if isinstance(values[0], str) else values[0]
            if sha(raw) in PROTECTED_CODE:
                self.deny("host_candidate_compile")
        if event == "exec":
            name = values[0].co_filename
            if name and not name.startswith("<") and Path(name).absolute().is_relative_to(self.args.directory):
                self.deny("host_fixture_python_exec")
        if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(values[0])).absolute()
            if path.is_relative_to(ORIGINAL_RUNS) and not path.is_relative_to(ROOT) and not path.is_relative_to(self.args.directory):
                self.deny("original_run_read")
            if path.is_relative_to(ROOT / "runs") and not path.is_relative_to(self.args.directory) and path not in {SCRIPT, self.args.sources, self.args.out}:
                self.deny("unapproved_local_run_read")
            mode, flags = values[1], values[2]
            writing = isinstance(mode, str) and any(char in mode for char in "wax+")
            writing |= bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not self.writable(path):
                self.deny("outside_write")
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime"} and not self.writable(values[0]):
            self.deny("outside_mutation")
        if event in {"os.rename", "os.link", "os.symlink"} and not all(self.writable(x) for x in values[:2]):
            self.deny("outside_move_or_link")

    def permitted(self, argv):
        if self.phase == "passive":
            return False
        if argv == ["context", "show"]:
            return self.endpoint is None
        if len(argv) == 5 and argv[:4] == ["context", "inspect", "--format", "{{json .Endpoints.docker}}"]:
            return self.endpoint is None and re.fullmatch("[A-Za-z0-9_.-]{1,128}", argv[4])
        if not self.endpoint or argv[:2] != ["--host", self.endpoint]:
            return False
        tail = argv[2:]
        if tail == ["image", "inspect", IMAGE] or tail == ["inspect", "--format", "{{json .}}", IMAGE]:
            return True
        if not self.active:
            return False
        if tail[:1] == ["create"]:
            try:
                name, label = tail[tail.index("--name") + 1], tail[tail.index("--label") + 1]
            except (ValueError, IndexError):
                return False
            match = re.fullmatch("buddha-([0-9a-f]{32})", name)
            if not match or label != self.executor.OWNER_LABEL + "=" + match.group(1):
                return False
            expected = self.executor._create_args(self.active["spec"], self.active["limits"], name, match.group(1))
            if tail != expected:
                return False
            self.active.update(name=name, owner=match.group(1))
            return True
        if len(tail) == 4 and tail[:3] == ["inspect", "--format", "{{json .}}"]:
            return tail[3] in self.owned
        if len(tail) == 3 and tail[:2] in (["start", "-ai"], ["rm", "-f"]):
            return tail[2] in self.owned
        if len(tail) == 2 and tail[0] == "kill":
            return tail[1] in self.owned
        if self.active.get("name") and tail == ["container", "ls", "-a", "--no-trunc", "--format", "{{.ID}}", "--filter", "name=^/" + self.active["name"] + "$", "--filter", "label=" + self.executor.OWNER_LABEL + "=" + self.active["owner"]]:
            return True
        return len(tail) == 8 and tail[:7] == ["container", "ls", "-a", "--no-trunc", "--format", "{{.ID}}", "--filter"] and tail[7].startswith("id=") and tail[7][3:] in self.owned

    def popen(self, command, *positional, **options):
        require(not positional and "executable" not in options and options.get("shell", False) is False,
                "shell/executable override forbidden")
        require(type(command) in (list, tuple) and len(command) >= 2 and all(type(x) is str for x in command)
                and command[0] == self.docker and self.permitted(list(command[1:])),
                "Docker command outside exact local owned lifecycle")
        require(getattr(self.registration, "value", None) is None, "nested process registration")
        self.registration.value = (tuple(command), subprocess.list2cmdline(command))
        self.evidence["docker_commands"].append({"argv_sha256": sha(encode(list(command))), "verb": command[3] if command[1:2] == ["--host"] else "context"})
        try:
            return self.original_popen(command, executable=self.docker, **options)
        finally:
            self.registration.value = None

    def control(self, docker, argv):
        require(docker == self.docker, "different Docker executable")
        raw = self.original_control(docker, argv)
        if argv[:3] == ["--host", self.endpoint, "create"]:
            identity = raw.strip().decode("ascii")
            require(re.fullmatch("[0-9a-f]{64}", identity), "created identity unavailable")
            self.owned.add(identity)
        elif self.active and argv[2:9] == ["container", "ls", "-a", "--no-trunc", "--format", "{{.ID}}", "--filter"] and len(argv) == 12:
            # The permitted command includes this active UUID name AND owner
            # label. Recover only that exact create after a lost acknowledgement.
            identities = raw.split()
            require(len(identities) <= 1 and all(re.fullmatch(b"[0-9a-f]{64}", value) for value in identities), "ambiguous owned recovery")
            self.owned.update(value.decode("ascii") for value in identities)
        return raw

    def connect(self, database, *args, **kwargs):
        require("factory" not in kwargs and self.database(str(database)), "unapproved SQL target/factory")
        guard = self

        class Connection(sqlite3.Connection):
            attaching = None
            deserializing = False

            def execute(self, sql, parameters=(), /):
                if sql.strip().upper().startswith("ATTACH"):
                    require(sql.strip().upper() == "ATTACH DATABASE ? AS FUNDING", "unrecognized SQL attachment")
                    require(type(parameters) in (tuple, list) and len(parameters) == 1
                            and type(parameters[0]) is str and guard.database(parameters[0])
                            and parameters[0] != ":memory:", "unapproved funding attachment")
                    self.attaching = parameters[0]
                try:
                    return super().execute(sql, parameters)
                finally:
                    self.attaching = None

            def deserialize(self, data, /, *, name="main"):
                require(str(database) == ":memory:" and name == "main", "deserialize requires main memory")
                self.deserializing = True
                try:
                    return super().deserialize(data, name=name)
                finally:
                    self.deserializing = False

        connection = self.original_connect(database, *args, factory=Connection, **kwargs)

        def authorizer(action, first, _second, _db, _trigger):
            if action == sqlite3.SQLITE_ATTACH:
                # deserialize has its own internal ATTACH argument (e.g. "x").
                # The scope exists only around main on an explicit memory DB.
                if connection.deserializing:
                    return sqlite3.SQLITE_OK
                if connection.attaching is not None and (first is None or first == connection.attaching):
                    return sqlite3.SQLITE_OK
                guard.evidence["denied_events"].append("sqlite_unapproved_attach")
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorizer)
        return connection


def main(args):
    map_raw, pins = preflight(args)
    evidence = {"format": "buddha.actual-mutation-witness-proof.v1", "status": "running",
                "started_utc": datetime.now(UTC).isoformat(), "fixture": str(args.directory),
                "script_sha256": args.script_sha256, "source_map_sha256": sha(map_raw),
                "source_sha256": pins, "denied_events": [], "docker_commands": [],
                "real_workers": [], "simulated_native": [], "cases": [],
                "limitations": ["Supplied literal Python, not model authorship or improved performance.",
                               "Native stages are request-free simulated records, not official commands or semantic judgments.",
                               "Existing isolation is reused; no fresh broad sandbox audit or model-context claim.",
                               "Passive repeats call the data-only inspector; completed-run active lock behavior is outside this proof."]}
    guard = Guards(args, evidence)
    sys.addaudithook(guard.audit)
    start = time.monotonic()
    try:
        args.directory.mkdir()
        temporary_root = args.directory / "scratch"
        temporary_root.mkdir()
        os.environ["TEMP"] = os.environ["TMP"] = str(temporary_root)
        tempfile.tempdir = str(temporary_root)
        sys.pycache_prefix = str(args.directory / "absent-host-bytecode-cache")
        require(not Path(sys.pycache_prefix).exists(), "host bytecode cache path must be absent")

        class RetainedTemporaryDirectory:
            def __init__(self, suffix=None, prefix=None, dir=None, **_kwargs):
                self.name = tempfile.mkdtemp(suffix=suffix or "", prefix=prefix or "case-", dir=dir or temporary_root)

            def cleanup(self):
                pass  # Retain every original proof input/outcome, including failures.

            def __enter__(self):
                return self.name

            def __exit__(self, *_args):
                return False

        sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
        with patch("subprocess.Popen", side_effect=guard.popen), patch("sqlite3.connect", side_effect=guard.connect), patch("tempfile.TemporaryDirectory", RetainedTemporaryDirectory):
            import test_source_screen_outcome as fixture_module
            from buddha import credentials, executor, gateway, provider, source_screen, source_search
            from buddha.releases import Release, _json, inventory, prepare_selection

            guard.executor, guard.original_control = executor, executor._control
            actual_run = executor.run_container

            def forbidden(*_args, **_kwargs):
                guard.deny("key_or_model_or_http_attempt")

            def inputs():
                require(sha(read(args.sources)) == args.sources_sha256, "source map changed")
                require(all(sha(read(Path(path))) == digest for path, digest in pins.items()), "approved inputs changed")

            with patch.object(executor, "_control", side_effect=guard.control), patch.object(gateway, "_credential", side_effect=forbidden), patch.object(gateway.RawHTTPTransport, "send_prepared", side_effect=forbidden), patch.object(provider.HTTPTransport, "_credential", side_effect=forbidden), patch.object(credentials, "key_environment", side_effect=forbidden), patch("http.client.HTTPSConnection", side_effect=forbidden):
                guard.endpoint = executor._endpoint(guard.docker)
                image = decode(executor._control(guard.docker, ["--host", guard.endpoint, "image", "inspect", IMAGE]))
                require(type(image) is list and len(image) == 1 and image[0]["Id"] == IMAGE, "exact local agent image unavailable")
                evidence.update(image=IMAGE, runtime_sha256=ENVIRONMENT_SHA, local_endpoint_sha256=sha(guard.endpoint.encode()))
                for label, program in PROGRAMS.items():
                    guard.phase = label
                    inputs()
                    f = fixture_module.SourceScreenOutcomeTests("runTest")
                    h = f.fixture()
                    record = copy.deepcopy(h.record)
                    roots = h.engine.fixture.roots
                    (roots["agent"] / "candidate.py").write_bytes(program.encode())
                    record["format"] = "buddha.source-screen.v2"
                    generation = record["generation"]
                    generation["selection"] = prepare_selection(Release.from_record(generation["selection"]["release"]), roots, capabilities=generation["selection"]["capabilities"]).to_record()
                    generation["max_callbacks"] = 0
                    generation["executor"]["docker_endpoint"] = guard.endpoint
                    record["native"]["executor"]["docker_endpoint"] = guard.endpoint
                    screen = source_screen.SourceScreen.from_bytes(_json(record))
                    require(screen.tasks.tasks[0].id == "1" and type(screen.tasks.tasks[0].id) is str
                            and [task.count for task in screen.tasks.tasks] == [2, 2], "ordered typed fixture task changed")
                    authority = h.authority(screen)
                    search = h.root / "actual-search"
                    case = {"label": label, "search": str(search), "authorization": str(authority.path),
                            "candidate_id": screen.candidate_id, "source_sha256": sha(program.encode()), "task_ids": [task.id for task in screen.tasks.tasks]}
                    evidence["cases"].append(case)
                    template = {key: generation[key] for key in ("config", "profile", "max_callbacks", "budget_microusd", "max_calls")}
                    spec = source_search.SourceSearchSpec.from_bytes(_json({"format": "buddha.source-search.v1", "iterations": 1, "method": "latest", "seed": 17, "max_active": 4}))
                    source_search.prepare_source_search(search, seed_screen=screen, proposal_template=template, spec=spec, authorization=authority, review=h.engine.fixture.review, expected_runtime_sha256=ENVIRONMENT_SHA, mutation_witness=True)
                    seen = set()

                    def simulated_native(specification, initial, handle):
                        session = handle.__self__
                        index = initial["command"]["index"]
                        inputs_root = dict(specification.mounts)["/inputs"]
                        require(inventory(inputs_root) == {item["source"]: item["sha256"] for item in initial["inputs"]}, "simulated native input differs")
                        audit = {module: {"kind": "official", "path": "/official/" + module.replace(".", "/") + ".py", "sha256": initial["inventories"]["official"][module.replace(".", "/") + ".py"]} for module in initial["hooks"]["modules"]}
                        handle({"type": "ready", "aliases": [], "audit": audit})
                        if index < 2:
                            rows = [json.loads(raw) for raw in read(inputs_root / initial["inputs"][0]["source"]).splitlines()]
                            for row in rows:
                                row["partition"], row["distinct"] = [0, 1], 2
                                if index == 1:
                                    row["generation_scores"], row["partition_scores"], row["utility"] = [7, 7], [7, 7], 7
                            outputs = {"partitions.jsonl" if index == 0 else "scores.jsonl": b"".join(_json(row) + b"\n" for row in rows)}
                        else:
                            outputs = {"summary.json": h.engine.summary}
                        for name, body in outputs.items():
                            for offset in range(0, len(body) or 1, 64 * 1024):
                                part = body[offset:offset + 64 * 1024]
                                handle({"type": "file", "path": name, "offset": offset, "eof": offset + len(part) == len(body), "data_base64": base64.b64encode(part).decode()})
                        handle({"type": "done", "status": "complete", "reason": "complete", "audit": audit})
                        evidence["simulated_native"].append({"owner": str(session.gateway.directory), "index": index, "output_sha256": {name: sha(body) for name, body in outputs.items()}, "request_frames": 0})
                        return h.engine.execution(specification)

                    def route(specification, **kwargs):
                        session = kwargs["handle"].__self__
                        owner = session.gateway.directory
                        require(owner.is_relative_to(search) and owner not in seen, "unexpected/repeated original proof worker")
                        seen.add(owner)
                        if specification.role != "agent":
                            require(specification.role == "evaluator", "unexpected worker role")
                            return simulated_native(specification, kwargs["initial"], kwargs["handle"])
                        inputs()
                        require(len(evidence["real_workers"]) < 14 and specification.image_id == IMAGE, "unexpected actual-agent schedule/image")
                        require(kwargs["initial"]["max_callbacks"] == 0 and {target for target, _ in specification.mounts} == {"/agent", "/runner"}, "actual source callback/mount controls changed")
                        require(all(value not in _json(kwargs["initial"]) for value in (b"VALIDATION-ONLY-SENTINEL", b"FINAL-ONLY-SENTINEL", b"dataset_base64")), "unselected host data crossed actual worker channel")
                        raw_source = read(dict(specification.mounts)["/agent"] / "candidate.py")
                        require(sha(raw_source) in PROTECTED_CODE, "unexpected supplied/further source")
                        real_event = {"owner": str(owner), "case": label, "session": str(session.output), "source_sha256": sha(raw_source), "initial": kwargs["initial"], "initial_sha256": sha(_json(kwargs["initial"])), "frames": []}
                        evidence["real_workers"].append(real_event)
                        original_handle = kwargs["handle"]

                        def frame(value):
                            require(value.get("type") != "request", "actual zero-callback source requested a model")
                            real_event["frames"].append({"type": value.get("type"), "sha256": sha(_json(value))})
                            return original_handle(value)

                        kwargs["handle"] = frame
                        guard.active = {"spec": specification, "limits": kwargs["limits"]}
                        try:
                            result = actual_run(specification, **kwargs)
                            require(result.image_id == IMAGE and result.exit_code == 0 and result.cleanup_status == "removed", "actual agent process/cleanup failed")
                            require(result.container_id in guard.owned, "actual container identity not observed at creation")
                            real_event["execution"] = {key: value for key, value in asdict(result).items() if key != "_configuration"}
                            real_event["configuration"] = result.configuration
                            remaining = executor._control(guard.docker, ["--host", guard.endpoint, "container", "ls", "-a", "--no-trunc", "--format", "{{.ID}}", "--filter", "id=" + result.container_id]).strip()
                            require(not remaining, "owned actual container remains")
                            return result
                        finally:
                            guard.active = None

                    with patch.object(executor, "run_container", side_effect=route):
                        result = source_search.run_source_search(search, transport=gateway.RawHTTPTransport(allow_paid=False))
                    require(result["status"] == "complete", "actual proof search incomplete")
                    statuses = [row["status"] for row in result["witnesses"]]
                    if label in {"missing", "raising"}:
                        require(result["reason"] == "no_parent_eligible" and statuses == ["failed"] and result["witnesses"][0]["reason"] == "agent_error" and not result["decisions"], "failed actual improver was admitted")
                    else:
                        require(statuses == ["passed", "failed"] and result["decisions"][0]["status"] == "mutation_witness_failed", "valid actual witness/fresh child admission differs")
                        child_id = sha(_json({"candidate.py": sha(CHILD.encode())}))
                        require(result["decisions"][0]["child_id"] == child_id and result["selection"]["selected_id"] == screen.candidate_id, "witness child was silently adopted")
                        proposal = json.loads(read(search / "seed-witness/proposal/report.json"))
                        require(read(Path(proposal["child"]["directory"]) / "candidate.py") == CHILD.encode(), "actual returned child bytes differ")
                    summary = authority.summary()
                    require(all(summary[name] == 0 for name in ("operation_count", "spent_microusd", "reserved_microusd", "committed_microusd")) and not any(row["active"] for row in summary["runs"]), "proof has model operations/liabilities/active owners")
                    case.update(result=result, authorization_summary=summary)
                    reports = {}
                    for event in evidence["real_workers"]:
                        if event["case"] == label:
                            path = Path(event["session"]) / "report.json"
                            raw = read(path)
                            reports[str(path)] = {"sha256": sha(raw), "report": decode(raw)}
                    case["real_session_reports"] = reports
                    before = tree(h.root)
                    guard.phase = "passive"
                    for _ in range(2):
                        inspected = source_search.inspect_source_search(search, authorization=authority.path, expected_report_sha256=sha(read(search / "report.json")))
                        require(inspected == result, "passive actual-witness replay differs")
                    after = tree(h.root)
                    require(before == after, "passive replay changed canonical fixture bytes")
                    case.update(files_before_passive=before, files_after_passive=after, passive_repeats=2)
                    guard.phase = label
                    inputs()
                require(len(evidence["real_workers"]) == 14 and len(evidence["simulated_native"]) == 24, "observed finite proof schedule differs")
                require(not evidence["denied_events"], "proof encountered a guard denial")
                evidence.update(status="complete", real_provider_calls=0, observed_model_operations=0,
                                source_pins_unchanged=True, observed_real_workers=len(evidence["real_workers"]),
                                observed_simulated_native_workers=len(evidence["simulated_native"]))
    except BaseException as error:
        evidence.update(status="failed", phase=guard.phase, error_type=type(error).__name__, failure_chain=failure_chain(error))
    finally:
        guard.phase = "passive"
        evidence.update(finished_utc=datetime.now(UTC).isoformat(), elapsed_seconds=time.monotonic() - start)
        with args.out.open("xb") as stream:
            stream.write(encode(evidence) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    print(json.dumps({key: evidence[key] for key in ("format", "status", "elapsed_seconds")}))
    return 0 if evidence["status"] == "complete" else 1


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("ordinary Python with assertions enabled is required")
    try:
        raise SystemExit(main(arguments()))
    except (ValueError, OSError, RuntimeError):
        print('{"format":"buddha.actual-mutation-witness-proof.v1","status":"preflight_stopped"}')
        raise SystemExit(2) from None
