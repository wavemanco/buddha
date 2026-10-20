"""The host native session consumes real frozen Gateway authority; no network."""

import base64
import copy
import hashlib
import json
import os
import shutil
import subprocess
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import test_gateway as fixtures

import buddha.native_run as native_run
from buddha.executor import ExecutionResult, Limits
from buddha.gateway import GatewayCall
from buddha.native_run import NativeRunError, NativeSession
from buddha.provider import PendingOperation
from buddha.releases import Release, _json, inventory, prepare_selection
from buddha.wire import RawEnvelope


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class NativeSessionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture = fixtures.GatewayTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.package = Path(native_run.__file__).resolve().parent
        self.runner_names = (
            "__init__.py",
            "channel.py",
            "native_worker.py",
            "native_context.py",
            "native_transport.py",
            "releases.py",
            "wire.py",
        )
        (fixture.roots["runner"] / "identity.txt").unlink()
        package = fixture.roots["runner"] / "buddha"
        package.mkdir()
        for name in self.runner_names:
            shutil.copyfile(self.package / name, package / name)
        fixture.write("official", "src/evaluate.py", "def main():\n    pass\n")
        fixture.release_record["source"] = inventory(fixture.roots["official"])
        fixture.release_record["commands"] = [{"module": "src.evaluate", "argv": ["{artifacts}"]}]
        fixture.profiles["format"] = "buddha.gateway-profiles.v2"
        fixture.profiles["profiles"]["primary"].update(
            headers={"user-agent": ["synthetic-host-session/1.0"]}, account_headers={}
        )
        fixture.write("host", "profiles/openai.json", json.dumps(fixture.profiles))
        self.inputs = fixture.root / "native-inputs"
        self.inputs.mkdir()
        self.answer_file = self.inputs / "partitions.jsonl"
        self.answer_file.write_bytes(b'{"id":"a","generations":["poor"],"partition":[0]}\n')
        self.descriptor = fixture.root / "native-command.json"
        command = {"index": 0, "module": "src.evaluate", "argv": ["/scratch/artifacts"]}
        self.worker = {
            "type": "configure",
            "format": "buddha.native-worker.v1",
            "command": command | {"sha256": sha(_json(command))},
            "release_sha256": Release.from_record(fixture.release_record).fingerprint(),
            "answers_sha256": sha(self.answer_file.read_bytes()),
            "roots": {
                "official": "/official",
                "runner": "/runner",
                "environment": "/opt/venv",
                "inputs": "/inputs",
                "artifacts": "/scratch/artifacts",
            },
            "inventories": {
                "official": inventory(fixture.roots["official"]),
                "runner": inventory(fixture.roots["runner"]),
                "environment": {
                    "helper_sha256": "d" * 64,
                    "manifest_sha256": "e" * 64,
                    "inventory": {
                        "lib/python3.13/site-packages/fixture.py": {
                            "sha256": "f" * 64,
                            "bytes": 1,
                        },
                    },
                    "synthetic_modules": ["synthetic_fixture"],
                },
            },
            "inputs": [
                {
                    "source": "partitions.jsonl",
                    "destination": "partitions.jsonl",
                    "sha256": sha(self.answer_file.read_bytes()),
                }
            ],
            "hooks": {"modules": ["src.evaluate"], "cache": None, "calls": [], "sdk": []},
        }
        self.record = {
            "format": "buddha.native-command.v1",
            "worker": self.worker,
            "executor": {
                "image_id": "sha256:" + "a" * 64,
                "role": "evaluator",
                "mounts": [
                    ["/official", str(fixture.roots["official"])],
                    ["/runner", str(fixture.roots["runner"])],
                    ["/inputs", str(self.inputs)],
                ],
                "runner_entrypoint": "buddha/native_worker.py",
                "image_environment": [["PATH", "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin"]],
                "limits": asdict(Limits()),
                "docker_endpoint": "unix:///var/run/docker.sock",
            },
            "profiles": {"openai": {"test-model": "primary"}},
        }
        self.host_sources = [
            self.package / name for name in (*self.runner_names, "executor.py", "native_run.py")
        ]
        self.preparations = 0
        self.freeze()

    def freeze(self, *, omit=(), **changes):
        fixture = self.fixture
        self.descriptor.write_bytes(_json(self.record))
        fixture.selection = prepare_selection(
            Release.from_record(fixture.release_record),
            fixture.roots,
            capabilities={fixtures.CAPABILITY: "profiles/openai.json"},
        )
        self.preparations += 1
        bound = [self.descriptor, self.answer_file, *self.host_sources]
        self.directory = fixture.prepare(
            "native-" + str(self.preparations),
            input_files=[path for path in bound if path not in omit],
            **changes,
        )
        self.gateway = fixture.gateway(directory=self.directory)
        self.output = fixture.root / ("output-" + str(self.preparations))

    def session(self):
        session = NativeSession(self.gateway, descriptor=self.descriptor, output=self.output)
        self.addCleanup(session.close)
        return session

    def audit(self):
        return {
            "src.evaluate": {
                "kind": "official",
                "path": "/official/src/evaluate.py",
                "sha256": self.worker["inventories"]["official"]["src/evaluate.py"],
            }
        }

    def ready(self, session):
        return session.handle({"type": "ready", "aliases": [], "audit": self.audit()})

    def request(self, *, seq=0, logical_id=None, attempt=0, body=None):
        return {
            "type": "request",
            "seq": seq,
            "request": {
                "provider": "openai",
                "method": "POST",
                "url": "https://api.openai.com/v1/chat/completions",
                "body_base64": base64.b64encode(body or self.fixture.body).decode("ascii"),
                "headers": [["user-agent", "synthetic-host-session/1.0"]],
                "logical_id": logical_id or "b" * 64,
                "attempt": attempt,
            },
        }

    def file(self, path, body=b"native", *, offset=0, eof=True):
        return {
            "type": "file",
            "path": path,
            "offset": offset,
            "data_base64": base64.b64encode(body).decode("ascii"),
            "eof": eof,
        }

    def done(self, *, status="complete", reason="complete"):
        return {"type": "done", "status": status, "reason": reason, "audit": self.audit()}

    def send(self, session, frame=None, *, connection=None):
        connection = connection or self.fixture.connection()
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            return session.handle(frame or self.request())

    def test_frozen_descriptor_and_all_actual_host_modules_are_required_before_output(self):
        for path in [self.descriptor, self.answer_file, *self.host_sources]:
            with self.subTest(missing=path.name):
                self.freeze(omit=(path,))
                with self.assertRaises(NativeRunError):
                    self.session()
                self.assertFalse(self.output.exists())
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_descriptor_and_declared_input_drift_are_rejected_before_output(self):
        for path in (self.descriptor, self.answer_file):
            original = path.read_bytes()
            path.write_bytes(original + b"changed")
            try:
                with self.subTest(path=path.name), self.assertRaises(NativeRunError):
                    self.session()
                self.assertFalse(self.output.exists())
            finally:
                path.write_bytes(original)

    def test_descriptor_trust_boundaries_are_checked_before_output(self):
        changes = [
            lambda r: r.update(extra=True),
            lambda r: r["worker"].update(format="buddha.native-worker.unsupported"),
            lambda r: r["worker"].update(type="not-configure"),
            lambda r: r["worker"].update(extra=True),
            lambda r: r["worker"]["roots"].update(official="/inputs"),
            lambda r: r["worker"].update(release_sha256="0" * 64),
            lambda r: r["worker"]["command"].update(sha256="0" * 64),
            lambda r: r["worker"].update(answers_sha256="0" * 64),
            lambda r: r["executor"].update(role="agent"),
            lambda r: r["executor"].update(docker_endpoint="tcp://localhost:2375"),
            lambda r: r["executor"]["mounts"][0].__setitem__(1, str(self.inputs)),
            lambda r: r["profiles"]["openai"].update({"test-model": "not-owned"}),
        ]
        original = copy.deepcopy(self.record)
        for number, change in enumerate(changes):
            self.record = copy.deepcopy(original)
            change(self.record)
            with self.subTest(boundary=number):
                self.freeze()
                with self.assertRaises(NativeRunError):
                    self.session()
                self.assertFalse(self.output.exists())

    def test_input_mount_cannot_include_undeclared_or_unhashed_source_files(self):
        extra = self.inputs / "private-extra.txt"
        extra.write_text("must not enter evaluator")
        with self.assertRaises(NativeRunError):
            self.session()
        self.assertFalse(self.output.exists())

    def test_runner_copy_must_match_actual_installed_modules(self):
        path = self.fixture.roots["runner"] / "buddha/native_context.py"
        path.write_bytes(path.read_bytes() + b"\n# divergent copy\n")
        self.record["worker"]["inventories"]["runner"] = inventory(self.fixture.roots["runner"])
        self.freeze()
        with self.assertRaises(NativeRunError):
            self.session()
        self.assertFalse(self.output.exists())

    def test_ready_is_required_once_before_requests_files_and_done(self):
        for frame in (self.request(), self.file("result.json"), self.done()):
            self.freeze()
            session = self.session()
            with self.subTest(type=frame["type"]), self.assertRaises(NativeRunError):
                session.handle(frame)
        self.freeze()
        session = self.session()
        self.assertIsNone(self.ready(session))
        with self.assertRaises(NativeRunError):
            self.ready(session)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_ready_rejects_invented_aliases_and_unsealed_or_mistyped_audit(self):
        bad = [
            {
                "type": "ready",
                "aliases": [{"path": "foreign:judge", "label": "judge"}],
                "audit": self.audit(),
            },
            {
                "type": "ready",
                "aliases": [],
                "audit": {
                    "src.evaluate": {
                        "kind": "official",
                        "path": "/official/src/evaluate.py",
                        "sha256": "0" * 64,
                    }
                },
            },
            {"type": "ready", "aliases": [], "audit": {"src.evaluate": {"kind": "made-up"}}},
            {
                "type": "ready",
                "aliases": [],
                "audit": {
                    "src.evaluate": {
                        "kind": "base-image",
                        "path": "/usr/local/lib/python3.13/site-packages/evil.py",
                        "sha256": "0" * 64,
                    }
                },
            },
        ]
        for frame in bad:
            self.freeze()
            with self.subTest(frame=frame), self.assertRaises(NativeRunError):
                self.session().handle(frame)

    def test_ready_accepts_declared_synthetic_module_with_sealed_loader_owner(self):
        session = self.session()
        audit = self.audit()
        audit["synthetic_fixture"] = {
            "kind": "image-synthetic",
            "loader_owner": {
                "kind": "environment",
                "path": "/opt/venv/lib/python3.13/site-packages/fixture.py",
                "sha256": "f" * 64,
            },
        }
        self.assertIsNone(session.handle({"type": "ready", "aliases": [], "audit": audit}))

    def test_derived_class_audit_requires_the_exact_sealed_declaration(self):
        environment = self.worker["inventories"]["environment"]
        environment["derived_modules"] = {
            "fixture.derived": {
                "kind": "class",
                "module": "fixture.owner",
                "qualname": "Derived",
                "owner": "lib/python3.13/site-packages/fixture.py",
            }
        }
        entry = {
            "kind": "image-derived-class",
            "module": "fixture.owner",
            "qualname": "Derived",
            "owner": {
                "kind": "environment",
                "path": "/opt/venv/lib/python3.13/site-packages/fixture.py",
                "sha256": "f" * 64,
            },
        }
        for mutation in (None, "module", "qualname", "owner", "undeclared"):
            with self.subTest(mutation=mutation):
                self.freeze()
                session = self.session()
                audit = self.audit() | {"fixture.derived": copy.deepcopy(entry)}
                if mutation in {"module", "qualname"}:
                    audit["fixture.derived"][mutation] = "Impostor"
                elif mutation == "owner":
                    audit["fixture.derived"]["owner"]["sha256"] = "0" * 64
                elif mutation == "undeclared":
                    audit["undeclared"] = audit.pop("fixture.derived")
                if mutation is None:
                    self.assertIsNone(
                        session.handle({"type": "ready", "aliases": [], "audit": audit})
                    )
                else:
                    with self.assertRaises(NativeRunError):
                        session.handle({"type": "ready", "aliases": [], "audit": audit})
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_derived_source_audit_requires_exact_hash_private_root_basename_and_owners(self):
        environment = self.worker["inventories"]["environment"]
        environment["derived_modules"] = {
            "fixture.generated": {
                "kind": "source",
                "root": "/tmp",
                "basename": "generated.py",
                "sha256": "a" * 64,
                "owners": ["lib/python3.13/site-packages/fixture.py"],
            }
        }
        entry = {
            "kind": "image-derived-source",
            "path": "/tmp/private/generated.py",
            "sha256": "a" * 64,
            "owners": [
                {
                    "kind": "environment",
                    "path": "/opt/venv/lib/python3.13/site-packages/fixture.py",
                    "sha256": "f" * 64,
                }
            ],
        }
        for mutation in (None, "hash", "root", "basename", "escape", "owner", "extra"):
            with self.subTest(mutation=mutation):
                self.freeze()
                session = self.session()
                audit = self.audit() | {"fixture.generated": copy.deepcopy(entry)}
                generated = audit["fixture.generated"]
                if mutation == "hash":
                    generated["sha256"] = "0" * 64
                elif mutation == "root":
                    generated["path"] = "/official/private/generated.py"
                elif mutation == "basename":
                    generated["path"] = "/tmp/private/different.py"
                elif mutation == "escape":
                    generated["path"] = "/tmp/../elsewhere/generated.py"
                elif mutation == "owner":
                    generated["owners"][0]["sha256"] = "0" * 64
                elif mutation == "extra":
                    generated["owners"].append(copy.deepcopy(generated["owners"][0]))
                if mutation is None:
                    self.assertIsNone(
                        session.handle({"type": "ready", "aliases": [], "audit": audit})
                    )
                else:
                    with self.assertRaises(NativeRunError):
                        session.handle({"type": "ready", "aliases": [], "audit": audit})
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_ready_rejects_namespace_path_without_any_selected_inventory(self):
        session = self.session()
        audit = self.audit()
        audit["invented_namespace"] = {
            "kind": "namespace",
            "paths": ["/official/not-in-selected-source"],
        }
        with self.assertRaises(NativeRunError):
            session.handle({"type": "ready", "aliases": [], "audit": audit})

    def test_request_maps_owner_profile_and_preserves_raw_bytes_through_real_ledger(self):
        session = self.session()
        self.ready(session)
        connection = self.fixture.connection()
        frame = self.send(session, connection=connection)
        self.assertEqual(frame["type"], "response")
        self.assertEqual(frame["seq"], 0)
        envelope = RawEnvelope.from_record(frame["envelope"])
        self.assertEqual(envelope.body, connection.getresponse.return_value.read.return_value)
        self.assertEqual(connection.request.call_args.kwargs["body"], self.fixture.body)
        self.assertEqual(
            connection.request.call_args.kwargs["headers"]["user-agent"],
            "synthetic-host-session/1.0",
        )
        ledger = self.fixture.authority.for_run(self.directory)
        self.assertEqual(ledger.totals()["spent_microusd"], 11)
        self.assertEqual(ledger.totals()["operation_count"], 1)
        call = GatewayCall(
            fixtures.CAPABILITY,
            "primary",
            "b" * 64,
            0,
            self.fixture.body,
            (("user-agent", "synthetic-host-session/1.0"),),
        )
        self.assertEqual(ledger.get(self.gateway.operation_id(call)).status, "completed")

    def test_completed_request_replay_uses_bound_identity_without_new_credentials_or_cost(self):
        first = self.session()
        self.ready(first)
        expected = self.send(first)
        other_output = self.fixture.root / "replay-output"
        replay = NativeSession(self.gateway, descriptor=self.descriptor, output=other_output)
        self.ready(replay)
        with patch.dict(os.environ, {}, clear=True), patch("http.client.HTTPSConnection") as send:
            self.assertEqual(replay.handle(self.request()), expected)
        send.assert_not_called()
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 1)

    def test_sequence_is_contiguous_exact_integer_and_request_fields_are_strict(self):
        bad = [self.request(seq=True), self.request(seq=1), self.request(seq=-1)]
        frame = self.request()
        frame["request"]["extra"] = "not allowed"
        bad.append(frame)
        for frame in bad:
            self.freeze()
            session = self.session()
            self.ready(session)
            with self.subTest(seq=frame["seq"]), self.assertRaises(NativeRunError):
                session.handle(frame)
            with patch.object(
                self.gateway, "execute", side_effect=AssertionError("poisoned session dispatched")
            ):
                with self.assertRaises(NativeRunError):
                    session.handle(self.request())
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_timeout_retains_unknown_hold_and_latches_stop_before_any_more_dispatch(self):
        session = self.session()
        self.ready(session)
        connection = self.fixture.connection()
        connection.getresponse.side_effect = TimeoutError("private diagnostic")
        self.assertEqual(
            self.send(session, connection=connection),
            {"type": "stop", "seq": 0, "reason": "unknown"},
        )
        with patch.object(
            self.gateway, "execute", side_effect=AssertionError("dispatch after stop")
        ):
            self.assertEqual(
                session.handle(self.request(seq=1, logical_id="c" * 64)),
                {"type": "stop", "seq": 1, "reason": "unknown"},
            )
        totals = self.fixture.authority.summary()
        self.assertEqual(totals["reserved_microusd"], 300)
        self.assertEqual(totals["operation_count"], 1)
        recovered = NativeSession(
            self.gateway,
            descriptor=self.descriptor,
            output=self.fixture.root / "unknown-restart",
        )
        self.ready(recovered)
        with patch.dict(os.environ, {}, clear=True), patch("http.client.HTTPSConnection") as send:
            self.assertEqual(
                recovered.handle(self.request()),
                {"type": "stop", "seq": 0, "reason": "authority"},
            )
        send.assert_not_called()
        self.assertEqual(self.fixture.authority.summary()["reserved_microusd"], 300)
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 1)
        with self.assertRaises(NativeRunError):
            session.handle(self.done())

    def test_pending_exception_maps_to_unknown_without_disclosing_diagnostic(self):
        session = self.session()
        self.ready(session)
        # The real shared guard usually halts an old unknown as BudgetExceeded.
        # This component check covers the narrower post-guard pending race signal.
        with patch.object(
            self.gateway, "execute", side_effect=PendingOperation("private diagnostic")
        ):
            self.assertEqual(
                session.handle(self.request()),
                {"type": "stop", "seq": 0, "reason": "unknown"},
            )
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_inactive_authority_and_protocol_error_map_to_sanitized_stops(self):
        session = self.session()
        self.ready(session)
        self.fixture.authority.deactivate("native-1", "offline test")
        self.assertEqual(self.send(session), {"type": "stop", "seq": 0, "reason": "protocol"})
        self.freeze()
        session = self.session()
        self.ready(session)
        bad_body = self.fixture.body.replace(b'"stream":false', b'"stream":true')
        self.assertEqual(
            self.send(session, self.request(body=bad_body)),
            {"type": "stop", "seq": 0, "reason": "protocol"},
        )
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_budget_refusal_and_known_token_overrun_stop_under_authority(self):
        self.freeze(budget_microusd=200)
        session = self.session()
        self.ready(session)
        with patch.dict(os.environ, {}, clear=True), patch("http.client.HTTPSConnection") as send:
            self.assertEqual(
                session.handle(self.request()),
                {"type": "stop", "seq": 0, "reason": "authority"},
            )
        send.assert_not_called()
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)
        self.freeze()
        session = self.session()
        self.ready(session)
        response = self.fixture.response(usage={"prompt_tokens": 101, "completion_tokens": 3})
        self.assertEqual(
            self.send(session, connection=self.fixture.connection(response)),
            {"type": "stop", "seq": 0, "reason": "authority"},
        )
        # Preserve Gateway's guard: token-bound breach within the monetary reserve
        # retains that reserve instead of treating out-of-contract usage as settled.
        self.assertEqual(self.fixture.authority.summary()["spent_microusd"], 0)
        self.assertEqual(self.fixture.authority.summary()["reserved_microusd"], 300)

    def test_owner_model_mapping_cannot_be_chosen_by_worker(self):
        session = self.session()
        self.ready(session)
        body = self.fixture.body.replace(b'"test-model"', b'"unreviewed-model"')
        with patch.object(
            self.gateway, "execute", side_effect=AssertionError("unreviewed model dispatched")
        ):
            with self.assertRaises(NativeRunError):
                session.handle(self.request(body=body))

    def test_native_files_are_separate_from_host_report_and_record_exact_bytes(self):
        session = self.session()
        self.ready(session)
        self.assertIsNone(session.handle(self.file("report.json", b"native report")))
        self.assertIsNone(session.handle(self.file("nested/result.json", b"\x00literal\xff")))
        self.assertEqual((self.output / "artifacts/report.json").read_bytes(), b"native report")
        self.assertEqual(
            (self.output / "artifacts/nested/result.json").read_bytes(), b"\x00literal\xff"
        )
        self.assertFalse((self.output / "report.json").exists())

    def test_artifact_paths_are_portable_unique_and_cannot_escape_or_replace(self):
        for path in ("../escape", "/absolute", "C:/absolute", "a\\b", "CON", "a/../b", "a."):
            self.freeze()
            session = self.session()
            self.ready(session)
            with self.subTest(path=path), self.assertRaises(NativeRunError):
                session.handle(self.file(path))
        for first, second in (
            ("Result.json", "result.json"),
            ("same", "same"),
            ("parent", "parent/child"),
        ):
            self.freeze()
            session = self.session()
            self.ready(session)
            session.handle(self.file(first, b"first"))
            with self.subTest(first=first, second=second), self.assertRaises(NativeRunError):
                session.handle(self.file(second, b"second"))
            self.assertEqual((self.output / "artifacts" / first).read_bytes(), b"first")

    def test_output_directory_is_fresh_and_existing_files_are_never_replaced(self):
        self.output.mkdir()
        marker = self.output / "owner.txt"
        marker.write_text("keep")
        with self.assertRaises(NativeRunError):
            self.session()
        self.assertEqual(marker.read_text(), "keep")

    def test_artifact_capture_does_not_replace_an_injected_hardlink(self):
        session = self.session()
        self.ready(session)
        outside = self.fixture.root / "outside-owner.txt"
        outside.write_bytes(b"owner data")
        target = self.output / "artifacts/injected.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(outside, target)
        with self.assertRaises(NativeRunError):
            session.handle(self.file("injected.txt", b"replaced"))
        self.assertEqual(outside.read_bytes(), b"owner data")

    def test_artifact_capture_rejects_an_injected_parent_directory_link(self):
        session = self.session()
        self.ready(session)
        outside = self.fixture.root / "outside-folder"
        outside.mkdir()
        target = self.output / "artifacts/injected"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("host does not permit directory symlinks")
            # Windows junctions need no symlink privilege and must be denied too.
            system = os.environ["SystemRoot"]
            result = subprocess.run(
                [
                    str(Path(system) / "System32/cmd.exe"),
                    "/c",
                    "mklink",
                    "/J",
                    str(target),
                    str(outside),
                ],
                capture_output=True,
                timeout=10,
                env={"SystemRoot": system},
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
            if result.returncode:
                self.skipTest("host permits neither directory symlinks nor junctions")
        with self.assertRaises(NativeRunError):
            session.handle(self.file("injected/escape.txt", b"must not escape"))
        self.assertFalse((outside / "escape.txt").exists())

    def test_file_chunks_require_canonical_base64_offset_bool_and_serial_completion(self):
        frames = [
            self.file("a", b"short", eof=False),
            self.file("a", offset=True),
            self.file("a", offset=1),
            self.file("a", eof=1),
            self.file("a", b"x" * (64 * 1024 + 1)),
        ]
        padded = self.file("a", b"a")
        padded["data_base64"] = "YR=="  # Decodes as 'a', but has noncanonical pad bits.
        frames.append(padded)
        for frame in frames:
            self.freeze()
            session = self.session()
            self.ready(session)
            with self.subTest(frame_keys=list(frame)), self.assertRaises(NativeRunError):
                session.handle(frame)
        self.freeze()
        session = self.session()
        self.ready(session)
        session.handle(self.file("a", b"x" * (64 * 1024), eof=False))
        with self.assertRaises(NativeRunError):
            session.handle(self.file("b"))
        with self.assertRaises(NativeRunError):
            session.handle(self.done())

    def test_artifact_file_count_individual_and_total_byte_limits_are_enforced(self):
        with patch.object(native_run, "MAX_FILES", 1):
            session = self.session()
            self.ready(session)
            session.handle(self.file("a"))
            with self.assertRaises(NativeRunError):
                session.handle(self.file("b"))
        self.freeze()
        with patch.object(native_run, "MAX_FILE_BYTES", 3):
            session = self.session()
            self.ready(session)
            with self.assertRaises(NativeRunError):
                session.handle(self.file("a", b"four"))
        self.freeze()
        with patch.object(native_run, "MAX_FILE_BYTES", 64 * 1024 + 1):
            session = self.session()
            self.ready(session)
            session.handle(self.file("a", b"x" * (64 * 1024), eof=False))
            with self.assertRaises(NativeRunError):
                session.handle(self.file("a", b"xx", offset=64 * 1024))
            self.assertFalse((self.output / "artifacts/a").exists())
        self.freeze()
        with patch.object(native_run, "MAX_TOTAL_BYTES", 3):
            session = self.session()
            self.ready(session)
            session.handle(self.file("a", b"ab"))
            with self.assertRaises(NativeRunError):
                session.handle(self.file("b", b"cd"))

    def test_done_is_terminal_and_reasons_and_audit_are_validated(self):
        session = self.session()
        self.ready(session)
        self.assertIsNone(session.handle(self.done()))
        for frame in (self.done(), self.request(), self.file("late")):
            with self.subTest(type=frame["type"]), self.assertRaises(NativeRunError):
                session.handle(frame)
        self.freeze()
        session = self.session()
        self.ready(session)
        with self.assertRaises(NativeRunError):
            session.handle(self.done(status="failed", reason="private arbitrary diagnostic"))
        self.freeze()
        session = self.session()
        self.ready(session)
        malformed = self.done()
        malformed["audit"]["src.evaluate"]["sha256"] = "0" * 64
        with self.assertRaises(NativeRunError):
            session.handle(malformed)

    def test_run_publishes_host_report_only_after_removed_execution_and_valid_done(self):
        session = self.session()

        def execute(spec, *, initial, handle, **kwargs):
            self.assertEqual(initial, self.worker)
            self.assertEqual(spec.role, "evaluator")
            self.assertFalse((self.output / "report.json").exists())
            handle({"type": "ready", "aliases": [], "audit": self.audit()})
            connection = self.fixture.connection()
            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
                patch("http.client.HTTPSConnection", return_value=connection),
            ):
                self.assertEqual(handle(self.request())["type"], "response")
            handle(self.file("summary.json", b'{"native":true}'))
            handle(self.done())
            self.assertFalse((self.output / "report.json").exists())
            return ExecutionResult(
                0, "c" * 64, "sha256:" + "a" * 64, 100, 0, sha(b""), 4, 0.1, b"{}"
            )

        with patch("buddha.native_run.executor.run_container", side_effect=execute):
            report = session.run()
        self.assertEqual(report["format"], "buddha.native-command-report.v1")
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["execution"]["cleanup_status"], "removed")
        self.assertEqual(report["artifacts"], {"summary.json": sha(b'{"native":true}')})
        self.assertEqual(report["calls"], {"requested": 1, "completed": 1, "stopped": 0})
        self.assertEqual(report["descriptor_sha256"], sha(self.descriptor.read_bytes()))
        self.assertEqual(report["gateway_manifest_sha256"], self.gateway.manifest_sha256)
        self.assertEqual(self.fixture.authority.summary()["spent_microusd"], 11)
        self.assertEqual(json.loads((self.output / "report.json").read_bytes()), report)

    def test_public_configuration_mutation_cannot_change_dispatched_configuration(self):
        session = self.session()
        changes = (
            lambda: session.worker["command"]["argv"].append("/unbound"),
            lambda: session.profiles["openai"].__setitem__("test-model", "not-owned"),
            lambda: setattr(session, "spec", replace(session.spec, image_id="sha256:" + "d" * 64)),
        )
        for mutate in changes:
            try:
                mutate()
            except (AttributeError, TypeError, NativeRunError):
                pass  # A read-only property/container may reject mutation immediately.

        def execute(spec, *, initial, handle, **kwargs):
            self.assertEqual(initial, self.worker)
            self.assertEqual(spec.image_id, self.record["executor"]["image_id"])
            handle({"type": "ready", "aliases": [], "audit": self.audit()})
            connection = self.fixture.connection()
            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": fixtures.KEY}, clear=True),
                patch("http.client.HTTPSConnection", return_value=connection),
            ):
                self.assertEqual(handle(self.request())["type"], "response")
            handle(self.done())
            return ExecutionResult(
                0, "c" * 64, "sha256:" + "a" * 64, 100, 0, sha(b""), 3, 0.1, b"{}"
            )

        with patch("buddha.native_run.executor.run_container", side_effect=execute) as run:
            try:
                report = session.run()
            except NativeRunError:
                run.assert_not_called()  # Rejecting changed config before execution is also safe.
                self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)
            else:
                self.assertEqual(report["status"], "complete")
                self.assertEqual(self.fixture.authority.summary()["spent_microusd"], 11)

    def test_missing_done_or_nonzero_exit_cannot_publish_complete_report(self):
        for with_done, exit_code, cleanup_status in (
            (False, 0, "removed"),
            (True, 1, "removed"),
            (True, 0, "not_removed"),
        ):
            self.freeze()
            session = self.session()

            def execute(
                spec,
                *,
                handle,
                session=session,
                with_done=with_done,
                exit_code=exit_code,
                cleanup_status=cleanup_status,
                **kwargs,
            ):
                self.ready(session)
                if with_done:
                    handle(self.done())
                return ExecutionResult(
                    exit_code,
                    "c" * 64,
                    "sha256:" + "a" * 64,
                    100,
                    0,
                    sha(b""),
                    1,
                    0.1,
                    b"{}",
                    cleanup_status,
                )

            with (
                self.subTest(with_done=with_done, exit_code=exit_code),
                patch("buddha.native_run.executor.run_container", side_effect=execute),
            ):
                report = session.run()
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["execution"]["cleanup_status"], cleanup_status)
