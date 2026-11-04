"""Prepare two unfunded fixed-seed references; never create owners or run models."""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

LIBRARY = Path(r"C:\Users\arvik\code\buddha\runs\reviews\fresh-primary-preparation")
HELPER = LIBRARY / "docs/conformance/prepare-fresh-primary.py"
HELPER_SHA = "a362fe4b5e2ed3d2eb44f7cfee09b04d0cc9726ac7b2c14fc542269f7770bbb2"
ROLES = {"assessment", "source", "release", "primary_check", "primary_handoff", "policy"}
MODES = ("regenerate", "in-context")


def inventory_pin(inventory, leaf, check):
    matches = [
        pin for name, pin in inventory.items() if PureWindowsPath(name) == PureWindowsPath(leaf)
    ]
    check(len(matches) == 1, "primary_inventory_leaf_missing_or_ambiguous")
    return matches[0]


def plain_sections(primary, mode, count, answers, check):
    check(
        mode in MODES
        and type(count) is int
        and count == 26
        and type(answers) is int
        and answers == 260,
        "plain_scope",
    )
    generation, native = (copy.deepcopy(primary[name]) for name in ("generation", "native"))
    config = copy.deepcopy(generation["config"])
    config.update(instructions="", sampling=mode)
    for section in (generation, native):
        for key in ("budget_microusd", "max_calls"):
            value = section[key]
            check(type(value) is int and 0 < value * count < 2**63, "nominal_envelope")
            section[key] = value * count
    check(generation["max_calls"] >= answers, "plain_answer_call_ceiling")
    return generation, native, config


def matching_config(primary, config, mode, check):
    check(
        config["instructions"] == ""
        and config["sampling"] == mode
        and mode in MODES
        and all(config[key] == primary[key] for key in ("provider", "model", "max_output_tokens")),
        "plain_model_or_mode_changed",
    )


def validate_executor(settings, agent, runner, api, check):
    check(
        settings["role"] == "agent"
        and settings["runner_entrypoint"] == "buddha/agent_worker.py"
        and settings["mounts"] == [["/agent", str(agent)], ["/runner", str(runner)]],
        "fixed_worker_or_mount_changed",
    )
    api.ContainerSpec(
        settings["image_id"],
        settings["role"],
        tuple((name, Path(value)) for name, value in settings["mounts"]),
        settings["runner_entrypoint"],
        tuple(tuple(pair) for pair in settings["image_environment"]),
    )
    api.Limits(**settings["limits"])
    api._local_endpoint(settings["docker_endpoint"])


def public_frames(error, sources):
    chain, seen = [], set()
    while error is not None and id(error) not in seen and len(chain) < 16:
        seen.add(id(error))
        frames, trace = [], error.__traceback__
        while trace is not None and len(frames) < 64:
            code = trace.tb_frame.f_code
            name = sources.get(Path(code.co_filename).absolute())
            if name is not None:
                frames.append({"module": name, "function": code.co_name, "line": trace.tb_lineno})
            trace = trace.tb_next
        chain.append({"frames": frames})
        error = error.__cause__ if error.__cause__ is not None else error.__context__
    return chain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    public = {Path(__file__).absolute(): "prepare_fresh_plain_references"}
    stage, helper, created, destination, pins, admitted = "admission", None, {}, None, None, False
    builder_ref, manifest_ref = None, None
    try:
        if hashlib.sha256(HELPER.read_bytes()).hexdigest() != HELPER_SHA:
            raise ValueError("helper_changed")
        spec = importlib.util.spec_from_file_location("reviewed_primary_helpers", HELPER)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)  # Current pinned definitions only; never main/prepare.
        h = helper
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
                "primary_result",
            },
            "manifest_fields",
        )
        h.need(
            record["format"] == "buddha.fresh-plain-inputs.v1"
            and h.path(record["source_root"]) == LIBRARY,
            "library_or_format",
        )
        destination = h.path(record["destination"])
        h.need(
            destination.parent == LIBRARY.parents[1]
            and not destination.exists()
            and not destination.is_symlink(),
            "fresh_destination_required",
        )
        h.need(type(record["inputs"]) is dict and set(record["inputs"]) == ROLES, "input_roles")
        h.need(
            h.sha(Path(__file__).read_bytes()) == h.digest(record["driver_sha256"]),
            "driver_changed",
        )
        builder_ref = {"path": str(Path(__file__).absolute()), "sha256": record["driver_sha256"]}
        manifest_ref = {"path": str(args.inputs.absolute()), "sha256": h.digest(args.sha256)}
        pins = {}
        for field in ("source_sha256", "files"):
            h.need(type(record[field]) is dict and 1 <= len(record[field]) <= 1024, "input_count")
            for name, pin in record[field].items():
                item = h.static_path(h.path(name))
                h.need(
                    item not in pins and pin not in h.AGENTS.values(), "private_or_duplicate_input"
                )
                if field == "source_sha256":
                    h.need(
                        item.is_relative_to(LIBRARY) and item.suffix == ".py", "public_source_scope"
                    )
                    public[item] = ".".join(item.relative_to(LIBRARY).with_suffix("").parts)
                pins[item] = h.digest(pin)
        parent = record["primary_result"]
        h.need(
            set(parent) == {"path", "sha256"}
            and pins.get(h.path(parent["path"])) == parent["sha256"],
            "parent_result_unbound",
        )
        for name in record["inputs"].values():
            h.need(h.path(name) in pins, "input_role_unbound")
        for item, pin in (
            (args.inputs.absolute(), h.digest(args.sha256)),
            (Path(__file__).absolute(), record["driver_sha256"]),
            (HELPER, HELPER_SHA),
        ):
            h.need(pins.get(item, pin) == pin, "control_pin_conflict")
            pins[item] = pin
        for item, pin in pins.items():
            h.read_pinned(item, pin)
        admitted = True
        # Preload exact trusted modules before the read fence; Python may probe absent .pyc files.
        sys.path.insert(0, str(LIBRARY))
        sys.dont_write_bytecode = True
        from buddha import (
            agent_run,
            baseline,
            executor,
            gateway,
            native_evaluation,
            plain_comparison,
            unified_launch,
        )
        from buddha.answers import TaskSet
        from buddha.doctor import _observation_policy
        from buddha.releases import Release, _json, _load, prepare_selection

        for module in (
            agent_run,
            baseline,
            executor,
            gateway,
            native_evaluation,
            plain_comparison,
            unified_launch,
        ):
            h.need(Path(module.__file__).absolute() in pins, "wrong_public_namespace")
        required = set(baseline._sources()) | set(native_evaluation._sources())
        h.need(required <= pins.keys(), "required_public_helper_unbound")

        def read(item):
            h.need(item in pins, "unknown_input")
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
                "buddha.baseline.prepare_baseline",
                "buddha.baseline.run_baseline",
            ):
                stack.enter_context(
                    patch(target, side_effect=h.PreparationError("forbidden_preparation_action"))
                )
            raw = {name: read(h.path(value)) for name, value in record["inputs"].items()}
            data = {name: _load(value) for name, value in raw.items() if name != "source"}
            primary = data["assessment"]
            handoff, checked = data["primary_handoff"], data["primary_check"]
            parent_record = _load(read(h.path(parent["path"])))
            h.need(
                parent_record["status"] == "complete_unfunded_configuration_only"
                and parent_record["source_and_input_pins_preserved"] is True,
                "primary_not_complete",
            )
            for role, leaf in (
                ("assessment", "assessment-proposed.json"),
                ("primary_check", "configuration-check.json"),
                ("source", "inputs/source.json"),
                ("release", "inputs/release.json"),
                ("primary_handoff", "handoff-unfunded.json"),
                ("policy", "observation-policy.json"),
            ):
                h.need(
                    inventory_pin(parent_record["files"], leaf, h.need) == h.sha(raw[role]),
                    "primary_leaf_changed",
                )
            h.need(
                checked["status"] == "configuration_checked"
                and checked["funding"]["status"] == "unallocated"
                and checked["assessment_sha256"] == h.sha(raw["assessment"])
                and checked["directory"] == handoff["directory"]
                and handoff["assessment"]
                == {"path": record["inputs"]["assessment"], "sha256": h.sha(raw["assessment"])}
                and primary["tasks"]
                == {"path": record["inputs"]["source"], "sha256": h.sha(raw["source"])},
                "primary_reference_changed",
            )
            h.need(
                data["policy"] == h.POLICY
                and handoff["source_sha256"].get(record["inputs"]["policy"]) == h.sha(raw["policy"])
                and checked["reviewed_bindings"].get(record["inputs"]["policy"])
                == h.sha(raw["policy"]),
                "primary_policy_changed",
            )
            source = TaskSet.from_bytes(raw["source"])
            release = Release.from_record(data["release"])
            tasks = source.select(primary["final_ids"])
            count, answers = len(tasks.tasks), sum(task.count for task in tasks.tasks)
            h.need(
                release.fingerprint() == source.release_sha256
                and count == 26
                and answers == 260
                and all(task.count == 10 for task in tasks.tasks),
                "plain_population_changed",
            )
            stage = "materialization"
            destination.mkdir()
            stack.enter_context(_observation_policy(data["policy"]))
            tasks_ref = write("tasks.json", tasks.to_bytes())
            seed = read(LIBRARY / "agents/frozen_seed.py")
            h.need(h.sha(seed) == agent_run.FROZEN_SEED_SHA256, "fixed_seed_changed")
            write("components/fixed-agent/seed.py", seed)
            for name in agent_run.RUNNER_FILES:
                relative = Path("buddha") / (name + ".py")
                write(Path("components/fixed-runner") / relative, read(LIBRARY / relative))
            descriptors = []
            for mode in MODES:
                stage = mode
                generation, native, config = plain_sections(primary, mode, count, answers, h.need)
                for section, native_role in ((generation, False), (native, True)):
                    roots = {name: h.path(value) for name, value in section["roots"].items()}
                    roots["agent"] = destination / "components/fixed-agent"
                    if not native_role:
                        roots["runner"] = destination / "components/fixed-runner"
                    section["roots"] = {name: str(value) for name, value in roots.items()}
                    section["selection"] = prepare_selection(
                        release, roots, capabilities=section["selection"]["capabilities"]
                    ).to_record()
                    h.need(
                        section["selection"]["components"]["agent"]
                        == {"seed.py": agent_run.FROZEN_SEED_SHA256},
                        "fixed_agent_inventory_changed",
                    )
                    if not native_role:
                        h.need(
                            section["selection"]["components"]["runner"]
                            == {
                                "buddha/" + name + ".py": pins[LIBRARY / "buddha" / (name + ".py")]
                                for name in agent_run.RUNNER_FILES
                            },
                            "fixed_runner_inventory_changed",
                        )
                settings = copy.deepcopy(generation["executor"])
                settings.update(
                    runner_entrypoint="buddha/agent_worker.py",
                    mounts=[
                        ["/agent", generation["roots"]["agent"]],
                        ["/runner", generation["roots"]["runner"]],
                    ],
                )
                validate_executor(
                    settings,
                    Path(generation["roots"]["agent"]),
                    Path(generation["roots"]["runner"]),
                    executor,
                    h.need,
                )
                recipe = {
                    "format": "buddha.frozen-generation.v1",
                    "tasks": tasks_ref["path"],
                    "config": config,
                    "entrypoint": "seed.py",
                    "executor": settings,
                    "profile": generation["profile"],
                }
                recipe_ref = saved(mode + "/generation.json", recipe)
                descriptor = {
                    "format": "buddha.native-baseline.v1",
                    "tasks": tasks_ref["path"],
                    "generation": {
                        key: generation[key]
                        for key in ("selection", "roots", "budget_microusd", "max_calls")
                    },
                    "native": native,
                    "stages": copy.deepcopy(primary["stages"]),
                }
                descriptor["generation"]["descriptor"] = recipe_ref["path"]
                baseline_ref = saved(mode + "/baseline.json", descriptor)
                parsed, found_tasks, found_release = baseline._definition(
                    h.path(baseline_ref["path"])
                )
                profiles = gateway._profiles(
                    baseline._component(descriptor["generation"])[0],
                    {name: h.path(value) for name, value in generation["roots"].items()},
                )
                frozen = native_evaluation._frozen_recipe(
                    _json(recipe), h.path(tasks_ref["path"]), {"profiles": profiles}
                )
                matching_config(primary["generation"]["config"], frozen["config"], mode, h.need)
                h.need(
                    parsed == descriptor
                    and found_tasks.to_bytes() == tasks.to_bytes()
                    and found_release.fingerprint() == release.fingerprint(),
                    "baseline_identity_changed",
                )
                h.need(
                    plain_comparison._instrument(native)
                    == plain_comparison._instrument(primary["native"])
                    and unified_launch._profile(generation, recipe["profile"])
                    == unified_launch._profile(
                        primary["generation"], primary["generation"]["profile"]
                    ),
                    "official_instrument_or_generation_profile_changed",
                )
                descriptors.append(
                    {
                        "sampling": mode,
                        "recipe": recipe_ref,
                        "baseline": baseline_ref,
                        "config_sha256": h.sha(_json(config)),
                        "nominal_generation": {
                            key: generation[key] for key in ("budget_microusd", "max_calls")
                        },
                        "nominal_native": {
                            key: native[key] for key in ("budget_microusd", "max_calls")
                        },
                    }
                )
            h.need(
                descriptors[0]["config_sha256"] != descriptors[1]["config_sha256"],
                "mode_identity_collapsed",
            )
            saved(
                "intent.json",
                {
                    "format": "buddha.plain-reference-preparation.v1",
                    "status": "unfunded_unadopted_not_launchable",
                    "builder": builder_ref,
                    "input_manifest": manifest_ref,
                    "references": descriptors,
                    "primary_result": parent,
                    "primary_handoff": {
                        "path": record["inputs"]["primary_handoff"],
                        "sha256": h.sha(raw["primary_handoff"]),
                    },
                    "tasks": tasks_ref,
                    "nominal_envelopes": (
                        "Whole-panel budgets and calls equal 26 per-task ceilings. "
                        "No spending authority or completion forecast."
                    ),
                    "funding_or_runtime_or_outgoing_request_readiness": False,
                    "review_setup_or_new_custody_attestation": False,
                },
            )
            stage, status = "complete", "complete_unfunded_plain_descriptors"
            failure = None
    except BaseException as error:
        status = "partial" if created else "stopped"
        failure = {
            "stage": stage,
            "class": type(error).__name__,
            "public_frames": public_frames(error, public),
        }
        if helper is not None:
            failure["reason"] = helper.reason(error)
    preserved, preservation_failure = False, None
    if helper is not None and admitted:
        try:
            for item, pin in pins.items():
                helper.read_pinned(item, pin)
            helper.need(
                all(helper.sha(item.read_bytes()) == pin for item, pin in created.items()),
                "output_changed",
            )
            preserved = True
        except BaseException as error:
            status = "partial" if created else "stopped"
            preservation_failure = {
                "stage": "preservation",
                "class": type(error).__name__,
                "public_frames": public_frames(error, public),
            }
            if failure is None:
                failure = preservation_failure
    result = {
        "format": "buddha.fresh-plain-preparation-result.v1",
        "builder": builder_ref,
        "input_manifest": manifest_ref,
        "status": status,
        "stage": stage,
        "failure": failure,
        "source_and_inputs_preserved": preserved,
        "preservation_failure": preservation_failure,
        "files": {str(item.relative_to(destination)): pin for item, pin in created.items()},
        "provider_calls": 0,
        "grants_owners_runtime_created": False,
        "private_program_inputs": False,
    }
    if created:
        saved("preparation-result.json", result)
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("status", "stage", "failure", "source_and_inputs_preserved")
            }
        )
    )
    return 0 if status == "complete_unfunded_plain_descriptors" else 2


if __name__ == "__main__":
    raise SystemExit(main())
