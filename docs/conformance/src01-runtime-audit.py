"""Read-only physical inventory for the separate SRC-01 stdlib runtime.

This helper neither loads candidate source nor supplies a model channel. The
immutable image remains the trust anchor; this measures its Python footprint.
"""

import hashlib
import json
import os
import platform
import re
import stat
import sys
from pathlib import Path

BASE = "python@sha256:3121f8b0804aa3698ab750d9a39ea4a42657a385c9b133722b915e55c51551a6"
VERSION = "3.13.12"
PYTHON = "python3.13"
BASE_LINKS = {
    "bin/idle": "idle3",
    "bin/idle3": "idle3.13",
    "bin/pydoc": "pydoc3",
    "bin/pydoc3": "pydoc3.13",
    "bin/python": "python3",
    "bin/python-config": "python3-config",
    "bin/python3": "python3.13",
    "bin/python3-config": "python3.13-config",
    "lib/libpython3.13.so": "libpython3.13.so.1.0",
    "lib/pkgconfig/python3-embed.pc": "python-3.13-embed.pc",
    "lib/pkgconfig/python3.pc": "python-3.13.pc",
    "man": "share/man",
    "share/man/man1/python3.1": "python3.13.1",
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def empty_directory(path, reason):
    require(path.is_dir() and not path.is_symlink() and not any(path.iterdir()), reason)


def inventory(root, links, external_targets=None):
    external_targets = external_targets or {}
    require(root.is_dir() and not root.is_symlink(), "root")
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        require(
            path.suffix not in {".whl", ".pth", ".pyc", ".pyo"}
            and path.stem not in {"sitecustomize", "usercustomize"},
            "dependency_artifact",
        )
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            target = os.readlink(path)
            require(relative in links and target == links[relative], "symlink")
            resolved = path.resolve(strict=True)
            require(
                resolved == external_targets[relative]
                if relative in external_targets
                else resolved.is_relative_to(root),
                "symlink",
            )
            entry = {"symlink": target, "target_is_directory": resolved.is_dir()}
            if resolved.is_file():
                entry["target_sha256"] = digest(resolved)
            result[relative] = entry
        elif stat.S_ISDIR(mode):
            result[relative] = {"directory": True}
        else:
            require(stat.S_ISREG(mode), "nonregular")
            result[relative] = {"sha256": digest(path), "bytes": path.stat().st_size}
    return result


def audit_layout(prefix, base, *, alternate_dirs=()):
    """Validate physical roots; the parameterized form also supports temp fixtures."""
    require(prefix.is_absolute() and base.is_absolute(), "root")
    require(not prefix.is_symlink() and not base.is_symlink(), "root")
    require(not prefix.is_relative_to(base) and not base.is_relative_to(prefix), "root")
    for root in (base, prefix):
        empty_directory(root / "lib/python3.13/site-packages", "site_packages")
        for path in (root / "lib").glob("python*"):
            require(path.name == PYTHON, "alternate_interpreter")
        require(not any((root / "bin").glob("pip*")), "dependency_artifact")
    bundled = base / "lib/python3.13/ensurepip/_bundled"
    require(
        not bundled.exists() or (bundled.is_dir() and not any(bundled.iterdir())),
        "dependency_artifact",
    )
    config_path = prefix / "pyvenv.cfg"
    require(not config_path.is_symlink(), "venv_config")
    config = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        require(separator and key.strip() not in config, "venv_config")
        config[key.strip()] = value.strip()
    require(
        config.get("home") == str(base / "bin")
        and config.get("include-system-site-packages") == "false"
        and config.get("version") == VERSION,
        "venv_config",
    )
    binary = base / "bin/python3.13"
    require(binary.is_file() and not binary.is_symlink(), "interpreter")
    binary_sha = digest(binary)
    for root in (base / "bin", prefix / "bin", *alternate_dirs):
        if not root.exists():
            continue
        for path in root.iterdir():
            if not re.match(r"(?:python|pypy)", path.name):
                continue
            allowed = {"python", "python3", PYTHON}
            if root == base / "bin":
                allowed |= {"python-config", "python3-config", "python3.13-config"}
            require(root not in alternate_dirs and path.name in allowed, "alternate_interpreter")
            if path.name in {"python", "python3", PYTHON}:
                if path.is_symlink():
                    require(path.resolve(strict=True) == binary, "symlink")
                else:
                    require(path.is_file() and digest(path) == binary_sha, "interpreter")
    require((prefix / "bin/python").is_file(), "interpreter")
    base_inventory = inventory(base, BASE_LINKS)
    # Venv interpreter aliases may leave the venv only for the measured binary.
    # Everything else must stay within the venv and match the known lib64 alias.
    venv_links = {"lib64": "lib"}
    for name in ("python", "python3", PYTHON):
        path = prefix / "bin" / name
        if path.is_symlink():
            target = os.readlink(path)
            require(path.resolve(strict=True) == binary, "symlink")
            require(
                target
                in {
                    "python",
                    "python3",
                    PYTHON,
                    str(base / "bin/python"),
                    str(base / "bin/python3"),
                    str(binary),
                },
                "symlink",
            )
            venv_links["bin/" + name] = target
    venv_inventory = inventory(
        prefix,
        venv_links,
        {relative: binary for relative in venv_links if relative != "lib64"},
    )
    return {
        "base_inventory": base_inventory,
        "venv_inventory": venv_inventory,
        "interpreter_sha256": binary_sha,
        "site_packages": {"base": [], "venv": []},
    }


def collect_audit():
    require(sys.platform == "linux" and platform.machine() == "x86_64", "platform")
    require(platform.python_version() == VERSION, "version")
    require(sys.prefix == "/opt/venv" and sys.base_prefix == "/usr/local", "prefix")
    require(sys.executable == "/opt/venv/bin/python", "executable")
    prefix, base = Path(sys.prefix), Path(sys.base_prefix)
    result = audit_layout(prefix, base, alternate_dirs=(Path("/usr/bin"), Path("/bin")))
    for parent in (Path("/usr/lib"), Path("/usr/local/lib")):
        for root in parent.glob("python*"):
            for name in ("site-packages", "dist-packages"):
                path = root / name
                if path.exists():
                    empty_directory(path, "site_packages")
    result.update(
        format="buddha.src01-stdlib-runtime.v1",
        base=BASE,
        python=sys.version,
        executable=sys.executable,
        prefix=sys.prefix,
        base_prefix=sys.base_prefix,
        os_release=Path("/etc/os-release").read_text(encoding="utf-8"),
    )
    return result


if __name__ == "__main__":
    print(json.dumps(collect_audit(), sort_keys=True, separators=(",", ":")))
