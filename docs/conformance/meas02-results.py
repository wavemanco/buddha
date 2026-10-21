"""Read a frozen MEAS-02 study without keys, spending, locks or state changes.

Run once: --run STUDY --authorization DATABASE --out NEW-REPORT.json.
For an incomplete study, explicitly add --observation STUDY/observations/ID.json.
Only that observation's rows are credited; earlier unsealed attempts are not
combined. Output must be new and outside the study and component directories.
Ctrl+C stops reading. Exit 0 means a complete-input diagnostic,
3 a partial-input diagnostic, and 2 invalid/unavailable evidence. No API calls.
"""

import argparse
import hashlib
import itertools
import json
import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.doctor import _authority, _Busy, _Capture, _owner, _Unsupported  # noqa: E402
from buddha.ledger import _amount  # noqa: E402
from buddha.releases import _json, _load, _object, _path, _paths, verify_selection  # noqa: E402
from buddha.search_evidence import _absolute, _overlap, _read, _tree  # noqa: E402

CONTROLLER = Path(__file__).with_name("meas02-native-audit.py")
CONTROLLER_SHA256 = "ac7cddb5021507712206352cd95fc1264f061e55a3c5fa0b298b8428c5ca23f1"
REVIEW_HELPER = Path(__file__).with_name("meas01-pack.py")
REVIEW_SHA256 = "6328f94c4280c29992cbdd87c205e45950406c00f6af636d4392fb7a6777e4fc"
EXPECTATIONS_SHA256 = "9211231da884cdce93a9a9b0c486d7f582646a113623f0ba784177808c6571d8"
FINANCIALS = ("committed_microusd", "spent_microusd", "reserved_microusd", "operation_count")
MAX_ARTIFACT = 64 * 1024**2


class ResultsError(ValueError):
    """Frozen study evidence is unavailable, changing or inconsistent."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _engineering(path, expected):
    raw = _read(path, 1024**2)
    if sha(raw) != expected:
        raise ResultsError("reviewed engineering source differs")
    module = ModuleType("_meas02_results_" + path.stem.replace("-", "_"))
    module.__file__ = str(path)
    # Hash-bound first-party helpers only; no official, agent or archived code.
    exec(compile(raw, str(path), "exec"), module.__dict__)  # nosec B102
    return module


C = _engineering(CONTROLLER, CONTROLLER_SHA256)
REVIEW = _engineering(REVIEW_HELPER, REVIEW_SHA256)


def _bytes(capture, path, expected=None, maximum=32 * 1024**2):
    raw = capture.read(path, maximum)
    if expected is not None and sha(raw) != expected:
        raise ResultsError("referenced evidence bytes differ")
    return raw


def _record(capture, path, expected=None):
    return _object(_load(_bytes(capture, path, expected)))


def _expectations(capture, pack_raw):
    folder = ROOT / "docs/conformance/meas01-study"
    manifest = _record(capture, folder / "manifest.json")
    for name, digest in _object(manifest["files"]).items():
        _bytes(capture, ROOT / _path(name), digest)
    pack = _load(pack_raw)
    response = _bytes(capture, folder / "adjudicator-response.json")
    adjudication = _bytes(capture, folder / "adjudication.json")
    decisions = {case["item_id"]: case["status"] for case in _load(adjudication)["cases"]}
    selected = [item["id"] for item in pack["items"] if decisions[item["id"]] == "resolved"]
    exported = REVIEW.adjudicated_expectations(
        pack,
        [_bytes(capture, folder / f"review-{index}.json") for index in (1, 2)],
        response,
        adjudication,
        selected,
    )
    expected = _record(
        capture, ROOT / "tests/fixtures/meas01-expectations.json", EXPECTATIONS_SHA256
    )
    if exported != expected:
        raise ResultsError("resolved expectations differ from the frozen export")
    return exported


def _attempt(capture, directory, attempt, files, index, owner, command):
    attempt = _path(attempt)
    if not re.fullmatch(rf"attempts/{index}-(?:0|[1-9][0-9]*)", attempt):
        raise ResultsError("attempt belongs to a different occasion")
    files = _object(files)
    _paths(list(files))
    if not 1 <= len(files) <= 128:
        raise ResultsError("invalid bounded attempt inventory")
    _tree(directory / attempt, files, 512)
    total, blobs = 0, {}
    for name, digest in files.items():
        raw = _bytes(capture, directory / attempt / name, digest, MAX_ARTIFACT)
        total += len(raw)
        if total > 128 * 1024**2:
            raise ResultsError("attempt exceeds its byte ceiling")
        blobs[name] = raw
    report = _object(_load(blobs["report.json"])) if "report.json" in blobs else None
    if report is not None:
        if (
            report["format"] != "buddha.native-command-report.v1"
            or report["gateway_manifest_sha256"] != owner.manifest_sha256
            or report["descriptor_sha256"]
            != sha(_bytes(capture, directory / f"command-{index}.json"))
            or report["command_sha256"] != command["worker"]["command"]["sha256"]
        ):
            raise ResultsError("native report is not bound to this occasion")
        for name, digest in _object(report["artifacts"]).items():
            if files.get("artifacts/" + _path(name)) != digest:
                raise ResultsError("native artifact differs from its report")
    return report, blobs


def _sealed(capture, directory, index, expected, owner, authority, command, batch):
    seal = _record(capture, directory / f"completed/{index}.json", expected)
    if (
        set(seal) != {"format", "index", "owner_sha256", "attempt", "files"}
        or seal["format"] != "buddha.meas02-batch.v1"
        or type(seal["index"]) is not int
        or seal["index"] != index
        or seal["owner_sha256"] != owner.manifest_sha256
        or {
            row["reason"]
            for row in authority["auth_deactivations"]
            if row["run_id"] == owner.run_id
        }
        != {"MEAS02 completed: " + expected}
        or any(op.status != "completed" for op in owner.operations)
    ):
        raise ResultsError("completion lacks its original authority anchor")
    report, blobs = _attempt(
        capture, directory, seal["attempt"], seal["files"], index, owner, command
    )
    if (
        report is None
        or report["status"] != "complete"
        or report["worker"]["status"] != "complete"
        or type(report["execution"]["exit_code"]) is not int
        or report["execution"]["exit_code"] != 0
        or report["execution"]["cleanup_status"] != "removed"
    ):
        raise ResultsError("native completion lacks successful cleanup")
    raw = blobs["artifacts/v1.1/partitions.jsonl"]
    C._partition_ids(raw, batch, complete=True)
    return report, [_load(line) for line in raw.splitlines()]


def _captured_accounting(observation, owners, config):
    seen, spent, held = set(), 0, 0
    order = {
        state: index
        for index, state in enumerate(("reserved", "dispatched", "unknown", "completed"))
    }
    for row in observation["evidence"]["operations"]:
        index, identity = row["owner"], row["operation_id"]
        _amount(row["reserve_microusd"], "captured reservation")
        if row["actual_microusd"] is not None:
            _amount(row["actual_microusd"], "captured charge")
        if type(index) is not int or not 0 <= index < 4 or identity in seen:
            raise ResultsError("captured operation identity differs")
        seen.add(identity)
        matches = [op for op in owners[index].operations if op.operation_id == identity]
        if len(matches) != 1:
            raise ResultsError("captured operation is absent from its original owner")
        op = matches[0]
        if row["status"] not in order or order[row["status"]] > order[op.status]:
            raise ResultsError("captured state contradicts the retained transition")
        if (
            row["request_sha256"] != op.request_sha256
            or row["reserve_microusd"] != op.reserve_microusd
        ):
            raise ResultsError("captured request or reservation differs")
        if row["status"] == "completed":
            if op.status != "completed" or row["actual_microusd"] != op.actual_microusd:
                raise ResultsError("captured completed charge differs")
            receipt = op.receipt
            spent += op.actual_microusd
        else:
            if (
                row["status"] not in {"reserved", "dispatched", "unknown"}
                or row["actual_microusd"] is not None
            ):
                raise ResultsError("invalid captured liability")
            receipt = op.checkpoint
            held += op.reserve_microusd
            if row["status"] in {"reserved", "dispatched"} and row["receipt_sha256"] is not None:
                raise ResultsError("captured unsent/dispatched state cannot have a raw receipt")
        if row["receipt_sha256"] is not None and (
            receipt is None or sha(_json(receipt)) != row["receipt_sha256"]
        ):
            raise ResultsError("captured raw receipt differs")
    result = dict(zip(FINANCIALS, (spent + held, spent, held, len(seen)), strict=True))
    saved = observation["authorization"]
    for key in (*FINANCIALS, "budget_microusd", "max_calls"):
        _amount(saved[key], "captured " + key)
    if any(saved[key] != value for key, value in result.items()) or any(
        saved[key] != config[key]
        for key in ("authorization_id", "terms_sha256", "budget_microusd", "max_calls", "scope")
    ):
        raise ResultsError("captured accounting is inconsistent")
    return result


def _diagnostic(batches, expectations, measured):
    resolved = {case["item"]["id"]: case for case in expectations["cases"]}
    uncertain = set(expectations["unresolved_item_ids"])
    targets, occasions = [], []
    for batch in batches:
        occasion = {
            "occasion": batch["occasion"],
            "target_count": len(batch["targets"]),
            "measured_targets": 0,
            "missing_targets": 0,
            "resolved_targets": 0,
            "uncertain_targets": 0,
            "agreeing_relations": 0,
            "disagreeing_relations": 0,
            "uncertain_relations": 0,
            "missing_relations": 0,
        }
        for target in batch["targets"]:
            case = resolved.get(target["item_id"])
            if case is None and target["item_id"] not in uncertain:
                raise ResultsError("target has no frozen resolution status")
            expected = (
                None
                if case is None
                else {
                    answer: index
                    for index, group in enumerate(case["assessment"]["groups"])
                    for answer in group
                }
            )
            source, row = measured.get(target["target_id"], (None, None))
            answers = target["answer_ids_in_pack_order"]
            relations = []
            for left, right in itertools.combinations(range(len(answers)), 2):
                relation = (
                    None
                    if expected is None
                    else (
                        "equivalent"
                        if expected[answers[left]] == expected[answers[right]]
                        else "distinct"
                    )
                )
                actual = (
                    None
                    if row is None
                    else (
                        "equivalent"
                        if row["partition"][left] == row["partition"][right]
                        else "distinct"
                    )
                )
                outcome = (
                    "missing"
                    if row is None
                    else "uncertain"
                    if relation is None
                    else "agree"
                    if relation == actual
                    else "disagree"
                )
                relations.append(
                    {
                        "left": answers[left],
                        "right": answers[right],
                        "expected": relation,
                        "actual": actual,
                        "outcome": outcome,
                    }
                )
            counts = {
                name: sum(pair["outcome"] == outcome for pair in relations)
                for name, outcome in (
                    ("agreeing_relations", "agree"),
                    ("disagreeing_relations", "disagree"),
                    ("uncertain_relations", "uncertain"),
                    ("missing_relations", "missing"),
                )
            }
            for name, value in counts.items():
                occasion[name] += value
            expectation = "resolved" if case else "uncertain"
            measurement = "measured" if row is not None else "missing"
            occasion["resolved_targets" if case else "uncertain_targets"] += 1
            occasion["measured_targets" if row is not None else "missing_targets"] += 1
            targets.append(
                {
                    "target_id": target["target_id"],
                    "item_id": target["item_id"],
                    "occasion": batch["occasion"],
                    "kind": target["kind"],
                    "expectation": expectation,
                    "measurement": measurement,
                    "evidence": source,
                    "answer_ids_in_pack_order": list(answers),
                    "partition": None if row is None else row["partition"],
                    "relations": relations,
                    "counts": counts,
                }
            )
        occasions.append(occasion)
    return targets, occasions


def _analyze(directory, authorization, observation):
    if not isinstance(directory, Path) or not isinstance(authorization, Path):
        raise ResultsError("explicit study and authority Paths required")
    directory, authorization = (
        _absolute(str(directory.absolute())),
        _absolute(str(authorization.absolute())),
    )
    capture = _Capture(directory)
    if "running.lock" in capture.entries:
        raise ResultsError("study has a writer lock")
    _bytes(capture, CONTROLLER, CONTROLLER_SHA256)
    _bytes(capture, REVIEW_HELPER, REVIEW_SHA256)
    _bytes(capture, Path(__file__).resolve())
    if sorted(path.name for path in (directory / "owners").iterdir()) != ["0", "1", "2", "3"]:
        raise ResultsError("exactly four original owners required")
    names = {path.name for path in (directory / "completed").iterdir()}
    if len(names) > 4 or names != {f"{index}.json" for index in range(len(names))}:
        raise ResultsError("completion files are not the original ordered prefix")
    owners = [_owner(capture, directory / "owners" / str(index)) for index in range(4)]
    if len({owner.run_id for owner in owners}) != 4:
        raise ResultsError("owner identities repeat")
    authority = _authority(capture, authorization, owners)
    if {row["run_id"] for row in authority["auth_runs"]} != {owner.run_id for owner in owners}:
        raise ResultsError("authority includes a different study population")
    for owner in owners:
        auth_run = next(row for row in authority["auth_runs"] if row["run_id"] == owner.run_id)
        if (
            owner.manifest["authorization_path"] != str(authorization)
            or auth_run["historical"]
            or auth_run["runtime_sha256"] != owner.manifest["execution_sha256"]
        ):
            raise ResultsError("owner authority or execution binding differs")
    bindings = {item["path"]: item["sha256"] for item in owners[0].manifest["invocation"]["inputs"]}
    for path, digest in bindings.items():
        _bytes(capture, _absolute(path), digest)
    context = _record(capture, directory / "context.json")
    descriptor = _absolute(context["descriptor"])
    definition, sources, batches, selection, roots = C._definition(descriptor, bindings)
    bound, _ = C._files(directory, descriptor, definition, sources, batches, selection, roots)
    if any(
        str(path) not in bindings
        for path in bound
        if path.is_relative_to(directory) or path in [descriptor, *sources]
    ):
        raise ResultsError("materialized input lacks its original invocation binding")
    controllers = [path for path in bindings if Path(path).name == CONTROLLER.name]
    if len(controllers) != 1 or bindings[controllers[0]] != CONTROLLER_SHA256:
        raise ResultsError("owner did not bind the reviewed study controller")
    # Recorded original paths stay original, including when this reader lives in
    # a different checkout. Never relocate or execute any saved source bundle.
    for index, owner in enumerate(owners):
        if (
            owner.manifest["invocation"]["inputs"] != owners[0].manifest["invocation"]["inputs"]
            or owner.manifest["selection"] != selection.to_record()
            or owner.manifest["roots"] != definition["native"]["roots"]
            or owner.manifest["review"] != owners[0].manifest["review"]
            or owner.run_id != C._owner_id(directory, descriptor, index)
            or owner.manifest["settings"]
            != {key: definition["native"][key] for key in ("budget_microusd", "max_calls")}
        ):
            raise ResultsError("original owner inputs or selection differ")
    expectations = _expectations(capture, _bytes(capture, sources[0], bindings[str(sources[0])]))
    commands = [_record(capture, directory / f"command-{index}.json") for index in range(4)]
    measured, reports, captured = {}, [], None
    selected = None
    if observation is None:
        final = _record(capture, directory / "report.json")
        seals = _object(final["batch_seals"], {str(index) for index in range(4)})
        stopped_index, stored = 4, None
        scope = "complete"
    else:
        if not isinstance(observation, Path):
            raise ResultsError("selected observation must be a Path")
        observation = _absolute(str(observation.absolute()))
        if observation.parent != directory / "observations" or not re.fullmatch(
            r"[0-9a-f]{32}\.json", observation.name
        ):
            raise ResultsError("select one original observation filename")
        selected = observation.relative_to(directory).as_posix()
        stored = _record(capture, observation)
        stopped_index = stored["stopped_batch"]
        if (
            stored["format"] != "buddha.meas02-native-study-report.v1"
            or stored["status"] != "incomplete"
            or stored["result"] != "partial"
            or stored["input_kind"] != "supplied audit controls"
            or type(stored["target_count"]) is not int
            or stored["target_count"] != 40
            or stored["observation"] != selected
            or type(stopped_index) is not int
            or not 0 <= stopped_index < 4
            or stored["stopped_occasion"] != batches[stopped_index]["occasion"]
        ):
            raise ResultsError("partial observation identity differs")
        stop = _object(stored["stop"], {"reason", "codes", "native_reason", "execution_reason"})
        if (
            not isinstance(stop["codes"], list)
            or not stop["codes"]
            or len(stop["codes"]) != len(set(stop["codes"]))
            or any(
                not isinstance(value, str) or re.fullmatch(r"[a-z_]{1,64}", value) is None
                for value in [
                    stop["reason"],
                    *stop["codes"],
                    *(
                        stop[key]
                        for key in ("native_reason", "execution_reason")
                        if stop[key] is not None
                    ),
                ]
            )
        ):
            raise ResultsError("partial stop metadata is not a bounded reason code")
        seals = _object(stored["batch_seals"], {str(index) for index in range(stopped_index)})
        captured = _captured_accounting(stored, owners, authority["config"])
        scope = "partial"
    for index in range(stopped_index):
        report, rows = _sealed(
            capture,
            directory,
            index,
            seals[str(index)],
            owners[index],
            authority,
            commands[index],
            batches[index],
        )
        reports.append(report)
        measured.update({row["id"]: ("sealed", row) for row in rows})
    if scope == "complete":
        if final != C._result(reports, seals):
            raise ResultsError("complete report differs from its anchored batches")
    else:
        partial_ids, partial_status, partial_report = [], "unavailable", None
        attempt, files = stored["evidence"]["attempt"], _object(stored["evidence"]["files"])
        if attempt is None:
            if files:
                raise ResultsError("observation files lack an attempt")
        else:
            prefix = _path(attempt) + "/"
            if any(not name.startswith(prefix) for name in files):
                raise ResultsError("partial file belongs to a different attempt")
            partial_report, blobs = _attempt(
                capture,
                directory,
                attempt,
                {name[len(prefix) :]: digest for name, digest in files.items()},
                stopped_index,
                owners[stopped_index],
                commands[stopped_index],
            )
            present = [
                name
                for name in (
                    "artifacts/v1.1/partitions.jsonl",
                    "artifacts/v1.1/partitions.jsonl.partial",
                )
                if name in blobs
            ]
            if present:
                try:
                    if len(present) != 1:
                        raise ResultsError("ambiguous partial output")
                    raw = blobs[present[0]]
                    partial_ids = C._partition_ids(raw, batches[stopped_index], complete=False)
                    rows = [_load(line) for line in raw.splitlines()]
                    partial_status = "valid"
                except (ValueError, KeyError, TypeError):
                    rows, partial_ids, partial_status = [], [], "invalid"
                measured.update({row["id"]: ("selected_partial", row) for row in rows})
        if stored["batches"] != reports + ([partial_report] if partial_report else []):
            raise ResultsError("partial native report references differ")
        expected_ids = [target["target_id"] for batch in batches for target in batch["targets"]]
        sealed_ids = [
            identity for identity in expected_ids if measured.get(identity, (None,))[0] == "sealed"
        ]
        coverage = stored["coverage"]
        if (
            coverage["expected_count"] != 40
            or coverage["sealed_target_ids"] != sealed_ids
            or coverage["partial_target_ids"] != partial_ids
            or coverage["partial_status"] != partial_status
            or coverage["missing_target_ids"]
            != [identity for identity in expected_ids if identity not in measured]
        ):
            raise ResultsError("declared partial coverage differs from literal rows")
    targets, occasions = _diagnostic(batches, expectations, measured)
    verify_selection(selection, roots, expected_sha256=selection.fingerprint())
    capture.finish()
    result = {
        "format": "buddha.meas02-target-results.v1",
        "scope": scope,
        "study_status": "complete" if scope == "complete" else "incomplete",
        "result": scope,
        "selected_observation": selected,
        "recorded_stop": None if stored is None else stored["stop"],
        "targets": targets,
        "occasions": occasions,
        "current_accounting": authority["totals"],
        "captured_accounting": captured,
        "input_sha256": {str(path): sha(raw) for path, raw in capture.raw.items()},
        "limits": [
            "Frozen model-development relations, not ground truth or population accuracy.",
            "Dependent answers, pairs and contexts; no pooled accuracy is reported.",
            "Only the selected unsealed attempt is credited; earlier observations stay separate.",
            "Forty observed rows do not turn a partial input into complete execution.",
            "Partitions follow pack order; class numbers are arbitrary equality labels.",
            "Final partitions do not establish parser/repair behavior, invoices or authentication.",
            "No revised official scores, rankings, held-out improvement or human-validation claim.",
        ],
    }
    return _load(_json(result)), [directory, *roots.values()]


def analyze_results(directory, *, authorization, observation=None):
    """Return a fresh diagnostic; never acquire locks or resume a study."""
    try:
        return _analyze(directory, authorization, observation)[0]
    except (OSError, ValueError, KeyError, TypeError, RecursionError, _Busy, _Unsupported):
        raise ResultsError("study evidence is unavailable, changing or inconsistent") from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ResultsError("invalid result-reader options")


def main(argv=None):
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument("--run", type=Path, required=True)
        parser.add_argument("--authorization", type=Path, required=True)
        parser.add_argument("--observation", type=Path)
        parser.add_argument("--out", type=Path, required=True)
        args = parser.parse_args(argv)
        result, protected = _analyze(args.run, args.authorization, args.observation)
        output = args.out.absolute()
        if ".." in output.parts:
            raise ResultsError("output path cannot contain parent traversal")
        output = _absolute(str(output.parent)) / _path(output.name)
        if output.exists() or any(
            _overlap(output, _absolute(str(path.absolute()))) for path in protected
        ):
            raise ResultsError("output must be new and outside all protected directories")
        with output.open("xb") as stream:
            stream.write(
                (
                    json.dumps(
                        result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
                    )
                    + "\n"
                ).encode()
            )
        print(json.dumps({"status": "written", "scope": result["scope"]}), flush=True)
        return 0 if result["scope"] == "complete" else 3
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError, RecursionError, _Busy, _Unsupported):
        print(
            "Result evidence or output is invalid/unavailable; study unchanged.",
            file=sys.stderr,
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
