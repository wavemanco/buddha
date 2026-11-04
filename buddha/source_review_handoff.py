"""Write immutable review files from one surviving checked source observation."""

import os
import tempfile
from pathlib import Path
from typing import Any

from buddha import native_pipeline as pipeline
from buddha import source_review, source_review_results
from buddha.doctor import _Busy, _entries, _Unsupported
from buddha.native_evidence import NativeEvidence
from buddha.releases import MAX_JSON_BYTES, ReleaseError, _json, _root
from buddha.source_review import SourceReviewError, _sha, encode_review
from buddha.validation_study import _absolute, _list, _obj


def _publish(path: Path, raw: bytes) -> None:
    """Bound conflict reads; link a flushed new file without replacing anything.

    The existing search._atomic has unbounded conflict reads. This narrower
    publisher uses the same stdlib pattern with the review artifact ceiling.
    Unknown crash leftovers are retained, never swept or treated as resumable.
    """
    if len(raw) > MAX_JSON_BYTES:
        raise SourceReviewError("review artifact exceeds its byte ceiling")
    _root(path.parent)
    if path.exists() or path.is_symlink():
        pipeline._read(path, _sha(raw))
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".review-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            # Remove our own extra link before the regular-file check below.
            pass
    finally:
        Path(temporary).unlink()
    pipeline._read(path, _sha(raw))


def _check_tree(output: Path, expected: dict[str, bytes]) -> set[str]:
    """Accept only a bounded, plain, byte-identical prefix of the fixed layout."""
    if not output.exists() and not output.is_symlink():
        return set()
    _root(output)
    directories = {Path(name).parent.as_posix() for name in expected} - {"."}
    present = set()
    for name in _entries(output):
        if name in directories:
            _root(output / name)
        elif name in expected:
            pipeline._read(output / name, _sha(expected[name]))
            present.add(name)
        else:
            raise SourceReviewError("review output contains an unexpected artifact; retained")
    if "complete.json" in present and present != set(expected):
        raise SourceReviewError("published review output is missing artifacts; retained")
    return present


def _destination(
    output: Path,
    directory: Path,
    reader: NativeEvidence,
    controls: dict[Path, str],
    *,
    extra_roots: tuple[Path, ...] = (),
) -> Path:
    if not isinstance(output, Path):
        raise SourceReviewError("review output requires an explicit Path")
    output = _absolute(str(output.absolute()))
    roots = {directory.absolute(), reader.root, reader.capture.root}
    roots.update(extra_roots)
    roots.update(capture.root for capture in reader._retained)
    for owner in reader.owners.values():
        roots.update(Path(str(value)) for value in _obj(owner.manifest["roots"]).values())
    files = set(controls) | set(reader.capture.raw)
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in roots) or any(
        output.is_relative_to(path) or path.is_relative_to(output) for path in files
    ):
        raise SourceReviewError("review output overlaps original evidence or component roots")
    return output


def _save(output: Path, artifacts: dict[str, bytes], marker: bytes, reader: NativeEvidence) -> None:
    if any(len(raw) > MAX_JSON_BYTES for raw in (*artifacts.values(), marker)):
        raise SourceReviewError("review artifact exceeds its byte ceiling")
    expected = artifacts | {"complete.json": marker}
    present = _check_tree(output, expected)
    reader.finish()
    if "complete.json" not in present:
        output.mkdir(exist_ok=True)
        for parent in sorted({Path(name).parent for name in artifacts}):
            (output / parent).mkdir(exist_ok=True)
        for name, raw in artifacts.items():
            _publish(output / name, raw)
        # Source drift and unexpected output bytes must fail before publication.
        if _check_tree(output, expected) != set(artifacts):
            raise SourceReviewError("review output lost an artifact before publication")
        reader.finish()
        _publish(output / "complete.json", marker)
    _check_tree(output, expected)
    reader.finish()


def export_source_review(
    directory: Path,
    *,
    kind: str,
    expected_report_sha256: str,
    plan: Path,
    expected_plan_sha256: str,
    output: Path,
    reviewers: list[dict[str, str]],
) -> dict[str, object]:
    """Publish one checked pack and private round, without keys or provider calls.

    Bind this module and source_review_results as original custody evidence before
    preparing trial owners. The explicit roster is frozen before distribution;
    files alone prove neither publication time nor independent human review.
    Identical unmarked prefixes may resume. Completed publications are read-only.
    """
    try:
        _json(reviewers)
        if type(reviewers) is not list or not reviewers:
            raise SourceReviewError("review export requires an explicit reviewer roster")
        materialization, reader, controls = source_review._read_source_review(
            directory,
            kind=kind,
            expected_report_sha256=expected_report_sha256,
            plan=plan,
            expected_plan_sha256=expected_plan_sha256,
        )
        for module in (Path(__file__).absolute(), Path(source_review_results.__file__).absolute()):
            if module not in controls:
                raise SourceReviewError("review handoff helper lacks its original approval pin")
            source_review._bound(reader, controls, module, controls[module])
        output = _destination(output, directory, reader, controls)
        private: dict[str, Any] = materialization["private"]
        round_record = {
            "format": "buddha.source-review-round.v1",
            **{key: private[key] for key in ("plan_sha256", "report_sha256", "packet_sha256")},
            "reviewers": reviewers,
        }
        # Reuse the importer's exact round/roster rules; missing forms are expected.
        source_review_results._round_roster(materialization, round_record)
        artifacts = {
            "private/materialization.json": encode_review(private),
            "private/round.json": encode_review(round_record),
        }
        available = materialization["packet"] is not None
        if available:
            artifacts.update(
                {
                    "reviewer/pack.json": encode_review(materialization["packet"]),
                    "reviewer/response-template.json": encode_review(materialization["template"]),
                    "reviewer/review.md": materialization["review"].encode("utf-8"),
                }
            )
        marker = encode_review(
            {
                "format": "buddha.source-review-export.v1",
                "publication_status": "complete",
                "source_status": private["status"],
                "reason": private["reason"],
                "artifacts": {name: _sha(raw) for name, raw in artifacts.items()},
            }
        )
        _save(output, artifacts, marker, reader)
        return {
            "format": "buddha.source-review-export.v1",
            "status": private["status"],
            "publication_status": "complete",
            "output": str(output),
            "complete": {"path": str(output / "complete.json"), "sha256": _sha(marker)},
            "round_plan": {
                "path": str(output / "private/round.json"),
                "sha256": _sha(artifacts["private/round.json"]),
            },
            "reviewer_directory": str(output / "reviewer") if available else None,
        }
    except (
        ReleaseError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        _Busy,
        _Unsupported,
    ) as error:
        if isinstance(error, SourceReviewError):
            raise
        raise SourceReviewError(
            "review export refused; original and output files retained"
        ) from None


def collect_source_reviews(
    directory: Path,
    *,
    kind: str,
    expected_report_sha256: str,
    plan: Path,
    expected_plan_sha256: str,
    round_plan: Path,
    expected_round_plan_sha256: str,
    submissions: list[dict[str, str]],
    output: Path,
) -> dict[str, object]:
    """Save one private comparison of explicit forms, retaining missing/invalid rows.

    Additions or corrections require a fresh output directory. Keep original
    forms, prior collections and the frozen round; never rewrite them in place.
    This does not obtain reviews, verify identities or change official scores.
    """
    try:
        if not isinstance(round_plan, Path):
            raise SourceReviewError("review round requires an explicit Path")
        result, reader, controls = source_review_results._read_source_reviews(
            directory,
            kind=kind,
            expected_report_sha256=expected_report_sha256,
            plan=plan,
            expected_plan_sha256=expected_plan_sha256,
            round_plan=round_plan.absolute(),
            expected_round_plan_sha256=expected_round_plan_sha256,
            submissions=submissions,
        )
        module = Path(__file__).absolute()
        if module not in controls:
            raise SourceReviewError("review handoff helper lacks its original approval pin")
        source_review._bound(reader, controls, module, controls[module])
        round_path = Path(_obj(result["round_plan"])["path"])
        protected = {round_path.parent}
        if round_path.name == "round.json" and round_path.parent.name == "private":
            protected.add(round_path.parent.parent)
        for row in _list(result["reviews"]):
            submission = _obj(row)["submission"]
            if submission is not None:
                protected.add(Path(_obj(submission)["path"]).parent)
        output = _destination(output, directory, reader, controls, extra_roots=tuple(protected))
        result["consumed_files"] = reader.fingerprints()
        report = encode_review(result)
        marker = encode_review(
            {
                "format": "buddha.source-review-collection.v1",
                "publication_status": "complete",
                "review_status": result["status"],
                "reasons": result["reasons"],
                "artifacts": {"report.json": _sha(report)},
            }
        )
        _save(output, {"report.json": report}, marker, reader)
        return {
            "format": "buddha.source-review-collection.v1",
            "status": result["status"],
            "publication_status": "complete",
            "output": str(output),
            "complete": {"path": str(output / "complete.json"), "sha256": _sha(marker)},
            "report": {"path": str(output / "report.json"), "sha256": _sha(report)},
        }
    except (
        ReleaseError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        _Busy,
        _Unsupported,
    ) as error:
        if isinstance(error, SourceReviewError):
            raise
        raise SourceReviewError(
            "review collection refused; original and output files retained"
        ) from None
