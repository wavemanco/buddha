"""Seal/download the full locked Linux partition closure; never install or run it.

The read-only check and bounded preparation commands are documented in
nb02c3b-runtime-review.md. The separately sealed C3A inputs remain unchanged.
"""

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import tarfile
import tempfile
import time
import tomllib
import unittest
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

REPOSITORY = Path(__file__).resolve().parents[2]
DOCS = REPOSITORY / "docs/conformance"
REFERENCE = REPOSITORY / (
    "runs/references/noveltybench-conformance/64a23be6b18ec1dacc298830aab276061b6e143c"
)
SEALS = {
    REFERENCE / "uv.lock": "ff6d5b15b77e4ca46a33604586eb7d99666d2802752ab962af9baa2924a50758",
    REFERENCE
    / "pyproject.toml": "4cc029019f51ef29b58d6dc861eb4ec8643c49e1855c471989e7957836dbc993",
    DOCS / "nb02c3-runtime-wheels.json": (
        "5d82d44433b13bd8444b88ea3d90d5e9dcbe6600d05195a90f8cd8629c9bfd0d"
    ),
    DOCS / "nb02c3-runtime-requirements.txt": (
        "afaf07a9bac1d73a5ef729de4a17815acb7082caaa761c9af18fca7a811c1b2d"
    ),
}
ROOTS = {"torch": "2.7.1", "transformers": "4.56.1", "sacrebleu": "2.5.1", "rouge-score": "0.1.2"}
TARGET = {
    "implementation_name": "cpython",
    "implementation_version": "3.13.12",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "platform_release": "",
    "platform_system": "Linux",
    "platform_version": "",
    "python_full_version": "3.13.12",
    "platform_python_implementation": "CPython",
    "python_version": "3.13",
    "sys_platform": "linux",
    "extra": "",
}
REQUIREMENTS = DOCS / "nb02c3b-runtime-requirements.txt"
MANIFEST = DOCS / "nb02c3b-runtime-wheels.json"
ADVISORIES = DOCS / "nb02c3b-runtime-advisories.json"
DEFAULT_DIRECTORY = REPOSITORY / "runs/reference-linux-nb02c3b"
MAX_METADATA = 8 * 1024 * 1024
MAX_NOTICE = 32 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify(path, expected, size=None):
    if not path.is_file() or path.is_symlink() or digest(path) != expected:
        raise ValueError("source/artifact SHA256 mismatch: " + str(path))
    if size is not None and path.stat().st_size != size:
        raise ValueError("artifact size mismatch: " + str(path))


def tags():
    platforms = [f"manylinux_2_{minor}_x86_64" for minor in range(36, 4, -1)]
    platforms += ["manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"]
    return list(cpython_tags((3, 13), ["cp313"], platforms)) + list(
        compatible_tags((3, 13), "cp313", platforms)
    )


def source_url(url, host="files.pythonhosted.org"):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != host or parsed.query or parsed.fragment:
        raise ValueError("unreviewed artifact/metadata source")
    return url


def plan():
    for path, expected in SEALS.items():
        verify(path, expected)
    lock = tomllib.loads((REFERENCE / "uv.lock").read_text(encoding="utf-8"))
    packages = {canonicalize_name(item["name"]): item for item in lock["package"]}
    if len(packages) != len(lock["package"]) or lock["requires-python"] != ">=3.11":
        raise ValueError("unreviewed lock shape")
    selected, pending = set(), list(ROOTS)
    edges = {}
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        selected.add(name)
        item = packages[name]
        if item["source"] != {"registry": "https://pypi.org/simple"}:
            raise ValueError("unreviewed package registry")
        dependencies = []
        for dependency in item.get("dependencies", []):
            if dependency.get("marker") and not Marker(dependency["marker"]).evaluate(TARGET):
                continue
            child = canonicalize_name(dependency["name"])
            if dependency.get("version", packages[child]["version"]) != packages[child]["version"]:
                raise ValueError("ambiguous locked dependency version")
            dependencies.append(child)
        edges[name] = sorted(dependencies)
        pending.extend(dependencies)
    if len(selected) != 51 or any(
        packages[name]["version"] != value for name, value in ROOTS.items()
    ):
        raise ValueError("partition closure differs from reviewed source")
    baseline = json.loads((DOCS / "nb02c3-runtime-wheels.json").read_text(encoding="utf-8"))
    base = {canonicalize_name(item["name"]): item for item in baseline["packages"]}
    if len(base) != 28 or base["anyio"]["version"] != "4.14.2":
        raise ValueError("C3A baseline differs")
    ranking = {tag: index for index, tag in enumerate(tags())}
    result = []
    for name in sorted(selected | base.keys()):
        item = packages[name]
        if name in base:
            previous = base[name]
            artifact = {
                "url": previous["source_url"],
                "hash": "sha256:" + previous["sha256"],
                "size": previous["bytes"],
            }
            version = previous["version"]
            if name != "anyio" and version != item["version"]:
                raise ValueError("undeclared baseline version override")
            if name != "anyio" and artifact not in item.get("wheels", []):
                raise ValueError("baseline artifact differs from upstream lock")
        else:
            version = item["version"]
            candidates = []
            for wheel in item.get("wheels", []):
                filename = wheel["url"].rsplit("/", 1)[-1]
                wheel_name, wheel_version, _, wheel_tags = parse_wheel_filename(filename)
                if wheel_name != name or str(wheel_version) != version:
                    raise ValueError("lock wheel name/version mismatch")
                match = [ranking[tag] for tag in wheel_tags if tag in ranking]
                if match:
                    candidates.append((min(match), filename, wheel))
            if candidates:
                artifact = min(candidates)[2]
            elif name == "rouge-score":
                artifact = item["sdist"]
            else:
                raise ValueError("no reviewed compatible wheel: " + name)
        url = source_url(artifact["url"])
        filename = url.rsplit("/", 1)[-1]
        result.append(
            {
                "name": name,
                "version": version,
                "filename": filename,
                "kind": "wheel" if filename.endswith(".whl") else "sdist",
                "sha256": artifact["hash"].removeprefix("sha256:"),
                "bytes": artifact["size"],
                "source_url": url,
                "origin": "C3A" if name in base else "upstream-lock",
            }
        )
    if len(result) != 72 or sum(item["kind"] == "wheel" for item in result) != 71:
        raise ValueError("combined artifact closure differs")
    return result, edges


def requirements(artifacts):
    return "".join(
        f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}\n" for item in artifacts
    )


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        source_url(newurl, urllib.parse.urlsplit(request.full_url).netloc)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def response(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SameHostRedirect())
    return opener.open(
        urllib.request.Request(url, headers={"User-Agent": "buddha-closure-review/1"}), timeout=30
    )


def obtain(item, directory):
    destination = directory / "artifacts" / item["filename"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        verify(destination, item["sha256"], item["bytes"])
        return destination
    previous = REPOSITORY / "runs/reference-linux-nb02c3/wheels" / item["filename"]
    temporary = destination.with_suffix(destination.suffix + ".part")
    if previous.is_file():
        verify(previous, item["sha256"], item["bytes"])
        shutil.copyfile(previous, temporary)
    else:
        started, count = time.monotonic(), 0
        with response(item["source_url"]) as reply, temporary.open("wb") as stream:
            if int(reply.headers.get("Content-Length", -1)) != item["bytes"]:
                raise ValueError("artifact HTTP length differs from lock")
            while chunk := reply.read(1024 * 1024):
                count += len(chunk)
                if count > item["bytes"] or time.monotonic() - started > 900:
                    raise ValueError("artifact download exceeded byte/time bound")
                stream.write(chunk)
    verify(temporary, item["sha256"], item["bytes"])
    temporary.replace(destination)
    print(json.dumps({"downloaded": item["filename"], "bytes": item["bytes"]}), flush=True)
    return destination


def safe_member(name):
    path = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe archive member")
    return path


def inspect_artifact(item, directory, *, extract=True):
    path = directory / "artifacts" / item["filename"]
    verify(path, item["sha256"], item["bytes"])
    notices, metadata, total = [], None, 0

    def consume(name, size, read):
        nonlocal metadata, total
        relative = safe_member(name)
        if relative.name in {"METADATA", "PKG-INFO"}:
            if size > MAX_METADATA:
                raise ValueError("oversized package metadata")
            candidate = BytesParser().parsebytes(read())
            if canonicalize_name(candidate.get("Name", "")) == item["name"]:
                metadata = candidate
        if not any(
            token in relative.name.lower() for token in ("licen", "copying", "notice", "copyright")
        ):
            return
        total += size
        if size > MAX_NOTICE or total > 128 * 1024 * 1024:
            raise ValueError("oversized package notice inventory")
        raw = read()
        if len(raw) != size:
            raise ValueError("archive notice size mismatch")
        target = directory / "licenses" / item["filename"] / Path(*relative.parts)
        if extract:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        else:
            verify(target, sha(raw), size)
        lower = raw.lower()
        notices.append(
            {
                "path": name,
                "sha256": sha(raw),
                "bytes": len(raw),
                "gnu_notice": any(
                    token in lower
                    for token in (b"gnu general public", b"gnu lesser", b"gcc runtime")
                ),
                "mpl_notice": b"mozilla public" in lower,
                "proprietary_notice": b"proprietary" in lower,
            }
        )

    if item["kind"] == "wheel":
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > 200000:
                raise ValueError("oversized wheel inventory")
            for member in archive.infolist():
                if not member.is_dir():
                    consume(member.filename, member.file_size, lambda m=member: archive.read(m))
    else:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                safe_member(member.name)
                if not member.isfile() and not member.isdir():
                    raise ValueError("source archive contains links or special files")
                if member.isfile():

                    def read(m=member):
                        stream = archive.extractfile(m)
                        if stream is None:
                            raise ValueError("source archive member unavailable")
                        with stream:
                            return stream.read()

                    consume(member.name, member.size, read)
    if metadata is None or str(metadata["Version"]) != item["version"]:
        raise ValueError("missing or contradictory package metadata: " + item["name"])
    return {
        **item,
        "license_expression": str(metadata.get("License-Expression") or ""),
        "license_summary": str(metadata.get("License") or "")[:2000],
        "license_classifiers": [
            value for value in metadata.get_all("Classifier", []) if value.startswith("License ::")
        ],
        "requires_python": str(metadata.get("Requires-Python") or ""),
        "requires_dist": metadata.get_all("Requires-Dist", []),
        "notice_status": "present" if notices else "absent-in-sealed-artifact",
        "license_files": sorted(notices, key=lambda notice: notice["path"]),
    }


def advisory_record(item, directory):
    url = source_url(f"https://pypi.org/pypi/{item['name']}/{item['version']}/json", "pypi.org")
    with response(url) as reply:
        raw = reply.read(MAX_METADATA + 1)
    if len(raw) > MAX_METADATA:
        raise ValueError("metadata response exceeds byte bound")
    parsed = json.loads(raw)
    if (
        canonicalize_name(parsed["info"]["name"]) != item["name"]
        or parsed["info"]["version"] != item["version"]
    ):
        raise ValueError("metadata response package mismatch")
    target = directory / "metadata" / (item["name"] + "-" + item["version"] + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {
        "name": item["name"],
        "version": item["version"],
        "source_url": url,
        "response_sha256": sha(raw),
        "response_bytes": len(raw),
        "vulnerabilities": parsed.get("vulnerabilities", []),
    }


def advisories(artifacts, directory):
    started = datetime.now(UTC).isoformat()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(lambda item: advisory_record(item, directory), artifacts))
    save(
        ADVISORIES,
        {
            "format": "buddha.review.nb02c3b-advisories.v1",
            "started_utc": started,
            "completed_utc": datetime.now(UTC).isoformat(),
            "package_count": len(records),
            "scope": (
                "Primary PyPI metadata preflight; "
                "not an installed/OS/ELF audit or an advisory waiver"
            ),
            "packages": records,
        },
    )
    print(
        json.dumps(
            {
                "metadata_checked": len(records),
                "affected_packages": [item["name"] for item in records if item["vulnerabilities"]],
            }
        )
    )


def validate_dependencies(packages):
    versions = {item["name"]: item["version"] for item in packages}
    for item in packages:
        if TARGET["python_full_version"] not in SpecifierSet(item.get("requires_python", "")):
            raise ValueError("package Python requirement incompatible")
        for raw in item["requires_dist"]:
            requirement = Requirement(raw)
            if requirement.marker and not requirement.marker.evaluate(TARGET):
                continue
            name = canonicalize_name(requirement.name)
            if (
                requirement.url
                or name not in versions
                or versions[name] not in requirement.specifier
            ):
                raise ValueError(
                    f"installed-metadata dependency incompatible: {item['name']} -> {raw}"
                )


def verify_requirements(path, artifacts):
    if path.read_bytes() != requirements(artifacts).encode("utf-8"):
        raise ValueError("frozen C3B requirements changed")


def manifest_record(packages, edges):
    return {
        "format": "buddha.review.nb02c3b-wheelhouse.v1",
        "target": TARGET,
        "source_seals": {
            path.relative_to(REPOSITORY).as_posix(): value for path, value in SEALS.items()
        },
        "requirements_sha256": digest(REQUIREMENTS),
        "partition_roots": ROOTS,
        "partition_dependency_edges": edges,
        "only_version_override": {"anyio": ["4.10.0", "4.14.2"]},
        "installation_enabled": False,
        "source_build_required": ["rouge-score==0.1.2"],
        "packages": packages,
    }


def check(artifacts, edges, directory):
    verify_requirements(REQUIREMENTS, artifacts)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    packages = [inspect_artifact(item, directory, extract=False) for item in artifacts]
    if manifest != manifest_record(packages, edges):
        raise ValueError("frozen C3B manifest differs from source plan")
    advisory = json.loads(ADVISORIES.read_text(encoding="utf-8"))
    if (
        advisory["format"] != "buddha.review.nb02c3b-advisories.v1"
        or advisory["package_count"] != len(artifacts)
        or [(item["name"], item["version"]) for item in advisory["packages"]]
        != [(item["name"], item["version"]) for item in artifacts]
    ):
        raise ValueError("advisory snapshot population differs")
    for item in advisory["packages"]:
        path = directory / "metadata" / (item["name"] + "-" + item["version"] + ".json")
        verify(path, item["response_sha256"], item["response_bytes"])
        raw = json.loads(path.read_bytes())
        if raw.get("vulnerabilities", []) != item["vulnerabilities"]:
            raise ValueError("advisory entries differ from retained primary response")
    validate_dependencies(packages)
    print(
        json.dumps(
            {
                "verified_artifacts": len(artifacts),
                "dependencies": "compatible",
                "installation_enabled": False,
            }
        )
    )


def self_test(artifacts):
    class Checks(unittest.TestCase):
        def test_selected_tags_are_real(self):
            nvjit = next(item for item in artifacts if item["name"] == "nvidia-nvjitlink-cu12")
            self.assertTrue(parse_wheel_filename(nvjit["filename"])[3] & set(tags()))
            self.assertFalse(parse_wheel_filename("x-1-cp313-cp313-win_amd64.whl")[3] & set(tags()))
            self.assertEqual(sum(item["name"].startswith("nvidia-") for item in artifacts), 14)

        def test_hash_and_source_guards(self):
            with tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / "artifact"
                target.write_bytes(b"sealed")
                verify(target, sha(b"sealed"), 6)
                target.write_bytes(b"edited")
                with self.assertRaises(ValueError):
                    verify(target, sha(b"sealed"), 6)
                with patch.dict(SEALS, {target: sha(b"sealed")}, clear=True):
                    with self.assertRaises(ValueError):
                        plan()
            with self.assertRaises(ValueError):
                source_url("https://evil.example/package.whl")
            with self.assertRaises(ValueError):
                safe_member("../LICENSE")

        def test_closure_and_requirements_are_frozen(self):
            self.assertEqual(len(artifacts), 72)
            self.assertEqual(len(requirements(artifacts).splitlines()), 72)
            with tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / "requirements.txt"
                target.write_text(requirements(artifacts), encoding="utf-8", newline="\n")
                verify_requirements(target, artifacts)
                target.write_text(
                    requirements(artifacts).replace("torch==2.7.1", "torch==9"), encoding="utf-8"
                )
                with self.assertRaises(ValueError):
                    verify_requirements(target, artifacts)
            with self.assertRaises(ValueError):
                validate_dependencies(
                    [{"name": "parent", "version": "1", "requires_dist": ["missing>=1"]}]
                )

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    )
    if not result.wasSuccessful():
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("metadata", "download", "check", "self-test"))
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    directory = args.directory.resolve()
    artifacts, edges = plan()
    if args.mode == "metadata":
        advisories(artifacts, directory)
    elif args.mode == "download":
        directory.mkdir(parents=True, exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda item: obtain(item, directory), artifacts))
        packages = [inspect_artifact(item, directory) for item in artifacts]
        validate_dependencies(packages)
        REQUIREMENTS.write_text(requirements(artifacts), encoding="utf-8", newline="\n")
        save(MANIFEST, manifest_record(packages, edges))
        check(artifacts, edges, directory)
    elif args.mode == "check":
        check(artifacts, edges, directory)
    else:
        self_test(artifacts)


if __name__ == "__main__":
    main()
