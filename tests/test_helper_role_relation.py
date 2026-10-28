"""A helper relation checks metadata; it does not authorize or execute anything."""

import copy
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

import test_releases as release_fixtures

from buddha import candidate_generation, gateway, launch_common, source_screen
from buddha.answers import TaskSet
from buddha.releases import ReleaseError, _json, _load, inventory


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class HelperRoleRelationTests(unittest.TestCase):
    def setUp(self):
        # This existing fixture only writes/inventories literal public test data.
        # No selected source is parsed, imported or executed; no SQL is created.
        self.fixture = f = release_fixtures.ReleaseSelectionTests("runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.root = f.root
        dataset = b"".join(
            _json({"id": name, "prompt": "literal " + name}) + b"\n"
            for name in ("development", "validation", "final")
        )
        (f.roots["official"] / "data/tasks.jsonl").write_bytes(dataset)
        f.record["source"] = inventory(f.roots["official"])
        for name in ("identity.txt", "policy.json"):
            (f.roots["agent"] / name).unlink()
        f.write("agent", "candidate.py", "OPAQUE SELECTED AGENT; NOT PYTHON")
        f.write("environment", "runtime.json", "opaque selected runtime")
        release = f.release()
        self.selection = f.prepare(release)
        tasks = TaskSet.from_dataset(release, dataset)
        roots = {name: str(path) for name, path in f.roots.items()}
        runtime = {
            "path": str(f.roots["environment"] / "runtime.json"),
            "sha256": self.selection.to_record()["components"]["environment"]["runtime.json"],
        }
        self.record = {
            "format": "buddha.source-screen.v2",
            "source": tasks.to_record(),
            "split": {
                "release_sha256": tasks.release_sha256,
                "dataset_sha256": tasks.dataset_sha256,
                "partitions": {name: [name] for name in ("development", "validation", "final")},
                "families": [{"id": task.id, "family": task.id} for task in tasks.tasks],
            },
            "selected_ids": ["development"],
            "generation": {
                "selection": self.selection.to_record(),
                "roots": roots,
                "config": {
                    "provider": "openai",
                    "model": "synthetic-model",
                    "max_output_tokens": 64,
                    "instructions": "fixed instructions",
                    "sampling": "regenerate",
                },
                "entrypoint": "candidate.py",
                "executor": {"mounts": [["/agent", roots["agent"]], ["/runner", roots["runner"]]]},
                "profile": {"capability": "ordered-text.v1", "profile_id": "primary"},
                "runtime": runtime,
                "max_callbacks": 1,
                "budget_microusd": 100,
                "max_calls": 2,
            },
            "native": {
                "selection": self.selection.to_record(),
                "roots": roots,
                "profiles": {"openai": {"synthetic-model": "primary"}},
                "executor": {"image_id": "sha256:" + "a" * 64},
                "budget_microusd": 100,
                "max_calls": 2,
            },
            "stages": [
                {
                    "inputs": ["generations.jsonl"],
                    "outputs": [
                        {"path": "v1/results.jsonl", "id_field": "id"},
                        {"path": "v1/summary.json", "id_field": None},
                    ],
                    "allow_model": False,
                }
            ],
            "projection": None,
            "lineage": None,
        }
        self.screen = source_screen.SourceScreen.from_bytes(_json(self.record))
        self.core = {
            "buddha/" + ("__init__.py" if name == "buddha" else name.rsplit(".", 1)[1] + ".py")
            for name in gateway.CORE
        }
        self.before_sources, self.after_sources = {}, {}
        before_root, after_root = self.root / "old/buddha", self.root / "new/buddha"
        before_root.mkdir(parents=True)
        after_root.mkdir(parents=True)
        paths = source_screen._sources()
        self.changed = next(
            "buddha/" + path.name for path in paths if "buddha/" + path.name not in self.core
        )
        for path in paths:
            role = "buddha/" + path.name
            before = path.read_bytes() if role in self.core else ("opaque " + role).encode()
            after = ("reviewed replacement " + role).encode() if role == self.changed else before
            for root, raw, sources in (
                (before_root, before, self.before_sources),
                (after_root, after, self.after_sources),
            ):
                target = root / path.name
                target.write_bytes(raw)
                sources[role] = {"path": str(target), "sha256": sha(raw)}
        self.overlay = self.root / "approved-relation.json"
        self.before_roles = copy.deepcopy(self.before_sources)
        self.after_roles = copy.deepcopy(self.after_sources)
        # The 32 actual outer helper roles are deliberately independent of the
        # production frozen profile. The existing screen supplies its other 33.
        extra = """agent_run agent_worker baseline baseline_results baseline_state
        candidate_improvement candidate_improvement_results comparison_observation credentials
        final_evaluation improvement_rule improver_analysis improver_assessment improver_handoff
        improver_launch improver_launch_state improver_study launch_common plain_comparison
        policy_panel policy_results reference source_capacity source_feedback source_review
        source_review_handoff source_review_results source_search unified_funding unified_launch
        validation_analysis validation_study""".split()
        outer = (
            "agents/frozen_seed.py",
            "docs/conformance/imp01-run.py",
            "docs/conformance/unified-run.py",
        )
        for role in [*("buddha/" + name + ".py" for name in extra), *outer]:
            for root, refs, raw in (
                (before_root.parent, self.before_roles, ("old " + role).encode()),
                (
                    after_root.parent,
                    self.after_roles,
                    ("old " + role).encode() if role == outer[0] else ("new " + role).encode(),
                ),
            ):
                target = root / role
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                refs[role] = {"path": str(target), "sha256": sha(raw)}
        self.assertEqual(len(self.before_roles), 68)
        self.manifest = self.root / "original-handoff.json"
        assessment = self.root / "original-assessment.json"
        assessment.write_bytes(b"{}")
        self.fixed = {
            f.roots["official"] / "data/tasks.jsonl": sha(dataset),
            f.roots["official"] / "src/evaluate.py": release.to_record()["source"][
                "src/evaluate.py"
            ],
            f.roots["host"] / "capabilities/text.json": self.selection.to_record()["components"][
                "host"
            ]["capabilities/text.json"],
            Path(runtime["path"]): runtime["sha256"],
            assessment: sha(b"{}"),
            self.manifest: "0" * 64,
        }
        self.fixed.update(
            {
                Path(self.before_roles[role]["path"]): self.before_roles[role]["sha256"]
                for role in outer
            }
        )
        while len(self.fixed) - 1 < 119:  # runtime is excluded from comparison external.
            self.fixed[self.root / "fixed" / (str(len(self.fixed)) + ".bin")] = "e" * 64
        recorded = {ref["path"]: ref["sha256"] for ref in self.before_roles.values()}
        for path, pin in self.fixed.items():
            if len(recorded) == 97:
                break
            if path != self.manifest:
                recorded.setdefault(str(path), pin)
        self.original_manifest = _json(
            {
                "format": "buddha.improver-handoff.v1",
                "assessment": {"path": str(assessment), "sha256": self.fixed[assessment]},
                "expected_runtime_sha256": runtime["sha256"],
                "directory": str(self.root / "original-trial"),
                "source_sha256": recorded,
            }
        )
        self.manifest.write_bytes(self.original_manifest)
        self.fixed[self.manifest] = sha(self.original_manifest)

    def context(self, sources, controls, screen=None):
        screen = self.screen if screen is None else screen
        record = screen.to_record()
        excluded = {Path(record["generation"]["runtime"]["path"])}
        if record["lineage"] is not None:
            excluded.add(Path(record["lineage"]["path"]))
        source_paths = {Path(row["path"]) for row in sources.values()}
        return {
            "format": source_screen._version(screen, "source-screen-context"),
            "screen_sha256": screen.fingerprint(),
            "expected_runtime_sha256": record["generation"]["runtime"]["sha256"],
            "controls": {str(path): digest for path, digest in controls.items()},
            "comparison_controls": {
                "sources": copy.deepcopy(sources),
                "external": {
                    str(path): digest
                    for path, digest in controls.items()
                    if path not in source_paths | excluded
                },
            },
        }

    def bundle(self, *, keep=()):
        before = {
            Path(row["path"]): row["sha256"] for row in self.before_roles.values()
        } | self.fixed
        after = {
            path: digest for path, digest in before.items() if path in self.fixed or path in keep
        }
        after.update({Path(row["path"]): row["sha256"] for row in self.after_roles.values()})
        result = {
            "original_source_manifest": self.original_manifest,
            "screen": self.screen,
            "before_context": self.context(self.before_sources, before),
            "before_controls": before,
            "after_context": self.context(self.after_sources, after),
            "after_controls": after,
        }
        return self.rebind(result)

    def rebind(self, bundle, relation=None):
        before = copy.deepcopy(self.before_roles)
        before.update(bundle["before_context"]["comparison_controls"]["sources"])
        after = copy.deepcopy(self.after_roles)
        screen_after = bundle["after_context"]["comparison_controls"]["sources"]
        new_root = Path(screen_after["buddha/source_screen.py"]["path"]).parent.parent
        for role, ref in after.items():
            if role not in screen_after:
                old = Path(ref["path"])
                ref["path"] = str(new_root / role)
                if old != Path(ref["path"]):
                    bundle["after_controls"].pop(old, None)
                    bundle["after_controls"][Path(ref["path"])] = ref["sha256"]
        after.update(screen_after)
        raw = _json(
            {
                "format": "buddha.helper-role-relation.v1",
                "source_manifest": {
                    "path": str(self.manifest),
                    "sha256": sha(bundle["original_source_manifest"]),
                },
                "roles": {role: {"before": before[role], "after": after[role]} for role in before},
            }
            if relation is None
            else relation
        )
        bundle["raw"] = raw
        bundle["expected_overlay"] = {"path": str(self.overlay), "sha256": sha(raw)}
        bundle["after_controls"][self.overlay] = sha(raw)
        bundle["after_context"] = self.context(
            screen_after, bundle["after_controls"], bundle["screen"]
        )
        return bundle

    def call(self, bundle=None):
        return launch_common._helper_role_relation(**(self.bundle() if bundle is None else bundle))

    def replace_manifest(self, bundle, record):
        bundle["original_source_manifest"] = _json(record)
        digest = sha(bundle["original_source_manifest"])
        bundle["before_controls"][self.manifest] = digest
        bundle["after_controls"][self.manifest] = digest
        bundle["before_context"] = self.context(
            self.before_sources, bundle["before_controls"], bundle["screen"]
        )
        return self.rebind(bundle)

    def test_actual_contexts_project_one_new_prefix_without_io_or_mutation(self):
        bundle = self.bundle()
        original = copy.deepcopy(bundle)
        before = source_screen._comparison_controls(
            bundle["before_context"], bundle["before_controls"], self.screen
        )
        after = source_screen._comparison_controls(
            bundle["after_context"], bundle["after_controls"], self.screen
        )
        self.assertNotEqual(before, after)
        with (
            patch.object(Path, "open", side_effect=AssertionError("relation attempted file I/O")),
            patch("socket.socket", side_effect=AssertionError("network forbidden")),
            patch("subprocess.Popen", side_effect=AssertionError("process forbidden")),
            patch("sqlite3.connect", side_effect=AssertionError("SQL forbidden")),
            patch("ast.parse", side_effect=AssertionError("source parsing forbidden")),
        ):
            result = self.call(bundle)
        self.assertEqual(result, bundle["after_controls"])
        self.assertEqual(bundle, original)
        result.clear()
        self.assertTrue(bundle["after_controls"])

    def test_full_anchored_185_to_189_shape_preserves_119_original_external_inputs(self):
        bundle = self.bundle()
        self.assertEqual(len(bundle["before_controls"]), 185)
        self.assertEqual(len(bundle["after_controls"]), 189)
        self.assertEqual(len(bundle["before_context"]["comparison_controls"]["sources"]), 33)
        self.assertEqual(len(bundle["before_context"]["comparison_controls"]["external"]), 151)
        self.assertEqual(len(bundle["after_context"]["comparison_controls"]["external"]), 155)
        self.assertEqual(len(_load(bundle["raw"])["roles"]), 68)
        self.assertEqual(len(_load(bundle["original_source_manifest"])["source_sha256"]), 97)
        result = self.call(bundle)
        for path, pin in self.fixed.items():
            self.assertEqual(result[path], pin)

    def test_an_old_small_generation_prefix_is_not_hidden_by_full_profile_coverage(self):
        names = {
            path.name for path in candidate_generation._sources("buddha.candidate-generation.v2")
        }
        self.assertEqual(len(names), 17)
        record = copy.deepcopy(self.record)
        prefix = Path(self.before_roles["buddha/candidate_generation.py"]["path"]).parent
        record["generation"]["roots"]["runner"] = str(prefix)
        record["generation"]["executor"]["mounts"][1][1] = str(prefix)
        record["generation"]["selection"]["components"]["runner"] = {
            name: self.before_roles["buddha/" + name]["sha256"] for name in names
        }
        self.screen = source_screen.SourceScreen.from_bytes(_json(record))
        bundle = self.bundle(keep=[prefix / name for name in names])
        with self.assertRaises(ReleaseError):
            self.call(bundle)

    def test_original_handoff_is_bound_hash_checked_and_has_exact_metadata(self):
        bundle = self.bundle()
        corrupt = b"unverified original source metadata"
        bundle["original_source_manifest"] = corrupt
        loader = launch_common._load

        def load(raw):
            if raw == corrupt:
                self.fail("original metadata was parsed before checksum verification")
            return loader(raw)

        with (
            patch.object(launch_common, "_load", side_effect=load),
            self.assertRaises(ReleaseError),
        ):
            self.call(bundle)
        for kind in ("unbound", "format", "runtime", "missing-role", "wrong-pin", "extra"):
            with self.subTest(kind=kind):
                bundle = self.bundle()
                record = _load(bundle["original_source_manifest"])
                if kind == "unbound":
                    del bundle["before_controls"][self.manifest]
                    bundle["before_context"] = self.context(
                        self.before_sources, bundle["before_controls"]
                    )
                else:
                    if kind == "format":
                        record["format"] = "other"
                    elif kind == "runtime":
                        record["expected_runtime_sha256"] = "a" * 64
                    elif kind == "missing-role":
                        del record["source_sha256"][self.before_roles[self.changed]["path"]]
                    elif kind == "wrong-pin":
                        record["source_sha256"][self.before_roles[self.changed]["path"]] = "a" * 64
                    else:
                        record["extra"] = None
                    self.replace_manifest(bundle, record)
                with self.assertRaises(ReleaseError):
                    self.call(bundle)

    def test_fixed_old_entrypoints_and_actual_new_entrypoints_are_both_bound(self):
        outer = (
            "agents/frozen_seed.py",
            "docs/conformance/imp01-run.py",
            "docs/conformance/unified-run.py",
        )
        for role in outer:
            for kind in ("old-changed", "new-missing"):
                with self.subTest(role=role, kind=kind):
                    bundle = self.bundle()
                    path = Path(
                        (self.before_roles if kind == "old-changed" else self.after_roles)[role][
                            "path"
                        ]
                    )
                    if kind == "old-changed":
                        bundle["after_controls"][path] = "a" * 64
                    else:
                        del bundle["after_controls"][path]
                    self.rebind(bundle)
                    with self.assertRaises(ReleaseError):
                        self.call(bundle)
        bundle = self.bundle()
        relation = _load(bundle["raw"])
        ref = relation["roles"]["agents/frozen_seed.py"]["after"]
        ref["sha256"] = "a" * 64
        bundle["after_controls"][Path(ref["path"])] = ref["sha256"]
        self.rebind(bundle, relation)
        with self.assertRaises(ReleaseError):
            self.call(bundle)

    def test_unknown_python_input_stays_fixed_and_cannot_be_injected_as_a_role(self):
        bundle = self.bundle()
        unknown = self.root / "old/buddha/scientific-input.py"
        pin = sha(b"opaque data; no source parsing")
        bundle["before_controls"][unknown] = pin
        bundle["after_controls"][unknown] = pin
        record = _load(bundle["original_source_manifest"])
        record["source_sha256"][str(unknown)] = pin
        self.replace_manifest(bundle, record)
        self.assertEqual(self.call(bundle)[unknown], pin)
        del bundle["after_controls"][unknown]
        self.rebind(bundle)
        with self.assertRaises(ReleaseError):
            self.call(bundle)
        bundle["after_controls"][unknown] = pin
        relation = _load(bundle["raw"])
        relation["roles"]["buddha/scientific-input.py"] = {
            "before": {"path": str(unknown), "sha256": pin},
            "after": {"path": str(self.root / "new/buddha/scientific-input.py"), "sha256": pin},
        }
        with self.assertRaises(ReleaseError):
            self.call(self.rebind(bundle, relation))

    def test_selected_dual_role_path_is_retained_as_immutable_external_data(self):
        path = Path(self.before_sources[self.changed]["path"])
        record = copy.deepcopy(self.record)
        record["generation"]["roots"]["runner"] = str(path.parent)
        record["generation"]["executor"]["mounts"][1][1] = str(path.parent)
        record["generation"]["selection"]["components"]["runner"] = {
            path.name: self.before_sources[self.changed]["sha256"]
        }
        self.screen = source_screen.SourceScreen.from_bytes(_json(record))
        bundle = self.bundle(keep=[path])
        result = self.call(bundle)
        self.assertEqual(result[path], self.before_sources[self.changed]["sha256"])
        self.assertIn(str(path), bundle["after_context"]["comparison_controls"]["external"])
        del bundle["after_controls"][path]
        self.rebind(bundle)
        with self.assertRaises(ReleaseError):
            self.call(bundle)

    def test_checksum_is_checked_before_parsing_and_record_has_no_self_reference(self):
        bundle = self.bundle()
        bundle["raw"] = b"not JSON"
        with patch.object(launch_common, "_load", side_effect=AssertionError("unverified parse")):
            with self.assertRaises(ReleaseError):
                self.call(bundle)
        for value in (
            {"format": "other", "roles": {}},
            _load(self.bundle()["raw"])
            | {"overlay": {"path": str(self.overlay), "sha256": "a" * 64}},
        ):
            with self.subTest(value=value), self.assertRaises(ReleaseError):
                self.call(self.rebind(self.bundle(), value))

    def test_component_bytes_reference_shape_and_strict_json_are_bounded(self):
        for raw in (
            None,
            bytearray(b"{}"),
            b"{}",
            b'{"format":"buddha.helper-role-relation.v1","roles":{},"roles":{}}',
        ):
            with self.subTest(raw=type(raw)), self.assertRaises(ReleaseError):
                bundle = self.bundle()
                bundle["raw"] = raw
                if type(raw) is bytes:
                    bundle["expected_overlay"]["sha256"] = sha(raw)
                self.call(bundle)
        for reference in (None, {}, self.bundle()["expected_overlay"] | {"extra": None}):
            with self.subTest(reference=reference), self.assertRaises(ReleaseError):
                bundle = self.bundle()
                bundle["expected_overlay"] = reference
                self.call(bundle)
        with (
            patch.object(launch_common, "MAX_JSON_BYTES", 8),
            patch.object(launch_common, "_load", side_effect=AssertionError("oversized parse")),
        ):
            with self.assertRaises(ReleaseError):
                self.call()

    def test_exact_context_identity_format_runtime_and_control_population_are_required(self):
        for side in ("before_context", "after_context"):
            for field, value in (
                ("format", "buddha.source-screen-context.v1"),
                ("screen_sha256", "a" * 64),
                ("expected_runtime_sha256", "a" * 64),
                ("controls", {}),
                ("extra", None),
            ):
                with self.subTest(side=side, field=field):
                    bundle = self.bundle()
                    bundle[side][field] = value
                    with self.assertRaises(ReleaseError):
                        self.call(bundle)

    def test_planned_science_provider_evaluator_and_resource_changes_are_not_grandfathered(self):
        for section, field, value in (
            ("config", "provider", "anthropic"),
            ("config", "model", "changed-model"),
            ("config", "instructions", "changed task policy"),
            ("config", "max_output_tokens", 65),
            ("generation", "max_callbacks", 2),
            ("generation", "budget_microusd", 101),
            ("native", "budget_microusd", 101),
            ("native", "profiles", {"openai": {"different": "primary"}}),
        ):
            with self.subTest(section=section, field=field):
                bundle = self.bundle()
                record = copy.deepcopy(self.record)
                target = record["generation"]["config"] if section == "config" else record[section]
                target[field] = value
                bundle["screen"] = source_screen.SourceScreen.from_bytes(_json(record))
                with self.assertRaises(ReleaseError):
                    self.call(bundle)
        for path in self.fixed:
            with self.subTest(pinned_input=path):
                bundle = self.bundle()
                bundle["after_controls"][path] = "b" * 64
                self.rebind(bundle)
                with self.assertRaises(ReleaseError):
                    self.call(bundle)

    def test_every_core_role_digest_stays_equal_when_the_helper_prefix_moves(self):
        for role in self.core:
            with self.subTest(role=role):
                bundle = self.bundle()
                ref = bundle["after_context"]["comparison_controls"]["sources"][role]
                ref["sha256"] = "c" * 64
                bundle["after_controls"][Path(ref["path"])] = "c" * 64
                self.rebind(bundle)
                with self.assertRaises(ReleaseError):
                    self.call(bundle)

    def test_closed_roles_reject_missing_extra_renamed_and_mismatched_pairs(self):
        for kind in ("missing", "extra", "renamed", "mismatch"):
            with self.subTest(kind=kind):
                bundle = self.bundle()
                relation = _load(bundle["raw"])
                pair = relation["roles"][self.changed]
                if kind == "missing":
                    del relation["roles"][self.changed]
                elif kind == "extra":
                    relation["roles"]["buddha/candidate.py"] = pair
                elif kind == "renamed":
                    pair["after"]["path"] = str(self.root / "new/buddha/arbitrary.py")
                else:
                    pair["before"]["sha256"] = "d" * 64
                with self.assertRaises(ReleaseError):
                    self.call(self.rebind(bundle, relation))

    def test_aliases_in_place_conflicts_and_overlay_collisions_are_rejected(self):
        for kind in (
            "relative",
            "parent",
            "overlay",
            "in-place",
            "case-alias",
            "context-map",
            "external",
            "pair",
        ):
            with self.subTest(kind=kind):
                bundle = self.bundle()
                if kind in {"relative", "parent"}:
                    bundle["expected_overlay"]["path"] = (
                        "relative.json"
                        if kind == "relative"
                        else str(self.root / "x/../relation.json")
                    )
                elif kind == "overlay":
                    ref = bundle["after_context"]["comparison_controls"]["sources"][self.changed]
                    bundle["expected_overlay"]["path"] = ref["path"]
                elif kind in {"context-map", "external"}:
                    context = bundle["after_context"]
                    row = (
                        context["controls"]
                        if kind == "context-map"
                        else context["comparison_controls"]["external"]
                    )
                    key = next(key for key in row if "official" in key)
                    row[key.replace("official", "OFFICIAL")] = row.pop(key)
                elif kind == "pair":
                    relation = _load(bundle["raw"])
                    ref = relation["roles"][self.changed]["before"]
                    ref["path"] = str(self.root / "OLD/buddha" / Path(ref["path"]).name)
                    self.rebind(bundle, relation)
                else:
                    before = bundle["before_context"]["comparison_controls"]["sources"]
                    after = bundle["after_context"]["comparison_controls"]["sources"]
                    for role, ref in after.items():
                        old = Path(ref["path"])
                        ref["path"] = (
                            str(self.root / "OLD/buddha" / Path(ref["path"]).name)
                            if kind == "case-alias"
                            else before[role]["path"]
                        )
                        if kind == "case-alias":
                            ref["sha256"] = before[role]["sha256"]
                        del bundle["after_controls"][old]
                        bundle["after_controls"][Path(ref["path"])] = ref["sha256"]
                    self.rebind(bundle)
                with self.assertRaises(ReleaseError):
                    self.call(bundle)

    def test_selected_root_aliases_are_checked_before_equal_path_keys_coalesce(self):
        record = copy.deepcopy(self.record)
        record["native"]["roots"] = dict(record["native"]["roots"])
        record["native"]["roots"]["environment"] = str(self.fixture.roots["environment"]).replace(
            "environment", "ENVIRONMENT"
        )
        self.screen = source_screen.SourceScreen.from_bytes(_json(record))
        with self.assertRaises(ReleaseError):
            self.call()

    def test_retaining_a_second_complete_selected_prefix_fails_closed(self):
        record = copy.deepcopy(self.record)
        prefix = Path(self.before_sources[self.changed]["path"]).parent
        record["generation"]["roots"]["runner"] = str(prefix)
        record["generation"]["executor"]["mounts"][1][1] = str(prefix)
        record["generation"]["selection"]["components"]["runner"] = {
            Path(ref["path"]).name: ref["sha256"] for ref in self.before_sources.values()
        }
        self.screen = source_screen.SourceScreen.from_bytes(_json(record))
        bundle = self.bundle(keep=[Path(ref["path"]) for ref in self.before_sources.values()])
        source_screen._comparison_controls(
            bundle["after_context"], bundle["after_controls"], self.screen
        )
        with self.assertRaises(ReleaseError):
            self.call(bundle)

    def test_the_full_union_keeps_the_existing_1024_path_ceiling(self):
        for amount in (1024, 1025):
            with self.subTest(amount=amount):
                bundle = self.bundle()
                missing = amount - len(bundle["after_controls"])
                for index in range(missing):
                    path = self.root / "additional" / (str(index) + ".bin")
                    bundle["before_controls"][path] = "e" * 64
                    bundle["after_controls"][path] = "e" * 64
                bundle["before_context"] = self.context(
                    self.before_sources, bundle["before_controls"]
                )
                self.rebind(bundle)
                if amount == 1024:
                    self.assertEqual(len(self.call(bundle)), amount)
                else:
                    with self.assertRaises(ReleaseError):
                        self.call(bundle)

    def test_a_relation_does_not_enable_legacy_parent_comparison(self):
        bundle = self.bundle()
        self.call(bundle)
        reports = [
            {
                "candidate_id": digit * 64,
                "comparison_key": self.screen.comparison_key(),
                "controls_sha256": source_screen._comparison_controls(
                    bundle[side + "_context"], bundle[side + "_controls"], self.screen
                ),
                "admission": {"eligible": True},
            }
            for side, digit in (("before", "a"), ("after", "b"))
        ]
        references = [
            {
                "directory": str(self.root / digit),
                "authorization": str(self.root / "unused.sqlite3"),
                "report_sha256": digit * 64,
            }
            for digit in ("a", "b")
        ]
        with patch.object(source_screen, "inspect_source_screen", side_effect=reports):
            with self.assertRaises(source_screen.SourceScreenError):
                source_screen.select_source_parent(
                    references, method="archive", max_active=2, seed=7, iteration=0
                )


if __name__ == "__main__":
    unittest.main()
