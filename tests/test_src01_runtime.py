"""Portable checks for the physically stripped SRC-01 runtime audit."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "docs/conformance/src01-runtime-audit.py"


def load_helper():
    module = ModuleType("src01_runtime_audit")
    module.__file__ = str(HELPER)
    exec(compile(HELPER.read_bytes(), str(HELPER), "exec"), module.__dict__)
    return module


class SourceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        # Windows readlink returns the verbatim namespace. Keep the entire
        # fixture in that namespace; the Linux audit's raw-target check stays exact.
        if os.name == "nt" and not str(self.root).startswith("\\\\?\\"):
            name = str(self.root)
            self.root = Path(
                "\\\\?\\UNC\\" + name[2:] if name.startswith("\\\\") else "\\\\?\\" + name
            )
        self.base = self.root / "base"
        self.prefix = self.root / "venv"
        for root in (self.base, self.prefix):
            (root / "bin").mkdir(parents=True)
            (root / "lib/python3.13/site-packages").mkdir(parents=True)
        (self.base / "bin/python3.13").write_bytes(b"literal interpreter fixture")
        (self.prefix / "bin/python").write_bytes(b"literal interpreter fixture")
        (self.base / "lib/python3.13/ensurepip/_bundled").mkdir(parents=True)
        (self.base / "lib/python3.13/os.py").write_bytes(b"literal stdlib fixture")
        (self.prefix / "pyvenv.cfg").write_text(
            "home = " + str(self.base / "bin") + "\n"
            "include-system-site-packages = false\nversion = 3.13.12\n",
            encoding="utf-8",
        )
        self.helper = load_helper()

    def test_empty_sites_and_literal_inventory_are_measured(self):
        value = self.helper.audit_layout(self.prefix, self.base)
        self.assertEqual(value["site_packages"], {"base": [], "venv": []})
        self.assertEqual(
            value["base_inventory"]["lib/python3.13/os.py"]["sha256"],
            hashlib.sha256(b"literal stdlib fixture").hexdigest(),
        )
        self.assertEqual(value, self.helper.audit_layout(self.prefix, self.base))

    def test_physical_package_files_fail_even_without_import(self):
        for label, root in (("base", self.base), ("venv", self.prefix)):
            with self.subTest(root=label):
                path = root / "lib/python3.13/site-packages/.hidden.pth"
                path.write_bytes(b"not imported in isolated mode")
                with self.assertRaisesRegex(RuntimeError, "site_packages"):
                    self.helper.audit_layout(self.prefix, self.base)
                path.unlink()

    def test_bundled_wheels_and_pip_launchers_are_rejected(self):
        for path in (
            self.base / "lib/python3.13/ensurepip/_bundled/pip.whl",
            self.base / "bin/pip3",
            self.prefix / "bin/pip",
        ):
            with self.subTest(path=path.name):
                path.write_bytes(b"unavailable deployment dependency")
                with self.assertRaisesRegex(RuntimeError, "dependency_artifact"):
                    self.helper.audit_layout(self.prefix, self.base)
                path.unlink()

    def test_hidden_customization_wheels_and_bytecode_are_rejected(self):
        for name in ("sitecustomize.py", "usercustomize.pyc", "archive.whl", "extra.pth"):
            with self.subTest(name=name):
                path = self.base / "lib/python3.13" / name
                path.write_bytes(b"not reached by isolated import lookup")
                with self.assertRaisesRegex(RuntimeError, "dependency_artifact"):
                    self.helper.audit_layout(self.prefix, self.base)
                path.unlink()

    def test_alternative_interpreters_are_rejected(self):
        for path in (self.base / "bin/python3.12", self.prefix / "bin/pypy3"):
            with self.subTest(path=path.name):
                path.write_bytes(b"alternate interpreter")
                with self.assertRaisesRegex(RuntimeError, "alternate_interpreter"):
                    self.helper.audit_layout(self.prefix, self.base)
                path.unlink()
        alternate = self.root / "system-bin"
        alternate.mkdir()
        (alternate / "python3").write_bytes(b"alternate system interpreter")
        with self.assertRaisesRegex(RuntimeError, "alternate_interpreter"):
            self.helper.audit_layout(self.prefix, self.base, alternate_dirs=(alternate,))

    def test_system_site_visibility_and_wrong_version_are_rejected(self):
        config = self.prefix / "pyvenv.cfg"
        original = config.read_text(encoding="utf-8")
        for bad in (
            original.replace("false", "true"),
            original.replace("3.13.12", "3.12.0"),
            original.replace(str(self.base / "bin"), str(self.root / "other")),
        ):
            with self.subTest(config=bad):
                config.write_text(bad, encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "venv_config"):
                    self.helper.audit_layout(self.prefix, self.base)
        config.write_text(original, encoding="utf-8")

    def symlink(self, target, path, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except OSError:
            self.skipTest("symlink creation requires platform privileges")

    def test_venv_interpreter_cannot_escape_the_pinned_base(self):
        external = self.root / "external-python"
        external.write_bytes(b"another binary")
        (self.prefix / "bin/python").unlink()
        self.symlink(external, self.prefix / "bin/python")
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.helper.audit_layout(self.prefix, self.base)

    def test_site_root_and_unexpected_nested_symlinks_are_rejected(self):
        site = self.prefix / "lib/python3.13/site-packages"
        site.rmdir()
        self.symlink(self.base / "lib/python3.13/site-packages", site, directory=True)
        with self.assertRaisesRegex(RuntimeError, "site_packages"):
            self.helper.audit_layout(self.prefix, self.base)

    def test_unknown_tree_symlink_is_rejected_even_with_safe_target(self):
        self.symlink("os.py", self.base / "lib/python3.13/extra.py")
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.helper.audit_layout(self.prefix, self.base)

    def test_supported_interpreter_alias_is_bound_to_actual_binary(self):
        (self.prefix / "bin/python").unlink()
        self.symlink(self.base / "bin/python3.13", self.prefix / "bin/python")
        self.assertEqual(os.readlink(self.prefix / "bin/python"), str(self.base / "bin/python3.13"))
        value = self.helper.audit_layout(self.prefix, self.base)
        self.assertEqual(
            value["venv_inventory"]["bin/python"]["target_sha256"],
            hashlib.sha256(b"literal interpreter fixture").hexdigest(),
        )


class RuntimeProbeTests(unittest.TestCase):
    def test_changed_recipe_is_rejected_before_any_container_execution(self):
        path = ROOT / "docs/conformance/src01-runtime-probe.py"
        module = ModuleType("src01_runtime_probe")
        module.__file__ = str(path)
        exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
        runtime = {
            "format": "buddha.src01-runtime-environment.v1",
            "base": module.BASE,
            "audit_helper": {
                "path": "/opt/runtime-audit.py",
                "sha256": hashlib.sha256(HELPER.read_bytes()).hexdigest(),
            },
            "build_context_sha256": {
                "Dockerfile": "0" * 64,
                "runtime-audit.py": hashlib.sha256(HELPER.read_bytes()).hexdigest(),
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            environment = Path(temporary) / "environment.json"
            environment.write_text(json.dumps(runtime), encoding="utf-8")
            output = ROOT / "src01-provenance-test-unused.json"
            self.assertFalse(output.exists())
            with patch.object(
                module, "fresh_audit", side_effect=AssertionError("container reached")
            ):
                with self.assertRaisesRegex(RuntimeError, "environment_recipe_identity"):
                    module.probe(environment, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
