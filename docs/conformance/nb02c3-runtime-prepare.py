"""Prepare/audit the separately identified minimal Linux native-evaluation image.

Download uses only hash-pinned binary distributions. Audit reads installed files;
neither mode invokes a model. See nb02c3-runtime.md before running this helper.
"""

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import subprocess
import sys
import tomllib
import urllib.request
import zipfile
from email.parser import BytesParser
from pathlib import Path

BASE = "python@sha256:3121f8b0804aa3698ab750d9a39ea4a42657a385c9b133722b915e55c51551a6"
ANYIO_HASH = "9f505dda5ac9f0c8309b5e8bd445a8c2bf7246f3ce950121e45ea15bc41d1494"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def download(root):
    repository = Path(__file__).resolve().parents[2]
    source = repository / "docs/conformance/nb02-reference-requirements.txt"
    root.mkdir(parents=True, exist_ok=True)
    requirements = root / "requirements.txt"
    original = source.read_text(encoding="utf-8")
    lines = original.splitlines()
    matching = [i for i, line in enumerate(lines) if line.startswith("anyio==")]
    if len(matching) != 1 or not lines[matching[0]].startswith("anyio==4.10.0 "):
        raise RuntimeError("original oracle requirements changed")
    lines[matching[0]] = f"anyio==4.14.2 --hash=sha256:{ANYIO_HASH}"
    requirements.write_text("\n".join(lines) + "\n", encoding="utf-8")
    wheelhouse = root / "wheels"
    wheelhouse.mkdir(exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--quiet",
        "--disable-pip-version-check",
        "--no-input",
        "--no-cache-dir",
        "--index-url=https://pypi.org/simple",
        "--only-binary=:all:",
        "--no-deps",
        "--require-hashes",
        "--python-version=3.13",
        "--implementation=cp",
        "--abi=cp313",
        "--timeout=15",
        "--retries=1",
        "--dest=" + str(wheelhouse),
        "-r",
        str(requirements),
    ]
    for minor in range(36, 16, -1):
        command.append(f"--platform=manylinux_2_{minor}_x86_64")
    command += ["--platform=manylinux2014_x86_64", "--platform=linux_x86_64"]
    subprocess.run(command, check=True, timeout=300)
    upstream_lock = repository / (
        "runs/references/noveltybench-conformance/64a23be6b18ec1dacc298830aab276061b6e143c/uv.lock"
    )
    lock = tomllib.loads(upstream_lock.read_text(encoding="utf-8"))
    locked_wheels = {
        item["url"].rsplit("/", 1)[-1]: item
        for package in lock["package"]
        for item in package.get("wheels", [])
    }
    with urllib.request.urlopen("https://pypi.org/pypi/anyio/4.14.2/json", timeout=15) as reply:
        overlay = json.load(reply)
    for item in overlay["urls"]:
        locked_wheels[item["filename"]] = {
            "url": item["url"],
            "hash": "sha256:" + item["digests"]["sha256"],
        }
    packages = []
    for wheel in sorted(wheelhouse.glob("*.whl")):
        provenance = locked_wheels[wheel.name]
        if provenance["hash"] != "sha256:" + digest(wheel):
            raise RuntimeError("wheel differs from its upstream/overlay source seal")
        with zipfile.ZipFile(wheel) as archive:
            metadata_name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
            metadata = BytesParser().parsebytes(archive.read(metadata_name))
            licenses = []
            for name in archive.namelist():
                relative = name.lower()
                if ".dist-info/" not in relative or not any(
                    word in relative for word in ("license", "licence", "copying", "notice")
                ):
                    continue
                raw = archive.read(name)
                licenses.append(
                    {
                        "path": name,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw),
                        "gnu_notice": any(
                            token in raw.lower()
                            for token in (b"gnu general public", b"gnu lesser", b"gcc runtime")
                        ),
                        "mpl_notice": b"mozilla public" in raw.lower(),
                    }
                )
                target = root / "licenses" / wheel.name / name
                if not target.resolve().is_relative_to((root / "licenses").resolve()):
                    raise RuntimeError("unsafe wheel license path")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            packages.append(
                {
                    "name": str(metadata["Name"]),
                    "version": str(metadata["Version"]),
                    "wheel": wheel.name,
                    "sha256": digest(wheel),
                    "source_url": provenance["url"],
                    "bytes": wheel.stat().st_size,
                    "license_expression": str(metadata.get("License-Expression") or ""),
                    "license_summary": str(metadata.get("License") or "")[:300],
                    "license_classifiers": [
                        item
                        for item in metadata.get_all("Classifier", [])
                        if item.startswith("License ::")
                    ],
                    "requires_dist": metadata.get_all("Requires-Dist", []),
                    "license_files": licenses,
                }
            )
    result = {
        "format": "buddha.review.nb02c3-linux-wheelhouse.v1",
        "base": BASE,
        "target": "CPython 3.13 / Linux amd64 / glibc <=2.36",
        "original_requirements_sha256": digest(source),
        "upstream_lock_sha256": digest(upstream_lock),
        "derived_requirements_sha256": digest(requirements),
        "only_version_override": {"anyio": ["4.10.0", "4.14.2"]},
        "command": command,
        "packages": packages,
    }
    save(root / "wheelhouse.json", result)
    print(json.dumps({"wheel_count": len(packages), "manifest": str(root / "wheelhouse.json")}))


def collect_audit():
    """Return the measured installed environment; raise on failed RECORD/tree checks."""
    root = Path(sys.prefix).resolve()
    distributions = []
    owned = set()
    for dist in sorted(importlib.metadata.distributions(), key=lambda item: item.metadata["Name"]):
        record = dist.read_text("RECORD")
        if record is None:
            raise RuntimeError("installed distribution lacks RECORD")
        files = []
        for name, expected, size in csv.reader(io.StringIO(record)):
            path = Path(dist.locate_file(name)).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise RuntimeError("installed RECORD path is unavailable or outside the venv")
            actual = digest(path)
            if expected:
                algorithm, encoded = expected.split("=", 1)
                if (
                    algorithm != "sha256"
                    or base64.urlsafe_b64encode(bytes.fromhex(actual)).rstrip(b"=").decode()
                    != encoded
                ):
                    raise RuntimeError("installed RECORD hash mismatch")
            if size and path.stat().st_size != int(size):
                raise RuntimeError("installed RECORD size mismatch")
            relative = path.relative_to(root).as_posix()
            owned.add(relative)
            files.append(
                {"path": relative, "sha256": actual, "record_hash_present": bool(expected)}
            )
        distributions.append(
            {"name": dist.metadata["Name"], "version": dist.version, "files": files}
        )
    inventory = {}
    unowned = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            resolved = path.resolve()
            if not (
                resolved.is_relative_to(root) or resolved.is_relative_to(Path("/usr/local/bin"))
            ):
                raise RuntimeError("unexpected venv link target")
            inventory[relative] = {"symlink": target, "target_is_directory": resolved.is_dir()}
            if resolved.is_file():
                inventory[relative]["target_sha256"] = digest(resolved)
        elif path.is_file():
            inventory[relative] = {"sha256": digest(path), "bytes": path.stat().st_size}
            if "/site-packages/" in relative and relative not in owned:
                unowned.append(relative)
    if unowned:
        raise RuntimeError("unowned files in active site-packages")
    return {
        "format": "buddha.review.nb02c3-installed-runtime.v1",
        "python": sys.version,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "os_release": Path("/etc/os-release").read_text(encoding="utf-8"),
        "base": BASE,
        "distributions": distributions,
        "inventory": inventory,
        "unowned_site_packages": unowned,
    }


def audit():
    print(json.dumps(collect_audit(), sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("download", "audit"))
    parser.add_argument("--directory", type=Path, default=Path("runs/reference-linux-nb02c3"))
    args = parser.parse_args()
    if args.mode == "download":
        download(args.directory.resolve())
    else:
        audit()
