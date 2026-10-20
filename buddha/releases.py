"""Read-only benchmark release selection, independent of evaluator/scoring code.

Inventories establish consistency, not source authenticity, dependency closure,
executable compatibility or paid authority. No selected source is imported.
"""

import hashlib
import json
import ntpath
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import urlsplit

MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_FILES = 100_000
MAX_FILE_BYTES = 8 * 1024**3
MAX_TREE_BYTES = 64 * 1024**3
ROLES = frozenset({"official", "environment", "runner", "host", "agent"})


class ReleaseError(ValueError):
    """Release data or selected files violate the supported offline contract."""


def _json(value: object) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("too large")
        return raw
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ReleaseError("release data must be bounded finite JSON") from None


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    if len(dict(items)) != len(items):
        raise ReleaseError("duplicate release JSON key")
    return dict(items)


def _load(raw: bytes) -> dict[str, object]:
    try:
        if type(raw) is not bytes or len(raw) > MAX_JSON_BYTES:
            raise ValueError("invalid bytes")
        value: object = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
        _json(value)
        return _object(value)
    except (ValueError, UnicodeError, RecursionError):
        raise ReleaseError("invalid bounded release JSON") from None


def _object(value: object, keys: set[str] | None = None) -> dict[str, object]:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise ReleaseError("expected a release object")
    if keys is not None and set(value) != keys:
        raise ReleaseError("missing or unexpected release fields")
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if type(value) is not str or not value.strip() or len(value) > 4096 or "\x00" in value:
        raise ReleaseError("expected bounded nonblank release text")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ReleaseError("release text must be valid UTF-8") from None
    return value


def _digest(value: object) -> str:
    if type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value):
        raise ReleaseError("expected a SHA-256 digest")
    return value


def _path(value: object) -> str:
    text = _text(value)
    parts = text.split("/")
    for part in parts:
        if (
            not part
            or part in {".", ".."}
            or part[-1:] in {".", " "}
            or any(ord(char) < 32 or char in '\\:<>"|?*' for char in part)
            or ntpath.isreserved(part)
        ):
            raise ReleaseError("paths must be portable relative file paths")
    return text


def _paths(values: object) -> list[str]:
    if type(values) is not list or not values or len(values) > MAX_FILES:
        raise ReleaseError("expected a bounded nonempty path list")
    paths = [_path(value) for value in values]
    folded = {path.casefold() for path in paths}
    if len(folded) != len(paths) or any(
        str(parent).casefold() in folded
        for path in paths
        for parent in PurePosixPath(path).parents
        if str(parent) != "."
    ):
        raise ReleaseError("file paths have aliases or ancestor collisions")
    prefixes: dict[str, str] = {}
    for path in paths:
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            if prefixes.setdefault(prefix.casefold(), prefix) != prefix:
                raise ReleaseError("directory paths have portable case aliases")
    return paths


def _inventory(value: object) -> dict[str, object]:
    record = _object(value)
    _paths(list(record))
    for digest in record.values():
        _digest(digest)
    return record


def _release(value: object) -> dict[str, object]:
    record = _object(
        value,
        {
            "format",
            "benchmark",
            "release",
            "upstream",
            "source",
            "dependency_lock",
            "task",
            "commands",
            "artifacts",
            "requires",
        },
    )
    if record["format"] != "buddha.benchmark-release.v1":
        raise ReleaseError("unsupported release format")
    _text(record["benchmark"])
    _text(record["release"])
    upstream = _object(record["upstream"], {"url", "revision"})
    try:
        url = urlsplit(_text(upstream["url"]))
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("invalid URL")
    except ValueError:
        raise ReleaseError(
            "upstream provenance requires an HTTPS URL without credentials"
        ) from None
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", _text(upstream["revision"])):
        raise ReleaseError("upstream revision must be a pinned Git object digest")
    source = _inventory(record["source"])
    if _path(record["dependency_lock"]) not in source:
        raise ReleaseError("dependency lock is absent from sealed official source")
    task = _object(
        record["task"], {"dataset", "id_field", "prompt_field", "answers_field", "count"}
    )
    if _path(task["dataset"]) not in source:
        raise ReleaseError("dataset is absent from sealed official source")
    names = [_text(task[key]) for key in ("id_field", "prompt_field", "answers_field")]
    if len(set(names)) != len(names):
        raise ReleaseError("task field mappings must be distinct literal JSON members")
    if type(task["count"]) is not int or not 1 <= task["count"] <= 1000:
        raise ReleaseError("answer count must be an integer from 1 to 1000")
    commands = record["commands"]
    if type(commands) is not list or not 1 <= len(commands) <= 32:
        raise ReleaseError("release requires a bounded command list")
    for raw in commands:
        command = _object(raw, {"module", "argv"})
        module = _text(command["module"])
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module, flags=re.ASCII):
            raise ReleaseError("entry point must be a Python module name")
        stem = module.replace(".", "/")
        if not any(path in source for path in (stem + ".py", stem + "/__main__.py")):
            raise ReleaseError("entry module is absent from sealed official source")
        argv = command["argv"]
        if type(argv) is not list or len(argv) > 128:
            raise ReleaseError("command arguments must be a bounded data list")
        for argument in argv:
            argument_text = _text(argument)
            if ("{" in argument_text or "}" in argument_text) and argument_text != "{artifacts}":
                raise ReleaseError("unsupported command placeholder; use whole-token {artifacts}")
    artifacts = _object(record["artifacts"], {"answers", "results", "summary"})
    results = _paths(artifacts["results"])
    _paths([artifacts["answers"], *results, artifacts["summary"]])
    requires = record["requires"]
    if type(requires) is not list or not requires or len(requires) > 128:
        raise ReleaseError("release must declare bounded required capabilities")
    if len({_text(item) for item in requires}) != len(requires):
        raise ReleaseError("duplicate release capability")
    return record


@dataclass(frozen=True)
class Release:
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _json(_release(_load(self.data))))

    @classmethod
    def from_record(cls, record: object) -> "Release":
        return cls(_json(record))

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Release":
        return cls(raw)

    def to_record(self) -> dict[str, object]:
        return _load(self.data)

    def to_bytes(self) -> bytes:
        return self.data

    def fingerprint(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def _information(path: Path) -> os.stat_result:
    information = path.lstat()
    if stat.S_ISLNK(information.st_mode) or (
        getattr(information, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise ReleaseError("component paths must not contain links or reparse points")
    return information


def _root(path: Path) -> Path:
    if not isinstance(path, Path):
        raise ReleaseError("component root must be a Path")
    absolute = path.absolute()
    for part in (absolute, *absolute.parents):
        _information(part)
    if not absolute.is_dir():
        raise ReleaseError("component root must be an existing directory")
    return absolute.resolve()


def _walk_error(error: OSError) -> None:
    raise error


def _signature(information: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        information.st_dev,
        information.st_ino,
        information.st_size,
        information.st_mtime_ns,
        information.st_ctime_ns,
    )


def inventory(root: Path) -> dict[str, str]:
    """Hash every regular file; never follow links or ignore nested dependencies."""
    try:
        directory = _root(root)
        result: dict[str, str] = {}
        total = 0
        entries = 0
        directories = {directory: _signature(_information(directory))}
        for parent, folders, files in directory.walk(on_error=_walk_error):
            for path in (parent / name for name in (*folders, *files)):
                entries += 1
                if entries > MAX_FILES:
                    raise ReleaseError("component entry limit exceeded")
                name = _path(path.relative_to(directory).as_posix())
                information = _information(path)
                if stat.S_ISDIR(information.st_mode):
                    directories[path] = _signature(information)
                    continue
                if not stat.S_ISREG(information.st_mode) or information.st_nlink != 1:
                    raise ReleaseError("component files must be regular without hard-link aliases")
                total += information.st_size
                if information.st_size > MAX_FILE_BYTES or total > MAX_TREE_BYTES:
                    raise ReleaseError("component byte limit exceeded")
                digest = hashlib.sha256()
                read = 0
                with path.open("rb") as stream:
                    while block := stream.read(min(1024 * 1024, information.st_size - read + 1)):
                        read += len(block)
                        if read > information.st_size:
                            raise ReleaseError("component grew during inventory")
                        digest.update(block)
                    # Windows Python 3.13 can report different ctime via fstat/lstat.
                    # Compare open identity/content metadata; full path checks retain ctime.
                    if _signature(os.fstat(stream.fileno()))[:4] != _signature(information)[:4]:
                        raise ReleaseError("opened component differs from inventoried file")
                if read != information.st_size or _signature(_information(path)) != _signature(
                    information
                ):
                    raise ReleaseError("component changed during inventory")
                result[name] = digest.hexdigest()
        if any(_signature(_information(path)) != before for path, before in directories.items()):
            raise ReleaseError("component directory changed during inventory")
        _inventory(result)
        return dict(sorted(result.items()))
    except OSError:
        raise ReleaseError("component inventory could not be read") from None


def _roots(roots: Mapping[str, Path]) -> dict[str, Path]:
    if not isinstance(roots, Mapping) or set(roots) != ROLES:
        raise ReleaseError("exactly official/environment/runner/host/agent roots are required")
    try:
        paths = {name: _root(path) for name, path in roots.items()}
    except OSError:
        raise ReleaseError("component root could not be read") from None
    if any(
        first.is_relative_to(second)
        for a, first in paths.items()
        for b, second in paths.items()
        if a != b
    ):
        raise ReleaseError("selected component roots must not overlap")
    return paths


@dataclass(frozen=True)
class Selection:
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        record = _object(_load(self.data), {"format", "release", "components", "capabilities"})
        if record["format"] != "buddha.release-selection.v1":
            raise ReleaseError("unsupported release selection")
        release = _release(record["release"])
        components = _object(record["components"], set(ROLES))
        for component in components.values():
            _inventory(component)
        if components["official"] != release["source"]:
            raise ReleaseError("selected official source differs from the release")
        capabilities = _object(record["capabilities"], set(cast(list[str], release["requires"])))
        host = _object(components["host"])
        if any(_path(path) not in host for path in capabilities.values()):
            raise ReleaseError("capability profile is absent from selected host files")
        object.__setattr__(self, "data", _json(record))

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Selection":
        return cls(raw)

    def to_record(self) -> dict[str, object]:
        return _load(self.data)

    def to_bytes(self) -> bytes:
        return self.data

    def fingerprint(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def release_sha256(self) -> str:
        return Release.from_record(self.to_record()["release"]).fingerprint()

    @property
    def agent_sha256(self) -> str:
        return hashlib.sha256(_json(_object(self.to_record()["components"])["agent"])).hexdigest()


def prepare_selection(
    release: Release, roots: Mapping[str, Path], *, capabilities: Mapping[str, str]
) -> Selection:
    """Validate configuration and real selected files, without executing or authorizing them."""
    if not isinstance(release, Release) or not isinstance(capabilities, Mapping):
        raise ReleaseError("selection requires a release and host capability mapping")
    record = release.to_record()
    required = cast(list[str], record["requires"])
    if any(name not in capabilities for name in required):
        raise ReleaseError("required release capability is unsupported")
    selected = {name: _path(capabilities[name]) for name in required}
    components = {name: inventory(path) for name, path in _roots(roots).items()}
    return Selection(
        _json(
            {
                "format": "buddha.release-selection.v1",
                "release": record,
                "components": components,
                "capabilities": selected,
            }
        )
    )


def verify_selection(
    selection: Selection, roots: Mapping[str, Path], *, expected_sha256: str
) -> str:
    """Compare against the owner's frozen identity and re-read every selected component."""
    if not isinstance(selection, Selection) or selection.fingerprint() != _digest(expected_sha256):
        raise ReleaseError("selection differs from its frozen owner identity")
    record = selection.to_record()
    actual = {name: inventory(path) for name, path in _roots(roots).items()}
    if actual != record["components"]:
        raise ReleaseError("selected component inventory changed")
    return selection.fingerprint()
