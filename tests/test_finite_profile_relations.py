"""Three caller-checked hashes; no descriptor, owner adoption or execution authority."""

import copy
import hashlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path
from unittest.mock import patch

import test_answers as answer_fixtures
import test_screen_control_relation as legacy_fixtures

from buddha import source_feedback as feedback
from buddha import source_screen as screens
from buddha import source_search
from buddha.answers import TaskSet
from buddha.releases import ReleaseError, _json


class FiniteProfileRelationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "study"
        self.authorization = self.directory / "grant.sqlite3"
        self.a, self.b, self.c = (letter * 64 for letter in "abc")
        self.old_anchor = {"path": str(self.directory / "old.json"), "sha256": "d" * 64}
        self.anchor = {"path": str(self.directory / "new.json"), "sha256": "e" * 64}
        self.rows = [
            (
                {
                    "directory": str(self.root / relative),
                    "authorization": str(self.authorization),
                    "report_sha256": "f" * 64,
                },
                digest,
            )
            for relative, digest in zip(
                ("common/0/0/screen", "cells/0/0/0/0/screen", "cells/0/0/1/0/screen"),
                (self.a, self.b, self.c),
                strict=True,
            )
        ]
        with self.legacy_scope():
            self.legacy = screens._screen_control_relation(self.rows[:2])
        self.legacy_raw = _json(self.legacy)
        self.legacy_sha = hashlib.sha256(self.legacy_raw).hexdigest()

    def legacy_scope(self):
        return screens._screen_control_profiles(
            self.root,
            self.authorization,
            before=self.a,
            after=self.b,
            continuation=self.old_anchor,
        )

    def scope(self, **changes):
        return screens._screen_control_profiles_v2(
            self.root,
            self.authorization,
            **(
                {
                    "before": self.a,
                    "after": self.b,
                    "current": self.c,
                    "continuation": self.anchor,
                    "legacy_relation": self.legacy,
                    "legacy_sha256": self.legacy_sha,
                }
                | changes
            ),
        )

    def test_exact_legacy_replay_and_actual_c_controls_have_fresh_markers(self):
        with patch("builtins.open", side_effect=AssertionError("primitive must not read files")):
            with self.scope():
                self.assertEqual(
                    _json(screens._screen_control_relation(self.rows[:2])), self.legacy_raw
                )
                for row in self.rows:
                    self.assertIsNone(screens._screen_control_relation([row]))
                ac = screens._screen_control_relation([self.rows[0], self.rows[2]])
                self.assertEqual(ac["controls_sha256"], [self.a, self.c])
                self.assertNotIn("legacy_relation", ac)
                self.assertEqual(ac["continuation"], self.anchor)
                self.assertEqual(
                    screens._screen_control_relation([self.rows[0], self.rows[0], self.rows[2]]), ac
                )
                bc = screens._screen_control_relation(self.rows[1:])
                self.assertEqual(bc["controls_sha256"], [self.b, self.c])
                self.assertNotIn("legacy_relation", bc)
                abc = screens._screen_control_relation(self.rows)
                self.assertEqual(abc["controls_sha256"], [self.a, self.b, self.c])
                # A compatibility proof for AB, not a claim that an old packet was visited.
                self.assertEqual(_json(abc["legacy_relation"]), self.legacy_raw)
                abc["legacy_relation"]["continuation"]["sha256"] = "0" * 64
                self.assertEqual(
                    _json(screens._screen_control_relation(self.rows)["legacy_relation"]),
                    self.legacy_raw,
                )

    def test_policy_composition_retains_only_actual_dependencies_and_legacy_bytes(self):
        plain = {"policy": dict(feedback._FULL_POLICY)}
        old = {"policy": feedback._FULL_POLICY | {"host_control_relation": self.legacy}}
        original = _json(old)
        with self.scope():
            self.assertEqual(
                feedback._relation_policy(feedback._COMPARISON_POLICY, plain),
                dict(feedback._COMPARISON_POLICY),
            )
            inherited = feedback._relation_policy(feedback._COMPARISON_POLICY, old, plain)
            self.assertEqual(_json(inherited["host_control_relation"]), self.legacy_raw)
            ac = screens._screen_control_relation([self.rows[0], self.rows[2]])
            new = feedback._relation_policy(feedback._COMPARISON_POLICY, plain, relation=ac)
            self.assertEqual(new["host_control_relation"]["controls_sha256"], [self.a, self.c])
            self.assertNotIn("legacy_relation", new["host_control_relation"])
            merged = feedback._relation_policy(feedback._FULL_FAILURE_POLICY, old, {"policy": new})
            marker = merged["host_control_relation"]
            self.assertEqual(marker["controls_sha256"], [self.a, self.b, self.c])
            self.assertEqual(_json(marker["legacy_relation"]), self.legacy_raw)
            self.assertEqual(feedback._relation_policy(merged)["host_control_relation"], marker)
            self.assertEqual(_json(old), original)
        with self.assertRaises(screens.SourceScreenError):
            feedback._relation_policy(feedback._FULL_POLICY, {"policy": new})

    def test_duplicate_hashes_and_changed_legacy_or_external_anchors_refuse_activation(self):
        variants = [{"current": self.a}, {"after": self.a}, {"legacy_sha256": "0" * 64}]
        for field, value in (
            ("format", "buddha.host-control-relation.v2"),
            ("before_controls_sha256", self.c),
            ("extra", True),
            ("continuation", self.old_anchor | {"sha256": "0" * 64}),
        ):
            changed = copy.deepcopy(self.legacy)
            changed[field] = value
            variants.append({"legacy_relation": changed})
        for path in (
            self.root / "inside.json",
            self.directory / "nested/../alias.json",
            self.directory / "old.json",
            self.authorization,
        ):
            variants.append({"continuation": self.anchor | {"path": str(path)}})
        for change in variants:
            with self.subTest(change=change), self.assertRaises(ReleaseError), self.scope(**change):
                pass
            self.assertIsNone(screens._CONTROL_PROFILES_V2.get())
        with self.assertRaises(TypeError):
            self.scope(fourth="0" * 64)

    def test_unknown_profiles_and_borrowed_or_malformed_references_are_rejected(self):
        bad = [[(self.rows[0][0], "0" * 64)], self.rows + [(self.rows[0][0], "0" * 64)]]
        bad.append([self.rows[0], (self.rows[0][0], self.b)])
        for field, value in (
            ("authorization", str(self.directory / "other.sqlite3")),
            ("directory", str(self.directory / "borrowed/common/0/0/screen")),
            ("directory", str(self.root / "cells/0/0/2/0/screen")),
            ("directory", str(self.root / "cells/0/0/0/0/proposal")),
            ("report_sha256", "bad"),
        ):
            bad.append([(self.rows[0][0] | {field: value}, self.a)])
        with self.scope():
            for rows in bad:
                with self.subTest(rows=rows), self.assertRaises(ReleaseError):
                    screens._screen_control_relation(rows)
            for rows in ([], self.rows * 86):
                with self.assertRaises(screens.SourceScreenError):
                    screens._screen_control_relation(rows)

    def test_marker_changes_missing_proofs_and_composition_bounds_are_rejected(self):
        with self.scope():
            marker = screens._screen_control_relation(self.rows)
            variants = []
            for field, value in (
                ("format", "buddha.host-control-relation.v1"),
                ("continuation", self.anchor | {"sha256": "0" * 64}),
                ("controls_sha256", [self.a, self.b, self.c, "0" * 64]),
                ("controls_sha256", [self.a, self.c, self.c]),
                ("controls_sha256", [self.c, self.b, self.a]),
                ("legacy_relation", self.legacy | {"after_controls_sha256": self.c}),
                ("extra", True),
            ):
                variants.append(marker | {field: value})
            missing = copy.deepcopy(marker)
            del missing["legacy_relation"]
            variants.append(missing)
            variants.append(self.legacy | {"continuation": self.anchor})
            for value in variants:
                with self.subTest(value=value), self.assertRaises(ReleaseError):
                    screens._checked_control_marker(value)
            with self.assertRaises(screens.SourceScreenError):
                screens._compose_control_relations([self.legacy] * 257)
        with self.assertRaises(screens.SourceScreenError):
            screens._checked_control_marker(marker)

    def test_scope_nesting_pid_thread_and_exception_cleanup_preserve_v1(self):
        with self.legacy_scope():
            with self.assertRaises(screens.SourceScreenError), self.scope():
                pass
            with self.assertRaises(screens.SourceScreenError):
                screens._screen_control_relation(self.rows)
            # The existing uniform early return remains unchanged outside v2.
            self.assertIsNone(screens._screen_control_relation([({}, "0" * 64)]))
        with self.scope():
            for nested in (self.scope, self.legacy_scope):
                with self.assertRaises(screens.SourceScreenError), nested():
                    pass
            with patch.object(screens.os, "getpid", return_value=-1):
                with self.assertRaises(screens.SourceScreenError):
                    screens._screen_control_relation(self.rows)
            context = copy_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(context.run, screens._screen_control_relation, self.rows)
                with self.assertRaises(screens.SourceScreenError):
                    future.result()
        with self.assertRaisesRegex(RuntimeError, "supplied failure"), self.scope():
            raise RuntimeError("supplied failure")
        self.assertIsNone(screens._CONTROL_PROFILES.get())
        self.assertIsNone(screens._CONTROL_PROFILES_V2.get())
        with self.legacy_scope():
            self.assertEqual(
                _json(screens._screen_control_relation(self.rows[:2])), self.legacy_raw
            )

    def test_direct_provenance_pairs_and_combined_bounds_are_checked(self):
        direct = {
            "reference": self.rows[2][0],
            "controls_sha256": self.c,
            "policy": dict(feedback._FULL_POLICY),
        }
        inherited = {"policy": feedback._FULL_POLICY | {"host_control_relation": self.legacy}}
        with self.scope():
            self.assertNotIn(
                "host_control_relation", feedback._relation_policy(feedback._FULL_POLICY, direct)
            )
            marker = feedback._relation_policy(feedback._FULL_POLICY, direct, inherited)[
                "host_control_relation"
            ]
            self.assertEqual(marker["controls_sha256"], [self.a, self.b, self.c])
            self.assertEqual(_json(marker["legacy_relation"]), self.legacy_raw)
            for field in ("reference", "controls_sha256"):
                partial = copy.deepcopy(direct)
                del partial[field]
                with (
                    self.subTest(missing=field),
                    self.assertRaisesRegex(feedback.SourceFeedbackError, "reference and controls"),
                ):
                    feedback._relation_policy(feedback._FULL_POLICY, partial)
            for changed in (
                direct | {"controls_sha256": "0" * 64},
                direct | {"reference": self.rows[2][0] | {"authorization": "borrowed"}},
            ):
                with self.subTest(changed=changed), self.assertRaises(ReleaseError):
                    feedback._relation_policy(feedback._FULL_POLICY, changed)
            with self.assertRaises(screens.SourceScreenError):
                screens._compose_control_relations([self.legacy], rows=[self.rows[2]] * 256)
            self.assertEqual(
                screens._compose_control_relations([self.legacy] * 255, rows=[self.rows[2]])[
                    "controls_sha256"
                ],
                [self.a, self.b, self.c],
            )

    def test_supplied_uniform_c_root_builder_joins_direct_controls_and_legacy_ancestry(self):
        # Measured-base/ancestry and root declaration are supplied boundaries.
        # The real wrapper runs; a verified three-producer lineage is not claimed.
        self.root.mkdir()
        dataset = b"".join(
            _json({"id": index, "prompt": "Synthetic task " + str(index)}) + b"\n"
            for index in range(3)
        )
        release = answer_fixtures.AnswerArtifactTests("runTest").make_release(dataset)
        source = TaskSet.from_dataset(release, dataset)
        split = {
            "release_sha256": source.release_sha256,
            "dataset_sha256": source.dataset_sha256,
            "partitions": {"development": [0], "validation": [1], "final": [2]},
            "families": [{"id": index, "family": "family-" + str(index)} for index in range(3)],
        }
        destination = self.directory / "supplied-packet"
        note = _json(
            {"kind": "saved_native_measurements", "distinct": 2, "utility": 7, "answers": []}
        ).decode()
        packet = {
            "format": "buddha.candidate-development-feedback.v2",
            "source": {"path": str(destination / "source.json"), "sha256": source.fingerprint()},
            "split": {
                "path": str(destination / "split.json"),
                "sha256": hashlib.sha256(_json(split)).hexdigest(),
            },
            "records": [{"task_id": 0, "note": note}],
        }
        base = {
            "source": source.to_record(),
            "split": split,
            "feedback": packet,
            "provenance": {
                "format": "buddha.source-screen-feedback.v3",
                "reference": self.rows[2][0],
                "controls_sha256": self.c,
                "candidate_id": "1" * 64,
                "policy": dict(feedback._FULL_POLICY),
                "tasks": [{"task_id": 0}],
            },
        }
        comparison = {
            "root": {
                "directory": str(self.root),
                "authorization": str(self.authorization),
                "manifest_sha256": "2" * 64,
            }
        }
        with self.scope():
            outputs = []
            for inherited in (False, True):
                supplied = copy.deepcopy(base)
                if inherited:
                    supplied["provenance"]["policy"]["host_control_relation"] = self.legacy
                with (
                    patch.object(feedback, "_build", return_value=supplied),
                    patch.object(
                        source_search, "_read_comparison_root", return_value={"supplied": True}
                    ),
                ):
                    outputs.append(
                        feedback._build_root_comparison(destination, self.rows[2][0], comparison)
                    )
        self.assertNotIn("host_control_relation", outputs[0]["provenance"]["policy"])
        marker = outputs[1]["provenance"]["policy"]["host_control_relation"]
        self.assertEqual(marker["format"], "buddha.host-control-relation.v2")
        self.assertEqual(marker["controls_sha256"], [self.a, self.b, self.c])
        self.assertEqual(_json(marker["legacy_relation"]), self.legacy_raw)
        for field in ("source", "split", "feedback"):
            self.assertEqual(_json(outputs[0][field]), _json(outputs[1][field]))
        task = source.tasks[0].to_record()
        projections = [
            [{"task": task, "note": row["note"]} for row in result["feedback"]["records"]]
            for result in outputs
        ]
        self.assertEqual(_json(projections[0]), _json(projections[1]))
        self.assertNotIn(b"host_control_relation", _json(projections[1]))
        self.assertEqual(_json(self.legacy), self.legacy_raw)

    def test_genuine_legacy_four_file_packet_replays_without_changing_projection(self):
        case = legacy_fixtures.ScreenControlRelationTests("runTest")
        self.addCleanup(case.doCleanups)
        case.fixture()
        destination = case.case.h.root / "legacy-replay"
        with case.scope():
            written = feedback.write_source_feedback(
                destination, reference=case.case.reference, comparison=case.case.comparison
            )
            old = feedback.inspect_source_feedback(
                destination, expected_provenance_sha256=written["provenance"]["sha256"]
            )
        files = {path.name: path.read_bytes() for path in destination.iterdir()}
        self.assertEqual(
            set(files), {name + ".json" for name in ("source", "split", "feedback", "provenance")}
        )
        marker = old["provenance"]["policy"]["host_control_relation"]
        before_sends = case.case.h.engine.physical_sends
        with (
            case.case.h.readonly(),
            screens._screen_control_profiles_v2(
                case.study,
                case.case.authority.path,
                before=case.before,
                after=case.after,
                current="0" * 64,
                continuation=self.anchor,
                legacy_relation=marker,
                legacy_sha256=hashlib.sha256(_json(marker)).hexdigest(),
            ),
        ):
            rebuilt = feedback.inspect_source_feedback(
                destination, expected_provenance_sha256=written["provenance"]["sha256"]
            )
        self.assertEqual({path.name: path.read_bytes() for path in destination.iterdir()}, files)
        self.assertEqual(rebuilt, old)
        self.assertEqual(case.case.h.engine.physical_sends, before_sends)
        tasks = {task.id: task for task in case.case.h.source.tasks}

        def projection(packet):
            return [
                {"task": tasks[row["task_id"]].to_record(), "note": row["note"]}
                for row in packet["feedback"]["records"]
            ]

        self.assertEqual(_json(projection(old)), _json(projection(rebuilt)))
        self.assertNotIn(b"host_control_relation", _json(projection(rebuilt)))


if __name__ == "__main__":
    unittest.main()
