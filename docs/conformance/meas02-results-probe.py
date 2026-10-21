"""Read actual retained synthetic native fixtures; no keys or provider calls."""

import sys

if not __debug__:
    raise RuntimeError("MEAS02_RESULTS_PROBE_OPTIMIZED_MODE_UNSUPPORTED")

import argparse
import hashlib
import io
import json
import socket
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.authorization import Authorization  # noqa: E402
from buddha.gateway import Gateway, RawHTTPTransport  # noqa: E402
from buddha.native_run import NativeSession  # noqa: E402
from buddha.releases import inventory  # noqa: E402

SOURCE = Path(__file__).with_name("meas02-results.py")
SOURCE_SHA256 = "a5c5ab7924b316a65645b33eb6aad466975c9e1cb26dd3e232a887736470effd"
NATIVE = Path(__file__).with_name("meas02-partial-native-proof.json")
NATIVE_SHA256 = "05559e8a1e9ce9d308f041524772de5564dc48e436f50899387e91c874548d38"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, expected):
    raw = path.read_bytes()
    assert sha(raw) == expected
    module = ModuleType("_meas02_results_smoke")
    module.__file__ = str(path)
    # Checked first-party engineering source only; no saved program executes.
    exec(compile(raw, str(path), "exec"), module.__dict__)  # nosec B102
    return module


def main(output):
    assert not output.exists() and output.parent.is_dir()
    probe_sha256 = sha(Path(__file__).read_bytes())
    native_raw = NATIVE.read_bytes()
    assert sha(native_raw) == NATIVE_SHA256
    native = json.loads(native_raw)
    fixture = ROOT / native["fixture"]
    before = inventory(fixture)
    reader = load(SOURCE, SOURCE_SHA256)
    destination = ROOT / "runs/reviews" / ("meas02-results-smoke-" + uuid.uuid4().hex)
    destination.mkdir()
    cases = [("complete", "ordinary", None, 40)]
    cases.append(("interrupted", "ordinary", native["interrupted_partial"]["path"], 0))
    cases.extend(
        (
            case["name"],
            case["name"],
            case["saved_partial"]["path"],
            0 if case["name"] == "unknown" else 1,
        )
        for case in native["controls"]
    )
    reports = []
    with (
        patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")),
        patch("http.client.HTTPSConnection", side_effect=AssertionError("HTTPS forbidden")),
        patch.object(Gateway, "__init__", side_effect=AssertionError("mutable Gateway forbidden")),
        patch.object(
            Authorization, "__init__", side_effect=AssertionError("mutable authority forbidden")
        ),
        patch.object(NativeSession, "run", side_effect=AssertionError("worker forbidden")),
        patch.object(
            RawHTTPTransport, "send_prepared", side_effect=AssertionError("send forbidden")
        ),
    ):
        for name, subdirectory, observation, count in cases:
            root = fixture / subdirectory
            arguments = [
                "--run",
                str(root / "study"),
                "--authorization",
                str(root / "authorization.sqlite3"),
                "--out",
                str(destination / (name + ".json")),
            ]
            if observation is not None:
                arguments.extend(["--observation", str(root / "study" / observation)])
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = reader.main(arguments)
            assert status == (0 if observation is None else 3), err.getvalue()
            path = destination / (name + ".json")
            report = json.loads(path.read_bytes())
            measured = sum(row["measurement"] == "measured" for row in report["targets"])
            assert len(report["targets"]) == 40 and measured == count
            assert sum(row["expectation"] == "resolved" for row in report["targets"]) == 23
            assert sum(row["expectation"] == "uncertain" for row in report["targets"]) == 17
            assert report["scope"] == ("complete" if observation is None else "partial")
            if observation is not None:
                assert report["study_status"] == "incomplete"
                assert (
                    report["recorded_stop"]["reason"]
                    == {
                        "interrupted": "interrupted",
                        "shared-budget": "money",
                        "unknown": "unknown",
                        "attempt-cap": "attempt_limit",
                    }[name]
                )
            if name == "interrupted":
                assert report["captured_accounting"]["operation_count"] == 1
                assert report["current_accounting"]["operation_count"] == 40
            reports.append(
                {
                    "name": name,
                    "exit_code": status,
                    "scope": report["scope"],
                    "measured": measured,
                    "missing": 40 - measured,
                    "report": path.relative_to(ROOT).as_posix(),
                    "sha256": sha(path.read_bytes()),
                    "occasions": report["occasions"],
                }
            )
        original = reader.analyze_results(
            fixture / "ordinary/study",
            authorization=fixture / "ordinary/authorization.sqlite3",
        )
        original["targets"][0]["partition"][0] = 99999
        again = reader.analyze_results(
            fixture / "ordinary/study",
            authorization=fixture / "ordinary/authorization.sqlite3",
        )
        assert again["targets"][0]["partition"][0] != 99999
    assert inventory(fixture) == before
    assert sha(SOURCE.read_bytes()) == SOURCE_SHA256
    assert sha(Path(__file__).read_bytes()) == probe_sha256
    result = {
        "format": "buddha.meas02-target-reader-native-proof.v1",
        "status": "PASS",
        "reader_sha256": SOURCE_SHA256,
        "probe_sha256": probe_sha256,
        "native_input": {"path": NATIVE.relative_to(ROOT).as_posix(), "sha256": NATIVE_SHA256},
        "source_fixture": fixture.relative_to(ROOT).as_posix(),
        "input_files_unchanged": len(before),
        "before_after_file_sha256_equal": True,
        "actual_provider_calls": 0,
        "keys_read": False,
        "state_or_authority_writes": 0,
        "new_reports_only": True,
        "defensive_result_replay": True,
        "cases": reports,
        "limits": [
            "Responses are mechanical shown-index parity, not semantic judgments.",
            "Disagreements are synthetic engineering outputs, not observed judge accuracy.",
            "No actual approved live grant, real run or credential is opened by this probe.",
        ],
    }
    with output.open("xb") as stream:
        stream.write((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"status": "PASS", "output": str(output), "sha256": sha(output.read_bytes())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)
