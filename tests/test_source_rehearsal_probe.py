"""Portable checks for the trusted rehearsal guard; no processes or funding."""

import ast
import importlib.util
import inspect
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class SourceRehearsalProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(__file__).resolve().parents[1] / "docs/conformance/src02-full-rehearsal.py"
        spec = importlib.util.spec_from_file_location("_trusted_source_rehearsal_tests", script)
        cls.probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.probe)

    def test_local_hostname_metadata_is_allowed_while_network_events_are_denied(self):
        # Extract only the trusted host guard, never candidate or official code.
        parsed = ast.parse(inspect.getsource(self.probe.main))
        functions = [
            node
            for node in ast.walk(parsed)
            if isinstance(node, ast.FunctionDef) and node.name == "audit"
        ]
        self.assertEqual(len(functions), 1)
        scope = {}
        exec(
            compile(
                ast.Module(body=functions, type_ignores=[]), "<trusted-rehearsal-audit>", "exec"
            ),
            scope,
        )
        audit = scope["audit"]
        self.assertIsNone(audit("socket.gethostname", ()))
        for event in ("socket.__new__", "socket.connect", "socket.bind", "socket.getaddrinfo"):
            with self.subTest(event=event), self.assertRaises(RuntimeError):
                audit(event, ())

    def test_exact_process_registration_covers_both_audit_representations(self):
        docker = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
        endpoint = "npipe:////./pipe/dockerDesktopLinuxEngine"
        events, calls = [], []
        command = [docker, "--host", endpoint, "image", "inspect", "sha256:" + "a" * 64]
        mode = "windows"

        def original(argv, **options):
            self.assertEqual(options, {"executable": docker, "shell": False})
            calls.append(tuple(argv))
            value = subprocess.list2cmdline(argv) if mode == "windows" else list(argv)
            audited(docker, value)
            with self.assertRaises(RuntimeError):
                audited(docker, value + " altered" if mode == "windows" else [*value, "altered"])
            with self.assertRaises(RuntimeError):
                audited(None, value)
            return "original-result"

        guarded, audited = self.probe.docker_process_guard(docker, endpoint, events, original)
        for mode in ("windows", "posix"):
            with self.subTest(mode=mode):
                self.assertEqual(guarded(command, shell=False), "original-result")
                with self.assertRaises(RuntimeError):
                    audited(docker, subprocess.list2cmdline(command))
        self.assertEqual(len(calls), 2)
        self.assertEqual([event["verb"] for event in events], ["image", "image"])

    def test_unapproved_processes_never_reach_original_popen(self):
        docker = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
        endpoint = "npipe:////./pipe/dockerDesktopLinuxEngine"

        def forbidden(*_args, **_kwargs):
            self.fail("unapproved argv reached the original process constructor")

        guarded, audited = self.probe.docker_process_guard(docker, endpoint, [], forbidden)
        command = [docker, "context", "show"]
        for argv, options in (
            (["another-executable", "context", "show"], {}),
            ([docker, "--host", "tcp://remote:2375", "inspect", "image"], {}),
            ([docker, "--host", endpoint, "exec", "container", "anything"], {}),
            (subprocess.list2cmdline(command), {}),
            (command, {"shell": True}),
            (command, {"executable": docker}),
            (command, {"executable": None}),
        ):
            with self.subTest(argv=argv, options=options), self.assertRaises(RuntimeError):
                guarded(argv, **options)
        with self.assertRaises(RuntimeError):
            guarded(command, 0)
        with self.assertRaises(RuntimeError):
            audited(docker, command)

    def test_output_paths_reject_windows_stream_device_and_trailing_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.assertEqual(
                self.probe.absolute(root / "new-output.json"), root / "new-output.json"
            )
            for name in (
                "evidence.json:stream",
                "evidence.json.",
                "evidence.json ",
                "NUL.json",
                "COM1",
                "CONOUT$",
            ):
                with self.subTest(name=name), self.assertRaises(RuntimeError):
                    self.probe.absolute(root / name)
            self.assertEqual(list(root.iterdir()), [])

    def test_wrong_script_pin_refuses_before_outputs_or_external_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            arguments = SimpleNamespace(
                directory=root / "new-run",
                out=root / "proof.json",
                sources=root / "absent-inventory.json",
                proposal=root / "absent-proposal.json",
                sources_sha256="0" * 64,
                script_sha256="0" * 64,
                proposal_sha256=self.probe.PROPOSAL_SHA256,
            )
            with (
                patch("subprocess.Popen", side_effect=AssertionError("process in preflight")),
                patch("sqlite3.connect", side_effect=AssertionError("SQL in preflight")),
                patch("socket.socket", side_effect=AssertionError("socket in preflight")),
                self.assertRaisesRegex(RuntimeError, "caller script pin differs"),
            ):
                self.probe.preflight(arguments)
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
