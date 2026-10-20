"""Offline release selection acceptance; no evaluator code or provider executes."""

import copy
import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from buddha.releases import (
    Release,
    ReleaseError,
    Selection,
    inventory,
    prepare_selection,
    verify_selection,
)


class ReleaseSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.roots = {
            name: self.root / name
            for name in ("official", "environment", "runner", "host", "agent")
        }
        for name, directory in self.roots.items():
            directory.mkdir()
            (directory / "identity.txt").write_text(name, encoding="utf-8")
        self.write("official", "src/evaluate.py", "raise RuntimeError('must not execute')\n")
        self.write("official", "uv.lock", "locked official dependencies")
        self.write("official", "data/tasks.jsonl", '{"id":"a","prompt":"say one digit"}\n')
        self.write("environment", "site-packages/nested/dependency.py", "VALUE = 'locked'\n")
        self.write("host", "capabilities/text.json", '{"interface":"ordered-text.v1"}')
        self.write("agent", "policy.json", '{"sampling":"independent","model":"fixed"}')
        self.capabilities = {"ordered-text.v1": "capabilities/text.json"}
        self.record = {
            "format": "buddha.benchmark-release.v1",
            "benchmark": "fixture",
            "release": "first",
            "upstream": {"url": "https://example.org/official", "revision": "a" * 40},
            "source": inventory(self.roots["official"]),
            "dependency_lock": "uv.lock",
            "task": {
                "dataset": "data/tasks.jsonl",
                "id_field": "id",
                "prompt_field": "prompt",
                "answers_field": "generations",
                "count": 10,
            },
            "commands": [{"module": "src.evaluate", "argv": ["--eval-dir", "{artifacts}"]}],
            "artifacts": {
                "answers": "generations.jsonl",
                "results": ["v1/results.jsonl"],
                "summary": "v1/summary.json",
            },
            "requires": ["ordered-text.v1"],
        }

    def write(self, component, relative, text):
        path = self.roots[component] / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def release(self, **changes):
        return Release.from_record(self.record | changes)

    def prepare(self, release=None, **changes):
        return prepare_selection(
            release or self.release(),
            self.roots,
            capabilities=changes.pop("capabilities", self.capabilities),
            **changes,
        )

    def test_real_nested_inventories_roundtrip_and_immutability(self):
        release = self.release()
        selection = self.prepare(release)
        self.assertEqual(selection.release_sha256, release.fingerprint())
        self.assertEqual(Selection.from_bytes(selection.to_bytes()), selection)
        self.assertEqual(Release.from_bytes(release.to_bytes()), release)
        self.assertIn(
            "site-packages/nested/dependency.py", selection.to_record()["components"]["environment"]
        )
        self.assertEqual(
            verify_selection(selection, self.roots, expected_sha256=selection.fingerprint()),
            selection.fingerprint(),
        )
        with self.assertRaises(FrozenInstanceError):
            selection.data = b"changed"
        exposed = selection.to_record()
        exposed["components"]["agent"].clear()
        self.assertTrue(selection.to_record()["components"]["agent"])
        self.record["task"]["count"] = 3
        self.assertEqual(release.to_record()["task"]["count"], 10)

    def test_other_compatible_release_configuration_keeps_agent_and_runner_identity(self):
        first = self.prepare()
        changed = copy.deepcopy(self.record)
        changed["release"] = "second"
        changed["task"].update(count=4, id_field="task_id", prompt_field="text")
        changed["artifacts"] = {
            "answers": "answers.jsonl",
            "results": ["new/rows.jsonl"],
            "summary": "new/report.json",
        }
        second = self.prepare(Release.from_record(changed))
        self.assertNotEqual(first.fingerprint(), second.fingerprint())
        self.assertEqual(first.agent_sha256, second.agent_sha256)
        self.assertEqual(
            first.to_record()["components"]["runner"], second.to_record()["components"]["runner"]
        )

    def test_unselected_installation_or_removal_does_not_invalidate_selection(self):
        selection = self.prepare()
        unused = self.root / "unselected-release"
        unused.mkdir()
        (unused / "driver.py").write_text("unrelated", encoding="utf-8")
        self.assertEqual(
            verify_selection(selection, self.roots, expected_sha256=selection.fingerprint()),
            selection.fingerprint(),
        )
        (unused / "driver.py").unlink()
        unused.rmdir()
        self.assertEqual(
            verify_selection(selection, self.roots, expected_sha256=selection.fingerprint()),
            selection.fingerprint(),
        )

    def test_every_selected_component_and_nested_dependency_drift_is_rejected(self):
        for role, relative in (
            ("official", "uv.lock"),
            ("official", "src/evaluate.py"),
            ("official", "data/tasks.jsonl"),
            ("environment", "site-packages/nested/dependency.py"),
            ("runner", "identity.txt"),
            ("host", "capabilities/text.json"),
            ("agent", "policy.json"),
        ):
            selection = self.prepare()
            path = self.roots[role] / relative
            original = path.read_bytes()
            with self.subTest(role=role, relative=relative):
                try:
                    path.write_bytes(original + b" changed")
                    with self.assertRaises(ReleaseError):
                        verify_selection(
                            selection, self.roots, expected_sha256=selection.fingerprint()
                        )
                finally:
                    path.write_bytes(original)

    def test_added_or_removed_selected_files_are_not_ignored(self):
        selection = self.prepare()
        extra = self.roots["environment"] / "extra.py"
        extra.write_text("unexpected importable code", encoding="utf-8")
        with self.assertRaises(ReleaseError):
            verify_selection(selection, self.roots, expected_sha256=selection.fingerprint())
        extra.unlink()
        (self.roots["agent"] / "policy.json").unlink()
        with self.assertRaises(ReleaseError):
            verify_selection(selection, self.roots, expected_sha256=selection.fingerprint())

    def test_official_source_seal_must_match_actual_complete_tree(self):
        self.write("official", "openai-api-key", "fake forbidden extra file")
        with self.assertRaises(ReleaseError):
            self.prepare()

    def test_unknown_capability_fails_before_file_reads_or_execution(self):
        release = self.release(requires=["unknown-paid-api.v1"])
        with patch("buddha.releases.inventory", side_effect=AssertionError("read too early")):
            with self.assertRaisesRegex(ReleaseError, "capabilit"):
                self.prepare(release)

    def test_capability_selection_is_host_data_bound_to_real_host_files(self):
        first = self.prepare()
        self.write("host", "capabilities/other.json", "another profile")
        selection = self.prepare()
        alternate = self.prepare(capabilities={"ordered-text.v1": "capabilities/other.json"})
        self.assertNotEqual(selection.fingerprint(), alternate.fingerprint())
        self.assertNotEqual(first.fingerprint(), selection.fingerprint())
        with self.assertRaises(ReleaseError):
            self.prepare(capabilities={"ordered-text.v1": "missing.json"})

    def test_manifest_content_and_source_revision_affect_release_identity(self):
        first = self.release().fingerprint()
        for changes in (
            {"upstream": self.record["upstream"] | {"revision": "b" * 40}},
            {"commands": [{"module": "src.evaluate", "argv": ["--different-setting"]}]},
            {"release": "different"},
        ):
            with self.subTest(changes=changes):
                self.assertNotEqual(first, self.release(**changes).fingerprint())

    def test_data_only_config_rejects_unknown_keys_wrong_types_and_unsafe_paths(self):
        bad = []
        for path in (
            "../escape",
            "/absolute",
            "C:/absolute",
            "a\\b",
            "a/./b",
            "a//b",
            "NUL.txt",
            "a/trailing.",
            "a\x00b",
        ):
            row = copy.deepcopy(self.record)
            row["artifacts"]["summary"] = path
            bad.append(row)
        for count in (True, 0, -1, 2.0):
            row = copy.deepcopy(self.record)
            row["task"]["count"] = count
            bad.append(row)
        bad.extend(
            (
                self.record | {"execute": "arbitrary command"},
                self.record | {"commands": [{"module": "os", "argv": []}]},
                self.record | {"commands": [{"module": "src.evaluate;bad", "argv": []}]},
                self.record | {"commands": [{"module": "src.evaluate", "argv": "shell"}]},
                self.record | {"requires": ["ordered-text.v1", "ordered-text.v1"]},
            )
        )
        for row in bad:
            with self.subTest(row=row):
                with self.assertRaises(ReleaseError):
                    Release.from_record(row)

    def test_duplicate_or_nonfinite_json_and_unknown_selection_fields_fail(self):
        raw = self.release().to_bytes()
        for value in (
            raw.replace(b'"first"', b"NaN"),
            b'{"format":1,"format":2}',
            b"\xff",
            b"[1]",
            b"[" * 2000,
        ):
            with self.subTest(value=value[:30]), self.assertRaises(ReleaseError):
                Release.from_bytes(value)
        record = self.prepare().to_record() | {"trusted": True}
        with self.assertRaises(ReleaseError):
            Selection.from_bytes(json.dumps(record).encode())

    def test_portable_case_aliases_and_artifact_collisions_are_rejected(self):
        source = self.record["source"] | {"SRC/evaluate.py": "f" * 64}
        with self.assertRaises(ReleaseError):
            self.release(source=source)
        artifacts = self.record["artifacts"] | {"summary": "generations.jsonl"}
        with self.assertRaises(ReleaseError):
            self.release(artifacts=artifacts)

    def test_windows_reserved_names_and_directory_case_aliases_are_rejected(self):
        for name in ("COM¹.txt", "COM².txt", "COM³.txt", "LPT¹.txt", "CONIN$", "CONOUT$"):
            for relative in (name, "nested/" + name):
                artifacts = self.record["artifacts"] | {"summary": relative}
                with self.subTest(relative=relative), self.assertRaises(ReleaseError):
                    self.release(artifacts=artifacts)
        source = self.record["source"] | {"Extra/a.py": "f" * 64, "extra/b.py": "e" * 64}
        with self.assertRaises(ReleaseError):
            self.release(source=source)

    def test_missing_or_overlapping_component_roots_fail(self):
        for roots in (
            self.roots | {"agent": self.roots["host"]},
            self.roots | {"runner": self.root},
            {key: value for key, value in self.roots.items() if key != "agent"},
        ):
            with self.subTest(roots=roots), self.assertRaises(ReleaseError):
                prepare_selection(self.release(), roots, capabilities=self.capabilities)

    def test_links_and_hard_link_aliases_are_rejected(self):
        target = self.roots["agent"] / "policy.json"
        link = self.roots["agent"] / "alias.json"
        try:
            os.link(target, link)
        except OSError:
            self.skipTest("host cannot create hard links")
        with self.assertRaises(ReleaseError):
            inventory(self.roots["agent"])

    def test_symlinked_file_or_parent_is_rejected(self):
        alias = self.root / "alias"
        try:
            alias.symlink_to(self.roots["agent"], target_is_directory=True)
        except OSError:
            self.skipTest("host cannot create symlinks")
        with self.assertRaises(ReleaseError):
            inventory(alias)

    def test_declared_but_unreadable_lock_dataset_or_module_cannot_be_selected(self):
        for field, value in (
            ("dependency_lock", "missing.lock"),
            ("task", self.record["task"] | {"dataset": "missing.jsonl"}),
        ):
            with self.subTest(field=field), self.assertRaises(ReleaseError):
                self.release(**{field: value})

    def test_selection_is_offline_and_does_not_execute_source_or_read_credentials(self):
        before = {
            path: path.read_bytes()
            for root in self.roots.values()
            for path in root.rglob("*")
            if path.is_file()
        }
        with (
            patch("socket.socket", side_effect=AssertionError("network forbidden")),
            patch("subprocess.Popen", side_effect=AssertionError("execution forbidden")),
            patch.dict(os.environ, {"OPENAI_API_KEY": "never-read-this-key"}),
        ):
            selected = self.prepare()
            verify_selection(selected, self.roots, expected_sha256=selected.fingerprint())
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertNotIn(b"never-read-this-key", selected.to_bytes())
        self.assertEqual(
            selected.agent_sha256,
            hashlib.sha256(
                json.dumps(
                    selected.to_record()["components"]["agent"],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
        )

    def test_consistently_edited_selection_is_denied_by_frozen_owner_identity(self):
        original = self.prepare()
        record = original.to_record()
        record["release"]["release"] = "changed-label"
        edited = Selection.from_bytes(json.dumps(record).encode())
        with patch("buddha.releases.inventory", side_effect=AssertionError("read too early")):
            with self.assertRaisesRegex(ReleaseError, "owner"):
                verify_selection(edited, self.roots, expected_sha256=original.fingerprint())

    def test_unreadable_directory_cannot_be_silently_omitted_from_inventory(self):
        blocked = self.roots["environment"] / "blocked"
        blocked.mkdir()
        (blocked / "hidden.py").write_text("must be inventoried", encoding="utf-8")
        scandir = os.scandir

        def denied(path):
            if Path(path) == blocked:
                raise PermissionError("denied selected subtree")
            return scandir(path)

        with patch("os.scandir", side_effect=denied):
            with self.assertRaises(ReleaseError):
                inventory(self.roots["environment"])

    def test_any_windows_reparse_file_is_denied_even_if_not_a_symlink_or_junction(self):
        target = self.roots["agent"] / "policy.json"
        lstat = Path.lstat

        def marked(path):
            value = lstat(path)
            if path != target:
                return value
            fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
            return SimpleNamespace(**(fields | {"st_file_attributes": 0x400}))

        with patch.object(Path, "lstat", marked):
            with self.assertRaises(ReleaseError):
                inventory(self.roots["agent"])

    def test_inventory_limits_entries_and_bytes_before_reading_large_files(self):
        for target, limit in (("MAX_FILES", 1), ("MAX_FILE_BYTES", 1), ("MAX_TREE_BYTES", 1)):
            with self.subTest(target=target), patch("buddha.releases." + target, limit):
                with self.assertRaises(ReleaseError):
                    inventory(self.roots["environment"])

    def test_handle_ctime_variation_does_not_reject_an_unchanged_file(self):
        expected = inventory(self.roots["agent"])
        fstat = os.fstat

        def different_ctime(descriptor):
            value = fstat(descriptor)
            fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
            return SimpleNamespace(**(fields | {"st_ctime_ns": value.st_ctime_ns + 1000}))

        with patch("os.fstat", side_effect=different_ctime):
            self.assertEqual(inventory(self.roots["agent"]), expected)

    def test_file_changed_during_hashing_is_rejected(self):
        target = self.roots["agent"] / "policy.json"
        original = target.read_bytes()
        sha256 = hashlib.sha256

        class MutatingHash:
            def __init__(self):
                self.inner = sha256()

            def update(self, block):
                self.inner.update(block)
                if block == original:
                    target.write_bytes(original + b"changed during read")

            def hexdigest(self):
                return self.inner.hexdigest()

        with patch("hashlib.sha256", MutatingHash):
            with self.assertRaises(ReleaseError):
                inventory(self.roots["agent"])

    def test_opened_file_identity_must_match_the_inventoried_path(self):
        fstat = os.fstat

        def different_identity(descriptor):
            value = fstat(descriptor)
            fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
            return SimpleNamespace(**(fields | {"st_ino": value.st_ino + 1}))

        with patch("os.fstat", side_effect=different_identity):
            with self.assertRaises(ReleaseError):
                inventory(self.roots["agent"])

    def test_unsupported_placeholders_are_data_errors_without_evaluation(self):
        for token in ("{arbitrary}", "prefix-{artifacts}", "${artifacts}"):
            commands = [{"module": "src.evaluate", "argv": [token]}]
            with self.subTest(token=token), self.assertRaises(ReleaseError):
                self.release(commands=commands)


if __name__ == "__main__":
    unittest.main()
