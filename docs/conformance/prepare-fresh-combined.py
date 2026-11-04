"""Prepare one unfunded combined declaration from reviewed metadata only.

--inputs names the reviewed manifest; --sha256 binds its exact bytes. This runs
once, writes only a new destination, and creates no runtime, authority or review.
It does not perform the future funded/full-handoff check or permit spending.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

LIBRARY = Path(r"C:\Users\arvik\code\buddha\runs\reviews\fresh-primary-preparation")
HELPER = LIBRARY / "docs/conformance/prepare-fresh-primary.py"
HELPER_SHA = "a362fe4b5e2ed3d2eb44f7cfee09b04d0cc9726ac7b2c14fc542269f7770bbb2"
UTILITIES = Path(
    r"C:\Users\arvik\code\buddha\runs\reviews\fresh-plain-reference-preparation\docs\conformance\prepare-fresh-plain-references.py"
)
UTILITIES_SHA = "8a60b6b35567714ae26f9dfd2992700968844e4b68f50e14a8378e65d4a22708"
MODES = ("regenerate", "in-context")
METHOD = "all_conditions_then_equal_prompts_descriptive.v1"
SEED_SHA = "2b87bfe0d3c97ee45db2d45260985ffe0234eca93967f4689fb7c59f82603921"
ROLES = {
    "primary_result",
    "plain_result",
    "review_result",
    "assessment",
    "handoff",
    "check",
    "review_plan",
    "regenerate_baseline",
    "regenerate_generation",
    "in-context_baseline",
    "in-context_generation",
}


def metadata_terms(assessment, handoff, checked, pairs, refs, instrument, need):
    need(
        handoff["format"] == "buddha.improver-handoff.v1"
        and handoff["assessment"] == refs["assessment"]
        and checked["assessment_sha256"] == refs["assessment"]["sha256"]
        and checked["directory"] == handoff["directory"]
        and checked["funding"] == {"status": "unallocated"}
        and checked["requested_phase_limits"] == assessment["phase_limits"]
        and all(
            checked["reviewed_bindings"].get(name) == pin
            for name, pin in handoff["source_sha256"].items()
        ),
        "review_handoff_join",
    )
    need(
        checked["planned"]
        == {
            "starts": 2,
            "development_repetitions": 2,
            "opportunities_per_arm": 2,
            "development_tasks": 3,
            "final_tasks": 26,
            "sealed_repetitions": 1,
            "maximum_final_cells": 312,
        }
        and set(pairs) == set(MODES),
        "combined_scientific_scope",
    )
    envelopes = {}
    for mode in MODES:
        baseline, recipe = pairs[mode]
        generation = baseline["generation"]
        need(
            baseline["format"] == "buddha.native-baseline.v1"
            and recipe["format"] == "buddha.frozen-generation.v1"
            and generation["descriptor"] == refs[mode + "_generation"]["path"]
            and baseline["tasks"] == recipe["tasks"] == refs["task"]["path"]
            and recipe["entrypoint"] == "seed.py"
            and recipe["config"]["instructions"] == ""
            and recipe["config"]["sampling"] == mode
            and all(
                recipe["config"][name] == assessment["generation"]["config"][name]
                for name in ("provider", "model", "max_output_tokens")
            )
            and recipe["profile"] == assessment["generation"]["profile"]
            and generation["selection"]["components"]["agent"] == {"seed.py": SEED_SHA}
            and generation["selection"]["components"]["host"]
            == assessment["generation"]["selection"]["components"]["host"]
            and baseline["stages"] == assessment["stages"]
            and instrument(baseline["native"]) == instrument(assessment["native"]),
            "plain_reference_join",
        )
        envelopes[mode] = {}
        for role in ("generation", "native"):
            values = {name: baseline[role][name] for name in ("budget_microusd", "max_calls")}
            need(
                all(type(value) is int and 0 < value < 2**63 for value in values.values()),
                "nominal_owner_envelope",
            )
            need(
                values == {name: assessment[role][name] * 26 for name in values},
                "nominal_owner_envelope",
            )
            envelopes[mode][role] = values
    return {
        "primary_phase_limits": copy.deepcopy(assessment["phase_limits"]),
        "plain_nominal_owner_envelopes": envelopes,
        "funding_status": "unallocated",
        "shared_reference_allocation": None,
        "combined_allocation": None,
    }


def extend_handoff(base, additions, own_path, need):
    need(own_path not in additions and own_path not in base["source_sha256"], "control_cycle")
    need(
        all(base["source_sha256"].get(name, pin) == pin for name, pin in additions.items()),
        "control_replacement",
    )
    result = copy.deepcopy(base)
    result["source_sha256"].update(additions)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    h = util = None
    public = {
        Path(__file__).absolute(): "prepare_fresh_combined",
        HELPER: "prepare_fresh_primary",
        UTILITIES: "prepare_fresh_plain_references",
    }
    created, pins, destination = {}, {}, None
    stage, failure = "admission", None
    try:
        for name, path, pin in (
            ("readers", HELPER, HELPER_SHA),
            ("utilities", UTILITIES, UTILITIES_SHA),
        ):
            if hashlib.sha256(path.read_bytes()).hexdigest() != pin:
                raise ValueError("public_helper_changed")
            spec = importlib.util.spec_from_file_location(name, path)
            value = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(value)
            if name == "readers":
                h = value
            else:
                util = value
        manifest_raw = h.read_pinned(args.inputs.absolute(), args.sha256)
        record = h.load(manifest_raw)
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
                "task_reference",
                "track_controls",
            }
            and record["format"] == "buddha.fresh-combined-inputs.v1"
            and h.path(record["source_root"]) == LIBRARY,
            "manifest_scope",
        )
        h.need(set(record["inputs"]) == ROLES, "input_roles")
        destination = h.path(record["destination"])
        h.need(
            destination.parent == LIBRARY.parents[1]
            and not destination.exists()
            and not destination.is_symlink(),
            "fresh_destination",
        )
        for field in ("source_sha256", "files"):
            h.need(type(record[field]) is dict and 1 <= len(record[field]) <= 1024, "input_count")
            for name, pin in record[field].items():
                path = h.static_path(h.path(name))
                h.need(path not in pins and not path.is_relative_to(destination), "input_alias")
                if field == "source_sha256":
                    public[path] = ".".join(path.relative_to(LIBRARY).with_suffix("").parts)
                    h.need(
                        path.is_relative_to(LIBRARY)
                        and path.suffix == ".py"
                        and pin not in h.AGENTS.values(),
                        "public_source",
                    )
                pins[path] = h.digest(pin)
        h.need(
            len(set(record["inputs"].values())) == len(ROLES)
            and all(h.path(path) in pins for path in record["inputs"].values()),
            "role_alias",
        )
        h.need(
            all(
                h.path(path).suffix == ".json" and pins[h.path(path)] not in h.AGENTS.values()
                for path in record["inputs"].values()
            ),
            "metadata_only_roles",
        )
        h.need(
            len(record["track_controls"]) == 3
            and {h.path(ref["path"]) for ref in record["track_controls"]}
            == {
                Path(__file__).absolute().parents[2] / name
                for name in (
                    "docs/REVIEW-TRACKS.md",
                    "docs/DESIGN.md",
                    "docs/conformance/imp01-review-tracks-decision.json",
                )
            },
            "track_controls",
        )
        builder = {
            "path": str(Path(__file__).absolute()),
            "sha256": h.digest(record["driver_sha256"]),
        }
        manifest = {"path": str(args.inputs.absolute()), "sha256": h.digest(args.sha256)}
        for path, pin in (
            (HELPER, HELPER_SHA),
            (UTILITIES, UTILITIES_SHA),
            (Path(builder["path"]), builder["sha256"]),
            (args.inputs.absolute(), manifest["sha256"]),
        ):
            h.need(pins.get(path, pin) == pin, "control_conflict")
            pins[path] = pin
        for path, pin in pins.items():
            h.read_pinned(path, pin)
        sys.path.insert(0, str(LIBRARY))
        from buddha import plain_comparison

        h.need(Path(plain_comparison.__file__).absolute() in pins, "library_namespace")
        consumers = plain_comparison._source_hashes()
        h.need(all(pins.get(Path(path)) == pin for path, pin in consumers.items()), "consumer_pins")
        stdlib = Path(sys.base_prefix).resolve()

        def audit(event, values):
            if event.startswith(("socket.", "subprocess.", "sqlite3.connect")) or event in {
                "os.system",
                "os.exec",
                "os.spawn",
                "os.posix_spawn",
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
            if event == "open" and not isinstance(values[0], int):
                path = Path(values[0]).absolute()
                writing = values[2] & (
                    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
                )
                h.need(
                    path.is_relative_to(destination)
                    if writing
                    else path in pins or path in created or path.is_relative_to(stdlib),
                    "file_scope",
                )
                if writing:
                    h.static_path(path)
            if event == "os.mkdir":
                h.need(Path(values[0]).absolute().is_relative_to(destination), "mkdir_scope")

        sys.addaudithook(audit)
        data = {
            name: h.load(h.read_pinned(h.path(path), pins[h.path(path)]))
            for name, path in record["inputs"].items()
        }
        refs = {
            name: {"path": path, "sha256": pins[h.path(path)]}
            for name, path in record["inputs"].items()
        }
        refs["task"] = record["task_reference"]
        for parent, status in (
            ("primary", "complete_unfunded_configuration_only"),
            ("plain", "complete_unfunded_plain_descriptors"),
            ("review", "complete_unfunded_review_configuration"),
        ):
            h.need(data[parent + "_result"]["status"] == status, "preparation_not_complete")
        h.need(
            data["primary_result"]["source_and_input_pins_preserved"] is True
            and all(
                data[name + "_result"]["source_and_inputs_preserved"] is True
                for name in ("plain", "review")
            ),
            "preparation_preservation",
        )
        for name, leaf in (
            ("assessment", "assessment-review-bound.json"),
            ("handoff", "handoff-unfunded.json"),
            ("check", "configuration-check.json"),
            ("review_plan", "review-plan.json"),
        ):
            h.need(
                util.inventory_pin(data["review_result"]["files"], leaf, h.need)
                == refs[name]["sha256"],
                "review_inventory_join",
            )
        for mode in MODES:
            for leaf in ("baseline", "generation"):
                h.need(
                    util.inventory_pin(
                        data["plain_result"]["files"], mode + "/" + leaf + ".json", h.need
                    )
                    == refs[mode + "_" + leaf]["sha256"],
                    "plain_inventory_join",
                )
        h.need(
            set(refs["task"]) == {"path", "sha256"}
            and Path(refs["task"]["path"]).parent == Path(refs["plain_result"]["path"]).parent
            and util.inventory_pin(
                data["plain_result"]["files"], Path(refs["task"]["path"]).name, h.need
            )
            == h.digest(refs["task"]["sha256"]),
            "task_reference_join",
        )
        pairs = {mode: (data[mode + "_baseline"], data[mode + "_generation"]) for mode in MODES}
        terms = metadata_terms(
            data["assessment"],
            data["handoff"],
            data["check"],
            pairs,
            refs,
            plain_comparison._instrument,
            h.need,
        )
        futures = {
            "primary_runtime": data["handoff"]["directory"],
            "reference_authority": str(destination / "NOT-CREATED-reference-authority.sqlite3"),
            "outer_launch": str(destination / "NOT-CREATED-unified-launch.json"),
            "outer_review": str(destination / "NOT-CREATED-review.json"),
        }
        for mode in MODES:
            futures[mode] = str(destination / ("NOT-CREATED-plain-" + mode))
        h.need(
            all(
                not h.path(path).exists() and not h.path(path).is_symlink()
                for path in futures.values()
            ),
            "future_exists",
        )
        stage = "declaration"
        destination.mkdir()

        def saved(name, value):
            path = destination / name
            raw = h.canonical(value)
            with path.open("xb") as stream:
                stream.write(raw)
            created[path] = h.sha(raw)
            return {"path": str(path), "sha256": created[path]}

        plan = {
            "format": "buddha.plain-comparison-plan.v1",
            "method": METHOD,
            "trial": futures["primary_runtime"],
            "definition_sha256": refs["assessment"]["sha256"],
            "references": [
                {
                    "name": mode,
                    "directory": futures[mode],
                    "authorization": futures["reference_authority"],
                    "definition": refs[mode + "_baseline"]["path"],
                    "sha256": refs[mode + "_baseline"]["sha256"],
                }
                for mode in MODES
            ],
            "consumer_sources": consumers,
        }
        h.need(plain_comparison._plan(h.canonical(plan)) == plan, "comparison_plan_invalid")
        plan_ref = saved("comparison-plan.json", plan)
        declaration_ref = saved(
            "unallocated-combined-declaration.json",
            {
                "format": "buddha.fresh-combined-declaration.v1",
                "status": "unadopted_unfunded_not_launchable",
                "builder": builder,
                "input_manifest": manifest,
                "comparison_plan": plan_ref,
                "review_assessment": refs["assessment"],
                "review_plan": refs["review_plan"],
                "prepared_results": [
                    refs[name + "_result"] for name in ("primary", "plain", "review")
                ],
                "terms": terms,
                "future_paths": futures,
                "task_reference": refs["task"],
                "tracks": {"ai_only_waits_for_humans": False, "human_ratings_created": False},
                "native_review_selection": (
                    "Retained candidate only; no context/model adoption or allocation."
                ),
                "new_custody_attestation": False,
                "validation_scope": (
                    "Metadata joins and existing comparison-plan validator only; "
                    "prepared task/protocol/custody/full-handoff evidence is inherited, not rerun."
                ),
            },
        )
        additions = dict(consumers)
        for ref in [
            plan_ref,
            declaration_ref,
            builder,
            manifest,
            refs["task"],
            *refs.values(),
            *record["track_controls"],
        ]:
            path, pin = h.path(ref["path"]), h.digest(ref["sha256"])
            if ref not in (refs["task"], plan_ref, declaration_ref):
                h.need(pins.get(path, created.get(path)) == pin, "binding_not_admitted")
            h.need(additions.get(str(path), pin) == pin, "binding_conflict")
            additions[str(path)] = pin
        binding_ref = saved(
            "reference-input-bindings.json",
            {
                "format": "buddha.prospective-reference-input-bindings.v1",
                "status": "unfunded_configuration_only",
                "input_files": list(additions),
                "expected_input_hashes": additions,
                "shared_authorization": futures["reference_authority"],
                "baseline_descriptors": [refs[mode + "_baseline"] for mode in MODES],
                "future_actual_outer_and_raw_review_inputs": [
                    {"path": futures[name], "sha256": None}
                    for name in ("outer_launch", "outer_review")
                ],
                (
                    "must_add_this_bindings_file_and_final_actual_outer_review_pins_to_raw_controls"
                ): True,
                "no_actual_outer_or_raw_review_created": True,
            },
        )
        additions[binding_ref["path"]] = binding_ref["sha256"]
        handoff_path = destination / "handoff-primary-unfunded.json"
        combined = extend_handoff(data["handoff"], additions, str(handoff_path), h.need)
        saved(handoff_path.name, combined)
        h.need(
            combined["assessment"] == refs["assessment"]
            and all(not h.path(path).exists() for path in futures.values()),
            "final_join",
        )
        stage = "complete"
    except BaseException as error:
        failure = {
            "stage": stage,
            "class": type(error).__name__,
            "public_frames": util.public_frames(error, public) if util else [],
        }
        if h is not None:
            failure["reason"] = h.reason(error)
    preserved = False
    if h is not None and pins:
        try:
            preserved = all(h.read_pinned(path, pin) is not None for path, pin in pins.items())
            preserved = preserved and all(
                h.sha(path.read_bytes()) == pin for path, pin in created.items()
            )
        except BaseException as error:
            failure = failure or {
                "stage": "preservation",
                "class": type(error).__name__,
                "public_frames": util.public_frames(error, public) if util else [],
            }
    result = {
        "format": "buddha.fresh-combined-preparation-result.v1",
        "status": "complete_unfunded_combined_declaration"
        if stage == "complete" and preserved and failure is None
        else "partial",
        "stage": stage,
        "failure": failure,
        "named_input_and_output_pins_preserved": preserved,
        "files": {str(path.relative_to(destination)): pin for path, pin in created.items()},
        "full_handoff_or_capacity_check_performed": False,
        "provider_calls": 0,
        "funding_or_adoption_or_new_attestation": False,
        "scope": (
            "Declaration-only; reference-only task bytes and inherited controls not reopened. "
            "No authority/runtime/owners/reviewers created; "
            "final funded/full-handoff validation remains."
        ),
    }
    if created:
        with (destination / "preparation-result.json").open("xb") as stream:
            stream.write(h.canonical(result))
    print(json.dumps({name: result[name] for name in ("status", "stage", "failure")}))
    return 0 if result["status"] == "complete_unfunded_combined_declaration" else 2


if __name__ == "__main__":
    raise SystemExit(main())
