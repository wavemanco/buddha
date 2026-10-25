"""Fresh, unfunded v4 handoff checks use real validators and synthetic data only."""

import copy
import errno
import hashlib
import json
import stat
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from buddha.releases import ReleaseError, _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def files(root):
    return {str(path): sha(path.read_bytes()) for path in root.rglob("*") if path.is_file()}


class ImproverHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Honest missing-API RED precedes fixture bootstrap, SQL and supplied workers.
        import test_improver_assessment as assessment_fixtures

        from buddha import improver_handoff

        cls.api = improver_handoff
        cls.Error = improver_handoff.ImproverHandoffError
        cls.fixture = assessment_fixtures.ImproverAssessmentTests("runTest")
        cls.addClassCleanup(cls.fixture.doCleanups)
        cls.fixture.setUp()
        cls.development, cls.definition = cls.fixture.capacity_definition()
        cls.root = cls.fixture.root

    def setUp(self):
        self.serial = 0
        self.case = self.root / ("handoff-" + self._testMethodName)
        self.case.mkdir()

    def bundle(self, *, definition=None, pretty=False, extra_pins=0):
        self.serial += 1
        root = self.case / str(self.serial)
        root.mkdir()
        definition = copy.deepcopy(self.definition if definition is None else definition)
        assessment = root / "assessment.json"
        assessment.write_bytes(
            json.dumps(definition, indent=2).encode() if pretty else _json(definition)
        )
        extra = root / "extra.txt"
        extra.write_bytes(b"Unfunded synthetic handoff input.\n")
        sources = {str(path): sha(path.read_bytes()) for path in self.api._sources()}
        sources[str(extra)] = sha(extra.read_bytes())
        for index in range(extra_pins):
            path = root / ("extra-" + str(index) + ".txt")
            path.write_bytes(b"Synthetic capacity input.\n")
            sources[str(path)] = sha(path.read_bytes())
        record = {
            "format": "buddha.improver-handoff.v1",
            "assessment": {"path": str(assessment), "sha256": sha(assessment.read_bytes())},
            "expected_runtime_sha256": self.fixture.engine.candidate.expected_runtime,
            "directory": str(root / "trial"),
            "source_sha256": sources,
        }
        path = root / "handoff.json"
        path.write_bytes(_json(record))
        return path, record, definition, extra

    def write(self, path, record):
        path.write_bytes(_json(record))

    def check(self, path, *, expected=None):
        return self.api.check_improver_handoff(
            path, expected_sha256=sha(path.read_bytes()) if expected is None else expected
        )

    @contextmanager
    def no_execution(self):
        # Fixture bootstrap happens once outside this boundary. The checker must
        # neither initialize storage nor launch/compile selected code or request keys.
        with ExitStack() as stack:
            for target in (
                "sqlite3.connect",
                "getpass.getpass",
                "socket.socket",
                "subprocess.Popen",
                "subprocess.run",
                "ast.parse",
                "buddha.authorization.Authorization.create",
                "buddha.executor.run_container",
                "buddha.gateway.RawHTTPTransport.prepare",
            ):
                stack.enter_context(
                    patch(target, side_effect=AssertionError("execution forbidden"))
                )
            yield

    def refused(self, path, *, expected=None):
        before = files(self.root)
        with self.no_execution(), self.assertRaises(self.Error):
            self.check(path, expected=expected)
        self.assertEqual(files(self.root), before)

    def test_readonly_v4_checks_original_bindings_and_returns_detached_data(self):
        from buddha import improver_study, validation_study

        path, record, definition, extra = self.bundle(pretty=True)
        before = files(self.root)
        with (
            self.no_execution(),
            patch.object(
                improver_study, "_capacity", wraps=improver_study._capacity
            ) as development,
            patch.object(validation_study, "_capacity", wraps=validation_study._capacity) as final,
        ):
            report = self.check(path)
        self.assertGreater(development.call_count, 0)
        self.assertGreater(final.call_count, 0)
        self.assertEqual(files(self.root), before)
        self.assertFalse(Path(record["directory"]).exists())
        self.assertEqual(report["format"], "buddha.improver-handoff-check.v1")
        self.assertEqual(report["status"], "configuration_checked")
        self.assertEqual(report["funding"], {"status": "unallocated"})
        self.assertEqual(report["assessment_sha256"], record["assessment"]["sha256"])
        self.assertEqual(report["definition_sha256"], sha(_json(definition)))
        self.assertNotEqual(report["assessment_sha256"], report["definition_sha256"])
        self.assertEqual(report["directory"], record["directory"])
        self.assertEqual(report["requested_phase_limits"], definition["phase_limits"])
        self.assertEqual(report["requested_totals"], {"budget_microusd": 2, "max_calls": 2})
        self.assertEqual(
            report["planned"],
            {
                "starts": 1,
                "development_repetitions": 1,
                "opportunities_per_arm": 1,
                "development_tasks": 1,
                "final_tasks": 2,
                "sealed_repetitions": 1,
                "maximum_final_cells": 6,
            },
        )
        for source, digest in record["source_sha256"].items():
            self.assertEqual(report["reviewed_bindings"][source], digest)
        for reference in (record["assessment"], definition["development"]):
            self.assertEqual(report["reviewed_bindings"][reference["path"]], reference["sha256"])
        self.assertEqual(report["reviewed_bindings"][str(path)], sha(path.read_bytes()))
        self.assertTrue(report["limitations"])
        self.assertTrue(all(isinstance(value, str) and value for value in report["limitations"]))
        pristine = copy.deepcopy(report)
        report["requested_phase_limits"]["search"]["max_calls"] = 999
        report["requested_totals"]["max_calls"] = 999
        report["planned"]["starts"] = 999
        report["reviewed_bindings"][str(extra)] = "0" * 64
        report["limitations"].clear()
        with self.no_execution():
            self.assertEqual(self.check(path), pristine)
        self.assertEqual(files(self.root), before)

    def test_raw_digest_strict_json_and_canonical_descriptor_paths(self):
        for case in (
            "wrong_raw",
            "duplicate",
            "extra_field",
            "missing_field",
            "format",
            "alias",
            "self",
        ):
            with self.subTest(case=case):
                path, record, _, extra = self.bundle()
                expected = None
                if case == "wrong_raw":
                    expected = "0" * 64
                elif case == "duplicate":
                    path.write_bytes(
                        path.read_bytes()[:-1] + b',"format":"buddha.improver-handoff.v1"}'
                    )
                else:
                    if case == "extra_field":
                        record["extra"] = True
                    elif case == "missing_field":
                        del record["expected_runtime_sha256"]
                    elif case == "format":
                        record["format"] = "buddha.improver-handoff.v0"
                    elif case == "alias":
                        nested = extra.parent / "nested"
                        nested.mkdir()
                        record["source_sha256"][str(nested / ".." / extra.name)] = record[
                            "source_sha256"
                        ].pop(str(extra))
                    elif case == "self":
                        record["source_sha256"][str(path)] = "0" * 64
                    self.write(path, record)
                self.refused(path, expected=expected)

    def test_required_extra_and_selected_component_drift_are_refused(self):
        for case in (
            "missing_required",
            "stale_required",
            "missing_extra",
            "stale_extra",
            "selected",
        ):
            with self.subTest(case=case):
                path, record, definition, extra = self.bundle()
                source = next(iter(self.api._sources()))
                changed, original = None, None
                if case == "missing_required":
                    del record["source_sha256"][str(source)]
                elif case == "stale_required":
                    record["source_sha256"][str(source)] = "0" * 64
                elif case == "missing_extra":
                    extra.unlink()
                elif case == "stale_extra":
                    extra.write_bytes(b"Changed fixture-local input.\n")
                else:
                    changed = Path(definition["generation"]["roots"]["agent"]) / "candidate.py"
                    original = changed.read_bytes()
                    changed.write_bytes(original + b"\n# component drift\n")
                self.write(path, record)
                try:
                    self.refused(path)
                finally:
                    if changed is not None:
                        changed.write_bytes(original)

    def test_original_references_versions_and_phase_semantics_are_required(self):
        for case in (
            "assessment_ref",
            "development_ref",
            "assessment_version",
            "development_version",
            "phase",
        ):
            with self.subTest(case=case):
                definition = copy.deepcopy(self.definition)
                if case == "development_ref":
                    definition["development"]["sha256"] = "0" * 64
                elif case == "assessment_version":
                    definition["format"] = "buddha.improver-assessment-trial.v3"
                elif case == "development_version":
                    changed = copy.deepcopy(self.development)
                    changed["format"] = "buddha.improver-study.v3"
                    reference = self.case / "old-development.json"
                    reference.write_bytes(_json(changed))
                    definition["development"] = {
                        "path": str(reference),
                        "sha256": sha(reference.read_bytes()),
                    }
                elif case == "phase":
                    definition["phase_limits"]["validation"]["max_calls"] = 1
                path, record, _, _ = self.bundle(definition=definition)
                if case == "assessment_ref":
                    record["assessment"]["sha256"] = "0" * 64
                    self.write(path, record)
                self.refused(path)

    def test_existing_overlapping_and_overcapacity_destinations_refuse_before_owner(self):
        for case in ("existing", "inside_selected", "contains_selected", "capacity"):
            with self.subTest(case=case):
                count = 1023 - len(self.api._sources()) - 1 if case == "capacity" else 0
                path, record, definition, _ = self.bundle(extra_pins=count)
                if case == "existing":
                    Path(record["directory"]).mkdir()
                elif case == "inside_selected":
                    record["directory"] = str(
                        Path(definition["generation"]["roots"]["agent"]) / "new-trial"
                    )
                elif case == "contains_selected":
                    record["directory"] = str(self.root)
                self.write(path, record)
                self.refused(path)

    def test_fresh_destination_cannot_be_inside_distinct_final_generation_component(self):
        from buddha import improver_assessment, validation_study

        definition = copy.deepcopy(self.definition)
        generation = definition["generation"]
        original = Path(generation["roots"]["agent"]) / "candidate.py"
        selected_root = self.case / "final-only-agent"
        selected_root.mkdir()
        (selected_root / "candidate.py").write_bytes(original.read_bytes())
        generation["roots"]["agent"] = str(selected_root)
        generation["executor"]["mounts"] = [
            [target, str(selected_root) if target == "/agent" else host]
            for target, host in generation["executor"]["mounts"]
        ]
        path, record, _, _ = self.bundle(definition=definition)
        record["directory"] = str(selected_root / "new-trial")
        self.write(path, record)
        runtime = record["expected_runtime_sha256"]
        with self.no_execution():
            state = improver_assessment._definition(_json(definition), runtime, active=False)
            validation_study._validate_execution(
                state["record"], state["tasks"], runtime, active=True
            )
        self.refused(path)

    def test_late_original_pin_changes_are_rechecked_after_real_execution_validation(self):
        from buddha import validation_study

        for case in ("extra", "assessment", "directory", "component_extra"):
            with self.subTest(case=case):
                path, record, definition, extra = self.bundle()
                changed = (
                    extra
                    if case == "extra"
                    else Path(record["assessment"]["path"])
                    if case == "assessment"
                    else Path(record["directory"])
                    if case == "directory"
                    else Path(definition["generation"]["roots"]["agent"]) / "late-undeclared.txt"
                )
                original = changed.read_bytes() if case in {"extra", "assessment"} else None
                validate = validation_study._validate_execution
                mutated = [False]

                def drift(
                    *args,
                    _validate=validate,
                    _changed=changed,
                    _original=original,
                    _case=case,
                    _mutated=mutated,
                    **kwargs,
                ):
                    result = _validate(*args, **kwargs)
                    if kwargs.get("active", True) and not _mutated[0]:
                        _mutated[0] = True
                        if _case == "directory":
                            _changed.mkdir()
                        else:
                            _changed.write_bytes(
                                _original + b"\n"
                                if _original is not None
                                else b"Undeclared synthetic component entry.\n"
                            )
                    return result

                try:
                    with (
                        self.no_execution(),
                        patch.object(validation_study, "_validate_execution", side_effect=drift),
                        self.assertRaises(self.Error),
                    ):
                        self.check(path)
                    self.assertTrue(mutated[0])
                    self.assertEqual(Path(record["directory"]).exists(), case == "directory")
                finally:
                    if original is not None:
                        changed.write_bytes(original)
                    elif changed.exists():
                        if case == "directory":
                            changed.rmdir()
                        else:
                            changed.unlink()

    def test_late_output_parent_reparse_is_refused_with_fresh_leaf(self):
        from buddha import validation_study

        path, record, _, _ = self.bundle()
        parent = self.case / "output-parent"
        parent.mkdir()
        directory = parent / "trial"
        record["directory"] = str(directory)
        self.write(path, record)
        active = [False]
        lstat = Path.lstat
        validate = validation_study._validate_execution

        def marked(candidate):
            value = lstat(candidate)
            if candidate != parent or not active[0]:
                return value
            fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
            return SimpleNamespace(**(fields | {"st_file_attributes": 0x400}))

        def late_reparse(*args, **kwargs):
            result = validate(*args, **kwargs)
            if kwargs.get("active", True) and not active[0]:
                active[0] = True
            return result

        try:
            with (
                self.no_execution(),
                patch.object(Path, "lstat", marked),
                patch.object(validation_study, "_validate_execution", side_effect=late_reparse),
                self.assertRaises(self.Error),
            ):
                self.check(path)
        finally:
            self.assertTrue(active[0])
            self.assertFalse(directory.exists())

    def test_distinct_final_component_alias_cannot_hide_output_overlap(self):
        from buddha import improver_assessment, validation_study

        definition = copy.deepcopy(self.definition)
        generation = definition["generation"]
        original = Path(generation["roots"]["agent"]) / "candidate.py"
        selected_root = self.case / "final-agent"
        selected_root.mkdir()
        (selected_root / "candidate.py").write_bytes(original.read_bytes())
        spelling = self.case / "spelling"
        spelling.mkdir()
        alias = spelling / ".." / selected_root.name
        generation["roots"]["agent"] = str(alias)
        generation["executor"]["mounts"] = [
            [target, str(alias) if target == "/agent" else host]
            for target, host in generation["executor"]["mounts"]
        ]
        path, record, _, _ = self.bundle(definition=definition)
        record["directory"] = str(selected_root / "new-trial")
        self.write(path, record)
        runtime = record["expected_runtime_sha256"]
        self.final_alias_active_validation_accepted = False
        with self.no_execution():
            try:
                state = improver_assessment._definition(_json(definition), runtime, active=False)
                validation_study._validate_execution(
                    state["record"], state["tasks"], runtime, active=True
                )
            except ReleaseError:
                pass
            else:
                self.final_alias_active_validation_accepted = True
        self.refused(path)

    def test_initial_and_late_dangling_junction_entries_are_not_fresh_destinations(self):
        from buddha import validation_study

        for delayed in (False, True):
            with self.subTest(delayed=delayed):
                path, record, _, _ = self.bundle()
                directory = Path(record["directory"])
                active = [not delayed]
                if not delayed:
                    directory.mkdir()
                real_stat, real_lstat = Path.stat, Path.lstat
                validate = validation_study._validate_execution

                def following_stat(
                    candidate,
                    *,
                    follow_symlinks=True,
                    _directory=directory,
                    _active=active,
                    _stat=real_stat,
                ):
                    if candidate == _directory and _active[0] and follow_symlinks:
                        raise FileNotFoundError(
                            errno.ENOENT, "synthetic dangling target", candidate
                        )
                    return _stat(candidate, follow_symlinks=follow_symlinks)

                def entry_stat(candidate, _directory=directory, _active=active, _lstat=real_lstat):
                    value = _lstat(candidate)
                    if candidate != _directory or not _active[0]:
                        return value
                    fields = {
                        name: getattr(value, name) for name in dir(value) if name.startswith("st_")
                    }
                    return SimpleNamespace(
                        **(
                            fields
                            | {
                                "st_file_attributes": getattr(value, "st_file_attributes", 0)
                                | 0x400,
                                "st_reparse_tag": 0xA0000003,
                            }
                        )
                    )

                def late_entry(
                    *args,
                    _validate=validate,
                    _directory=directory,
                    _active=active,
                    **kwargs,
                ):
                    result = _validate(*args, **kwargs)
                    if kwargs.get("active", True) and not _active[0]:
                        _directory.mkdir()
                        _active[0] = True
                    return result

                try:
                    # A real empty directory anchors the entry. Only its
                    # synthetic reparse view has a missing followed target;
                    # lstat still exposes the existing junction entry.
                    with (
                        self.no_execution(),
                        patch.object(Path, "stat", following_stat),
                        patch.object(Path, "lstat", entry_stat),
                        patch.object(
                            validation_study, "_validate_execution", side_effect=late_entry
                        ),
                    ):
                        if not delayed:
                            self.assertTrue(stat.S_ISDIR(directory.lstat().st_mode))
                            self.assertFalse(directory.exists())
                            self.assertFalse(directory.is_symlink())
                        with self.assertRaises(self.Error):
                            self.check(path)
                        self.assertTrue(active[0])
                finally:
                    if directory.exists():
                        self.assertTrue(stat.S_ISDIR(real_lstat(directory).st_mode))
                        directory.rmdir()


if __name__ == "__main__":
    unittest.main()
