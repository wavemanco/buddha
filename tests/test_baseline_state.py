"""Whole-reference custody preflight using fresh synthetic baseline owners only."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_baseline as fixtures
from test_improver_launch_state import files, passive_only, sha

from buddha import baseline, baseline_state, plain_comparison, unified_funding
from buddha.authorization import Authorization
from buddha.gateway import GatewayCall
from buddha.ledger import BudgetExceeded
from buddha.releases import _json


class BaselineStateTests(unittest.TestCase):
    def setUp(self):
        self.fixture()

    def fixture(self):
        case = fixtures.BaselineTests("runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.case, self.root = case, case.root
        self.plan_path = self.root / "reference-plan.json"
        self.extra_path = self.root / "approved-control.json"
        self.extra_path.write_bytes(b'{"approved":"synthetic"}')
        self.extra = {self.extra_path: sha(self.extra_path.read_bytes())}
        self.definitions, self.recipes, self.directories = {}, {}, {}
        rows = []
        for name in ("regenerate", "in-context"):
            recipe = copy.deepcopy(case.agent.record)
            recipe["config"].update(instructions="", sampling=name)
            recipe_path = self.root / (name + "-generation.json")
            recipe_path.write_bytes(_json(recipe))
            definition = copy.deepcopy(case.record)
            definition["generation"]["descriptor"] = str(recipe_path)
            path = self.root / (name + "-definition.json")
            path.write_bytes(_json(definition))
            self.definitions[name] = path
            self.recipes[name] = recipe
            self.directories[name] = self.root / name
            rows.append(
                {
                    "name": name,
                    "directory": str(self.directories[name]),
                    "authorization": str(self.root / "reference-authorization.sqlite3"),
                    "definition": str(path),
                    "sha256": sha(path.read_bytes()),
                }
            )
        self.plan = {
            "format": "buddha.plain-comparison-plan.v1",
            "method": "all_conditions_then_equal_prompts_descriptive.v1",
            "trial": str(self.root / "not-created-primary"),
            "definition_sha256": "0" * 64,
            "references": rows,
            "consumer_sources": plain_comparison._source_hashes(),
        }
        self.plan_path.write_bytes(_json(self.plan))
        self.digest = sha(self.plan_path.read_bytes())
        self.authority = Authorization.create(
            self.root / "reference-authorization.sqlite3",
            authorization_id="synthetic-shared-references",
            budget_microusd=100_000,
            max_calls=100,
            scope=unified_funding.reference_scope(self.digest),
        )
        self.case.authority = self.authority
        self.controls = {
            self.plan_path: self.digest,
            **{Path(path): digest for path, digest in self.plan["consumer_sources"].items()},
            Path(baseline_state.__file__).absolute(): sha(
                Path(baseline_state.__file__).read_bytes()
            ),
            **self.extra,
        }

    def tree(self):
        return (
            files(self.root),
            tuple(
                sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_dir())
            ),
            self.case.physical_sends,
            len(self.case.events),
        )

    def inspect(self, **options):
        before = self.tree()
        try:
            with (
                passive_only(self),
                patch("os.getenv", side_effect=AssertionError("credential read")),
                patch("os.environ.get", side_effect=AssertionError("credential read")),
                patch(
                    "buddha.baseline.prepare_baseline", side_effect=AssertionError("owner created")
                ),
                patch(
                    "buddha.baseline.run_baseline", side_effect=AssertionError("producer called")
                ),
            ):
                return baseline_state.inspect_references(
                    self.plan_path,
                    **(
                        {
                            "expected_plan_sha256": self.digest,
                            "input_bindings": self.extra,
                        }
                        | options
                    ),
                )
        finally:
            self.assertEqual(self.tree(), before)

    def prepare(self, *names, controls=None):
        bound = self.controls if controls is None else controls
        for name in names or tuple(self.directories):
            baseline.prepare_baseline(
                self.directories[name],
                descriptor=self.definitions[name],
                authorization=self.authority,
                review=self.case.fixture.review,
                input_files=list(bound),
                expected_input_hashes=bound,
            )

    def execute(self, name):
        self.case.agent.config.update(self.recipes[name]["config"])
        return self.case.run_pipeline(directory=self.directories[name])

    def row(self, result, name):
        return next(row for row in result["references"] if row["name"] == name)

    def owner_ids(self, name):
        return {
            p.parent.name: json.loads(p.read_bytes())["run_id"]
            for p in (self.directories[name] / "owners").glob("*/manifest.json")
        }

    def corrupt(self, path, raw):
        original = path.read_bytes()
        try:
            path.write_bytes(raw)
            with self.assertRaises(baseline_state.BaselineStateError):
                self.inspect()
        finally:
            path.write_bytes(original)

    def retained_move(self, source, preserved):
        self.assertTrue(source.resolve().is_relative_to(self.root))
        self.assertTrue(preserved.resolve().is_relative_to(self.root))
        self.assertFalse(preserved.exists())
        source.rename(preserved)
        try:
            with self.assertRaises(baseline_state.BaselineStateError):
                self.inspect()
        finally:
            preserved.rename(source)

    def test_fresh_and_prepared_two_modes_are_keyless_readonly_and_detached(self):
        fresh = self.inspect()
        self.assertEqual(fresh["format"], "buddha.reference-state.v1")
        self.assertEqual(fresh["state"], "fresh")
        self.assertTrue(fresh["ready"])
        self.assertEqual(fresh["funding"]["owner_count"], 0)
        self.assertEqual({row["name"] for row in fresh["references"]}, set(self.directories))
        self.prepare()
        prepared = self.inspect()
        self.assertEqual(prepared["state"], "prepared")
        self.assertTrue(prepared["ready"])
        self.assertEqual(prepared["blocked_reasons"], [])
        self.assertEqual(prepared["funding"]["owner_count"], 2)
        for row in prepared["references"]:
            self.assertEqual(
                (row["state"], row["next_stage"], row["completed_stages"], row["owner_count"]),
                ("prepared", 0, 0, 1),
            )
        fingerprint = prepared["state_sha256"]
        prepared["funding"]["status_counts"].clear()
        prepared["blocked_reasons"].append("caller mutation")
        self.assertEqual(self.inspect()["state_sha256"], fingerprint)
        self.assertEqual(self.inspect()["blocked_reasons"], [])

    def test_complete_peer_work_keeps_original_publication_and_retired_producers_readable(self):
        self.prepare()
        self.assertEqual(self.execute("regenerate")["status"], "complete")
        first = self.directories["regenerate"] / "report.json"
        original = first.read_bytes()
        self.assertEqual(self.execute("in-context")["status"], "complete")
        expected = self.authority.summary()
        complete = self.inspect()
        self.assertEqual(complete["state"], "complete")
        self.assertTrue(complete["ready"])
        self.assertEqual(complete["funding"]["owner_count"], 8)
        for key in ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count"):
            self.assertEqual(complete["funding"][key], expected[key])
        for row in complete["references"]:
            self.assertEqual(
                (row["state"], row["next_stage"], row["completed_stages"]), ("complete", 4, 4)
            )
        self.assertEqual(first.read_bytes(), original)
        seed = self.case.agent.seed
        preserved = self.root / "retired-synthetic-seed.py"
        self.assertTrue(seed.resolve().is_relative_to(self.root))
        seed.rename(preserved)
        self.assertEqual(self.inspect()["state"], "complete")
        self.assertEqual(first.read_bytes(), original)

    def test_generation_failure_keeps_original_owner_and_replays_its_receipts(self):
        self.prepare()
        self.case.fail_generation_once = True
        result = self.execute("regenerate")
        self.assertEqual((result["status"], result["stopped_stage"]), ("incomplete", 0))
        identities = self.owner_ids("regenerate")
        before = self.authority.summary()
        physical_sends = self.case.physical_sends
        self.assertEqual(before["operation_count"], 3)
        observed = self.row(self.inspect(), "regenerate")
        self.assertEqual((observed["next_stage"], observed["completed_stages"]), (0, 0))
        self.assertEqual(self.execute("regenerate")["status"], "complete")
        self.assertEqual(self.owner_ids("regenerate")["0"], identities["0"])
        self.assertEqual(self.authority.summary()["operation_count"], before["operation_count"] + 3)
        self.assertEqual(self.case.physical_sends, physical_sends + 3)
        self.assertTrue((self.directories["regenerate"] / "attempts/0-0/report.json").is_file())

    def test_native_failure_keeps_completed_prefix_and_same_native_owner(self):
        self.prepare()
        self.case.fail_native_once = True
        result = self.execute("regenerate")
        self.assertEqual((result["status"], result["stopped_stage"]), ("incomplete", 1))
        identities = self.owner_ids("regenerate")
        before = self.authority.summary()
        observed = self.row(self.inspect(), "regenerate")
        self.assertEqual((observed["next_stage"], observed["completed_stages"]), (1, 1))
        self.assertEqual(self.execute("regenerate")["status"], "complete")
        self.assertEqual({key: self.owner_ids("regenerate")[key] for key in identities}, identities)
        self.assertEqual(self.authority.summary()["operation_count"], before["operation_count"] + 1)
        self.assertTrue((self.directories["regenerate"] / "attempts/1-0/report.json").is_file())

    def test_missing_funded_peer_root_or_later_owner_cannot_be_replaced(self):
        self.prepare()
        self.retained_move(self.directories["in-context"], self.root / "preserved-peer")
        self.case.halt_native_once = True
        self.assertEqual(self.execute("regenerate")["stopped_stage"], 1)
        self.retained_move(
            self.directories["regenerate"] / "owners/1", self.root / "preserved-owner"
        )

    def test_empty_foreign_and_gapped_owner_directories_refuse(self):
        self.prepare()
        owners = self.directories["in-context"] / "owners"
        for name in ("foreign", "1", "2"):
            path = owners / name
            path.mkdir()
            try:
                with self.subTest(name=name), self.assertRaises(baseline_state.BaselineStateError):
                    self.inspect()
            finally:
                path.rmdir()
        baseline.prepare_baseline(
            self.root / "unplanned-reference",
            descriptor=self.definitions["regenerate"],
            authorization=self.authority,
            review=self.case.fixture.review,
            input_files=list(self.controls),
            expected_input_hashes=self.controls,
        )
        with self.assertRaises(baseline_state.BaselineStateError):
            self.inspect()

    def test_changed_original_controls_caller_pins_and_missing_mandatory_input_refuse(self):
        self.prepare(
            "regenerate", controls={p: d for p, d in self.controls.items() if p != self.plan_path}
        )
        with self.assertRaises(baseline_state.BaselineStateError):
            self.inspect()
        self.fixture()
        self.prepare()
        self.corrupt(self.extra_path, b'{"changed":true}')
        with self.assertRaises(baseline_state.BaselineStateError):
            self.inspect(input_bindings={self.extra_path: "f" * 64})
        unbound = self.root / "unbound-control.json"
        unbound.write_bytes(b"{}")
        with self.assertRaises(baseline_state.BaselineStateError):
            self.inspect(input_bindings=self.extra | {unbound: sha(unbound.read_bytes())})
        with self.assertRaises(baseline_state.BaselineStateError):
            self.inspect(expected_plan_sha256="f" * 64)
        self.fixture()
        opaque = b"x" * (33 * 1024**2)
        self.extra_path.write_bytes(opaque)
        digest = sha(opaque)
        self.extra[self.extra_path] = digest
        self.controls[self.extra_path] = digest
        self.prepare()
        self.assertTrue(self.inspect()["ready"])

    def test_prepared_recipe_requires_original_profile_plain_mode_and_empty_instructions(self):
        for index, (key, value) in enumerate(
            (
                ("model", "foreign-model"),
                ("sampling", "regenerate"),
                ("instructions", "undeclared instruction"),
            )
        ):
            if index:
                self.fixture()
            recipe = self.recipes["in-context"]
            recipe["config"][key] = value
            path = Path(
                json.loads(self.definitions["in-context"].read_bytes())["generation"]["descriptor"]
            )
            path.write_bytes(_json(recipe))
            with (
                self.subTest(key=key, state="fresh"),
                self.assertRaises(baseline_state.BaselineStateError),
            ):
                self.inspect()
            self.prepare()
            with (
                self.subTest(key=key, state="prepared"),
                self.assertRaises(baseline_state.BaselineStateError),
            ):
                self.inspect()

    def test_changed_owner_selection_descriptor_staging_or_seal_refuse(self):
        self.prepare()
        self.assertEqual(self.execute("regenerate")["status"], "complete")
        root = self.directories["regenerate"]
        owner = root / "owners/2/manifest.json"
        record = json.loads(owner.read_bytes())
        record["selection"]["components"]["agent"] = {"foreign.py": "f" * 64}
        self.corrupt(owner, _json(record))
        self.corrupt(self.definitions["regenerate"], b"{}")
        self.corrupt(root / "staging/1/0.bin", b"changed staging")
        self.corrupt(root / "completed/1.json", b"{}")

    def test_inactive_unfinished_original_owner_blocks_without_reactivation(self):
        self.prepare()
        identifier = self.owner_ids("in-context")["0"]
        self.authority.deactivate(identifier, "synthetic inactive unfinished owner")
        result = self.inspect()
        self.assertFalse(result["ready"])
        self.assertIn("inactive_original_owner", result["blocked_reasons"])
        self.assertEqual(self.row(result, "in-context")["next_stage"], 0)

    def test_global_reserved_dispatched_and_unknown_peer_liabilities_are_preserved(self):
        for index, status in enumerate(("reserved", "dispatched", "unknown")):
            if index:
                self.fixture()
            self.prepare()
            owner = self.directories["in-context"] / "owners/0"
            ledger = self.authority.for_run(owner)
            operation = sha(b"synthetic retained peer operation")
            ledger.reserve(operation, sha(b"synthetic request"), 17)
            if status != "reserved":
                ledger.dispatch(operation)
            if status == "unknown":
                ledger.mark_unknown(operation)
            result = self.inspect()
            self.assertEqual(result["funding"]["reserved_microusd"], 17)
            self.assertEqual(result["funding"]["operation_count"], 1)
            self.assertEqual(result["funding"]["status_counts"][status], 1)
            if status != "reserved":
                self.assertFalse(result["ready"])
                self.assertIn(status + "_operations", result["blocked_reasons"])
            self.assertEqual(
                self.owner_ids("in-context")["0"],
                json.loads((owner / "manifest.json").read_bytes())["run_id"],
            )

    def test_real_gateway_known_reservation_overrun_blocks_both_modes(self):
        self.prepare()
        owner = self.directories["in-context"] / "owners/0"
        fixture = self.case.fixture
        gateway = fixture.gateway(directory=owner)
        profile = fixture.profiles["profiles"]["primary"]["spec"]
        body = _json(
            {
                "model": profile["model"],
                "max_completion_tokens": profile["max_output_tokens"],
                "messages": [{"role": "user", "content": "Synthetic retained overrun."}],
            }
        )
        manifest = json.loads((owner / "manifest.json").read_bytes())
        call = GatewayCall(
            next(iter(manifest["profiles"])), "primary", "synthetic-overrun", 0, body
        )
        response = fixture.response(
            usage={"prompt_tokens": profile["input_token_ceiling"] * 4, "completion_tokens": 3}
        )
        with self.assertRaises(BudgetExceeded):
            fixture.send(gateway, call, fixture.connection(response))
        operation = gateway.ledger.get(gateway.operation_id(call))
        self.assertEqual(operation.status, "completed")
        self.assertGreater(operation.actual_microusd, operation.reserve_microusd)
        result = self.inspect()
        self.assertFalse(result["ready"])
        self.assertIn("reservation_overrun", result["blocked_reasons"])
        self.assertEqual(result["funding"]["spent_microusd"], operation.actual_microusd)

    def test_unsealed_generation_refuses_orphan_future_materializations_before_calls(self):
        self.prepare()
        root = self.directories["in-context"]
        for label, path, directory in (
            ("native-answers", root / "native-answers.jsonl", False),
            ("command", root / "command-1.json", False),
            ("staging", root / "staging/1", True),
        ):
            with self.subTest(material=label):
                preserved = self.root / ("preserved-orphan-" + label)
                self.assertTrue(path.resolve().is_relative_to(self.root))
                self.assertTrue(preserved.resolve().is_relative_to(self.root))
                self.assertFalse(path.exists())
                self.assertFalse(preserved.exists())
                payload = b"synthetic impossible future material"
                if directory:
                    path.mkdir()
                    (path / "0.bin").write_bytes(payload)
                else:
                    path.write_bytes(payload)
                try:
                    with self.assertRaises(baseline_state.BaselineStateError):
                        self.inspect()
                    self.assertEqual(
                        (path / "0.bin").read_bytes() if directory else path.read_bytes(),
                        payload,
                    )
                finally:
                    path.rename(preserved)
        # This later interruption is legitimate: generation is already sealed,
        # but native inputs were staged before the native owner could be bound.
        native_owner = self.directories["regenerate"] / "owners/1"
        prepare_gateway = baseline.prepare_gateway

        def interrupt_native_owner(directory, **options):
            if directory == native_owner:
                raise KeyboardInterrupt
            return prepare_gateway(directory, **options)

        with patch("buddha.baseline.prepare_gateway", side_effect=interrupt_native_owner):
            with self.assertRaises(KeyboardInterrupt):
                self.execute("regenerate")
        original_ids = self.owner_ids("regenerate")
        before = self.authority.summary()["operation_count"]
        physical_sends = self.case.physical_sends
        self.assertEqual(before, 4)
        self.assertEqual(set(original_ids), {"0"})
        self.assertTrue((self.directories["regenerate"] / "command-1.json").is_file())
        self.assertTrue((self.directories["regenerate"] / "staging/1/0.bin").is_file())
        observed = self.row(self.inspect(), "regenerate")
        self.assertEqual(
            (
                observed["state"],
                observed["next_stage"],
                observed["completed_stages"],
                observed["owner_count"],
            ),
            ("prepared", 1, 1, 1),
        )
        self.assertEqual(self.execute("regenerate")["status"], "complete")
        self.assertEqual(self.owner_ids("regenerate")["0"], original_ids["0"])
        self.assertEqual(self.authority.summary()["operation_count"], before + 2)
        self.assertEqual(self.case.physical_sends, physical_sends + 2)
        self.assertEqual(len(list((self.directories["regenerate"] / "attempts").glob("0-*"))), 1)

    def test_fresh_recipe_bytes_change_state_seal_and_late_mutation_refuses(self):
        from buddha import gateway, native_pipeline

        definition = json.loads(self.definitions["in-context"].read_bytes())
        recipe_path = Path(definition["generation"]["descriptor"])
        original = recipe_path.read_bytes()
        recipe = json.loads(original)
        recipe["executor"]["limits"]["wall_seconds"] += 1
        changed = _json(recipe)
        baseline_state_hash = self.inspect()["state_sha256"]
        with self.subTest(case="valid_fresh_recipe_change"):
            try:
                recipe_path.write_bytes(changed)
                observed = self.inspect()
                self.assertEqual(observed["state"], "fresh")
                self.assertTrue(observed["ready"])
                self.assertNotEqual(observed["state_sha256"], baseline_state_hash)
            finally:
                recipe_path.write_bytes(original)

        read, profiles = native_pipeline._read, gateway._profiles
        consumed = mutated = False

        def read_then_mark(path, *args, **options):
            nonlocal consumed
            raw = read(path, *args, **options)
            if path == recipe_path:
                consumed = True
            return raw

        def profiles_after_recipe(*args, **options):
            nonlocal mutated
            result = profiles(*args, **options)
            if consumed and not mutated:
                recipe_path.write_bytes(changed)
                mutated = True
            return result

        with self.subTest(case="late_fresh_recipe_change"):
            before = self.tree()
            try:
                with (
                    passive_only(self),
                    patch("buddha.native_pipeline._read", side_effect=read_then_mark),
                    patch("buddha.gateway._profiles", side_effect=profiles_after_recipe),
                    self.assertRaises(baseline_state.BaselineStateError),
                ):
                    baseline_state.inspect_references(
                        self.plan_path, expected_plan_sha256=self.digest, input_bindings=self.extra
                    )
            finally:
                recipe_path.write_bytes(original)
            self.assertTrue(mutated)
            self.assertEqual(self.tree(), before)

    def test_peer_execution_lock_blocks_and_remains_untouched(self):
        self.prepare()
        path = self.directories["in-context"] / "running.lock"
        path.write_bytes(b"123456789")
        result = self.inspect()
        self.assertFalse(result["ready"])
        self.assertIn("execution_lock_present", result["blocked_reasons"])
        self.assertEqual(path.read_bytes(), b"123456789")

    def test_unanchored_completed_stage_is_refused_without_blessing_it(self):
        self.prepare()
        with patch.object(
            Authorization, "deactivate", side_effect=OSError("synthetic interruption")
        ):
            with self.assertRaises(baseline.BaselineError):
                self.execute("regenerate")
        self.assertTrue((self.directories["regenerate"] / "completed/0.json").is_file())
        with self.assertRaises(baseline_state.BaselineStateError):
            self.inspect()

    def test_late_consumed_control_and_ledger_sidecar_changes_refuse(self):
        from buddha.doctor import _Capture

        self.prepare()
        finish = _Capture.finish
        target_root = self.directories["regenerate"]
        ledger = target_root / "owners/0/operations.sqlite3"
        for sidecar in (False, True):
            before = self.tree()
            original = self.extra_path.read_bytes()
            sidecar_path = ledger.with_name(ledger.name + "-wal")
            injected = False

            def change(capture, *, sidecar=sidecar, sidecar_path=sidecar_path, original=original):
                nonlocal injected
                if capture.root == target_root and not injected:
                    injected = True
                    if sidecar:
                        sidecar_path.write_bytes(b"synthetic active sidecar")
                    else:
                        self.extra_path.write_bytes(original + b" ")
                return finish(capture)

            try:
                with (
                    self.subTest(sidecar=sidecar),
                    passive_only(self),
                    patch.object(_Capture, "finish", new=change),
                    self.assertRaises(baseline_state.BaselineStateError),
                ):
                    baseline_state.inspect_references(
                        self.plan_path, expected_plan_sha256=self.digest, input_bindings=self.extra
                    )
                self.assertTrue(injected)
            finally:
                self.extra_path.write_bytes(original)
                if sidecar_path.exists():
                    sidecar_path.unlink()
            self.assertEqual(self.tree(), before)
