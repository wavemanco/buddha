"""Bounded worker wire, configured hooks and full-module execution checks."""

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from buddha.channel import ChannelError, read_frame, write_frame
from buddha.native_worker import NativeWorker, WorkerError
from buddha.releases import ReleaseError, inventory
from buddha.wire import RawEnvelope


class ChannelTests(unittest.TestCase):
    def test_exact_object_roundtrip_and_next_frame(self):
        stream = io.BytesIO()
        write_frame(stream, {"type": "x", "literal": "\n雪", "nested": [1, None, False]})
        write_frame(stream, {"type": "y"})
        stream.seek(0)
        self.assertEqual(
            read_frame(stream), {"type": "x", "literal": "\n雪", "nested": [1, None, False]}
        )
        self.assertEqual(read_frame(stream), {"type": "y"})

    def test_eof_missing_newline_invalid_utf8_and_nonobject_are_rejected(self):
        for raw in (b"", b"{}", b"\xff\n", b"[]\n", b"null\n", b"{'x':1}\n"):
            with self.subTest(raw=raw), self.assertRaises(ChannelError):
                read_frame(io.BytesIO(raw))

    def test_duplicates_nonfinite_and_excessive_nesting_are_rejected(self):
        for raw in (
            b'{"a":1,"a":2}\n',
            b'{"x":NaN}\n',
            b'{"x":Infinity}\n',
            b'{"x":1e999}\n',
            b'{"x":' + b"[" * 65 + b"0" + b"]" * 65 + b"}\n",
        ):
            with self.subTest(raw=raw[:60]), self.assertRaises(ChannelError):
                read_frame(io.BytesIO(raw))

    def test_read_bound_includes_newline_and_does_not_drain_unbounded_data(self):
        stream = io.BytesIO(b'{"x":0}\n' + b"z" * 100)
        with patch("buddha.channel.MAX_FRAME_BYTES", 8):
            self.assertEqual(read_frame(stream), {"x": 0})
            with self.assertRaises(ChannelError):
                read_frame(stream)
        self.assertLessEqual(stream.tell(), 17)
        with patch("buddha.channel.MAX_FRAME_BYTES", 7), self.assertRaises(ChannelError):
            read_frame(io.BytesIO(b'{"x":0}\n'))

    def test_write_rejects_bad_types_finite_limits_and_depth_before_output(self):
        nested = 0
        for _ in range(65):
            nested = [nested]
        for value in (
            [],
            {1: "key"},
            {"nested": {1: "key"}},
            {"x": (1,)},
            {"x": float("nan")},
            {"x": object()},
            {"x": nested},
        ):
            stream = io.BytesIO()
            with self.subTest(value_type=type(value)), self.assertRaises(ChannelError):
                write_frame(stream, value)
            self.assertEqual(stream.getvalue(), b"")
        with patch("buddha.channel.MAX_FRAME_BYTES", 2), self.assertRaises(ChannelError):
            write_frame(io.BytesIO(), {})

    def test_short_writes_complete_and_io_errors_are_sanitized(self):
        class Partial(io.BytesIO):
            def write(self, raw):
                return super().write(raw[:2])

        stream = Partial()
        write_frame(stream, {"x": 0})
        self.assertEqual(stream.getvalue(), b'{"x":0}\n')

        class Broken:
            def readline(self, bound):
                raise OSError("private payload")

            def write(self, raw):
                raise OSError("private payload")

        for operation in (lambda: read_frame(Broken()), lambda: write_frame(Broken(), {})):
            with self.assertRaises(ChannelError) as failed:
                operation()
            self.assertNotIn("private payload", str(failed.exception))

    def test_read_requires_actual_bytes_and_write_must_make_progress(self):
        class WrongRead:
            def readline(self, bound):
                return "{}\n"

        class NoProgress:
            def write(self, raw):
                return 0

        with self.assertRaises(ChannelError):
            read_frame(WrongRead())
        with self.assertRaises(ChannelError):
            write_frame(NoProgress(), {})


class NativeWorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.roots = {
            name: self.root / name
            for name in ("official", "runner", "environment", "inputs", "artifacts")
        }
        for path in self.roots.values():
            path.mkdir()
        self.prefix = "fixture_" + self.root.name.replace("-", "_")
        self.main_name, self.io_name, self.judge_name = (
            self.prefix + suffix for suffix in ("_main", "_io", "_judge")
        )
        self.put(
            "official",
            self.io_name + ".py",
            """import hashlib,json
def evaluation_key(row, config):
    return hashlib.sha256(json.dumps([row['prompt'],config],sort_keys=True).encode()).hexdigest()
async def run_cached(instances, output_file, key_field, config, compute, concurrency=1):
    rows=[]
    for row in instances:
        rows.append(dict(row,**await compute(row)))
    with open(output_file,'w') as stream:
        for row in rows: stream.write(json.dumps(row)+'\\n')
""",
        )
        self.put(
            "official",
            self.judge_name + ".py",
            """spy=None
async def judge(value):
    return {'identity':spy(), 'literal':value}
async def judge_call(value):
    return await judge(value)
""",
        )
        self.put(
            "official",
            self.main_name + ".py",
            f"""import json,sys
from {self.io_name} import run_cached
from {self.judge_name} import judge_call
async def main():
    with open(sys.argv[1]+'/partitions.jsonl') as stream:
        rows=[json.loads(line) for line in stream]
    async def compute(row):
        return await judge_call(row['generations'][0])
    await run_cached(rows,sys.argv[1]+'/scores.jsonl','score_key',{{'config':'actual'}},compute,1)
""",
        )
        self.put("runner", "identity.txt", "explicit unit fixture; not an installed runner\n")
        self.put("environment", "identity.txt", "explicit unit fixture; not an installed runtime\n")
        self.input = (
            b'{"id":1,"prompt":"same","generations":[""]}\n'
            b'{"id":"1","prompt":"same","generations":["poor"]}\n'
        )
        (self.roots["inputs"] / "partitions.jsonl").write_bytes(self.input)
        self.config = {
            "type": "configure",
            "format": "buddha.native-worker.v1",
            "command": {
                "index": 0,
                "module": self.main_name,
                "argv": [str(self.roots["artifacts"])],
                "sha256": "a" * 64,
            },
            "release_sha256": "b" * 64,
            "answers_sha256": "c" * 64,
            "roots": {name: str(path) for name, path in self.roots.items()},
            "inventories": {
                "official": inventory(self.roots["official"]),
                "runner": inventory(self.roots["runner"]),
                "environment": {
                    "helper_sha256": "d" * 64,
                    "manifest_sha256": "e" * 64,
                    "inventory": {
                        "identity.txt": {
                            "sha256": hashlib.sha256(
                                b"explicit unit fixture; not an installed runtime\n"
                            ).hexdigest(),
                            "bytes": 56,
                        }
                    },
                },
            },
            "inputs": [
                {
                    "source": "partitions.jsonl",
                    "destination": "partitions.jsonl",
                    "sha256": hashlib.sha256(self.input).hexdigest(),
                }
            ],
            "hooks": {
                "modules": [self.main_name, self.io_name, self.judge_name],
                "cache": {
                    "target": self.io_name + ":run_cached",
                    "key_target": self.io_name + ":evaluation_key",
                    "parameters": {
                        name: name
                        for name in (
                            "instances",
                            "output_file",
                            "key_field",
                            "config",
                            "compute",
                            "concurrency",
                        )
                    },
                    "id_field": "id",
                },
                "calls": [
                    {"target": self.judge_name + ":judge_call", "label": "judge_call"},
                    {"target": self.judge_name + ":judge", "label": "judge"},
                ],
                "sdk": [],
            },
        }
        self.addCleanup(
            lambda: [
                sys.modules.pop(name, None)
                for name in tuple(sys.modules)
                if name.startswith(self.prefix)
            ]
        )
        old_path = sys.path[:]
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))
        self.addCleanup(patch.stopall)
        self.import_audit = NativeWorker._audit_imports
        self.environment_audit = NativeWorker._environment
        patch("buddha.native_worker.WORKER_ROOTS", self.roots).start()
        patch("sys.pycache_prefix", "/__absent_bytecode_cache").start()
        # These are component fixtures. Installed-environment/full-module proof is
        # the separate actual confined runtime oracle, not this synthetic helper.
        patch.object(
            NativeWorker,
            "_environment",
            return_value=self.config["inventories"]["environment"]["inventory"],
        ).start()
        patch.object(
            NativeWorker, "_audit_imports", return_value={"fixture": {"kind": "unit-fixture"}}
        ).start()

    def put(self, role, name, text):
        (self.roots[role] / name).write_text(text, encoding="utf-8")

    def worker(self, config=None, reader=None):
        return NativeWorker(config or self.config, reader or io.BytesIO(), io.BytesIO())

    def frames(self, worker):
        stream = io.BytesIO(worker.writer.getvalue())
        result = []
        while stream.tell() < len(stream.getvalue()):
            result.append(read_frame(stream))
        return result

    async def test_bytecode_cache_isolation_is_required_before_official_imports(self):
        for prefix in (None, "/another_cache"):
            worker = self.worker()
            with patch("sys.pycache_prefix", prefix), self.assertRaises(WorkerError):
                worker.prepare()
            self.assertEqual(worker.modules, {})
            self.assertEqual(self.frames(worker), [])
        cache = str(self.root / "existing-cache")
        Path(cache).mkdir()
        worker = self.worker()
        with (
            patch("sys.pycache_prefix", cache),
            patch("buddha.native_worker.PYCACHE_PREFIX", cache),
            self.assertRaises(WorkerError),
        ):
            worker.prepare()
        self.assertEqual(worker.modules, {})
        self.assertEqual(self.frames(worker), [])

    async def test_original_module_aliases_compute_context_and_files(self):
        worker = self.worker()
        worker.prepare()
        sys.modules[self.judge_name].spy = worker.contexts.attempt
        await worker.run()
        frames = self.frames(worker)
        self.assertEqual(frames[0]["type"], "ready")
        aliases = {item["path"] for item in frames[0]["aliases"]}
        self.assertIn(self.main_name + ":run_cached", aliases)
        self.assertIn(self.main_name + ":judge_call", aliases)
        self.assertEqual(frames[-1]["status"], "complete")
        rows = [
            json.loads(line)
            for line in (self.roots["artifacts"] / "scores.jsonl").read_bytes().splitlines()
        ]
        self.assertEqual([row["literal"] for row in rows], ["", "poor"])
        self.assertNotEqual(rows[0]["identity"][0], rows[1]["identity"][0])
        files = [frame for frame in frames if frame["type"] == "file"]
        self.assertEqual([frame["path"] for frame in files], ["partitions.jsonl", "scores.jsonl"])
        self.assertTrue(all(frame["offset"] == 0 and frame["eof"] for frame in files))

    async def test_sync_summary_entrypoint_is_supported(self):
        source = self.roots["official"] / (self.main_name + ".py")
        source.write_text(
            "from pathlib import Path\nimport sys\ndef main():\n"
            " Path(sys.argv[1]+'/summary.json').write_text('{\"native\":true}')\n",
            encoding="utf-8",
        )
        self.config["inventories"]["official"] = inventory(self.roots["official"])
        self.config["hooks"] = {"modules": [self.main_name], "cache": None, "calls": [], "sdk": []}
        worker = self.worker()
        await worker.run()
        self.assertEqual(self.frames(worker)[-1]["status"], "complete")
        self.assertEqual(
            json.loads((self.roots["artifacts"] / "summary.json").read_bytes()), {"native": True}
        )

    def exit_worker(self, code, *, asynchronous):
        entry = "async def main():" if asynchronous else "def main():"
        source = (
            "from pathlib import Path\nimport sys\n" + entry + "\n"
            " Path(sys.argv[1]+'/partitions.jsonl.partial').write_bytes("
            "b'completed native row\\n')\n"
            f" raise SystemExit({code!r})\n"
        )
        self.put("official", self.main_name + ".py", source)
        self.config["inventories"]["official"] = inventory(self.roots["official"])
        self.config["hooks"] = {"modules": [self.main_name], "cache": None, "calls": [], "sdk": []}
        return self.worker()

    async def test_system_exit_zero_is_native_success_and_exports_artifacts(self):
        worker = self.exit_worker(0, asynchronous=False)
        await worker.run()
        self.assertEqual(self.frames(worker)[-1]["status"], "complete")
        self.assertEqual(self.frames(worker)[-1]["reason"], "complete")
        self.assertTrue(any(frame["type"] == "file" for frame in self.frames(worker)))

    async def test_system_exit_none_is_native_success(self):
        worker = self.exit_worker(None, asynchronous=True)
        await worker.run()
        self.assertEqual(self.frames(worker)[-1]["status"], "complete")

    async def test_system_exit_nonzero_is_native_failure_and_keeps_journal(self):
        worker = self.exit_worker(2, asynchronous=True)
        await worker.run()
        self.assertEqual(self.frames(worker)[-1]["status"], "failed")
        self.assertEqual(self.frames(worker)[-1]["reason"], "native_error")
        self.assertEqual(
            (self.roots["artifacts"] / "partitions.jsonl.partial").read_bytes(),
            b"completed native row\n",
        )

    async def test_source_style_incomplete_exit_is_native_failure(self):
        worker = self.exit_worker("1 eval dirs incomplete: /scratch/artifacts", asynchronous=True)
        await worker.run()
        self.assertEqual(self.frames(worker)[-1]["status"], "failed")
        self.assertEqual(self.frames(worker)[-1]["reason"], "native_error")
        paths = [frame["path"] for frame in self.frames(worker) if frame["type"] == "file"]
        self.assertIn("partitions.jsonl.partial", paths)

    async def test_system_exit_false_is_native_success(self):
        worker = self.exit_worker(False, asynchronous=True)
        await worker.run()
        self.assertEqual(self.frames(worker)[-1]["status"], "complete")

    async def test_system_exit_noninteger_zero_is_native_failure(self):
        worker = self.exit_worker(0.0, asynchronous=True)
        await worker.run()
        self.assertEqual(self.frames(worker)[-1]["status"], "failed")
        self.assertEqual(self.frames(worker)[-1]["reason"], "native_error")

    async def test_keyboard_interrupt_still_escapes_after_journal_export(self):
        self.exit_worker(None, asynchronous=True)
        source = self.roots["official"] / (self.main_name + ".py")
        source.write_bytes(
            source.read_bytes().replace(b"raise SystemExit(None)", b"raise KeyboardInterrupt()")
        )
        self.config["inventories"]["official"] = inventory(self.roots["official"])
        worker = self.worker()
        with self.assertRaises(KeyboardInterrupt):
            await worker.run()
        frames = self.frames(worker)
        self.assertEqual(frames[-1]["status"], "failed")
        self.assertTrue(any(frame["type"] == "file" for frame in frames))

    async def test_missing_hook_and_source_drift_fail_before_ready(self):
        self.config["hooks"]["calls"][0]["target"] = self.judge_name + ":absent"
        worker = self.worker()
        with self.assertRaises(WorkerError):
            worker.prepare()
        self.assertEqual(self.frames(worker), [])
        self.config["hooks"]["calls"][0]["target"] = self.judge_name + ":judge_call"
        self.put("official", self.judge_name + ".py", "# changed\n")
        with self.assertRaises(WorkerError):
            self.worker().prepare()

    async def test_input_hash_escape_and_unassigned_roots_fail(self):
        for change in (
            {"source": "../outside"},
            {"destination": "../outside"},
            {"sha256": "f" * 64},
        ):
            original = self.config["inputs"][0].copy()
            self.config["inputs"][0].update(change)
            with self.subTest(change=change), self.assertRaises(WorkerError):
                self.worker().prepare()
            self.config["inputs"][0] = original
        self.config["roots"]["official"] = str(self.root)
        with self.assertRaises(WorkerError):
            self.worker()

    async def test_stop_latches_exchange_and_preserves_partial_file(self):
        reader = io.BytesIO()
        write_frame(reader, {"type": "stop", "seq": 0, "reason": "unknown"})
        reader.seek(0)
        worker = self.worker(reader=reader)
        from buddha.native_context import NativeStop
        from buddha.native_transport import NativeRequest

        request = NativeRequest(
            "openai", "POST", "https://api.openai.com/v1/chat/completions", b"{}", (), "a" * 64, 0
        )
        for _ in range(2):
            with self.assertRaises(NativeStop) as stopped:
                await worker.exchange(request)
            self.assertEqual(stopped.exception.reason, "unknown")
        self.assertEqual(len(self.frames(worker)), 1)

    async def test_response_correlation_and_raw_replay(self):
        from buddha.native_context import NativeStop
        from buddha.native_transport import NativeRequest

        request = NativeRequest(
            "openai", "POST", "https://api.openai.com/v1/chat/completions", b"{}", (), "a" * 64, 0
        )
        envelope = RawEnvelope("openai", 200, b"raw", (("retry-after-ms", "7"),))
        reader = io.BytesIO()
        write_frame(reader, {"type": "response", "seq": 0, "envelope": envelope.to_record()})
        reader.seek(0)
        worker = self.worker(reader=reader)
        self.assertEqual(await worker.exchange(request), envelope)
        reader = io.BytesIO()
        write_frame(reader, {"type": "response", "seq": 1, "envelope": envelope.to_record()})
        reader.seek(0)
        with self.assertRaises(NativeStop):
            await self.worker(reader=reader).exchange(request)

    async def test_cache_identity_binds_output_namespace_and_config(self):
        worker = self.worker()
        worker.prepare()
        sys.modules[self.judge_name].spy = worker.contexts.attempt
        cached = sys.modules[self.io_name].run_cached

        async def compute(row):
            return await sys.modules[self.judge_name].judge_call("")

        identities = []
        for output, key, config in (
            ("a.jsonl", "score_key", {}),
            ("b.jsonl", "score_key", {}),
            ("a.jsonl", "other_key", {}),
            ("a.jsonl", "score_key", {"changed": True}),
        ):
            await cached(
                [{"id": "a", "prompt": "same"}],
                str(self.roots["artifacts"] / output),
                key,
                config,
                compute,
            )
            row = json.loads((self.roots["artifacts"] / output).read_text())
            identities.append(row["identity"][0])
        self.assertEqual(len(set(identities)), 4)
        with self.assertRaises(WorkerError):
            await cached(
                [{"id": True, "prompt": "same"}],
                str(self.roots["artifacts"] / "a.jsonl"),
                "score_key",
                {},
                compute,
            )
        with self.assertRaises(ValueError):
            await cached([], str(self.root / "escaped.jsonl"), "score_key", {}, compute)

    async def test_stopped_native_command_still_exports_partial_journal(self):
        source = self.roots["official"] / (self.main_name + ".py")
        source.write_text(
            "from pathlib import Path\nimport sys\nfrom buddha.native_context import NativeStop\n"
            "async def main():\n Path(sys.argv[1]+'/scores.jsonl.partial').write_bytes(b'kept')\n"
            " raise NativeStop('unknown')\n",
            encoding="utf-8",
        )
        self.config["inventories"]["official"] = inventory(self.roots["official"])
        worker = self.worker()
        await worker.run()
        frames = self.frames(worker)
        self.assertEqual((frames[-1]["status"], frames[-1]["reason"]), ("stopped", "unknown"))
        journal = next(frame for frame in frames if frame.get("path") == "scores.jsonl.partial")
        self.assertEqual(base64.b64decode(journal["data_base64"]), b"kept")

    async def test_file_chunks_are_bounded_sorted_and_limits_precede_output(self):
        worker = self.worker()
        data = b"x" * (64 * 1024 + 3)
        (self.roots["artifacts"] / "a.partial").write_bytes(data)
        (self.roots["artifacts"] / "z.empty").write_bytes(b"")
        worker._files()
        frames = self.frames(worker)
        self.assertEqual([frame["path"] for frame in frames], ["a.partial", "a.partial", "z.empty"])
        self.assertEqual([frame["offset"] for frame in frames], [0, 65536, 0])
        self.assertEqual([frame["eof"] for frame in frames], [False, True, True])
        self.assertEqual(b"".join(base64.b64decode(frame["data_base64"]) for frame in frames), data)
        blocked = self.worker()
        with patch("buddha.native_worker.MAX_FILE_BYTES", 3), self.assertRaises(WorkerError):
            blocked._files()
        self.assertEqual(self.frames(blocked), [])
        with patch("buddha.native_worker.MAX_FILES", 1), self.assertRaises(WorkerError):
            self.worker()._files()

    async def test_import_audit_rejects_unknown_origins_and_tracks_selected_file(self):
        worker = self.worker()
        module = ModuleType(self.main_name)
        module.__file__ = str(self.roots["official"] / (self.main_name + ".py"))
        with patch.dict(sys.modules, {self.main_name: module}, clear=True):
            result = self.import_audit(worker)
        self.assertEqual(result[self.main_name]["kind"], "official")
        outside = self.root / "outside.py"
        outside.write_text("# not selected", encoding="utf-8")
        module.__file__ = str(outside)
        with (
            patch.dict(sys.modules, {self.main_name: module}, clear=True),
            self.assertRaises(WorkerError),
        ):
            self.import_audit(worker)
        del module.__file__
        with (
            patch.dict(sys.modules, {self.main_name: module}, clear=True),
            self.assertRaises(WorkerError),
        ):
            self.import_audit(worker)

    async def test_final_audit_failure_does_not_drop_native_outputs(self):
        worker = self.worker()
        worker.prepare()
        sys.modules[self.judge_name].spy = worker.contexts.attempt
        with patch.object(worker, "_audit_imports", side_effect=WorkerError("late origin")):
            await worker.run()
        frames = self.frames(worker)
        self.assertEqual((frames[-1]["status"], frames[-1]["reason"]), ("failed", "protocol"))
        self.assertTrue(any(frame.get("path") == "scores.jsonl" for frame in frames))

    async def test_declared_image_synthetic_precedes_empty_namespace_path(self):
        self.config["inventories"]["environment"]["synthetic_modules"] = ["fixture.synthetic"]
        worker = self.worker()
        synthetic = ModuleType("fixture.synthetic")
        synthetic.__path__ = []
        with patch.dict(sys.modules, {"fixture.synthetic": synthetic}, clear=True):
            result = self.import_audit(worker)
        self.assertEqual(result["fixture.synthetic"], {"kind": "image-synthetic"})

    def derived_class(self):
        owner = (self.roots["environment"] / "derived.py").resolve()
        raw = (
            b"from types import ModuleType\nclass Derived(ModuleType):\n"
            b"    __file__ = 'relative-placeholder.py'\n"
            b"    def __init__(self):\n        super().__init__('fixture.derived')\n"
        )
        owner.write_bytes(raw)
        namespace = {"__name__": "fixture.owner", "__file__": str(owner)}
        exec(compile(raw, str(owner), "exec"), namespace)
        environment = self.config["inventories"]["environment"]
        environment["inventory"]["derived.py"] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
        environment["derived_modules"] = {
            "fixture.derived": {
                "kind": "class",
                "module": "fixture.owner",
                "qualname": "Derived",
                "owner": "derived.py",
            }
        }
        worker = self.worker()
        worker.expected_environment = environment["inventory"]
        return worker, namespace["Derived"], owner

    async def test_derived_class_matches_sealed_defining_namespace_without_dynamic_lookups(self):
        worker, cls, _ = self.derived_class()
        module = cls()
        with patch.dict(sys.modules, {"fixture.derived": module}, clear=True):
            result = self.import_audit(worker)
        self.assertEqual(result["fixture.derived"]["kind"], "image-derived-class")
        self.assertEqual(result["fixture.derived"]["owner"]["kind"], "environment")

    async def test_derived_class_fixture_resolves_alias_before_defining_and_sealing(self):
        environment = self.roots["environment"]
        (environment / "sub").mkdir()
        self.roots["environment"] = environment / "sub" / ".."
        self.config["roots"]["environment"] = str(self.roots["environment"])
        worker, cls, owner = self.derived_class()
        module = cls()
        with patch.dict(sys.modules, {"fixture.derived": module}, clear=True):
            result = self.import_audit(worker)
            self.assertEqual(result["fixture.derived"]["owner"]["path"], str(owner))
            self.assertEqual(owner, (environment / "derived.py").resolve())
            alias = str(self.roots["environment"] / "derived.py")
            initializer = cls.__init__
            code = initializer.__code__
            for changed in ("namespace", "code"):
                with self.subTest(changed=changed):
                    initializer.__globals__["__file__"] = str(owner)
                    initializer.__code__ = code
                    if changed == "namespace":
                        initializer.__globals__["__file__"] = alias
                    else:
                        initializer.__code__ = code.replace(co_filename=alias)
                    with self.assertRaises(WorkerError):
                        self.import_audit(worker)

    async def test_derived_class_rejects_impostor_reusing_constructor_and_owner_drift(self):
        worker, cls, owner = self.derived_class()
        impostor = type(
            "Derived",
            (cls,),
            {
                "__module__": "fixture.owner",
                "__init__": cls.__init__,
            },
        )
        with patch.dict(sys.modules, {"fixture.derived": impostor()}, clear=True):
            with self.assertRaises(WorkerError):
                self.import_audit(worker)
        owner.write_bytes(b"# changed sealed defining source\n")
        with patch.dict(sys.modules, {"fixture.derived": cls()}, clear=True):
            with self.assertRaises(WorkerError):
                self.import_audit(worker)

    async def test_exact_derived_source_rejects_drift_escape_and_undeclared_files(self):
        private = self.root / "private"
        private.mkdir()
        (private / "sub").mkdir()
        generated = private / "generated.py"
        raw = b"value = 'fixed generated source'\n"
        generated.write_bytes(raw)
        environment = self.config["inventories"]["environment"]
        owner_raw = (self.roots["environment"] / "identity.txt").read_bytes()
        environment["inventory"]["identity.txt"] = {
            "sha256": hashlib.sha256(owner_raw).hexdigest(),
            "bytes": len(owner_raw),
        }
        environment["derived_modules"] = {
            "fixture.generated": {
                "kind": "source",
                "root": str(private),
                "basename": "generated.py",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "owners": ["identity.txt"],
            }
        }
        worker = self.worker()
        worker.expected_environment = environment["inventory"]
        module = ModuleType("fixture.generated")
        module.__file__ = str(generated)
        module.__spec__ = type("Spec", (), {"origin": str(generated)})()
        with patch("buddha.native_worker.SAFE_ENV", {"TMPDIR": str(private)}):
            with patch.dict(sys.modules, {"fixture.generated": module}, clear=True):
                result = self.import_audit(worker)
            self.assertEqual(result["fixture.generated"]["kind"], "image-derived-source")
            for mutation in (
                "drift",
                "escape",
                "undeclared",
                "owner",
                "origin",
                "parent_alias",
                "dot_alias",
                "double_alias",
            ):
                with self.subTest(mutation=mutation):
                    generated.write_bytes(raw)
                    module.__file__ = str(generated)
                    module.__spec__.origin = str(generated)
                    if mutation == "drift":
                        generated.write_bytes(b"different generated source\n")
                    elif mutation == "escape":
                        escaped = self.root / "generated.py"
                        escaped.write_bytes(raw)
                        module.__file__ = module.__spec__.origin = str(escaped)
                    elif mutation == "undeclared":
                        worker.inventories["environment"]["derived_modules"] = {}
                    elif mutation == "owner":
                        (self.roots["environment"] / "identity.txt").write_bytes(b"drift")
                    elif mutation.endswith("_alias"):
                        middle = {
                            "parent_alias": "sub" + os.sep + "..",
                            "dot_alias": ".",
                            "double_alias": "",
                        }[mutation]
                        module.__file__ = module.__spec__.origin = (
                            str(private) + os.sep + middle + os.sep + "generated.py"
                        )
                    else:
                        module.__spec__.origin = "different-origin"
                    with patch.dict(sys.modules, {"fixture.generated": module}, clear=True):
                        with self.assertRaises(WorkerError):
                            self.import_audit(worker)
                    worker.inventories["environment"]["derived_modules"] = environment[
                        "derived_modules"
                    ]
                    (self.roots["environment"] / "identity.txt").write_bytes(owner_raw)

    async def test_artifact_hard_links_are_rejected_before_export(self):
        first = self.roots["artifacts"] / "first"
        first.write_bytes(b"native")
        try:
            os.link(first, self.roots["artifacts"] / "second")
        except OSError as error:
            self.skipTest("host cannot create a hard link: " + type(error).__name__)
        worker = self.worker()
        with self.assertRaises(WorkerError):
            worker._files()
        self.assertEqual(self.frames(worker), [])

    async def test_replaced_artifact_root_cannot_export_another_tree(self):
        worker = self.worker()
        self.roots["artifacts"].rmdir()
        try:
            os.symlink(self.roots["inputs"], self.roots["artifacts"], target_is_directory=True)
        except OSError as error:
            self.roots["artifacts"].mkdir()
            self.skipTest("host cannot create a directory link: " + type(error).__name__)
        with self.assertRaises(ReleaseError):
            worker._files()
        self.assertEqual(self.frames(worker), [])

    async def test_script_startup_creates_scratch_and_resets_safe_environment(self):
        self.roots["artifacts"].rmdir()
        repository = Path(__file__).resolve().parents[1]
        code = (
            (
                "import sys, pathlib, os\n"
                f"sys.path.insert(0,{str(repository)!r})\n"
                "from buddha import native_worker as worker\n"
                f"worker.WORKER_ROOTS={self.roots!r}\n"
                "class Probe:\n"
                " def __init__(self,config,reader,writer):self.writer=writer\n"
                " async def run(self):\n"
                "  worker.write_frame(self.writer,{'type':'probe','env':dict(os.environ)})\n"
                "worker.NativeWorker=Probe\nworker.main()\n"
            )
            .replace("WindowsPath(", "pathlib.WindowsPath(")
            .replace("PosixPath(", "pathlib.PosixPath(")
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", code],
            input=b"{}\n",
            capture_output=True,
            timeout=15,
            env={
                "UNAUTHORIZED_SECRET": "synthetic-secret",
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        frame = read_frame(io.BytesIO(result.stdout))
        self.assertTrue(self.roots["artifacts"].is_dir())
        self.assertNotIn("UNAUTHORIZED_SECRET", frame["env"])
        self.assertEqual(frame["env"]["HOME"], "/scratch/home")
        self.assertEqual(frame["env"]["OPENBLAS_NUM_THREADS"], "1")


if __name__ == "__main__":
    unittest.main()
