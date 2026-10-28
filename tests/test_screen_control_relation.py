"""Two literal control profiles; real measured edges, supplied workers/replies.

The private comparison scope is not a funded continuation or a helper-closure
verifier. These fixtures supply its already checked fingerprint inputs.
"""

import copy
import hashlib
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path
from unittest.mock import patch

import test_source_comparison_feedback as comparison_fixtures
import test_source_screen as screen_fixtures

from buddha import source_feedback as feedback
from buddha import source_screen as screens
from buddha.releases import _json, prepare_selection


class ScreenControlRelationTests(unittest.TestCase):
    def fixture(self):
        case = comparison_fixtures.SourceComparisonFeedbackTests("runTest")
        self.addCleanup(case.doCleanups)
        original = screen_fixtures.SourceScreenTests.prepare

        def prepare(h, screen, directory=None, authority=None, **changes):
            study = h.root / "study"
            if screen.to_record()["lineage"] is None:
                directory = study / "common/0/0/screen"
            else:
                directory = study / "cells/0/0/0/0/screen"
                control = h.root / "continued-host-note.txt"
                control.write_bytes(b"literal additional fixture control")
                changes["input_bindings"] = {
                    control: hashlib.sha256(control.read_bytes()).hexdigest()
                }
            directory.parent.mkdir(parents=True, exist_ok=True)
            return original(h, screen, directory, authority, **changes)

        with patch.object(screen_fixtures.SourceScreenTests, "prepare", new=prepare):
            case.fixture()
        self.case = case
        self.study = case.h.root / "study"
        self.parent_report = case.h.inspect(Path(case.parent_ref["directory"]), case.authority)
        self.current_report = case.h.inspect(Path(case.reference["directory"]), case.authority)
        self.before = self.parent_report["controls_sha256"]
        self.after = self.current_report["controls_sha256"]
        self.assertNotEqual(self.before, self.after)
        self.assertEqual(
            self.parent_report["comparison_key"], self.current_report["comparison_key"]
        )
        anchor = case.h.root / "explicit-continuation.json"
        anchor.write_bytes(b"{}")
        self.anchor = {"path": str(anchor), "sha256": hashlib.sha256(b"{}").hexdigest()}
        self.references = [case.parent_ref, case.reference]

    def scope(self, **changes):
        return screens._screen_control_profiles(
            self.study,
            self.case.authority.path,
            **({"before": self.before, "after": self.after, "continuation": self.anchor} | changes),
        )

    def select(self, references=None):
        return screens.select_source_parent(
            self.references if references is None else references,
            method="archive",
            max_active=2,
            seed=7,
            iteration=1,
        )

    def test_genuine_mixed_selection_feedback_and_exact_rebuild_preserve_actual_fingerprints(self):
        self.fixture()
        case = self.case
        with case.h.readonly(), self.assertRaises(screens.SourceScreenError):
            self.select()
        old_packet = case.h.root / "parent-feedback"
        old_pin = hashlib.sha256((old_packet / "provenance.json").read_bytes()).hexdigest()
        old_bytes = {p.name: p.read_bytes() for p in old_packet.iterdir()}
        destination = case.h.root / "mixed-comparison"
        sends = case.h.engine.physical_sends
        with self.scope():
            selected = self.select()
            self.assertEqual(selected["format"], "buddha.source-parent-selection.v2")
            self.assertNotIn("controls_sha256", selected)
            self.assertEqual(
                selected["control_profiles"],
                [
                    {
                        "reference": reference,
                        "candidate_id": report["candidate_id"],
                        "controls_sha256": report["controls_sha256"],
                    }
                    for reference, report in zip(
                        self.references, (self.parent_report, self.current_report), strict=True
                    )
                ],
            )
            written = feedback.write_source_feedback(
                destination, reference=case.reference, comparison=case.comparison
            )
            bundle = feedback.inspect_source_feedback(
                destination, expected_provenance_sha256=written["provenance"]["sha256"]
            )
            provenance = bundle["provenance"]
            self.assertEqual(provenance["controls_sha256"], self.after)
            self.assertEqual(provenance["comparison"], case.comparison)
            self.assertEqual(
                provenance["policy"]["host_control_relation"], selected["host_control_relation"]
            )
            self.assertEqual(
                self.select([case.parent_ref])["format"], "buddha.source-parent-selection.v1"
            )
            parent = feedback.inspect_source_feedback(
                old_packet, expected_provenance_sha256=old_pin
            )
            self.assertNotIn("host_control_relation", parent["provenance"]["policy"])
            self.assertEqual(old_bytes, {p.name: p.read_bytes() for p in old_packet.iterdir()})
        self.assertEqual(case.h.engine.physical_sends, sends)
        with case.h.readonly(), self.assertRaises(feedback.SourceFeedbackError):
            feedback.inspect_source_feedback(
                destination, expected_provenance_sha256=written["provenance"]["sha256"]
            )

    def test_third_profiles_scope_borrowing_and_copied_threads_cannot_extend_the_relation(self):
        self.fixture()
        rows = list(zip(self.references, (self.before, self.after), strict=True))
        with self.scope():
            marker = screens._screen_control_relation(rows)
            self.assertIsNotNone(marker)
            bad_rows = []
            bad_rows.append(rows + [(self.case.reference, "f" * 64)])
            for field, value in (
                ("authorization", str(self.case.h.root / "other.sqlite3")),
                ("directory", str(self.case.h.root / "other/cells/0/0/0/0/screen")),
                ("directory", str(self.study / "cells/0/0/0/1/proposal")),
                ("directory", str(self.study / "cells/0/0/2/0/screen")),
            ):
                bad_rows.append([rows[0], (rows[1][0] | {field: value}, self.after)])
            for changed in bad_rows:
                with self.subTest(changed=changed), self.assertRaises(screens.SourceScreenError):
                    screens._screen_control_relation(changed)
            with self.assertRaises(screens.SourceScreenError), self.scope():
                pass
            context = copy_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(context.run, screens._screen_control_relation, rows)
                with self.assertRaises(screens.SourceScreenError):
                    future.result()
            changed = copy.deepcopy(marker)
            changed["continuation"]["sha256"] = "a" * 64
            with self.assertRaises(screens.SourceScreenError):
                screens._checked_control_marker(changed)
        with self.assertRaises(screens.SourceScreenError):
            screens._screen_control_relation(rows)

    def test_wrapper_policy_preserves_only_its_actual_dependencies(self):
        self.fixture()
        rows = list(zip(self.references, (self.before, self.after), strict=True))
        with self.scope():
            relation = screens._screen_control_relation(rows)
            plain = {"policy": dict(feedback._FULL_POLICY)}
            marked = feedback._relation_policy(
                feedback._FULL_FAILURE_POLICY, plain, relation=relation
            )
            dependency = {"policy": marked}
            for policy in (
                feedback._FROZEN_FAILURE_POLICY,
                feedback._COMPARISON_POLICY,
                feedback._ROOT_COMPARISON_POLICY,
                feedback._STUDY_ROOT_COMPARISON_POLICY,
            ):
                result = feedback._relation_policy(policy, dependency, plain)
                self.assertEqual(result["host_control_relation"], relation)
                self.assertEqual(result["version"], policy["version"])
                self.assertEqual(feedback._relation_policy(policy, plain), dict(policy))
            raw = _json(dependency)
            self.assertEqual(json.loads(raw)["policy"]["host_control_relation"], relation)
        with self.assertRaises(screens.SourceScreenError):
            feedback._relation_policy(feedback._COMPARISON_POLICY, dependency)

    def test_transitive_proposal_dependency_is_retained_when_direct_profiles_are_uniform(self):
        self.fixture()
        case = self.case
        with self.scope():
            written = feedback.write_source_feedback(
                case.h.root / "mixed-parent-packet",
                reference=case.reference,
                comparison=case.comparison,
            )
            proposal, proposal_directory = case.propose(
                "next-original-proposal",
                case.current_record,
                written,
                {
                    "source": comparison_fixtures.CHILD + "# next literal child\n",
                    "hypothesis": "next",
                },
            )
            record = copy.deepcopy(case.current_record)
            generation = record["generation"]
            roots = {name: Path(path) for name, path in generation["roots"].items()}
            roots["agent"] = Path(proposal["child"]["directory"])
            generation.update(
                selection=prepare_selection(
                    case.h.engine.candidate.release,
                    roots,
                    capabilities=generation["selection"]["capabilities"],
                ).to_record(),
                roots={name: str(path) for name, path in roots.items()},
            )
            generation["executor"]["mounts"] = [
                ["/agent", str(roots["agent"])],
                ["/runner", str(roots["runner"])],
            ]
            record["lineage"] = proposal["child"]["lineage"]
            screen = case.h.screen(record)
            directory = self.study / "cells/0/0/0/1/screen"
            directory.parent.mkdir(parents=True)
            control = case.h.root / "continued-host-note.txt"
            case.h.prepare(
                screen,
                directory,
                case.authority,
                input_bindings={control: hashlib.sha256(control.read_bytes()).hexdigest()},
            )
            report = case.h.run_screen(directory)
            self.assertEqual(report["controls_sha256"], self.after)
            reference = case.h.reference(directory, case.authority)
            bundle = feedback.build_source_feedback(
                case.h.root / "next-comparison-packet",
                reference=reference,
                comparison={
                    "parent": case.reference,
                    "proposal": case.h.reference(proposal_directory, case.authority),
                    "screen": reference,
                },
            )
            self.assertEqual(
                bundle["provenance"]["policy"]["host_control_relation"]["continuation"],
                self.anchor,
            )


if __name__ == "__main__":
    unittest.main()
