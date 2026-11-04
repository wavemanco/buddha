"""Pinned ordinary operator limits; supplied lifecycle seams, no migration or providers."""

import copy
import importlib.util
import io
import json
import unittest
from contextlib import ExitStack, contextmanager, redirect_stdout
from unittest.mock import patch

import test_unified_launch as fixtures

from buddha import doctor, unified_launch
from buddha.releases import _json
from buddha.search_evidence import EvidencePathLimitError

POLICY = {
    "format": "buddha.evidence-observation-policy.v2",
    "max_total_bytes": 32 * 1024**3,
    "max_tree_entries": 100_000,
    "max_consumed_paths": 65_536,
    "max_resident_bytes": 0,
}
LIMITS = (POLICY["max_total_bytes"], POLICY["max_tree_entries"], POLICY["max_consumed_paths"])


class UnifiedObservationPolicyTests(unittest.TestCase):
    def fixture(self):
        h = fixtures.UnifiedLaunchLifecycleTests("runTest")
        self.addCleanup(h.doCleanups)
        h.setUp()
        h.policy_path = h.root / "observation-policy.json"
        h.policy_path.write_bytes(_json(POLICY))
        h.record.update(
            format="buddha.unified-launch.v2",
            observation_policy=fixtures.reference(h.policy_path),
        )
        h.record["source_sha256"].update(
            {str(path): fixtures.sha(path.read_bytes()) for path in unified_launch._sources()}
        )
        h.record["source_sha256"][str(h.policy_path)] = fixtures.sha(h.policy_path.read_bytes())
        self.save(h)
        spec = importlib.util.spec_from_file_location(
            "unified_policy_cli_fixture", unified_launch._entrypoint()
        )
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        return h, cli

    @staticmethod
    def save(h):
        h.path.write_bytes(_json(h.record))
        h.digest = fixtures.sha(h.path.read_bytes())
        h.original_inputs = fixtures.files(h.root)

    @staticmethod
    def invoke(h, cli, *flags):
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(["--handoff", str(h.path), "--sha256", h.digest, *flags])
        return code, json.loads(output.getvalue().splitlines()[-1])

    def arm(self, *args, **kwargs):
        self.assertEqual(doctor._observation_limits(), LIMITS)
        return {}, set()

    @contextmanager
    def lifecycle(self, h, seen):
        configuration = unified_launch._configuration
        checked = h.check

        def check(path, digest, *, owned_lock=False):
            with ExitStack() as observation:
                configuration(path, digest, observation=observation)
                self.assertEqual(doctor._observation_limits(), LIMITS)
                seen.append("check")
                return checked(path, digest, owned_lock=owned_lock)

        def observed(name, function):
            def call(*args, **kwargs):
                self.assertEqual(doctor._observation_limits(), LIMITS)
                seen.append(name)
                return function(*args, **kwargs)

            return call

        # The ordinary parser/context and CLI remain real. Existing lifecycle
        # seams provide only synthetic phase outcomes and accounting records.
        with (
            h.seams(),
            patch.object(unified_launch, "_configuration", side_effect=configuration),
            patch.object(unified_launch, "_check", side_effect=check),
            patch("buddha.comparison_observation._arm", side_effect=self.arm),
            patch("buddha.improver_launch.launch", side_effect=observed("primary", h.primary)),
            patch("buddha.baseline.prepare_baseline", side_effect=observed("prepare", h.prepare)),
            patch("buddha.baseline.run_baseline", side_effect=observed("plain", h.run_reference)),
            patch(
                "buddha.plain_comparison.compare_plain_references",
                side_effect=observed("publication", h.compare),
            ),
            patch(
                "buddha.comparison_observation.save_observation",
                side_effect=observed("partial", h.observe),
            ),
        ):
            yield

    def test_ordinary_entrypoint_scopes_check_all_phases_publication_and_keyless_replay(self):
        h, cli = self.fixture()
        before, seen = doctor._observation_limits(), []
        with self.lifecycle(h, seen):
            code, report = self.invoke(h, cli, "--check")
            self.assertEqual((code, report["status"]), (0, "checked"))
            self.assertFalse(h.workspace.exists())
            self.assertFalse(any(event[0] == "keys" for event in h.events))
            code, report = self.invoke(h, cli, "--live", "--prompt-keys", "--confirm-project-keys")
            self.assertEqual((code, report["status"]), (0, "complete"))
            self.assertTrue({"check", "primary", "prepare", "plain", "publication"} <= set(seen))
            self.assertEqual(seen.count("plain"), 2)
            saved = (h.workspace / "comparison.json").read_bytes()
            with patch("buddha.credentials.key_environment", side_effect=AssertionError("keys")):
                code, replay = self.invoke(h, cli)
            self.assertEqual((code, replay["status"]), (0, "complete"))
            self.assertEqual((h.workspace / "comparison.json").read_bytes(), saved)
        self.assertEqual(doctor._observation_limits(), before)

    def test_ordinary_entrypoint_keeps_policy_for_error_and_cancelled_partial_recording(self):
        before = doctor._observation_limits()
        for error, expected in ((RuntimeError("private error"), 2), (KeyboardInterrupt(), 130)):
            with self.subTest(error=type(error).__name__):
                h, cli = self.fixture()
                h.primary_error, seen = error, []
                with self.lifecycle(h, seen):
                    code, report = self.invoke(h, cli, "--live", "--confirm-project-keys")
                    self.assertEqual(code, expected)
                    self.assertIn("partial", seen)
                    self.assertTrue(list((h.workspace / "observations").glob("*.json")))
                    self.assertNotIn("private error", json.dumps(report))
                self.assertEqual(doctor._observation_limits(), before)

    def test_malformed_unbound_and_changed_policy_refuse_before_keys_or_heavy_arm(self):
        cases = (
            "missing_leaf",
            "v1_with_leaf",
            "unbound_leaf",
            "wrong_leaf_hash",
            "changed_policy",
            "legacy_policy",
            "resident_cache",
        )
        before = doctor._observation_limits()
        for name in cases:
            with self.subTest(case=name):
                h, cli = self.fixture()
                if name == "missing_leaf":
                    h.record.pop("observation_policy")
                elif name == "v1_with_leaf":
                    h.record["format"] = "buddha.unified-launch.v1"
                elif name == "unbound_leaf":
                    h.record["source_sha256"].pop(str(h.policy_path))
                elif name == "wrong_leaf_hash":
                    h.record["observation_policy"]["sha256"] = "0" * 64
                elif name == "changed_policy":
                    h.policy_path.write_bytes(_json(POLICY | {"max_total_bytes": 1}))
                else:
                    policy = copy.deepcopy(POLICY)
                    if name == "legacy_policy":
                        policy["format"] = "buddha.evidence-observation-policy.v1"
                        policy.pop("max_tree_entries")
                        policy.pop("max_consumed_paths")
                    else:
                        policy["max_resident_bytes"] = 1
                    h.policy_path.write_bytes(_json(policy))
                    h.record["observation_policy"] = fixtures.reference(h.policy_path)
                    h.record["source_sha256"][str(h.policy_path)] = fixtures.sha(
                        h.policy_path.read_bytes()
                    )
                self.save(h)
                with (
                    patch(
                        "buddha.comparison_observation._arm", side_effect=AssertionError("arm")
                    ) as arm,
                    patch(
                        "buddha.credentials.key_environment", side_effect=AssertionError("keys")
                    ) as keys,
                    patch(
                        "buddha.improver_launch.launch", side_effect=AssertionError("primary")
                    ) as primary,
                ):
                    code, report = self.invoke(h, cli, "--live", "--confirm-project-keys")
                arm.assert_not_called()
                keys.assert_not_called()
                primary.assert_not_called()
                self.assertEqual((code, report["status"]), (2, "stopped"))
                self.assertFalse(h.workspace.exists())
                self.assertEqual(doctor._observation_limits(), before)

    def test_policy_change_during_key_entry_stops_before_phase_dispatch(self):
        h, cli = self.fixture()
        before, seen = doctor._observation_limits(), []
        original = h.policy_path.read_bytes()
        h.enter_change = lambda: h.policy_path.write_bytes(original + b"\n")
        with self.lifecycle(h, seen):
            try:
                code, report = self.invoke(h, cli, "--live", "--confirm-project-keys")
                self.assertEqual((code, report["status"]), (2, "stopped"))
                self.assertNotIn("primary", seen)
                self.assertIn("partial", seen)
            finally:
                h.policy_path.write_bytes(original)
        self.assertEqual(doctor._observation_limits(), before)

    def test_real_check_requires_primary_binding_and_selected_capture_limits(self):
        h, _ = self.fixture()
        before = doctor._observation_limits()
        controls = h.record["source_sha256"]
        primary = {
            "directory": str(h.primary_root),
            "state": "fresh",
            "stop_code": None,
            "bindings": copy.deepcopy(controls),
        }
        raw = {
            "state": "fresh",
            "references": [
                {"name": name, "state": "fresh"} for name in ("regenerate", "in-context")
            ],
            "blocked_reasons": [],
            "state_sha256": "0" * 64,
        }

        def funding(**kwargs):
            self.assertEqual(doctor._observation_limits(), LIMITS)
            return {"primary": primary}

        with (
            patch("buddha.comparison_observation._arm", side_effect=self.arm),
            patch("buddha.unified_funding.check_funding", side_effect=funding),
            patch("buddha.baseline_state.inspect_references", return_value=raw),
            patch.object(unified_launch, "_compatible", return_value=[]),
        ):
            self.assertIsNone(
                unified_launch.check_launch(h.path, expected_sha256=h.digest)["stop_code"]
            )
            primary["bindings"].pop(str(h.policy_path))
            with self.assertRaises(unified_launch.UnifiedLaunchError):
                unified_launch.check_launch(h.path, expected_sha256=h.digest)
        self.assertEqual(doctor._observation_limits(), before)

        # Exercise the real path limiter under a bound small policy; no large
        # fixture or inferred process-memory ceiling is needed for this proof.
        probe = h.root / "capture-probe"
        probe.mkdir()
        for name in ("first", "second"):
            (probe / name).write_bytes(b"x")
        policy = POLICY | {"max_consumed_paths": 1}
        h.policy_path.write_bytes(_json(policy))
        h.record["observation_policy"] = fixtures.reference(h.policy_path)
        h.record["source_sha256"][str(h.policy_path)] = fixtures.sha(h.policy_path.read_bytes())
        self.save(h)
        with (
            ExitStack() as observation,
            patch("buddha.comparison_observation._arm", return_value=({}, set())),
        ):
            unified_launch._configuration(h.path, h.digest, observation=observation)
            capture = doctor._Capture(probe)
            capture.read(probe / "first")
            with self.assertRaises(EvidencePathLimitError):
                capture.read(probe / "second")
        self.assertEqual(doctor._observation_limits(), before)

    def test_legacy_descriptor_keeps_default_scope_and_never_reads_policy_leaf(self):
        h, _ = self.fixture()
        h.record["format"] = "buddha.unified-launch.v1"
        h.record.pop("observation_policy")
        h.record["source_sha256"].pop(str(h.policy_path))
        self.save(h)
        before, reads = doctor._observation_limits(), []
        original = unified_launch.pipeline._read

        def read(path, *args, **kwargs):
            reads.append(path)
            return original(path, *args, **kwargs)

        with (
            ExitStack() as observation,
            patch("buddha.comparison_observation._arm", return_value=({}, set())),
            patch.object(unified_launch.pipeline, "_read", side_effect=read),
        ):
            unified_launch._configuration(h.path, h.digest, observation=observation)
            self.assertEqual(doctor._observation_limits(), before)
        self.assertEqual(reads, [h.path])
        self.assertEqual(doctor._observation_limits(), before)
