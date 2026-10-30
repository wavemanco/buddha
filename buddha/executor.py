"""Owned Linux containers with bounded stdio; no model sender runs in a thread.

The wall limit terminates worker execution. A synchronous host callback must
finish its durable accounting before this function can return. Docker control
responses are trusted-daemon metadata, size checked after capture, not a claim
of bounded allocation against a malicious Docker daemon.
"""

import hashlib
import io
import math
import os
import queue
import re
import shutil

# The local Docker CLI is invoked with typed argv and without a shell.
import subprocess  # nosec B404
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, cast

from buddha.channel import ChannelError, read_frame, write_frame
from buddha.releases import MAX_JSON_BYTES, ReleaseError, _json, _load, _path, _root, file_hash

# Private container tmpfs; this path is never used for host temporary files.
CONTAINER_TMP = "/tmp"  # nosec B108
OWNER_LABEL = "org.buddha.executor"
IMAGE_ENV = frozenset(
    {
        "PATH",
        "LANG",
        "GPG_KEY",
        "PYTHON_VERSION",
        "PYTHON_SHA256",
        "VIRTUAL_ENV",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "PIP_DISABLE_PIP_VERSION_CHECK",
    }
)
WORKER_ENV = {
    "HOME": "/scratch/home",
    "TMPDIR": CONTAINER_TMP,
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


def _pre_cleanup_record(value: object) -> dict[str, object] | None:
    if type(value) is not tuple or len(value) != 2:
        return None
    stage, reason = value
    if any(type(item) is not str or len(item) > 64 for item in (stage, reason)):
        return None
    return {
        "format": "buddha.executor-pre-cleanup-failure.v1",
        "stage": stage
        if stage
        in {
            "image_inspect",
            "create",
            "container_verify",
            "start",
            "initial_frame",
            "exchange",
            "wait",
            "stdout",
            "stderr",
            "watchdog",
        }
        else "other",
        "reason": reason
        if reason
        in {
            "configuration",
            "control",
            "ownership",
            "launch",
            "output",
            "diagnostics",
            "timeout",
            "host",
            "cancelled",
        }
        else "other",
    }


class ExecutorError(ReleaseError):
    def __init__(
        self,
        reason: str,
        *,
        cleanup_status: str = "not_created",
        container_id: str | None = None,
        pre_cleanup_failure: tuple[str, str] | None = None,
    ) -> None:
        self.reason, self.cleanup_status, self.container_id = reason, cleanup_status, container_id
        self.pre_cleanup_failure = pre_cleanup_failure
        super().__init__(f"isolated execution stopped: {reason}; cleanup {cleanup_status}")

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "container_id": self.container_id,
            "cleanup_status": self.cleanup_status,
            "reason": self.reason,
        }
        try:
            if diagnostic := _pre_cleanup_record(self.pre_cleanup_failure):
                record["pre_cleanup_failure"] = diagnostic
        except BaseException:
            pass  # Optional diagnostics must not replace the original execution failure.
        return record


@dataclass(frozen=True)
class Limits:
    wall_seconds: float = 60
    memory_mib: int = 512
    scratch_mib: int = 128
    pids: int = 64
    cpus: float = 1
    max_stdout_bytes: int = 128 * 1024**2
    max_stderr_bytes: int = 64 * 1024
    max_frames: int = 100000

    def __post_init__(self) -> None:
        maxima = {
            "wall_seconds": 86400,
            "memory_mib": 65536,
            "scratch_mib": 65536,
            "pids": 1024,
            "cpus": 64,
            "max_stdout_bytes": 2**31 - 1,
            "max_stderr_bytes": 16 * 1024**2,
            "max_frames": 1000000,
        }
        for name, maximum in maxima.items():
            value = getattr(self, name)
            types = (int, float) if name in {"wall_seconds", "cpus"} else (int,)
            if type(value) not in types or not math.isfinite(value) or not 0 < value <= maximum:
                raise ExecutorError("configuration")


def _validate_container_fields(
    image_id: str,
    role: str,
    mounts: tuple[tuple[str, Path], ...],
    runner_entrypoint: str = "buddha/native_worker.py",
    image_environment: tuple[tuple[str, str], ...] = (),
) -> None:
    """Validate saved executor metadata without reopening retired mount roots."""
    if type(image_id) is not str or not re.fullmatch("sha256:[0-9a-f]{64}", image_id):
        raise ExecutorError("configuration")
    if type(role) is not str or role not in {"evaluator", "agent"}:
        raise ExecutorError("configuration")
    _path(runner_entrypoint)
    allowed = {"/runner", "/inputs", "/official" if role == "evaluator" else "/agent"}
    if type(mounts) is not tuple or not 1 <= len(mounts) <= 3:
        raise ExecutorError("configuration")
    seen = set()
    for pair in mounts:
        if type(pair) is not tuple or len(pair) != 2:
            raise ExecutorError("configuration")
        target, source = pair
        if type(target) is not str or target not in allowed or target in seen:
            raise ExecutorError("configuration")
        if not isinstance(source, Path) or not source.is_absolute() or "," in str(source):
            raise ExecutorError("configuration")
        seen.add(target)
    if "/runner" not in seen:
        raise ExecutorError("configuration")
    if type(image_environment) is not tuple or len(image_environment) > 64:
        raise ExecutorError("configuration")
    names = set()
    for env_pair in image_environment:
        if type(env_pair) is not tuple or len(env_pair) != 2:
            raise ExecutorError("configuration")
        name, value = env_pair
        if type(name) is not str or name not in IMAGE_ENV or name in names:
            raise ExecutorError("configuration")
        if (
            type(value) is not str
            or not value
            or len(value) > 8192
            or any(not 32 <= ord(char) <= 126 for char in value)
        ):
            raise ExecutorError("configuration")
        names.add(name)


@dataclass(frozen=True)
class ContainerSpec:
    image_id: str
    role: str
    mounts: tuple[tuple[str, Path], ...]
    runner_entrypoint: str = "buddha/native_worker.py"
    image_environment: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _validate_container_fields(
            self.image_id, self.role, self.mounts, self.runner_entrypoint, self.image_environment
        )
        for _, source in self.mounts:
            _root(source)
        file_hash(dict(self.mounts)["/runner"] / self.runner_entrypoint)


@dataclass(frozen=True)
class ExecutionResult:
    exit_code: int
    container_id: str
    image_id: str
    stdout_bytes: int
    stderr_bytes: int
    stderr_sha256: str
    frame_count: int
    elapsed_seconds: float
    _configuration: bytes = field(repr=False)
    cleanup_status: str = "removed"

    @property
    def configuration(self) -> dict[str, object]:
        return _load(self._configuration)


def _control(docker: str, args: list[str]) -> bytes:
    try:
        result = subprocess.run(  # nosec B603
            [docker, *args],
            capture_output=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        if result.returncode or len(result.stdout) + len(result.stderr) > MAX_JSON_BYTES:
            raise ExecutorError("control")
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        raise ExecutorError("control") from None


def _local_endpoint(value: object) -> str:
    if (
        type(value) is not str
        or not (
            re.fullmatch(r"npipe:////\./pipe/[A-Za-z0-9_.-]{1,128}", value)
            or re.fullmatch(r"unix:///[A-Za-z0-9_./-]{1,4096}", value)
        )
        or "/../" in value
    ):
        raise ExecutorError("configuration")
    return value


def _endpoint(docker: str) -> str:
    context = os.environ.get("DOCKER_CONTEXT")
    endpoint: object = os.environ.get("DOCKER_HOST") if not context else None
    if not endpoint:
        try:
            context = context or _control(docker, ["context", "show"]).decode("utf-8").strip()
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", context):
                raise ExecutorError("configuration")
            record = _load(
                _control(
                    docker,
                    ["context", "inspect", "--format", "{{json .Endpoints.docker}}", context],
                )
            )
            endpoint = record.get("Host")
        except (ValueError, UnicodeError):
            raise ExecutorError("configuration") from None
    return _local_endpoint(endpoint)


def _tmpfs(limits: Limits) -> dict[str, str]:
    tail = "noexec,nosuid,nodev,uid=65532,gid=65532,mode=0700"
    return {
        "/scratch": f"rw,size={limits.scratch_mib}m,{tail}",
        CONTAINER_TMP: f"rw,size=16m,{tail}",
    }


def _create_args(spec: ContainerSpec, limits: Limits, name: str, owner: str) -> list[str]:
    args = [
        "create",
        "--platform",
        "linux/amd64",
        "--pull",
        "never",
        "-i",
        "--name",
        name,
        "--label",
        f"{OWNER_LABEL}={owner}",
        "--hostname",
        "worker",
        "--network",
        "none",
        "--read-only",
        "--user",
        "65532:65532",
        "--workdir",
        "/scratch",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(limits.pids),
        "--memory",
        f"{limits.memory_mib}m",
        "--memory-swap",
        f"{limits.memory_mib}m",
        "--cpus",
        str(limits.cpus),
        "--ipc",
        "none",
        "--cgroupns",
        "private",
        "--log-driver",
        "none",
        "--no-healthcheck",
        "--ulimit",
        "nofile=128:128",
        "--ulimit",
        f"nproc={limits.pids}:{limits.pids}",
        "--entrypoint",
        "/opt/venv/bin/python",
    ]
    for target, source in spec.mounts:
        args += [
            "--mount",
            f"type=bind,source={source},target={target},readonly,bind-recursive=disabled",
        ]
    for target, options in _tmpfs(limits).items():
        args += ["--tmpfs", f"{target}:{options}"]
    for key, value in (dict(spec.image_environment) | WORKER_ENV).items():
        args += ["--env", f"{key}={value}"]
    return args + [
        spec.image_id,
        "-I",
        "-B",
        "-X",
        "pycache_prefix=/__absent_bytecode_cache",
        "/runner/" + spec.runner_entrypoint,
    ]


def _owned(record: dict[str, object], identity: str, name: str, owner: str) -> None:
    config = record.get("Config")
    if (
        record.get("Id") != identity
        or record.get("Name") != "/" + name
        or type(config) is not dict
        or type(config.get("Labels")) is not dict
        or config["Labels"].get(OWNER_LABEL) != owner
    ):
        raise ExecutorError("ownership")


def _configuration(record: dict[str, object], spec: ContainerSpec, limits: Limits) -> bytes:
    config, host = record.get("Config"), record.get("HostConfig")
    if type(config) is not dict or type(host) is not dict:
        raise ExecutorError("configuration")
    expected = {
        "NetworkMode": "none",
        "ReadonlyRootfs": True,
        "Privileged": False,
        "CapDrop": ["ALL"],
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
        "Tmpfs": _tmpfs(limits),
    }
    for name, value in expected.items():
        if host.get(name) != value:
            raise ExecutorError("configuration")
    for name in (
        "CapAdd",
        "Binds",
        "Devices",
        "DeviceRequests",
        "ExtraHosts",
        "Links",
        "VolumesFrom",
    ):
        if host.get(name):
            raise ExecutorError("configuration")
    if (
        record.get("Image") != spec.image_id
        or config.get("User") != "65532:65532"
        or config.get("WorkingDir") != "/scratch"
        or config.get("Entrypoint") != ["/opt/venv/bin/python"]
        or config.get("Cmd")
        != [
            "-I",
            "-B",
            "-X",
            "pycache_prefix=/__absent_bytecode_cache",
            "/runner/" + spec.runner_entrypoint,
        ]
        or config.get("Tty") is not False
        or config.get("OpenStdin") is not True
        or config.get("Volumes")
        or config.get("Healthcheck") not in (None, {"Test": ["NONE"]})
    ):
        raise ExecutorError("configuration")
    env = config.get("Env")
    if type(env) is not list or any(type(item) is not str or "=" not in item for item in env):
        raise ExecutorError("configuration")
    pairs = [item.split("=", 1) for item in env]
    if len(dict(pairs)) != len(pairs) or dict(pairs) != dict(spec.image_environment) | WORKER_ENV:
        raise ExecutorError("configuration")
    mounts, actual = host.get("Mounts"), record.get("Mounts")
    if type(mounts) is not list or type(actual) is not list or len(mounts) != len(spec.mounts):
        raise ExecutorError("configuration")
    expected_mounts = {target: str(source) for target, source in spec.mounts}
    found = {}
    for mount in mounts:
        if (
            type(mount) is not dict
            or mount.get("Type") != "bind"
            or mount.get("ReadOnly") is not True
            or mount.get("BindOptions") != {"NonRecursive": True}
            or mount.get("Target") in found
        ):
            raise ExecutorError("configuration")
        found[mount.get("Target")] = mount.get("Source")
    if found != expected_mounts or len(actual) != len(spec.mounts):
        raise ExecutorError("configuration")
    seen = set()
    for mount in actual:
        if (
            type(mount) is not dict
            or mount.get("Type") != "bind"
            or mount.get("RW") is not False
            or mount.get("Destination") not in expected_mounts
            or mount.get("Destination") in seen
        ):
            raise ExecutorError("configuration")
        seen.add(mount["Destination"])
    ulimits = host.get("Ulimits")
    wanted = [
        {"Name": "nofile", "Hard": 128, "Soft": 128},
        {"Name": "nproc", "Hard": limits.pids, "Soft": limits.pids},
    ]
    if type(ulimits) is not list or sorted(ulimits, key=lambda x: x["Name"]) != wanted:
        raise ExecutorError("configuration")
    return _json({"image": spec.image_id, "role": spec.role, "host": expected, "mounts": found})


def run_container(
    spec: ContainerSpec,
    *,
    initial: dict[str, object],
    handle: Callable[[dict[str, object]], dict[str, object] | None],
    limits: Limits | None = None,
    docker: str | None = None,
    docker_endpoint: str | None = None,
) -> ExecutionResult:
    limits = Limits() if limits is None else limits
    if (
        not isinstance(spec, ContainerSpec)
        or not isinstance(limits, Limits)
        or not callable(handle)
    ):
        raise ExecutorError("configuration")
    if type(initial) is not dict:
        raise ExecutorError("configuration")
    canonical = _load(_json(initial))
    if canonical != initial:
        raise ExecutorError("configuration")
    initial = canonical
    executable = shutil.which("docker") if docker is None else docker
    if (
        type(executable) is not str
        or not Path(executable).is_absolute()
        or not Path(executable).is_file()
    ):
        raise ExecutorError("unavailable")
    endpoint = (
        _endpoint(executable) if docker_endpoint is None else _local_endpoint(docker_endpoint)
    )

    def control(args: list[str]) -> bytes:
        return _control(executable, ["--host", endpoint, *args])

    def inspect_id(identity: str) -> dict[str, object]:
        return _load(control(["inspect", "--format", "{{json .}}", identity]))

    owner = uuid.uuid4().hex
    name = "buddha-" + owner
    identity: str | None = None
    process: subprocess.Popen[bytes] | None = None
    threads: list[threading.Thread] = []
    events: queue.Queue[dict[str, object] | None] = queue.Queue(maxsize=2)
    stop = threading.Event()
    lock = threading.Lock()
    failure: list[str] = []
    failure_stage = "exchange"
    counts = {"stdout": 0, "stderr": 0, "frames": 0}
    stderr_digest = hashlib.sha256()
    started = time.monotonic()
    proof = b""
    cleanup = "not_created"
    error: BaseException | None = None
    pre_cleanup_failure: tuple[str, str] | None = None
    stage = "image_inspect"
    exit_code = -1

    def fail(reason: str, *, stage: str = "exchange") -> None:
        nonlocal failure_stage
        with lock:
            if not failure:
                failure.append(reason)
                failure_stage = stage
        stop.set()

    def check_failure() -> None:
        with lock:
            if failure:
                raise ExecutorError(failure[0], pre_cleanup_failure=(failure_stage, failure[0]))

    def enqueue(value: dict[str, object] | None) -> None:
        while not stop.is_set():
            try:
                events.put(value, timeout=0.05)
                return
            except queue.Full:
                pass

    stdout_ceiling = limits.max_stdout_bytes

    def stdout(stream: io.BufferedReader) -> None:
        class Counted:
            def readline(self, size: int) -> bytes:
                raw = stream.readline(size)
                counts["stdout"] += len(raw)
                if counts["stdout"] > stdout_ceiling:
                    raise ChannelError("output limit")
                return raw

        try:
            while not stop.is_set():
                # EOF differs from an unterminated frame; peek only one byte.
                if not stream.peek(1):
                    enqueue(None)
                    return
                value = read_frame(cast(BinaryIO, Counted()))
                counts["frames"] += 1
                if counts["frames"] > limits.max_frames:
                    raise ChannelError("frame limit")
                enqueue(value)
        except Exception:
            fail("output", stage="stdout")

    def stderr(stream: io.BufferedReader) -> None:
        try:
            while raw := stream.read1(4096):
                counts["stderr"] += len(raw)
                stderr_digest.update(raw)
                if counts["stderr"] > limits.max_stderr_bytes:
                    fail("diagnostics", stage="stderr")
                    return
        except Exception:
            fail("diagnostics", stage="stderr")

    def watchdog() -> None:
        if not stop.wait(limits.wall_seconds):
            fail("timeout", stage="watchdog")
        if failure and identity:
            try:
                control(["kill", identity])
            except ExecutorError:
                pass  # Final owned removal remains mandatory and separately reported.

    try:
        image = inspect_id(spec.image_id)
        image_config = image.get("Config")
        if (
            image.get("Id") != spec.image_id
            or image.get("Os") != "linux"
            or image.get("Architecture") != "amd64"
            or type(image_config) is not dict
            or image_config.get("Volumes")
        ):
            raise ExecutorError("configuration")
        stage = "create"
        raw = control(_create_args(spec, limits, name, owner)).strip()
        if not re.fullmatch(b"[0-9a-f]{64}", raw):
            raise ExecutorError("launch")
        identity = raw.decode("ascii")
        stage = "container_verify"
        record = inspect_id(identity)
        _owned(record, identity, name, owner)
        proof_record = _load(_configuration(record, spec, limits))
        proof_record["engine_endpoint_sha256"] = hashlib.sha256(endpoint.encode()).hexdigest()
        proof = _json(proof_record)
        stage = "start"
        process = subprocess.Popen(  # nosec B603
            [executable, "--host", endpoint, "start", "-ai", identity],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise ExecutorError("launch")
        threads = [
            threading.Thread(target=stdout, args=(process.stdout,), name=name + "-stdout"),
            threading.Thread(target=stderr, args=(process.stderr,), name=name + "-stderr"),
            threading.Thread(target=watchdog, name=name + "-watchdog"),
        ]
        for thread in threads:
            thread.start()
        stage = "initial_frame"
        write_frame(cast(BinaryIO, process.stdin), initial)
        stage = "exchange"
        while not failure:
            try:
                frame = events.get(timeout=0.05)
            except queue.Empty:
                continue
            if frame is None:
                break
            check_failure()
            reply = handle(frame)  # Synchronous owner: never abandon a dispatched paid call.
            if failure:
                break
            if reply is not None:
                write_frame(cast(BinaryIO, process.stdin), reply)
        check_failure()
        process.stdin.close()
        stage = "wait"
        try:
            exit_code = process.wait(timeout=limits.wall_seconds)
        except subprocess.TimeoutExpired:
            fail("timeout", stage="wait")
            raise ExecutorError("timeout", pre_cleanup_failure=("wait", "timeout")) from None
        check_failure()
    except BaseException as caught:
        error = caught
        reason = "cancelled" if isinstance(caught, (KeyboardInterrupt, SystemExit)) else "host"
        try:
            if type(caught) is ExecutorError:
                value = caught.pre_cleanup_failure
                if value is None:
                    value = (stage, caught.reason)
            else:
                value = (stage, reason)
            if diagnostic := _pre_cleanup_record(value):
                pre_cleanup_failure = (
                    cast(str, diagnostic["stage"]),
                    cast(str, diagnostic["reason"]),
                )
        except BaseException:
            pass  # Diagnostic capture cannot replace the failure or its mandatory cleanup.
        fail(reason, stage=stage)
    finally:
        stop.set()
        try:
            if error is None:
                with lock:
                    if failure:
                        pre_cleanup_failure = (failure_stage, failure[0])
        except BaseException:
            pass  # Observe only failures recorded before cleanup begins.
        # Recover only our preselected UUID+label when create acknowledgement was lost.
        try:
            if identity is None:
                ids = control(
                    [
                        "container",
                        "ls",
                        "-a",
                        "--no-trunc",
                        "--format",
                        "{{.ID}}",
                        "--filter",
                        "name=^/" + name + "$",
                        "--filter",
                        f"label={OWNER_LABEL}={owner}",
                    ],
                ).split()
                if len(ids) == 1 and re.fullmatch(b"[0-9a-f]{64}", ids[0]):
                    identity = ids[0].decode("ascii")
                elif ids:
                    raise ExecutorError("ownership")
            if identity:
                _owned(inspect_id(identity), identity, name, owner)
                control(["rm", "-f", identity])
                cleanup = "removed"
        except BaseException:
            cleanup = "unknown"
        if process is not None:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.SubprocessError):
                    cleanup = "unknown"
            except (OSError, subprocess.SubprocessError):
                cleanup = "unknown"
        for thread in threads:
            thread.join(timeout=12)
            if thread.is_alive():
                cleanup = "unknown"
        if process is not None and all(not thread.is_alive() for thread in threads):
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        cleanup = "unknown"
        if error is None and failure:
            error = ExecutorError(failure[0])
    if cleanup == "unknown":
        raise ExecutorError(
            "cleanup",
            cleanup_status=cleanup,
            container_id=identity,
            pre_cleanup_failure=pre_cleanup_failure,
        ) from None
    if error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise error
        reason = error.reason if isinstance(error, ExecutorError) else "host"
        raise ExecutorError(reason, cleanup_status=cleanup, container_id=identity) from None
    if identity is None:
        raise ExecutorError("launch", cleanup_status=cleanup)
    return ExecutionResult(
        exit_code,
        identity,
        spec.image_id,
        counts["stdout"],
        counts["stderr"],
        stderr_digest.hexdigest(),
        counts["frames"],
        time.monotonic() - started,
        proof,
    )
