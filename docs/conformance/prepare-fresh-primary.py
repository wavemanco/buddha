"""One fresh, unfunded IMP-01 primary bundle; requires a reviewed per-file manifest.

This file imports no historical constructor and executes no selected program.
Run only after the manifest, driver and current public source have been reviewed.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
from contextlib import ExitStack
from pathlib import Path
from threading import get_ident
from unittest.mock import patch

MAX_BYTES = 256 * 1024**2
INPUT_NAMES = {
    "study",
    "definition",
    "source",
    "release",
    "split",
    "panel",
    "custody",
    "population",
    "analysis",
    "rule",
}
METADATA_NAMES = ("study", "definition", "release", "custody", "population", "analysis")
AGENTS = {
    # Prospective input-compatibility fork; historical builders retain their original P.
    "initial": "b84ae0e392d6dd51d46342c8502c62b365eaabb9371394f13d7c47825d2ee1a7",
    "evolved": "f1c832d5168986bf4bf220bb31f31754192cf262d523118b1f47ea0540fb6bc7",
}
POLICY = {
    "format": "buddha.evidence-observation-policy.v2",
    "max_total_bytes": 32 * 1024**3,
    "max_tree_entries": 100_000,
    "max_consumed_paths": 65_536,
    "max_resident_bytes": 0,
}
HISTORY_PARTS = {
    "owners",
    "attempts",
    "observations",
    "completed",
    "cells",
    "witness",
    "search",
    "final",
    "trial",
    "trial-runtime",
    "not-created-trial-runtime",
}


class PreparationError(ValueError):
    """A fixed, safe-to-record preparation refusal code."""


def need(condition, code):
    if not condition:
        raise PreparationError(code)


def reason(error):
    return str(error) if type(error) is PreparationError else type(error).__name__


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "invalid_digest")
    return value


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def load(raw):
    def invalid(_):
        raise PreparationError("nonfinite_json")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    need(type(value) is dict, "metadata_root_not_object")
    return value


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def metadata_inputs(raw, parser):
    result = {}
    for name in METADATA_NAMES:
        try:
            result[name] = parser(raw[name])
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise PreparationError("invalid_metadata_" + name) from None
    return result


def reference_readers(original_ref, original_read, hash_only, pins, opaque_paths):
    allowed = None

    def metadata_read(item, *args, **kwargs):
        nonlocal allowed
        target = path(str(Path(item).absolute()))
        if target in hash_only | opaque_paths:
            need(
                len(args) == 1
                and not kwargs
                and type(args[0]) is str
                and allowed == (target, args[0], os.getpid(), get_ident()),
                "opaque_input_on_metadata_route",
            )
            allowed = None  # Consume the single original _ref byte-verification read.
        return original_read(item, *args, **kwargs)

    def checked_ref(value, controls, *, source=False):
        nonlocal allowed
        target = (
            path(value["path"]) if type(value) is dict and type(value.get("path")) is str else None
        )
        if target not in hash_only:
            return original_ref(value, controls, source=source)
        need(
            set(value) == {"path", "sha256"}
            and source is False
            and digest(value["sha256"]) == pins[target],
            "hash_reference_not_exact",
        )
        need(allowed is None, "nested_hash_reference")
        allowed = (target, pins[target], os.getpid(), get_ident())
        try:
            return original_ref(value, controls, source=source)
        finally:
            allowed = None

    return checked_ref, metadata_read


def path(value):
    need(type(value) is str, "path_not_text")
    item = Path(value)
    need(item.is_absolute() and item == item.resolve(), "path_not_canonical")
    return item


def static_path(item):
    lowered = item.name.lower()
    need(
        not any(part.casefold() in HISTORY_PARTS for part in item.parts), "runtime_history_refused"
    )
    need(not re.search(r"\.(?:db|sqlite\d?)(?:$|[-.])", lowered), "database_path_refused")
    return item


def regular(item):
    for current in (*item.parents, item):
        info = current.lstat()
        need(
            not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400),
            "linked_input_refused",
        )
    need(
        stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_BYTES,
        "input_type_link_or_size",
    )
    return info


def signature(info):
    # Match releases.file_hash, including its Windows fstat/lstat ctime distinction.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def read_pinned(item, expected):
    static_path(item)
    before = regular(item)
    with item.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        need(
            opened.st_nlink == 1 and signature(opened)[:4] == signature(before)[:4],
            "opened_input_changed",
        )
        raw = stream.read(before.st_size + 1)
        opened = os.fstat(stream.fileno())
        need(
            opened.st_nlink == 1 and signature(opened)[:4] == signature(before)[:4],
            "opened_input_changed",
        )
    need(len(raw) == before.st_size and sha(raw) == digest(expected), "input_hash_changed")
    need(signature(regular(item)) == signature(before), "input_changed_during_read")
    return raw


def manifest(raw):
    record = load(raw)
    need(
        set(record)
        == {
            "format",
            "driver_sha256",
            "source_root",
            "source_sha256",
            "destination",
            "experiment_id",
            "files",
            "inputs",
            "copies",
            "provenance_receipts",
            "hash_only",
        },
        "manifest_fields",
    )
    need(record["format"] == "buddha.fresh-primary-inputs.v1", "manifest_format")
    digest(record["driver_sha256"])
    root, destination = path(record["source_root"]), path(record["destination"])
    need(root.is_dir() and destination.parent.is_dir(), "missing_root_or_parent")
    need(not destination.exists() and not destination.is_symlink(), "destination_exists")
    need(
        not root.is_relative_to(destination) and not destination.is_relative_to(root),
        "source_destination_overlap",
    )
    need(
        type(record["experiment_id"]) is str
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", record["experiment_id"]),
        "experiment_id",
    )
    inputs = record["inputs"]
    need(type(inputs) is dict and set(inputs) == INPUT_NAMES, "input_roles")
    pins = {}
    for field in ("source_sha256", "files"):
        need(type(record[field]) is dict and 1 <= len(record[field]) <= 65_536, "input_count")
        for name, pin in record[field].items():
            item = static_path(path(name))
            need(item not in pins, "input_alias_or_duplicate")
            if field == "source_sha256":
                need(item.is_relative_to(root) and item.suffix == ".py", "public_source_scope")
                need(pin not in AGENTS.values(), "selected_source_as_public_helper")
            need(not item.is_relative_to(destination), "output_as_input")
            pins[item] = digest(pin)
    need(all(path(name) in pins for name in inputs.values()), "unbound_input_role")
    need(
        all(pins[path(name)] not in AGENTS.values() for name in inputs.values()),
        "selected_source_digest_as_metadata",
    )
    need(type(record["hash_only"]) is list, "hash_only_list")
    hash_only = {path(name) for name in record["hash_only"]}
    need(
        len(hash_only) == len(record["hash_only"]) and hash_only <= pins.keys(),
        "hash_only_alias_or_unbound",
    )
    need(
        not hash_only.intersection(path(name) for name in inputs.values()), "hash_only_as_metadata"
    )
    copies = record["copies"]
    need(type(copies) is dict and copies, "component_copy_map")
    outputs = set()
    opaque = set()
    for name, source in copies.items():
        relative = Path(name)
        need(
            relative.parts
            and not relative.is_absolute()
            and relative.parts[0] == "components"
            and all(part not in {".", ".."} for part in relative.parts),
            "component_destination",
        )
        need(
            len(relative.parts) >= 3
            and relative.parts[1] not in {"source-runner", "native-runner"},
            "archived_runner_copy_refused",
        )
        target = destination / relative
        need(target not in outputs and path(source) in pins, "component_alias_or_unbound")
        outputs.add(target)
        for label, expected in AGENTS.items():
            if relative == Path("components") / (label + "-agent") / "candidate.py":
                need(pins[path(source)] == expected, "frozen_agent_hash")
                opaque.add(path(source))
    need(len(opaque) == 2, "missing_frozen_agents")
    need(not hash_only.intersection(path(name) for name in copies.values()), "hash_only_as_copy")
    need(not opaque.intersection(path(name) for name in inputs.values()), "source_as_metadata")
    need(
        all(
            pins[path(source)] not in AGENTS.values()
            or Path(name)
            in {Path("components") / (label + "-agent") / "candidate.py" for label in AGENTS}
            for name, source in copies.items()
        ),
        "opaque_source_role_alias",
    )
    need(
        type(record["provenance_receipts"]) is list and record["provenance_receipts"],
        "missing_static_provenance",
    )
    for ref in record["provenance_receipts"]:
        need(
            type(ref) is dict
            and set(ref) == {"path", "sha256"}
            and pins.get(path(ref["path"])) == digest(ref["sha256"]),
            "unbound_provenance",
        )
    return record, root, destination, pins, opaque


def relocate_screen(old, destination, release, prepare_selection):
    from buddha.channel import MAX_FRAME_BYTES

    result = copy.deepcopy(old)
    for role in ("generation", "native"):
        section = result[role]
        roots = {}
        for name, old_path in section["roots"].items():
            old_root = Path(old_path)
            need("components" in old_root.parts, "component_root_shape")
            suffix = old_root.parts[old_root.parts.index("components") + 1 :]
            roots[name] = destination.joinpath("components", *suffix)
            need(roots[name].is_dir(), "missing_component_root")
        section["roots"] = {key: str(value) for key, value in roots.items()}
        section["selection"] = prepare_selection(
            release, roots, capabilities=section["selection"]["capabilities"]
        ).to_record()
        if role == "generation":
            limits = section["executor"]["limits"]
            # Ready, callbacks, one over-quota request and done share the output stream.
            limits["max_stdout_bytes"] = max(
                limits["max_stdout_bytes"], (section["max_callbacks"] + 3) * MAX_FRAME_BYTES
            )
            section["runtime"]["path"] = str(roots["environment"] / "runtime.json")
            section["executor"]["mounts"] = [
                ["/agent", str(roots["agent"])],
                ["/runner", str(roots["runner"])],
            ]
    return result


def supplied_numerical(population, identities):
    """Existing test_improver_analysis fixture pattern, never empirical rows."""
    slots, rows = [], []
    for start, starter in enumerate(identities):
        for repeat in range(2):
            children = [
                sha(f"synthetic-{start}-{repeat}-{arm}".encode("ascii")) for arm in range(2)
            ]
            for arm, improver in enumerate(identities):
                slots.append(
                    {
                        "start": start,
                        "repetition": repeat,
                        "arm": arm,
                        "starter_agent_sha256": starter,
                        "improver_agent_sha256": improver,
                        "status": "selected",
                        "descendant_agent_sha256": children[arm],
                    }
                )
            for role, agent, utility, distinct in (
                ("starter", starter, 2, 3),
                ("initial", children[0], 5, 5),
                ("evolved", children[1], 7, 6),
            ):
                for index, task in enumerate(population["tasks"]):
                    rows.append(
                        {
                            "start": start,
                            "repetition": repeat,
                            "role": role,
                            "task_index": index,
                            "task_id": task["task_id"],
                            "family_id": task["family_id"],
                            "sealed_repetition": 0,
                            "agent_sha256": agent,
                            "status": "observed",
                            "utility": utility,
                            "distinct": distinct,
                        }
                    )
    return slots, rows


def prepare(record, root, destination, pins, opaque, manifest_ref, driver_ref):
    sys.path.insert(0, str(root))
    sys.dont_write_bytecode = True
    from buddha import (
        candidate_run,
        improver_analysis,
        improver_assessment,
        improver_handoff,
        improver_study,
        native_pipeline,
        native_run,
        source_screen,
        unified_launch,
        validation_study,
    )
    from buddha.answers import TaskSet
    from buddha.doctor import _observation_policy
    from buddha.improvement_rule import ImprovementRule
    from buddha.releases import Release, Selection, _json, _load, prepare_selection

    modules = (
        candidate_run,
        native_run,
        improver_analysis,
        improver_assessment,
        improver_handoff,
        improver_study,
        source_screen,
        unified_launch,
    )
    need(
        all(Path(module.__file__).absolute().is_relative_to(root) for module in modules),
        "wrong_import_namespace",
    )
    closure = {}
    for item in unified_launch._sources():
        item = item.absolute()
        need(item.is_relative_to(root) and item in pins, "source_closure_unbound")
        closure[item] = sha(read_pinned(item, pins[item]))
    input_raw = {
        name: read_pinned(path(value), pins[path(value)])
        for name, value in record["inputs"].items()
    }
    old = metadata_inputs(input_raw, _load)
    need(
        all(
            pins.get(path(ref["path"])) == digest(ref["sha256"])
            for ref in old["custody"]["evidence"]
        ),
        "unreviewed_custody_reference",
    )
    hash_only = {path(name) for name in record["hash_only"]}
    need(
        len(old["custody"]["evidence"]) == 60
        and {path(ref["path"]) for ref in old["custody"]["evidence"]} == hash_only,
        "inherited_custody_graph_changed",
    )
    release = Release.from_record(old["release"])
    tasks = TaskSet.from_bytes(input_raw["source"])
    need(
        len(old["study"]["starts"]) == 2
        and old["study"]["repetitions"] == 2
        and old["study"]["descendant_opportunities"] == 2
        and old["study"]["selection"]["seed"] == 7
        and len(old["definition"]["final_ids"]) == 26,
        "scientific_grid_changed",
    )
    need(
        all(len(row["screen"]["selected_ids"]) == 3 for row in old["study"]["starts"]),
        "development_panel_changed",
    )
    consumed = set()
    created = {}

    def read(item):
        need(item in pins, "unknown_input_read")
        consumed.add(item)
        return read_pinned(item, pins[item])

    def write(name, raw):
        target = destination / name
        need(target.is_relative_to(destination), "output_escape")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
        created[target] = sha(raw)
        return {"path": str(target), "sha256": created[target]}

    def saved(name, value):
        return write(name, _json(value))

    # The audit hook is deliberately process-local and never a hostile-code sandbox.
    # All selected programs remain byte data; no selected worker is launched.
    library = Path(sys.base_prefix).resolve()
    public = {item for item in pins if item.is_relative_to(root)}
    opaque_paths = opaque | {
        destination / "components" / (label + "-agent") / "candidate.py" for label in AGENTS
    }

    def output_path(item):
        need(item.is_relative_to(destination), "write_outside_bundle")
        static_path(item)

    def audit(event, args):
        if event.startswith(("socket.", "subprocess.", "sqlite3.connect")) or event in {
            "os.system",
            "os.exec",
            "os.posix_spawn",
            "os.spawn",
        }:
            raise PreparationError("external_operation_refused")
        if event in {"compile", "exec"}:
            name = args[1] if event == "compile" else getattr(args[0], "co_filename", "")
            if (type(name) is str and Path(name) in opaque_paths) or (
                event == "compile" and type(args[0]) is bytes and sha(args[0]) in AGENTS.values()
            ):
                raise PreparationError("selected_source_execution_refused")
        if event == "open" and not isinstance(args[0], int):
            item = Path(args[0]).absolute()
            flags = args[2]
            writing = bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if writing:
                output_path(item)
            else:
                need(
                    item in pins
                    or item in created
                    or item in public
                    or item.is_relative_to(library),
                    "read_outside_manifest",
                )
        if event in {"os.mkdir", "os.remove", "os.rename", "os.rmdir"}:
            need(event == "os.mkdir", "filesystem_mutation_refused")
            output_path(Path(args[0]).absolute())

    sys.addaudithook(audit)
    guards = (
        "ast.parse",
        "getpass.getpass",
        "buddha.authorization.Authorization.__init__",
        "buddha.authorization.Authorization.create",
        "buddha.gateway.Gateway.__init__",
        "buddha.executor.run_container",
        "buddha.gateway.RawHTTPTransport.prepare",
        "buddha.credentials.key_environment",
        "buddha.gateway.credential_fingerprints",
    )
    with ExitStack() as stack:
        stack.enter_context(_observation_policy(POLICY))
        for target in guards:
            stack.enter_context(
                patch(target, side_effect=PreparationError("forbidden_preparation_action"))
            )
        checked_ref, metadata_read = reference_readers(
            validation_study._ref, native_pipeline._read, hash_only, pins, opaque_paths
        )
        stack.enter_context(patch.object(validation_study, "_ref", side_effect=checked_ref))
        stack.enter_context(patch.object(native_pipeline, "_read", side_effect=metadata_read))
        destination.mkdir()
        stage = "materialize"
        try:
            for name, source in record["copies"].items():
                write(name, read(path(source)))
            for label, names in (
                ("source-runner", candidate_run.RUNNER_FILES),
                ("native-runner", native_run.RUNNER_FILES),
            ):
                for name in names:
                    relative = Path("buddha") / (name + ".py")
                    write(Path("components") / label / relative, read(root / relative))
            for item in closure:
                write(Path("trusted-host") / item.relative_to(root), read(item))
            for name in ("source", "release", "split", "panel", "custody"):
                write(
                    "inputs/" + ("development-panel" if name == "panel" else name) + ".json",
                    input_raw[name],
                )
            policy_ref = saved("observation-policy.json", POLICY)
            screens = []
            for start in old["study"]["starts"]:
                screen = source_screen.SourceScreen.from_bytes(
                    _json(relocate_screen(start["screen"], destination, release, prepare_selection))
                )
                screens.append(screen)
            identities = [
                Selection.from_bytes(_json(row["screen"]["generation"]["selection"])).agent_sha256
                for row in old["study"]["starts"]
            ]
            need(
                [screen.candidate_id for screen in screens] == identities,
                "selected_source_identity_changed",
            )
            study = copy.deepcopy(old["study"])
            study.update(
                format=improver_study._SETTLED_FORMAT,
                experiment_id=record["experiment_id"] + "-development",
                starts=[
                    {"name": row["name"], "screen": screen.to_record()}
                    for row, screen in zip(study["starts"], screens, strict=True)
                ],
                improvers=[
                    {
                        "name": label,
                        "selection": screen.to_record()["generation"]["selection"],
                        "roots": screen.to_record()["generation"]["roots"],
                        "entrypoint": "candidate.py",
                    }
                    for label, screen in zip(AGENTS, screens, strict=True)
                ],
                consumer_sources={
                    str(Path(improver_study.__file__).absolute()): pins[
                        Path(improver_study.__file__).absolute()
                    ]
                },
                assessment={"status": "not_frozen", "reason": "Fresh unfunded preparation."},
            )
            nominal = improver_study._caps(study, screens[0])
            need(
                all(
                    study["limits"][key] == value
                    for key, value in nominal.items()
                    if key != "study"
                ),
                "nominal_limits_changed",
            )
            study_ref = saved("inputs/study.json", study)
            runtime = screens[0].to_record()["generation"]["runtime"]["sha256"]
            parsed, parsed_screens = improver_study._declaration(study, runtime, active=False)
            _, source_texts, _ = improver_study._intrinsic_inputs(
                parsed,
                parsed_screens,
                path(study_ref["path"]),
                study_ref["sha256"],
                runtime,
                active=False,
            )
            need(source_texts == [], "selected_source_decoded")
            stage = "numerical"
            population = copy.deepcopy(old["population"])
            need(
                population["taskset_sha256"] == tasks.fingerprint()
                and population["custody_sha256"] == sha(input_raw["custody"]),
                "population_binding_changed",
            )
            population_ref = saved("numerical-population-proposed.json", population)
            rule = ImprovementRule.from_bytes(input_raw["rule"])
            rule_ref = write("improvement-rule-proposed.json", rule.to_bytes())
            plan = copy.deepcopy(old["analysis"])
            plan.update(
                population_sha256=population_ref["sha256"],
                analyzer_sources=improver_analysis._source_hashes(),
            )
            analysis = improver_analysis.ImproverAnalysisPlan.from_bytes(_json(plan))
            plan_ref = write("analysis-plan-proposed.json", analysis.to_bytes())
            need(
                len(population["tasks"]) == 26
                and len({row["family_id"] for row in population["tasks"]}) == 25
                and all(row["count"] == 10 for row in population["tasks"]),
                "family_population_changed",
            )
            slots, rows = supplied_numerical(population, identities)
            numeric = improver_analysis.analyze_improver_panel(
                analysis, population=population, slots=slots, rows=rows, rule=rule
            )
            need(
                numeric["coverage"]["complete"] and len(rows) == 312 and len(slots) == 8,
                "synthetic_coverage_changed",
            )
            for contrast, utility, distinct in (
                ("initial_gain", 3, 2),
                ("evolved_gain", 5, 3),
                ("improver_effect", 2, 1),
            ):
                for axis, value in (("utility", utility), ("distinct", distinct)):
                    need(
                        numeric["contrasts"][contrast][axis]["point"]
                        == {"numerator": value, "denominator": 1},
                        "synthetic_arithmetic_changed",
                    )
            numerical_ref = saved(
                "current-synthetic-numerical-check.json",
                {
                    "synthetic": True,
                    "not_actual_trial_data_or_adoption": True,
                    "plan": plan_ref,
                    "population": population_ref,
                    "rule": rule_ref,
                    "supplied_slots": slots,
                    "supplied_rows": rows,
                    "result": numeric,
                    "old_numerical_or_empirical_results_read": False,
                },
            )
            stage = "unfunded_handoff"
            definition = copy.deepcopy(old["definition"])
            definition.update(
                format=improver_assessment._SETTLED_FORMAT,
                experiment_id=record["experiment_id"],
                development=study_ref,
                tasks={
                    "path": str(destination / "inputs/source.json"),
                    "sha256": sha(input_raw["source"]),
                },
                custody={
                    "path": str(destination / "inputs/custody.json"),
                    "sha256": sha(input_raw["custody"]),
                },
                analysis_plan=plan_ref,
                improvement_rule=rule_ref,
                consumer_sources=improver_assessment._source_hashes(),
                **{
                    name: screens[0].to_record()[name]
                    for name in ("generation", "native", "stages")
                },
            )
            definition_ref = saved("assessment-proposed.json", definition)
            future = destination / "NOT-CREATED-trial-runtime"
            intent_ref = saved(
                "intent.json",
                {
                    "format": "buddha.imp01-unfunded-study-proposal.v3",
                    "status": "unfunded_proposal_not_adopted",
                    "live_launchable": False,
                    "experiment_id": record["experiment_id"],
                    "input_manifest": manifest_ref,
                    "builder": driver_ref,
                    "phase_limits_proposed_only": definition["phase_limits"],
                    "parent_configuration_receipts": record["provenance_receipts"],
                    "custody_metadata": "Exact retained declaration; no new exposure attestation.",
                    "pending": [
                        "prospective separation and protocol adoption",
                        "ordinary v2 full pass",
                        "comparable-size gate",
                        "accounts/prices/requests/runtime checks",
                        "separate funding, real approval and checked live handoff",
                    ],
                },
            )
            controls = {str(item): pin for item, pin in closure.items()} | {
                item["path"]: item["sha256"]
                for item in (
                    policy_ref,
                    intent_ref,
                    numerical_ref,
                    manifest_ref,
                    driver_ref,
                    *record["provenance_receipts"],
                )
            }
            handoff_ref = saved(
                "handoff-unfunded.json",
                {
                    "format": "buddha.improver-handoff.v1",
                    "assessment": definition_ref,
                    "expected_runtime_sha256": runtime,
                    "directory": str(future),
                    "source_sha256": controls,
                },
            )
            checked = improver_handoff.check_improver_handoff(
                path(handoff_ref["path"]), expected_sha256=handoff_ref["sha256"]
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
                },
                "planned_grid_changed",
            )
            need(
                checked["requested_phase_limits"] == old["definition"]["phase_limits"]
                and checked["reviewed_bindings"].get(policy_ref["path"]) == policy_ref["sha256"]
                and not future.exists(),
                "handoff_terms_or_policy_changed",
            )
            saved("configuration-check.json", checked)
            status, stop_reason = "complete_unfunded_configuration_only", None
        except Exception as error:
            status, stop_reason = "partial", reason(error)
        # Recheck only the named graph, never an original run directory or ledger.
        preserved = False
        preservation_error = None
        try:
            for item, pin in pins.items():
                read_pinned(item, pin)
            need(
                all(sha(item.read_bytes()) == pin for item, pin in created.items()),
                "output_changed",
            )
            preserved = True
        except Exception as error:
            preservation_error = reason(error)
            if status != "partial":
                status, stage, stop_reason = "partial", "preservation", preservation_error
        result = {
            "format": "buddha.fresh-primary-preparation-result.v1",
            "status": status,
            "stage": stage,
            "reason": stop_reason,
            "bundle": str(destination),
            "files": {str(item.relative_to(destination)): pin for item, pin in created.items()},
            "source_and_input_pins_preserved": preserved,
            "provider_calls": 0,
            "preservation_error": preservation_error,
            "grants_owners_runtime_approvals_account_reviews_launches_created": False,
            "SQL_connections": 0,
            "selected_source_semantics_read": False,
            "scientific_or_funding_adoption": False,
            "live_launchable": False,
            "snapshot_limit": (
                "Named before/after reads; no atomic snapshot or fresh custody claim."
            ),
        }
        saved("preparation-result.json", result)
        print(json.dumps({key: result[key] for key in ("status", "stage", "reason", "bundle")}))
        return 0 if status != "partial" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        need(digest(args.sha256) not in AGENTS.values(), "selected_source_as_manifest")
        raw = read_pinned(args.inputs.absolute(), args.sha256)
        record, root, destination, pins, opaque = manifest(raw)
        driver_path = Path(__file__).absolute()
        need(sha(driver_path.read_bytes()) == record["driver_sha256"], "driver_changed")
        manifest_ref = {"path": str(args.inputs.absolute()), "sha256": digest(args.sha256)}
        driver_ref = {"path": str(driver_path), "sha256": record["driver_sha256"]}
        for ref in (manifest_ref, driver_ref):
            item = path(ref["path"])
            need(pins.get(item, ref["sha256"]) == ref["sha256"], "control_pin_conflict")
            pins[item] = ref["sha256"]
        for item, pin in pins.items():
            read_pinned(item, pin)
        return prepare(record, root, destination, pins, opaque, manifest_ref, driver_ref)
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "stopped",
                    "reason": reason(error),
                    "details": "Input/source/body details omitted; existing evidence retained.",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
