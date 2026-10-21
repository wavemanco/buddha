"""Original caller-reviewed bytes must precede every owner manifest publication."""

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_gateway as gateway_fixtures
import test_policy_run as fixtures

from buddha import baseline, gateway, native_evaluation, policy_run
from buddha.gateway import Gateway, GatewayError, RawHTTPTransport, _read_manifest
from buddha.policy_run import PolicyRunError
from buddha.releases import _json


class PublicationBindingsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PolicyRunTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.original_descriptor = _json(self.fixture.record)
        self.expected_digest = hashlib.sha256(self.original_descriptor).hexdigest()
        self.first_owner = self.fixture.directory / "cells/0/baseline/owners/0"

    def failed_first_preparation(self):
        original = baseline.prepare_gateway

        def changed(owner, **arguments):
            self.assertEqual(owner, self.first_owner)
            # Valid, equivalent JSON with different reviewed physical bytes.
            # Drift happens after the study's snapshot, before Gateway captures it.
            self.fixture.descriptor.write_bytes(self.original_descriptor + b"\n")
            return original(owner, **arguments)

        with patch.object(baseline, "prepare_gateway", side_effect=changed):
            with self.assertRaises(PolicyRunError):
                self.fixture.prepare()
        self.assertEqual(self.fixture.fixture.physical_sends, 0)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_first_owner_cannot_publish_newly_observed_control_after_failed_prepare(self):
        self.failed_first_preparation()
        manifest = self.first_owner / "manifest.json"
        if manifest.exists():
            records = json.loads(manifest.read_bytes())["invocation"]["inputs"]
            recorded = {row["path"]: row["sha256"] for row in records}
            self.assertEqual(recorded[str(self.fixture.descriptor)], self.expected_digest)
        self.assertFalse(manifest.exists(), "changed original input reached manifest publication")

    def test_ignoring_failed_prepare_cannot_resume_changed_original_control(self):
        self.failed_first_preparation()
        incomplete = {"status": "incomplete", "reason": "agent_error", "stages": []}
        with patch.object(baseline, "run_baseline", return_value=incomplete) as child:
            try:
                policy_run.run_study(
                    self.fixture.directory, transport=RawHTTPTransport(allow_paid=False)
                )
            except PolicyRunError:
                pass
            self.assertEqual(child.call_count, 0, "failed preparation became executable state")
        self.assertEqual(self.fixture.fixture.physical_sends, 0)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)


class GatewayPublicationBindingsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = gateway_fixtures.GatewayTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.expected = hashlib.sha256(self.fixture.input_file.read_bytes()).hexdigest()

    def test_expected_hash_is_recorded_without_changing_input_order_or_schema(self):
        second = self.fixture.root / "publication.json"
        second.write_bytes(b'{"protocol":"frozen"}')
        directory = self.fixture.prepare(
            "pinned",
            input_files=[second, self.fixture.input_file],
            expected_input_hashes={self.fixture.input_file: self.expected},
        )
        inputs = _read_manifest(directory)["invocation"]["inputs"]
        self.assertEqual(
            inputs,
            [
                {"path": str(second), "sha256": hashlib.sha256(second.read_bytes()).hexdigest()},
                {"path": str(self.fixture.input_file), "sha256": self.expected},
            ],
        )
        self.assertEqual(
            set(_read_manifest(directory)), set(_read_manifest(self.fixture.directory))
        )

    def test_changed_expected_input_is_rejected_before_owner_or_funding_publication(self):
        self.fixture.input_file.write_bytes(b'{"changed":"after review"}')
        runs = self.fixture.authority.summary()["runs"]
        with self.assertRaises(GatewayError):
            self.fixture.prepare(
                "changed", expected_input_hashes={self.fixture.input_file: self.expected}
            )
        self.assertFalse((self.fixture.root / "changed").exists())
        self.assertEqual(self.fixture.authority.summary()["runs"], runs)

    def test_pins_must_be_bounded_typed_digests_and_actual_invocation_members(self):
        missing = self.fixture.root / "not-an-input.json"
        missing.write_bytes(b"{}")
        cases = [
            [],
            {str(self.fixture.input_file): self.expected},
            {self.fixture.input_file: "bad"},
            {self.fixture.input_file: False},
            {missing: hashlib.sha256(b"{}").hexdigest()},
            {self.fixture.root / str(index): "0" * 64 for index in range(1025)},
        ]
        for index, pins in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(GatewayError):
                self.fixture.prepare("invalid-" + str(index), expected_input_hashes=pins)
            self.assertFalse((self.fixture.root / ("invalid-" + str(index))).exists())

    def test_later_drift_leaves_reviewed_hash_never_newly_observed_hash(self):
        original_profiles = gateway._profiles

        def changed(*arguments):
            result = original_profiles(*arguments)
            self.fixture.input_file.write_bytes(b'{"changed":"after input capture"}')
            return result

        with patch.object(gateway, "_profiles", side_effect=changed):
            with self.assertRaises(GatewayError):
                self.fixture.prepare(
                    "later-drift", expected_input_hashes={self.fixture.input_file: self.expected}
                )
        directory = self.fixture.root / "later-drift"
        self.assertEqual(
            _read_manifest(directory)["invocation"]["inputs"],
            [{"path": str(self.fixture.input_file), "sha256": self.expected}],
        )
        with self.assertRaises(GatewayError):
            Gateway(directory, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(len(self.fixture.authority.summary()["runs"]), 1)

    def test_default_preserves_ordered_unpinned_input_records(self):
        second = self.fixture.root / "second.json"
        second.write_bytes(b"{}")
        directory = self.fixture.prepare(
            "legacy-default", input_files=[second, self.fixture.input_file]
        )
        self.assertEqual(
            _read_manifest(directory)["invocation"]["inputs"],
            [
                {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in (second, self.fixture.input_file)
            ],
        )


class StudyPublicationBindingsTests(unittest.TestCase):
    setUp = PublicationBindingsTests.setUp

    def prepare_with(self, pins):
        self.fixture.descriptor.write_bytes(self.original_descriptor)
        return policy_run.prepare_study(
            self.fixture.directory,
            descriptor=self.fixture.descriptor,
            authorization=self.fixture.authority,
            review=self.fixture.fixture.fixture.review,
            input_bindings=pins,
        )

    def test_external_publication_is_in_original_owner_and_recovered_without_resupply(self):
        publication = self.fixture.root / "publication.json"
        publication.write_bytes(b'{"reviewed":"external immutable publication"}')
        digest = hashlib.sha256(publication.read_bytes()).hexdigest()
        self.prepare_with({publication: digest})
        records = _read_manifest(self.first_owner)["invocation"]["inputs"]
        self.assertIn({"path": str(publication), "sha256": digest}, records)

        def stop(directory, execution, authority, review, controls, bindings, transport):
            self.assertIn(publication, controls)
            self.assertEqual(bindings[str(publication)], digest)
            raise PolicyRunError("stop before any child execution")

        with patch.object(policy_run, "_preflight", side_effect=stop) as preflight:
            with self.assertRaises(PolicyRunError):
                policy_run.run_study(
                    self.fixture.directory, transport=RawHTTPTransport(allow_paid=False)
                )
            self.assertEqual(preflight.call_count, 1)
        self.assertEqual(self.fixture.fixture.physical_sends, 0)

    def test_publication_reaches_every_owner_and_original_keyless_replay(self):
        publication = self.fixture.root / "publication.json"
        literal = b'{"protocol":"reviewed immutable publication"}'
        publication.write_bytes(literal)
        digest = hashlib.sha256(literal).hexdigest()
        self.prepare_with({publication: digest})
        report = self.fixture.run_study()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(self.fixture.fixture.physical_sends, 64)
        owners = self.fixture.authority.summary()["runs"]
        self.assertEqual(len(owners), 56)
        for owner in owners:
            with self.subTest(owner=owner["directory"]):
                inputs = _read_manifest(Path(owner["directory"]))["invocation"]["inputs"]
                self.assertIn({"path": str(publication), "sha256": digest}, inputs)
        original_files = {
            path: path.read_bytes() for path in self.fixture.directory.rglob("*") if path.is_file()
        }
        reused = self.fixture.run_study(paid=False)
        self.assertEqual(reused, report)
        self.assertEqual(self.fixture.fixture.physical_sends, 64)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 64)
        self.assertEqual({path: path.read_bytes() for path in original_files}, original_files)
        publication.write_bytes(literal + b"\n")
        with patch.object(baseline, "run_baseline") as child:
            with self.assertRaises(PolicyRunError):
                self.fixture.run_study(paid=False)
            child.assert_not_called()
        self.assertEqual(self.fixture.fixture.physical_sends, 64)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 64)

    def test_fresh_occasion_cannot_adopt_changed_original_publication(self):
        publication = self.fixture.root / "publication.json"
        original = b'{"protocol":"original immutable publication"}'
        publication.write_bytes(original)
        self.prepare_with({publication: hashlib.sha256(original).hexdigest()})
        owner = self.fixture.directory / "cells/0/judgments/1/owners/1"
        completed_baseline = self.fixture.directory / "cells/0/baseline/report.json"
        prepare = native_evaluation.prepare_gateway
        preserved = []

        def changed(path, **arguments):
            if path == owner:
                preserved.append(completed_baseline.read_bytes())
                publication.write_bytes(original + b"\n")
            return prepare(path, **arguments)

        with patch.object(native_evaluation, "prepare_gateway", side_effect=changed):
            with self.assertRaises(PolicyRunError):
                self.fixture.run_study()
        self.assertEqual(len(preserved), 1)
        self.assertEqual(completed_baseline.read_bytes(), preserved[0])
        self.assertEqual(self.fixture.fixture.physical_sends, 6)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 6)
        self.assertFalse(owner.exists())
        with (
            patch.object(baseline, "run_baseline") as generation,
            patch.object(native_evaluation, "run_evaluation") as evaluation,
        ):
            with self.assertRaises(PolicyRunError):
                self.fixture.run_study(paid=False)
            generation.assert_not_called()
            evaluation.assert_not_called()
        self.assertEqual(self.fixture.fixture.physical_sends, 6)

    def test_changed_publication_pin_is_rejected_before_first_owner(self):
        publication = self.fixture.root / "publication.json"
        publication.write_bytes(b'{"reviewed":"changed"}')
        with self.assertRaises(PolicyRunError):
            self.prepare_with({publication: hashlib.sha256(b"original").hexdigest()})
        self.assertFalse(self.first_owner.exists())
        self.assertEqual(self.fixture.authority.summary()["runs"], [])

    def test_publication_changed_at_gateway_boundary_is_not_newly_adopted(self):
        publication = self.fixture.root / "publication.json"
        original = b'{"reviewed":"original"}'
        publication.write_bytes(original)
        prepare = baseline.prepare_gateway

        def changed(owner, **arguments):
            publication.write_bytes(original + b"\n")
            return prepare(owner, **arguments)

        with patch.object(baseline, "prepare_gateway", side_effect=changed):
            with self.assertRaises(PolicyRunError):
                self.prepare_with({publication: hashlib.sha256(original).hexdigest()})
        self.assertFalse(self.first_owner.exists())
        with patch.object(baseline, "run_baseline") as child:
            with self.assertRaises(PolicyRunError):
                policy_run.run_study(
                    self.fixture.directory, transport=RawHTTPTransport(allow_paid=False)
                )
            child.assert_not_called()


if __name__ == "__main__":
    unittest.main()
