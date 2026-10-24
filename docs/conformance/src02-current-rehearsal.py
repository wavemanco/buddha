"""UNEXECUTED DRAFT: current full-output source route, actual confinement, fake HTTPS.

Review this program and freeze its source map before running in NEW paths.
The caller-pinned NEW handoff3 proposal stays read-only. A synthetic grant exercises
the real launcher/controller; no user authorization, real key or provider call
is involved. Supplied descendants and canned judgments are engineering inputs.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import stat

# Every Popen requires exact registered Docker argv before the real process call.
import subprocess  # nosec B404
import sys
import threading
import time
import traceback
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

if not __debug__:
    raise RuntimeError("This proof requires ordinary Python with assertions enabled")

SCRIPT = Path(__file__).resolve()
ROOT = None  # Set only from the explicit, source-map-pinned --repo root.
SEED_SHA256 = "77cfa68f6b3c6996fd503e1ce6f7a964eb57abdb8bde98f6761de5f6e298ff4f"
TASK_IDS = ["curated-0", "curated-47", "curated-97"]
QUALITY_SCORES = {0: [7, 7, 7], 2: [8, 6, 8]}  # Supplied controls, not semantic judgments.
PROPOSAL_INSTRUCTIONS_VERSION = "buddha.current-source-proposal-instructions.v1"
PROPOSAL_INSTRUCTIONS = (
    "Use the measured development feedback to propose substantive, evidence-grounded procedural "
    "changes to both generate and propose_improvement (or their actually used helpers). Preserve "
    "complete feedback, callable interfaces and all host/model/resource boundaries. Explain each "
    "proposed change in hypothesis without claiming success. Changes confined to prompt constants, "
    "names, comments or formatting do not meet this observation's aim."
)
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


def checked_write_target(value, *, unlink=False):
    """Check actual audit-event spellings, including not-yet-created descendants.

    This local proof trusts the host against concurrent filesystem replacement;
    it rejects links/aliases rather than using resolution to launder them.
    """
    try:
        spelling = os.fsdecode(value)
        target = Path(spelling)
        if (
            not target.is_absolute()
            or spelling != str(target)
            or spelling.startswith(("//", "\\\\"))
            or any(part in {".", ".."} for part in spelling.replace("\\", "/").split("/"))
        ):
            return None
        reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
            prefix + number for prefix in ("COM", "LPT") for number in "123456789¹²³"
        }
        for name in target.parts[1:]:
            if (
                not name
                or name != name.rstrip(" .")
                or name.split(".", 1)[0].rstrip(" .").upper() in reserved
                or any(char in '<>:"/\\|?*' or ord(char) < 32 for char in name)
            ):
                return None
        # lstat every existing parent BEFORE resolving: future descendants are
        # allowed only when all existing components are plain and canonical.
        for current in reversed((target, *target.parents)):
            try:
                info = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return None
            if current != target and not stat.S_ISDIR(info.st_mode):
                return None
            if current == target and not (
                stat.S_ISDIR(info.st_mode)
                or stat.S_ISREG(info.st_mode)
                and (info.st_nlink == 1 or unlink and info.st_nlink > 1)
            ):
                return None
        if str(target.resolve(strict=False)) != str(target):
            return None
        return target
    except (OSError, TypeError, ValueError):
        return None


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


def docker_process_guard(docker, endpoint, events, original, runtime, images):
    """Exact current owned lifecycle, adapted from the reviewed witness guard."""
    registration, owned = threading.local(), set()

    def permitted(argv):
        if runtime.get("passive"):
            return False
        if argv == ["context", "show"]:
            return True
        if len(argv) == 5 and argv[:4] == [
            "context",
            "inspect",
            "--format",
            "{{json .Endpoints.docker}}",
        ]:
            return re.fullmatch("[A-Za-z0-9_.-]{1,128}", argv[4]) is not None
        if argv[:2] != ["--host", endpoint]:
            return False
        tail, current = argv[2:], runtime.get("active")
        if len(tail) == 3 and tail[:2] == ["image", "inspect"] and tail[2] in images:
            return True
        if len(tail) == 4 and tail[:3] == ["inspect", "--format", "{{json .}}"]:
            return tail[3] in owned or tail[3] in images
        if any(
            tail == value
            for identity in owned
            for value in (
                [
                    "container",
                    "ls",
                    "-a",
                    "--no-trunc",
                    "--format",
                    "{{.ID}}",
                    "--filter",
                    "id=" + identity,
                ],
                [
                    "container",
                    "ls",
                    "-a",
                    "--no-trunc",
                    "--filter",
                    "id=" + identity,
                    "--format",
                    "{{.ID}}",
                ],
            )
        ):
            return True
        if current is None:
            return False
        if tail[:1] == ["create"]:
            try:
                name = tail[tail.index("--name") + 1]
                label = tail[tail.index("--label") + 1]
            except (ValueError, IndexError):
                return False
            match = re.fullmatch("buddha-([0-9a-f]{32})", name)
            executor = runtime["executor"]
            if not match or label != executor.OWNER_LABEL + "=" + match.group(1):
                return False
            if tail != executor._create_args(
                current["spec"], current["limits"], name, match.group(1)
            ):
                return False
            current.update(name=name, owner=match.group(1))
            return True
        if len(tail) == 3 and tail[:2] in (["start", "-ai"], ["rm", "-f"]):
            return tail[2] in owned
        if len(tail) == 2 and tail[0] == "kill":
            return tail[1] in owned
        if current.get("name") and tail == [
            "container",
            "ls",
            "-a",
            "--no-trunc",
            "--format",
            "{{.ID}}",
            "--filter",
            "name=^/" + current["name"] + "$",
            "--filter",
            "label=" + runtime["executor"].OWNER_LABEL + "=" + current["owner"],
        ]:
            return True
        for identity in owned:
            if tail in (
                [
                    "container",
                    "ls",
                    "-a",
                    "--no-trunc",
                    "--format",
                    "{{.ID}}",
                    "--filter",
                    "id=" + identity,
                ],
                [
                    "container",
                    "ls",
                    "-a",
                    "--no-trunc",
                    "--filter",
                    "id=" + identity,
                    "--format",
                    "{{.ID}}",
                ],
            ):
                return True
        return False

    def guarded(command, *positional, **options):
        require(
            not positional and "executable" not in options and options.get("shell", False) is False,
            "shell/executable override forbidden",
        )
        require(
            type(command) in (list, tuple)
            and len(command) >= 2
            and all(type(value) is str for value in command)
            and command[0] == docker
            and permitted(list(command[1:])),
            "Docker command outside exact local owned lifecycle",
        )
        require(getattr(registration, "value", None) is None, "nested subprocess registration")
        registration.value = (tuple(command), subprocess.list2cmdline(command))
        try:
            return original(command, executable=docker, **options)
        finally:
            del registration.value

    def audited(executable, command):
        current = getattr(registration, "value", None)
        require(executable == docker and current is not None, "unregistered process executable")
        argv, serialized = current
        require(
            type(command) is str
            and command == serialized
            or type(command) in (list, tuple)
            and tuple(command) == argv,
            "process audit differs from exact validated argv",
        )
        events.append(
            {
                "sha256": sha(encoded(argv)),
                "verb": argv[3] if argv[1:2] == ("--host",) else "context",
            }
        )

    def control(executable, argv):
        require(executable == docker, "different Docker executable")
        raw = runtime["original_control"](executable, argv)
        if argv[:3] == ["--host", endpoint, "create"]:
            identity = raw.strip().decode("ascii")
            require(re.fullmatch("[0-9a-f]{64}", identity), "created container identity absent")
            owned.add(identity)
        elif (
            runtime.get("active")
            and len(argv) == 12
            and argv[2:9]
            == ["container", "ls", "-a", "--no-trunc", "--format", "{{.ID}}", "--filter"]
        ):
            values = raw.split()
            require(
                len(values) <= 1 and all(re.fullmatch(b"[0-9a-f]{64}", value) for value in values),
                "ambiguous owned lost-create lookup",
            )
            owned.update(value.decode("ascii") for value in values)
        return raw

    return guarded, audited, control, owned


def save(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


GENERATION_CALLBACKS = (10, 10, 11, 11)  # P, W0, C, W1; supplied, not observed.


def programs(parent_raw):
    """Return literal controls only; NEVER compile/evaluate these strings on host."""
    require(
        type(parent_raw) is bytes and sha(parent_raw) == SEED_SHA256,
        "current trusted seed-v2 bytes differ",
    )
    parent = parent_raw.decode("utf-8")
    marker = "# buddha.source-seed-improver.v2: appended to the unchanged frozen seed."
    require(
        parent.count(marker) == parent.count("def generate(") == 1,
        "current trusted source layout differs",
    )
    start, end = parent.index("def generate("), parent.index(marker)
    require(start < end, "trusted composition order differs")
    reverse = """def generate(task, config, complete):
    item, selected = _task(task), _config(config)
    answers = []
    for _ in range(item["count"]):
        answers.append(normalize(selected["provider"], complete(
            selected["provider"], request(selected, item, answers))))
    return list(reversed(answers))
"""
    planned = (
        "def generate(task, config, complete):\n"
        "    item, selected = _task(task), _config(config)\n"
        '    planning = dict(item, prompt="Plan contrasting central content for'
        ' this task: " + item["prompt"])\n'
        '    plan = normalize(selected["provider"], complete(\n'
        '        selected["provider"], request(selected, planning)))\n'
        '    drafting = dict(item, prompt=item["prompt"] + "\\nPrivate planning '
        'input: " + plan)\n'
        "    answers = []\n"
        '    for _ in range(item["count"]):\n'
        '        answers.append(normalize(selected["provider"], complete(\n'
        '            selected["provider"], request(selected, drafting, answers)'
        ")))\n"
        "    return answers\n"
    )
    alternating = """def generate(task, config, complete):
    item, selected = _task(task), _config(config)
    drafts = []
    for _ in range(item["count"] + 1):
        drafts.append(normalize(selected["provider"], complete(
            selected["provider"], request(selected, item, drafts))))
    return (drafts[::2] + drafts[1::2])[:item["count"]]
"""
    improver = """
# Supplied C changes actual improver control flow and consumes a planning response.
_current_demo_original_improver = propose_improvement

def propose_improvement(parent_bundle, development_feedback, config, complete):
    selected = _config(config)
    if not callable(complete):
        raise SeedError("callback required")
    notes = [json.loads(row["note"]) for row in development_feedback]
    weakest = min(range(len(notes)), key=lambda index: notes[index]["utility"])
    payload = json.dumps({"parent": parent_bundle,
        "development_feedback": development_feedback,
        "target_task_id": development_feedback[weakest]["task"]["id"]},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    task = {"id": "current-demo-mutation-plan", "count": 1,
        "prompt": "CURRENT_DEMO_PLAN\\n" + payload}
    reply = complete(selected["provider"], request(selected, task))
    if (reply["choices"][0]["finish_reason"] if selected["provider"] == "openai"
        else reply["stop_reason"]) != ("stop" if selected["provider"] == "openai" else "end_turn"):
        raise SeedError("planning did not finish")
    plan = normalize(selected["provider"], reply)
    enriched = [{"task": row["task"], "note": json.dumps({
        "measurements": note, "mutation_plan": plan,
        "target_task_id": development_feedback[weakest]["task"]["id"]},
        sort_keys=True, separators=(",", ":"), allow_nan=False)}
        for row, note in zip(development_feedback, notes, strict=True)]
    return _current_demo_original_improver(parent_bundle, enriched, config, complete)
"""

    def changed(body, extra=""):
        return (parent[:start] + body + "\n\n" + parent[end:] + extra).encode("utf-8")

    result = (
        parent_raw,
        changed(reverse),
        changed(planned, improver),
        changed(alternating, improver),
    )
    require(
        len(set(result)) == 4 and all(len(raw) <= 1024**2 for raw in result),
        "supplied sources are not distinct/bounded",
    )
    return result


def proposal_user_message(messages):
    expected_system = (
        [{"role": "system", "content": PROPOSAL_INSTRUCTIONS}] if PROPOSAL_INSTRUCTIONS else []
    )
    if (
        type(messages) is not list
        or len(messages) != len(expected_system) + 1
        or messages[:-1] != expected_system
    ):
        raise ValueError("prospective proposal system instructions differ")
    message = messages[-1]
    if (
        type(message) is not dict
        or set(message) != {"role", "content"}
        or message["role"] != "user"
    ):
        raise ValueError("proposal user message differs")
    return message


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
    message = proposal_user_message(record["messages"])
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
        or packet["format"] != "buddha.source-seed-improver.v2"
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
            or len(note.encode("utf-8")) > 1024**2
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
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--sources-sha256", required=True)
    parser.add_argument("--script-sha256", required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    return parser.parse_args()


def preflight(args):
    global ROOT
    ROOT = absolute(args.repo)
    require(ROOT.is_dir(), "explicit source root is absent")
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
    digest(args.proposal_sha256)
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
    require(sha(proposal_raw) == args.proposal_sha256, "raw NEW proposal differs")
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
        and proposal["format"] == "buddha.source-handoff.v3"
        and proposal["mutation_witness"]
        == {
            "format": "buddha.source-mutation-witness.v1",
            "task_policy": "first_ordered_development_task",
            "depth": 1,
        }
        and proposal["source_copy"]
        == {"format": "buddha.source-copy.v1", "method": "verified_private_snapshot_before_owner"}
        and proposal["spec"]
        == {
            "format": "buddha.source-search.v1",
            "iterations": 1,
            "max_active": 2,
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
        and proposal["proposal_template"]["config"]["instructions"] == PROPOSAL_INSTRUCTIONS
        and proposal["requested_terms"] == {"budget_microusd": 25_000_000, "max_calls": 512},
        "concrete quota or synthetic grant schedule differs",
    )
    source_path = Path(generation["roots"]["agent"]) / "candidate.py"
    parent_raw = read(source_path)
    require(sha(parent_raw) == SEED_SHA256, "actual composed starter differs")
    supplied = programs(parent_raw)
    fragment = read(args.proposal.parent / "inputs/improver-fragment.txt")
    require(
        supplied[0].endswith(fragment)
        and supplied[1].endswith(fragment)
        and fragment in supplied[2]
        and fragment in supplied[3],
        "literal v2 fragment differs",
    )
    contract = fragment.decode().split('_SOURCE_SEED_PROMPT = """', 1)[1].split('"""', 1)[0]
    agent_ids = [sha(encoded({"candidate.py": sha(value)})) for value in supplied]
    owner_paths = (
        {
            root / "tasks" / str(task) / role / "owners" / str(index)
            for root in [
                search / "seed",
                search / "iterations/0/screen",
            ]
            for task in range(3)
            for role, indices in (("generation", [0]), ("evaluation", [1, 2, 3]))
            for index in indices
        }
        | {search / "iterations/0/proposal/owners/0"}
        | {
            root / role / "owners/0"
            for root in (search / "seed-witness", search / "iterations/0/witness")
            for role in ("proposal", "generation")
        }
    )
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
        len(owner_paths) == 29 and len(databases) == 30, "original synthetic owner plan differs"
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
        "format": "buddha.src02-current-demo-rehearsal-draft.v2",
        "status": "running",
        "fixture": str(args.directory),
        "script_sha256": args.script_sha256,
        "source_map_sha256": sha(map_raw),
        "source_sha256": pins,
        "proposal": {"path": str(args.proposal), "sha256": args.proposal_sha256},
        "started_utc": datetime.now(UTC).isoformat(),
        "task_ids": TASK_IDS,
        "candidate_source_bytes": [len(value) for value in supplied],
        "candidate_source_sha256": [sha(value) for value in supplied],
        "candidate_ids": agent_ids,
        "callbacks_per_generation_task": GENERATION_CALLBACKS,
        "supplied_quality_scores": QUALITY_SCORES,
        "proposal_instructions": {
            "format": PROPOSAL_INSTRUCTIONS_VERSION,
            "text": PROPOSAL_INSTRUCTIONS,
            "sha256": sha(PROPOSAL_INSTRUCTIONS.encode("utf-8")),
        },
        "guard_controls": [],
        "declared_upper_bound": {
            "workers": 29,
            "generation_sets": 8,
            "native_assessments": 6,
            "proposal_roles": 3,
        },
        "counts_are_observed_only_after_execution": True,
        "real_provider_calls": 0,
        "actual_provider_keys_used": False,
        "host_candidate_execution": False,
        "host_official_execution": False,
        "workers": [],
        "frame_failures": [],
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
            "Fixed supplied P/W0/C/W1 controls; no universal mutation-competence, "
            "edited-improver efficacy or improvement claim.",
            "Host and local Docker daemon are trusted; "
            "original records and user funding are not used.",
            "Fake keys are already in this dedicated process; "
            "the key-entry observer checks ordering, not interactive paste behavior.",
        ],
    }
    phase = "preparation"
    runtime = {"active": None}
    guarded_popen, audited_popen, guarded_control, owned_containers = docker_process_guard(
        docker,
        endpoint,
        evidence["docker_commands"],
        subprocess.Popen,
        runtime,
        {generation["executor"]["image_id"], native["executor"]["image_id"]},
    )

    def inputs():
        require(sha(read(args.sources, 32 * 1024**2)) == args.sources_sha256, "source map changed")
        require(
            all(sha(read(Path(path))) == expected for path, expected in pins.items()),
            "pinned current or historical input changed",
        )

    def writable(value, *, unlink=False):
        if isinstance(value, int):
            return phase != "completed-keyless-repeat"
        path = checked_write_target(value, unlink=unlink)
        if unlink:
            return (
                path is not None
                and phase != "completed-keyless-repeat"
                and path.is_relative_to(args.directory)
            )
        return path is not None and (
            path in permitted_outputs
            or (phase != "completed-keyless-repeat" and path.is_relative_to(args.directory))
        )

    def audit(event, values):
        if event.startswith(("os.system", "os.posix_spawn", "os.exec", "os.spawn")):
            raise RuntimeError("unregistered host process forbidden")
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
        if event == "os.remove":
            require(writable(values[0], unlink=True), "mutation outside synthetic outputs")
        if event in {"os.mkdir", "os.rmdir", "os.chmod", "os.utime"}:
            require(writable(values[0]), "mutation outside synthetic outputs")
        if event in {"os.rename", "os.link", "os.symlink"}:
            require(
                writable(values[0]) and writable(values[1]), "move/link outside synthetic outputs"
            )

    original_connect = sqlite3.connect

    def guarded_connect(database, *args_, **options):
        require(
            "factory" not in options
            and str(database) in allowed_sql
            and (phase != "completed-keyless-repeat" or database == ":memory:"),
            "unapproved SQL path or factory",
        )

        class Connection(sqlite3.Connection):
            attaching, deserializing = None, False

            def execute(self, sql, parameters=(), /):
                if sql.strip().upper().startswith("ATTACH"):
                    require(
                        sql.strip().upper() == "ATTACH DATABASE ? AS FUNDING"
                        and type(parameters) in (list, tuple)
                        and len(parameters) == 1
                        and parameters[0] in allowed_sql
                        and parameters[0] != ":memory:"
                        and phase != "completed-keyless-repeat",
                        "unapproved funding attachment",
                    )
                    self.attaching = parameters[0]
                try:
                    return super().execute(sql, parameters)
                finally:
                    self.attaching = None

            def deserialize(self, data, /, *, name="main"):
                require(
                    database == ":memory:" and name == "main", "deserialize requires main memory"
                )
                self.deserializing = True
                try:
                    return super().deserialize(data, name=name)
                finally:
                    self.deserializing = False

        connection = original_connect(database, *args_, factory=Connection, **options)

        def authorizer(action, first, _second, _database, _trigger):
            if action == sqlite3.SQLITE_ATTACH:
                if (
                    connection.deserializing
                    or connection.attaching is not None
                    and first in (None, connection.attaching)
                ):
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorizer)
        return connection

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
        # Real guarded API probes, all before any authority or worker. These NEW
        # sibling canaries are never existing user paths. A wrong exception fails.
        outside_write = args.directory.with_name(args.directory.name + "-guard-outside-write")
        outside_sql = args.directory.with_name(args.directory.name + "-guard-outside.sqlite3")
        for canary in (outside_write, outside_sql):
            require(
                checked_write_target(canary) == canary
                and not canary.exists()
                and not canary.is_symlink()
                and canary not in permitted_outputs
                and str(canary) not in pins,
                "guard canary must be a NEW non-output sibling",
            )
        guard_controls = []
        evidence["guard_controls"] = guard_controls

        def refused(label, operation, message):
            try:
                operation()
            except RuntimeError as error:
                require(
                    type(error) is RuntimeError and str(error) == message,
                    "guard control failed for a different reason: " + label,
                )
            else:
                raise RuntimeError("guard control unexpectedly allowed: " + label)
            require(
                not outside_write.exists() and not outside_sql.exists(),
                "guard control created an outside canary",
            )
            guard_controls.append({"control": label, "status": "rejected", "message": message})

        def create_empty(target):
            with target.open("xb"):
                pass

        refused(
            "outside_write",
            lambda: create_empty(outside_write),
            "write outside new synthetic outputs",
        )
        refused(
            "traversal_write",
            lambda: create_empty(args.directory / ".." / outside_write.name),
            "write outside new synthetic outputs",
        )
        refused(
            "outside_sql",
            lambda: sqlite3.connect(str(outside_sql)),
            "SQL outside original synthetic plan or completed passive mode",
        )
        refused(
            "non_docker_process",
            lambda: subprocess.Popen([sys.executable, "-c", "raise SystemExit(73)"]),
            "unregistered process executable",
        )
        refused("socket_creation", lambda: socket.socket(), "real host network operation forbidden")
        require(not args.directory.exists(), "negative controls changed the absent fixture")
        args.directory.mkdir()
        positive_parent = args.directory / "guard-control-future"
        positive = positive_parent / "contained.txt"
        positive_parent.mkdir()
        with positive.open("xb") as stream:
            stream.write(b"contained guard positive\n")
        require(
            positive.read_bytes() == b"contained guard positive\n",
            "contained write control differs",
        )
        positive.unlink()
        positive_parent.rmdir()
        require(
            not any(args.directory.iterdir())
            and not outside_write.exists()
            and not outside_sql.exists(),
            "guard controls did not leave an empty fresh fixture",
        )
        guard_controls.append(
            {"control": "contained_future_write", "status": "created_verified_removed"}
        )
        linked_temporary = args.directory / "guard-linked-temporary"
        linked_target = args.directory / "guard-linked-publication"
        linked_bytes = b"contained hardlink publication positive\n"
        with linked_temporary.open("xb") as stream:
            stream.write(linked_bytes)
        os.link(linked_temporary, linked_target)
        require(
            linked_temporary.stat().st_nlink == linked_target.stat().st_nlink == 2,
            "hardlink guard control did not publish two names",
        )
        refused(
            "linked_file_write",
            lambda: create_empty(linked_temporary),
            "write outside new synthetic outputs",
        )
        linked_temporary.unlink()
        require(
            linked_target.read_bytes() == linked_bytes and linked_target.stat().st_nlink == 1,
            "contained hardlink unlink changed the publication",
        )
        linked_target.unlink()
        require(not any(args.directory.iterdir()), "hardlink guard control left fixture data")
        guard_controls.append(
            {
                "control": "contained_hardlink_publication",
                "status": "linked_unlinked_verified_removed",
            }
        )
        with (
            patch.dict(os.environ, fake_environment, clear=True),
            patch("subprocess.Popen", side_effect=guarded_popen),
            patch("sqlite3.connect", side_effect=guarded_connect),
        ):
            sys.path.insert(0, str(ROOT))
            from buddha import (
                candidate_improvement,
                executor,
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
            runtime.update(executor=executor, original_control=executor._control)
            executor._control = guarded_control
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
                args.proposal, expected_sha256=args.proposal_sha256
            )
            require(
                checked_proposal["planned"]["maximum_stage_owners"] == 29,
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
                source_launch._planned_owners(search, screen, 1, mutation_witness=True)
                == owner_paths,
                "launcher derives a different owner schedule",
            )
            inputs()
            require(
                args.directory.is_dir() and not any(args.directory.iterdir()),
                "guard fixture changed before authority",
            )
            authority = Authorization.create(
                authority_path,
                authorization_id="synthetic-full-source-" + sha(str(args.directory).encode())[:24],
                scope=checked_proposal["funding"]["scope"],
                **proposal["requested_terms"],
            )
            terms = authority.summary()
            approval = {
                "format": "buddha.source-approval.v1",
                "proposal_sha256": args.proposal_sha256,
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
                "proposal": {"path": str(args.proposal), "sha256": args.proposal_sha256},
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
                    f"  Supplied rehearsal text: program={program}; "
                    f"task={TASK_IDS[task]}; callback={ordinal}.\n"
                    + "Literal Café 雪 — preserve the entire supplied output. " * 20
                    + f"\nLATE ENDING program={program}; task={task}; ordinal={ordinal}.  "
                )

            def expected_generation(program, task, ordinal):
                item, first_answer = tasks[task], 0
                prompt = item["prompt"]
                if program == 2:
                    if ordinal == 0:
                        prompt = "Plan contrasting central content for this task: " + prompt
                    else:
                        prompt += "\nPrivate planning input: " + literal(program, task, 0)
                        first_answer = 1
                history = (
                    []
                    if program == 2 and ordinal == 0
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
                        len(evidence["sends"]) < 154 and active, "extra physical send attempted"
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
                        require(
                            self.provider == "openai" and self.model == "gpt-6.1-sol",
                            "proposal provider/model differs",
                        )
                        expected_parent = {
                            "entrypoint": "candidate.py",
                            "source": supplied[active["program"]].decode(),
                            "agent_sha256": agent_ids[active["program"]],
                        }
                        if active["program"] == 2 and ordinal == 0:
                            require(
                                set(request)
                                == {
                                    "model",
                                    "messages",
                                    "max_completion_tokens",
                                    "reasoning_effort",
                                    "service_tier",
                                }
                                and request["max_completion_tokens"] == 32768
                                and request["reasoning_effort"] == "low"
                                and request["service_tier"] == "default",
                                "C improver planning envelope differs",
                            )
                            content = proposal_user_message(request["messages"])
                            require(
                                content["role"] == "user"
                                and content["content"].startswith("CURRENT_DEMO_PLAN\n"),
                                "actual changed C improver planning branch was not used",
                            )
                            packet = decode(content["content"].split("\n", 1)[1])
                            utilities = [
                                decode(row["note"])["utility"] for row in active["feedback"]
                            ]
                            weakest = min(range(3), key=lambda index: utilities[index])
                            require(
                                weakest == 1
                                and utilities.count(utilities[weakest]) == 1
                                and TASK_IDS[weakest] == "curated-47",
                                (
                                    "C planning did not select the unique "
                                    "nonfirst weakest measured task"
                                ),
                            )
                            require(
                                packet
                                == {
                                    "parent": expected_parent,
                                    "development_feedback": active["feedback"],
                                    "target_task_id": TASK_IDS[weakest],
                                },
                                "C planning lost original full measured packet",
                            )
                            self.text = (
                                "Supplied planning result; preserve all original measurements."
                            )
                            active["plan"] = self.text
                        else:
                            packet = proposal_payload(body)
                            expected_feedback = active["feedback"]
                            if active["program"] == 2:
                                weakest = min(
                                    range(3),
                                    key=lambda index: decode(active["feedback"][index]["note"])[
                                        "utility"
                                    ],
                                )
                                expected_feedback = [
                                    {
                                        "task": row["task"],
                                        "note": encoded(
                                            {
                                                "measurements": decode(row["note"]),
                                                "mutation_plan": active["plan"],
                                                "target_task_id": TASK_IDS[weakest],
                                            }
                                        ).decode(),
                                    }
                                    for row in active["feedback"]
                                ]
                            require(
                                packet["parent"] == expected_parent
                                and packet["development_feedback"] == expected_feedback,
                                (
                                    "actual parent or complete measured "
                                    "feedback/planning result differs"
                                ),
                            )
                            require(
                                proposal_user_message(request["messages"])["content"].split(
                                    "\n\nINPUT_JSON\n", 1
                                )[0]
                                == contract,
                                "fixed source contract differs",
                            )
                            self.text = _json(
                                {
                                    "source": supplied[active["reply_program"]].decode(),
                                    "hypothesis": (
                                        "Supplied control only; no model authorship "
                                        "or improvement claim."
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
                        self.text = _json(
                            {"score": QUALITY_SCORES[active["program"]][active["task"]]}
                        ).decode()
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
                require(len(evidence["workers"]) < 29, "extra worker attempted")
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
                    if parts[0] == "seed-witness":
                        program, reply_program = 0, 1
                    elif "witness" in parts:
                        program, reply_program = 2, 3
                    else:
                        program, reply_program = 0, 2
                    active.update(
                        stage="proposal",
                        program=program,
                        reply_program=reply_program,
                        expected_calls=2 if program == 2 else 1,
                        feedback=initial["feedback"],
                    )
                    require(
                        initial["format"] == "buddha.candidate-improvement-worker.v2"
                        and initial["config"] == proposal["proposal_template"]["config"]
                        and initial["max_callbacks"] == 3,
                        "full-output inherited proposal worker differs",
                    )
                    require(
                        [row["task"] for row in initial["feedback"]] == tasks,
                        "full feedback task order differs",
                    )
                    require(
                        max(len(row["note"].encode("utf-8")) for row in initial["feedback"]) > 4096,
                        "full-output rehearsal failed to exceed the historical note ceiling",
                    )
                    measured_root = search / ("seed" if program == 0 else "iterations/0/screen")
                    for task_index, row in enumerate(initial["feedback"]):
                        note = decode(row["note"])
                        seal_root = measured_root / "tasks" / str(task_index) / "generation"
                        seal = decode(read(seal_root / "completed/0.json"))
                        measured = Answers.from_bytes(
                            read(seal_root / seal["attempt"] / "session/answers.json")
                        )
                        literal_answers = measured.to_record()["outputs"][0]["answers"]
                        require(
                            note["answers"]
                            == [
                                {"position": index, "text": text}
                                for index, text in enumerate(literal_answers)
                            ]
                            and note["omitted_answer_positions"] == 0
                            and note["omitted_partition_positions"] == 0
                            and note["omitted_score_positions"] == 0,
                            "P/C measured packet omitted/changed literal answer positions",
                        )
                elif "generation" in parts and "witness" in "/".join(parts):
                    program = 1 if parts[0] == "seed-witness" else 3
                    task = 0
                    active.update(
                        stage="generation",
                        program=program,
                        task=0,
                        expected_calls=GENERATION_CALLBACKS[program],
                    )
                    require(
                        initial["task"] == tasks[0], "witness did not use first ordered full task"
                    )
                    expected_copy = (
                        search / "seed-witness/agent"
                        if program == 1
                        else search / "iterations/0/witness/agent"
                    )
                    require(
                        dict(specification.mounts)["/agent"] == expected_copy,
                        "witness did not consume verified private source copy",
                    )
                else:
                    program = 0 if parts[0] == "seed" else 2
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
                            "common generation worker/task differs",
                        )
                        if program == 2:
                            require(
                                dict(specification.mounts)["/agent"]
                                == search / "iterations/0/agent",
                                "C common screen did not use verified private copy",
                            )
                    else:
                        command, index = initial["command"], initial["command"]["index"]
                        active.update(
                            stage=["partition", "score", "summary"][index],
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
                            "actual protected native command changed",
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
                    try:
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
                    except BaseException as error:
                        message = str(error)
                        for key in KEYS.values():
                            message = message.replace(key, "[synthetic key redacted]")
                        kind = value.get("type") if type(value) is dict else None
                        evidence["frame_failures"].append(
                            {
                                "owner": str(owner)[:4096],
                                "phase": phase,
                                "frame_kind": kind[:128] if type(kind) is str else "<not-text>",
                                "exception_type": type(error).__name__,
                                "message": message[:4096],
                                "frames": [
                                    {
                                        "file": row.filename[:1024],
                                        "line": row.lineno,
                                        "function": row.name[:256],
                                    }
                                    for row in traceback.extract_tb(error.__traceback__)[-20:]
                                ],
                            }
                        )
                        raise

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
                runtime["active"] = {"spec": specification, "limits": kwargs["limits"]}
                try:
                    result = actual_run(specification, **kwargs)
                finally:
                    runtime["active"] = None
                require(
                    result.exit_code == 0
                    and result.cleanup_status == "removed"
                    and result.image_id == specification.image_id
                    and re.fullmatch("[0-9a-f]{64}", result.container_id),
                    "worker or cleanup failed",
                )
                require(
                    result.container_id in owned_containers,
                    "actual worker ownership was not observed",
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
            interrupted = False
            original_proposal_run = candidate_improvement.run_candidate_improvement
            proposal_root = search / "iterations/0/proposal"

            def interrupt_after_counted_proposal(directory, **options):
                nonlocal interrupted
                value = original_proposal_run(directory, **options)
                if directory == proposal_root and not interrupted:
                    require(
                        value["status"] == "complete" and value["disposition"] == "materialized",
                        "counted proposal did not durably materialize",
                    )
                    interrupted = True
                    raise KeyboardInterrupt
                return value

            with (
                patch("http.client.HTTPSConnection", side_effect=Connection),
                patch("buddha.executor.run_container", side_effect=observed),
                patch.object(
                    source_launch.credentials, "key_environment", side_effect=observed_keys
                ),
            ):
                try:
                    with patch.object(
                        candidate_improvement,
                        "run_candidate_improvement",
                        side_effect=interrupt_after_counted_proposal,
                    ):
                        invoke(receipts["prefix"])
                except KeyboardInterrupt:
                    require(
                        interrupted and (proposal_root / "report.json").is_file(),
                        "interruption preceded durable counted proposal",
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
                    and len(evidence["workers"]) == 15
                    and len(evidence["sends"]) == 75,
                    "cancelled prefix or its work counts differ",
                )
                prefix = tree(search)
                prefix_funding = authority.summary()
                prefix_owners = {row["directory"]: row["run_id"] for row in prefix_funding["runs"]}
                require(
                    len(prefix_owners) == 15
                    and prefix_funding["operation_count"] == 75
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
                evidence["phases"].append({"phase": phase, "workers": 15, "new_replies": 75})
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
                        "workers": len(evidence["workers"]) - 15,
                        "new_replies": len(evidence["sends"]) - 75,
                    }
                )
            phase = "completed-evidence"
            require(
                len(evidence["workers"]) == len(seen) == 29
                and len(evidence["sends"]) == 154
                and len({row["container_id"] for row in evidence["workers"]}) == 29,
                "full concrete work schedule differs",
            )
            require(
                Counter(row["stage"] for row in evidence["sends"])
                == {"generation": 84, "proposal": 4, "partition": 6, "score": 60},
                "physical stage totals differ",
            )
            report_raw = read(search / "report.json")
            report = source_search.inspect_source_search(
                search, authorization=authority_path, expected_report_sha256=sha(report_raw)
            )
            require(
                [row["status"] for row in report["decisions"]] == ["admitted"]
                and [row["parent_id"] for row in report["decisions"]] == [agent_ids[0]]
                and [row["child_id"] for row in report["decisions"]] == [agent_ids[2]]
                and report["selection"]["selected_id"] == agent_ids[2]
                and len(report["screens"]) == 2
                and not report["failures"]
                and [row["status"] for row in report["witnesses"]] == ["passed", "passed"],
                "full current P/C and own-C further-child path differs",
            )
            for program, location, task_indices in (
                (0, search / "seed", range(3)),
                (2, search / "iterations/0/screen", range(3)),
                (1, search / "seed-witness", [0]),
                (3, search / "iterations/0/witness", [0]),
            ):
                for task in task_indices:
                    generation_root = (
                        location / "generation"
                        if program in {1, 3}
                        else location / "tasks" / str(task) / "generation"
                    )
                    seal = decode(read(generation_root / "completed/0.json"))
                    answers = Answers.from_bytes(
                        read(generation_root / seal["attempt"] / "session/answers.json")
                    )
                    positions = (
                        list(reversed(range(10)))
                        if program == 1
                        else list(range(1, 11))
                        if program == 2
                        else [*range(0, 11, 2), *range(1, 11, 2)][:10]
                        if program == 3
                        else list(range(10))
                    )
                    require(
                        answers.to_record()["outputs"][0]["answers"]
                        == [literal(program, task, index) for index in positions],
                        "actual generation C1/order differs",
                    )
            evidence["supplied_procedure_control"] = {
                "status": "exercised_if_all_assertions_pass",
                "model_authored": False,
                "task_code_change": "P sequential generation becomes C planning-plus-drafting",
                "improver_change": (
                    "C adds measured-utility selection/planning call "
                    "and uses returned plan in full-note wrapper"
                ),
                "used_further_child": agent_ids[3],
                "witnesses_are_counted_or_adopted": False,
            }
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
                len(funding["runs"]) == 29
                and all(not row["active"] for row in funding["runs"])
                and funding["authorization_id"] == terms["authorization_id"]
                and sum(len(row.operations) for row in histories)
                == funding["operation_count"]
                == 154
                and funding["spent_microusd"] == funding["committed_microusd"] == expected_charge
                and funding["reserved_microusd"] == 0,
                "original grant/owner accounting differs",
            )
            evidence["report"] = {"path": str(search / "report.json"), "sha256": sha(report_raw)}
            evidence["funding"] = funding
            phase = "completed-keyless-repeat"
            runtime["passive"] = True
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
            failure_type=type(error).__name__,
            failure_message=str(error)[:4096],
            failure_frames=[
                {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(error.__traceback__)[-20:]
            ],
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
                "workers": len(evidence["workers"]),
                "synthetic_replies": len(evidence["sends"]),
                "real_provider_calls": 0,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main(arguments())
