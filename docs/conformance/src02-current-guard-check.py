"""Root-reviewed extracted-helper microtests; never import/run the adapter main.

Requires explicit pinned trusted driver and a NEW owned --directory. Uses only
new local fixture files, stdlib threads and a Popen stub. No app/SQL/network/
Docker/provider/authority/selected-source execution. Do not run before review.
"""

import argparse
import ast
import copy
import hashlib
import json
import os
import re
import stat
import subprocess  # nosec B404: list2cmdline only; process creation is stubbed
import sys
import threading
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace

DRIVER = None
WORK = None


def extracted():
    tree = ast.parse(DRIVER.read_text(encoding="utf-8"), filename=str(DRIVER))
    wanted = {
        "require",
        "sha",
        "encoded",
        "checked_write_target",
        "docker_process_guard",
        "writable",
        "audit",
        "frame",
    }
    nodes = [
        copy.deepcopy(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name in wanted
    ]
    if len(nodes) != len(wanted) or {n.name for n in nodes} != wanted:
        raise RuntimeError("trusted helper inventory differs")
    namespace = {
        "os": os,
        "re": re,
        "stat": stat,
        "Path": Path,
        "hashlib": hashlib,
        "json": json,
        "subprocess": subprocess,
        "threading": threading,
        "traceback": traceback,
    }
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(DRIVER) + "::<extracted-helpers>", "exec"), namespace)
    return namespace


class RehearsalGuardTests(unittest.TestCase):
    def test_hardlink_publish_unlink_preserves_strict_mutation_boundary(self):
        ns = extracted()
        case = WORK / "hardlink"
        root = case / "fixture"
        root.mkdir(parents=True)
        outside = case / "outside"
        outside.write_bytes(b"outside unchanged")
        ns.update(
            args=SimpleNamespace(directory=root, proposal=case / "proposal"),
            phase="preparation",
            permitted_outputs={case / "receipt.json"},
            allowed_sql={":memory:"},
            protected_code=set(),
            audited_popen=lambda *_: (_ for _ in ()).throw(RuntimeError("no process")),
        )
        enabled = {"value": False}

        def hook(event, values):
            if enabled["value"]:
                ns["audit"](event, values)

        sys.addaudithook(hook)
        enabled["value"] = True
        temporary, target, another = root / "temporary", root / "published", root / "new-link"
        try:
            temporary.write_bytes(b"exact artifact bytes")
            os.link(temporary, target)
            self.assertEqual(temporary.stat().st_nlink, 2)
            self.assertEqual(target.stat().st_nlink, 2)
            self.assertEqual(temporary.stat().st_ino, target.stat().st_ino)
            for operation, message in (
                (
                    lambda: temporary.write_bytes(b"must not replace"),
                    "write outside new synthetic outputs",
                ),
                (
                    lambda: os.chmod(temporary, temporary.stat().st_mode),
                    "mutation outside synthetic outputs",
                ),
                (lambda: os.utime(temporary, None), "mutation outside synthetic outputs"),
                (lambda: os.link(temporary, another), "move/link outside synthetic outputs"),
                (lambda: outside.unlink(), "mutation outside synthetic outputs"),
                (
                    lambda: (root / ".." / outside.name).unlink(),
                    "mutation outside synthetic outputs",
                ),
            ):
                with self.subTest(message=message):
                    with self.assertRaises(RuntimeError) as caught:
                        operation()
                    self.assertEqual(str(caught.exception), message)
            self.assertFalse(another.exists())
            temporary.unlink()
            self.assertFalse(temporary.exists())
            self.assertEqual(target.read_bytes(), b"exact artifact bytes")
            self.assertEqual(target.stat().st_nlink, 1)
            self.assertEqual(outside.read_bytes(), b"outside unchanged")
            ns["phase"] = "completed-keyless-repeat"
            with self.assertRaises(RuntimeError) as caught:
                target.unlink()
            self.assertEqual(str(caught.exception), "mutation outside synthetic outputs")
            self.assertTrue(target.is_file())
        finally:
            enabled["value"] = False

    def test_registration_is_current_thread_exact_and_allows_owned_watchdog(self):
        ns = extracted()
        docker, endpoint, identity = "synthetic-docker.exe", "npipe:////./pipe/synthetic", "a" * 64
        entered, release, finished_b = threading.Event(), threading.Event(), threading.Event()
        runtime, events, calls, errors = {"active": {}}, [], [], {}
        start = [docker, "--host", endpoint, "start", "-ai", identity]
        kill = [docker, "--host", endpoint, "kill", identity]
        guarded = audited = None

        def original(command, *, executable, **options):
            calls.append(tuple(command))
            audited(executable, subprocess.list2cmdline(command))
            if threading.current_thread().name == "A":
                with self.assertRaises(RuntimeError) as caught:
                    guarded(command)
                self.assertEqual(str(caught.exception), "nested subprocess registration")
                with self.assertRaises(RuntimeError) as caught:
                    audited("other.exe", subprocess.list2cmdline(command))
                self.assertEqual(str(caught.exception), "unregistered process executable")
                with self.assertRaises(RuntimeError) as caught:
                    audited(executable, subprocess.list2cmdline(kill))
                self.assertEqual(
                    str(caught.exception), "process audit differs from exact validated argv"
                )
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("controlled thread release timed out")
            else:
                audited(executable, command)
            return "stub-only"

        guarded, audited, _control, owned = ns["docker_process_guard"](
            docker, endpoint, events, original, runtime, set()
        )
        owned.add(identity)

        def run(name, command):
            try:
                self.assertEqual(guarded(command), "stub-only")
            except BaseException as error:
                errors[name] = error
            finally:
                if name == "B":
                    finished_b.set()

        a = threading.Thread(target=run, args=("A", start), name="A")
        b = threading.Thread(target=run, args=("B", kill), name="B")
        a.start()
        try:
            self.assertTrue(entered.wait(10), "controlled first registration not entered")
            # MAIN is unregistered while A holds a genuine validated registration.
            # The v3 global list incorrectly lets MAIN borrow that registration.
            with self.assertRaises(RuntimeError) as caught:
                audited(docker, subprocess.list2cmdline(start))
            self.assertEqual(str(caught.exception), "unregistered process executable")
            b.start()
            self.assertTrue(finished_b.wait(10), "controlled watchdog did not finish")
        finally:
            release.set()
            a.join(10)
            if b.ident is not None:
                b.join(10)
        self.assertFalse(a.is_alive())
        self.assertFalse(b.is_alive())
        self.assertEqual(errors, {})
        self.assertEqual(calls, [tuple(start), tuple(kill)])
        self.assertEqual(len(events), 3)  # A serialized; B serialized and list audit.
        for command, options, message in (
            (
                ["other.exe", "context", "show"],
                {},
                "Docker command outside exact local owned lifecycle",
            ),
            (
                [docker, "--host", "remote", "kill", identity],
                {},
                "Docker command outside exact local owned lifecycle",
            ),
            (start, {"shell": True}, "shell/executable override forbidden"),
        ):
            with self.subTest(command=command, options=options):
                with self.assertRaises(RuntimeError) as caught:
                    guarded(command, **options)
                self.assertEqual(str(caught.exception), message)
        self.assertEqual(len(calls), 2)
        with self.assertRaises(RuntimeError) as caught:
            audited(docker, subprocess.list2cmdline(start))
        self.assertEqual(str(caught.exception), "unregistered process executable")

    def test_callback_failure_retains_bounded_redacted_origin_and_same_exception(self):
        ns = extracted()
        key, marker = "known-synthetic-key", "must-not-retain-frame-payload"
        failure = RuntimeError(key + " original callback failure " + "x" * 5000)
        evidence, frames = {"frame_failures": []}, []

        def handle(_value):
            raise failure

        owner = WORK / "callback" / "owners" / "0"
        ns.update(
            _json=lambda value: json.dumps(value).encode(),
            handle=handle,
            frames=frames,
            owner=owner,
            phase="synthetic-check",
            evidence=evidence,
            KEYS={"openai": key},
        )
        with self.assertRaises(RuntimeError) as caught:
            ns["frame"]({"type": "file", "payload": marker})
        self.assertIs(caught.exception, failure)
        self.assertEqual(len(evidence["frame_failures"]), 1)
        record = evidence["frame_failures"][0]
        self.assertEqual(record["owner"], str(owner))
        self.assertEqual(record["phase"], "synthetic-check")
        self.assertEqual(record["frame_kind"], "file")
        self.assertEqual(record["exception_type"], "RuntimeError")
        self.assertLessEqual(len(record["message"]), 4096)
        self.assertLessEqual(len(record["frames"]), 20)
        self.assertNotIn(key, json.dumps(record))
        self.assertNotIn(marker, json.dumps(record))
        self.assertIn("[synthetic key redacted]", record["message"])
        self.assertEqual(frames, [])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", required=True, type=Path)
    parser.add_argument("--driver-sha256", required=True)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    DRIVER = args.driver
    if hashlib.sha256(DRIVER.read_bytes()).hexdigest() != args.driver_sha256:
        raise RuntimeError("driver pin differs")
    WORK = args.directory
    check = extracted()["checked_write_target"]
    if check(WORK) != WORK or WORK.exists():
        raise RuntimeError("microtest directory must be NEW plain canonical path")
    WORK.mkdir()
    unittest.main(argv=[__file__], verbosity=2)
