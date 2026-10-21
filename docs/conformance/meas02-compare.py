"""Compare saved equivalence relations with explicit development judgments, in memory."""

import hashlib
import itertools
import json
import re


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty identity text required")
    return value


def _index(value):
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative integer required")
    return value


def _hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("answer SHA256 required")
    return value


def _groups(groups, members):
    if not isinstance(groups, list) or not groups:
        raise ValueError("complete explicit groups required")
    result = {}
    for index, group in enumerate(groups):
        if not isinstance(group, list) or not group:
            raise ValueError("nonempty group required")
        for member in group:
            _text(member)
            if member not in members or member in result:
                raise ValueError("unknown or repeated group member")
            result[member] = index
    if set(result) != set(members):
        raise ValueError("group coverage differs")
    return result


def _source(record):
    index = _index(record["original_index_0based"])
    digest = _hash(record["answer_utf8_sha256"])
    if "control_id" in record:
        if any(key in record for key in ("run_id", "candidate_id", "prompt_id")):
            raise ValueError("authored and historical scope mixed")
        control = _text(record["control_id"])
        return ("authored", control), index, f"authored:{control}:{index}", digest
    scope = ("historical", *(_text(record[key]) for key in ("run_id", "candidate_id", "prompt_id")))
    return scope, index, _text(record["reference_id"]), digest


def _provenance(items):
    if not isinstance(items, list) or not items:
        raise ValueError("complete provenance population required")
    indexed, opaque_ids, references, positions, full = {}, set(), {}, {}, {}
    for item in items:
        identity = _text(item["item_id"])
        if identity in indexed or item["status"] not in ("resolved", "uncertain"):
            raise ValueError("duplicate item or unknown resolution")
        kind = item["kind"]
        if kind not in ("historical_set", "historical_comparison", "authored_control"):
            raise ValueError("unknown source kind")
        sources = item["answer_sources"]
        if not isinstance(sources, dict) or not sources:
            raise ValueError("answer provenance required")
        parsed = {}
        for opaque, metadata in sources.items():
            _text(opaque)
            if opaque in opaque_ids:
                raise ValueError("repeated opaque answer ID")
            opaque_ids.add(opaque)
            source = _source(metadata)
            scope, index, reference, _ = source
            if reference in references and references[reference] != source:
                raise ValueError("source reference identity or text differs")
            if (scope, index) in positions and positions[scope, index] != source:
                raise ValueError("source position identity or text differs")
            references[reference], positions[scope, index] = source, source
            parsed[opaque] = source
        if len({source[2] for source in parsed.values()}) != len(parsed):
            raise ValueError("repeated source within one item")
        scopes = {source[0] for source in parsed.values()}
        authored = {scope[0] for scope in scopes} == {"authored"}
        if (kind == "authored_control") != authored or (
            kind != "authored_control" and any(scope[0] != "historical" for scope in scopes)
        ):
            raise ValueError("source kind differs")
        if kind in ("historical_set", "authored_control"):
            if len(scopes) != 1:
                raise ValueError("complete set mixes scopes")
            ordered = sorted(parsed.values(), key=lambda source: source[1])
            if [source[1] for source in ordered] != list(range(len(ordered))):
                raise ValueError("complete set index coverage differs")
            if kind == "historical_set":
                scope = ordered[0][0]
                if scope in full and full[scope] != ordered:
                    raise ValueError("full source population differs")
                full[scope] = ordered
        indexed[identity] = item, parsed
    for source in references.values():
        if source[0][0] == "historical" and (
            source[0] not in full or source not in full[source[0]]
        ):
            raise ValueError("historical comparison lacks full original scope")
    return indexed, full


def _rows(rows, full):
    if not isinstance(rows, list):
        raise ValueError("saved partition rows required")
    indexed = {}
    for row in rows:
        scope = (
            "historical",
            *(_text(row[key]) for key in ("run_id", "candidate_id", "prompt_id")),
        )
        if scope not in full or scope in indexed:
            raise ValueError("unknown or duplicate saved scope")
        expected = full[scope]
        references, hashes, labels = row["reference_ids"], row["answer_sha256"], row["partition"]
        if (
            not isinstance(references, list)
            or references != [source[2] for source in expected]
            or not isinstance(hashes, list)
            or hashes != [source[3] for source in expected]
            or not isinstance(labels, list)
            or len(labels) != len(expected)
        ):
            raise ValueError("saved source population, order or text differs")
        for label in labels:
            _index(label)
        indexed[scope] = labels, _hash(row["prompt_sha256"])
    return indexed


def _scope(scope):
    return dict(zip(("run_id", "candidate_id", "prompt_id"), scope[1:], strict=True))


def _compare(expectations, provenance_items, partition_rows):
    if expectations["format"] != "buddha.meas01-expectations.v1":
        raise ValueError("unsupported expectation format")
    provenance, full = _provenance(provenance_items)
    rows = _rows(partition_rows, full)
    cases, excluded = expectations["cases"], expectations["unresolved_item_ids"]
    if not isinstance(cases, list) or not isinstance(excluded, list):
        raise ValueError("explicit selected and unresolved populations required")
    if len(set(excluded)) != len(excluded) or set(excluded) != {
        identity for identity, (record, _) in provenance.items() if record["status"] == "uncertain"
    }:
        raise ValueError("uncertain item population differs")
    items, selected, unique = [], set(), {}
    for case in cases:
        item, assessment, adjudication = case["item"], case["assessment"], case["adjudication"]
        identity = _text(item["id"])
        if identity not in provenance or identity in selected:
            raise ValueError("unknown or duplicate selected item")
        record, sources = provenance[identity]
        if (
            record["status"] != "resolved"
            or adjudication["status"] != "resolved"
            or adjudication["item_id"] != identity
            or assessment["id"] != identity
            or assessment["uncertain_pairs"] != []
            or record.get("uncertain_pairs", []) != []
        ):
            raise ValueError("selected item is not explicitly resolved")
        selected.add(identity)
        prompt_hash = hashlib.sha256(_text(item["prompt"]).encode()).hexdigest()
        if record["kind"] != "authored_control" and any(
            source[0] in rows and rows[source[0]][1] != prompt_hash for source in sources.values()
        ):
            raise ValueError("selected historical prompt differs from saved task")
        answers = item["answers"]
        if not isinstance(answers, list) or len(answers) != len(sources):
            raise ValueError("selected answer population differs")
        public = []
        for answer in answers:
            opaque = _text(answer["id"])
            if opaque not in sources or opaque in public or not isinstance(answer["text"], str):
                raise ValueError("selected answer identity differs")
            if hashlib.sha256(answer["text"].encode()).hexdigest() != sources[opaque][3]:
                raise ValueError("selected answer text differs")
            public.append(opaque)
        expected = _groups(assessment["groups"], set(public))
        stated = _groups(record["groups"], {source[2] for source in sources.values()})
        scopes = {source[0] for source in sources.values()}
        candidate_scope = next(iter(scopes)) if len(scopes) == 1 else None
        if record["kind"] == "authored_control":
            status = "not_measured_no_saved_judgment"
        elif candidate_scope is None:
            status = "not_measured_cross_scope"
        elif candidate_scope not in rows:
            status = "not_measured_missing_saved_judgment"
        else:
            status = "compared"
        pairs = []
        for left, right in itertools.combinations(public, 2):
            relation = "equivalent" if expected[left] == expected[right] else "distinct"
            a, b = sources[left], sources[right]
            if (stated[a[2]] == stated[b[2]]) != (relation == "equivalent"):
                raise ValueError("selected judgment differs from frozen provenance")
            a, b = sorted((a, b), key=lambda source: (source[0], source[1]))
            saved = None
            if status == "compared":
                labels = rows[candidate_scope][0]
                saved = "equivalent" if labels[a[1]] == labels[b[1]] else "distinct"
            outcome = ("agree" if relation == saved else "disagree") if saved else status
            duplicate = False
            if candidate_scope is not None and record["kind"] != "authored_control":
                key = candidate_scope, a[1], b[1]
                duplicate = key in unique
                if not duplicate:
                    unique[key] = {
                        "scope": _scope(candidate_scope),
                        "references": [a[2], b[2]],
                        "expected_relations": set(),
                        "saved": saved,
                        "appearance_count": 0,
                    }
                unique[key]["expected_relations"].add(relation)
                unique[key]["appearance_count"] += 1
            pairs.append(
                {
                    "references": [a[2], b[2]],
                    "expected": relation,
                    "saved": saved,
                    "outcome": outcome,
                    "duplicate_appearance": duplicate,
                }
            )
        items.append(
            {
                "item_id": identity,
                "status": status,
                "source_references": [sources[opaque][2] for opaque in public],
                "pairs": pairs,
            }
        )
    if selected | set(excluded) != set(provenance) or selected & set(excluded):
        raise ValueError("selected item coverage differs")
    unique_pairs = []
    for key in sorted(unique):
        pair = unique[key]
        pair["expected_relations"] = sorted(pair["expected_relations"])
        pair["conflicting_expectations"] = len(pair["expected_relations"]) > 1
        pair["outcome"] = (
            "not_measured_missing_saved_judgment"
            if pair["saved"] is None
            else "conflicting_expectations"
            if pair["conflicting_expectations"]
            else "agree"
            if pair["saved"] == pair["expected_relations"][0]
            else "disagree"
        )
        unique_pairs.append(pair)
    statuses = (
        "compared",
        "not_measured_cross_scope",
        "not_measured_no_saved_judgment",
        "not_measured_missing_saved_judgment",
    )
    counts = {
        "resolved_items": len(items),
        "item_statuses": {
            status: sum(item["status"] == status for item in items) for status in statuses
        },
        "pair_appearances": sum(len(item["pairs"]) for item in items),
        "compared_pair_appearances": sum(
            len(item["pairs"]) for item in items if item["status"] == "compared"
        ),
        "unique_candidate_pairs": len(unique_pairs),
        "duplicate_pair_appearances": sum(pair["appearance_count"] - 1 for pair in unique_pairs),
        "unique_agreeing_pairs": sum(pair["outcome"] == "agree" for pair in unique_pairs),
        "unique_disagreeing_pairs": sum(pair["outcome"] == "disagree" for pair in unique_pairs),
        "unique_conflicting_pairs": sum(pair["conflicting_expectations"] for pair in unique_pairs),
        "unique_unmeasured_pairs": sum(pair["saved"] is None for pair in unique_pairs),
    }
    return {
        "format": "buddha.meas02-relation-comparison.v1",
        "items": items,
        "counts": counts,
        "unique_pairs": unique_pairs,
        "unresolved_item_ids": list(excluded),
        "limits": [
            "Saved class relations versus development judgments; no ground truth claim.",
            "Repeated pairs and source answers are dependent; counts are descriptive appearances.",
            "Cross-scope and authored cases have no saved within-candidate judgment here.",
            "Missing measurements and conflicting expectations remain explicit.",
            "No official score, ranking, head quality or financial record is changed.",
        ],
    }


def compare_resolved(expectations, provenance_items, partition_rows):
    """Return source-bound pair diagnostics without I/O, judging or a corrected score."""
    try:
        result = _compare(expectations, provenance_items, partition_rows)
        return json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (KeyError, IndexError, TypeError, AttributeError, UnicodeError, RecursionError) as error:
        raise ValueError("malformed saved relation comparison") from error
