"""Reconstruct this registered development study; no execution or authorization.

The intent and protocol are trusted repository inputs. Their publication before
outcomes must be established separately; their hashes do not authenticate time.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.answers import TaskSet  # noqa: E402
from buddha.native_pipeline import _read, _write  # noqa: E402
from buddha.policy_study import PolicyStudy  # noqa: E402
from buddha.releases import (  # noqa: E402
    MAX_JSON_BYTES,
    Release,
    ReleaseError,
    _json,
    _load,
    _object,
    _path,
    file_hash,
)


def build(intent_raw: bytes, dataset_raw: bytes, protocol_raw: bytes) -> PolicyStudy:
    if type(protocol_raw) is not bytes or len(protocol_raw) > MAX_JSON_BYTES:
        raise ReleaseError("study protocol must be bounded original bytes")
    intent = _object(
        _load(intent_raw), {"format", "protocol_sha256", "release", "study", "expected"}
    )
    if (
        intent["format"] != "buddha.policy-study-intent.v1"
        or hashlib.sha256(protocol_raw).hexdigest() != intent["protocol_sha256"]
    ):
        raise ReleaseError("study intent format or original protocol differs")
    release = Release.from_record(intent["release"])
    source = TaskSet.from_dataset(release, dataset_raw)
    record = _object(
        intent["study"],
        {
            "format",
            "split",
            "selected_ids",
            "child_policy",
            "generation",
            "generation_repeats",
            "judge_occasions",
            "execution_order",
        },
    )
    study = PolicyStudy.from_bytes(_json(record | {"source": source.to_record()}))
    actual = {
        "release_sha256": release.fingerprint(),
        "source_tasks_sha256": source.fingerprint(),
        "selected_tasks_sha256": study.tasks.fingerprint(),
        "study_sha256": study.fingerprint(),
        "arm_ids": [arm["arm_id"] for arm in study.arms],
        "cell_ids": [cell["cell_id"] for cell in study.schedule()],
    }
    if _json(intent["expected"]) != _json(actual):
        raise ReleaseError("reconstructed study differs from its registered identities")
    return study


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="sealed official source folder")
    parser.add_argument(
        "--intent", type=Path, default=Path(__file__).with_name("pol02-study-intent.json")
    )
    parser.add_argument("--protocol", type=Path, default=ROOT / "docs/POLICY-COMPARISON.md")
    parser.add_argument(
        "--output", type=Path, help="optional new local study file; never overwritten"
    )
    args = parser.parse_args()
    stage = "intent"
    try:
        raw = _read(args.intent)
        release = Release.from_record(_load(raw)["release"])
        stage = "source"
        for name, digest in _object(release.to_record()["source"]).items():
            if file_hash(args.source / name) != digest:
                raise ReleaseError("selected official source differs from the intent")
        dataset = str(_object(release.to_record()["task"])["dataset"])
        stage = "protocol/study"
        study = build(raw, _read(args.source / dataset), _read(args.protocol))
        if args.output is not None:
            stage = "output"
            _path(args.output.name)
            _write(args.output, study.to_bytes())
        print(
            json.dumps(
                {
                    "format": "buddha.policy-study-intent-check.v1",
                    "status": "checked",
                    "intent_sha256": hashlib.sha256(raw).hexdigest(),
                    "study_sha256": study.fingerprint(),
                    "selected_ids": [task.id for task in study.tasks.tasks],
                    "cells": len(study.schedule()),
                    "provider_calls": 0,
                    "authority_created": False,
                    "artifact_written": args.output is not None,
                }
            )
        )
        return 0
    except (ReleaseError, OSError, KeyError, TypeError):
        print(
            f"Study intent checks stopped at {stage}; no model execution was started.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
