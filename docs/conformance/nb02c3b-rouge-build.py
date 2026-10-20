"""Check ROUGE source parsing or build twice inside the existing owned executor."""

import argparse
import base64
import csv
import dataclasses
import gzip
import hashlib
import io
import json
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
import uuid
import zipfile
from email.parser import BytesParser
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from packaging.requirements import Requirement

DOCS = Path(__file__).resolve().parent
REPOSITORY = DOCS.parents[1]
DIRECTORY = REPOSITORY / "runs/reference-linux-nb02c3b/cpu"
WORKER = DOCS / "nb02c3b-rouge-build-worker.py"
SOURCE = DIRECTORY / "artifacts/rouge_score-0.1.2.tar.gz"
CPU_SEAL = "7a83b877580fdebcbab8e863b6c637b5847c9c9c662240bab8037ce739103d93"
ENVIRONMENT_SEAL = "dc58b658821a536d13c300b6b1f756aa8dc3b2adcc5699627a4827f8361f7d9a"
IMAGE_ID = "sha256:d9476e5c6baf21ba4e70709b96100bdc7fe30637e59a377432690088c8dc77c1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_worker():
    raw = WORKER.read_bytes()
    module = ModuleType("rouge_builder")
    module.__file__ = str(WORKER)
    exec(compile(raw, str(WORKER), "exec"), module.__dict__)
    module.consumed_bytes = raw
    return module


def verified_environment(raw):
    if sha(raw) != ENVIRONMENT_SEAL:
        raise ValueError("reviewed C3A environment record changed")
    environment = json.loads(raw)
    if environment["image_id"] != IMAGE_ID:
        raise ValueError("reviewed C3A image changed")
    return environment


def source_snapshot():
    return {
        path.relative_to(REPOSITORY).as_posix(): sha(path.read_bytes())
        for path in (
            Path(__file__).resolve(),
            WORKER,
            REPOSITORY / "buddha/executor.py",
            REPOSITORY / "buddha/channel.py",
            REPOSITORY / "buddha/__init__.py",
            REPOSITORY / "buddha/releases.py",
            DOCS / "nb02c3-runtime-environment.json",
            DOCS / "nb02c3b-cpu-wheels.json",
        )
    }


def verify_sources(snapshot):
    if source_snapshot() != snapshot:
        raise ValueError("consumed host preparation source changed")


def verify_runner(runner, snapshot):
    expected = {
        "build-worker.py": snapshot[WORKER.relative_to(REPOSITORY).as_posix()],
        **{
            f"buddha/{name}": snapshot[f"buddha/{name}"]
            for name in ("__init__.py", "channel.py", "releases.py")
        },
    }
    if file_inventory(runner) != expected:
        raise ValueError("staged runner differs from consumed source")


def file_inventory(root):
    return {
        path.relative_to(root).as_posix(): sha(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    }


def stage_runner(runner, worker):
    (runner / "build-worker.py").write_bytes(worker.consumed_bytes)
    (runner / "buddha").mkdir()
    for name in ("__init__.py", "channel.py", "releases.py"):
        shutil.copyfile(REPOSITORY / "buddha" / name, runner / "buddha" / name)


def validate_wheel(raw, source_files, worker):
    if not 0 < len(raw) <= worker.MAX_WHEEL:
        raise ValueError("exported wheel size differs")
    package_files = {
        name.removeprefix("rouge_score-0.1.2/"): content
        for name, content in source_files.items()
        if name.startswith("rouge_score-0.1.2/rouge_score/")
    }
    prefix = "rouge_score-0.1.2.dist-info/"
    metadata_files = {prefix + name for name in ("METADATA", "WHEEL", "top_level.txt", "RECORD")}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names, contents, total = set(), {}, 0
        for item in archive.infolist():
            worker.portable(item.filename)
            key = item.filename.casefold()
            mode = stat.S_IFMT(item.external_attr >> 16)
            total += item.file_size
            if (
                key in names
                or mode not in {0, stat.S_IFREG}
                or item.is_dir()
                or item.file_size > 64 * 1024
                or total > worker.MAX_WHEEL
                or len(names) >= 128
                or item.date_time != (2024, 1, 1, 0, 0, 0)
            ):
                raise ValueError("wheel path/type/byte/timestamp inventory differs")
            names.add(key)
            contents[item.filename] = archive.read(item)
    if set(contents) != package_files.keys() | metadata_files:
        raise ValueError("wheel package/metadata inventory differs")
    for name, original in package_files.items():
        if contents[name] != original:
            raise ValueError("built package source differs from sealed archive")
    metadata = BytesParser().parsebytes(contents[prefix + "METADATA"])
    expected = {str(Requirement(value)) for value in ("absl-py", "nltk", "numpy", "six>=1.14.0")}
    if (
        metadata["Name"].replace("_", "-") != "rouge-score"
        or metadata["Version"] != "0.1.2"
        or {str(Requirement(value)) for value in metadata.get_all("Requires-Dist", [])} != expected
        or metadata["Requires-Python"] != ">=3.7"
    ):
        raise ValueError("built wheel metadata differs from reviewed source")
    wheel = BytesParser().parsebytes(contents[prefix + "WHEEL"])
    if wheel["Root-Is-Purelib"] != "true" or wheel.get_all("Tag") != ["py3-none-any"]:
        raise ValueError("built wheel target differs")
    record = {}
    for name, encoded, size in csv.reader(io.StringIO(contents[prefix + "RECORD"].decode())):
        if name in record or name not in contents:
            raise ValueError("wheel RECORD path differs")
        if name == prefix + "RECORD":
            if encoded or size:
                raise ValueError("wheel RECORD self entry differs")
        elif encoded != "sha256=" + base64.urlsafe_b64encode(
            hashlib.sha256(contents[name]).digest()
        ).rstrip(b"=").decode() or size != str(len(contents[name])):
            raise ValueError("wheel RECORD hash/size differs")
        record[name] = {
            "sha256": sha(contents[name]),
            "bytes": len(contents[name]),
            "source_mapping": "sealed source" if name in package_files else "generated metadata",
        }
    if set(record) != set(contents):
        raise ValueError("wheel RECORD omits a member")
    return record


def parser_checks(worker):
    class Checks(unittest.TestCase):
        def archive(self, entries):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w:") as archive:
                for name, kind, data in entries:
                    entry = tarfile.TarInfo(name)
                    entry.type = kind
                    entry.size = len(data) if kind == tarfile.REGTYPE else 0
                    entry.linkname = (
                        "/outside" if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE} else ""
                    )
                    archive.addfile(entry, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
            return gzip.compress(stream.getvalue(), mtime=0)

        def denied(self, entries):
            raw = self.archive(entries)
            with self.assertRaises(ValueError):
                worker.sources(raw, sha(raw))

        def test_actual_sealed_source_and_wrong_hash(self):
            raw = SOURCE.read_bytes()
            files, count, total = worker.sources(raw, worker.SOURCE_SHA)
            self.assertEqual((count, total), (26, 75835))
            self.assertEqual(len([name for name in files if "/rouge_score/" in name]), 14)
            with self.assertRaises(ValueError):
                worker.sources(raw, "0" * 64)

        def test_nonportable_paths_and_aliases(self):
            for name in (
                "/absolute",
                "../outside",
                "rouge_score-0.1.2/../outside",
                "rouge_score-0.1.2\\escape",
                "rouge_score-0.1.2/CON",
                "rouge_score-0.1.2/trailing.",
                "other-root/file",
            ):
                with self.subTest(name=name):
                    self.denied([(name, tarfile.REGTYPE, b"x")])
            for paths in (
                ("same", "same"),
                ("Same", "same"),
                ("parent", "parent/child"),
                ("parent/child", "parent"),
                ("Parent/child", "parent/other"),
            ):
                with self.subTest(paths=paths):
                    self.denied(
                        [("rouge_score-0.1.2/" + path, tarfile.REGTYPE, b"x") for path in paths]
                    )

        def test_links_special_files_and_bounds(self):
            for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE):
                with self.subTest(kind=kind):
                    self.denied([("rouge_score-0.1.2/file", kind, b"")])
            self.denied([("rouge_score-0.1.2/large", tarfile.REGTYPE, b"x" * 65537)])
            self.denied(
                [("rouge_score-0.1.2/f" + str(i), tarfile.REGTYPE, b"x") for i in range(65)]
            )
            raw = SOURCE.read_bytes() + b"trailing"
            with self.assertRaises(ValueError):
                worker.sources(raw, sha(raw))

        def test_changed_environment_rejected(self):
            environment = (DOCS / "nb02c3-runtime-environment.json").read_bytes()
            verified_environment(environment)
            changed = json.loads(environment)
            changed["image_id"] = "sha256:" + "0" * 64
            with self.assertRaises(ValueError):
                verified_environment(json.dumps(changed).encode())

        def test_consumed_host_source_drift_rejected(self):
            snapshot = source_snapshot()
            original = Path.read_bytes

            def changed(path):
                return b"changed worker" if path == WORKER else original(path)

            with patch.object(Path, "read_bytes", changed):
                with self.assertRaises(ValueError):
                    verify_sources(snapshot)

        def test_staged_runner_matches_consumed_source(self):
            snapshot = source_snapshot()
            with tempfile.TemporaryDirectory() as temporary:
                runner = Path(temporary)
                stage_runner(runner, worker)
                verify_runner(runner, snapshot)
                (runner / "build-worker.py").write_bytes(b"changed copy")
                with self.assertRaises(ValueError):
                    verify_runner(runner, snapshot)

        def test_real_staged_channel_import_under_isolation(self):
            with tempfile.TemporaryDirectory() as temporary:
                runner = Path(temporary)
                stage_runner(runner, worker)
                result = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        "-X",
                        "pycache_prefix=/__absent_bytecode_cache",
                        "-c",
                        "import json,sys;sys.path.insert(0,sys.argv[1]);"
                        "import buddha,buddha.channel,buddha.releases;"
                        "print(json.dumps([m.__file__ for m in "
                        "(buddha,buddha.channel,buddha.releases)]))",
                        str(runner),
                    ],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                paths = json.loads(result.stdout)
                self.assertEqual(
                    {Path(path).name for path in paths},
                    {"__init__.py", "channel.py", "releases.py"},
                )
                self.assertTrue(
                    all(Path(path).resolve().is_relative_to(runner.resolve()) for path in paths)
                )

        def test_actual_builder_template_paths_without_relaxing_source_parser(self):
            sys.path.insert(0, str(REPOSITORY))
            path = DIRECTORY / "artifacts/setuptools-79.0.1-py3-none-any.whl"
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.endswith("/"):
                        worker.builder_member(name)
            self.assertEqual(
                worker.builder_member("setuptools/script (dev).tmpl"),
                ["setuptools", "script (dev).tmpl"],
            )
            with self.assertRaises(ValueError):
                worker.portable("setuptools/script (dev).tmpl")

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    )
    if not result.wasSuccessful():
        raise SystemExit(1)


def build(worker):
    snapshot = source_snapshot()
    if sha(worker.consumed_bytes) != snapshot[WORKER.relative_to(REPOSITORY).as_posix()]:
        raise ValueError("loaded engineering worker differs from source snapshot")
    sys.path.insert(0, str(REPOSITORY))
    from buddha.executor import ContainerSpec, Limits, run_container
    from buddha.releases import _root, file_hash

    manifest_raw = (DOCS / "nb02c3b-cpu-wheels.json").read_bytes()
    if sha(manifest_raw) != CPU_SEAL:
        raise ValueError("reviewed CPU source profile changed")
    manifest = json.loads(manifest_raw)
    source_files, _, _ = worker.sources(SOURCE.read_bytes(), worker.SOURCE_SHA)
    setuptools = next(item for item in manifest["packages"] if item["name"] == "setuptools")
    wheel = DIRECTORY / "artifacts" / setuptools["filename"]
    if sha(wheel.read_bytes()) != setuptools["sha256"]:
        raise ValueError("reviewed builder wheel changed")
    environment = verified_environment((DOCS / "nb02c3-runtime-environment.json").read_bytes())
    verify_sources(snapshot)
    captured = []

    def handle(frame):
        if (
            not captured
            and set(frame) == {"type", "error_type", "details"}
            and frame["type"] == "error"
            and type(frame["error_type"]) is str
            and type(frame["details"]) is str
            and len(frame["details"]) <= 8192
        ):
            captured.append(frame)
        elif not captured and set(frame) == {"type", "report"} and frame["type"] == "result":
            captured.append(frame)
        elif (
            len(captured) == 1
            and captured[0]["type"] == "result"
            and set(frame) == {"type", "name", "data_base64"}
            and frame["type"] == "wheel"
            and frame["name"] == worker.WHEEL_NAME
        ):
            raw = base64.b64decode(frame["data_base64"], validate=True)
            if (
                len(raw) > worker.MAX_WHEEL
                or base64.b64encode(raw).decode() != frame["data_base64"]
            ):
                raise ValueError("wheel frame size/encoding differs")
            captured.append(raw)
        else:
            raise ValueError("build frame sequence differs")
        return None

    _root(DIRECTORY)
    receipts = DIRECTORY / "build-results"
    if not receipts.exists():
        receipts.mkdir()
    _root(receipts)
    receipt = receipts / uuid.uuid4().hex
    receipt.mkdir()
    _root(receipt)
    derived = DIRECTORY / "derived-wheels"
    if not derived.exists():
        derived.mkdir()
    _root(derived)
    with tempfile.TemporaryDirectory(prefix="staging-", dir=receipt) as temporary:
        staging = Path(temporary).resolve()
        if not staging.is_relative_to(DIRECTORY.resolve()):
            raise ValueError("temporary build path outside intended folder")
        runner, inputs = staging / "runner", staging / "inputs"
        runner.mkdir()
        inputs.mkdir()
        stage_runner(runner, worker)
        verify_runner(runner, snapshot)
        shutil.copyfile(SOURCE, inputs / SOURCE.name)
        shutil.copyfile(wheel, inputs / wheel.name)
        (inputs / "builder-requirements.txt").write_text(
            "setuptools==79.0.1 --hash=sha256:" + setuptools["sha256"] + "\n",
            encoding="utf-8",
            newline="\n",
        )
        initial = {
            "format": "buddha.rouge-build.v1",
            "runner": file_inventory(runner),
            "inputs": file_inventory(inputs),
        }
        spec = ContainerSpec(
            image_id=environment["image_id"],
            role="evaluator",
            mounts=(("/runner", runner), ("/inputs", inputs)),
            runner_entrypoint="build-worker.py",
            image_environment=tuple(
                tuple(value.split("=", 1)) for value in environment["config"]["Env"]
            ),
        )
        try:
            execution = run_container(
                spec,
                initial=initial,
                handle=handle,
                limits=Limits(
                    wall_seconds=120,
                    memory_mib=512,
                    scratch_mib=128,
                    pids=32,
                    cpus=1,
                    max_stdout_bytes=2 * 1024 * 1024,
                    max_stderr_bytes=64 * 1024,
                    max_frames=4,
                ),
            )
        except BaseException as error:
            _root(receipt)
            with (receipt / "failure.json").open("xb") as stream:
                stream.write(
                    json.dumps(
                        {
                            "format": "buddha.rouge-build-failure.v1",
                            "error_type": type(error).__name__,
                            "container_id": getattr(error, "container_id", None),
                            "cleanup_status": getattr(error, "cleanup_status", "unknown"),
                            "source_files": snapshot,
                            "inputs": initial,
                        },
                        sort_keys=True,
                    ).encode()
                )
            raise
        execution_record = {
            key: value
            for key, value in dataclasses.asdict(execution).items()
            if not key.startswith("_")
        }
        execution_record["configuration"] = execution.configuration
        _root(receipt)
        with (receipt / "execution.json").open("xb") as stream:
            stream.write(
                json.dumps(
                    {
                        "format": "buddha.rouge-build-execution.v1",
                        "validated_wheel": False,
                        "diagnostics": [
                            item
                            for item in captured
                            if type(item) is dict and item["type"] == "error"
                        ],
                        "execution": execution_record,
                        "source_files": snapshot,
                        "inputs": initial,
                    },
                    sort_keys=True,
                ).encode()
            )
        if execution.exit_code or execution.cleanup_status != "removed" or len(captured) != 2:
            raise ValueError("build did not complete with owned cleanup")
        verify_sources(snapshot)
        verify_runner(runner, snapshot)
        for root, expected in ((runner, initial["runner"]), (inputs, initial["inputs"])):
            if file_inventory(root) != expected:
                raise ValueError("read-only build input changed")
        _root(receipt)
        _root(staging)
    report, raw = captured[0]["report"], captured[1]
    inventory = validate_wheel(raw, source_files, worker)
    if report["wheel_sha256"] != sha(raw) or report["repeat_sha256"] != [sha(raw), sha(raw)]:
        raise ValueError("reported repeat/export hashes differ")
    verify_sources(snapshot)
    target = derived / worker.WHEEL_NAME
    _root(derived)
    _root(receipt)
    if target.exists():
        if file_hash(target, max_bytes=worker.MAX_WHEEL) != sha(raw):
            raise ValueError("different derived wheel already exists")
    else:
        with target.open("xb") as stream:
            stream.write(raw)
    evidence = {"worker": report, "execution": execution_record, "inputs": initial}
    evidence_path = receipt / "evidence.json"
    with evidence_path.open("xb") as stream:
        stream.write((json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode())
    summary = {
        "format": "buddha.review.nb02c3b-derived-rouge.v1",
        "source_sha256": worker.SOURCE_SHA,
        "wheel_sha256": sha(raw),
        "wheel_bytes": len(raw),
        "filename": worker.WHEEL_NAME,
        "repeat_sha256": report["repeat_sha256"],
        "image_id": execution.image_id,
        "cleanup_status": execution.cleanup_status,
        "toolchain": report["toolchain"],
        "source_date_epoch": report["source_date_epoch"],
        "hash_seed": report["hash_seed"],
        "builder_audit_sha256": sha(json.dumps(report["builder_audit"], sort_keys=True).encode()),
        "evidence_sha256": sha(evidence_path.read_bytes()),
        "evidence_path": evidence_path.relative_to(REPOSITORY).as_posix(),
        "source_files": snapshot,
        "wheel_inventory": inventory,
        "installation_enabled": False,
    }
    summary_path = receipt / "summary.json"
    with summary_path.open("xb") as stream:
        stream.write((json.dumps(summary, indent=2, sort_keys=True) + "\n").encode())
    print(
        json.dumps(
            {
                "wheel": str(target),
                "sha256": sha(raw),
                "bytes": len(raw),
                "repeat_equal": True,
                "summary": str(summary_path),
                "installation_enabled": False,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("self-test", "build"))
    args = parser.parse_args()
    builder = load_worker()
    if args.mode == "self-test":
        parser_checks(builder)
    else:
        build(builder)
