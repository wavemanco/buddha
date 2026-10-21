"""Actual first-live handoff and keyless unknown-stop proof; synthetic HTTPS only."""

import sys

if not __debug__:
    raise RuntimeError("MEAS02_LIVE_PROBE_OPTIMIZED_MODE_UNSUPPORTED")

import argparse
import hashlib
import io
import json
import os
import shutil
import socket
import sqlite3
import tempfile
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha import executor  # noqa: E402
from buddha.authorization import Authorization  # noqa: E402
from buddha.gateway import Gateway  # noqa: E402
from buddha.native_run import NativeSession  # noqa: E402
from buddha.releases import Selection, _json, inventory, verify_selection  # noqa: E402
from buddha.wire import RawEnvelope  # noqa: E402

SCRIPT = Path(__file__).resolve()
CONFIGURATION = ROOT / "runs/meas02-live-20261020"
LIVE = SCRIPT.with_name("meas02-live.py")
LIVE_SHA256 = "c4c325c98ca0433e7ad77a7a86df0defb924a91a38112d54d5597bab527ff2d4"
RECIPE_SHA256 = "4461d0edd17e2ceab019b323f62305110293ecd5ac8b6be65b77d437a49b5acf"
KEY = "offline-live-launch-proof-not-a-real-key"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_live():
    raw = LIVE.read_bytes()
    assert sha(raw) == LIVE_SHA256
    module = ModuleType("_meas02_live_proof")
    module.__file__ = str(LIVE)
    exec(compile(raw, str(LIVE), "exec"), module.__dict__)  # nosec B102
    return module


class Terminal(io.StringIO):
    def isatty(self):
        return True


class Response:
    status = 200

    def __init__(self):
        self.calls = []
        self.raw = _json(
            {
                "id": "cmpl-offline-live-proof",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-5.6-luna",
                "service_tier": "default",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"groups": [[0], [1]]}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": "invalid", "completion_tokens": 1},
            }
        )

    def connect(self, host, **options):
        assert host == "api.openai.com" and options == {"timeout": 60.0}
        return self

    def request(self, method, path, *, body, headers):
        assert method == "POST" and path == "/v1/chat/completions"
        assert headers["Authorization"] == "Bearer " + KEY
        value = json.loads(body)
        assert value["model"] == "gpt-5.6-luna"
        assert value["response_format"]["json_schema"]["name"] == "Partition"
        assert "service_tier" not in value and "max_tokens" not in value
        self.calls.append({"body_sha256": sha(body), "model": value["model"]})
        assert len(self.calls) == 1

    def getresponse(self):
        return self

    def read(self, maximum):
        assert len(self.raw) < maximum
        return self.raw

    def getheaders(self):
        return [("content-type", "application/json"), ("x-request-id", "offline-live-proof")]

    def close(self):
        pass


def invoke(live, handoff, *, resumed=False):
    out, err = Terminal(), Terminal()
    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}),
        patch("buddha.__main__.sys.stdin.isatty", return_value=True),
        patch(
            "buddha.__main__.getpass.getpass",
            side_effect=AssertionError("resume prompted") if resumed else None,
            return_value=KEY,
        ) as hidden,
        redirect_stdout(out),
        redirect_stderr(err),
    ):
        code = live.main(
            ["--handoff", str(handoff), "--live", "--prompt-keys", "--confirm-project-key"]
        )
        assert os.environ["OPENAI_API_KEY"] == ""
    assert code == 3 and hidden.call_count == (0 if resumed else 1), err.getvalue()
    assert KEY not in out.getvalue() + err.getvalue()
    public = json.loads(out.getvalue())
    assert public["result"] == "partial" and public["reason"] == "unknown"
    return public


def main(output):
    assert not output.exists(), "proof output must be new"
    user_path = CONFIGURATION / "authorization.sqlite3"
    user_bytes = user_path.read_bytes()
    user_before = Authorization(user_path).summary()
    assert user_before["operation_count"] == 0 and user_before["runs"] == []
    original = (CONFIGURATION / "recipe.json").read_bytes()
    assert sha(original) == RECIPE_SHA256
    definition = json.loads(original)
    selection = Selection.from_bytes(_json(definition["native"]["selection"]))
    original_roots = {name: Path(path) for name, path in definition["native"]["roots"].items()}
    verify_selection(selection, original_roots, expected_sha256=selection.fingerprint())
    fixture = Path(
        tempfile.mkdtemp(prefix="meas02-live-launch-", dir=ROOT / "runs/reviews")
    ).resolve()
    roots = {name: fixture / "components" / name for name in original_roots}
    for name, path in roots.items():
        shutil.copytree(original_roots[name], path)
    verify_selection(selection, roots, expected_sha256=selection.fingerprint())
    definition["native"]["roots"] = {name: str(path) for name, path in roots.items()}
    descriptor = fixture / "recipe.json"
    descriptor.write_bytes(_json(definition))
    authority = Authorization.create(
        fixture / "authorization.sqlite3",
        authorization_id="synthetic-" + fixture.name,
        budget_microusd=15_000_000,
        max_calls=120,
        scope="offline first-live handoff engineering proof only; no live permission",
    )
    assert authority.path != user_path and authority.summary()["operation_count"] == 0
    live = load_live()
    operator = live._operator()
    controller = operator._controller()
    study = fixture / "study"
    files = {
        SCRIPT,
        LIVE,
        live.OPERATOR,
        descriptor,
        ROOT / "docs/conformance/meas02-live-approval.json",
        *(Path(definition[name]) for name in ("pack", "proposal", "provenance")),
        *controller._sources(),
        *(ROOT / "buddha").glob("*.py"),
    }
    sources = {str(path): sha(path.read_bytes()) for path in files}
    total = authority.summary()
    handoff = fixture / "handoff.json"
    handoff.write_bytes(
        _json(
            {
                "format": "buddha.meas02-live-handoff.v1",
                "study": str(study),
                "descriptor": str(descriptor),
                "review": str(fixture / "account-review.json"),
                "account_scope": "synthetic project-scoped key; Standard public PAYG; no overrides",
                "authorization": {
                    "path": str(authority.path),
                    "id": total["authorization_id"],
                    "terms_sha256": total["terms_sha256"],
                    "budget_microusd": 15_000_000,
                    "max_calls": 120,
                    "scope": total["scope"],
                },
                "source_sha256": sources,
            }
        )
    )
    response = Response()
    with (
        patch("http.client.HTTPSConnection", side_effect=response.connect),
        patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")),
        patch.object(executor, "run_container", wraps=executor.run_container) as containers,
    ):
        first = invoke(live, handoff)
    assert containers.call_count == 1 and len(response.calls) == 1
    observed = json.loads((study / first["observation"]).read_bytes())
    assert observed["coverage"]["partial_target_ids"] == []
    assert observed["coverage"]["sealed_target_ids"] == []
    assert len(observed["coverage"]["missing_target_ids"]) == 40
    assert observed["batches"][0]["execution"]["cleanup_status"] == "removed"
    totals = authority.summary()
    assert totals["operation_count"] == 1 and len(totals["runs"]) == 4
    assert totals["spent_microusd"] == 0 and totals["reserved_microusd"] == 755_400
    ledger = study / "owners/0/operations.sqlite3"
    with closing(sqlite3.connect(":memory:")) as db:
        db.deserialize(ledger.read_bytes())
        db.execute("PRAGMA query_only=ON")
        operations = db.execute("SELECT operation_id,status FROM operations").fetchall()
        receipts = db.execute("SELECT response_json FROM unknown_receipts").fetchall()
    assert len(operations) == 1 and operations[0][1] == "unknown" and len(receipts) == 1
    envelope = RawEnvelope.from_record(json.loads(receipts[0][0])["envelope"])
    assert envelope.body == response.raw and envelope.received_sha256 == sha(response.raw)
    before = inventory(study)
    financial_bytes = authority.path.read_bytes()
    with (
        patch("http.client.HTTPSConnection", side_effect=AssertionError("resume HTTPS")),
        patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")),
        patch.object(executor, "run_container", side_effect=AssertionError("resume container")),
        patch.object(NativeSession, "run", side_effect=AssertionError("resume worker")),
        patch.object(Gateway, "execute", side_effect=AssertionError("resume dispatch")),
        patch.object(Authorization, "create", side_effect=AssertionError("resume grant")),
    ):
        second = invoke(live, handoff, resumed=True)
    after = inventory(study)
    assert second["observation"] != first["observation"]
    assert after.keys() - before.keys() == {second["observation"]}
    assert all(after[name] == digest for name, digest in before.items())
    assert authority.summary() == totals and authority.path.read_bytes() == financial_bytes
    assert all(sha(Path(path).read_bytes()) == digest for path, digest in sources.items())
    verify_selection(selection, original_roots, expected_sha256=selection.fingerprint())
    verify_selection(selection, roots, expected_sha256=selection.fingerprint())
    user_after = Authorization(user_path).summary()
    assert user_after == user_before and user_path.read_bytes() == user_bytes
    assert (CONFIGURATION / "recipe.json").read_bytes() == original
    for name in after:
        assert KEY.encode() not in (study / name).read_bytes()
    assert KEY.encode() not in (fixture / "account-review.json").read_bytes()
    evidence = {
        "format": "buddha.meas02-live-launch-native-proof.v1",
        "status": "PASS",
        "source_sha256": {
            str(Path(path).relative_to(ROOT)): digest for path, digest in sources.items()
        },
        "fixture": fixture.relative_to(ROOT).as_posix(),
        "configuration_sha256": RECIPE_SHA256,
        "selection_sha256": selection.fingerprint(),
        "image_id": definition["native"]["executor"]["image_id"],
        "mocked_physical_sends": 1,
        "actual_provider_calls": 0,
        "real_credentials_used": False,
        "first_launch_hidden_entries": 1,
        "resumed_hidden_entries": 0,
        "actual_containers": 1,
        "temporary_key_environment_restored": True,
        "original_user_authority": {
            "before_operations": 0,
            "after_operations": 0,
            "sha256": sha(user_bytes),
            "bytes_unchanged": True,
        },
        "synthetic_authorization": totals,
        "raw_receipt": {
            "received_sha256": envelope.received_sha256,
            "retained_literal_bytes": len(envelope.body),
            "status": "unknown",
        },
        "first_public_result": first,
        "resumed_public_result": second,
        "first_observation": observed,
        "resumed_observation": json.loads((study / second["observation"]).read_bytes()),
        "existing_study_bytes_unchanged_on_resume": True,
        "requests": response.calls,
        "limits": [
            "Synthetic malformed usage, not a scientific judgment or provider billing fact.",
            "No real API call, account authentication or semantic audit result.",
        ],
    }
    with output.open("xb") as stream:
        stream.write((json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode())
    print(
        json.dumps({"status": "PASS", "output": str(output), "sha256": sha(output.read_bytes())}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)
