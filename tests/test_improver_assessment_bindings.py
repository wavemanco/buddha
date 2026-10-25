"""Runtime outer bindings use real v4 preparation and synthetic first owners only."""

import copy
import hashlib
import json
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from buddha.releases import ReleaseError, _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def files(root):
    return {str(path): sha(path.read_bytes()) for path in root.rglob("*") if path.is_file()}


class ImproverAssessmentBindingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_improver_assessment as fixtures

        cls.f = fixtures.ImproverAssessmentTests("runTest")
        cls.addClassCleanup(cls.f.doCleanups)
        cls.f.setUp()
        cls.development, cls.definition = cls.f.capacity_definition()
        cls.api = cls.f.api
        cls.root = cls.f.root

    def setUp(self):
        self.serial = 0
        self.case = self.root / ("outer-" + self._testMethodName)
        self.case.mkdir()

    def bind(self):
        self.serial += 1
        self.f.bind(
            self.case.name + "-trial-" + str(self.serial),
            definition=copy.deepcopy(self.definition),
        )
        return self.f.trial

    def prepare(self, **options):
        return self.api.prepare_improver_assessment_trial(
            self.f.trial,
            declaration=self.f.declaration,
            expected_sha256=sha(self.f.declaration.read_bytes()),
            expected_runtime_sha256=self.f.engine.candidate.expected_runtime,
            authorizations=self.f.authorities,
            development_review=self.f.engine.fixture.review,
            **options,
        )

    def extra(self, name="launch-input.json"):
        path = self.case / name
        path.write_bytes(b"Frozen synthetic outer launch input.\n")
        return path, sha(path.read_bytes())

    @contextmanager
    def no_execution(self):
        with ExitStack() as stack:
            for target in (
                "getpass.getpass",
                "buddha.executor.run_container",
                "buddha.gateway.RawHTTPTransport.prepare",
            ):
                stack.enter_context(
                    patch(target, side_effect=AssertionError("execution forbidden"))
                )
            yield

    def passive(self, directory):
        with (
            self.no_execution(),
            patch.dict("os.environ", {}, clear=True),
            patch("sqlite3.connect", side_effect=AssertionError("passive SQL forbidden")),
        ):
            return self.api._state(directory, active=False)

    def test_bound_inputs_reach_context_first_owner_and_active_passive_reconstruction(self):
        directory = self.bind()
        extra, digest = self.extra()
        bindings = {extra: digest}
        execution_before = self.f.engine.workers, self.f.engine.physical_sends
        with self.no_execution():
            self.assertEqual(self.prepare(input_bindings=bindings), directory)
        context = json.loads((directory / "context.json").read_bytes())
        self.assertEqual(context["format"], "buddha.improver-assessment-context.v2")
        self.assertEqual(context["input_bindings"], {str(extra): digest})
        self.assertEqual(context["controls"][str(extra)], digest)
        first = directory / "search/study/common/0/0/screen/tasks/0/generation/owners/0"
        manifest = json.loads((first / "manifest.json").read_bytes())
        inputs = {row["path"]: row["sha256"] for row in manifest["invocation"]["inputs"]}
        self.assertEqual(inputs[str(extra)], digest)
        with self.no_execution():
            active = self.api._state(directory, active=True)
        self.assertEqual(active["controls"][extra], digest)
        self.assertEqual(self.passive(directory)["controls"][extra], digest)
        bindings[extra] = "0" * 64
        self.assertEqual(self.passive(directory)["controls"][extra], digest)
        self.assertEqual((self.f.engine.workers, self.f.engine.physical_sends), execution_before)
        self.assertEqual(self.f.authorities["search"].summary()["operation_count"], 0)
        self.assertFalse((directory / "freeze").exists())

    def test_explicit_empty_bindings_opt_into_closed_v2_context(self):
        original_keys = {
            "format",
            "external_declaration",
            "expected_runtime_sha256",
            "controls",
            "host_core",
            "host_runtime",
            "development_review",
        }
        for label, options, version in (
            ("omitted", {}, 1),
            ("none", {"input_bindings": None}, 1),
            ("empty", {"input_bindings": {}}, 2),
        ):
            with self.subTest(label=label):
                directory = self.bind()
                with self.no_execution():
                    self.assertEqual(self.prepare(**options), directory)
                context = json.loads((directory / "context.json").read_bytes())
                self.assertEqual(
                    context["format"], f"buddha.improver-assessment-context.v{version}"
                )
                self.assertEqual(
                    set(context), original_keys | ({"input_bindings"} if version == 2 else set())
                )
                if version == 2:
                    self.assertEqual(context["input_bindings"], {})
                self.assertEqual(len(list(directory.rglob("owners/0/manifest.json"))), 1)
                self.passive(directory)

    def test_invalid_drifted_conflicting_and_mutable_grant_inputs_refuse_before_publication(self):
        for case in (
            "mapping",
            "string_key",
            "digest",
            "missing",
            "stale",
            "alias",
            "declaration",
            "authority",
            "inside_output",
        ):
            with self.subTest(case=case):
                directory = self.bind()
                extra, digest = self.extra(case + ".json")
                bindings = {extra: digest}
                if case == "mapping":
                    bindings = []
                elif case == "string_key":
                    bindings = {str(extra): digest}
                elif case == "digest":
                    bindings = {extra: "invalid"}
                elif case == "missing":
                    extra.unlink()
                elif case == "stale":
                    extra.write_bytes(b"Changed after binding.\n")
                elif case == "alias":
                    spelling = self.case / "spelling"
                    spelling.mkdir()
                    bindings = {spelling / ".." / extra.name: digest}
                elif case == "declaration":
                    bindings = {self.f.declaration: "0" * 64}
                elif case == "authority":
                    grant = self.f.authorities["search"].path
                    bindings = {grant: sha(grant.read_bytes())}
                elif case == "inside_output":
                    directory.mkdir()
                    extra = directory / "approval.json"
                    extra.write_bytes(b"Input inside future output.\n")
                    bindings = {extra: sha(extra.read_bytes())}
                before = files(self.root)
                with self.no_execution(), self.assertRaises(self.api.ImproverAssessmentError):
                    self.prepare(input_bindings=bindings)
                self.assertEqual(files(self.root), before)
                self.assertFalse((directory / ".buddha-evaluation-trial.json").exists())
                self.assertFalse(list(directory.rglob("manifest.json")))

    def test_both_real_capacity_projections_include_outer_inputs_before_publication(self):
        from buddha import final_evaluation, improver_study, validation_study

        directory = self.bind()
        extra, digest = self.extra()
        order, projected = [], {}
        development, final, publication = (
            improver_study._capacity,
            validation_study._capacity,
            final_evaluation._prepare_trial_root,
        )

        def development_capacity(*args, **kwargs):
            order.append("development")
            projected.setdefault("development", set(args[3]))
            return development(*args, **kwargs)

        def final_capacity(*args, **kwargs):
            order.append("final")
            projected.setdefault("final", {Path(path) for path in args[1]["controls"]})
            return final(*args, **kwargs)

        def publish(*args, **kwargs):
            order.append("publication")
            return publication(*args, **kwargs)

        with (
            self.no_execution(),
            patch.object(improver_study, "_capacity", side_effect=development_capacity),
            patch.object(validation_study, "_capacity", side_effect=final_capacity),
            patch.object(final_evaluation, "_prepare_trial_root", side_effect=publish),
        ):
            self.prepare(input_bindings={extra: digest})
        self.assertLess(order.index("development"), order.index("publication"))
        self.assertLess(order.index("final"), order.index("publication"))
        self.assertIn(extra, projected["development"])
        self.assertIn(extra, projected["final"])
        self.assertTrue(directory.exists())

        overflow = {}
        for index in range(1024):
            path, checksum = self.extra("capacity-" + str(index) + ".json")
            overflow[path] = checksum
        directory = self.bind()
        with (
            self.no_execution(),
            patch.object(final_evaluation, "_prepare_trial_root", wraps=publication) as publish_spy,
            self.assertRaises(self.api.ImproverAssessmentError),
        ):
            self.prepare(input_bindings=overflow)
        publish_spy.assert_not_called()
        self.assertFalse(directory.exists())

        directory = self.bind()
        original = extra.read_bytes()

        def drift_after_final_capacity(*args, **kwargs):
            result = final(*args, **kwargs)
            extra.write_bytes(original + b"late drift\n")
            return result

        try:
            with (
                self.no_execution(),
                patch.object(validation_study, "_capacity", side_effect=drift_after_final_capacity),
                self.assertRaises(self.api.ImproverAssessmentError),
            ):
                self.prepare(input_bindings={extra: digest})
            self.assertFalse(directory.exists())
        finally:
            extra.write_bytes(original)

    def test_closed_context_and_explicit_program_pin_remain_required_keylessly(self):
        directory = self.bind()
        extra, digest = self.extra()
        self.prepare(input_bindings={extra: digest})
        context_path = directory / "context.json"
        raw = context_path.read_bytes()
        for case in ("extra_field", "missing_field", "pin", "controls", "alias"):
            with self.subTest(case=case):
                changed = json.loads(raw)
                if case == "extra_field":
                    changed["unreviewed"] = True
                elif case == "missing_field":
                    del changed["input_bindings"]
                elif case == "pin":
                    changed["input_bindings"][str(extra)] = "0" * 64
                elif case == "controls":
                    del changed["controls"][str(extra)]
                else:
                    spelling = self.case / "spelling"
                    spelling.mkdir()
                    changed["input_bindings"] = {str(spelling / ".." / extra.name): digest}
                try:
                    context_path.write_bytes(_json(changed))
                    with self.assertRaises(ReleaseError):
                        self.passive(directory)
                finally:
                    context_path.write_bytes(raw)
        self.passive(directory)

        runtime = self.f.engine.candidate.expected_runtime
        original = self.api._definition(_json(self.definition), runtime, active=False)
        actor = self.development["improvers"][0]
        program = Path(actor["roots"]["agent"]) / actor["entrypoint"]
        self.assertIn(program, original["retirable_producers"])
        program_raw = program.read_bytes()
        directory = self.bind()
        self.prepare(input_bindings={program: sha(program_raw)})
        self.assertNotIn(program, self.passive(directory)["retirable_producers"])
        try:
            program.write_bytes(program_raw + b"\n# changed explicitly pinned toy program\n")
            with self.assertRaises(ReleaseError):
                self.passive(directory)
        finally:
            program.write_bytes(program_raw)


if __name__ == "__main__":
    unittest.main()
