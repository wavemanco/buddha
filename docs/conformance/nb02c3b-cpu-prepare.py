"""Prepare the explicitly different official Torch CPU artifact profile; no install."""

import argparse
import json
import shutil
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.tags import Tag
from packaging.utils import canonicalize_name, parse_wheel_filename

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parents[1] / "runs/reference-linux-nb02c3b"
DIRECTORY = ROOT / "cpu"
OUTPUT = DOCS / "nb02c3b-cpu-wheels.json"
REQUIREMENTS = DOCS / "nb02c3b-cpu-requirements.txt"
ADVISORIES = DOCS / "nb02c3b-cpu-advisories.json"
SEALS = {
    "nb02c3b-runtime-prepare.py": (
        "aeed1d41ef1c47e3b665c767cbd7b2b971bdb98513d4e6aa5d46f7354b7058bf"
    ),
    "nb02c3b-runtime-wheels.json": (
        "3a4f480e9b09d60282c9987aa9dc19c2b1c85bcd839a41f5340d7f72598f2746"
    ),
    "nb02c3b-runtime-requirements.txt": (
        "c97223ac8937d444711fa157cbce86ec640d7bd784fc78f41dd25ab3ea5f56ee"
    ),
    "nb02c3b-runtime-advisories.json": (
        "be9bd1fcb1b9a9187ecdd9b355e49d5909669258dc3d7c3eab7f0d06740d3a77"
    ),
}
CPU = {
    "name": "torch",
    "version": "2.7.1+cpu",
    "filename": "torch-2.7.1+cpu-cp313-cp313-manylinux_2_28_x86_64.whl",
    "kind": "wheel",
    "sha256": "84ea1f6a1d15663037d01b121d6e33bb9da3c90af8e069e5072c30f413455a57",
    "bytes": 175839558,
    "source_url": "https://download-r2.pytorch.org/whl/cpu/torch-2.7.1%2Bcpu-cp313-cp313-manylinux_2_28_x86_64.whl",
    "origin": "official-pytorch-cpu-index",
}
METADATA_SHA = "0464be2f825052a9766185210a6143fbde6762d77cffd1a77d2f8326baf12ae5"
ROUGE_SETUP_SHA = "c6942fba16f1e883b2c2fcb6210022fba246124644d05c855436c85909ba8386"
ROUGE_REQUIREMENTS = ["absl-py", "nltk", "numpy", "six>=1.14.0"]


def load_helper():
    # Verify bytes before importing the separately frozen engineering helper.
    import hashlib

    for name, expected in SEALS.items():
        if hashlib.sha256((DOCS / name).read_bytes()).hexdigest() != expected:
            raise ValueError("held preparation source/record changed")
    path = DOCS / "nb02c3b-runtime-prepare.py"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SEALS[path.name]:
        raise ValueError("held helper changed before consumption")
    module = ModuleType("held_runtime")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    module.plan()
    return module


def selection(helper, *, extract):
    helper.source_url(CPU["source_url"], "download-r2.pytorch.org")
    helper.verify(DIRECTORY / "metadata/torch-cpu.METADATA", METADATA_SHA)
    helper.verify(DIRECTORY / "artifacts" / CPU["filename"], CPU["sha256"], CPU["bytes"])
    if (
        Tag("cp313", "cp313", "manylinux_2_28_x86_64")
        not in parse_wheel_filename(CPU["filename"])[3]
    ):
        raise ValueError("CPU wheel tag differs")
    with zipfile.ZipFile(DIRECTORY / "artifacts" / CPU["filename"]) as archive:
        if helper.sha(archive.read("torch-2.7.1+cpu.dist-info/METADATA")) != METADATA_SHA:
            raise ValueError("wheel metadata differs from sealed official index metadata")
    held = json.loads((DOCS / "nb02c3b-runtime-wheels.json").read_text(encoding="utf-8"))
    records = {item["name"]: item for item in held["packages"]}
    records["torch"] = helper.inspect_artifact(CPU, DIRECTORY, extract=extract)
    rouge = records["rouge-score"]
    helper.verify(DIRECTORY / "artifacts" / rouge["filename"], rouge["sha256"], rouge["bytes"])
    with tarfile.open(DIRECTORY / "artifacts" / rouge["filename"]) as archive:
        stream = archive.extractfile("rouge_score-0.1.2/setup.py")
        if stream is None or helper.sha(stream.read()) != ROUGE_SETUP_SHA:
            raise ValueError("reviewed ROUGE source metadata changed")
    baseline = json.loads((DOCS / "nb02c3-runtime-wheels.json").read_text(encoding="utf-8"))
    pending = list(helper.ROOTS) + [
        canonicalize_name(item["name"]) for item in baseline["packages"]
    ]
    selected, edges = set(), {}
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        selected.add(name)
        requirements = (
            ROUGE_REQUIREMENTS if name == "rouge-score" else records[name]["requires_dist"]
        )
        children = []
        for raw in requirements:
            requirement = Requirement(raw)
            if requirement.marker and not Marker(str(requirement.marker)).evaluate(helper.TARGET):
                continue
            child = canonicalize_name(requirement.name)
            if (
                requirement.url
                or child not in records
                or records[child]["version"] not in requirement.specifier
            ):
                raise ValueError("CPU dependency outside frozen compatible artifacts")
            children.append(child)
        edges[name] = sorted(set(children))
        pending.extend(children)
    if (
        len(selected) != 57
        or "triton" in selected
        or any(name.startswith("nvidia-") for name in selected)
    ):
        raise ValueError("CPU closure differs from reviewed 57 distributions")
    return [records[name] for name in sorted(selected)], edges


def manifest(helper, packages, edges):
    return {
        "format": "buddha.review.nb02c3b-cpu-wheelhouse.v1",
        "target": helper.TARGET,
        "held_source_seals": SEALS,
        "official_index_url": "https://download.pytorch.org/whl/cpu/torch/",
        "official_index_snapshot_sha256": (
            "44c503ca1a65ae8135f2bb538827c4e9585e5eaf14762b75ab7982a3c7c137c5"
        ),
        "official_metadata_sha256": METADATA_SHA,
        "binary_variant": {"torch": ["2.7.1", "2.7.1+cpu"]},
        "exact_upstream_binary_lock": False,
        "installation_enabled": False,
        "version_overlay": {"anyio": ["4.10.0", "4.14.2"]},
        "source_metadata_fallback": {
            "rouge-score": {
                "setup_sha256": ROUGE_SETUP_SHA,
                "requires_dist": ROUGE_REQUIREMENTS,
                "reason": "Original PKG-INFO omits Requires-Dist",
            }
        },
        "requirements_sha256": helper.digest(REQUIREMENTS),
        "active_dependency_edges": edges,
        "packages": packages,
    }


def advisory_record(helper, packages):
    original = json.loads((DOCS / "nb02c3b-runtime-advisories.json").read_text(encoding="utf-8"))
    selected = {item["name"] for item in packages}
    return {
        "format": "buddha.review.nb02c3b-cpu-advisories.v1",
        "source_snapshot_sha256": SEALS["nb02c3b-runtime-advisories.json"],
        "source_completed_utc": original["completed_utc"],
        "torch_mapping": {
            "artifact_version": "2.7.1+cpu",
            "advisory_source_version": "2.7.1",
            "scope": (
                "Base Torch source advisories retained; "
                "CPU binary is not an independently clean PyPI release"
            ),
        },
        "packages": [item for item in original["packages"] if item["name"] in selected],
    }


def bundled_advisories(helper, packages):
    item = next(item for item in packages if item["name"] == "setuptools")
    helper.verify(DIRECTORY / "artifacts" / item["filename"], item["sha256"], item["bytes"])
    records = []
    with zipfile.ZipFile(DIRECTORY / "artifacts" / item["filename"]) as archive:
        members = sorted(
            name
            for name in archive.namelist()
            if name.startswith("setuptools/_vendor/") and name.endswith(".dist-info/METADATA")
        )
        if len(members) != 16:
            raise ValueError("Setuptools vendored metadata inventory differs")
        for name in members:
            raw = archive.read(name)
            metadata = helper.BytesParser().parsebytes(raw)
            record = helper.advisory_record(
                {"name": canonicalize_name(metadata["Name"]), "version": metadata["Version"]},
                DIRECTORY,
            )
            record["bundled_metadata"] = {
                "artifact": item["filename"],
                "artifact_sha256": item["sha256"],
                "path": name,
                "sha256": helper.sha(raw),
            }
            records.append(record)
    helper.save(
        DOCS / "nb02c3b-cpu-bundled-advisories.json",
        {
            "format": "buddha.review.nb02c3b-bundled-advisories.v1",
            "checked_utc": helper.datetime.now(helper.UTC).isoformat(),
            "scope": (
                "Actual sixteen Setuptools vendored metadata versions; primary PyPI preflight only"
            ),
            "packages": records,
        },
    )
    print(
        json.dumps(
            {
                "bundled_checked": len(records),
                "affected": [item["name"] for item in records if item["vulnerabilities"]],
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "check", "bundled"))
    args = parser.parse_args()
    helper = load_helper()
    # The mutable index snapshot is retained provenance, not a new dependency source.
    index = DIRECTORY / "metadata/torch-index.html"
    if index.exists():
        helper.verify(index, "44c503ca1a65ae8135f2bb538827c4e9585e5eaf14762b75ab7982a3c7c137c5")
    if args.mode == "prepare":
        metadata = DIRECTORY / "metadata/torch-cpu.METADATA"
        if not metadata.exists():
            with helper.response(CPU["source_url"] + ".metadata") as reply:
                raw = reply.read(helper.MAX_METADATA + 1)
            if len(raw) > helper.MAX_METADATA or helper.sha(raw) != METADATA_SHA:
                raise ValueError("official CPU metadata hash mismatch")
            metadata.parent.mkdir(parents=True, exist_ok=True)
            metadata.write_bytes(raw)
        helper.obtain(CPU, DIRECTORY)
        held = json.loads((DOCS / "nb02c3b-runtime-wheels.json").read_text(encoding="utf-8"))
        helper.obtain(
            next(item for item in held["packages"] if item["name"] == "rouge-score"), DIRECTORY
        )
    packages, edges = selection(helper, extract=args.mode == "prepare")
    if args.mode == "bundled":
        bundled_advisories(helper, packages)
        return
    if args.mode == "prepare":
        for item in packages:
            target = DIRECTORY / "artifacts" / item["filename"]
            if not target.exists():
                source = ROOT / "artifacts" / item["filename"]
                if source.exists():
                    helper.verify(source, item["sha256"], item["bytes"])
                    shutil.copyfile(source, target)
                else:
                    helper.obtain(item, DIRECTORY)
            actual = helper.inspect_artifact(item, DIRECTORY)
            if actual != item:
                raise ValueError("CPU copied artifact metadata differs from held source")
        REQUIREMENTS.write_text(helper.requirements(packages), encoding="utf-8", newline="\n")
        helper.save(OUTPUT, manifest(helper, packages, edges))
        helper.save(ADVISORIES, advisory_record(helper, packages))
    helper.verify_requirements(REQUIREMENTS, packages)
    for item in packages:
        if helper.inspect_artifact(item, DIRECTORY, extract=False) != item:
            raise ValueError("CPU artifact/notice record changed")
    if json.loads(OUTPUT.read_text(encoding="utf-8")) != manifest(helper, packages, edges):
        raise ValueError("CPU frozen manifest changed")
    if json.loads(ADVISORIES.read_text(encoding="utf-8")) != advisory_record(helper, packages):
        raise ValueError("CPU advisory mapping changed")
    validated = [
        dict(item, requires_dist=ROUGE_REQUIREMENTS) if item["name"] == "rouge-score" else item
        for item in packages
    ]
    helper.validate_dependencies(validated)
    print(
        json.dumps(
            {
                "artifacts": len(packages),
                "bytes": sum(item["bytes"] for item in packages),
                "exact_upstream_binary_lock": False,
                "installation_enabled": False,
            }
        )
    )


if __name__ == "__main__":
    main()
