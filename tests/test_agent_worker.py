"""Portable worker subprocess checks; OS confinement is proved separately with Docker."""

import base64
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buddha.agent_worker import AgentWorker, AgentWorkerError
from buddha.channel import read_frame, write_frame
from buddha.releases import _json, inventory
from buddha.wire import RawEnvelope

PROJECT = Path(__file__).resolve().parent.parent
RUNNER_FILES = ("__init__.py", "channel.py", "releases.py", "wire.py", "agent_worker.py")


class AgentWorkerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.roots = {name: self.root / name for name in ("agent", "runner")}
        self.roots["agent"].mkdir()
        (self.roots["runner"] / "buddha").mkdir(parents=True)
        self.seed = self.roots["agent"] / "frozen_seed.py"
        self.seed.write_bytes((PROJECT / "agents/frozen_seed.py").read_bytes())
        for name in RUNNER_FILES:
            (self.roots["runner"] / "buddha" / name).write_bytes(
                (PROJECT / "buddha" / name).read_bytes()
            )
        self.initial = {
            "type": "configure",
            "format": "buddha.agent-worker.v1",
            "roots": {name: str(path) for name, path in self.roots.items()},
            "inventories": {},
            "entrypoint": "frozen_seed.py",
            "agent_sha256": "",
            "config": {
                "provider": "openai",
                "model": "synthetic-seed-model",
                "max_output_tokens": 100,
                "instructions": "",
                "sampling": "regenerate",
            },
            "task": {"id": "selected", "prompt": "Literal task café 🌱.", "count": 2},
            "task_index": 0,
        }
        self.refresh()

    def refresh(self):
        self.initial["inventories"] = {name: inventory(path) for name, path in self.roots.items()}
        self.initial["agent_sha256"] = hashlib.sha256(
            _json(self.initial["inventories"]["agent"])
        ).hexdigest()

    def envelope(self, text=" same \n", *, provider=None, finish=None, **changes):
        provider = provider or self.initial["config"]["provider"]
        if provider == "openai":
            body = {
                "model": "synthetic-seed-model",
                "choices": [{"message": {"content": text}, "finish_reason": finish or "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        else:
            body = {
                "model": "synthetic-seed-model",
                "content": [{"type": "text", "text": text}],
                "stop_reason": finish or "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        return RawEnvelope(provider, 200, _json(body), **changes)

    def reply(self, sequence, envelope=None):
        return {
            "type": "response",
            "sequence": sequence,
            "envelope": (envelope or self.envelope()).to_record(),
        }

    def run_worker(self, replies=(), *, initial=None, execute_from=None, extra_launch="", env=None):
        payload = io.BytesIO()
        for frame in [initial if initial is not None else self.initial, *replies]:
            write_frame(payload, frame)
        cache = self.root / "absent-bytecode"
        launch = (
            (
                "import pathlib,sys\n"
                f"sys.path.insert(0,{str(execute_from or self.roots['runner'])!r})\n"
                "import buddha.agent_worker as worker\n"
                f"worker.ROOTS={self.roots!r}\n"
                f"worker.SCRATCH=pathlib.Path({str(self.root / 'scratch')!r})\n"
                f"worker.PYCACHE_PREFIX={str(cache)!r}\n"
                "sys.modules['__main__'].__file__=worker.__file__\n"
                + extra_launch
                + "\nworker.main()\n"
            )
            .replace("WindowsPath(", "pathlib.Path(")
            .replace("PosixPath(", "pathlib.Path(")
        )
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-X", f"pycache_prefix={cache}", "-c", launch],
            input=payload.getvalue(),
            capture_output=True,
            timeout=15,
            check=False,
            env=env,
        )
        stream, frames = io.BytesIO(completed.stdout), []
        while stream.tell() < len(completed.stdout):
            frames.append(read_frame(stream))
        return completed, frames

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

    def test_valid_two_and_ten_both_providers_modes_exact_frames_and_literal_answers(self):
        for provider in ("openai", "anthropic"):
            for sampling in ("regenerate", "in-context"):
                for count in (2, 10):
                    with self.subTest(provider=provider, sampling=sampling, count=count):
                        self.initial["config"] |= {"provider": provider, "sampling": sampling}
                        self.initial["task"]["count"] = count
                        process, frames = self.run_worker([self.reply(i) for i in range(count)])
                        self.assertEqual(process.returncode, 0, process.stderr.decode())
                        self.assertEqual(
                            frames[0],
                            {
                                "type": "ready",
                                "agent_sha256": self.initial["agent_sha256"],
                                "task_sha256": hashlib.sha256(
                                    _json(self.initial["task"])
                                ).hexdigest(),
                            },
                        )
                        requests = frames[1:-1]
                        self.assertEqual(len(requests), count)
                        for index, frame in enumerate(requests):
                            self.assertEqual(
                                set(frame), {"type", "sequence", "provider", "body_base64"}
                            )
                            self.assertEqual(
                                (frame["type"], frame["sequence"], frame["provider"]),
                                ("request", index, provider),
                            )
                            raw = base64.b64decode(frame["body_base64"], validate=True)
                            self.assertEqual(base64.b64encode(raw).decode(), frame["body_base64"])
                            body = json.loads(raw)
                            self.assertEqual(body["model"], "synthetic-seed-model")
                            self.assertEqual(
                                len(body["messages"]),
                                1 + (2 * index if sampling == "in-context" else 0),
                            )
                        self.assert_done(frames, "complete", "complete", [" same \n"] * count)

    def test_empty_refused_truncated_and_duplicate_answers_are_not_filtered(self):
        self.initial["task"]["count"] = 4
        replies = [
            self.reply(0, self.envelope(" \n")),
            self.reply(1, self.envelope("hidden", finish="content_filter")),
            self.reply(2, self.envelope("unfinished and", finish="length")),
            self.reply(3, self.envelope("unfinished and", finish="length")),
        ]
        process, frames = self.run_worker(replies)
        self.assertEqual(process.returncode, 0)
        self.assert_done(
            frames,
            "complete",
            "complete",
            ["[empty]", "[refused]", "unfinished and", "unfinished and"],
        )

    def test_only_one_sanitized_task_and_exact_configuration_are_accepted(self):
        bad = []
        for field, value in [
            ("dataset", "host-only"),
            ("release", {}),
            ("profiles", {}),
            ("task_index", True),
            ("task_index", -1),
            ("task_index", 2**31),
            ("agent_sha256", "0" * 64),
            ("entrypoint", "../frozen_seed.py"),
        ]:
            bad.append(self.initial | {field: value})
        bad.append(self.initial | {"task": self.initial["task"] | {"source": "host-only"}})
        bad.append(self.initial | {"config": self.initial["config"] | {"endpoint": "forbidden"}})
        bad.append(self.initial | {"roots": self.initial["roots"] | {"official": "/official"}})
        with patch("buddha.agent_worker.ROOTS", self.roots):
            AgentWorker(self.initial, io.BytesIO(), io.BytesIO())
            for record in bad:
                with self.subTest(record=record), self.assertRaises(AgentWorkerError):
                    AgentWorker(record, io.BytesIO(), io.BytesIO())

    def test_missing_drifted_and_wrong_loaded_runner_sources_fail_before_ready(self):
        self.seed.write_bytes(self.seed.read_bytes() + b"\n")
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")
        self.assertEqual(len(frames), 1)
        self.seed.unlink()
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")
        self.seed.write_bytes((PROJECT / "agents/frozen_seed.py").read_bytes())
        _, frames = self.run_worker(execute_from=PROJECT)
        self.assert_done(frames, "failed", "protocol")
        self.assertEqual(len(frames), 1)

    def test_selected_bytecode_extra_runner_files_and_active_cache_are_rejected(self):
        for relative in ("cached.pyc", "cached.pyo"):
            path = self.roots["agent"] / relative
            path.write_bytes(b"not executable")
            self.refresh()
            _, frames = self.run_worker()
            self.assert_done(frames, "failed", "protocol")
            path.unlink()
        self.refresh()
        (self.roots["runner"] / "buddha/forbidden.py").write_text("pass\n")
        self.refresh()
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")
        (self.roots["runner"] / "buddha/forbidden.py").unlink()
        self.refresh()
        (self.root / "absent-bytecode").mkdir()
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")

    def test_symlinked_source_is_rejected_even_when_expected_bytes_match(self):
        target = self.root / "outside.py"
        target.write_bytes(self.seed.read_bytes())
        self.seed.unlink()
        try:
            self.seed.symlink_to(target)
        except OSError:
            self.skipTest("host does not permit symlinks; actual container probe covers it")
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")

    def test_source_rechecked_before_first_and_second_requests_and_final_publication(self):
        original = self.seed.read_text(encoding="utf-8")
        for moment in ("before", "between", "after"):
            with self.subTest(moment=moment):
                self.seed.write_text(
                    original
                    + f"""
_original_generate = generate
def generate(task, config, complete):
    from pathlib import Path
    def change(): Path(__file__).write_text('changed')
    if {moment!r} == 'before': change()
    def wrapped(provider, body):
        value = complete(provider, body)
        if {moment!r} == 'between': change()
        return value
    result = _original_generate(task, config, wrapped)
    if {moment!r} == 'after': change()
    return result
""",
                    encoding="utf-8",
                )
                self.refresh()
                _, frames = self.run_worker([self.reply(0), self.reply(1)])
                self.assert_done(frames, "failed", "protocol")
                expected = {"before": 0, "between": 1, "after": 2}[moment]
                self.assertEqual(sum(frame["type"] == "request" for frame in frames), expected)

    def test_host_stops_escape_seed_without_another_request_or_partial_answers(self):
        for reason in ("authority", "unknown", "protocol", "cancelled"):
            with self.subTest(reason=reason):
                _, frames = self.run_worker(
                    [
                        self.reply(0),
                        {"type": "stop", "sequence": 1, "reason": reason},
                    ]
                )
                self.assert_done(frames, "stopped", reason)
                self.assertEqual(sum(frame["type"] == "request" for frame in frames), 2)

    def test_malformed_or_uncorrelated_host_frames_fail_without_retry(self):
        for frame in [
            self.reply(True),
            self.reply(1),
            self.reply(0) | {"extra": "forbidden"},
            {"type": "stop", "sequence": 0, "reason": "unknown private reason"},
            {"type": "stop", "sequence": 0, "reason": "authority", "extra": True},
            {"type": "unrecognized", "sequence": 0},
        ]:
            with self.subTest(frame=frame):
                _, frames = self.run_worker([frame])
                self.assert_done(frames, "failed", "protocol")
                self.assertEqual(sum(item["type"] == "request" for item in frames), 1)
        _, frames = self.run_worker()
        self.assert_done(frames, "failed", "protocol")

    def test_bad_raw_envelopes_json_or_provider_fail_as_protocol(self):
        invalid = [
            RawEnvelope("openai", 200, b"not JSON"),
            RawEnvelope("openai", 200, b'{"duplicate":1,"duplicate":2}'),
            RawEnvelope("openai", 429, b"{}"),
            self.envelope(provider="anthropic"),
            self.envelope(truncated=True),
            RawEnvelope("openai", 200, b"", withheld=True, received_sha256="0" * 64),
        ]
        for raw in invalid:
            with self.subTest(raw=raw):
                _, frames = self.run_worker([self.reply(0, raw)])
                self.assert_done(frames, "failed", "protocol")
                self.assertEqual(sum(item["type"] == "request" for item in frames), 1)

    def test_malformed_assistant_content_with_valid_usage_is_agent_error_not_empty(self):
        raw = json.loads(self.envelope().body)
        raw["choices"][0]["message"]["content"] = {"malformed": "private payload"}
        envelope = RawEnvelope("openai", 200, _json(raw))
        process, frames = self.run_worker([self.reply(0), self.reply(1, envelope)])
        self.assert_done(frames, "failed", "agent_error")
        self.assertNotIn(b"private payload", process.stdout + process.stderr)

    def test_agent_exception_system_exit_and_incomplete_answers_are_sanitized(self):
        for expression in [
            "raise ValueError('private payload')",
            "raise SystemExit('private payload')",
            "return ['partial']",
            "return ['literal', 1]",
            "return ['\\ud800', 'literal']",
        ]:
            with self.subTest(expression=expression):
                self.seed.write_text(f"def generate(task, config, complete):\n    {expression}\n")
                self.refresh()
                process, frames = self.run_worker()
                self.assert_done(frames, "failed", "agent_error")
                self.assertNotIn(b"private payload", process.stdout + process.stderr)

    def test_agent_cannot_choose_provider_or_submit_nonbytes_nonjson_or_excess_requests(self):
        cases = [
            "complete('anthropic', b'{}')",
            "complete('openai', '{}')",
            "complete('openai', b'[]')",
            "complete('openai', b'not json')",
            "complete('openai', b'x' * (16 * 1024**2 + 1))",
            "[complete('openai', b'{}') for _ in range(task['count'] + 1)]",
        ]
        for expression in cases:
            with self.subTest(expression=expression):
                self.seed.write_text(
                    f"def generate(task, config, complete):\n    return {expression}\n"
                )
                self.refresh()
                _, frames = self.run_worker([self.reply(0), self.reply(1)])
                self.assert_done(frames, "failed", "protocol")
                self.assertLessEqual(sum(item["type"] == "request" for item in frames), 2)

    def test_import_from_undeclared_source_fails_before_ready(self):
        self.seed.write_text("import external_fixture\ndef generate(*args): return ['x', 'x']\n")
        (self.root / "external_fixture.py").write_text("secret = 'private payload'\n")
        self.refresh()
        process, frames = self.run_worker(extra_launch=f"sys.path.insert(0,{str(self.root)!r})\n")
        self.assert_done(frames, "failed", "protocol")
        self.assertEqual(len(frames), 1)
        self.assertNotIn(b"private payload", process.stdout + process.stderr)

    def test_worker_environment_is_private_and_has_no_inherited_provider_credentials(self):
        self.seed.write_text("""import os
def generate(task, config, complete):
    assert 'OPENAI_API_KEY' not in os.environ
    assert 'ANTHROPIC_API_KEY' not in os.environ
    assert 'PRIVATE_AGENT_TEST' not in os.environ
    assert os.path.dirname(os.getcwd()) == os.path.dirname(os.environ['HOME'])
    assert os.path.basename(os.getcwd()) == 'work'
    return ['literal'] * task['count']
""")
        self.refresh()
        process, frames = self.run_worker(
            env=os.environ
            | {
                "OPENAI_API_KEY": "not-a-real-key",
                "ANTHROPIC_API_KEY": "not-a-real-key",
                "PRIVATE_AGENT_TEST": "private payload",
            }
        )
        self.assertEqual(process.returncode, 0)
        self.assert_done(frames, "complete", "complete", ["literal", "literal"])
        self.assertNotIn(b"private payload", process.stdout + process.stderr)

    def test_constructor_copies_configuration_before_external_mutation(self):
        initial = copy.deepcopy(self.initial)
        with patch("buddha.agent_worker.ROOTS", self.roots):
            worker = AgentWorker(initial, io.BytesIO(), io.BytesIO())
        initial["task"]["prompt"] = "changed outside the worker"
        initial["config"]["provider"] = "anthropic"
        self.assertNotEqual(worker.initial, initial)

    def test_host_stop_remains_latched_even_if_agent_catches_baseexception(self):
        self.seed.write_text("""def generate(task, config, complete):
    for _ in range(2):
        try: complete('openai', b'{}')
        except BaseException: pass
    return ['fabricated'] * task['count']
""")
        self.refresh()
        _, frames = self.run_worker([{"type": "stop", "sequence": 0, "reason": "unknown"}])
        self.assert_done(frames, "stopped", "unknown")
        self.assertEqual(sum(frame["type"] == "request" for frame in frames), 1)

    def test_keyboard_interrupt_exits_without_done_or_exception_payload(self):
        self.seed.write_text("def generate(*args): raise KeyboardInterrupt('private payload')\n")
        self.refresh()
        process, frames = self.run_worker()
        self.assertEqual(process.returncode, 130)
        self.assertEqual([frame["type"] for frame in frames], ["ready"])
        self.assertNotIn(b"private payload", process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
