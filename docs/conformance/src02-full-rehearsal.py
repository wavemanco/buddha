"""One concrete source experiment, actual confinement and synthetic HTTPS only.

Review this program and freeze its source map before running in NEW paths.
The exact unallocated v3 proposal stays read-only. A synthetic grant exercises
the real launcher/controller; no user authorization, real key or provider call
is involved. Supplied descendants and canned judgments are engineering inputs.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat

# Every Popen requires exact registered Docker argv before the real process call.
import subprocess  # nosec B404
import sys
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

if not __debug__:
    raise RuntimeError("This proof requires ordinary Python with assertions enabled")

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
PROPOSAL_SHA256 = "58201cb25ae027a24549f4153fcdf2bb82cdca8783c93cc687034cd5629bffa9"
SEED_SHA256 = "d7ba10ac6d4786cf22d7447242fa9188830f40ba5a5bf9d30c26681f7377491e"
TASK_IDS = ["curated-0", "curated-47", "curated-97"]
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
KEYS = {
    provider: "offline-full-source-rehearsal-not-a-real-" + provider + "-key"
    for provider in ("openai", "anthropic")
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    require(type(value) is str and re.fullmatch("[0-9a-f]{64}", value), "invalid raw hash")
    return value


def absolute(path):
    require(
        isinstance(path, Path)
        and path.is_absolute()
        and ".." not in path.parts
        and not str(path).startswith(("//", "\\\\")),
        "plain absolute paths required",
    )
    require(path.resolve(strict=False) == path, "canonical long paths required")
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
        prefix + number for prefix in ("COM", "LPT") for number in "123456789¹²³"
    }
    for name in path.parts[1:]:
        require(
            name
            and name == name.rstrip(" .")
            and not any(char in '<>:"/\\|?*' or ord(char) < 32 for char in name)
            and name.split(".", 1)[0].rstrip(" .").upper() not in reserved,
            "path component has a Windows stream, device or filename alias",
        )
    for ancestor in reversed(path.parents):
        info = ancestor.lstat()
        require(
            stat.S_ISDIR(info.st_mode)
            and not ancestor.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & 0x400,
            "path parent is not a plain directory",
        )
    return path


def read(path, maximum=256 * 1024**2):
    info = path.lstat()
    require(
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and not path.is_symlink()
        and not getattr(info, "st_file_attributes", 0) & 0x400
        and info.st_size <= maximum,
        "input is not a bounded plain regular file",
    )
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    after = path.lstat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    require(
        len(raw) <= maximum
        and len(raw) == info.st_size
        and all(getattr(info, name) == getattr(after, name) for name in fields),
        "input changed while reading",
    )
    return raw


def pairs(items):
    value = dict(items)
    require(len(value) == len(items), "duplicate proof JSON key")
    return value


def decode(raw):
    def nonfinite(_value):
        raise ValueError("proof JSON must be finite")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def docker_process_guard(docker, endpoint, events, original):
    """Register validated argv while Popen emits its platform-specific audit event."""
    active = []

    def guarded(command, *positional, **options):
        require(
            not positional
            and "executable" not in options
            and ("shell" not in options or options["shell"] is False),
            "process shell or executable override forbidden",
        )
        require(
            type(command) in (list, tuple)
            and len(command) >= 2
            and all(type(value) is str for value in command)
            and command[0] == docker,
            "original process argv must name the exact Docker executable",
        )
        argv = list(command[1:])
        permitted = argv[:2] == ["context", "show"] or argv[:2] == ["context", "inspect"]
        permitted |= (
            len(argv) >= 3
            and argv[:2] == ["--host", endpoint]
            and argv[2] in {"create", "inspect", "start", "kill", "rm", "container", "image"}
        )
        require(permitted, "Docker command outside reviewed local runtime")
        registration = (tuple(command), subprocess.list2cmdline(command))
        active.append(registration)
        try:
            # Windows otherwise audits executable=None. Pinning argv[0] as the
            # explicit executable preserves the validated command on both OSes.
            return original(command, executable=docker, **options)
        finally:
            active.remove(registration)

    def audited(executable, command):
        require(
            type(executable) is str and executable == docker,
            "unregistered process executable forbidden",
        )
        match = next(
            (
                argv
                for argv, serialized in active
                if (
                    type(command) is str
                    and command == serialized
                    or type(command) in (list, tuple)
                    and tuple(command) == argv
                )
            ),
            None,
        )
        require(match is not None, "process audit has no exact active argv registration")
        argv = match[1:]
        events.append(
            {
                "sha256": sha(encoded(match)),
                "verb": argv[2] if argv[:2] == ("--host", endpoint) else "context",
            }
        )

    return guarded, audited


def save(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


GENERATION_CALLBACKS = (10, 11, 11, 12)


def programs(parent_raw):
    if type(parent_raw) is not bytes:
        raise ValueError("the exact composed starter bytes are required")
    parent = parent_raw.decode("utf-8")
    marker = "# buddha.source-seed-improver.v1: appended to the unchanged frozen seed."
    if parent.count(marker) != 1 or parent.count("def generate(") != 1:
        raise ValueError("the composed starter layout differs")
    start, end = parent.index("def generate("), parent.index(marker)
    if start >= end:
        raise ValueError("the composed starter layout differs")

    def changed(body):
        return (parent[:start] + body + "\n\n" + parent[end:]).encode("utf-8")

    alternating = changed("""def generate(task, config, complete):
    item, selected = _task(task), _config(config)
    drafts = []
    for _ in range(item["count"] + 1):
        drafts.append(normalize(selected["provider"], complete(
            selected["provider"], request(selected, item, drafts))))
    return (drafts[::2] + drafts[1::2])[:item["count"]]
""")
    one_plan = changed("""def generate(task, config, complete):
    item, selected = _task(task), _config(config)
    planning = dict(item, prompt=(
        "Plan contrasting central content for this task: " + item["prompt"]))
    plan = normalize(selected["provider"], complete(
        selected["provider"], request(selected, planning)))
    drafting = dict(item, prompt=item["prompt"] + "\\nPrivate planning input: " + plan)
    answers = []
    for _ in range(item["count"]):
        answers.append(normalize(selected["provider"], complete(
            selected["provider"], request(selected, drafting, answers))))
    return answers
""")
    two_plans = changed("""def generate(task, config, complete):
    item, selected = _task(task), _config(config)
    planning = dict(item, prompt=(
        "Plan contrasting central content for this task: " + item["prompt"]))
    first = normalize(selected["provider"], complete(
        selected["provider"], request(selected, planning)))
    revision = dict(item, prompt=(
        "Revise the plan to preserve every literal task constraint and strengthen "
        "contrasts in causes, actions and outcomes. Original task: " + item["prompt"]
        + "\\nFirst plan: " + first))
    second = normalize(selected["provider"], complete(
        selected["provider"], request(selected, revision)))
    drafting = dict(item, prompt=item["prompt"] + "\\nPrivate planning input: " + second)
    answers = []
    for _ in range(item["count"]):
        answers.append(normalize(selected["provider"], complete(
            selected["provider"], request(selected, drafting, answers))))
    return answers
""")
    result = (parent_raw, alternating, one_plan, two_plans)
    fragment = parent[end:].encode("utf-8")
    if len(set(result)) != 4 or any(not value.endswith(fragment) for value in result):
        raise ValueError("supplied controls lost distinct source or inherited improver")
    return result


def proposal_payload(body):
    """Check the concrete recipe envelope; callers additionally compare exact parent/feedback."""
    if type(body) is not bytes:
        raise ValueError("proposal request body must be bytes")
    record = json.loads(body)
    if type(record) is not dict or set(record) != {
        "model",
        "messages",
        "max_completion_tokens",
        "reasoning_effort",
        "service_tier",
    }:
        raise ValueError("proposal request envelope differs")
    if (
        record["model"] != "gpt-6.1-sol"
        or type(record["max_completion_tokens"]) is not int
        or record["max_completion_tokens"] != 32768
        or record["reasoning_effort"] != "low"
        or record["service_tier"] != "default"
    ):
        raise ValueError("proposal configuration differs")
    messages = record["messages"]
    if type(messages) is not list or len(messages) != 1:
        raise ValueError("proposal messages differ")
    message = messages[0]
    if type(message) is not dict or set(message) != {"role", "content"}:
        raise ValueError("proposal message differs")
    prompt = message["content"]
    marker = "\n\nINPUT_JSON\n"
    if message["role"] != "user" or type(prompt) is not str or prompt.count(marker) != 1:
        raise ValueError("proposal task prompt differs")
    contract, payload = prompt.split(marker, 1)
    if not contract.startswith(
        "Return only a JSON object with exactly source and hypothesis string fields.\n"
    ) or not contract.endswith("Return no prose outside the JSON."):
        raise ValueError("proposal instruction envelope differs")
    packet = json.loads(payload)
    if (
        type(packet) is not dict
        or set(packet) != {"format", "parent", "development_feedback"}
        or packet["format"] != "buddha.source-seed-improver.v1"
    ):
        raise ValueError("proposal packet differs")
    parent = packet["parent"]
    if type(parent) is not dict or set(parent) != {"entrypoint", "source", "agent_sha256"}:
        raise ValueError("proposal parent projection differs")
    identity = parent["agent_sha256"]
    if (
        parent["entrypoint"] != "candidate.py"
        or type(parent["source"]) is not str
        or type(identity) is not str
        or len(identity) != 64
        or any(char not in "0123456789abcdef" for char in identity)
    ):
        raise ValueError("proposal parent fields differ")
    feedback = packet["development_feedback"]
    if type(feedback) is not list or len(feedback) != 3:
        raise ValueError("proposal must contain the exact three-task development projection")
    for row, identifier in zip(feedback, ("curated-0", "curated-47", "curated-97"), strict=True):
        if type(row) is not dict or set(row) != {"task", "note"}:
            raise ValueError("proposal feedback projection differs")
        task, note = row["task"], row["note"]
        if (
            type(task) is not dict
            or set(task) != {"id", "prompt", "count"}
            or task["id"] != identifier
            or type(task["count"]) is not int
            or task["count"] != 10
            or type(task["prompt"]) is not str
            or not task["prompt"].strip()
            or type(note) is not str
            or not note.strip()
            or len(note.encode("utf-8")) > 4096
        ):
            raise ValueError("proposal task or note projection differs")
    return packet


def tree(root):
    files, directories = {}, []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        require(
            not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & 0x400,
            "fixture tree has a linked entry",
        )
        name = path.relative_to(root).as_posix()
        if stat.S_ISDIR(info.st_mode):
            directories.append(name)
        else:
            raw = read(path, 512 * 1024**2)
            files[name] = {"bytes": len(raw), "sha256": sha(raw)}
    return {"directories": directories, "files": files}


def storage(root):
    sizes = [path.stat().st_size for path in root.rglob("*") if path.is_file()]
    return {
        "file_count": len(sizes),
        "total_bytes": sum(sizes),
        "largest_file_bytes": max(sizes, default=0),
    }


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--sources-sha256", required=True)
    parser.add_argument("--script-sha256", required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    return parser.parse_args()


def preflight(args):
    for path in (args.directory, args.out, args.sources, args.proposal):
        absolute(path)
    receipts = {
        name: args.out.with_name(args.out.stem + "-" + name + ".json")
        for name in ("prefix", "continuation", "keyless")
    }
    outputs = [args.directory, args.out, *receipts.values()]
    require(
        len(set(outputs)) == 5 and all(not p.exists() and not p.is_symlink() for p in outputs),
        "every fixture and receipt path must be NEW",
    )
    require(
        not any(p.is_relative_to(args.directory) for p in outputs[1:]),
        "receipts must be outside the fixture",
    )
    for path in (args.out, *receipts.values()):
        require(path.parent.is_dir(), "receipt parent is absent")
    require(args.directory.parent.is_dir(), "fixture parent is absent")
    digest(args.sources_sha256)
    digest(args.script_sha256)
    require(args.proposal_sha256 == PROPOSAL_SHA256, "this is not the frozen v3 proposal")
    require(sha(read(SCRIPT)) == args.script_sha256, "caller script pin differs")
    map_raw = read(args.sources, 32 * 1024**2)
    require(sha(map_raw) == args.sources_sha256, "caller source map pin differs")
    pins = decode(map_raw)
    require(type(pins) is dict and 1 <= len(pins) <= 4096, "source map must be a bounded path map")
    for name, expected in pins.items():
        require(type(name) is str, "source map path must be text")
        path = absolute(Path(name))
        require(str(path) == name and path != args.sources, "source map alias or self-reference")
        require(
            not any(path.is_relative_to(out) or out.is_relative_to(path) for out in outputs),
            "proof output overlaps a pinned input",
        )
        require(sha(read(path)) == digest(expected), "reviewed source input differs")
    proposal_raw = read(args.proposal, 32 * 1024**2)
    require(sha(proposal_raw) == PROPOSAL_SHA256, "raw v3 proposal differs")
    proposal = decode(proposal_raw)
    required = {SCRIPT, args.proposal, *ROOT.joinpath("buddha").glob("*.py")}
    required.update(Path(name) for name in proposal["source_sha256"])
    required.update(path for path in args.proposal.parent.rglob("*") if path.is_file())
    require(all(str(path) in pins for path in required), "source map omits required current inputs")
    require(pins[str(SCRIPT)] == args.script_sha256, "map does not pin this script")
    require(
        not args.directory.is_relative_to(args.proposal.parent)
        and not args.out.is_relative_to(args.proposal.parent),
        "outputs overlap the proposal",
    )
    return map_raw, pins, proposal, receipts


def main(args):
    map_raw, pins, proposal, receipts = preflight(args)
    started = time.monotonic()
    search, authority_path = (
        args.directory / "search",
        args.directory / "synthetic-authorization.sqlite3",
    )
    review_path = args.directory / "synthetic-key-review.json"
    launch_path, approval_path = (
        args.directory / "synthetic-launch.json",
        args.directory / "synthetic-approval.json",
    )
    screen_record = proposal["seed_screen"]
    generation, native = screen_record["generation"], screen_record["native"]
    require(
        screen_record["selected_ids"] == TASK_IDS
        and proposal["spec"]
        == {
            "format": "buddha.source-search.v1",
            "iterations": 3,
            "max_active": 4,
            "method": "latest",
            "seed": 7,
        },
        "concrete task or search schedule differs",
    )
    require(
        generation["config"]["sampling"] == "in-context"
        and generation["config"]["model"] == "gpt-5.6-luna"
        and generation["max_callbacks"] == generation["max_calls"] == 12
        and proposal["proposal_template"]["max_callbacks"] == 3
        and proposal["requested_terms"] == {"budget_microusd": 25_000_000, "max_calls": 512},
        "concrete quota or synthetic grant schedule differs",
    )
    source_path = Path(generation["roots"]["agent"]) / "candidate.py"
    parent_raw = read(source_path)
    require(sha(parent_raw) == SEED_SHA256, "actual composed starter differs")
    supplied = programs(parent_raw)
    fragment = read(args.proposal.parent / "inputs/improver-fragment.txt")
    require(all(value.endswith(fragment) for value in supplied), "inherited fragment differs")
    contract = fragment.decode().split('_SOURCE_SEED_PROMPT = """', 1)[1].split('"""', 1)[0]
    agent_ids = [sha(encoded({"candidate.py": sha(value)})) for value in supplied]
    owner_paths = {
        root / "tasks" / str(task) / role / "owners" / str(index)
        for root in [
            search / "seed",
            *(search / "iterations" / str(i) / "screen" for i in range(3)),
        ]
        for task in range(3)
        for role, indices in (("generation", [0]), ("evaluation", [1, 2, 3]))
        for index in indices
    } | {search / "iterations" / str(i) / "proposal/owners/0" for i in range(3)}
    databases = [authority_path, *(path / "operations.sqlite3" for path in owner_paths)]
    allowed_sql = {
        ":memory:",
        *(
            value
            for path in databases
            for value in (str(path), path.as_uri() + "?mode=rw", path.as_uri() + "?mode=ro")
        ),
    }
    require(
        len(owner_paths) == 51 and len(databases) == 52, "original synthetic owner plan differs"
    )
    docker = shutil.which("docker")
    require(docker is not None and Path(docker).is_absolute(), "Docker CLI unavailable")
    endpoint = generation["executor"]["docker_endpoint"]
    require(endpoint == native["executor"]["docker_endpoint"], "source/native endpoints differ")
    protected_code = {sha(raw) for raw in supplied} | {
        sha(read(path)) for path in Path(native["roots"]["official"]).rglob("*.py")
    }
    permitted_outputs = {args.out, *receipts.values()}
    evidence = {
        "format": "buddha.src02-concrete-full-rehearsal.v1",
        "status": "running",
        "fixture": str(args.directory),
        "script_sha256": args.script_sha256,
        "source_map_sha256": sha(map_raw),
        "source_sha256": pins,
        "proposal": {"path": str(args.proposal), "sha256": PROPOSAL_SHA256},
        "started_utc": datetime.now(UTC).isoformat(),
        "task_ids": TASK_IDS,
        "candidate_source_bytes": [len(value) for value in supplied],
        "candidate_source_sha256": [sha(value) for value in supplied],
        "candidate_ids": agent_ids,
        "callbacks_per_generation_task": GENERATION_CALLBACKS,
        "real_provider_calls": 0,
        "actual_provider_keys_used": False,
        "host_candidate_execution": False,
        "host_official_execution": False,
        "workers": [],
        "sends": [],
        "notices": [],
        "key_entries": [],
        "phases": [],
        "docker_commands": [],
        "limitations": [
            "Supplied descendants and synthetic provider text/usage; "
            "no model authorship or live pricing evidence.",
            "Canned singleton groups and quality scores, including closed-answer tasks, "
            "are not semantic judgments.",
            "Actual byte/storage/timing observations do not establish "
            "vendor token-context fit or live latency.",
            "Fixed known-source chain; no universal mutation-competence, "
            "edited-improver efficacy or improvement claim.",
            "Host and local Docker daemon are trusted; "
            "original records and user funding are not used.",
            "Fake keys are already in this dedicated process; "
            "the key-entry observer checks ordering, not interactive paste behavior.",
        ],
    }
    phase = "preparation"
    guarded_popen, audited_popen = docker_process_guard(
        docker, endpoint, evidence["docker_commands"], subprocess.Popen
    )

    def inputs():
        require(sha(read(args.sources, 32 * 1024**2)) == args.sources_sha256, "source map changed")
        require(
            all(sha(read(Path(path))) == expected for path, expected in pins.items()),
            "pinned current or historical input changed",
        )

    def writable(value):
        if isinstance(value, int):
            return phase != "completed-keyless-repeat"
        path = Path(os.fsdecode(value)).absolute()
        return path in permitted_outputs or (
            phase != "completed-keyless-repeat" and path.is_relative_to(args.directory)
        )

    def audit(event, values):
        # platform.machine() reads local hostname metadata on a cold interpreter.
        if event.startswith("socket.") and event != "socket.gethostname":
            raise RuntimeError("real host network operation forbidden")
        if event == "sqlite3.connect":
            value = str(values[0]) if isinstance(values[0], Path) else values[0]
            require(
                type(value) is str
                and value in allowed_sql
                and (phase != "completed-keyless-repeat" or value == ":memory:"),
                "SQL outside original synthetic plan or completed passive mode",
            )
        if event == "subprocess.Popen":
            audited_popen(*values[:2])
        if event == "compile" and isinstance(values[0], (bytes, str)):
            raw = values[0] if isinstance(values[0], bytes) else values[0].encode()
            require(sha(raw) not in protected_code, "candidate or official compilation on host")
        if event == "exec":
            name = values[0].co_filename
            if name and not name.startswith("<"):
                path = Path(name).absolute()
                require(
                    not path.is_relative_to(args.directory)
                    and not path.is_relative_to(args.proposal.parent),
                    "candidate or official execution on host",
                )
        if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            mode, flags = values[1], values[2]
            writing = isinstance(mode, str) and any(char in mode for char in "wax+")
            writing |= bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            require(not writing or writable(values[0]), "write outside new synthetic outputs")
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime"}:
            require(writable(values[0]), "mutation outside synthetic outputs")
        if event in {"os.rename", "os.link", "os.symlink"}:
            require(
                writable(values[0]) and writable(values[1]), "move/link outside synthetic outputs"
            )

    ordinary = {name: os.environ[name] for name in SAFE_OS if name in os.environ}
    fake_environment = ordinary | {name.upper() + "_API_KEY": value for name, value in KEYS.items()}
    # This dedicated process exits after the proof. Enumerate names only: even
    # patch.dict's restoration copy must never read an original credential.
    for name in list(os.environ):
        del os.environ[name]
    os.environ.update(fake_environment)
    sys.dont_write_bytecode = True
    sys.addaudithook(audit)
    try:
        with (
            patch.dict(os.environ, fake_environment, clear=True),
            patch("subprocess.Popen", side_effect=guarded_popen),
        ):
            sys.path.insert(0, str(ROOT))
            from buddha import (
                executor,
                native_pipeline,
                source_handoff,
                source_launch,
                source_screen,
                source_search,
            )
            from buddha.answers import Answers
            from buddha.authorization import Authorization
            from buddha.gateway import RawHTTPTransport, _read_manifest
            from buddha.gateway_history import read_gateway_history
            from buddha.provider import ModelSpec
            from buddha.releases import _json

            require(
                all(str(path) in pins for path in source_launch._sources()),
                "source map omits an installed launch helper",
            )
            require(executor._endpoint(docker) == endpoint, "local Docker endpoint differs")
            for image in {generation["executor"]["image_id"], native["executor"]["image_id"]}:
                actual = decode(
                    executor._control(docker, ["--host", endpoint, "image", "inspect", image])
                )
                require(
                    type(actual) is list and len(actual) == 1 and actual[0]["Id"] == image,
                    "exact sealed image unavailable",
                )
            checked_proposal = source_handoff.check_source_handoff(
                args.proposal, expected_sha256=PROPOSAL_SHA256
            )
            require(
                checked_proposal["planned"]["maximum_stage_owners"] == 51,
                "actual configuration owner schedule differs",
            )
            screen = source_screen.SourceScreen.from_bytes(_json(screen_record))
            tasks = [task.to_record() for task in screen.tasks.tasks]
            require(
                [task["id"] for task in tasks] == TASK_IDS
                and all(task["count"] == 10 for task in tasks),
                "selected full tasks differ",
            )
            require(
                source_launch._planned_owners(search, screen, 3) == owner_paths,
                "launcher derives a different owner schedule",
            )
            inputs()
            args.directory.mkdir()
            authority = Authorization.create(
                authority_path,
                authorization_id="synthetic-full-source-" + sha(str(args.directory).encode())[:24],
                scope=checked_proposal["funding"]["scope"],
                **proposal["requested_terms"],
            )
            terms = authority.summary()
            approval = {
                "format": "buddha.source-approval.v1",
                "proposal_sha256": PROPOSAL_SHA256,
                "comparison_key": screen.comparison_key(),
                "directory": str(search),
                "review": str(review_path),
                "authorization": {
                    "path": str(authority_path),
                    "id": terms["authorization_id"],
                    "terms_sha256": terms["terms_sha256"],
                    "scope": terms["scope"],
                },
                **proposal["requested_terms"],
                "account_scope": "Synthetic offline standard/default public PAYG; "
                "not a real account approval",
            }
            save(approval_path, approval)
            launch = {
                "format": "buddha.source-launch.v1",
                "proposal": {"path": str(args.proposal), "sha256": PROPOSAL_SHA256},
                "approval": {"path": str(approval_path), "sha256": sha(read(approval_path))},
                "directory": str(search),
                "review": str(review_path),
                "timeout_seconds": 300,
                "source_sha256": {str(path): pins[str(path)] for path in source_launch._sources()}
                | {str(SCRIPT): args.script_sha256, str(args.sources): args.sources_sha256},
            }
            save(launch_path, launch)
            launch_sha = sha(read(launch_path))
            first_check = source_launch.check_launch(launch_path, expected_sha256=launch_sha)
            require(
                first_check["state"] == "fresh" and first_check["stop_code"] is None,
                "synthetic launch did not pass unchanged preparation",
            )
            evidence["launch"] = {
                "path": str(launch_path),
                "sha256": launch_sha,
                "initial_invocation_control_count": first_check["initial_invocation_control_count"],
            }
            evidence["original_authorization_id"] = terms["authorization_id"]
            active, seen = {}, set()

            def literal(program, task, ordinal):
                return (
                    f"Supplied rehearsal text: program={program}; "
                    f"task={TASK_IDS[task]}; callback={ordinal}."
                )

            def expected_generation(program, task, ordinal):
                item = tasks[task]
                prompt, first_answer = item["prompt"], 0
                if program in {2, 3}:
                    if ordinal == 0:
                        prompt = "Plan contrasting central content for this task: " + prompt
                    elif program == 3 and ordinal == 1:
                        prompt = (
                            "Revise the plan to preserve every literal task constraint "
                            "and strengthen contrasts in causes, actions and outcomes. "
                            "Original task: "
                            + prompt
                            + "\nFirst plan: "
                            + literal(program, task, 0)
                        )
                    else:
                        prompt += "\nPrivate planning input: " + literal(
                            program, task, 0 if program == 2 else 1
                        )
                        first_answer = 1 if program == 2 else 2
                history = (
                    []
                    if program >= 2 and ordinal < (1 if program == 2 else 2)
                    else [literal(program, task, index) for index in range(first_answer, ordinal)]
                )
                messages = [
                    {"role": "system", "content": generation["config"]["instructions"]},
                    {"role": "user", "content": prompt},
                ]
                for previous in history:
                    messages += [
                        {"role": "assistant", "content": previous},
                        {"role": "user", "content": "Can you generate a different answer?"},
                    ]
                return {
                    "model": "gpt-5.6-luna",
                    "messages": messages,
                    "max_completion_tokens": 4096,
                    "reasoning_effort": "low",
                    "service_tier": "default",
                }

            class Connection:
                status = 200

                def __init__(self, host, **options):
                    require(options == {"timeout": 300}, "physical timeout differs")
                    require(
                        host in {"api.openai.com", "api.anthropic.com"}, "provider host differs"
                    )
                    self.provider = "openai" if host == "api.openai.com" else "anthropic"

                def request(self, method, path, *, body, headers):
                    require(
                        len(evidence["sends"]) < 267 and active, "extra physical send attempted"
                    )
                    require(
                        method == "POST"
                        and path
                        == (
                            "/v1/chat/completions" if self.provider == "openai" else "/v1/messages"
                        ),
                        "provider endpoint differs",
                    )
                    require(
                        headers.get("Authorization") == "Bearer " + KEYS[self.provider]
                        if self.provider == "openai"
                        else headers.get("x-api-key") == KEYS[self.provider],
                        "synthetic credential differs",
                    )
                    require(
                        all(key.encode() not in body for key in KEYS.values()), "credential in body"
                    )
                    request = decode(body)
                    self.model, ordinal = request["model"], active["calls"]
                    require(ordinal < active["expected_calls"], "extra callback for original owner")
                    active["calls"] += 1
                    stage = active["stage"]
                    if stage == "generation":
                        require(
                            self.provider == "openai"
                            and request
                            == expected_generation(active["program"], active["task"], ordinal),
                            "generation procedure/history differs",
                        )
                        self.text = literal(active["program"], active["task"], ordinal)
                    elif stage == "proposal":
                        require(self.provider == "openai", "proposal provider differs")
                        packet = proposal_payload(body)
                        require(
                            request["messages"][0]["content"].split("\n\nINPUT_JSON\n", 1)[0]
                            == contract,
                            "literal inherited proposal instruction differs",
                        )
                        require(
                            packet["parent"]
                            == {
                                "entrypoint": "candidate.py",
                                "source": supplied[active["program"]].decode(),
                                "agent_sha256": agent_ids[active["program"]],
                            }
                            and packet["development_feedback"] == active["feedback"],
                            "literal parent or measured feedback projection differs",
                        )
                        self.text = _json(
                            {
                                "source": supplied[active["program"] + 1].decode(),
                                "hypothesis": (
                                    "Supplied offline procedure control "
                                    + str(active["program"] + 1)
                                    + "; no observed improvement claim."
                                ),
                            }
                        ).decode()
                    elif stage == "partition":
                        require(
                            self.provider == "openai"
                            and self.model == "gpt-5.6-luna"
                            and request["response_format"]["json_schema"]["name"] == "Partition"
                            and "max_tokens" not in request
                            and "max_completion_tokens" not in request,
                            "official partition request differs",
                        )
                        self.text = _json({"groups": [[index] for index in range(10)]}).decode()
                    else:
                        require(
                            stage == "score"
                            and self.provider == "anthropic"
                            and self.model == "claude-opus-5"
                            and request["max_tokens"] == 16000
                            and request["thinking"] == {"type": "adaptive"}
                            and request["output_config"]["effort"] == "high"
                            and request["output_config"]["format"]["type"] == "json_schema",
                            "official quality request differs",
                        )
                        self.text = '{"score":7}'
                    self.index = len(evidence["sends"])
                    evidence["sends"].append(
                        {
                            "index": self.index,
                            "stage": stage,
                            "owner": str(active["owner"]),
                            "ordinal": ordinal,
                            "model": self.model,
                            "provider": self.provider,
                            "body_sha256": sha(body),
                            "body_bytes": len(body),
                            "payload_sha256": sha(self.text.encode()),
                            "payload_bytes": len(self.text.encode()),
                        }
                    )

                def getresponse(self):
                    return self

                def read(self, maximum):
                    if self.provider == "openai":
                        record = {
                            "id": "synthetic-full-source-" + str(self.index),
                            "object": "chat.completion",
                            "created": 0,
                            "model": self.model,
                            "service_tier": "default",
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": self.text,
                                        "refusal": None,
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 5,
                                "completion_tokens": 3,
                                "total_tokens": 8,
                            },
                        }
                    else:
                        record = {
                            "id": "msg-synthetic-full-source-" + str(self.index),
                            "type": "message",
                            "role": "assistant",
                            "model": self.model,
                            "content": [{"type": "text", "text": self.text}],
                            "stop_reason": "end_turn",
                            "stop_sequence": None,
                            "usage": {"input_tokens": 5, "output_tokens": 3},
                        }
                    raw = _json(record)
                    require(len(raw) <= maximum, "synthetic response exceeds original capture")
                    evidence["sends"][self.index].update(
                        reply_sha256=sha(raw), reply_bytes=len(raw)
                    )
                    return raw

                def getheaders(self):
                    return [
                        ("content-type", "application/json"),
                        (
                            "x-request-id" if self.provider == "openai" else "request-id",
                            "synthetic-full-source-" + str(self.index),
                        ),
                    ]

                def close(self):
                    pass

            actual_run = executor.run_container

            def observed(specification, **kwargs):
                observed_start = time.monotonic()
                inputs()
                require(len(evidence["workers"]) < 51, "extra worker attempted")
                session = kwargs["handle"].__self__
                owner = session.gateway.directory
                require(
                    owner in owner_paths and owner not in seen,
                    "worker owner is replaced or outside fixed plan",
                )
                seen.add(owner)
                initial, parts = kwargs["initial"], owner.relative_to(search).parts
                active.clear()
                if "proposal" in parts:
                    program = int(parts[1])
                    active.update(
                        stage="proposal",
                        program=program,
                        expected_calls=1,
                        feedback=initial["feedback"],
                    )
                    require(
                        initial["format"] == "buddha.candidate-improvement-worker.v1"
                        and initial["config"] == proposal["proposal_template"]["config"]
                        and initial["max_callbacks"] == 3,
                        "inherited proposal worker differs",
                    )
                else:
                    program = 0 if parts[0] == "seed" else int(parts[1]) + 1
                    task = int(parts[parts.index("tasks") + 1])
                    if specification.role == "agent":
                        active.update(
                            stage="generation",
                            program=program,
                            task=task,
                            expected_calls=GENERATION_CALLBACKS[program],
                        )
                        require(
                            initial["format"] == "buddha.candidate-worker.v1"
                            and initial["task"] == tasks[task]
                            and initial["config"] == generation["config"]
                            and initial["max_callbacks"] == 12,
                            "generation worker/task differs",
                        )
                    else:
                        command = initial["command"]
                        index = command["index"]
                        stage = ["partition", "score", "summary"][index]
                        active.update(
                            stage=stage,
                            program=program,
                            task=task,
                            expected_calls=[1, 10, 0][index],
                        )
                        frozen = native["selection"]["release"]["commands"][index]
                        require(
                            command["module"] == frozen["module"]
                            and command["argv"]
                            == [
                                "/scratch/artifacts" if value == "{artifacts}" else value
                                for value in frozen["argv"]
                            ],
                            "complete official command changed",
                        )
                active.update(owner=owner, calls=0)
                section = generation if specification.role == "agent" else native
                require(
                    specification.image_id == section["executor"]["image_id"]
                    and asdict(kwargs["limits"]) == section["executor"]["limits"]
                    and kwargs["docker_endpoint"] == endpoint
                    and specification.runner_entrypoint == section["executor"]["runner_entrypoint"],
                    "actual image/resource/entrypoint settings changed",
                )
                if specification.role == "agent":
                    require(
                        initial["agent_sha256"] == agent_ids[program]
                        and initial["runtime"]["sha256"] == proposal["expected_runtime_sha256"]
                        and set(initial["roots"]) == {"agent", "runner"},
                        "actual proposing/generating source differs",
                    )
                    require(
                        {name for name, _ in specification.mounts} == {"/agent", "/runner"},
                        "candidate mounts changed",
                    )
                else:
                    require(
                        {name for name, _ in specification.mounts}
                        == {"/official", "/runner", "/inputs"},
                        "native mounts changed",
                    )
                require(
                    all(key.encode() not in _json(initial) for key in KEYS.values()),
                    "credential crossed frame",
                )
                manifest = _read_manifest(owner)
                controls = manifest["invocation"]["inputs"]
                require(
                    type(controls) is list and len(controls) <= 1024,
                    "actual invocation input bound differs",
                )
                frames, handle = [], kwargs["handle"]

                def frame(value):
                    raw = _json(value)
                    response = handle(value)
                    reply = None if response is None else _json(response)
                    frames.append(
                        {
                            "type": value.get("type"),
                            "bytes": len(raw) + 1,
                            "sha256": sha(raw),
                            "reply_bytes": 0 if reply is None else len(reply) + 1,
                        }
                    )
                    return response

                kwargs["handle"] = frame
                print(
                    json.dumps(
                        {
                            "phase": phase,
                            "worker": len(evidence["workers"]) + 1,
                            "owner": owner.relative_to(search).as_posix(),
                        }
                    ),
                    flush=True,
                )
                observer_seconds = time.monotonic() - observed_start
                result = actual_run(specification, **kwargs)
                require(
                    result.exit_code == 0
                    and result.cleanup_status == "removed"
                    and result.image_id == specification.image_id
                    and re.fullmatch("[0-9a-f]{64}", result.container_id),
                    "worker or cleanup failed",
                )
                require(
                    active["calls"] == active["expected_calls"], "actual callback schedule differs"
                )
                limits = kwargs["limits"]
                require(
                    result.stdout_bytes <= limits.max_stdout_bytes
                    and result.stderr_bytes <= limits.max_stderr_bytes
                    and result.frame_count <= limits.max_frames
                    and result.elapsed_seconds <= limits.wall_seconds,
                    "actual cumulative execution bound exceeded",
                )
                require(
                    not executor._control(
                        docker,
                        [
                            "--host",
                            endpoint,
                            "container",
                            "ls",
                            "-a",
                            "--no-trunc",
                            "--filter",
                            "id=" + result.container_id,
                            "--format",
                            "{{.ID}}",
                        ],
                    ).strip(),
                    "reported owned container remains",
                )
                artifact = None
                if specification.role != "agent":
                    sizes = []
                    for name, expected in session.artifacts.items():
                        raw = read(session.output / "artifacts" / name, 64 * 1024**2)
                        require(sha(raw) == expected, "native artifact changed before measurement")
                        sizes.append(len(raw))
                    artifact = {
                        "file_count": len(sizes),
                        "total_bytes": sum(sizes),
                        "largest_file_bytes": max(sizes, default=0),
                    }
                    require(
                        len(sizes) <= 128
                        and sum(sizes) <= 128 * 1024**2
                        and max(sizes, default=0) <= 64 * 1024**2,
                        "native artifact bound exceeded",
                    )
                event = {
                    key: value for key, value in asdict(result).items() if key != "_configuration"
                }
                event.update(
                    configuration_sha256=sha(_json(result.configuration)),
                    owner=str(owner),
                    stage=active["stage"],
                    program=program,
                    calls=active["calls"],
                    initial_bytes=len(_json(initial)) + 1,
                    invocation_control_count=len(controls),
                    invocation_control_bytes=sum(
                        Path(row["path"]).stat().st_size for row in controls
                    ),
                    frames=frames,
                    limits=asdict(limits),
                    observer_preflight_seconds=observer_seconds,
                    artifacts=artifact,
                    storage=storage(args.directory),
                )
                evidence["workers"].append(event)
                return result

            def notice(message):
                evidence["notices"].append(
                    {
                        "elapsed_seconds": time.monotonic() - started,
                        "phase": phase,
                        "message": message,
                    }
                )
                print("[rehearsal] " + message, flush=True)

            original_keys = source_launch.credentials.key_environment

            @contextmanager
            def observed_keys(*positional, **options):
                entered = time.monotonic() - started
                require(
                    any(
                        row["phase"] == phase
                        and row["elapsed_seconds"] <= entered
                        and row["message"].startswith("Checking approved configuration")
                        for row in evidence["notices"]
                    ),
                    "checking notice did not precede original key-context entry",
                )
                evidence["key_entries"].append(
                    {
                        "phase": phase,
                        "elapsed_seconds": entered,
                        "notice_count": len(evidence["notices"]),
                        "prompt_keys": options["prompt_keys"],
                        "credentials": "synthetic environment only",
                    }
                )
                with original_keys(*positional, **options):
                    yield

            def invoke(receipt):
                return source_launch.launch(
                    launch_path,
                    expected_sha256=launch_sha,
                    live=True,
                    confirm_project_keys=True,
                    prompt_keys=False,
                    receipt=receipt,
                    transport=RawHTTPTransport(allow_paid=True, timeout_seconds=300),
                    notice=notice,
                    heartbeat_seconds=2,
                )

            phase = "interrupted-prefix"
            wrote, interrupted = native_pipeline._write, False
            decision_path = search / "iterations/0/decision.json"

            def interrupt_after_decision(path, raw):
                nonlocal interrupted
                wrote(path, raw)
                if path == decision_path and not interrupted:
                    interrupted = True
                    raise KeyboardInterrupt

            with (
                patch("http.client.HTTPSConnection", side_effect=Connection),
                patch("buddha.executor.run_container", side_effect=observed),
                patch.object(
                    source_launch.credentials, "key_environment", side_effect=observed_keys
                ),
            ):
                try:
                    with patch.object(
                        native_pipeline, "_write", side_effect=interrupt_after_decision
                    ):
                        invoke(receipts["prefix"])
                except KeyboardInterrupt:
                    require(
                        interrupted and decision_path.is_file(),
                        "interruption preceded durable decision",
                    )
                else:
                    raise RuntimeError("planned interruption did not occur")
                cancelled = decode(read(receipts["prefix"]))
                observation = decode(read(search / "observations/0.json"))
                require(
                    cancelled["status"] == "cancelled"
                    and cancelled["reason"] == "cancelled"
                    and observation["status"] == "incomplete"
                    and observation["reason"] == "cancelled"
                    and len(evidence["workers"]) == 25
                    and len(evidence["sends"]) == 130,
                    "cancelled prefix or its work counts differ",
                )
                prefix = tree(search)
                prefix_funding = authority.summary()
                prefix_owners = {row["directory"]: row["run_id"] for row in prefix_funding["runs"]}
                require(
                    len(prefix_owners) == 25
                    and prefix_funding["operation_count"] == 130
                    and prefix_funding["reserved_microusd"] == 0,
                    "prefix owner accounting differs",
                )
                evidence["prefix"] = {
                    "files": prefix,
                    "authority": prefix_funding,
                    "authorization_sha256": sha(read(authority_path)),
                    "owners": prefix_owners,
                    "receipt": str(receipts["prefix"]),
                    "receipt_sha256": sha(read(receipts["prefix"])),
                }
                evidence["phases"].append({"phase": phase, "workers": 25, "new_replies": 130})
                phase = "same-owner-continuation"
                result = invoke(receipts["continuation"])
                require(result["status"] == "complete", "same-owner continuation was incomplete")
                for name, value in prefix["files"].items():
                    require(sha(read(search / name)) == value["sha256"], "completed prefix changed")
                funding = authority.summary()
                require(
                    all(
                        {row["directory"]: row["run_id"] for row in funding["runs"]}.get(path)
                        == identifier
                        for path, identifier in prefix_owners.items()
                    ),
                    "continuation replaced original owner",
                )
                evidence["phases"].append(
                    {
                        "phase": phase,
                        "workers": len(evidence["workers"]) - 25,
                        "new_replies": len(evidence["sends"]) - 130,
                    }
                )
            phase = "completed-evidence"
            require(
                len(evidence["workers"]) == len(seen) == 51
                and len(evidence["sends"]) == 267
                and len({row["container_id"] for row in evidence["workers"]}) == 51,
                "full concrete work schedule differs",
            )
            require(
                Counter(row["stage"] for row in evidence["sends"])
                == {"generation": 132, "proposal": 3, "partition": 12, "score": 120},
                "physical stage totals differ",
            )
            report_raw = read(search / "report.json")
            report = source_search.inspect_source_search(
                search, authorization=authority_path, expected_report_sha256=sha(report_raw)
            )
            require(
                [row["status"] for row in report["decisions"]] == ["admitted"] * 3
                and [row["parent_id"] for row in report["decisions"]] == agent_ids[:3]
                and [row["child_id"] for row in report["decisions"]] == agent_ids[1:]
                and report["selection"]["selected_id"] == agent_ids[3]
                and len(report["screens"]) == 4
                and not report["failures"],
                "actual inherited chain differs",
            )
            for program, reference in enumerate(report["screens"]):
                location = Path(reference["directory"])
                for task in range(3):
                    generation_root = location / "tasks" / str(task) / "generation"
                    seal = decode(read(generation_root / "completed/0.json"))
                    answers = Answers.from_bytes(
                        read(generation_root / seal["attempt"] / "session/answers.json")
                    )
                    positions = (
                        [*range(0, 11, 2), *range(1, 11, 2)][:10]
                        if program == 1
                        else (
                            list(range(1, 11))
                            if program == 2
                            else list(range(2, 12))
                            if program == 3
                            else list(range(10))
                        )
                    )
                    require(
                        answers.to_record()["outputs"][0]["answers"]
                        == [literal(program, task, index) for index in positions],
                        "actual generation procedure/C1 differs",
                    )
            expected_charge, histories = 0, []
            for owner in sorted(owner_paths):
                manifest = _read_manifest(owner)
                history = read_gateway_history(
                    owner,
                    manifest_sha256=sha(_json(manifest)),
                    ledger_sha256=sha(read(owner / "operations.sqlite3")),
                )
                require(
                    all(op.status == "completed" for op in history.operations),
                    "owner has uncertain operation",
                )
                for operation in history.operations:
                    request = operation.receipt["request"]
                    profile = manifest["profiles"][request["capability"]]["profiles"][
                        request["profile_id"]
                    ]
                    charge = ModelSpec(**profile["spec"]).cost_microusd(5, 3)
                    require(
                        operation.actual_microusd == charge,
                        "synthetic selected-profile charge differs",
                    )
                    expected_charge += charge
                histories.append(history)
            require(
                len(funding["runs"]) == 51
                and all(not row["active"] for row in funding["runs"])
                and funding["authorization_id"] == terms["authorization_id"]
                and sum(len(row.operations) for row in histories)
                == funding["operation_count"]
                == 267
                and funding["spent_microusd"] == funding["committed_microusd"] == expected_charge
                and funding["reserved_microusd"] == 0,
                "original grant/owner accounting differs",
            )
            evidence["report"] = {"path": str(search / "report.json"), "sha256": sha(report_raw)}
            evidence["funding"] = funding
            phase = "completed-keyless-repeat"
            before = tree(args.directory)

            def forbidden(*_args, **_kwargs):
                raise RuntimeError("completed keyless repeat attempted an active operation")

            original_getitem = type(os.environ).__getitem__

            def keyless_getitem(environment, name):
                require(
                    name not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"},
                    "completed repeat attempted provider-key lookup",
                )
                return original_getitem(environment, name)

            with (
                patch.dict(os.environ, ordinary, clear=True),
                patch("os.environ.get", side_effect=forbidden),
                patch("os.getenv", side_effect=forbidden),
                patch.object(type(os.environ), "__getitem__", keyless_getitem),
                patch("getpass.getpass", side_effect=forbidden),
                patch("http.client.HTTPSConnection", side_effect=forbidden),
                patch("buddha.executor.run_container", side_effect=forbidden),
                patch("buddha.authorization.Authorization.__init__", side_effect=forbidden),
                patch("buddha.authorization.Authorization.summary", side_effect=forbidden),
                patch.object(source_launch.credentials, "key_environment", side_effect=forbidden),
            ):
                repeated = source_launch.launch(
                    launch_path,
                    expected_sha256=launch_sha,
                    receipt=receipts["keyless"],
                    notice=notice,
                    heartbeat_seconds=2,
                )
            require(
                repeated["status"] == "complete" and tree(args.directory) == before,
                "completed keyless repeat changed saved evidence",
            )
            evidence["phases"].append({"phase": phase, "new_replies": 0, "new_workers": 0})
            require(
                any("Phase: executing" in row["message"] for row in evidence["notices"]),
                "actual execution progress was not observed",
            )
            require(
                len(evidence["key_entries"]) == 2
                and all(not row["prompt_keys"] for row in evidence["key_entries"]),
                "fake key-context entry count differs",
            )
            evidence["receipts"] = {
                name: {"path": str(path), "sha256": sha(read(path))}
                for name, path in receipts.items()
            }
            evidence["final_storage"] = storage(args.directory)
            evidence["highwater"] = {
                name: max(worker[name] for worker in evidence["workers"])
                for name in (
                    "initial_bytes",
                    "invocation_control_count",
                    "invocation_control_bytes",
                    "stdout_bytes",
                    "stderr_bytes",
                    "frame_count",
                    "elapsed_seconds",
                )
            }
            evidence["highwater"]["frame_bytes"] = max(
                frame["bytes"] for worker in evidence["workers"] for frame in worker["frames"]
            )
            evidence["highwater"]["storage_total_bytes"] = max(
                row["storage"]["total_bytes"] for row in evidence["workers"]
            )
            inputs()
            evidence.update(
                status="pass",
                phase="complete",
                elapsed_seconds=time.monotonic() - started,
                finished_utc=datetime.now(UTC).isoformat(),
            )
    except BaseException as error:
        evidence.update(
            status="incomplete" if isinstance(error, KeyboardInterrupt) else "fail",
            phase=phase,
            reason="cancelled"
            if isinstance(error, KeyboardInterrupt)
            else "rehearsal_check_failed",
            elapsed_seconds=time.monotonic() - started,
        )
        raise
    finally:
        save(args.out, evidence)
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "proof": str(args.out),
                "workers": 51,
                "synthetic_replies": 267,
                "real_provider_calls": 0,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main(arguments())
