"""Recorded source closure is metadata, separate from current active CORE checks."""

import base64
import copy
import hashlib
import json
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

LEGACY_CORE = frozenset(
    {
        "buddha",
        "buddha.gateway",
        "buddha.wire",
        "buddha.releases",
        "buddha.authorization",
        "buddha.ledger",
        "buddha.history",
        "buddha.provider",
        "buddha.common",
    }
)


def metadata_core(names):
    # Pure contract data, not an assertion that a producer executed this source.
    return {name: hashlib.sha256(name.encode()).hexdigest() for name in sorted(names)}


class TrialFenceHistoryTests(unittest.TestCase):
    def test_passive_witness_owner_uses_recorded_identity_and_active_path_still_checks_files(self):
        from buddha import gateway_history, source_search

        fixture = json.loads(
            (Path(__file__).parent / "fixtures/gateway-v1-old-core.json").read_bytes()
        )
        raw = zlib.decompress(base64.b64decode(fixture["manifest"]["data"], validate=True))
        manifest = gateway_history._manifest(raw, fixture["manifest_sha256"])
        authority = Path(manifest["authorization_path"])
        directory = authority.parent / "synthetic-stage"
        reader = SimpleNamespace(
            authorization=authority,
            owner=Mock(return_value=SimpleNamespace(manifest=manifest, run_id=manifest["run_id"])),
            _bindings=Mock(return_value={}),
        )
        state = {
            "record": {"review": manifest["review"]},
            "funding": {
                "auth_runs": [
                    {
                        "run_id": manifest["run_id"],
                        "historical": 0,
                        "runtime_sha256": manifest["execution_sha256"],
                    }
                ]
            },
        }
        section = {
            "selection": manifest["selection"],
            "roots": manifest["roots"],
            **manifest["settings"],
        }
        with patch.object(source_search.gateway, "execution_identity") as active_identity:
            source_search._stage_owner(reader, state, directory, section, {})
            active_identity.assert_not_called()
            state["funding"]["auth_runs"][0]["runtime_sha256"] = "0" * 64
            with self.assertRaises(source_search.SourceSearchError):
                source_search._stage_owner(reader, state, directory, section, {})
            active_identity.assert_not_called()
            state["funding"]["auth_runs"][0]["runtime_sha256"] = manifest["execution_sha256"]
            source_search._stage_owner(reader, state, directory, section, {}, verify_files=True)
            active_identity.assert_called_once()
            self.assertEqual(active_identity.call_args.args, (directory, manifest))
            self.assertIs(active_identity.call_args.kwargs.get("verify_files", True), True)

    def test_recorded_legacy_core_filters_only_new_helper_without_source_reads(self):
        from buddha import candidate_generation, gateway
        from buddha.candidate_generation import _recorded_sources

        core = metadata_core(LEGACY_CORE)
        core_before = copy.deepcopy(core)
        for recipe_format in (
            "buddha.candidate-generation.v1",
            "buddha.candidate-generation.v2",
        ):
            paths = candidate_generation._sources(recipe_format)
            original = list(paths)
            expected = [path for path in paths if path.name != "trial_fence.py"]
            self.assertEqual(len(paths) - len(expected), 1)
            with (
                self.subTest(recipe_format=recipe_format),
                patch.object(Path, "open", side_effect=AssertionError("retired source opened")),
                patch.object(Path, "stat", side_effect=AssertionError("retired source stat")),
                patch.object(Path, "lstat", side_effect=AssertionError("retired source lstat")),
                patch.object(gateway, "_core_sources", side_effect=AssertionError("current CORE")),
            ):
                self.assertEqual(_recorded_sources(paths, core), expected)
            self.assertEqual(paths, original)
            self.assertEqual(core, core_before)
            # Selecting historical metadata must never weaken prospective preparation.
            self.assertEqual(candidate_generation._sources(recipe_format), original)
            self.assertIn("trial_fence.py", [path.name for path in original])

    def test_recorded_fenced_core_requires_helper_and_preserves_complete_order(self):
        from buddha import candidate_generation
        from buddha.candidate_generation import CandidateGenerationError, _recorded_sources

        paths = candidate_generation._sources("buddha.candidate-generation.v2")
        core = metadata_core(LEGACY_CORE | {"buddha.trial_fence"})
        original = list(paths)
        with (
            patch.object(Path, "open", side_effect=AssertionError("source opened")),
            patch.object(Path, "stat", side_effect=AssertionError("source stat")),
            patch.object(Path, "lstat", side_effect=AssertionError("source lstat")),
        ):
            result = _recorded_sources(paths, core)
            self.assertIs(type(result), list)
            self.assertEqual(result, original)
            missing = [path for path in paths if path.name != "trial_fence.py"]
            with self.assertRaises(CandidateGenerationError):
                _recorded_sources(missing, core)
        self.assertEqual(paths, original)

    def test_recorded_candidate_core_profiles_and_digests_are_closed(self):
        from buddha import candidate_generation
        from buddha.candidate_generation import CandidateGenerationError, _recorded_sources

        paths = candidate_generation._sources("buddha.candidate-generation.v2")
        scientific_old = (LEGACY_CORE - {"buddha.common"}) | {
            "buddha.benchmark",
            "buddha.evaluation",
        }
        bad_digest = metadata_core(LEGACY_CORE)
        bad_digest["buddha.gateway"] = True
        malformed_digest = metadata_core(LEGACY_CORE)
        malformed_digest["buddha.gateway"] = "not-a-source-sha256"
        cases = {
            "missing original module": metadata_core(LEGACY_CORE - {"buddha.common"}),
            "unknown future module": metadata_core(LEGACY_CORE | {"buddha.unreviewed"}),
            "different older scientific profile": metadata_core(scientific_old),
            "boolean digest": bad_digest,
            "malformed digest": malformed_digest,
            "not an inventory": list(LEGACY_CORE),
        }
        for label, core in cases.items():
            with self.subTest(label=label), self.assertRaises(CandidateGenerationError):
                _recorded_sources(paths, core)

    def test_genuine_older_raw_history_manifest_remains_independent_of_current_core(self):
        from buddha import gateway, gateway_history

        fixture = json.loads(
            (Path(__file__).parent / "fixtures/gateway-v1-old-core.json").read_bytes()
        )
        self.assertEqual(
            fixture["provenance"]["commit"], "7d1ebd2325788f928b6f8da7b5347eabca2d42a8"
        )
        raw = zlib.decompress(base64.b64decode(fixture["manifest"]["data"], validate=True))
        self.assertEqual(len(raw), fixture["manifest"]["bytes"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture["manifest"]["sha256"])
        original = json.loads(raw)
        with (
            patch.object(gateway, "CORE", frozenset({"buddha.future_uninstalled_core"})),
            patch.object(gateway, "_core_sources", side_effect=AssertionError("current source")),
            patch.object(
                gateway, "validate_manifest", side_effect=AssertionError("active validator")
            ),
            patch.object(
                gateway, "execution_identity", side_effect=AssertionError("active runtime")
            ),
            patch.object(Path, "open", side_effect=AssertionError("producer opened")),
        ):
            manifest = gateway_history._manifest(raw, fixture["manifest_sha256"])
        self.assertEqual(manifest["core"], original["core"])
        self.assertEqual(len(manifest["core"]), 10)
        self.assertIn("buddha.benchmark", manifest["core"])
        self.assertIn("buddha.evaluation", manifest["core"])
        self.assertNotIn("buddha.common", manifest["core"])
        self.assertNotIn("buddha.trial_fence", manifest["core"])
        # This checks an existing genuine raw-manifest fixture only. It is not
        # a retrofitted current owner or old candidate-generation attestation.
