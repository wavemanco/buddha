"""Read-only configuration check for an unallocated initial source experiment.

Reuses the real source-search preparation validators without creating a grant,
owner or output. Identity checks do not establish live model access or pricing.
"""

from pathlib import Path
from typing import cast

from buddha import gateway, source_screen, source_search
from buddha import native_pipeline as pipeline
from buddha.releases import ReleaseError, _digest, _json, _load, _object, file_hash


class SourceHandoffError(ReleaseError):
    """The proposed source experiment differs from its pinned configuration."""


def _sources() -> list[Path]:
    return list(dict.fromkeys([*source_search._sources(), Path(__file__).absolute()]))


def check_source_handoff(path: Path, *, expected_sha256: str) -> dict[str, object]:
    """Check a new initial source experiment, without keys, databases or execution.

    A caller-trusted raw hash identifies the reviewed proposal. Up to 1,023
    regular-file control pins leave one slot for the proposal itself in the
    existing 1,024-input preparation boundary. Selected components retain their
    existing independent Selection inventories. No authority is inferred.
    """
    try:
        if not isinstance(path, Path):
            raise SourceHandoffError("an explicit proposal Path is required")
        path = pipeline._absolute(str(path.absolute()))
        expected_sha256 = _digest(expected_sha256)
        raw = pipeline._read(path, expected_sha256)
        record = _object(
            _load(raw),
            {
                "format",
                "seed_screen",
                "proposal_template",
                "spec",
                "expected_runtime_sha256",
                "source_sha256",
                "requested_terms",
            },
        )
        if record["format"] != "buddha.source-handoff.v1":
            raise SourceHandoffError("unsupported unallocated source proposal")
        pins = _object(record["source_sha256"])
        if not 1 <= len(pins) <= 1023:
            raise SourceHandoffError("source controls exceed the existing preparation boundary")
        aliases: set[Path] = set()
        for name, digest in pins.items():
            source = pipeline._absolute(name)
            if str(source) != name or source == path or source in aliases:
                raise SourceHandoffError("control paths have aliases or self-reference")
            aliases.add(source)
            _digest(digest)
        screen = source_screen.SourceScreen.from_bytes(_json(record["seed_screen"]))
        seed = screen.to_record()
        generation = _object(seed["generation"])
        if (
            seed["format"] != "buddha.source-screen.v2"
            or generation["entrypoint"] != "candidate.py"
            or seed["lineage"] is not None
        ):
            raise SourceHandoffError("initial proposal requires a prospective one-file seed")
        spec = source_search.SourceSearchSpec.from_bytes(_json(record["spec"]))
        template = source_search._template(record["proposal_template"])
        runtime_sha256 = _digest(record["expected_runtime_sha256"])
        # These are the same real validators used before source-search preparation.
        source_screen._configuration(screen, runtime_sha256)
        source_screen._configuration(
            source_search._template_screen(screen, template), runtime_sha256
        )
        gateway._core_sources()
        required = {str(source): file_hash(source) for source in _sources()}
        runtime = _object(generation["runtime"])
        required[str(pipeline._absolute(runtime["path"]))] = runtime_sha256
        if any(pins.get(name) != digest for name, digest in required.items()):
            raise SourceHandoffError("proposal omits or changes an installed helper or runtime pin")
        terms = _object(record["requested_terms"], {"budget_microusd", "max_calls"})
        for value in terms.values():
            gateway._amount(value, positive=True)
        source_screen._configuration(screen, runtime_sha256)
        source_screen._configuration(
            source_search._template_screen(screen, template), runtime_sha256
        )
        # Recheck controls after the final component reads, including every extra pin.
        for name, expected in pins.items():
            if file_hash(Path(name), max_bytes=256 * 1024**2) != expected:
                raise SourceHandoffError("reviewed source proposal input changed")
        if pipeline._read(path, expected_sha256) != raw:
            raise SourceHandoffError("source proposal changed during checking")
        tasks = screen.tasks.tasks
        maximum_screens = cast(int, spec.to_record()["iterations"]) + 1
        stages = cast(list[object], seed["stages"])
        result = {
            "format": "buddha.source-handoff-check.v1",
            "status": "configuration_checked",
            "seed_screen_sha256": screen.fingerprint(),
            "candidate_id": screen.candidate_id,
            "comparison_key": screen.comparison_key(),
            "spec_sha256": spec.fingerprint(),
            "planned": {
                "task_ids": [task.id for task in tasks],
                "maximum_candidate_screens": maximum_screens,
                "maximum_stage_owners": maximum_screens * len(tasks) * (1 + len(stages))
                + maximum_screens
                - 1,
            },
            "requested_terms": terms,
            "funding": {
                "status": "unallocated",
                "scope": "source screen: " + screen.comparison_key(),
            },
            "reviewed_bindings": dict(pins) | {str(path): expected_sha256},
            "limitations": [
                "Configuration consistency only; no authority, keys, database access or execution.",
                "Selected image records do not prove a locally running or available runtime.",
                "Profile bounds do not verify current prices, token capacity or account access.",
                "Stage-owner ceiling excludes recovery attempts; it is not an API-call estimate.",
                "No mutation-competence gate, semantic review or scientific improvement claim.",
            ],
        }
        return _load(_json(result))
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        raise SourceHandoffError(
            "unallocated source configuration is invalid; no execution prepared"
        ) from None
