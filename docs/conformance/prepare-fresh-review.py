"""Prepare unfunded review controls; do not create a trial or contact reviewers."""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

LIBRARY = Path(r"C:\Users\arvik\code\buddha\runs\reviews\fresh-primary-preparation")
HELPER = LIBRARY / "docs/conformance/prepare-fresh-primary.py"
HELPER_SHA = "a362fe4b5e2ed3d2eb44f7cfee09b04d0cc9726ac7b2c14fc542269f7770bbb2"
UTILITIES = Path(
    r"C:\Users\arvik\code\buddha\runs\reviews\fresh-plain-reference-preparation\docs\conformance\prepare-fresh-plain-references.py"
)
UTILITIES_SHA = "8a60b6b35567714ae26f9dfd2992700968844e4b68f50e14a8378e65d4a22708"
PRIMARY = {
    "assessment": "assessment-proposed.json",
    "source": "inputs/source.json",
    "release": "inputs/release.json",
    "study": "inputs/study.json",
    "custody": "inputs/custody.json",
    "population": "numerical-population-proposed.json",
    "analysis": "analysis-plan-proposed.json",
    "rule": "improvement-rule-proposed.json",
    "primary_check": "configuration-check.json",
    "primary_handoff": "handoff-unfunded.json",
    "policy": "observation-policy.json",
}
ARCHIVED = {
    "archived_plan": "review-plan.json",
    "protocol": "protocol.md",
    "materials": "materials.json",
    "native_route": "native-target-review-route-proposed.md",
}
TRACKS = (
    "docs/REVIEW-TRACKS.md",
    "docs/conformance/imp01-review-tracks-decision.json",
    "docs/DESIGN.md",
)


def rebound_plan(original, experiment, taskset, protocol, materials, check):
    check(
        set(original)
        == {
            "format",
            "experiment_id",
            "kind",
            "tasks_sha256",
            "seed",
            "protocol",
            "materials",
            "sets",
        }
        and original["format"] == "buddha.source-review-plan.v1"
        and original["kind"] == "improver"
        and original["seed"] == 7
        and original["tasks_sha256"] == taskset,
        "archived_plan_science_changed",
    )
    result = copy.deepcopy(original)
    result.update(experiment_id=experiment, protocol=protocol, materials=materials)
    return result


def sample_scope(plan, population, check):
    members = {row["task_id"]: row for row in population["tasks"]}
    groups = {}
    for row in plan["sets"]:
        key = (row["role_index"], row["task_id"], row["repetition"])
        roles = groups.setdefault(key, set())
        check(row["role"] not in roles, "review_role_repeated")
        roles.add(row["role"])
    identifiers = {row["task_id"] for row in plan["sets"]}
    check(
        len(plan["sets"]) == 12
        and len(groups) == 4
        and {key[0] for key in groups} == set(range(4))
        and all(key[2] == 0 for key in groups)
        and all(roles == {"starter", "initial", "evolved"} for roles in groups.values())
        and len(identifiers) == 4
        and identifiers <= members.keys()
        and len({members[key]["family_id"] for key in identifiers}) == 4
        and all(members[key]["count"] == 10 for key in identifiers),
        "review_sample_changed",
    )
    return {
        "whole_sets": 12,
        "full_answer_positions": 120,
        "tasks": 4,
        "families": 4,
        "conditions": 4,
    }


def extended_custody(original, leaves, check):
    old_paths = {row["path"] for row in original["evidence"]}
    check(
        len(original["evidence"]) == 60
        and len(leaves) == 8
        and len({row["path"] for row in leaves}) == 8
        and not old_paths.intersection(row["path"] for row in leaves),
        "review_evidence_changed",
    )
    result = copy.deepcopy(original)
    result["evidence"] += copy.deepcopy(leaves)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    h, util, pins, destination, admitted = None, None, {}, None, False
    public, created = {Path(__file__).absolute(): "prepare_fresh_review"}, {}
    stage, builder_ref, manifest_ref = "admission", None, None
    try:
        for name, item, pin in (
            ("reviewed_primary_helpers", HELPER, HELPER_SHA),
            ("reviewed_plain_utilities", UTILITIES, UTILITIES_SHA),
        ):
            if hashlib.sha256(item.read_bytes()).hexdigest() != pin:
                raise ValueError("preparation_helper_changed")
            spec = importlib.util.spec_from_file_location(name, item)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # Pinned definitions only, never historical mains.
            if item == HELPER:
                h = module
            else:
                util = module
        record = h.load(h.read_pinned(args.inputs.absolute(), args.sha256))
        h.need(
            set(record)
            == {
                "format",
                "driver_sha256",
                "source_root",
                "source_sha256",
                "destination",
                "files",
                "inputs",
                "hash_only",
                "primary_result",
                "review_receipt",
                "track_controls",
            }
            and record["format"] == "buddha.fresh-review-inputs.v1"
            and h.path(record["source_root"]) == LIBRARY,
            "manifest_fields_or_library",
        )
        destination = h.path(record["destination"])
        h.need(
            destination.parent == LIBRARY.parents[1]
            and not destination.exists()
            and not destination.is_symlink(),
            "fresh_destination_required",
        )
        h.need(set(record["inputs"]) == PRIMARY.keys() | ARCHIVED.keys(), "input_roles")
        for field in ("source_sha256", "files"):
            h.need(type(record[field]) is dict and 1 <= len(record[field]) <= 1024, "input_count")
            for name, pin in record[field].items():
                item = h.static_path(h.path(name))
                h.need(
                    item not in pins and not item.is_relative_to(destination),
                    "input_alias_or_output",
                )
                if field == "source_sha256":
                    h.need(
                        item.is_relative_to(LIBRARY)
                        and item.suffix == ".py"
                        and pin not in h.AGENTS.values(),
                        "public_source_scope",
                    )
                    public[item] = ".".join(item.relative_to(LIBRARY).with_suffix("").parts)
                pins[item] = h.digest(pin)
        hash_only = {h.path(name) for name in record["hash_only"]}
        opaque = {item for item, pin in pins.items() if pin in h.AGENTS.values()}
        h.need(
            type(record["hash_only"]) is list
            and len(hash_only) == len(record["hash_only"]) == 60
            and hash_only <= pins.keys(),
            "hash_only_scope",
        )
        for name in record["inputs"].values():
            item = h.path(name)
            h.need(item in pins and item not in hash_only | opaque, "metadata_role_scope")
        h.need(len(set(record["inputs"].values())) == len(record["inputs"]), "input_role_alias")
        refs = [record["primary_result"], record["review_receipt"], *record["track_controls"]]
        for ref in refs:
            h.need(
                type(ref) is dict
                and set(ref) == {"path", "sha256"}
                and pins.get(h.path(ref["path"])) == h.digest(ref["sha256"]),
                "unbound_reference",
            )
        h.need(
            {h.path(ref["path"]) for ref in record["track_controls"]}
            == {Path(__file__).absolute().parents[2] / name for name in TRACKS}
            and len(record["track_controls"]) == 3,
            "track_control_scope",
        )
        builder_ref = {
            "path": str(Path(__file__).absolute()),
            "sha256": h.digest(record["driver_sha256"]),
        }
        manifest_ref = {"path": str(args.inputs.absolute()), "sha256": h.digest(args.sha256)}
        for item, pin in (
            (HELPER, HELPER_SHA),
            (UTILITIES.absolute(), UTILITIES_SHA),
            (args.inputs.absolute(), manifest_ref["sha256"]),
            (Path(__file__).absolute(), builder_ref["sha256"]),
        ):
            h.need(pins.get(item, pin) == pin, "control_pin_conflict")
            pins[item] = pin
        for item, pin in pins.items():
            h.read_pinned(item, pin)
        admitted = True
        sys.path.insert(0, str(LIBRARY))
        sys.dont_write_bytecode = True
        from buddha import (
            improver_analysis,
            improver_assessment,
            improver_handoff,
            native_pipeline,
            policy_panel,
            source_review,
            source_review_handoff,
            source_review_results,
            validation_study,
        )
        from buddha.answers import TaskSet
        from buddha.doctor import _observation_policy
        from buddha.improvement_rule import ImprovementRule
        from buddha.releases import Selection, _json, _load

        modules = (
            improver_analysis,
            improver_assessment,
            improver_handoff,
            native_pipeline,
            policy_panel,
            source_review,
            source_review_handoff,
            source_review_results,
            validation_study,
        )
        for module in modules:
            h.need(Path(module.__file__).absolute() in pins, "wrong_public_namespace")
        helpers = [
            Path(module.__file__).absolute()
            for module in (
                source_review,
                policy_panel,
                source_review_handoff,
                source_review_results,
            )
        ]
        h.need(set(improver_handoff._sources()) <= pins.keys(), "required_helper_unbound")

        def read(item):
            h.need(
                item in pins and item not in hash_only | opaque, "unknown_or_opaque_metadata_read"
            )
            return h.read_pinned(item, pins[item])

        def write(name, raw):
            item = destination / name
            h.need(item.is_relative_to(destination), "output_escape")
            item.parent.mkdir(parents=True, exist_ok=True)
            with item.open("xb") as stream:
                stream.write(raw)
            created[item] = h.sha(raw)
            return {"path": str(item), "sha256": created[item]}

        def saved(name, value):
            return write(name, _json(value))

        library = Path(sys.base_prefix).resolve()

        def audit(event, values):
            if event.startswith(("socket.", "subprocess.", "sqlite3.connect")) or event in {
                "os.system",
                "os.exec",
                "os.posix_spawn",
                "os.spawn",
                "os.remove",
                "os.rename",
                "os.rmdir",
                "os.link",
                "os.symlink",
                "os.chmod",
                "os.utime",
                "os.truncate",
            }:
                raise h.PreparationError("external_or_mutation_refused")
            if event in {"compile", "exec"}:
                name = values[1] if event == "compile" else getattr(values[0], "co_filename", "")
                if (type(name) is str and Path(name) in opaque) or (
                    event == "compile"
                    and type(values[0]) is bytes
                    and h.sha(values[0]) in h.AGENTS.values()
                ):
                    raise h.PreparationError("selected_source_execution_refused")
            if event == "open" and not isinstance(values[0], int):
                item = Path(values[0]).absolute()
                writing = bool(
                    values[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                )
                if writing:
                    h.need(item.is_relative_to(destination), "write_outside_bundle")
                    h.static_path(item)
                else:
                    h.need(
                        item in pins or item in created or item.is_relative_to(library),
                        "unknown_read",
                    )
            if event == "os.mkdir":
                item = Path(values[0]).absolute()
                h.need(item.is_relative_to(destination), "mkdir_outside_bundle")
                h.static_path(item)

        # Process-local accidental-operation guards, not a hostile-code sandbox.
        sys.addaudithook(audit)
        with ExitStack() as stack:
            for target in (
                "ast.parse",
                "getpass.getpass",
                "buddha.authorization.Authorization.__init__",
                "buddha.authorization.Authorization.create",
                "buddha.gateway.Gateway.__init__",
                "buddha.executor.run_container",
                "buddha.gateway.RawHTTPTransport.prepare",
                "buddha.credentials.key_environment",
                "buddha.gateway.credential_fingerprints",
                "buddha.improver_study.prepare_improver_study",
                "buddha.improver_assessment.prepare_improver_assessment_trial",
                "buddha.source_review.materialize_source_review",
                "buddha.source_review_handoff.export_source_review",
                "buddha.source_review_handoff.collect_source_reviews",
            ):
                stack.enter_context(
                    patch(target, side_effect=h.PreparationError("forbidden_preparation_action"))
                )
            checked_ref, checked_read = h.reference_readers(
                validation_study._ref, native_pipeline._read, hash_only, pins, opaque
            )
            stack.enter_context(patch.object(validation_study, "_ref", checked_ref))
            stack.enter_context(patch.object(native_pipeline, "_read", checked_read))
            raw = {name: read(h.path(value)) for name, value in record["inputs"].items()}
            data = {
                name: _load(value)
                for name, value in raw.items()
                if name not in {"source", "protocol", "native_route"}
            }
            parent, receipt = (
                _load(read(h.path(record[name]["path"])))
                for name in ("primary_result", "review_receipt")
            )
            h.need(
                parent["status"] == "complete_unfunded_configuration_only"
                and parent["source_and_input_pins_preserved"] is True,
                "primary_not_complete",
            )
            for role, leaf in PRIMARY.items():
                h.need(
                    util.inventory_pin(parent["files"], leaf, h.need) == h.sha(raw[role]),
                    "primary_leaf_changed",
                )
            for role, leaf in ARCHIVED.items():
                h.need(
                    util.inventory_pin(receipt["files"], leaf, h.need)["sha256"]
                    == h.sha(raw[role]),
                    "archived_review_leaf_changed",
                )
            primary, handoff = data["assessment"], data["primary_handoff"]
            inherited_hashes = {
                h.path(name): h.digest(pin)
                for name, pin in handoff["source_sha256"].items()
                if not h.path(name).is_relative_to(LIBRARY) and name != record["inputs"]["policy"]
            }
            h.need(
                len(inherited_hashes) == 10
                and all(pins.get(item) == pin for item, pin in inherited_hashes.items())
                and not set(inherited_hashes).intersection(
                    h.path(name) for name in record["inputs"].values()
                ),
                "inherited_hash_only_scope",
            )
            # Keep the captured set object: these refs never receive the custody-only exception.
            opaque.update(inherited_hashes)
            h.need(
                handoff["assessment"]
                == {"path": record["inputs"]["assessment"], "sha256": h.sha(raw["assessment"])}
                and data["primary_check"]["assessment_sha256"] == h.sha(raw["assessment"])
                and data["primary_check"]["funding"]["status"] == "unallocated",
                "primary_reference_changed",
            )
            h.need(
                data["policy"] == h.POLICY
                and handoff["source_sha256"].get(record["inputs"]["policy"])
                == h.sha(raw["policy"]),
                "observation_policy_changed",
            )
            stack.enter_context(_observation_policy(data["policy"]))
            tasks = TaskSet.from_bytes(raw["source"])
            h.need(
                tasks.fingerprint() == data["population"]["taskset_sha256"]
                and data["population"]["custody_sha256"] == h.sha(raw["custody"])
                and len(data["population"]["tasks"]) == 26
                and len({row["family_id"] for row in data["population"]["tasks"]}) == 25,
                "primary_population_changed",
            )
            h.need(
                {h.path(ref["path"]) for ref in data["custody"]["evidence"]} == hash_only
                and all(
                    pins[h.path(ref["path"])] == ref["sha256"]
                    for ref in data["custody"]["evidence"]
                ),
                "custody_hash_only_changed",
            )
            stage = "materialization"
            destination.mkdir()
            protocol_ref = write("protocol.md", raw["protocol"])
            materials_ref = write("materials.json", raw["materials"])
            route_ref = write("native-target-review-route-proposed.md", raw["native_route"])
            plan = rebound_plan(
                data["archived_plan"],
                primary["experiment_id"],
                tasks.fingerprint(),
                protocol_ref,
                materials_ref,
                h.need,
            )
            plan_ref = saved("review-plan.json", plan)
            leaves = [
                plan_ref,
                protocol_ref,
                materials_ref,
                route_ref,
                *({"path": str(item), "sha256": pins[item]} for item in helpers),
            ]
            custody = extended_custody(data["custody"], leaves, h.need)
            custody_ref = saved("custody-review-bound.json", custody)
            population = copy.deepcopy(data["population"])
            population["custody_sha256"] = custody_ref["sha256"]
            population_ref = saved("numerical-population-review-bound.json", population)
            analysis_record = copy.deepcopy(data["analysis"])
            analysis_record.update(
                population_sha256=population_ref["sha256"],
                analyzer_sources=improver_analysis._source_hashes(),
            )
            analysis = improver_analysis.ImproverAnalysisPlan.from_bytes(_json(analysis_record))
            analysis_ref = write("analysis-plan-review-bound.json", analysis.to_bytes())
            stage = "current-synthetic-numerical-check"
            identities = [
                Selection.from_bytes(_json(row["screen"]["generation"]["selection"])).agent_sha256
                for row in data["study"]["starts"]
            ]
            rule = ImprovementRule.from_bytes(raw["rule"])
            slots, rows = h.supplied_numerical(population, identities)
            numeric = improver_analysis.analyze_improver_panel(
                analysis, population=population, slots=slots, rows=rows, rule=rule
            )
            h.need(
                numeric["coverage"]["complete"] and len(slots) == 8 and len(rows) == 312,
                "synthetic_coverage_changed",
            )
            for contrast, utility, distinct in (
                ("initial_gain", 3, 2),
                ("evolved_gain", 5, 3),
                ("improver_effect", 2, 1),
            ):
                for axis, value in (("utility", utility), ("distinct", distinct)):
                    h.need(
                        numeric["contrasts"][contrast][axis]["point"]
                        == {"numerator": value, "denominator": 1},
                        "synthetic_arithmetic_changed",
                    )
            numerical_ref = saved(
                "current-synthetic-numerical-check.json",
                {
                    "synthetic": True,
                    "not_actual_trial_data_or_adoption": True,
                    "plan": analysis_ref,
                    "population": population_ref,
                    "rule": {"path": record["inputs"]["rule"], "sha256": h.sha(raw["rule"])},
                    "supplied_slots": slots,
                    "supplied_rows": rows,
                    "result": numeric,
                    "old_numerical_or_empirical_results_parsed_or_used_as_input": False,
                    "inherited_static_controls": (
                        "Exact named byte verification only; no old-result parsing."
                    ),
                },
            )
            definition = copy.deepcopy(primary)
            definition.update(
                custody=custody_ref,
                analysis_plan=analysis_ref,
                consumer_sources=improver_assessment._source_hashes(),
            )
            definition_ref = saved("assessment-review-bound.json", definition)
            stage = "review-materials-and-selectors"
            literal_rule, rubric = policy_panel._materials(
                raw["materials"],
                materials_ref["sha256"],
                raw["protocol"],
                protocol_ref["sha256"],
                data["release"],
            )
            h.need(
                literal_rule["sha256"]
                == "5df0b3a31c86ea37e15b17348a34ad064790b670be345dd93fcd0a4d18385eca"
                and h.sha(rubric.encode())
                == "733be657c9c72bdb6f66a04028f423b3f4a30e9ff8aaf8f9321296e6502f89bd",
                "literal_review_criteria_changed",
            )
            state = improver_assessment._definition(
                _json(definition), handoff["expected_runtime_sha256"], active=False
            )
            h.need(
                _json(improver_assessment._population(state)) == _json(population),
                "derived_population_changed",
            )
            selected = source_review._selectors(
                plan,
                state,
                {
                    "selected_ids": definition["final_ids"],
                    "repetitions": definition["sealed_repetitions"],
                },
                "improver",
            )
            h.need(selected == data["archived_plan"]["sets"], "review_coordinates_changed")
            sample = sample_scope(plan, population, h.need)
            h.need(
                all(state["controls"].get(h.path(ref["path"])) == ref["sha256"] for ref in leaves),
                "review_controls_unbound",
            )
            intent_ref = saved(
                "intent.json",
                {
                    "format": "buddha.fresh-review-preparation.v1",
                    "status": "unfunded_unadopted_not_launchable",
                    "builder": builder_ref,
                    "input_manifest": manifest_ref,
                    "primary_result": record["primary_result"],
                    "archived_review_receipt": record["review_receipt"],
                    "review_plan": plan_ref,
                    "sample": sample,
                    "custody": (
                        "Retained non-evidence declaration unchanged; "
                        "no new exposure or independence attestation."
                    ),
                    "tracks": (
                        "AI-only proceeds without human availability; actual human ratings "
                        "remain separate and missing until supplied."
                    ),
                    "track_controls": record["track_controls"],
                    "native_reviewer_allocation_created": False,
                    "funding_transferred_or_created": False,
                },
            )
            controls = dict(handoff["source_sha256"])
            for ref in [
                *leaves,
                *record["track_controls"],
                numerical_ref,
                intent_ref,
                builder_ref,
                manifest_ref,
                record["primary_result"],
                record["review_receipt"],
                {"path": str(HELPER), "sha256": HELPER_SHA},
                {"path": str(UTILITIES.absolute()), "sha256": UTILITIES_SHA},
            ]:
                h.need(
                    controls.get(ref["path"], ref["sha256"]) == ref["sha256"],
                    "control_replacement_refused",
                )
                controls[ref["path"]] = ref["sha256"]
            future = destination / "NOT-CREATED-trial-runtime"
            new_handoff = handoff | {
                "assessment": definition_ref,
                "directory": str(future),
                "source_sha256": controls,
            }
            handoff_ref = saved("handoff-unfunded.json", new_handoff)
            stage = "unfunded-handoff"
            checked = improver_handoff.check_improver_handoff(
                h.path(handoff_ref["path"]), expected_sha256=handoff_ref["sha256"]
            )
            h.need(
                checked["planned"] == data["primary_check"]["planned"]
                and checked["requested_phase_limits"]
                == data["primary_check"]["requested_phase_limits"]
                and checked["funding"]["status"] == "unallocated"
                and not future.exists(),
                "scientific_limits_or_funding_changed",
            )
            h.need(
                all(
                    checked["reviewed_bindings"].get(name) == pin for name, pin in controls.items()
                ),
                "handoff_controls_missing",
            )
            saved("configuration-check.json", checked)
            stage, status, failure = "complete", "complete_unfunded_review_configuration", None
    except BaseException as error:
        status = "partial" if created else "stopped"
        failure = {
            "stage": stage,
            "class": type(error).__name__,
            "public_frames": util.public_frames(error, public) if util else [],
        }
        if h is not None:
            failure["reason"] = h.reason(error)
    preserved, preservation_failure = False, None
    if h is not None and admitted:
        try:
            for item, pin in pins.items():
                h.read_pinned(item, pin)
            h.need(
                all(h.sha(item.read_bytes()) == pin for item, pin in created.items()),
                "output_changed",
            )
            preserved = True
        except BaseException as error:
            status = "partial" if created else "stopped"
            preservation_failure = {
                "stage": "preservation",
                "class": type(error).__name__,
                "public_frames": util.public_frames(error, public),
            }
            if failure is None:
                failure = preservation_failure
    result = {
        "format": "buddha.fresh-review-preparation-result.v1",
        "builder": builder_ref,
        "input_manifest": manifest_ref,
        "status": status,
        "stage": stage,
        "failure": failure,
        "source_and_inputs_preserved": preserved,
        "preservation_failure": preservation_failure,
        "files": {str(item.relative_to(destination)): pin for item, pin in created.items()},
        "provider_calls": 0,
        "grants_owners_runtime_reviewers_packets_created": False,
        "new_custody_attestation": False,
        "funding_or_scientific_adoption": False,
    }
    if created:
        with (destination / "preparation-result.json").open("xb") as stream:
            stream.write(h.canonical(result))
    print(json.dumps({key: result[key] for key in ("status", "stage", "failure")}))
    return 0 if status == "complete_unfunded_review_configuration" else 2


if __name__ == "__main__":
    raise SystemExit(main())
