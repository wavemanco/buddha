"""Validate five inert report paths before omitting only CI's long test suite."""

import json
import os
import re
import shutil
import stat
import subprocess  # nosec B404
from pathlib import Path
from typing import NoReturn

REQUEST_FORMAT = "buddha.fresh-request-observations-delivery.v1"
CONFINEMENT_FORMAT = "buddha.fresh-confinement-observations-delivery.v1"
REPORTS = {
    "docs/conformance/fresh-request-observations-delivery.json": REQUEST_FORMAT,
    "docs/conformance/fresh-confinement-observations-delivery.json": CONFINEMENT_FORMAT,
}
LEAVES = frozenset(REPORTS) | {
    "docs/PLAN.md",
    "docs/FRESH-REQUEST-OBSERVATIONS.md",
    "docs/FRESH-CONFINEMENT-OBSERVATIONS.md",
}
MAX_BYTES = 4 * 1024**2


class InvalidLeaf(ValueError):
    """A qualifying leaf document failed its actual content validation."""


def _git(root: Path, *args: str) -> bytes:
    # Only fixed read-only Git commands and validated SHA arguments are supplied.
    executable = shutil.which("git")
    if executable is None:
        raise OSError("Git is unavailable")
    value = subprocess.run(  # nosec B603
        [executable, "-C", str(root), *args],
        check=True,
        capture_output=True,
        timeout=15,
    ).stdout
    if len(value) > MAX_BYTES:
        raise ValueError("Git metadata exceeds the leaf-document bound")
    return value


def _changed(raw: bytes) -> list[str] | None:
    fields = raw.split(b"\0")
    if fields[-1] or len(fields) % 2 != 1 or len(fields) == 1:
        return None
    paths = []
    for header, name in zip(fields[0:-1:2], fields[1:-1:2], strict=True):
        parts = header.split()
        if len(parts) != 5:
            return None
        old_mode, new_mode, old_sha, new_sha, status = parts
        if (
            new_mode != b"100644"
            or status not in (b"A", b"M")
            or old_mode != (b":000000" if status == b"A" else b":100644")
            or not re.fullmatch(b"[0-9a-f]{40}", old_sha)
            or not re.fullmatch(b"[0-9a-f]{40}", new_sha)
            or new_sha == b"0" * 40
            or (status == b"A") != (old_sha == b"0" * 40)
        ):
            return None
        path = name.decode("utf-8")
        if path not in LEAVES or path in paths:
            return None
        paths.append(path)
    return paths


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in values:
        if key in result:
            raise InvalidLeaf("duplicate JSON field")
        result[key] = value
    return result


def _constant(_value: str) -> NoReturn:
    raise InvalidLeaf("nonfinite JSON value")


def _validate(root: Path, paths: list[str]) -> None:
    for name in paths:
        path = root / name
        if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > MAX_BYTES:
            raise InvalidLeaf("invalid leaf file")
        try:
            text = path.read_bytes().decode("utf-8-sig")
            if name in REPORTS:
                value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
                if type(value) is not dict or value.get("format") != REPORTS[name]:
                    raise InvalidLeaf("unexpected leaf report format")
        except (UnicodeError, ValueError, RecursionError) as error:
            raise InvalidLeaf("invalid leaf content") from error


def leaf_documents(root: Path, event_name: str, event: object, merge_sha: str) -> bool:
    """Fail closed unless a real cumulative PR merge changes only validated leaves."""
    try:
        if event_name != "pull_request" or type(event) is not dict:
            return False
        pr = event.get("pull_request")
        if type(pr) is not dict:
            return False
        base, head = pr.get("base"), pr.get("head")
        if type(base) is not dict or type(head) is not dict:
            return False
        base_sha, head_sha = base.get("sha"), head.get("sha")
        if type(base_sha) is not str or type(head_sha) is not str or type(merge_sha) is not str:
            return False
        if any(
            not re.fullmatch("[0-9a-f]{40}", value) for value in (base_sha, head_sha, merge_sha)
        ):
            return False
        if _git(root, "rev-parse", "HEAD").decode().strip() != merge_sha:
            return False
        if _git(root, "show", "-s", "--format=%P", "HEAD").decode().split() != [base_sha, head_sha]:
            return False
        paths = _changed(
            _git(
                root,
                "diff",
                "--raw",
                "-z",
                "--no-abbrev",
                "--no-renames",
                "--no-ext-diff",
                "--no-textconv",
                base_sha,
                merge_sha,
                "--",
            )
        )
        if not paths:
            return False
        _validate(root, paths)
        try:
            _git(root, "diff", "--check", "--no-ext-diff", base_sha, merge_sha, "--")
        except subprocess.CalledProcessError as error:
            raise InvalidLeaf("leaf whitespace errors") from error
        return True
    except InvalidLeaf:
        raise
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        return False


def main() -> int:
    try:
        event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        event = (
            json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
            if event_name == "pull_request"
            else None
        )
        leaf = leaf_documents(Path.cwd(), event_name, event, os.environ.get("GITHUB_SHA", ""))
    except InvalidLeaf:
        print('{"format":"buddha.ci-leaf-docs.v1","status":"invalid_leaf_document"}')
        return 1
    except (KeyError, OSError, ValueError, RecursionError):
        leaf = False
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write(f"leaf_docs={str(leaf).lower()}\n")
    print(
        json.dumps(
            {"format": "buddha.ci-leaf-docs.v1", "mode": "leaf_documents" if leaf else "full"}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
