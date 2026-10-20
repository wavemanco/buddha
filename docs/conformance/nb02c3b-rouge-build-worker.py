"""Reviewed, offline ROUGE wheel builder for the existing confined executor."""

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile
import zlib
from pathlib import Path

SOURCE_SHA = "c7d4da2683e68c9abf0135ef915d63a46643666f848e558a1b9f7ead17ff0f04"
WHEEL_NAME = "rouge_score-0.1.2-py3-none-any.whl"
MAX_WHEEL = 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def portable(name):
    parts = name.rstrip("/").split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        prefix + str(index) for prefix in ("COM", "LPT") for index in range(1, 10)
    }
    if not parts or any(
        not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part)
        or part.endswith(".")
        or part.split(".")[0].upper() in reserved
        for part in parts
    ):
        raise ValueError("nonportable archive member")
    return parts


def sources(raw, expected):
    """Read a bounded tar.gz as data, rejecting aliases, links and special files."""
    if len(raw) > 1024 * 1024 or sha(raw) != expected:
        raise ValueError("source archive seal differs")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    decoded = decoder.decompress(raw, 256 * 1024 + 1)
    if len(decoded) > 256 * 1024 or not decoder.eof or decoder.unused_data:
        raise ValueError("source gzip framing or byte bound differs")
    files, seen, prefixes, count, total = {}, {}, {}, 0, 0
    with tarfile.open(fileobj=io.BytesIO(decoded), mode="r:") as archive:
        for member in archive:
            count += 1
            parts = portable(member.name)
            if count > 64 or parts[0] != "rouge_score-0.1.2":
                raise ValueError("source archive root/count differs")
            if member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE}:
                raise ValueError("source archive contains links or special files")
            name, key = "/".join(parts), "/".join(parts).casefold()
            if key in seen or any(
                seen.get("/".join(parts[:index]).casefold()) == "file"
                for index in range(1, len(parts))
            ):
                raise ValueError("duplicate or file ancestor")
            if member.isfile() and any(value.startswith(key + "/") for value in seen):
                raise ValueError("file replaces an ancestor directory")
            for index in range(1, len(parts) + 1):
                prefix = "/".join(parts[:index])
                if prefixes.get(prefix.casefold(), prefix) != prefix:
                    raise ValueError("case alias")
                prefixes[prefix.casefold()] = prefix
            seen[key] = "file" if member.isfile() else "directory"
            if member.isfile():
                total += member.size
                if member.size < 0 or member.size > 64 * 1024 or total > 128 * 1024:
                    raise ValueError("source member byte bound exceeded")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("source member unavailable")
                with stream:
                    content = stream.read(64 * 1024 + 1)
                if len(content) != member.size:
                    raise ValueError("source member size differs")
                files[name] = content
    return files, count, total


def run(argv, *, cwd=None, env=None):
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=30, check=True)
    if len(result.stdout) + len(result.stderr) > 2 * 1024 * 1024:
        raise ValueError("build diagnostics exceed bound")
    return result.stdout


def builder_member(name):
    from buddha.releases import _path

    return _path(name).split("/")


def main():
    sys.path.insert(0, "/runner")
    from buddha import channel

    initial = channel.read_frame(sys.stdin.buffer)
    if (
        set(initial) != {"format", "inputs", "runner"}
        or initial["format"] != "buddha.rouge-build.v1"
    ):
        raise ValueError("build configuration differs")
    for root, values in (("/inputs", initial["inputs"]), ("/runner", initial["runner"])):
        if set(values) != {
            path.relative_to(root).as_posix() for path in Path(root).rglob("*") if path.is_file()
        }:
            raise ValueError("build input inventory differs")
        for name, expected in values.items():
            portable(name)
            if sha((Path(root) / name).read_bytes()) != expected:
                raise ValueError("build input seal differs")
    raw = Path("/inputs/rouge_score-0.1.2.tar.gz").read_bytes()
    files, count, total = sources(raw, SOURCE_SHA)
    if count != 26 or total != 75835:
        raise ValueError("sealed source inventory differs")
    python = ["/usr/local/bin/python", "-I", "-B", "-X", "pycache_prefix=/__absent_bytecode_cache"]
    run(python + ["-m", "venv", "--without-pip", "--symlinks", "/scratch/builder"])
    builder = Path("/scratch/builder/bin/python")
    if not builder.is_symlink() or builder.resolve() != Path("/usr/local/bin/python3.13"):
        raise ValueError("builder interpreter is not the immutable base symlink")
    run(
        python
        + [
            "-m",
            "pip",
            "--isolated",
            "--python",
            str(builder),
            "install",
            "--no-index",
            "--find-links=/inputs",
            "--no-deps",
            "--no-compile",
            "--no-cache-dir",
            "--require-hashes",
            "-r",
            "/inputs/builder-requirements.txt",
        ]
    )
    builder_python = [str(builder), *python[1:]]
    audit_before = json.loads(run(builder_python + ["/opt/runtime-prepare.py", "audit"]))
    # Independently compare installed source files with the sealed original wheel.
    setuptools = Path("/inputs/setuptools-79.0.1-py3-none-any.whl")
    if sha(setuptools.read_bytes()) != initial["inputs"][setuptools.name]:
        raise ValueError("builder wheel changed")
    with zipfile.ZipFile(setuptools) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith(".dist-info/RECORD"):
                continue
            parts = builder_member(info.filename)
            target = Path("/scratch/builder/lib/python3.13/site-packages", *parts)
            if sha(target.read_bytes()) != sha(archive.read(info)):
                raise ValueError("installed builder file differs from sealed wheel")
    built, commands = [], []
    for label in ("a", "b"):
        source_root = Path("/scratch/source-" + label)
        source_root.mkdir()
        for name, content in files.items():
            target = source_root.joinpath(*portable(name))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(content)
        argv = builder_python + [
            "setup.py",
            "bdist_wheel",
            "--dist-dir",
            "/scratch/dist-" + label,
            "--bdist-dir",
            "/scratch/build-" + label,
        ]
        commands.append(argv)
        run(
            argv,
            cwd=source_root / "rouge_score-0.1.2",
            env=os.environ | {"SOURCE_DATE_EPOCH": "1704067200", "TZ": "UTC"},
        )
        output = Path("/scratch/dist-" + label)
        if [path.name for path in output.iterdir()] != [WHEEL_NAME]:
            raise ValueError("unexpected build output")
        content = (output / WHEEL_NAME).read_bytes()
        if not 0 < len(content) <= MAX_WHEEL:
            raise ValueError("wheel byte bound exceeded")
        built.append(content)
    audit_after = json.loads(run(builder_python + ["/opt/runtime-prepare.py", "audit"]))
    if built[0] != built[1] or audit_before != audit_after:
        raise ValueError("independent source builds or shared toolchain differ")
    toolchain = json.loads(
        run(
            python
            + [
                "-c",
                "import importlib.metadata,json,sys; "
                "print(json.dumps({'python':sys.version,'pip':importlib.metadata.version('pip')}))",
            ]
        )
    )
    report = {
        "format": "buddha.rouge-build-result.v1",
        "source_sha256": SOURCE_SHA,
        "source_member_count": count,
        "source_file_bytes": total,
        "build_commands": commands,
        "toolchain": toolchain,
        "builder_audit": audit_after,
        "source_date_epoch": 1704067200,
        "hash_seed": "randomized under -I; no deterministic seed claim",
        "shared_builder_environment": True,
        "independent_source_and_build_directories": True,
        "wheel_name": WHEEL_NAME,
        "wheel_sha256": sha(built[0]),
        "wheel_bytes": len(built[0]),
        "repeat_sha256": [sha(value) for value in built],
    }
    channel.write_frame(sys.stdout.buffer, {"type": "result", "report": report})
    channel.write_frame(
        sys.stdout.buffer,
        {
            "type": "wheel",
            "name": WHEEL_NAME,
            "data_base64": base64.b64encode(built[0]).decode("ascii"),
        },
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        details = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            details += "\n" + (error.stderr or b"")[-4096:].decode("utf-8", errors="replace")
        print(
            json.dumps(
                {"type": "error", "error_type": type(error).__name__, "details": details[-8192:]}
            ),
            flush=True,
        )
        raise SystemExit(1) from None
