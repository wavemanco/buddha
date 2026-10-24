"""Passive source-review imports; declarations and disagreements stay explicit."""

from pathlib import Path
from typing import Any, cast

from buddha import source_review
from buddha.doctor import _Busy, _Unsupported
from buddha.releases import ReleaseError, _digest, _json, _load
from buddha.validation_study import _absolute, _list, _obj


def _text(value: object) -> str:
    # Compatibility with the frozen meas01 validator: rationales have no 4 KiB cap.
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty review text required")
    return value


def _validate_submission(pack: dict[str, Any], submission: dict[str, Any]) -> None:
    """Preserve the historical helper's schema; the original file stays unchanged.

    Ported from docs/conformance/meas01-pack.py, SHA256
    6328f94c4280c29992cbdd87c205e45950406c00f6af636d4392fb7a6777e4fc.
    Differential checks retain its grouping/coverage semantics. No adjudication.
    """
    if set(pack) != {"format", "rule", "items"} or pack["format"] != "buddha.meas01-pack.v1":
        raise ValueError("review pack fields differ")
    item_ids, all_answer_ids = set(), set()
    if not isinstance(pack["items"], list) or not pack["items"]:
        raise ValueError("review pack population required")
    for item in pack["items"]:
        if set(item) != {"id", "prompt", "answers"}:
            raise ValueError("review pack item fields differ")
        if _text(item["id"]) in item_ids:
            raise ValueError("duplicate pack item")
        item_ids.add(item["id"])
        _text(item["prompt"])
        if not isinstance(item["answers"], list) or not item["answers"]:
            raise ValueError("review pack answers required")
        for answer in item["answers"]:
            if set(answer) != {"id", "text"} or not isinstance(answer["text"], str):
                raise ValueError("review pack answer fields differ")
            if _text(answer["id"]) in all_answer_ids:
                raise ValueError("duplicate pack answer")
            all_answer_ids.add(answer["id"])
    if set(submission) != {"format", "pack_sha256", "reviewer", "items"}:
        raise ValueError("submission fields differ")
    if submission["format"] != "buddha.meas01-submission.v1" or submission[
        "pack_sha256"
    ] != source_review._sha(source_review.encode_review(pack)):
        raise ValueError("submission pack differs")
    reviewer = submission["reviewer"]
    if set(reviewer) != {"id", "type", "prior_exposure"}:
        raise ValueError("reviewer declaration required")
    for value in reviewer.values():
        _text(value)
    if reviewer["type"] not in ("human", "model"):
        raise ValueError("reviewer type required")
    expected = {item["id"]: item for item in pack["items"]}
    seen = set()
    for item in submission["items"]:
        if set(item) != {"id", "groups", "uncertain_pairs", "rationale", "answers"}:
            raise ValueError("review item fields differ")
        item_id = item["id"]
        if item_id not in expected or item_id in seen:
            raise ValueError("unknown or duplicate review item")
        seen.add(item_id)
        _text(item["rationale"])
        answer_ids = {answer["id"] for answer in expected[item_id]["answers"]}
        groups = item["groups"]
        if (
            not isinstance(groups, list)
            or not groups
            or any(not isinstance(group, list) or not group for group in groups)
        ):
            raise ValueError("explicit complete groups required")
        flattened = [answer for group in groups for answer in group]
        if len(flattened) != len(answer_ids) or set(flattened) != answer_ids:
            raise ValueError("groups must cover each answer once")
        if not isinstance(item["uncertain_pairs"], list):
            raise ValueError("uncertainty must be explicit")
        pairs = set()
        for pair in item["uncertain_pairs"]:
            if set(pair) != {"left", "right", "rationale"}:
                raise ValueError("uncertain pair fields differ")
            members = frozenset((pair["left"], pair["right"]))
            if len(members) != 2 or not members <= answer_ids or members in pairs:
                raise ValueError("invalid or duplicate uncertain pair")
            pairs.add(members)
            _text(pair["rationale"])
        rated = set()
        for answer in item["answers"]:
            if set(answer) != {
                "id",
                "compliance",
                "compliance_rationale",
                "craft_notes",
                "uncertainty",
            }:
                raise ValueError("answer assessment fields differ")
            if answer["id"] not in answer_ids or answer["id"] in rated:
                raise ValueError("unknown or duplicate answer assessment")
            rated.add(answer["id"])
            if answer["compliance"] not in ("complies", "violates", "uncertain"):
                raise ValueError("literal compliance required")
            _text(answer["compliance_rationale"])
            if any(not isinstance(answer[key], str) for key in ("craft_notes", "uncertainty")):
                raise ValueError("literal observation fields required")
        if rated != answer_ids:
            raise ValueError("answer assessments incomplete")
    if seen != set(expected):
        raise ValueError("review item coverage incomplete")


def validate_review_submission(packet: object, submission: object) -> None:
    """Validate bounded literal data with the frozen review schema, without I/O."""
    try:
        _json(packet)
        _json(submission)
        _validate_submission(_obj(packet), _obj(submission))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        raise source_review.SourceReviewError("invalid complete review submission") from error


def _round_roster(
    materialization: dict[str, Any],
    round_record: dict[str, Any],
) -> list[dict[str, Any]]:
    """Share the exact round identity and explicit roster rules with publication."""
    round_record = _obj(
        round_record, {"format", "plan_sha256", "report_sha256", "packet_sha256", "reviewers"}
    )
    private = materialization["private"]
    if round_record["format"] != "buddha.source-review-round.v1" or any(
        round_record[key] != private[key]
        for key in ("plan_sha256", "report_sha256", "packet_sha256")
    ):
        raise source_review.SourceReviewError("review round changes the original sample")
    roster = [_obj(row, {"id", "type"}) for row in _list(round_record["reviewers"])]
    identities = [_text(row["id"]) for row in roster]
    if (
        not roster
        or len(set(identities)) != len(roster)
        or any(row["type"] not in ("human", "model") for row in roster)
    ):
        raise source_review.SourceReviewError("review roster is empty, repeated or contradictory")
    return roster


def _summarize(
    materialization: dict[str, Any],
    round_record: dict[str, Any],
    submission_records: dict[str, tuple[dict[str, str], bytes]],
) -> dict[str, Any]:
    """Summarize already captured data; this alone does not establish source custody."""
    roster = _round_roster(materialization, round_record)
    if not set(submission_records) <= {row["id"] for row in roster}:
        raise source_review.SourceReviewError("review roster is empty, repeated or contradictory")
    private = materialization["private"]
    packet = materialization["packet"]
    coverage: dict[str, Any] = {
        "planned": len(roster),
        "valid": 0,
        "missing": 0,
        "invalid": 0,
        **{
            kind: {"planned": 0, "valid": 0, "missing": 0, "invalid": 0}
            for kind in ("human", "model")
        },
    }
    reviews: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    for reviewer in roster:
        identifier, kind = reviewer["id"], reviewer["type"]
        coverage[kind]["planned"] += 1
        entry = submission_records.get(identifier)
        ref = None if entry is None else entry[0]
        status = "missing"
        reason: str | None = "submission_not_supplied"
        response: dict[str, Any] | None = None
        if ref is not None and packet is None:
            status, reason = "invalid", "no_available_packet"
        elif entry is not None:
            try:
                response = cast(dict[str, Any], _load(entry[1]))
                validate_review_submission(packet, response)
                if any(response["reviewer"][key] != reviewer[key] for key in ("id", "type")):
                    raise ValueError("reviewer differs from declared round")
                status, reason = "valid", None
                valid.append(response)
            except (ValueError, TypeError, KeyError):
                status, reason, response = "invalid", "invalid_submission", None
        coverage[status] += 1
        coverage[kind][status] += 1
        reviews.append(
            {
                "reviewer": reviewer,
                "status": status,
                "reason": reason,
                "submission": ref,
                "response": response,
            }
        )
    by_item: dict[str, list[dict[str, Any]]] = {}
    for response in valid:
        for item in response["items"]:
            by_item.setdefault(item["id"], []).append(
                {
                    "reviewer_id": response["reviewer"]["id"],
                    "type": response["reviewer"]["type"],
                    **{
                        key: item[key]
                        for key in ("groups", "uncertain_pairs", "rationale", "answers")
                    },
                }
            )
    items = []
    for item in [] if packet is None else packet["items"]:
        compared = by_item.get(item["id"], [])
        partitions = {
            tuple(sorted(tuple(sorted(group)) for group in review["groups"])) for review in compared
        }
        compliance: dict[str, set[str]] = {}
        for review in compared:
            for answer in review["answers"]:
                compliance.setdefault(answer["id"], set()).add(answer["compliance"])
        items.append(
            {
                "id": item["id"],
                "reviews": compared,
                "partition_disagreement": len(partitions) > 1 if len(compared) > 1 else None,
                "compliance_disagreements": sorted(
                    key for key, values in compliance.items() if len(values) > 1
                ),
            }
        )
    reasons = []
    if private["status"] != "complete":
        reasons.append("source_sample_unavailable")
    if coverage["missing"]:
        reasons.append("missing_reviews")
    if coverage["invalid"]:
        reasons.append("invalid_reviews")
    return {
        "format": "buddha.source-review-report.v1",
        "status": "incomplete" if reasons else "complete",
        "reasons": reasons,
        "coverage": {"source": private["coverage"], "reviewers": coverage},
        "source": private,
        "reviews": reviews,
        "items": items,
        "claim": (
            "Declared review coverage and observations; no independence attestation, "
            "adjudication, gold labels, official-score change or scientific improvement claim."
        ),
    }


def inspect_source_reviews(
    directory: Path,
    *,
    kind: str,
    expected_report_sha256: str,
    plan: Path,
    expected_plan_sha256: str,
    round_plan: Path,
    expected_round_plan_sha256: str,
    submissions: list[dict[str, str]],
) -> dict[str, object]:
    """Reconstruct source custody and compare pinned complete review forms, read-only.

    Freeze the round roster before distribution. Pins prove identity, not timing,
    human authorship, prior exposure, independence or reviewer competence.
    Missing refs and malformed pinned forms remain explicit incomplete results;
    changing or contradictory evidence is a typed error.
    """
    try:
        if not isinstance(round_plan, Path):
            raise source_review.SourceReviewError("review round requires an explicit Path")
        path, digest = _absolute(str(round_plan)), _digest(expected_round_plan_sha256)
        _json(submissions)
        refs: dict[str, dict[str, str]] = {}
        paths: set[str] = set()
        hashes: set[str] = set()
        for value in _list(submissions):
            row = _obj(value, {"reviewer_id", "path", "sha256"})
            identifier = _text(row["reviewer_id"])
            if identifier in refs:
                raise source_review.SourceReviewError("duplicate submitted reviewer")
            ref = {"path": str(_absolute(row["path"])), "sha256": _digest(row["sha256"])}
            if ref["path"] in paths or ref["sha256"] in hashes:
                raise source_review.SourceReviewError("duplicate submitted response evidence")
            paths.add(ref["path"])
            hashes.add(ref["sha256"])
            refs[identifier] = ref
        materialization, reader, controls = source_review._read_source_review(
            directory,
            kind=kind,
            expected_report_sha256=expected_report_sha256,
            plan=plan,
            expected_plan_sha256=expected_plan_sha256,
        )
        module = Path(__file__).absolute()
        if module not in controls:
            raise source_review.SourceReviewError("review importer lacks its original approval pin")
        source_review._bound(reader, controls, module, controls[module])
        round_record = _load(reader.raw(path, digest))
        records = {
            identifier: (ref, reader.raw(Path(ref["path"]), ref["sha256"]))
            for identifier, ref in refs.items()
        }
        result = _summarize(materialization, round_record, records)
        result["round_plan"] = {"path": str(path), "sha256": digest}
        result["consumed_files"] = {
            str(path): source_review._sha(raw) for path, raw in reader.capture.raw.items()
        }
        _json(result)
        reader.finish()
        return cast(dict[str, object], result)
    except (
        ReleaseError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        UnicodeError,
        RecursionError,
        OverflowError,
        _Busy,
        _Unsupported,
    ) as error:
        if isinstance(error, source_review.SourceReviewError):
            raise
        raise source_review.SourceReviewError(
            "invalid source-review collection or original evidence"
        ) from None
