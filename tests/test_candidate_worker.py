"""Portable protocol tests with reviewed literal fixtures; Docker proves confinement."""

import base64
import copy
import gzip
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buddha.candidate_worker import CandidateWorker, CandidateWorkerError
from buddha.channel import read_frame, write_frame
from buddha.releases import _json, inventory
from buddha.wire import RawEnvelope

PROJECT = Path(__file__).resolve().parent.parent
RUNNER_FILES = ("__init__.py", "channel.py", "releases.py", "wire.py", "candidate_worker.py")
LOCAL = b'def generate(task, config, complete):\n    return [" same \\n", ""]\n'
CALLS = """import json
def generate(task, config, complete):
    replies = []
    for i in range(CALL_COUNT):
        replies.append(complete(config["provider"], json.dumps({"ordinal": i}).encode()))
    return [str(len(replies)), replies[-1]["model"]]
"""


class CandidateWorkerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.roots = {name: self.root / name for name in ("agent", "runner")}
        self.roots["agent"].mkdir()
        (self.roots["runner"] / "buddha").mkdir(parents=True)
        for name in RUNNER_FILES:
            (self.roots["runner"] / "buddha" / name).write_bytes(
                (PROJECT / "buddha" / name).read_bytes()
            )
        self.source = self.roots["agent"] / "candidate.py"
        self.source.write_bytes(LOCAL)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.helper = self.runtime / "runtime-audit.py"
        self.helper.write_bytes(b'def collect_audit():\n    return {"fixture": "sealed runtime"}\n')
        self.manifest = self.runtime / "runtime-manifest.json"
        self.manifest.write_bytes(_json({"fixture": "sealed runtime"}) + b"\n")
        self.initial = {
            "type": "configure",
            "format": "buddha.candidate-worker.v1",
            "roots": {name: str(path) for name, path in self.roots.items()},
            "inventories": {},
            "entrypoint": "candidate.py",
            "agent_sha256": "",
            "config": {
                "provider": "openai",
                "model": "synthetic-candidate-model",
                "max_output_tokens": 100,
                "instructions": "Literal instructions café 🌱",
                "sampling": "regenerate",
            },
            "task": {"id": "selected", "prompt": "Literal task café 🌱.", "count": 2},
            "max_callbacks": 0,
            "runtime": {
                "sha256": hashlib.sha256(b"reviewed environment fixture").hexdigest(),
                "helper_sha256": hashlib.sha256(self.helper.read_bytes()).hexdigest(),
                "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            },
        }
        self.refresh()

    def refresh(self):
        self.initial["inventories"] = {name: inventory(path) for name, path in self.roots.items()}
        self.initial["agent_sha256"] = hashlib.sha256(
            _json(self.initial["inventories"]["agent"])
        ).hexdigest()

    def candidate(self, raw):
        self.source.write_bytes(raw if isinstance(raw, bytes) else raw.encode())
        self.refresh()

    def reply(self, sequence, *, provider=None, compressed=False):
        provider = provider or self.initial["config"]["provider"]
        raw = _json({"model": "synthetic-candidate-model", "literal": " preserved \n"})
        envelope = RawEnvelope(
            provider,
            200,
            gzip.compress(raw) if compressed else raw,
            headers=(("content-encoding", "gzip"),) if compressed else (),
        )
        return {"type": "response", "sequence": sequence, "envelope": envelope.to_record()}

    def run_worker(self, replies=(), *, initial=None, execute_from=None, extra_launch="", env=None):
        payload = io.BytesIO()
        for frame in [initial if initial is not None else self.initial, *replies]:
            write_frame(payload, frame)
        cache = self.root / "absent-bytecode"
        launch = (
            (
                "import pathlib,sys\n"
                f"sys.path.insert(0,{str(execute_from or self.roots['runner'])!r})\n"
                "import buddha.candidate_worker as worker\n"
                f"worker.ROOTS={self.roots!r}\n"
                f"worker.SCRATCH=pathlib.Path({str(self.root / 'scratch')!r})\n"
                f"worker.PYCACHE_PREFIX={str(cache)!r}\n"
                f"worker.RUNTIME_HELPER=pathlib.Path({str(self.helper)!r})\n"
                f"worker.RUNTIME_MANIFEST=pathlib.Path({str(self.manifest)!r})\n"
                + extra_launch
                + "\nworker.main()\n"
            )
            .replace("WindowsPath(", "pathlib.Path(")
            .replace("PosixPath(", "pathlib.Path(")
        )
        process = subprocess.run(
            [sys.executable, "-I", "-B", "-X", f"pycache_prefix={cache}", "-c", launch],
            input=payload.getvalue(),
            capture_output=True,
            timeout=15,
            check=False,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        stream, frames = io.BytesIO(process.stdout), []
        while stream.tell() < len(process.stdout):
            frames.append(read_frame(stream))
        return process, frames

    def assert_done(self, frames, status, reason, answers=None):
        self.assertTrue(frames)
        self.assertEqual(
            frames[-1],
            {
                "type": "done",
                "status": status,
                "reason": reason,
                "answers": [] if answers is None else answers,
            },
        )
        self.assertEqual(sum(frame["type"] == "done" for frame in frames), 1)

    def test_zero_callbacks_preserves_literal_empty_and_duplicate_answers(self):
        for answers in ([" same \n", ""], ["duplicate", "duplicate"], [" ten \n"] * 10):
            with self.subTest(answers=answers):
                self.initial["task"]["count"] = len(answers)
                self.candidate("def generate(task, config, complete):\n    return " + repr(answers))
                process, frames = self.run_worker()
                self.assertEqual(process.returncode, 0, process.stderr.decode())
                self.assertEqual(
                    frames[0],
                    {
                        "type": "ready",
                        "agent_sha256": self.initial["agent_sha256"],
                        "task_sha256": hashlib.sha256(_json(self.initial["task"])).hexdigest(),
                        "runtime_sha256": self.initial["runtime"]["sha256"],
                    },
                )
                self.assertEqual(len(frames), 2)
                self.assert_done(frames, "complete", "complete", answers)

    def test_one_and_many_callbacks_are_independent_of_answer_count(self):
        for provider in ("openai", "anthropic"):
            for count in (1, 3):
                with self.subTest(provider=provider, callbacks=count):
                    self.initial["config"]["provider"] = provider
                    self.initial["max_callbacks"] = count
                    self.candidate(CALLS.replace("CALL_COUNT", str(count)))
                    process, frames = self.run_worker([self.reply(i) for i in range(count)])
                    self.assertEqual(process.returncode, 0, process.stderr.decode())
                    requests = frames[1:-1]
                    self.assertEqual([r["sequence"] for r in requests], list(range(count)))
                    for request in requests:
                        self.assertEqual(
                            set(request), {"type", "sequence", "provider", "body_base64"}
                        )
                        self.assertEqual(request["provider"], provider)
                        raw = base64.b64decode(request["body_base64"], validate=True)
                        self.assertEqual(base64.b64encode(raw).decode(), request["body_base64"])
                    self.assert_done(
                        frames, "complete", "complete", [str(count), "synthetic-candidate-model"]
                    )

    def test_host_quota_stop_is_requested_and_latched_despite_candidate_catching_it(self):
        self.candidate("""def generate(task, config, complete):
    for i in range(2):
        try:
            complete(config["provider"], b"{}")
        except BaseException:
            pass
    return ["forged", "complete"]
""")
        for reason in ("quota", "unknown", "authority", "protocol", "cancelled"):
            with self.subTest(reason=reason):
                process, frames = self.run_worker(
                    [{"type": "stop", "sequence": 0, "reason": reason}]
                )
                self.assertEqual(process.returncode, 0)
                self.assertEqual([f["type"] for f in frames], ["ready", "request", "done"])
                self.assert_done(frames, "stopped", reason)

    def test_only_sanitized_task_configuration_and_exact_runtime_fields_are_accepted(self):
        records = []
        for field, value in (
            ("dataset", "host-only"),
            ("task_index", 0),
            ("max_callbacks", True),
            ("max_callbacks", -1),
            ("agent_sha256", "0" * 64),
            ("entrypoint", "../candidate.py"),
        ):
            records.append(self.initial | {field: value})
        records.extend(
            [
                self.initial | {"task": self.initial["task"] | {"dataset": "host-only"}},
                self.initial | {"task": self.initial["task"] | {"count": True}},
                self.initial | {"config": self.initial["config"] | {"endpoint": "forbidden"}},
                self.initial | {"config": self.initial["config"] | {"max_output_tokens": True}},
                self.initial | {"runtime": self.initial["runtime"] | {"path": "/foreign"}},
                self.initial | {"runtime": self.initial["runtime"] | {"sha256": "bad"}},
                self.initial | {"roots": self.initial["roots"] | {"official": "/official"}},
            ]
        )
        with patch("buddha.candidate_worker.ROOTS", self.roots):
            CandidateWorker(self.initial, io.BytesIO(), io.BytesIO())
            for record in records:
                with self.subTest(record=record), self.assertRaises(CandidateWorkerError):
                    CandidateWorker(record, io.BytesIO(), io.BytesIO())

    def test_runtime_helper_manifest_and_fresh_audit_are_checked_before_candidate(self):
        marker = self.root / "candidate-loaded"
        self.candidate(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('loaded')\n"
            "def generate(task, config, complete): return ['A', 'B']\n"
        )
        original_helper, original_manifest = self.helper.read_bytes(), self.manifest.read_bytes()
        for mode in ("helper_drift", "manifest_drift", "fresh_mismatch", "noncanonical"):
            with self.subTest(mode=mode):
                initial = copy.deepcopy(self.initial)
                self.helper.write_bytes(original_helper)
                self.manifest.write_bytes(original_manifest)
                if mode == "helper_drift":
                    self.helper.write_bytes(original_helper + b"\n")
                elif mode == "manifest_drift":
                    self.manifest.write_bytes(original_manifest + b"\n")
                elif mode == "fresh_mismatch":
                    self.helper.write_bytes(b"def collect_audit():\n    return {}\n")
                    initial["runtime"]["helper_sha256"] = hashlib.sha256(
                        self.helper.read_bytes()
                    ).hexdigest()
                else:
                    self.manifest.write_bytes(b'{ "fixture": "sealed runtime" }\n')
                    initial["runtime"]["manifest_sha256"] = hashlib.sha256(
                        self.manifest.read_bytes()
                    ).hexdigest()
                _, frames = self.run_worker(initial=initial)
                self.assert_done(frames, "failed", "protocol")
                self.assertEqual(len(frames), 1)
                self.assertFalse(marker.exists())

    def test_source_drift_missing_and_wrong_loaded_runner_origin_fail_before_ready(self):
        self.source.write_bytes(LOCAL + b"\n")
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")
        self.assertEqual(len(frames), 1)
        self.source.unlink()
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")
        self.source.write_bytes(LOCAL)
        _, frames = self.run_worker(execute_from=PROJECT)
        self.assert_done(frames, "failed", "protocol")
        self.assertEqual(len(frames), 1)

    def test_bytecode_extra_files_and_non_utf8_source_are_rejected(self):
        for name in ("candidate.pyc", "hidden.txt"):
            with self.subTest(name=name):
                path = self.roots["agent"] / name
                path.write_bytes(b"not selected executable source")
                self.refresh()
                _, frames = self.run_worker()
                self.assert_done(frames, "failed", "protocol")
                self.assertEqual(len(frames), 1)
                path.unlink()
        self.candidate(b"# invalid UTF8\n\xff")
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")

    def test_source_change_before_callback_prevents_request(self):
        self.candidate("""from pathlib import Path
def generate(task, config, complete):
    Path(__file__).write_text("changed source")
    complete(config["provider"], b"{}")
    return ["A", "B"]
""")
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")
        self.assertEqual([f["type"] for f in frames], ["ready", "done"])

    def test_bad_provider_or_nonobject_json_body_fails_before_request(self):
        for expression in (
            '"foreign", b"{}"',
            'config["provider"], "not bytes"',
            'config["provider"], b"{"',
            'config["provider"], b"[]"',
        ):
            with self.subTest(expression=expression):
                self.candidate(
                    "def generate(task, config, complete):\n"
                    f"    complete({expression})\n    return ['A', 'B']\n"
                )
                _, frames = self.run_worker()
                self.assert_done(frames, "failed", "protocol")
                self.assertEqual([f["type"] for f in frames], ["ready", "done"])
        self.candidate("""def generate(task, config, complete):
    complete(config["provider"], b'{"literal":"' + b'A' * 64 + b'"}')
    return ["A", "B"]
""")
        _, frames = self.run_worker(extra_launch="worker.MAX_BODY_BYTES=32\n")
        self.assert_done(frames, "failed", "protocol")
        self.assertEqual([f["type"] for f in frames], ["ready", "done"])

    def test_reply_correlation_bad_frames_and_body_errors_latch_protocol_failure(self):
        self.candidate("""def generate(task, config, complete):
    try:
        complete(config["provider"], b"{}")
    except Exception:
        pass
    return ["forged", "complete"]
""")
        malformed = [
            self.reply(True),
            self.reply(1),
            self.reply(0) | {"extra": True},
            {"type": "stop", "sequence": 0, "reason": "foreign"},
            self.reply(0, provider="anthropic"),
            {
                "type": "response",
                "sequence": 0,
                "envelope": RawEnvelope("openai", 200, b"not JSON").to_record(),
            },
        ]
        for response in malformed:
            with self.subTest(response=response):
                _, frames = self.run_worker([response])
                self.assert_done(frames, "failed", "protocol")
                self.assertEqual([f["type"] for f in frames], ["ready", "request", "done"])

    def test_complete_returns_decoded_literal_api_object_without_normalizing_content(self):
        self.candidate("""def generate(task, config, complete):
    value = complete(config["provider"], b"{}")
    return [value["literal"], value["model"]]
""")
        _, frames = self.run_worker([self.reply(0, compressed=True)])
        self.assert_done(
            frames, "complete", "complete", [" preserved \n", "synthetic-candidate-model"]
        )

    def test_wrong_count_nonliteral_answers_and_agent_exceptions_are_not_completed(self):
        for body in (
            "return ['one']",
            "return ['A', 2]",
            "return ('A', 'B')",
            "raise ValueError('secret diagnostic canary')",
            "raise SystemExit(0)",
        ):
            with self.subTest(body=body):
                self.candidate("def generate(task, config, complete):\n    " + body + "\n")
                process, frames = self.run_worker()
                self.assert_done(frames, "failed", "agent_error")
                self.assertNotIn(b"secret diagnostic canary", process.stdout + process.stderr)

    def test_private_environment_and_stdout_protocol_survive_candidate_noise(self):
        self.candidate("""import os
print("candidate noise")
def generate(task, config, complete):
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("credential exposure")
    return ["A", "B"]
""")
        process, frames = self.run_worker(
            env=dict(os.environ) | {"OPENAI_API_KEY": "offline-not-a-real-key"}
        )
        self.assert_done(frames, "complete", "complete", ["A", "B"])
        self.assertIn(b"candidate noise", process.stderr)
        self.assertNotIn(b"offline-not-a-real-key", process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
