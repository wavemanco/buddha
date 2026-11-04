"""A failed caller pin cannot arm a receipt inside original evidence or inputs."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_launch as launch_fixtures


class SourceLaunchReceiptTests(unittest.TestCase):
    def setUp(self):
        self.f = launch_fixtures.SourceLaunchTests("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def refuse_without_writing(self, receipt):
        self.f.save()
        before = self.f.snapshot()
        self.assertFalse(receipt.exists())
        with (
            patch.dict(os.environ, {}, clear=True),
            self.f.passive(),
            self.assertRaises(self.f.Error),
        ):
            self.f.api.launch(
                self.f.launch_path,
                expected_sha256="0" * 64,
                receipt=receipt,
                notice=lambda _: None,
            )
        self.assertFalse(receipt.exists(), "untrusted controls cannot authorize a receipt write")
        self.assertEqual(self.f.snapshot(), before)

    def test_bad_caller_pin_cannot_add_a_receipt_to_selected_agent_component(self):
        agent = Path(self.f.f.seed.to_record()["generation"]["roots"]["agent"])
        self.refuse_without_writing(agent / "unexpected-receipt.json")

    def test_bad_caller_pin_cannot_add_a_receipt_to_original_prepared_owner(self):
        self.f.f.prepare()
        owner = self.f.f.directory / "seed/tasks/0/generation/owners/0"
        self.assertTrue((owner / "manifest.json").is_file())
        self.refuse_without_writing(owner / "unexpected-receipt.json")

    def test_bad_caller_pin_cannot_create_the_absent_original_review(self):
        self.refuse_without_writing(self.f.review)


class LaunchOptionTests(unittest.TestCase):
    def test_huge_heartbeat_is_a_typed_precheck_refusal_for_both_launchers(self):
        from buddha import source_launch

        for module, error in ((source_launch, source_launch.SourceLaunchError),):
            with (
                self.subTest(launcher=module.__name__),
                patch.object(module, "check_launch", side_effect=AssertionError("checked")),
                self.assertRaises(error),
            ):
                module.launch(
                    Path(module.__file__),
                    expected_sha256="0" * 64,
                    heartbeat_seconds=10**1000,
                    notice=lambda _: self.fail("an invalid launch emitted progress"),
                )


if __name__ == "__main__":
    unittest.main()
