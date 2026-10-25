"""Thin matched-launch custody with original synthetic grants and controllers."""

import copy
import os
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from test_improver_launch_state import files, passive_only, sha

from buddha.releases import _json


class ImproverLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_improver_assessment as fixtures

        from buddha import improver_assessment, improver_handoff, improver_launch

        cls.api, cls.assessment, cls.handoff = (
            improver_launch,
            improver_assessment,
            improver_handoff,
        )
        cls.Error = improver_launch.ImproverLaunchError
        cls.f = fixtures.ImproverAssessmentTests("runTest")
        cls.addClassCleanup(cls.f.doCleanups)
        cls.f.setUp()
        development, cls.definition = cls.f.capacity_definition()
        cls.f.f.recompute_limits(development)
        cls.definition["development"] = cls.f.write("launcher-development.json", development)
        cls.definition["phase_limits"]["search"] = copy.deepcopy(development["limits"]["study"])
        cls.definition["phase_limits"]["final"] = copy.deepcopy(
            cls.f.definition["phase_limits"]["final"]
        )
        cls.root = cls.f.root

    def setUp(self):
        self.serial = 0
        self.case = self.root / ("launcher-" + self._testMethodName)
        self.case.mkdir()

    @staticmethod
    def reference(path):
        return {"path": str(path), "sha256": sha(path.read_bytes())}

    def bundle(self):
        self.serial += 1
        folder = self.case / str(self.serial)
        folder.mkdir()
        self.f.bind(self.case.name + "-" + str(self.serial), definition=self.definition)
        extra = folder / "additional-control.txt"
        extra.write_bytes(b"Synthetic reviewed matched-launch input.\n")
        proposal_path, approval_path, launch_path = (
            folder / (name + ".json") for name in ("proposal", "approval", "launch")
        )
        review_path = folder / "review.json"
        proposal = {
            "format": "buddha.improver-handoff.v1",
            "assessment": self.reference(self.f.declaration),
            "expected_runtime_sha256": self.f.engine.candidate.expected_runtime,
            "directory": str(self.f.trial),
            "source_sha256": {
                str(path): sha(path.read_bytes()) for path in (*self.handoff._sources(), extra)
            },
        }
        proposal_path.write_bytes(_json(proposal))
        authorizations = {}
        for phase, authority in self.f.authorities.items():
            summary = authority.summary()
            authorizations[phase] = {
                "path": str(authority.path),
                "id": summary["authorization_id"],
                **{
                    key: summary[key]
                    for key in ("terms_sha256", "scope", "budget_microusd", "max_calls")
                },
            }
        approval = {
            "format": "buddha.improver-approval.v1",
            "proposal_sha256": sha(proposal_path.read_bytes()),
            "definition_sha256": sha(_json(self.definition)),
            "directory": str(self.f.trial),
            "review": str(review_path),
            "account_scope": "Synthetic public PAYG scope; no account assertion about a real user",
            "authorizations": authorizations,
        }
        record = {
            "format": "buddha.improver-launch.v1",
            "proposal": self.reference(proposal_path),
            "approval": {},
            "directory": str(self.f.trial),
            "review": str(review_path),
            "source_sha256": {str(path): sha(path.read_bytes()) for path in self.api._sources()},
            "timeout_seconds": 300,
        }
        bundle = {
            "folder": folder,
            "proposal_path": proposal_path,
            "approval_path": approval_path,
            "path": launch_path,
            "review_path": review_path,
            "proposal": proposal,
            "approval": approval,
            "record": record,
            "directory": self.f.trial,
            "declaration": self.f.declaration,
            "authorities": dict(self.f.authorities),
            "extra": extra,
        }
        self.save(bundle)
        return bundle

    def save(self, bundle):
        bundle["approval_path"].write_bytes(_json(bundle["approval"]))
        bundle["record"]["approval"] = self.reference(bundle["approval_path"])
        bundle["path"].write_bytes(_json(bundle["record"]))
        return sha(bundle["path"].read_bytes())

    def check(self, bundle, *, expected=None):
        before = files(self.root), self.f.engine.physical_sends, self.f.engine.workers
        try:
            with (
                passive_only(self),
                patch("os.getenv", side_effect=AssertionError("credential environment read")),
                patch("os.environ.get", side_effect=AssertionError("credential environment read")),
            ):
                return self.api.check_launch(
                    bundle["path"],
                    expected_sha256=sha(bundle["path"].read_bytes())
                    if expected is None
                    else expected,
                )
        finally:
            self.assertEqual(
                (files(self.root), self.f.engine.physical_sends, self.f.engine.workers), before
            )

    def prepare(self, bundle):
        import test_gateway as gateway_fixtures

        from buddha import gateway

        checked = self.check(bundle)
        providers = list(dict.fromkeys(profile["provider"] for profile in checked["profiles"]))
        with patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True):
            fingerprints = gateway.credential_fingerprints(
                providers, context=sha(bundle["path"].read_bytes())
            )
        review = {
            "format": "buddha.account-review.v2",
            "checked_on": datetime.now(UTC).date().isoformat(),
            "credential_context": sha(bundle["path"].read_bytes()),
            "credential_fingerprints": fingerprints,
            "account_scope": bundle["approval"]["account_scope"],
        }
        bundle["review_path"].write_bytes(_json(review))
        bindings = {Path(path): digest for path, digest in checked["bindings"].items()}
        bindings[bundle["review_path"]] = sha(bundle["review_path"].read_bytes())
        self.assessment.prepare_improver_assessment_trial(
            bundle["directory"],
            declaration=bundle["declaration"],
            expected_sha256=sha(bundle["declaration"].read_bytes()),
            expected_runtime_sha256=self.f.engine.candidate.expected_runtime,
            authorizations=bundle["authorities"],
            development_review=review,
            input_bindings=bindings,
        )
        return checked, review

    def test_fresh_check_is_keyless_readonly_and_binds_all_three_original_phase_reserves(self):
        bundle = self.bundle()
        checked = self.check(bundle)
        self.assertEqual(checked["format"], "buddha.improver-launch-check.v1")
        self.assertEqual((checked["state"], checked["phase"]), ("fresh", "search"))
        self.assertIsNone(checked["stop_code"])
        self.assertIsNone(checked["review"])
        self.assertEqual(checked["directory"], str(bundle["directory"]))
        self.assertEqual(checked["review_path"], str(bundle["review_path"]))
        self.assertEqual(checked["definition_sha256"], sha(_json(self.definition)))
        self.assertEqual(checked["timeout_seconds"], 300)
        self.assertEqual(set(checked["authorizations"]), {"search", "validation", "final"})
        self.assertEqual(
            checked["authorizations"],
            {phase: str(authority.path) for phase, authority in bundle["authorities"].items()},
        )
        self.assertEqual(set(checked["funding"]["phases"]), set(checked["authorizations"]))
        for phase, limits in self.definition["phase_limits"].items():
            terms = checked["funding"]["phases"][phase]
            self.assertEqual({key: terms[key] for key in limits}, limits)
        self.assertEqual(
            checked["funding"]["totals"],
            dict.fromkeys(
                ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count"),
                0,
            ),
        )
        for path in (
            bundle["path"],
            bundle["approval_path"],
            bundle["proposal_path"],
            bundle["declaration"],
            bundle["extra"],
        ):
            self.assertEqual(checked["bindings"][str(path)], sha(path.read_bytes()))
        self.assertTrue(checked["profiles"])
        self.assertRegex(checked["state_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(bundle["directory"].exists())
        self.assertFalse(bundle["review_path"].exists())
        original = copy.deepcopy(checked)
        checked["bindings"].clear()
        checked["funding"]["phases"]["search"]["max_calls"] = 999
        checked["profiles"].clear()
        self.assertEqual(self.check(bundle), original)

    def test_unreviewed_hash_schema_paths_and_foreign_or_changed_phase_grants_refuse(self):
        for case in (
            "raw_hash",
            "extra_launch_field",
            "extra_approval_field",
            "missing_phase",
            "changed_phase_cap",
            "changed_scope",
            "substituted_phase",
            "foreign_identity",
            "canonical_alias",
            "missing_helper",
            "stale_control",
            "review_inside_output",
        ):
            with self.subTest(case=case):
                bundle = self.bundle()
                approval, record = bundle["approval"], bundle["record"]
                expected = None
                if case == "raw_hash":
                    expected = "0" * 64
                elif case == "extra_launch_field":
                    record["unreviewed"] = True
                elif case == "extra_approval_field":
                    approval["unreviewed"] = True
                elif case == "missing_phase":
                    del approval["authorizations"]["validation"]
                elif case == "changed_phase_cap":
                    approval["authorizations"]["final"]["max_calls"] += 1
                elif case == "changed_scope":
                    approval["authorizations"]["search"]["scope"] += "; foreign"
                elif case == "substituted_phase":
                    approval["authorizations"]["validation"] = copy.deepcopy(
                        approval["authorizations"]["final"]
                    )
                elif case == "foreign_identity":
                    approval["definition_sha256"] = "0" * 64
                elif case == "canonical_alias":
                    alias = bundle["folder"] / "alias"
                    alias.mkdir()
                    record["review"] = approval["review"] = str(alias / ".." / "review.json")
                elif case == "missing_helper":
                    del record["source_sha256"][str(Path(self.api.__file__).absolute())]
                elif case == "stale_control":
                    bundle["extra"].write_bytes(b"Changed after proposal review.\n")
                elif case == "review_inside_output":
                    record["review"] = approval["review"] = str(bundle["directory"] / "review.json")
                self.save(bundle)
                with self.assertRaises(self.Error):
                    self.check(bundle, expected=expected)

    def test_original_prepared_owner_locks_and_unknown_hold_stop_before_key_entry(self):
        from buddha import trial_fence

        bundle = self.bundle()
        _, review = self.prepare(bundle)
        prepared = self.check(bundle)
        self.assertEqual((prepared["state"], prepared["phase"]), ("prepared", "search"))
        self.assertEqual(prepared["review"], review)
        self.assertIsNone(prepared["stop_code"])
        first = bundle["directory"] / "search/study/common/0/0/screen/tasks/0/generation/owners/0"
        for name in (".trial-running.lock", "search/study/.search.lock"):
            lock = bundle["directory"] / name
            try:
                lock.write_bytes(b"Synthetic retained lock")
                self.assertEqual(self.check(bundle)["stop_code"], "execution_lock_present")
            finally:
                lock.unlink()
        # Model loss of the trial/review files without erasing their genuine
        # original grant enrollment. Preserve both synthetic artifacts in
        # verified sibling locations, then restore their exact bytes/paths.
        directory, review_path = bundle["directory"], bundle["review_path"]
        parked = directory.with_name(directory.name + "-preserved-for-test")
        parked_review = review_path.with_name("preserved-review-for-test.json")
        for source, target in ((directory, parked), (review_path, parked_review)):
            self.assertEqual(source.parent.resolve(), target.parent.resolve())
            self.assertTrue(source.resolve().is_relative_to(self.root.resolve()))
            self.assertTrue(target.resolve().is_relative_to(self.root.resolve()))
            self.assertFalse(target.exists())
        original_files = files(self.root)
        directory.rename(parked)
        try:
            review_path.rename(parked_review)
            try:
                with self.assertRaises(self.Error):
                    self.check(bundle)
                self.assertFalse(directory.exists())
                self.assertFalse(review_path.exists())
            finally:
                parked_review.rename(review_path)
        finally:
            parked.rename(directory)
            self.assertEqual(files(self.root), original_files)
        authority = bundle["authorities"]["search"]
        ledger = authority.for_run(first)
        operation_id = sha(b"synthetic matched-launch unknown attempt")
        with trial_fence.work(authority.path, authority._terms(), directory=first, kind="gateway"):
            ledger.reserve(operation_id, sha(b"synthetic pending request"), 1)
            ledger.dispatch(operation_id)
            ledger.mark_unknown(operation_id)
        blocked = self.check(bundle)
        self.assertEqual(blocked["stop_code"], "unknown_operations")
        self.assertEqual(blocked["funding"]["totals"]["reserved_microusd"], 1)
        with (
            passive_only(self),
            patch("buddha.credentials.key_environment", side_effect=AssertionError("key entry")),
        ):
            result = self.api.launch(
                bundle["path"],
                expected_sha256=sha(bundle["path"].read_bytes()),
                live=True,
                prompt_keys=True,
                confirm_project_keys=True,
                notice=lambda text: None,
            )
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["reason"], "unknown_operations")
        self.assertEqual(self.check(bundle)["funding"], blocked["funding"])

    def test_real_handoff_then_late_control_change_is_refused_without_publication(self):
        bundle = self.bundle()
        extra = bundle["extra"]
        original = extra.read_bytes()
        before = files(self.root)
        actual = self.handoff.check_improver_handoff
        changed = []

        def checked_then_change(*args, **kwargs):
            result = actual(*args, **kwargs)
            if not changed:
                extra.write_bytes(original + b"Late test-induced drift.\n")
                changed.append(True)
            return result

        try:
            with (
                passive_only(self),
                patch.object(
                    self.handoff, "check_improver_handoff", side_effect=checked_then_change
                ),
                self.assertRaises(self.Error),
            ):
                self.api.check_launch(
                    bundle["path"], expected_sha256=sha(bundle["path"].read_bytes())
                )
            self.assertEqual(changed, [True])
        finally:
            extra.write_bytes(original)
            self.assertEqual(files(self.root), before)

    def test_key_entry_change_and_untrusted_receipt_cannot_publish_or_overwrite_inputs(self):
        import test_gateway as gateway_fixtures

        from buddha import credentials

        bundle = self.bundle()
        protected_receipt = (
            Path(self.definition["generation"]["roots"]["agent"]) / "new-receipt.json"
        )
        before = files(self.root)
        with (
            passive_only(self),
            patch("buddha.credentials.key_environment", side_effect=AssertionError("key entry")),
            self.assertRaises(self.Error),
        ):
            self.api.launch(
                bundle["path"],
                expected_sha256="0" * 64,
                receipt=protected_receipt,
                notice=lambda text: None,
            )
        self.assertFalse(protected_receipt.exists())
        self.assertEqual(files(self.root), before)
        extra, real_environment = bundle["extra"], credentials.key_environment
        original, entered = extra.read_bytes(), []

        @contextmanager
        def change_during_entry(*args, **kwargs):
            with real_environment(*args, **kwargs):
                entered.append(True)
                extra.write_bytes(original + b"Changed during local key entry.\n")
                yield

        try:
            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": gateway_fixtures.KEY}, clear=True),
                patch.object(credentials, "key_environment", side_effect=change_during_entry),
                patch("buddha.executor.run_container", side_effect=AssertionError("worker")),
                patch("http.client.HTTPSConnection", side_effect=AssertionError("network")),
                self.assertRaises(self.Error),
            ):
                self.api.launch(
                    bundle["path"],
                    expected_sha256=sha(bundle["path"].read_bytes()),
                    live=True,
                    confirm_project_keys=True,
                    notice=lambda text: None,
                )
            self.assertEqual(entered, [True])
            self.assertFalse(bundle["directory"].exists())
            self.assertFalse(bundle["review_path"].exists())
        finally:
            extra.write_bytes(original)
            self.assertEqual(files(self.root), before)


class ImproverLaunchInterfaceTests(unittest.TestCase):
    def test_caller_pinned_matched_launch_interfaces_are_available(self):
        from buddha.improver_launch import check_launch, launch

        self.assertTrue(callable(check_launch))
        self.assertTrue(callable(launch))


if __name__ == "__main__":
    unittest.main()
