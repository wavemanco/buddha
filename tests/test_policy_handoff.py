"""An unallocated proposal checks real inputs without authority or execution."""

import copy
import hashlib
import json
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import test_policy_panel_read as panel_fixtures

from buddha import gateway, native_pipeline, policy_handoff, policy_run
from buddha.policy_handoff import PolicyHandoffError, check_handoff
from buddha.releases import _json


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PolicyHandoffTests(unittest.TestCase):
    def setUp(self):
        self.panel = panel_fixtures.PolicyPanelReadTests("runTest")
        # Reuse the data/selection fixture without preparing a study or any work.
        with patch("test_policy_run.prepare_study", return_value=None):
            self.panel.setUp()
        self.addCleanup(self.panel.doCleanups)
        self.f = self.panel.f
        self.root = self.f.root
        self.plan = self.root / "panel-plan.json"
        self.plan.write_bytes(_json(self.panel.plan))
        self.materials = self.root / "review-materials.json"
        self.materials.write_bytes(_json(self.panel.materials))
        self.handoff = self.root / "handoff.json"
        self.record = {
            "format": "buddha.policy-handoff.v1",
            "study": self.reference(self.f.study_path),
            "baseline": self.reference(self.f.template),
            "publications": {
                "intent": self.reference(self.panel.saved.intent),
                "protocol": self.reference(self.panel.saved.protocol),
                "source_review": self.reference(self.panel.review_path),
                "panel_plan": self.reference(self.plan),
                "review_materials": self.reference(self.materials),
            },
            "source_sha256": self.inventory(),
            "requested_terms": {"budget_microusd": 50_000_000, "max_calls": 4096},
        }
        self.assertFalse(self.f.directory.exists())

    def reference(self, path):
        return {"path": str(path), "sha256": sha(path.read_bytes())}

    def inventory(self):
        package = Path(policy_run.__file__).resolve().parent
        paths = {
            *policy_run._sources(),
            self.f.study_path,
            self.f.template,
            self.f.fixture.agent.tasks_path,
            self.f.fixture.agent.descriptor,
            self.panel.saved.intent,
            self.panel.saved.protocol,
            self.panel.review_path,
            self.plan,
            self.materials,
            package / "policy_handoff.py",
            package / "policy_panel.py",
            package / "policy_study.py",
        }
        for name in gateway.CORE:
            paths.add(
                package / ("__init__.py" if name == "buddha" else name.rsplit(".", 1)[1] + ".py")
            )
        result = {str(path): sha(path.read_bytes()) for path in paths}
        return result

    def save(self):
        self.handoff.write_bytes(_json(self.record))
        return sha(self.handoff.read_bytes())

    @contextmanager
    def keyless(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("configuration checker used authority, credentials or execution")

        original = Path.open

        def opened(path, mode="r", *args, **kwargs):
            if any(character in mode for character in "wax+") or path.suffix == ".sqlite3":
                forbidden()
            return original(path, mode, *args, **kwargs)

        with ExitStack() as stack:
            for name in (
                "buddha.authorization.Authorization.__init__",
                "buddha.authorization.Authorization.create",
                "buddha.authorization.Authorization.summary",
                "buddha.gateway.Gateway.__init__",
                "buddha.agent_run.AgentSession.__init__",
                "buddha.native_run.NativeSession.__init__",
                "buddha.executor.run_container",
                "buddha.policy_run.prepare_study",
                "buddha.policy_run.run_study",
                "sqlite3.connect",
                "getpass.getpass",
                "os.getenv",
                "os.environ.get",
                "http.client.HTTPSConnection",
                "socket.create_connection",
                "subprocess.Popen",
            ):
                stack.enter_context(patch(name, side_effect=forbidden))
            stack.enter_context(patch.object(Path, "open", opened))
            yield

    def check(self, *, expected=None):
        pin = self.save()
        with self.keyless():
            return check_handoff(
                self.handoff, expected_sha256=pin if expected is None else expected
            )

    def test_real_configuration_and_publications_check_without_authority_or_writes(self):
        pin = self.save()
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with self.keyless():
            result = check_handoff(self.handoff, expected_sha256=pin)
        self.assertEqual(result["format"], "buddha.policy-handoff-check.v1")
        self.assertEqual(result["status"], "configuration_checked")
        self.assertEqual(
            result["funding"],
            {
                "status": "unallocated",
                "budget_microusd": 50_000_000,
                "max_calls": 4096,
                "scope": "policy study: " + self.f.study.fingerprint(),
            },
        )
        self.assertEqual(result["study_sha256"], self.f.study.fingerprint())
        self.assertEqual(result["planned"]["task_ids"], ["1", 1])
        self.assertEqual(result["planned"]["cells"], 8)
        self.assertEqual(result["planned"]["judging_occasions"], 16)
        self.assertEqual(result["planned"]["panel"], {"tasks": 2, "sets": 8, "positions": 16})
        self.assertEqual(result["reviewed_bindings"][str(self.handoff)], pin)
        self.assertEqual(
            {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}, before
        )
        self.assertFalse(self.f.directory.exists())
        self.assertEqual(self.f.fixture.physical_sends, 0)

    def test_original_raw_pins_reject_mutually_rewritten_publications(self):
        self.save()
        pin = sha(self.handoff.read_bytes())
        protocol = self.panel.saved.protocol
        protocol.write_bytes(protocol.read_bytes() + b"changed")
        self.record["publications"]["protocol"] = self.reference(protocol)
        self.record["source_sha256"][str(protocol)] = sha(protocol.read_bytes())
        self.save()
        with self.keyless(), self.assertRaises(PolicyHandoffError):
            check_handoff(self.handoff, expected_sha256=pin)

    def test_required_source_core_component_and_configuration_cannot_be_omitted(self):
        package = Path(policy_run.__file__).resolve().parent
        for path in (package / "policy_handoff.py", package / "authorization.py", self.f.template):
            original = self.record["source_sha256"].pop(str(path))
            try:
                with self.subTest(path=path.name), self.assertRaises(PolicyHandoffError):
                    self.check()
            finally:
                self.record["source_sha256"][str(path)] = original

    def test_missing_or_changed_selected_component_fails_actual_selection_verification(self):
        path = self.f.fixture.native_roots["runner"] / "buddha/native_worker.py"
        original = path.read_bytes()
        try:
            path.unlink()
            with self.assertRaises(PolicyHandoffError):
                self.check()
            path.write_bytes(original + b"\n# changed selected bytes\n")
            with self.assertRaises(PolicyHandoffError):
                self.check()
            path.write_bytes(original)
            profiles = policy_handoff._profiles
            opened = Path.open

            def changed(execution):
                value = profiles(execution)
                with opened(path, "wb") as stream:
                    stream.write(original + b"\n# late selected component drift\n")
                return value

            with patch.object(policy_handoff, "_profiles", side_effect=changed):
                with self.assertRaises(PolicyHandoffError):
                    self.check()
        finally:
            path.write_bytes(original)

    def test_conflicting_inventory_hash_cannot_replace_derived_expected_value(self):
        self.record["source_sha256"][str(self.f.template)] = "0" * 64
        with self.assertRaises(PolicyHandoffError):
            self.check()

    def test_panel_coordinates_and_release_protocol_materials_are_not_self_asserted(self):
        for path in (self.plan, self.materials):
            original = path.read_bytes()
            changed = json.loads(original)
            if path == self.plan:
                changed["sets"][0]["arm_index"] = 99
                name = "panel_plan"
            else:
                changed["rule"]["upstream_revision"] = "0" * 40
                name = "review_materials"
            path.write_bytes(_json(changed))
            self.record["publications"][name] = self.reference(path)
            self.record["source_sha256"][str(path)] = sha(path.read_bytes())
            try:
                with self.subTest(path=path.name), self.assertRaises(PolicyHandoffError):
                    self.check()
            finally:
                path.write_bytes(original)
                self.record["publications"][name] = self.reference(path)
                self.record["source_sha256"][str(path)] = sha(original)

    def test_generation_and_native_profiles_must_match_selected_roles(self):
        recipe = self.f.fixture.agent.descriptor
        original_recipe, original_template = recipe.read_bytes(), self.f.template.read_bytes()
        bad = json.loads(original_recipe)
        bad["profile"]["capability"] = "anthropic.messages.v1"
        recipe.write_bytes(_json(bad))
        self.record["source_sha256"][str(recipe)] = sha(recipe.read_bytes())
        with self.assertRaises(PolicyHandoffError):
            self.check()
        recipe.write_bytes(original_recipe)
        self.record["source_sha256"][str(recipe)] = sha(original_recipe)
        bad = json.loads(original_template)
        bad["native"]["profiles"] = {"openai": {"foreign-model": "primary"}}
        self.f.template.write_bytes(_json(bad))
        self.record["baseline"] = self.reference(self.f.template)
        self.record["source_sha256"][str(self.f.template)] = sha(self.f.template.read_bytes())
        with self.assertRaises(PolicyHandoffError):
            self.check()

    def test_wrong_first_generation_config_is_rejected_before_any_owner(self):
        recipe = self.f.fixture.agent.descriptor
        record = json.loads(recipe.read_bytes())
        record["config"]["instructions"] = "different treatment"
        recipe.write_bytes(_json(record))
        self.record["source_sha256"][str(recipe)] = sha(recipe.read_bytes())
        with self.assertRaises(PolicyHandoffError):
            self.check()
        self.assertFalse(self.f.directory.exists())

    def test_requested_terms_are_positive_bounded_proposals_never_authority(self):
        for terms in (
            {"budget_microusd": False, "max_calls": 4096},
            {"budget_microusd": 0, "max_calls": 4096},
            {"budget_microusd": 50_000_000, "max_calls": 2**63},
            {"budget_microusd": 50_000_000, "max_calls": 4096, "authorization": None},
        ):
            self.record["requested_terms"] = terms
            with self.subTest(terms=terms), self.assertRaises(PolicyHandoffError):
                self.check()

    def test_consumed_protocol_drift_is_rejected_before_detached_success(self):
        original = native_pipeline._read
        opened = Path.open
        path = self.panel.saved.protocol

        def drift(source, expected=None):
            raw = original(source, expected)
            if source == path:
                with opened(path, "wb") as stream:
                    stream.write(raw + b"changed after read")
            return raw

        with patch.object(native_pipeline, "_read", side_effect=drift):
            with self.assertRaises(PolicyHandoffError):
                self.check()

    def test_results_are_detached_and_inventory_limit_is_checked(self):
        first = self.check()
        second = copy.deepcopy(first)
        first["planned"]["task_ids"].clear()
        first["reviewed_bindings"].clear()
        self.assertEqual(self.check(), second)
        with patch.object(policy_handoff, "MAX_FILES", 2), self.assertRaises(PolicyHandoffError):
            self.check()

    def test_shared_configuration_keeps_consumed_descriptor_hash_and_real_authority_join(self):
        original = _json(self.f.record)
        self.f.descriptor.write_bytes(original)
        configuration = policy_run._configuration

        def changed(*args, **kwargs):
            value = configuration(*args, **kwargs)
            self.f.descriptor.write_bytes(original + b"\n")
            return value

        with patch.object(policy_run, "_configuration", side_effect=changed):
            execution = policy_run._definition(self.f.descriptor, self.f.authority)
        self.assertEqual(execution.files[self.f.descriptor], sha(original))
        self.assertNotEqual(sha(self.f.descriptor.read_bytes()), sha(original))
        bad = copy.deepcopy(self.f.record)
        bad["authorization"]["id"] = "foreign"
        self.f.descriptor.write_bytes(_json(bad))
        with self.assertRaises(policy_run.PolicyRunError):
            policy_run._definition(self.f.descriptor, self.f.authority)
        with self.assertRaises(policy_run.PolicyRunError):
            policy_run.prepare_study(
                self.f.directory,
                descriptor=self.f.descriptor,
                authorization=None,
                review=self.f.fixture.fixture.review,
            )
        self.assertFalse(self.f.directory.exists())


if __name__ == "__main__":
    unittest.main()
