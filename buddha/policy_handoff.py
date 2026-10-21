"""Check a caller-pinned, unallocated policy proposal; never prepare execution.

This verifies configuration and selected bytes, not provider access, current
pricing, an installed container, available funds or authority to dispatch.
The returned control bindings fit the existing 1,024-input preparation seam.
"""

import hashlib
import sys
from pathlib import Path
from typing import cast

from buddha import gateway, policy_panel, policy_run, policy_study
from buddha import native_pipeline as pipeline
from buddha.releases import (
    MAX_FILES,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _text,
    file_hash,
)


class PolicyHandoffError(ReleaseError):
    """The proposal differs from its trusted pins or required configuration."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sources() -> list[Path]:
    return list(
        dict.fromkeys(
            [
                *policy_run._sources(),
                *(Path(_text(sys.modules[name].__file__)).absolute() for name in gateway.CORE),
                Path(__file__).absolute(),
                Path(_text(policy_panel.__file__)).absolute(),
                Path(_text(policy_study.__file__)).absolute(),
            ]
        )
    )


def _profiles(execution: policy_run._Execution) -> dict[str, object]:
    selected = {}
    for role in ("generation", "native"):
        component = _object(execution.template[role])
        selection = Selection.from_bytes(_json(component["selection"]))
        roots = {key: pipeline._absolute(path) for key, path in _object(component["roots"]).items()}
        selected[role] = gateway._profiles(selection, roots)
    config = _object(execution.recipe["config"])
    if _json(config) != _json(execution.study.schedule()[0]["generation_config"]):
        raise PolicyHandoffError("generation config differs from the exact first treatment")
    generation_role = _object(execution.recipe["profile"], {"capability", "profile_id"})
    capability, profile_id = (
        _text(generation_role["capability"]),
        _text(generation_role["profile_id"]),
    )
    if (
        capability not in gateway.CAPABILITIES
        or gateway.CAPABILITIES[capability][0] != config["provider"]
    ):
        raise PolicyHandoffError("generation capability differs from its provider")
    profile = _object(_object(_object(selected["generation"][capability])["profiles"])[profile_id])
    spec = _object(profile["spec"])
    if any(spec[key] != config[key] for key in ("provider", "model", "max_output_tokens")):
        raise PolicyHandoffError("generation differs from the selected host profile")
    native = []
    for provider, models in _object(_object(execution.template["native"])["profiles"]).items():
        if provider not in {"openai", "anthropic"}:
            raise PolicyHandoffError("unsupported native model provider")
        capability = next(
            key for key, value in gateway.CAPABILITIES.items() if value[0] == provider
        )
        choices = _object(_object(selected["native"][capability])["profiles"])
        for model, name in _object(models).items():
            _text(model)
            owned = _object(choices[_text(name)])
            owned_spec = _object(owned["spec"])
            if owned_spec["model"] != model or owned_spec["provider"] != provider:
                raise PolicyHandoffError("native mapping differs from the selected host profile")
            native.append(
                {
                    "provider": provider,
                    "model": model,
                    "capability": capability,
                    "profile_id": name,
                    "profile": owned,
                }
            )
    return {"generation": generation_role | {"profile": profile}, "native": native}


def check_handoff(path: Path, *, expected_sha256: str) -> dict[str, object]:
    """Return detached proposal consistency only; funding always stays unallocated.

    Caller-trusted raw pins establish reviewed identity, not authenticity or
    publication time. Up to 1,024 regular-file control pins are checked; full
    component trees use the existing Selection inventory and byte ceilings.
    """
    try:
        if not isinstance(path, Path):
            raise PolicyHandoffError("an explicit proposal Path is required")
        path = path.absolute()
        raw = pipeline._read(path, _digest(expected_sha256))
        record = _object(
            _load(raw),
            {"format", "study", "baseline", "publications", "source_sha256", "requested_terms"},
        )
        if record["format"] != "buddha.policy-handoff.v1":
            raise PolicyHandoffError("unsupported unallocated policy proposal")
        pins = _object(record["source_sha256"])
        if len(pins) > min(MAX_FILES, 1024):
            raise PolicyHandoffError("proposal control inventory exceeds its bounded input seam")
        aliases: set[Path] = set()
        for name, digest in pins.items():
            source = pipeline._absolute(name)
            if str(source) != name or ".." in source.parts or source in aliases or source == path:
                raise PolicyHandoffError("proposal control paths have aliases or self-reference")
            aliases.add(source)
            _digest(digest)
        execution = policy_run._configuration(record["study"], record["baseline"], pins)
        reviewed = {str(source): digest for source, digest in execution.files.items()}

        def reference(value: object) -> bytes:
            item = _object(value, {"path", "sha256"})
            source = pipeline._absolute(item["path"])
            digest = _digest(item["sha256"])
            if str(source) in reviewed and reviewed[str(source)] != digest:
                raise PolicyHandoffError("proposal references have conflicting identities")
            data = pipeline._read(source, digest)
            reviewed[str(source)] = digest
            return data

        publications = _object(
            record["publications"],
            {"intent", "protocol", "source_review", "panel_plan", "review_materials"},
        )
        intent, protocol, source_review, saved_plan, materials = (
            reference(publications[key])
            for key in ("intent", "protocol", "source_review", "panel_plan", "review_materials")
        )
        protocol_sha256 = _sha(protocol)
        plan = policy_panel.plan_panel(
            execution.study,
            intent_raw=intent,
            expected_intent_sha256=_sha(intent),
            source_review_raw=source_review,
            expected_source_review_sha256=_sha(source_review),
            expected_protocol_sha256=protocol_sha256,
        )
        if _json(_load(saved_plan)) != _json(plan):
            raise PolicyHandoffError("saved panel differs from its exact planned coordinates")
        source_record = _object(execution.study.to_record()["source"])
        policy_panel._materials(
            materials, _sha(materials), protocol, protocol_sha256, _object(source_record["release"])
        )
        # Derive installed closure independently; unrelated supplied hashes cannot replace it.
        gateway._core_sources()
        for item in _sources():
            name, digest = str(item), file_hash(item, max_bytes=256 * 1024**2)
            if pins.get(name) != digest:
                raise PolicyHandoffError("required installed source is absent or changed")
            reviewed[name] = digest
        for name, digest in reviewed.items():
            if pins.get(name) != digest:
                raise PolicyHandoffError(
                    "required configuration/publication pin is absent or changed"
                )
        selected = {}
        for role in ("generation", "native"):
            selection = Selection.from_bytes(_json(_object(execution.template[role])["selection"]))
            selected[role] = {
                "selection_sha256": selection.fingerprint(),
                "component_files": {
                    name: len(_object(files))
                    for name, files in _object(selection.to_record()["components"]).items()
                },
            }
        profiles = _profiles(execution)
        terms = _object(record["requested_terms"], {"budget_microusd", "max_calls"})
        for value in terms.values():
            gateway._amount(value, positive=True)
        # Recheck consumed and extra controls; do not adopt drift as a new reviewed hash.
        for name, expected in pins.items():
            if file_hash(Path(name), max_bytes=256 * 1024**2) != expected:
                raise PolicyHandoffError("proposal input changed during checking")
        for role in ("generation", "native"):
            pipeline._component(_object(execution.template[role]))
        if pipeline._read(path, expected_sha256) != raw:
            raise PolicyHandoffError("proposal changed during checking")
        reviewed.update({name: _digest(digest) for name, digest in pins.items()})
        reviewed[str(path)] = expected_sha256
        if len(reviewed) > 1024:
            raise PolicyHandoffError("reviewed controls exceed the existing preparation input seam")
        study, tasks, schedule = execution.study, execution.study.tasks, execution.study.schedule()
        result = {
            "format": "buddha.policy-handoff-check.v1",
            "status": "configuration_checked",
            "study_sha256": study.fingerprint(),
            "tasks_sha256": tasks.fingerprint(),
            "planned": {
                "task_ids": [task.id for task in tasks.tasks],
                "arms": [arm["arm_id"] for arm in study.arms],
                "cell_ids": [cell["cell_id"] for cell in schedule],
                "cells": len(schedule),
                "generation_sets": len(tasks.tasks) * len(schedule),
                "generation_answers": sum(task.count for task in tasks.tasks) * len(schedule),
                "judging_occasions": sum(
                    len(cast(list[object], cell["judge_occasions"])) for cell in schedule
                ),
                "panel": plan["counts"],
            },
            "funding": {
                "status": "unallocated",
                **terms,
                "scope": "policy study: " + study.fingerprint(),
            },
            "selections": selected,
            "profiles": profiles,
            "reviewed_bindings": reviewed,
            "limitations": [
                "Configuration consistency only; no authority, provider access or readiness.",
                "Image/environment bytes are configuration, not a running-container audit.",
                "Profile rates are caller-selected bounds, not current billing verification.",
                "Execution requires separately bound existing authority and local review.",
            ],
        }
        return _load(_json(result))
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        raise PolicyHandoffError(
            "unallocated policy configuration is invalid; no execution prepared"
        ) from None
