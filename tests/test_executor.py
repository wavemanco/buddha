"""Executor API boundaries; actual Docker confinement is a separate acceptance probe."""

import copy
import hashlib
import io
import json
import math
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from buddha.executor import ContainerSpec, ExecutorError, Limits, run_container
from buddha.releases import ReleaseError

IMAGE = "sha256:" + "a" * 64
CONTAINER = "b" * 64
OWNER_LABEL = "org.buddha.executor"
ENDPOINT = "unix:///scope-docker.sock"
WORKER_ENVIRONMENT = {
    "HOME": "/scratch/home",
    "TMPDIR": "/tmp",
    "ANTHROPIC_CONFIG_DIR": "/scratch/home/anthropic",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    **{
        name: ""
        for key in ("http_proxy", "https_proxy", "ftp_proxy", "all_proxy", "no_proxy")
        for name in (key, key.upper())
    },
}


class RecordingInput(io.BytesIO):
    saved = b""

    def close(self):
        self.saved = self.getvalue()
        super().close()


class Child:
    def __init__(self, stdout, stderr):
        self.stdin = RecordingInput()
        self.stdout = io.BufferedReader(io.BytesIO(stdout))
        self.stderr = io.BufferedReader(io.BytesIO(stderr))
        self.returncode = None
        self.killed = False

    def wait(self, timeout=None):
        self.returncode = 137 if self.killed else 0
        return self.returncode

    def kill(self):
        self.killed = True


class DockerFixture:
    """Actual Docker inspect-shaped canned data; this does not prove confinement."""

    def __init__(self, spec, limits, *, stdout=b'{"message":"one"}\n', stderr=b""):
        self.spec, self.limits = spec, limits
        self.child = Child(stdout, stderr)
        self.calls = []
        self.raw_calls = []
        self.started = []
        self.record = None
        self.modify = lambda value: None
        self.create_error = None
        self.remove_error = None
        self.killed = threading.Event()

    def inspection(self, name, owner):
        spec, limits = self.spec, self.limits
        options = "noexec,nosuid,nodev,uid=65532,gid=65532,mode=0700"
        return {
            "Id": CONTAINER,
            "Name": "/" + name,
            "Image": IMAGE,
            "Config": {
                "User": "65532:65532",
                "WorkingDir": "/scratch",
                "Entrypoint": ["/opt/venv/bin/python"],
                "Cmd": [
                    "-I",
                    "-B",
                    "-X",
                    "pycache_prefix=/__absent_bytecode_cache",
                    "/runner/" + spec.runner_entrypoint,
                ],
                "Env": [
                    key + "=" + value
                    for key, value in (dict(spec.image_environment) | WORKER_ENVIRONMENT).items()
                ],
                "Labels": {OWNER_LABEL: owner},
                "Volumes": None,
                "Healthcheck": {"Test": ["NONE"]},
                "Tty": False,
                "OpenStdin": True,
            },
            "HostConfig": {
                "NetworkMode": "none",
                "ReadonlyRootfs": True,
                "Privileged": False,
                "CapDrop": ["ALL"],
                "CapAdd": None,
                "SecurityOpt": ["no-new-privileges:true"],
                "PidsLimit": limits.pids,
                "Memory": limits.memory_mib * 1024**2,
                "MemorySwap": limits.memory_mib * 1024**2,
                "NanoCpus": int(limits.cpus * 10**9),
                "IpcMode": "none",
                "CgroupnsMode": "private",
                "PidMode": "",
                "UTSMode": "",
                "LogConfig": {"Type": "none", "Config": {}},
                "Tmpfs": {
                    "/scratch": f"rw,size={limits.scratch_mib}m,{options}",
                    "/tmp": "rw,size=16m," + options,
                },
                "Ulimits": [
                    {"Name": "nofile", "Hard": 128, "Soft": 128},
                    {"Name": "nproc", "Hard": limits.pids, "Soft": limits.pids},
                ],
                "Mounts": [
                    {
                        "Type": "bind",
                        "Source": str(source),
                        "Target": target,
                        "ReadOnly": True,
                        "BindOptions": {"NonRecursive": True},
                    }
                    for target, source in spec.mounts
                ],
                "Binds": None,
                "Devices": [],
                "DeviceRequests": None,
                "ExtraHosts": None,
                "Links": None,
                "VolumesFrom": None,
            },
            "Mounts": [
                {"Type": "bind", "Source": str(source), "Destination": target, "RW": False}
                for target, source in spec.mounts
            ],
        }

    def control(self, argv, **kwargs):
        self.raw_calls.append(list(argv))
        if argv[1:3] != ["--host", ENDPOINT]:
            raise AssertionError("Docker command did not retain the frozen local endpoint")
        argv = [argv[0], *argv[3:]]
        self.calls.append(list(argv))
        self.assert_safe_process(kwargs)
        args = argv[1:]
        if args[0] == "create":
            name = args[args.index("--name") + 1]
            owner = args[args.index("--label") + 1].split("=", 1)[1]
            self.record = self.inspection(name, owner)
            self.modify(self.record)
            if self.create_error:
                raise self.create_error
            raw = (CONTAINER + "\n").encode()
        elif args[0] == "inspect" and args[-1] == IMAGE:
            raw = json.dumps(
                {
                    "Id": IMAGE,
                    "Os": "linux",
                    "Architecture": "amd64",
                    "Config": {"Volumes": None, "Env": []},
                }
            ).encode()
        elif args[0] == "inspect":
            raw = json.dumps(self.record).encode()
        elif args[:2] == ["container", "ls"]:
            raw = (CONTAINER + "\n").encode() if self.record else b""
        elif args[0] == "kill":
            self.child.killed = True
            self.killed.set()
            raw = (CONTAINER + "\n").encode()
        elif args[0] == "rm":
            if self.remove_error:
                raise self.remove_error
            raw = (CONTAINER + "\n").encode()
        else:
            raise AssertionError(f"unexpected canned Docker command: {args[0]}")
        return subprocess.CompletedProcess(argv, 0, stdout=raw, stderr=b"")

    def popen(self, argv, **kwargs):
        self.assert_safe_process(kwargs)
        if argv[1:3] != ["--host", ENDPOINT]:
            raise AssertionError("worker attachment changed the frozen local endpoint")
        argv = [argv[0], *argv[3:]]
        self.started.append(list(argv))
        if argv[1:] != ["start", "-ai", CONTAINER]:
            raise AssertionError("worker launch is not the owned attached container")
        return self.child

    @staticmethod
    def assert_safe_process(kwargs):
        if kwargs.get("shell", False):
            raise AssertionError("Docker commands must not pass through a shell")


class ExecutorFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runner = self.root / "runner"
        entrypoint = self.runner / "buddha" / "native_worker.py"
        entrypoint.parent.mkdir(parents=True)
        entrypoint.write_text("# offline worker fixture\n", encoding="utf-8")
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()

    def spec(self, **changes):
        return ContainerSpec(
            **(
                {
                    "image_id": IMAGE,
                    "role": "evaluator",
                    "mounts": (("/runner", self.runner), ("/inputs", self.inputs)),
                }
                | changes
            )
        )


class ExecutorInputTests(ExecutorFixture):
    def test_container_fields_validate_absent_mount_metadata_without_weakening_live_spec(self):
        from buddha import executor

        missing_agent = self.root / "retired-agent"
        fields = {
            "image_id": IMAGE,
            "role": "agent",
            "mounts": (("/runner", self.runner), ("/agent", missing_agent)),
            "runner_entrypoint": "buddha/native_worker.py",
            "image_environment": (("LANG", "C.UTF-8"),),
        }
        self.assertFalse(missing_agent.exists())
        with (
            patch.object(executor, "_root", side_effect=AssertionError("metadata opened root")),
            patch.object(executor, "file_hash", side_effect=AssertionError("metadata read file")),
        ):
            executor._validate_container_fields(**fields)
        # Constructing an executable specification still checks the actual roots.
        with self.assertRaises(FileNotFoundError):
            ContainerSpec(**fields)

    def test_container_fields_reject_malformed_metadata_before_filesystem_access(self):
        from buddha import executor

        fields = {
            "image_id": IMAGE,
            "role": "agent",
            "mounts": (("/runner", self.runner), ("/agent", self.root / "retired-agent")),
            "runner_entrypoint": "buddha/native_worker.py",
            "image_environment": (),
        }
        with (
            patch.object(executor, "_root", side_effect=AssertionError("metadata opened root")),
            patch.object(executor, "file_hash", side_effect=AssertionError("metadata read file")),
        ):
            for change in (
                {"image_id": "python:latest"},
                {"role": True},
                {"mounts": [("/runner", self.runner)]},
                {"mounts": (("/runner", Path("relative")),)},
                {"mounts": (("/runner", self.runner), ("/official", self.inputs))},
                {"mounts": (("/runner", self.runner), ("/runner", self.inputs))},
                {"mounts": (("/agent", self.inputs),)},
                {"runner_entrypoint": "../outside.py"},
                {"image_environment": [("LANG", "C")]},
                {"image_environment": (("LANG", "C"), ("LANG", "other"))},
                {"image_environment": (("LD_PRELOAD", "value"),)},
                {"image_environment": (("LANG", "line\nvalue"),)},
            ):
                with self.subTest(change=change), self.assertRaises(ReleaseError):
                    executor._validate_container_fields(**(fields | change))

    def test_public_errors_are_release_errors_and_configuration_is_immutable(self):
        self.assertTrue(issubclass(ExecutorError, ReleaseError))
        spec = self.spec()
        limits = Limits()
        self.assertEqual(spec.runner_entrypoint, "buddha/native_worker.py")
        self.assertEqual(spec.image_environment, ())
        self.assertEqual(limits.wall_seconds, 60)
        self.assertEqual(limits.memory_mib, 512)
        self.assertEqual(limits.scratch_mib, 128)
        self.assertEqual(limits.pids, 64)
        self.assertEqual(limits.cpus, 1)
        self.assertEqual(limits.max_stdout_bytes, 128 * 1024**2)
        self.assertEqual(limits.max_stderr_bytes, 64 * 1024)
        self.assertEqual(limits.max_frames, 100000)
        with self.assertRaises(FrozenInstanceError):
            spec.role = "agent"
        with self.assertRaises(FrozenInstanceError):
            limits.wall_seconds = 999

    def test_roles_have_distinct_allowed_mount_sets(self):
        official = self.root / "official"
        agent = self.root / "agent"
        official.mkdir()
        agent.mkdir()
        self.spec(mounts=(("/runner", self.runner), ("/official", official)))
        self.spec(role="agent", mounts=(("/runner", self.runner), ("/agent", agent)))
        for changes in (
            {"role": "unknown"},
            {"role": True},
            {"mounts": (("/runner", self.runner), ("/agent", agent))},
            {"role": "agent", "mounts": (("/runner", self.runner), ("/official", official))},
            {"mounts": (("/inputs", self.inputs),)},
            {"mounts": (("/runner", self.runner), ("/host-home", self.inputs))},
            {"mounts": (("/runner", self.runner), ("/runner", self.inputs))},
        ):
            with self.subTest(changes=changes), self.assertRaises(ReleaseError):
                self.spec(**changes)

    def test_mutable_relative_and_option_ambiguous_mounts_are_rejected(self):
        comma = self.root / "source,readonly=false"
        comma.mkdir()
        for mounts in (
            [("/runner", self.runner)],
            (["/runner", self.runner],),
            (("/runner", Path("relative")),),
            (("/runner/..", self.runner),),
            (("/runner", comma),),
            (("/runner", self.runner, "rw"),),
        ):
            with self.subTest(mounts=mounts), self.assertRaises(ReleaseError):
                self.spec(mounts=mounts)

    def test_image_identity_and_entrypoint_are_literal_bounded_inputs(self):
        for image in ("python:latest", "python@" + IMAGE, "sha256:" + "A" * 64, IMAGE + "x", ""):
            with self.subTest(image=image), self.assertRaises(ReleaseError):
                self.spec(image_id=image)
        for path in ("../outside.py", "/outside.py", "C:/outside.py", "buddha\\worker.py", ""):
            with self.subTest(path=path), self.assertRaises(ReleaseError):
                self.spec(runner_entrypoint=path)

    def test_image_environment_is_an_immutable_unique_text_inventory(self):
        self.spec(image_environment=(("LANG", "C.UTF-8"), ("PATH", "/usr/local/bin")))
        for values in (
            [("LANG", "C.UTF-8")],
            (["LANG", "C.UTF-8"],),
            (("LANG", "C"), ("LANG", "other")),
            (("BAD=NAME", "value"),),
            (("LANG", "line\nvalue"),),
            (("LANG", 1),),
        ):
            with self.subTest(values=values), self.assertRaises(ReleaseError):
                self.spec(image_environment=values)

    def test_every_limit_rejects_boolean_zero_negative_and_unbounded_values(self):
        for field in (
            "wall_seconds",
            "memory_mib",
            "scratch_mib",
            "pids",
            "cpus",
            "max_stdout_bytes",
            "max_stderr_bytes",
            "max_frames",
        ):
            for value in (True, 0, -1, math.inf, math.nan, "1"):
                with self.subTest(field=field, value=value), self.assertRaises(ReleaseError):
                    Limits(**{field: value})

    def test_explicit_unavailable_docker_fails_without_callback_or_child_text(self):
        called = []
        with self.assertRaises(ExecutorError) as failed:
            run_container(
                self.spec(),
                initial={"format": "offline-initial.v1"},
                handle=lambda frame: called.append(frame),
                docker=str(self.root / "absent-docker-executable"),
            )
        self.assertEqual(called, [])
        self.assertTrue(failed.exception.reason)
        self.assertIsNone(failed.exception.container_id)
        self.assertNotIn(str(self.root), str(failed.exception))

    def test_invalid_initial_and_callback_fail_before_any_docker_control(self):
        for initial in ([], None, {1: "coerced key"}, {"nan": math.nan}, {"bad": object()}):
            with (
                self.subTest(initial=initial),
                patch("subprocess.run") as control,
                patch("subprocess.Popen") as child,
                self.assertRaises(ReleaseError),
            ):
                run_container(self.spec(), initial=initial, handle=lambda frame: None)
            control.assert_not_called()
            child.assert_not_called()
        with (
            patch("subprocess.run") as control,
            patch("subprocess.Popen") as child,
            self.assertRaises(ReleaseError),
        ):
            run_container(self.spec(), initial={}, handle=None)
        control.assert_not_called()
        child.assert_not_called()

    def test_explicit_remote_or_malformed_docker_endpoint_fails_before_any_control(self):
        for endpoint in (
            "tcp://127.0.0.1:2375",
            "tcp://remote.example:2376",
            "ssh://remote.example",
            "unix://remote.example/sock",
            "npipe:////remote.example/pipe/docker_engine",
            ENDPOINT + "\nextra",
            "",
        ):
            with (
                self.subTest(endpoint=endpoint),
                patch("subprocess.run") as control,
                patch("subprocess.Popen") as child,
                self.assertRaises(ReleaseError),
            ):
                run_container(
                    self.spec(),
                    initial={},
                    handle=lambda frame: None,
                    docker=sys.executable,
                    docker_endpoint=endpoint,
                )
            control.assert_not_called()
            child.assert_not_called()


class ExecutorLifecycleTests(ExecutorFixture):
    def execute(self, fixture, handle=lambda frame: None):
        with (
            patch("buddha.executor._endpoint", return_value=ENDPOINT),
            patch("subprocess.run", side_effect=fixture.control),
            patch("subprocess.Popen", side_effect=fixture.popen),
        ):
            return run_container(
                fixture.spec,
                initial={"format": "offline-initial.v1"},
                handle=handle,
                limits=fixture.limits,
                docker=sys.executable,
            )

    def test_inspected_safe_owned_container_streams_frames_and_copies_configuration(self):
        raw = b'{"message":"one"}\n'
        diagnostics = b"unpublished binary diagnostics\xff"
        fixture = DockerFixture(self.spec(), Limits(), stdout=raw, stderr=diagnostics)
        seen = []

        def handle(frame):
            seen.append(frame)
            return {"reply": "received"}

        result = self.execute(fixture, handle)
        self.assertEqual(seen, [{"message": "one"}])
        self.assertEqual(
            (result.exit_code, result.container_id, result.image_id), (0, CONTAINER, IMAGE)
        )
        self.assertEqual(result.stdout_bytes, len(raw))
        self.assertEqual(result.stderr_bytes, len(diagnostics))
        self.assertEqual(result.stderr_sha256, hashlib.sha256(diagnostics).hexdigest())
        self.assertEqual(result.frame_count, 1)
        self.assertGreaterEqual(result.elapsed_seconds, 0)
        self.assertEqual(result.cleanup_status, "removed")
        self.assertNotIn("unpublished", repr(result))
        self.assertEqual(
            [json.loads(line) for line in fixture.child.stdin.saved.splitlines()],
            [{"format": "offline-initial.v1"}, {"reply": "received"}],
        )
        configuration = copy.deepcopy(result.configuration)
        result.configuration["role"] = "changed"
        self.assertEqual(result.configuration, configuration)
        create = next(argv[1:] for argv in fixture.calls if argv[1] == "create")
        for flag, value in (
            ("--pull", "never"),
            ("--network", "none"),
            ("--user", "65532:65532"),
            ("--cap-drop", "ALL"),
            ("--security-opt", "no-new-privileges:true"),
            ("--log-driver", "none"),
            ("--memory", "512m"),
            ("--memory-swap", "512m"),
        ):
            self.assertEqual(create[create.index(flag) + 1], value)
        self.assertIn("--read-only", create)
        self.assertNotIn("--privileged", create)
        self.assertNotIn("-t", create)
        self.assertEqual(
            create[create.index(IMAGE) + 1 :],
            [
                "-I",
                "-B",
                "-X",
                "pycache_prefix=/__absent_bytecode_cache",
                "/runner/buddha/native_worker.py",
            ],
        )
        self.assertEqual(fixture.started, [[sys.executable, "start", "-ai", CONTAINER]])
        self.assertIn([sys.executable, "rm", "-f", CONTAINER], fixture.calls)
        self.assertTrue(fixture.child.stdin.closed)
        self.assertTrue(fixture.child.stdout.closed)
        self.assertTrue(fixture.child.stderr.closed)

    def test_unsafe_inspection_never_starts_worker_or_calls_handler(self):
        mutations = (
            ("network", lambda r: r["HostConfig"].update(NetworkMode="bridge")),
            ("root", lambda r: r["Config"].update(User="0:0")),
            ("swap", lambda r: r["HostConfig"].update(MemorySwap=1024**3)),
            ("logs", lambda r: r["HostConfig"].update(LogConfig={"Type": "json-file"})),
            ("capability", lambda r: r["HostConfig"].update(CapAdd=["SYS_ADMIN"])),
            ("volume", lambda r: r["Config"].update(Volumes={"/extra": {}})),
            ("proxy", lambda r: r["Config"]["Env"].append("HTTPS_PROXY=private-value")),
            ("key", lambda r: r["Config"]["Env"].append("OPENAI_API_KEY=private-value")),
            (
                "bytecode_prefix",
                lambda r: r["Config"].update(Cmd=["-I", "-B", "/runner/buddha/native_worker.py"]),
            ),
            ("writable", lambda r: r["Mounts"][0].update(RW=True)),
            ("source", lambda r: r["HostConfig"]["Mounts"][0].update(Source="other-root")),
        )
        for name, modify in mutations:
            fixture = DockerFixture(self.spec(), Limits())
            fixture.modify = modify
            called = []
            with self.subTest(name=name), self.assertRaises(ExecutorError) as failed:
                self.execute(fixture, called.append)
            self.assertEqual(called, [])
            self.assertEqual(fixture.started, [])
            self.assertEqual(failed.exception.cleanup_status, "removed")
            self.assertNotIn("private-value", str(failed.exception))

    def test_bad_or_excessive_frames_stop_before_handler_and_remove_owned_container(self):
        cases = (
            (b"not JSON child-private-marker\n", Limits()),
            (b'{"duplicate":1,"duplicate":2}\n', Limits()),
            (b"[]\n", Limits()),
            (b'{"unterminated":true}', Limits()),
            (b'{"too-large":true}\n', Limits(max_stdout_bytes=2)),
            (b"{}\n{}\n", Limits(max_frames=1)),
        )
        for stdout, limits in cases:
            fixture = DockerFixture(self.spec(), limits, stdout=stdout)
            seen = []
            with self.subTest(stdout=stdout), self.assertRaises(ExecutorError) as failed:
                self.execute(fixture, seen.append)
            self.assertEqual(failed.exception.reason, "output")
            self.assertEqual(failed.exception.cleanup_status, "removed")
            self.assertLessEqual(len(seen), limits.max_frames)
            self.assertNotIn("child-private-marker", str(failed.exception))
            self.assertIn([sys.executable, "rm", "-f", CONTAINER], fixture.calls)

    def test_stderr_overflow_stops_without_publishing_diagnostic_text(self):
        fixture = DockerFixture(
            self.spec(), Limits(max_stderr_bytes=2), stderr=b"child-private-marker"
        )
        with self.assertRaises(ExecutorError) as failed:
            self.execute(fixture)
        self.assertEqual(failed.exception.reason, "diagnostics")
        self.assertEqual(failed.exception.cleanup_status, "removed")
        self.assertNotIn("child-private-marker", str(failed.exception))

    def test_stderr_delivered_after_worker_exit_still_enforces_its_byte_limit(self):
        fixture = DockerFixture(self.spec(), Limits(max_stderr_bytes=2))
        cleanup_waited = threading.Event()
        delivered = threading.Event()
        waits = []

        class LateDiagnostics:
            closed = False

            def read1(self, amount):
                if delivered.is_set():
                    return b""
                if not cleanup_waited.wait(2):
                    raise AssertionError("cleanup never waited for its owned process")
                delivered.set()
                return b"child-private-marker"

            def close(self):
                self.closed = True

        def wait(timeout=None):
            waits.append(timeout)
            if len(waits) >= 2:
                cleanup_waited.set()
            fixture.child.returncode = 0
            return 0

        fixture.child.stderr = LateDiagnostics()
        fixture.child.wait = wait
        with self.assertRaises(ExecutorError) as failed:
            self.execute(fixture)
        self.assertTrue(delivered.is_set())
        self.assertEqual(failed.exception.reason, "diagnostics")
        self.assertEqual(failed.exception.cleanup_status, "removed")
        self.assertNotIn("child-private-marker", str(failed.exception))

    def test_callback_failure_is_sanitized_and_still_removes_container(self):
        fixture = DockerFixture(self.spec(), Limits())

        def handle(frame):
            raise RuntimeError("child-private-marker")

        with self.assertRaises(ExecutorError) as failed:
            self.execute(fixture, handle)
        self.assertEqual(failed.exception.reason, "host")
        self.assertEqual(failed.exception.cleanup_status, "removed")
        self.assertNotIn("child-private-marker", str(failed.exception))

    def test_lost_create_acknowledgement_reconciles_exact_name_and_owner(self):
        fixture = DockerFixture(self.spec(), Limits())
        fixture.create_error = subprocess.TimeoutExpired("synthetic Docker", 10)
        with self.assertRaises(ExecutorError) as failed:
            self.execute(fixture)
        self.assertEqual(fixture.started, [])
        self.assertEqual(failed.exception.cleanup_status, "removed")
        self.assertEqual(failed.exception.container_id, CONTAINER)
        listing = next(argv for argv in fixture.calls if argv[1:3] == ["container", "ls"])
        name = fixture.record["Name"]
        owner = fixture.record["Config"]["Labels"][OWNER_LABEL]
        self.assertIn("name=^" + name + "$", listing)
        self.assertIn("label=" + OWNER_LABEL + "=" + owner, listing)
        self.assertIn([sys.executable, "rm", "-f", CONTAINER], fixture.calls)

    def test_foreign_owner_is_never_started_or_removed(self):
        fixture = DockerFixture(self.spec(), Limits())
        fixture.modify = lambda record: record["Config"]["Labels"].update(
            {OWNER_LABEL: "someone-else"}
        )
        with self.assertRaises(ExecutorError) as failed:
            self.execute(fixture)
        self.assertEqual(fixture.started, [])
        self.assertEqual(failed.exception.cleanup_status, "unknown")
        self.assertFalse(any(argv[1] in {"rm", "kill"} for argv in fixture.calls))

    def test_cleanup_failure_cannot_return_a_successful_result(self):
        fixture = DockerFixture(self.spec(), Limits())
        fixture.remove_error = OSError("child-private-marker")
        with self.assertRaises(ExecutorError) as failed:
            self.execute(fixture)
        self.assertEqual(failed.exception.reason, "cleanup")
        self.assertEqual(failed.exception.cleanup_status, "unknown")
        self.assertEqual(failed.exception.container_id, CONTAINER)
        self.assertNotIn("child-private-marker", str(failed.exception))

    def test_worker_timeout_waits_for_inflight_owner_callback_before_returning(self):
        fixture = DockerFixture(self.spec(), Limits(wall_seconds=0.1))
        entered = threading.Event()
        release = threading.Event()
        terminal = threading.Event()
        outcome = []

        def handle(frame):
            entered.set()
            if not release.wait(5):
                raise AssertionError("test callback release timed out")
            terminal.set()
            return {"reply": "durably completed"}

        def run():
            try:
                outcome.append(self.execute(fixture, handle))
            except BaseException as error:
                outcome.append(error)

        owner = threading.Thread(target=run, name="executor-test-owner")
        owner.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertTrue(fixture.killed.wait(2))
            self.assertTrue(owner.is_alive(), "executor abandoned its synchronous owner callback")
            self.assertFalse(terminal.is_set())
        finally:
            release.set()
            owner.join(timeout=5)
        self.assertFalse(owner.is_alive())
        self.assertTrue(terminal.is_set())
        self.assertEqual(len(outcome), 1)
        self.assertIsInstance(outcome[0], ExecutorError)
        self.assertEqual(outcome[0].reason, "timeout")
        self.assertEqual(outcome[0].cleanup_status, "removed")
        self.assertFalse(any(t.name.startswith("buddha-") for t in threading.enumerate()))


if __name__ == "__main__":
    unittest.main()
