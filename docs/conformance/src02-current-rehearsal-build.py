"""UNEXECUTED DRAFT: build only a NEW unfunded current-source rehearsal bundle.

Requires independently reviewed driver/protocol/current source pins. Creates
literal data/components and a source map; no authority, key, model or worker.
All application imports below are trusted host modules, never candidate input.
"""

import argparse
import hashlib
import json
import os
import socket
import sqlite3
import stat
import subprocess  # nosec B404: only a denied non-Docker guard control
import sys
from pathlib import Path

SAFE_OS = {
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
}
OLD_SHA = "58201cb25ae027a24549f4153fcdf2bb82cdca8783c93cc687034cd5629bffa9"
SEED_SHA = "77cfa68f6b3c6996fd503e1ce6f7a964eb57abdb8bde98f6761de5f6e298ff4f"
PROPOSAL_INSTRUCTIONS_VERSION = "buddha.current-source-proposal-instructions.v1"
PROPOSAL_INSTRUCTIONS = (
    "Use the measured development feedback to propose substantive, evidence-grounded procedural "
    "changes to both generate and propose_improvement (or their actually used helpers). Preserve "
    "complete feedback, callable interfaces and all host/model/resource boundaries. Explain each "
    "proposed change in hypothesis without claiming success. Changes confined to prompt constants, "
    "names, comments or formatting do not meet this observation's aim."
)


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raw(path):
    info = path.lstat()
    require(
        stat.S_ISREG(info.st_mode)
        and not path.is_symlink()
        and info.st_nlink == 1
        and not getattr(info, "st_file_attributes", 0) & 0x400
        and info.st_size <= 256 * 1024**2,
        "bounded plain input required",
    )
    value = path.read_bytes()
    after = path.lstat()
    require(
        len(value) == info.st_size
        and all(
            getattr(info, name) == getattr(after, name)
            for name in ("st_dev", "st_ino", "st_size", "st_mtime_ns")
        ),
        "input changed during read",
    )
    return value


def path(value):
    require(
        value.is_absolute()
        and ".." not in value.parts
        and value.resolve(strict=False) == value
        and not str(value).startswith(("//", "\\\\")),
        "canonical local absolute path required",
    )
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
        prefix + number for prefix in ("COM", "LPT") for number in "123456789¹²³"
    }
    for name in value.parts[1:]:
        require(
            name == name.rstrip(" .")
            and name.split(".", 1)[0].rstrip(" .").upper() not in reserved
            and not any(char in '<>:"/\\|?*' or ord(char) < 32 for char in name),
            "filename alias rejected",
        )
    for parent in value.parents:
        info = parent.lstat()
        require(
            stat.S_ISDIR(info.st_mode)
            and not parent.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & 0x400,
            "plain existing parent required",
        )
    return value


def checked_write_target(value):
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
                stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            ):
                return None
        if str(target.resolve(strict=False)) != str(target):
            return None
        return target
    except (OSError, TypeError, ValueError):
        return None


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def main(args):
    for item in (
        args.repo,
        args.historical_proposal,
        args.directory,
        args.out,
        args.driver,
        args.protocol,
        args.review_criteria,
    ):
        path(item)
    source_map = args.out.with_name(args.out.stem + "-sources.json")
    path(source_map)
    require(
        not any(item.exists() for item in (args.directory, args.out, source_map)),
        "all outputs must be NEW",
    )
    protected = [
        args.repo,
        args.historical_proposal.parent,
        args.driver,
        args.protocol,
        args.review_criteria,
        Path(__file__).resolve(),
    ]
    require(
        not any(
            args.directory.is_relative_to(item) or item.is_relative_to(args.directory)
            for item in protected
        ),
        "bundle overlaps protected inputs",
    )
    require(
        not args.out.is_relative_to(args.directory)
        and not source_map.is_relative_to(args.directory),
        "receipt/map must be outside the bundle to avoid self-reference",
    )
    require(
        not any(
            target.is_relative_to(args.historical_proposal.parent)
            for target in (args.out, source_map)
        ),
        "new receipt/map overlaps original bundle",
    )
    historical_raw = raw(args.historical_proposal)
    require(
        sha(historical_raw) == OLD_SHA
        and sha(raw(args.driver)) == args.driver_sha256
        and sha(raw(args.protocol)) == args.protocol_sha256
        and sha(raw(args.review_criteria)) == args.review_criteria_sha256
        and sha(raw(Path(__file__).resolve())) == args.script_sha256,
        "caller original pins differ",
    )
    old_files = {
        item: sha(raw(item))
        for item in args.historical_proposal.parent.rglob("*")
        if item.is_file()
    }
    project = [
        p
        for folder in ("buddha", "agents", "tests", "docs/conformance")
        for p in (args.repo / folder).rglob("*.py")
        if "__pycache__" not in p.parts
    ]
    project += [
        args.repo / name for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt")
    ]
    before = {
        item: sha(raw(item))
        for item in [
            *project,
            args.driver,
            args.protocol,
            args.review_criteria,
            Path(__file__).resolve(),
        ]
    }
    # Read only explicitly permitted OS values, then delete all original names.
    ordinary = {name: os.environ[name] for name in list(os.environ) if name.upper() in SAFE_OS}
    for name in list(os.environ):
        del os.environ[name]
    os.environ.update(ordinary)
    sys.dont_write_bytecode = True

    def writable(value):
        if isinstance(value, int):
            return True
        target = checked_write_target(value)
        return target is not None and (
            target in {args.out, source_map} or target.is_relative_to(args.directory)
        )

    def audit(event, values):
        require(
            not (event.startswith("socket.") and event != "socket.gethostname")
            and event not in {"sqlite3.connect", "subprocess.Popen", "os.system"}
            and not event.startswith(("os.posix_spawn", "os.spawn", "os.exec")),
            "builder execution/network/SQL forbidden",
        )
        if event == "open":
            mode, flags = values[1], values[2]
            writing = isinstance(mode, str) and any(char in mode for char in "wax+")
            writing |= bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            require(not writing or writable(values[0]), "write outside NEW bundle/map/receipt")
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime"}:
            require(writable(values[0]), "mutation outside NEW outputs")
        if event in {"os.rename", "os.link", "os.symlink"}:
            raise RuntimeError("builder does not rename or link inputs")

    sys.addaudithook(audit)
    # Real guarded API probes, all before any authority or worker. These NEW
    # sibling canaries are never existing user paths. A wrong exception fails.
    outside_write = args.directory.with_name(args.directory.name + "-guard-outside-write")
    outside_sql = args.directory.with_name(args.directory.name + "-guard-outside.sqlite3")
    for canary in (outside_write, outside_sql):
        require(
            checked_write_target(canary) == canary
            and not canary.exists()
            and not canary.is_symlink()
            and canary not in {args.out, source_map}
            and canary not in before
            and canary not in old_files,
            "guard canary must be a NEW non-output sibling",
        )
    guard_controls = []

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
        print(json.dumps(guard_controls[-1], sort_keys=True), flush=True)

    def create_empty(target):
        with target.open("xb"):
            pass

    refused(
        "outside_write", lambda: create_empty(outside_write), "write outside NEW bundle/map/receipt"
    )
    refused(
        "traversal_write",
        lambda: create_empty(args.directory / ".." / outside_write.name),
        "write outside NEW bundle/map/receipt",
    )
    refused(
        "outside_sql",
        lambda: sqlite3.connect(str(outside_sql)),
        "builder execution/network/SQL forbidden",
    )
    refused(
        "non_docker_process",
        lambda: subprocess.Popen([sys.executable, "-c", "raise SystemExit(73)"]),
        "builder execution/network/SQL forbidden",
    )
    refused("socket_creation", lambda: socket.socket(), "builder execution/network/SQL forbidden")
    require(not args.directory.exists(), "negative controls changed the absent fixture")
    args.directory.mkdir()
    positive_parent = args.directory / "guard-control-future"
    positive = positive_parent / "contained.txt"
    positive_parent.mkdir()
    with positive.open("xb") as stream:
        stream.write(b"contained guard positive\n")
    require(
        positive.read_bytes() == b"contained guard positive\n", "contained write control differs"
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
    print(json.dumps(guard_controls[-1], sort_keys=True), flush=True)
    sys.path.insert(0, str(args.repo))
    from buddha import candidate_run, source_handoff, source_launch, source_search, source_seed
    from buddha.releases import Release, _json, prepare_selection

    def write(target, value):
        if target.is_relative_to(args.directory):
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            require(
                target in {args.out, source_map} and target.parent.is_dir(),
                "external output is not a prepared receipt/map",
            )
        with target.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())

    def remap(value):
        if type(value) is str:
            return value.replace(str(args.historical_proposal.parent), str(args.directory))
        if type(value) is list:
            return [remap(item) for item in value]
        if type(value) is dict:
            return {key: remap(item) for key, item in value.items()}
        return value

    old = json.loads(historical_raw)
    record = remap(old)
    # Copy immutable input bytes first; overwrite none.
    # Regenerate only the named recipes below.
    regenerate = {
        "proposal.json",
        "configuration-check.json",
        "inputs/composition.json",
        "inputs/improver-fragment.txt",
        "inputs/protocol.md",
        "inputs/intent.json",
        "inputs/proposal-template.json",
        "inputs/screen.json",
        "inputs/source.json",
        "inputs/split.json",
        "inputs/search-spec.json",
        "components/source-agent/candidate.py",
    }
    runner_paths = set()
    for section in (record["seed_screen"]["generation"], record["seed_screen"]["native"]):
        runner_paths.update(
            (Path(section["roots"]["runner"]) / relative).relative_to(args.directory).as_posix()
            for relative in section["selection"]["components"]["runner"]
        )
    for original in old_files:
        relative = original.relative_to(args.historical_proposal.parent)
        if relative.as_posix() not in regenerate | runner_paths:
            write(args.directory / relative, raw(original))
    prefix = raw(args.repo / "agents/frozen_seed.py")
    candidate = source_seed.compose_source_seed(prefix)
    require(
        sha(candidate) == SEED_SHA and len(candidate) == 13455,
        "current trusted seed2 composition differs",
    )
    write(args.directory / "components/source-agent/candidate.py", candidate)
    if (args.directory / "inputs/frozen_seed.py").exists():
        require(
            raw(args.directory / "inputs/frozen_seed.py") == prefix, "copied trusted prefix differs"
        )
    else:
        write(args.directory / "inputs/frozen_seed.py", prefix)
    write(args.directory / "inputs/improver-fragment.txt", source_seed.FRAGMENT.encode())
    write(
        args.directory / "inputs/composition.json",
        _json(
            {
                "format": "buddha.source-seed-composition.v2",
                "fragment_version": source_seed.FRAGMENT_VERSION,
                "candidate_sha256": sha(candidate),
                "fragment_sha256": sha(source_seed.FRAGMENT.encode()),
                "frozen_seed_sha256": sha(prefix),
                "separator_hex": "0a0a",
            }
        ),
    )
    screen = record["seed_screen"]
    original_generation_config = encoded(screen["generation"]["config"])
    original_native_settings = encoded(
        {key: value for key, value in screen["native"].items() if key not in {"roots", "selection"}}
    )
    original_proposal_config = dict(record["proposal_template"]["config"])
    record["proposal_template"]["config"] = dict(
        original_proposal_config, instructions=PROPOSAL_INSTRUCTIONS
    )
    require(
        {
            key: value
            for key, value in record["proposal_template"]["config"].items()
            if key != "instructions"
        }
        == {key: value for key, value in original_proposal_config.items() if key != "instructions"},
        "only prospective proposal instructions may change",
    )
    for name in ("generation", "native"):
        section = screen[name]
        names = (
            ["buddha/" + item + ".py" for item in candidate_run.RUNNER_FILES]
            if name == "generation"
            else list(section["selection"]["components"]["runner"])
        )
        for relative in names:
            write(Path(section["roots"]["runner"]) / relative, raw(args.repo / relative))
        section["selection"] = prepare_selection(
            Release.from_record(section["selection"]["release"]),
            {key: Path(value) for key, value in section["roots"].items()},
            capabilities=section["selection"]["capabilities"],
        ).to_record()
    record["format"] = "buddha.source-handoff.v3"
    record["mutation_witness"] = dict(source_search.MUTATION_WITNESS_POLICY)
    record["source_copy"] = dict(source_search.SOURCE_COPY_POLICY)
    record["spec"] = {
        "format": "buddha.source-search.v1",
        "iterations": 1,
        "method": "latest",
        "seed": 7,
        "max_active": 2,
    }
    require(
        screen["selected_ids"] == ["curated-0", "curated-47", "curated-97"],
        "selected task set differs",
    )
    require(
        record["requested_terms"] == {"budget_microusd": 25000000, "max_calls": 512},
        "synthetic rehearsal terms differ",
    )
    write(args.directory / "inputs/protocol.md", raw(args.protocol))
    write(args.directory / "inputs/review-criteria.json", raw(args.review_criteria))
    instruction_commitment = {
        "format": PROPOSAL_INSTRUCTIONS_VERSION,
        "text": PROPOSAL_INSTRUCTIONS,
        "sha256": sha(PROPOSAL_INSTRUCTIONS.encode("utf-8")),
    }
    require(
        encoded(screen["generation"]["config"]) == original_generation_config
        and encoded(
            {
                key: value
                for key, value in screen["native"].items()
                if key not in {"roots", "selection"}
            }
        )
        == original_native_settings,
        "generation or official native configuration changed",
    )
    write(args.directory / "inputs/proposal-template.json", _json(record["proposal_template"]))
    write(
        args.directory / "inputs/intent.json",
        _json(
            {
                "format": "buddha.current-source-rehearsal-intent.v2",
                "proposal_instructions": instruction_commitment,
                "scope": (
                    "supplied-response engineering rehearsal only; unallocated, no model authorship"
                ),
                "maximum_owner_slots": 29,
                "task_ids": screen["selected_ids"],
                "iterations": 1,
                "source_copy": record["source_copy"],
                "mutation_witness": record["mutation_witness"],
            }
        ),
    )
    for name, value in (
        ("screen", screen),
        ("source", screen["source"]),
        ("split", screen["split"]),
        ("search-spec", record["spec"]),
    ):
        write(args.directory / ("inputs/" + name + ".json"), _json(value))
    controls = list(
        dict.fromkeys(
            [
                *source_launch._sources(),
                args.repo / "buddha/source_seed.py",
                args.repo / "agents/frozen_seed.py",
                args.protocol,
                args.review_criteria,
                Path(__file__).resolve(),
                args.driver,
                *(item for item in (args.directory / "inputs").rglob("*") if item.is_file()),
                Path(screen["generation"]["runtime"]["path"]),
            ]
        )
    )
    record["source_sha256"] = {str(item): sha(raw(item)) for item in controls}
    proposal = args.directory / "proposal.json"
    write(proposal, _json(record))
    checked = source_handoff.check_source_handoff(proposal, expected_sha256=sha(raw(proposal)))
    require(
        checked["format"] == "buddha.source-handoff-check.v3"
        and checked["planned"]["maximum_stage_owners"] == 29
        and checked["funding"]["status"] == "unallocated",
        "new current configuration did not pass actual passive checker",
    )
    write(args.directory / "configuration-check.json", _json(checked))
    require(
        all(sha(raw(item)) == digest for item, digest in old_files.items())
        and all(sha(raw(item)) == digest for item, digest in before.items()),
        "protected input changed",
    )
    pins = {
        str(item): sha(raw(item))
        for item in dict.fromkeys(
            [
                *project,
                *controls,
                proposal,
                *(item for item in args.directory.rglob("*") if item.is_file()),
            ]
        )
    }
    write(source_map, _json(pins))
    write(
        args.out,
        _json(
            {
                "format": "buddha.current-source-rehearsal-build.v2",
                "status": "unfunded_configuration_checked",
                "guard_controls": guard_controls,
                "proposal_instructions": instruction_commitment,
                "proposal": {"path": str(proposal), "sha256": sha(raw(proposal))},
                "sources": {
                    "path": str(source_map),
                    "sha256": sha(raw(source_map)),
                    "count": len(pins),
                },
                "driver": {"path": str(args.driver), "sha256": args.driver_sha256},
                "original_files_unchanged": len(old_files),
                "current_inputs_unchanged": len(before),
                "authority_created": False,
                "provider_calls": 0,
                "workers": 0,
            }
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "repo",
        "historical-proposal",
        "directory",
        "out",
        "driver",
        "protocol",
        "review-criteria",
    ):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("driver-sha256", "protocol-sha256", "review-criteria-sha256", "script-sha256"):
        parser.add_argument("--" + name, required=True)
    main(parser.parse_args())
