"""Prospective copy policy must survive proposal, launch and prepared custody."""

import copy
import json
import unittest
from unittest.mock import patch

import test_source_handoff as handoff_fixtures
import test_source_launch as launch_fixtures

from buddha import source_launch_state, source_search
from buddha.releases import _json

SOURCE_COPY_POLICY = {
    "format": "buddha.source-copy.v1",
    "method": "verified_private_snapshot_before_owner",
}


class SourceCopyHandoffTests(unittest.TestCase):
    def handoff_fixture(self):
        case = handoff_fixtures.SourceHandoffTests("runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def check_handoff(self, case, record):
        pin = case.write(record)
        before = case.snapshot()
        try:
            with (
                patch("sqlite3.connect", side_effect=AssertionError("no handoff SQL")),
                patch("http.client.HTTPSConnection", side_effect=AssertionError("no provider")),
                patch("buddha.executor.run_container", side_effect=AssertionError("no worker")),
                patch(
                    "buddha.source_search.prepare_source_search",
                    side_effect=AssertionError("no handoff owner"),
                ),
            ):
                return case.check(case.path, expected_sha256=pin)
        finally:
            self.assertEqual(case.snapshot(), before)

    def launch_fixture(self, version):
        case = launch_fixtures.SourceLaunchTests("runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        if version >= 2:
            case.witness_handoff()
        if version == 3:
            case.proposal.update(
                format="buddha.source-handoff.v3", source_copy=copy.deepcopy(SOURCE_COPY_POLICY)
            )
            self.save_proposal(case)
        return case

    @staticmethod
    def save_proposal(case):
        case.proposal_path.write_bytes(_json(case.proposal))
        case.proposal_sha = launch_fixtures.sha(case.proposal_path.read_bytes())
        case.approval["proposal_sha256"] = case.proposal_sha
        case.record["proposal"] = case.reference(case.proposal_path)

    def test_handoff_v3_binds_exact_copy_policy_and_old_versions_remain_no_copy(self):
        case = self.handoff_fixture()
        for version in (1, 2, 3):
            with self.subTest(version=version):
                record = copy.deepcopy(case.record)
                record["format"] = f"buddha.source-handoff.v{version}"
                if version >= 2:
                    record["mutation_witness"] = copy.deepcopy(handoff_fixtures.WITNESS_POLICY)
                if version == 3:
                    record["source_copy"] = copy.deepcopy(SOURCE_COPY_POLICY)
                checked = self.check_handoff(case, record)
                self.assertEqual(checked["format"], f"buddha.source-handoff-check.v{version}")
                if version == 3:
                    self.assertEqual(checked["source_copy"], SOURCE_COPY_POLICY)
                    self.assertEqual(checked["mutation_witness"], handoff_fixtures.WITNESS_POLICY)
                else:
                    self.assertNotIn("source_copy", checked)
                    self.assertNotIn("source_copy", record)

    def test_copy_policy_is_closed_versioned_and_requires_the_fixed_witness(self):
        case = self.handoff_fixture()
        prospective = case.record | {
            "format": "buddha.source-handoff.v3",
            "mutation_witness": copy.deepcopy(handoff_fixtures.WITNESS_POLICY),
            "source_copy": copy.deepcopy(SOURCE_COPY_POLICY),
        }
        invalid = [
            prospective | {"format": "buddha.source-handoff.v1"},
            prospective | {"format": "buddha.source-handoff.v2"},
            {key: value for key, value in prospective.items() if key != "source_copy"},
            {key: value for key, value in prospective.items() if key != "mutation_witness"},
            prospective | {"mutation_witness": handoff_fixtures.WITNESS_POLICY | {"depth": 2}},
        ]
        invalid.extend(
            prospective | {"source_copy": policy}
            for policy in (
                None,
                False,
                {"format": "buddha.source-copy.v1"},
                SOURCE_COPY_POLICY | {"format": "buddha.source-copy.v2"},
                SOURCE_COPY_POLICY | {"method": "reuse_original_directory"},
                SOURCE_COPY_POLICY | {"optional": True},
            )
        )
        for ordinal, record in enumerate(invalid):
            with self.subTest(case=ordinal), self.assertRaises(case.Error):
                self.check_handoff(case, record)

    def test_launcher_passes_explicit_copy_choice_to_preparation_and_retained_inspection(self):
        for version, manifest_version in ((1, 2), (2, 3), (3, 4)):
            with self.subTest(version=version):
                case = self.launch_fixture(version)
                pin = case.save()
                with (
                    patch(
                        "buddha.source_search.prepare_source_search",
                        wraps=source_search.prepare_source_search,
                    ) as prepared,
                    patch(
                        "buddha.source_launch_state.inspect_prepared_search",
                        wraps=source_launch_state.inspect_prepared_search,
                    ) as inspected,
                    patch(
                        "buddha.source_search.run_source_search", side_effect=KeyboardInterrupt
                    ) as run,
                    self.assertRaises(KeyboardInterrupt),
                ):
                    case.run_launch(pin)
                prepared.assert_called_once()
                inspected.assert_called_once()
                run.assert_called_once()
                for call in (prepared.call_args, inspected.call_args):
                    self.assertIs(call.kwargs["source_copy"], version == 3)
                    self.assertIs(call.kwargs["mutation_witness"], version >= 2)
                manifest = json.loads((case.f.directory / "manifest.json").read_bytes())
                self.assertEqual(
                    manifest["format"], f"buddha.source-search-manifest.v{manifest_version}"
                )
                if version == 3:
                    self.assertEqual(manifest["source_copy"], SOURCE_COPY_POLICY)
                else:
                    self.assertNotIn("source_copy", manifest)
                before = case.snapshot()
                with (
                    patch(
                        "buddha.source_launch_state.inspect_prepared_search",
                        wraps=source_launch_state.inspect_prepared_search,
                    ) as retained,
                    case.passive(),
                ):
                    checked = case.api.check_launch(case.launch_path, expected_sha256=pin)
                self.assertEqual(checked["state"], "prepared")
                self.assertIs(retained.call_args.kwargs["source_copy"], version == 3)
                self.assertEqual(case.snapshot(), before)
                self.assertEqual(case.f.engine.physical_sends, 0)

    def test_copy_launch_refuses_coherently_prepared_witnessed_no_copy_downgrade(self):
        case = self.launch_fixture(3)
        pin = case.save()
        original = source_search.prepare_source_search

        def downgrade(*args, **kwargs):
            self.assertIs(kwargs["source_copy"], True)
            self.assertIs(kwargs["mutation_witness"], True)
            return original(*args, **(kwargs | {"source_copy": False}))

        with (
            patch("buddha.source_search.prepare_source_search", side_effect=downgrade),
            patch("buddha.source_search.run_source_search") as run,
            self.assertRaises(case.Error),
        ):
            case.run_launch(pin)
        run.assert_not_called()
        manifest = json.loads((case.f.directory / "manifest.json").read_bytes())
        self.assertEqual(manifest["format"], "buddha.source-search-manifest.v3")
        self.assertEqual(manifest["mutation_witness"], handoff_fixtures.WITNESS_POLICY)
        self.assertNotIn("source_copy", manifest)
        self.assertTrue(
            (case.f.directory / "seed/tasks/0/generation/owners/0/manifest.json").is_file()
        )
        self.assertEqual(case.f.engine.physical_sends, 0)
        self.assertEqual(case.f.authority.summary()["operation_count"], 0)
        before = case.snapshot()
        with case.passive(), self.assertRaises(case.Error):
            case.api.check_launch(case.launch_path, expected_sha256=pin)
        self.assertEqual(case.snapshot(), before)

    def test_launch_rejects_rebound_wrong_policy_before_preparation_or_dispatch(self):
        case = self.launch_fixture(3)
        case.proposal["source_copy"] = SOURCE_COPY_POLICY | {"method": "reuse_original_directory"}
        self.save_proposal(case)
        pin = case.save()
        with (
            patch("buddha.source_search.prepare_source_search") as prepared,
            patch("buddha.source_search.run_source_search") as run,
            self.assertRaises(case.Error),
        ):
            case.run_launch(pin)
        prepared.assert_not_called()
        run.assert_not_called()
        self.assertFalse(case.f.directory.exists())
        self.assertFalse(case.review.exists())
        self.assertEqual(case.f.engine.physical_sends, 0)
        self.assertEqual(case.f.authority.summary()["operation_count"], 0)


if __name__ == "__main__":
    unittest.main()
