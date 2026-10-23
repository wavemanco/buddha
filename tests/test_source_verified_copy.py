"""Prospective source copies; real stage custody with supplied worker channels.

The private helper tables test physical source boundaries without executing source.
The composed case uses the existing simulated executor, not actual containers or
official benchmark semantics. All files, grants and replies are fresh fixtures.
"""

import copy
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_mutation_witness as witnesses
import test_source_search as fixtures

from buddha.releases import MAX_SOURCE_BYTES, ReleaseError, _json, inventory


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SourceVerifiedCopyTests(unittest.TestCase):
    def unit_fixture(self):
        from buddha import source_search

        case = fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(case.doCleanups)
        case.mutation_witness = True
        case.prepare()
        state = source_search._restore(case.directory, case.authority.path)
        stage = case.directory / "iterations/0"
        stage.mkdir()
        return case, state, stage

    @staticmethod
    def child_fixture(case, label, raw=None):
        """Helper-only metadata; the composed test supplies genuinely sealed proposals."""
        raw = fixtures.REPAIRED.encode() if raw is None else raw
        original = case.root / ("original-child-" + label)
        original.mkdir()
        (original / "candidate.py").write_bytes(raw)
        digest = sha(raw)
        lineage = original.parent / ("lineage-" + label + ".json")
        parent = case.seed.to_record()["generation"]["selection"]["components"]["agent"]
        lineage.write_bytes(
            _json(
                {
                    "format": "buddha.source-lineage.v1",
                    "parent": {
                        "entrypoint": "candidate.py",
                        "source_sha256": parent["candidate.py"],
                        "agent_sha256": case.seed.candidate_id,
                    },
                    "child": {
                        "entrypoint": "candidate.py",
                        "source_sha256": digest,
                        "agent_sha256": sha(_json({"candidate.py": digest})),
                    },
                    "descriptor_sha256": "0" * 64,
                    "feedback": {"file_sha256": "1" * 64, "input_sha256": "2" * 64},
                    "proposal_sha256": "3" * 64,
                    "owner": {
                        "path": str(case.root / "helper-only-proposal/owners/0"),
                        "manifest_sha256": "4" * 64,
                    },
                }
            )
            + b"\n"
        )
        return {
            "status": "complete",
            "disposition": "materialized",
            "parent_agent_sha256": case.seed.candidate_id,
            "child": {
                "directory": str(original),
                "entrypoint": "candidate.py",
                "source_sha256": digest,
                "agent_sha256": sha(_json({"candidate.py": digest})),
                "lineage": {"path": str(lineage), "sha256": sha(lineage.read_bytes())},
            },
        }

    def assert_projection(self, case, actual, proposal, root):
        expected = copy.deepcopy(case.seed.to_record())
        child = proposal["child"]
        generation = expected["generation"]
        generation["selection"]["components"]["agent"] = {"candidate.py": child["source_sha256"]}
        generation["roots"]["agent"] = str(root)
        generation["executor"]["mounts"] = [
            ["/agent", str(root)],
            ["/runner", generation["roots"]["runner"]],
        ]
        expected["lineage"] = child["lineage"]
        self.assertEqual(actual.to_record(), expected)
        self.assertEqual(actual.candidate_id, child["agent_sha256"])
        self.assertEqual(actual.comparison_key(), case.seed.comparison_key())

    def test_default_copy_roundtrip_binds_both_paths_preserves_lineage_and_resumes_same_owner(self):
        from buddha import candidate_generation, source_screen, source_search
        from buddha.source_launch import _planned_owners

        h = witnesses._Harness(self, iterations=2)
        case = h.case
        h.normal_callbacks = 0
        h.normal_sources = [fixtures.REPAIRED, fixtures.GRANDCHILD]
        # Call the public preparation's new default, independently of the old
        # witness fixture's explicitly historical preparation convenience.
        case.prepare()
        stage = case.directory / "seed-witness"
        generation = stage / "generation"
        snapshot = stage / "agent"
        actual_prepare = candidate_generation.prepare_candidate_generation
        interrupted = False

        def stop_after_original_prepare(directory, **kwargs):
            nonlocal interrupted
            if directory == generation and not interrupted:
                # This is the initial behavioral RED on the original controller:
                # it supplies the returned child directory instead of this root.
                self.assertEqual(kwargs["roots"]["agent"], snapshot)
                actual_prepare(directory, **kwargs)
                interrupted = True
                raise KeyboardInterrupt("supplied stop after the original owner was bound")
            return actual_prepare(directory, **kwargs)

        with (
            patch.object(
                candidate_generation,
                "prepare_candidate_generation",
                side_effect=stop_after_original_prepare,
            ),
            self.assertRaises(source_search.SourceSearchInterrupted) as caught,
        ):
            h.run()
        self.assertEqual(caught.exception.partial["reason"], "cancelled")
        self.assertTrue(interrupted)
        owner = generation / "owners/0"
        manifest = json.loads((owner / "manifest.json").read_bytes())
        self.assertEqual(Path(manifest["roots"]["agent"]), snapshot)
        self.assertEqual(inventory(snapshot), manifest["selection"]["components"]["agent"])
        original_copy = (snapshot / "candidate.py").read_bytes()
        fixed_owner = case.h.files(owner)
        original_manifest = (owner / "manifest.json").read_bytes()
        fixed_authority = case.authority.summary()
        fixed_counts = case.engine.workers, case.engine.physical_sends
        for mode in ("missing", "changed", "foreign"):
            with self.subTest(bound_owner_source=mode):
                source, extra = snapshot / "candidate.py", snapshot / "foreign.py"
                if mode == "missing":
                    source.unlink()
                elif mode == "changed":
                    source.write_bytes(original_copy + b"\n# changed fixture\n")
                else:
                    extra.write_bytes(b"foreign source must not be silently removed\n")
                altered = case.h.files(snapshot)
                try:
                    with (
                        patch.object(
                            candidate_generation,
                            "prepare_candidate_generation",
                            side_effect=AssertionError("replacement owner preparation"),
                        ),
                        patch.object(
                            case, "execute", side_effect=AssertionError("dispatch after drift")
                        ),
                        self.assertRaises(case.Error),
                    ):
                        h.run()
                    self.assertEqual(case.h.files(snapshot), altered)
                    self.assertEqual(case.h.files(owner), fixed_owner)
                    self.assertEqual(case.authority.summary(), fixed_authority)
                    self.assertEqual(
                        (case.engine.workers, case.engine.physical_sends), fixed_counts
                    )
                finally:
                    # Restore only this intentionally corrupted synthetic setup,
                    # never through production recovery or a replacement owner.
                    if extra.exists():
                        extra.unlink()
                    source.write_bytes(original_copy)

        mounts = []
        execute = case.execute

        def observe(spec, *, initial, handle, **kwargs):
            if spec.role == "agent":
                mounts.append((handle.__self__.gateway.directory, dict(spec.mounts)["/agent"]))
            return execute(spec, initial=initial, handle=handle, **kwargs)

        case.execute = observe
        result = h.run()
        self.assertEqual(result["status"], "complete")
        self.assertEqual([row["status"] for row in result["decisions"]], ["admitted", "admitted"])
        self.assertEqual(
            json.loads((case.directory / "manifest.json").read_bytes())["format"],
            "buddha.source-search-manifest.v4",
        )
        self.assertEqual((owner / "manifest.json").read_bytes(), original_manifest)
        self.assertEqual(len(list((generation / "owners").iterdir())), 1)
        expected_mounts = {generation / "owners/0": snapshot}
        locations = [case.directory / "seed-witness"]
        locations += [case.directory / "iterations" / str(i) / "witness" for i in range(2)]
        locations += [case.directory / "iterations" / str(i) for i in range(2)]
        for location in locations:
            proposal = json.loads((location / "proposal/report.json").read_bytes())
            copied = location / "agent"
            original = Path(proposal["child"]["directory"]) / "candidate.py"
            self.assertNotEqual(copied, original.parent)
            self.assertEqual((copied / "candidate.py").read_bytes(), original.read_bytes())
            self.assertEqual(
                inventory(copied), {"candidate.py": proposal["child"]["source_sha256"]}
            )
            if location.name in {"witness", "seed-witness"}:
                descriptor = json.loads((location / "generation.json").read_bytes())
                self.assertEqual(descriptor["executor"]["mounts"][0], ["/agent", str(copied)])
                self.assertEqual(descriptor["tasks"], str(location / "task.json"))
                expected_mounts[location / "generation/owners/0"] = copied
            else:
                screened = source_screen.SourceScreen.from_bytes(
                    (location / "screen/screen.json").read_bytes()
                )
                self.assert_projection(case, screened, proposal, copied)
                screen_report = json.loads((location / "screen/report.json").read_bytes())
                self.assertEqual(screen_report["controls_sha256"], result["controls_sha256"])
                for task_index in range(len(case.seed.tasks.tasks)):
                    expected_mounts[
                        location / "screen/tasks" / str(task_index) / "generation/owners/0"
                    ] = copied
                expected_mounts[location / "witness/proposal/owners/0"] = copied
        expected_mounts[case.directory / "iterations/1/proposal/owners/0"] = (
            case.directory / "iterations/0/agent"
        )
        observed = dict(mounts)
        for path, expected in expected_mounts.items():
            self.assertEqual(observed[path], expected)
            bound = json.loads((path / "manifest.json").read_bytes())
            self.assertEqual(bound["roots"]["agent"], str(expected))
            original_generation = case.seed.to_record()["generation"]
            roots = original_generation["roots"] | {"agent": str(expected)}
            self.assertEqual(bound["roots"], roots)
            selected = copy.deepcopy(original_generation["selection"])
            selected["components"]["agent"] = inventory(expected)
            self.assertEqual(bound["selection"], selected)
        self.assertEqual(
            {Path(row["directory"]) for row in case.authority.summary()["runs"]},
            _planned_owners(case.directory, case.seed, 2, mutation_witness=True),
        )
        before = case.h.files(case.directory), case.authority.summary(), case.engine.physical_sends
        with patch.object(
            source_search,
            "_materialize_child_source",
            side_effect=AssertionError("completed replay attempted source materialization"),
        ):
            self.assertEqual(case.inspect(), result)
            self.assertEqual(h.run(paid=False), result)
        self.assertEqual(
            (case.h.files(case.directory), case.authority.summary(), case.engine.physical_sends),
            before,
        )

    def test_helper_copies_exact_bytes_and_changes_only_the_selected_agent_root(self):
        from buddha import source_search

        case, state, location = self.unit_fixture()
        proposal = self.child_fixture(case, "exact")
        original = Path(proposal["child"]["directory"])
        before = case.h.files(original), case.authority.summary()
        source_search._materialize_child_source(
            state, proposal, location, owner_directory=location / "screen"
        )
        copied = location / "agent"
        self.assertEqual(inventory(copied), {"candidate.py": proposal["child"]["source_sha256"]})
        self.assertEqual(
            (copied / "candidate.py").read_bytes(), (original / "candidate.py").read_bytes()
        )
        projected = source_search._child_screen(state, proposal, location)
        self.assert_projection(case, projected, proposal, copied)
        self.assertEqual((case.h.files(original), case.authority.summary()), before)
        self.assertFalse((location / "screen").exists())
        self.assertEqual((case.engine.workers, case.engine.physical_sends), (0, 0))

    def test_helper_refuses_missing_changed_foreign_linked_oversized_and_non_utf8_sources(self):
        from buddha import source_search

        case, state, root = self.unit_fixture()
        for mode in ("missing", "changed", "foreign", "linked", "oversized", "non_utf8"):
            with self.subTest(source=mode):
                location = root / mode
                location.mkdir()
                raw = None
                if mode == "oversized":
                    raw = b"#" + b"x" * MAX_SOURCE_BYTES
                elif mode == "non_utf8":
                    raw = b"\xffinvalid UTF-8 source"
                proposal = self.child_fixture(case, mode, raw)
                original = Path(proposal["child"]["directory"])
                source = original / "candidate.py"
                if mode == "missing":
                    source.unlink()
                elif mode == "changed":
                    source.write_bytes(b"changed after original metadata was captured\n")
                elif mode == "foreign":
                    (original / "foreign.py").write_bytes(b"unselected dependency\n")
                elif mode == "linked":
                    os.link(source, case.root / "source-hardlink.py")
                before = case.h.files(original), case.authority.summary()
                with self.assertRaises(ReleaseError):
                    source_search._materialize_child_source(
                        state, proposal, location, owner_directory=location / "screen"
                    )
                self.assertEqual((case.h.files(original), case.authority.summary()), before)
                self.assertFalse((location / "screen").exists())
                self.assertEqual((case.engine.workers, case.engine.physical_sends), (0, 0))

    def test_existing_changed_foreign_or_linked_copy_is_never_overwritten(self):
        from buddha import source_search

        case, state, root = self.unit_fixture()
        proposal = self.child_fixture(case, "destination")
        original = Path(proposal["child"]["directory"]) / "candidate.py"
        for mode in ("changed", "foreign", "linked"):
            with self.subTest(copy=mode):
                location = root / mode
                copied = location / "agent"
                copied.mkdir(parents=True)
                source = copied / "candidate.py"
                source.write_bytes(original.read_bytes())
                if mode == "changed":
                    source.write_bytes(b"preexisting different bytes\n")
                elif mode == "foreign":
                    (copied / "foreign.py").write_bytes(b"preexisting foreign source\n")
                else:
                    os.link(source, case.root / "destination-hardlink.py")
                before = case.h.files(copied), case.authority.summary()
                with self.assertRaises(ReleaseError):
                    source_search._materialize_child_source(
                        state, proposal, location, owner_directory=location / "screen"
                    )
                self.assertEqual((case.h.files(copied), case.authority.summary()), before)
                self.assertFalse((location / "screen").exists())
                self.assertEqual((case.engine.workers, case.engine.physical_sends), (0, 0))

    def test_explicit_legacy_v3_route_keeps_original_root_and_requires_no_copy(self):
        from buddha import source_launch_state, source_search

        case = fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(case.doCleanups)
        case.mutation_witness = True
        case.prepare(source_copy=False)
        manifest = json.loads((case.directory / "manifest.json").read_bytes())
        self.assertEqual(manifest["format"], "buddha.source-search-manifest.v3")
        self.assertNotIn("source_copy", manifest)
        before = case.h.files(case.directory), case.authority.summary()
        with case.h.readonly():
            source_launch_state.inspect_prepared_search(
                case.directory,
                case.authority.path,
                seed_screen=case.seed,
                proposal_template=case.template,
                spec=case.spec,
                review=case.engine.fixture.review,
                expected_runtime_sha256=case.engine.candidate.expected_runtime,
                input_bindings={},
                mutation_witness=True,
                source_copy=False,
            )
        self.assertEqual((case.h.files(case.directory), case.authority.summary()), before)
        state = source_search._restore(case.directory, case.authority.path)
        proposal = self.child_fixture(case, "legacy")
        location = case.directory / "iterations/0"
        projected = source_search._child_screen(state, proposal, location)
        self.assert_projection(case, projected, proposal, Path(proposal["child"]["directory"]))
        before = case.h.files(case.directory), case.authority.summary()
        source_search._materialize_child_source(
            state, proposal, location, owner_directory=location / "screen"
        )
        self.assertEqual((case.h.files(case.directory), case.authority.summary()), before)
        self.assertFalse((location / "agent").exists())
        self.assertEqual((case.engine.workers, case.engine.physical_sends), (0, 0))

    def test_copy_selector_requires_literal_boolean_and_cannot_enable_task_only_work(self):
        case = fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(case.doCleanups)
        before = case.authority.summary()
        for value in (0, 1, "true", [], {}):
            with self.subTest(source_copy=value), self.assertRaises(case.Error):
                case.prepare(source_copy=value)
            self.assertFalse(case.directory.exists())
            self.assertEqual(case.authority.summary(), before)
        with self.assertRaises(case.Error):
            case.prepare(source_copy=True, mutation_witness=False)
        self.assertFalse(case.directory.exists())
        self.assertEqual(case.authority.summary(), before)
        self.assertEqual((case.engine.workers, case.engine.physical_sends), (0, 0))


if __name__ == "__main__":
    unittest.main()
