"""Passive census of both original plain-reference baselines before key entry."""

from pathlib import Path
from typing import Any, cast

from buddha import baseline, baseline_results, gateway, plain_comparison
from buddha import launch_common as common
from buddha import native_pipeline as pipeline
from buddha.answers import TaskSet
from buddha.doctor import _Busy, _Unsupported
from buddha.improver_launch_state import _summary
from buddha.native_evaluation import _frozen_recipe, _read_baseline_generation
from buddha.native_evidence import NativeEvidence, _rows, _sha
from buddha.provider import _integer
from buddha.releases import ReleaseError, _digest, _json, _load, _object, _path, file_hash
from buddha.unified_funding import reference_scope


class BaselineStateError(ReleaseError):
    """Original reference owners or their frozen evidence cannot be joined."""


def _absent(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    return False


def _prefix(reader: NativeEvidence, tasks: TaskSet) -> int:
    """Validate every sealed predecessor and the one possible unfinished owner."""
    root, anchor = reader.root, reader.owner(reader.root / "owners/0")
    generation = _object(reader.template["generation"])
    recipe = _frozen_recipe(
        reader.bound(anchor, pipeline._absolute(generation["descriptor"])),
        pipeline._absolute(reader.template["tasks"]),
        anchor.manifest,
    )
    config = _object(recipe["config"])
    if config["instructions"] != "":
        raise BaselineStateError("plain references cannot add scaffold instructions")
    stages = reader._rows(reader.template["stages"])
    source, completed, available = None, 0, {}
    for index in range(len(reader.owners)):
        sealed = root / "completed" / (str(index) + ".json")
        if sealed.relative_to(root).as_posix() not in reader.capture.entries:
            if index != len(reader.owners) - 1:
                raise BaselineStateError("later owner skips an unfinished predecessor")
            if index:
                if source is None:
                    raise BaselineStateError("native owner lacks its original generation")
                reader.native_configuration(root, index, source.answers_path, available)
            break
        report, attempt = reader.stage(root, index, baseline=True)
        if index == 0:
            source = _read_baseline_generation(
                {
                    "baseline_directory": str(root),
                    "stage_seal_sha256": _sha(reader.raw(sealed)),
                    "owner_manifest_sha256": anchor.manifest_sha256,
                    "owner_ledger_sha256": anchor.ledger_sha256,
                },
                reader.authorization,
            )
            reader.verify_files(source.files)
            if source.tasks.fingerprint() != tasks.fingerprint():
                raise BaselineStateError("generation changes the selected reference tasks")
            answers = root / "native-answers.jsonl"
            if "native-answers.jsonl" in reader.capture.entries:
                if reader.raw(answers) != source.answers.native_bytes():
                    raise BaselineStateError("reference changes its original native answers")
            elif len(reader.owners) > 1:
                raise BaselineStateError("native owner lacks its original answer handoff")
            artifacts = _object(reader.release.to_record()["artifacts"])
            available[_path(artifacts["answers"])] = answers
        else:
            if source is None:
                raise BaselineStateError("native seal precedes generation")
            reader.native(root, index, report, source.answers_path, available)
            for output in reader._rows(stages[index - 1]["outputs"]):
                name = _path(output["path"])
                available[name] = attempt / "artifacts" / name
                if output["id_field"] is not None:
                    pipeline._coverage(
                        available[name],
                        cast(str, output["id_field"]),
                        tasks,
                        _object(report["artifacts"])[name],
                    )
        completed += 1
    if completed == 0 and "native-answers.jsonl" in reader.capture.entries:
        raise BaselineStateError("native answers precede sealed generation")
    for name in reader.capture.entries:
        if name.startswith("command-") and "/" not in name:
            token = name.removeprefix("command-").removesuffix(".json")
            index = int(token)
            canonical = name == "command-" + str(index) + ".json"
        elif name.startswith("staging/"):
            token = name.split("/", 2)[1]
            index = int(token)
            canonical = token == str(index)
        else:
            continue
        if not canonical or not 1 <= index <= min(completed, len(stages)):
            raise BaselineStateError("native preparation skips a sealed predecessor")
    found = {name for name in reader.capture.entries if name.startswith("completed/")}
    if found != {"completed/" + str(i) + ".json" for i in range(completed)}:
        raise BaselineStateError("reference contains a foreign or out-of-order stage seal")
    return completed


def inspect_references(
    plan: Path,
    *,
    expected_plan_sha256: str,
    input_bindings: dict[Path, str] | None = None,
) -> dict[str, object]:
    """Read all original owners, never create replacements, remove locks or spend.

    Ready means no observed custody stop, not execution approval or certification
    of accounts, current producer/runtime availability, prices or future capacity.
    """
    try:
        if not isinstance(plan, Path):
            raise BaselineStateError("reference state needs an explicit plan Path")
        path, digest = common._path(str(plan.absolute())), _digest(expected_plan_sha256)
        record = plain_comparison._plan(pipeline._read(path, digest))
        controls = {
            path: digest,
            **{common._path(p): d for p, d in record["consumer_sources"].items()},
            Path(__file__).absolute(): file_hash(Path(__file__).absolute()),
        }
        if input_bindings is not None:
            if type(input_bindings) is not dict or len(input_bindings) > 1024:
                raise BaselineStateError("reference controls need a bounded Path mapping")
            for source, pin in input_bindings.items():
                if not isinstance(source, Path):
                    raise BaselineStateError("reference controls need explicit Paths")
                source, pin = common._path(str(source.absolute())), _digest(pin)
                if source in controls and controls[source] != pin:
                    raise BaselineStateError("conflicting reference controls")
                controls[source] = pin
        if len(controls) > 1024:
            raise BaselineStateError("reference control inventory exceeds its boundary")
        references = cast(list[dict[str, Any]], record["references"])
        grants = {common._path(row["authorization"]) for row in references}
        if len(grants) != 1:
            raise BaselineStateError("reference modes need one shared original authority")
        authority = grants.pop()
        if authority in controls:
            raise BaselineStateError("mutable reference funding is not a frozen input")
        funding, funding_raw = common._snapshot(authority)
        if _object(funding["config"])["scope"] != reference_scope(digest):
            raise BaselineStateError("reference funding differs from the prospective plan")
        if funding["auth_acceptances"]:
            raise BaselineStateError("reference funding cannot inherit foreign paid history")
        readers, observations, missing = [], [], []
        definitions: dict[Path, str] = {}
        fresh_files: dict[Path, bytes] = {}

        def fresh_data(source: Path) -> bytes:
            raw = pipeline._read(source)
            if source in fresh_files and fresh_files[source] != raw:
                raise BaselineStateError("fresh reference inputs changed between reads")
            fresh_files[source] = raw
            return raw

        owners: dict[str, object] = {}
        for row in references:
            root, descriptor = common._path(row["directory"]), common._path(row["definition"])
            raw = pipeline._read(descriptor, row["sha256"])
            if descriptor in controls and controls[descriptor] != row["sha256"]:
                raise BaselineStateError("reference definition conflicts with explicit controls")
            definitions[descriptor] = _digest(row["sha256"])
            definition = _object(_load(raw), {"format", "tasks", "generation", "native", "stages"})
            if definition["format"] != "buddha.native-baseline.v1":
                raise BaselineStateError("unsupported plain reference definition")
            stage_count = len(_rows(definition["stages"])) + 1
            item: dict[str, object] = {
                "name": row["name"],
                "directory": str(root),
                "state": "fresh",
                "next_stage": 0,
                "completed_stages": 0,
                "owner_count": 0,
            }
            if _absent(root):
                generation = _object(definition["generation"])
                tasks_path = pipeline._absolute(definition["tasks"])
                tasks_raw = fresh_data(tasks_path)
                recipe_raw = fresh_data(pipeline._absolute(generation["descriptor"]))
                original, tasks, _ = baseline._definition(descriptor)
                if (
                    original != definition
                    or tasks.fingerprint() != TaskSet.from_bytes(tasks_raw).fingerprint()
                ):
                    raise BaselineStateError("fresh reference declaration changed during reading")
                selected, roots = baseline._component(generation)
                profiles = gateway._profiles(selected, roots)
                selection = selected.to_record()
                for relative in _object(selection["capabilities"]).values():
                    relative = _path(relative)
                    profile = roots["host"] / relative
                    expected = _object(_object(selection["components"])["host"])[relative]
                    if _sha(fresh_data(profile)) != expected:
                        raise BaselineStateError("fresh reference profile changed during reading")
                recipe = _frozen_recipe(
                    recipe_raw,
                    tasks_path,
                    {"profiles": profiles},
                )
                config = _object(recipe["config"])
                if config["sampling"] != row["name"] or config["instructions"] != "":
                    raise BaselineStateError("fresh plain reference changes its declared mode")
                missing.append(root)
                observations.append(item)
                continue
            reader = NativeEvidence(root, authority, error_type=BaselineStateError)
            original, tasks = baseline_results._context(reader, row["sha256"], complete=False)
            anchor = reader.owner(root / "owners/0")
            context = _load(reader.bound(anchor, root / "context.json"))
            if context["descriptor"] != str(descriptor) or original != definition:
                raise BaselineStateError("reference replaces its declared original definition")
            if _json(reader.funded) != _json(funding):
                raise BaselineStateError("shared reference funding changed during observation")
            for owner in reader.owners.values():
                if owner.run_id in owners:
                    raise BaselineStateError("reference owner identities are repeated")
                owners[owner.run_id] = owner
                for source, pin in controls.items():
                    if reader._bindings(owner).get(str(source)) != pin:
                        raise BaselineStateError("reference lacks an original prospective control")
                    if _sha(reader.capture.read(source, 256 * 1024**2)) != pin:
                        raise BaselineStateError("original reference control bytes changed")
            recipe = _frozen_recipe(
                reader.bound(
                    anchor, pipeline._absolute(_object(definition["generation"])["descriptor"])
                ),
                pipeline._absolute(definition["tasks"]),
                anchor.manifest,
            )
            if _object(recipe["config"])["sampling"] != row["name"]:
                raise BaselineStateError("plain reference mode differs from its generation recipe")
            completed = _prefix(reader, tasks)
            if "report.json" in reader.capture.entries:
                baseline_results.inspect_baseline(
                    root,
                    authorization=authority,
                    expected_report_sha256=_sha(reader.raw(root / "report.json")),
                    expected_definition_sha256=row["sha256"],
                )
                if completed != stage_count:
                    raise BaselineStateError("complete reference lacks all original stages")
                item["state"] = "complete"
            else:
                item["state"] = "prepared"
            item.update(
                next_stage=completed, completed_stages=completed, owner_count=len(reader.owners)
            )
            readers.append(reader)
            observations.append(item)
        funded = {str(row["run_id"]): row for row in _rows(funding["auth_runs"])}
        if set(funded) != set(owners) or any(row["historical"] != 0 for row in funded.values()):
            raise BaselineStateError(
                "shared grant has missing, foreign or replaced original owners"
            )
        reasons = []
        if any(
            name.rsplit("/", 1)[-1] in {"running.lock", ".trial-running.lock", ".search.lock"}
            for reader in readers
            for name in reader.capture.entries
        ):
            reasons.append("execution_lock_present")
        operations = _rows(funding["auth_operations"])
        if any(
            row["status"] == "completed"
            and _integer(row["actual_microusd"], "recorded charge")
            > _integer(row["reserve_microusd"], "reserved charge")
            for row in operations
        ):
            reasons.append("reservation_overrun")
        for status in ("dispatched", "unknown"):
            if any(row["status"] == status for row in operations):
                reasons.append(status + "_operations")
        inactive = {str(row["run_id"]) for row in _rows(funding["auth_deactivations"])}
        if any(
            owner.run_id in inactive
            and "completed/" + owner.directory.name + ".json" not in reader.capture.entries
            for reader in readers
            for owner in reader.owners.values()
        ):
            reasons.append("inactive_original_owner")
        files = {
            str(path): _sha(raw) for reader in readers for path, raw in reader.capture.raw.items()
        }
        for source, pin in (controls | definitions).items():
            if file_hash(source, max_bytes=256 * 1024**2) != pin:
                raise BaselineStateError("reference control changed during observation")
            files[str(source)] = pin
        for source, raw in fresh_files.items():
            if pipeline._read(source) != raw:
                raise BaselineStateError("fresh reference input changed during observation")
            files[str(source)] = _sha(raw)
        for reader in readers:
            reader.finish()
        common._finish_snapshot(authority, funding_raw, error=BaselineStateError)
        if any(not _absent(root) for root in missing):
            raise BaselineStateError("reference appeared during observation")
        financial = _summary(authority, cast(dict[str, Any], funding))
        states = [row["state"] for row in observations]
        state = (
            "complete"
            if all(s == "complete" for s in states)
            else "fresh"
            if all(s == "fresh" for s in states)
            else "prepared"
        )
        return _load(
            _json(
                {
                    "format": "buddha.reference-state.v1",
                    "state": state,
                    "ready": not reasons,
                    "blocked_reasons": reasons,
                    "references": observations,
                    "funding": financial,
                    "state_sha256": pipeline._sha(
                        {
                            "files": files | {str(authority): _sha(funding_raw)},
                            "trees": {
                                str(reader.root): reader.capture.entries for reader in readers
                            },
                            "absent": [str(root) for root in missing],
                        }
                    ),
                    "claim": "Original reference custody only; no funding approval, keys, writes, "
                    "retry, lock removal, account authentication or "
                    "runtime/capacity certification.",
                }
            )
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
        OverflowError,
        _Busy,
        _Unsupported,
    ):
        raise BaselineStateError(
            "original reference checks failed; retained records unchanged"
        ) from None
