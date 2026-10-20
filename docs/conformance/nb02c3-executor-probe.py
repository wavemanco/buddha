"""Real, bounded Docker confinement checks; no provider calls or image downloads.

Run once from PowerShell with ``python docs/conformance/nb02c3-executor-probe.py``.
It uses the already installed pinned runtime image, creates private temporary
fixtures/containers, and saves sanitized results under runs/reviews. It spends
no API money. Ctrl+C stops the probe and attempts owned-container cleanup.
The hostile fixture below is written as data and executed only inside Docker.
This is executor evidence, not official evaluator or universal host-escape proof.
"""

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.executor import (  # noqa: E402
    ContainerSpec,
    ExecutorError,
    Limits,
    _endpoint,
    run_container,
)
from buddha.releases import _json, _load, file_hash  # noqa: E402

ENVIRONMENT = ROOT / "docs/conformance/nb02c3-runtime-environment.json"
EVIDENCE = ROOT / "runs/reviews/nb02c3-executor-evidence.json"

# This literal is never imported, eval'd or executed by the host interpreter.
WORKER = r"""
import errno
import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

initial = json.loads(sys.stdin.buffer.readline(65536))
case = initial["case"]

def emit(value):
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()

def fields(path):
    return {
        key.rstrip(":"): value
        for key, value in (line.split(None, 1) for line in Path(path).read_text().splitlines())
    }

def denied_write(path):
    try:
        with open(path, "ab") as output:
            output.write(b"forbidden mutation")
    except OSError as error:
        return error.errno in {errno.EROFS, errno.EACCES, errno.EPERM}
    return False

def denied_socket(family, kind, destination):
    try:
        with socket.socket(family, kind) as connection:
            connection.settimeout(0.25)
            if kind == socket.SOCK_DGRAM:
                connection.sendto(b"offline-isolation-probe", destination)
            else:
                connection.connect(destination)
    except OSError as error:
        return {"denied": True, "errno": error.errno}
    return {"denied": False, "errno": None}

if case == "canary":
    emit({"case": case, "ready": True})
    reply = json.loads(sys.stdin.buffer.readline(65536))
    assert reply == {"release": True}
elif case in {"evaluator_boundary", "agent_boundary"}:
    status = fields("/proc/self/status")
    role = initial["role"]
    private_names = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "BUDDHA_HOST_PRIVATE_SENTINEL")
    proxies = [name for name in os.environ if name.lower().endswith("_proxy")]
    mounts = [line.split(" ")[4] for line in Path("/proc/self/mountinfo").read_text().splitlines()]
    expected_mount = "/official" if role == "evaluator" else "/agent"
    forbidden_mount = "/agent" if role == "evaluator" else "/official"
    cgroup = Path("/sys/fs/cgroup")
    result = {
        "case": case,
        "uid": os.getuid(), "gid": os.getgid(), "cwd": os.getcwd(),
        "caps_effective": int(status["CapEff"], 16),
        "no_new_privileges": int(status["NoNewPrivs"]),
        "seccomp": int(status["Seccomp"]),
        "memory_max": int((cgroup / "memory.max").read_text()),
        "swap_max": int((cgroup / "memory.swap.max").read_text()),
        "pids_max": int((cgroup / "pids.max").read_text()),
        "cpu_max": (cgroup / "cpu.max").read_text().split(),
        "root_write_denied": denied_write("/root-write-probe"),
        "runner_write_denied": denied_write("/runner/probe.py"),
        "inputs_write_denied": denied_write("/inputs/task.json"),
        "role_write_denied": denied_write(expected_mount + "/public.txt"),
        "selected_role_fixture_readable": (
            Path(expected_mount + "/public.txt").read_text() == "public fixture"
        ),
        "opposite_role_absent": not Path(forbidden_mount).exists(),
        "private_env_absent": all(name not in os.environ for name in private_names),
        "proxy_values_empty": all(os.environ[name] == "" for name in proxies),
        "home_is_private_scratch": os.environ.get("HOME") == "/scratch/home",
        "docker_socket_absent": all(
            not Path(path).exists() for path in ("/var/run/docker.sock", "/run/docker.sock")
        ),
        "host_paths_absent": all(not Path(path).exists() for path in initial["forbidden_paths"]),
        "mount_targets": sorted(mounts),
        "host_mounts_absent": all(
            path not in mounts for path in ("/host", "/host-home", "/final", "/final-data")
        ),
        "input_is_single_task": json.loads(Path("/inputs/task.json").read_text()) == {
            "id": "fixture-one", "prompt": "offline fixture", "count": 2
        },
    }
    emit(result)
elif case == "network":
    os.environ["RES_OPTIONS"] = "attempts:1 timeout:1"
    outcomes = {
        "ipv4_tcp": denied_socket(socket.AF_INET, socket.SOCK_STREAM, ("192.0.2.1", 80)),
        "ipv4_udp": denied_socket(socket.AF_INET, socket.SOCK_DGRAM, ("192.0.2.1", 53)),
        "ipv6_tcp": denied_socket(socket.AF_INET6, socket.SOCK_STREAM, ("2001:db8::1", 80)),
        "ipv6_udp": denied_socket(socket.AF_INET6, socket.SOCK_DGRAM, ("2001:db8::1", 53)),
    }
    try:
        socket.getaddrinfo("example.com", 443)
        outcomes["dns"] = {"denied": False}
    except OSError as error:
        outcomes["dns"] = {"denied": True, "errno": error.errno}
    for name, port in (("alternate_http", 8080), ("alternate_https", 8443)):
        transport = http.client.HTTPConnection if port == 8080 else http.client.HTTPSConnection
        connection = transport("192.0.2.1", port, timeout=0.25)
        try:
            connection.request("GET", "/offline-isolation-probe")
            outcomes[name] = {"denied": False}
        except OSError as error:
            outcomes[name] = {"denied": True, "errno": error.errno}
        finally:
            connection.close()
    interfaces = sorted(path.name for path in Path("/sys/class/net").iterdir())
    emit({"case": case, "interfaces": interfaces, "outcomes": outcomes})
elif case == "source_bytecode":
    prefix_absent = (
        sys.pycache_prefix == "/__absent_bytecode_cache"
        and not Path(sys.pycache_prefix).exists()
    )
    sys.path.insert(0, "/runner")
    import helper
    emit({
        "case": case, "source_value": helper.VALUE,
        "cache_tag": sys.implementation.cache_tag,
        "prefix": sys.pycache_prefix, "prefix_absent": prefix_absent,
        "cached_path": helper.__cached__,
        "adjacent_poison_cache_present": any(
            (Path("/runner") / "__pycache__").glob("helper.*.pyc")
        ),
    })
elif case == "scratch":
    written = 0
    denied = False
    try:
        with open("/scratch/fill", "wb", buffering=0) as output:
            for _ in range(initial["scratch_mib"] + 2):
                written += output.write(b"x" * (1024 * 1024))
    except OSError as error:
        denied = error.errno in {errno.ENOSPC, errno.EDQUOT}
    Path("/scratch/fill").unlink()
    Path("/scratch/attempt.sh").write_text("#!/bin/sh\nexit 0\n")
    os.chmod("/scratch/attempt.sh", 0o700)
    noexec = False
    try:
        subprocess.run(["/scratch/attempt.sh"], check=False, timeout=1)
    except OSError as error:
        noexec = error.errno in {errno.EACCES, errno.EPERM}
    emit({"case": case, "space_denied": denied, "written": written, "noexec": noexec})
elif case == "cpu_throttle":
    before = fields("/sys/fs/cgroup/cpu.stat")
    started = time.monotonic()
    while time.monotonic() - started < 1.25:
        pass
    after = fields("/sys/fs/cgroup/cpu.stat")
    emit({
        "case": case,
        "throttled_periods": int(after["nr_throttled"]) - int(before["nr_throttled"]),
        "usage_usec": int(after["usage_usec"]) - int(before["usage_usec"]),
    })
elif case == "descendant_timeout":
    child = os.fork()
    if child == 0:
        os.setsid()
        while True:
            pass
    emit({"case": case, "descendant_created": True, "pid": child})
    while True:
        pass
elif case == "stdout_unterminated":
    sys.stdout.buffer.write(b"x" * (32 * 1024 * 1024 + 1))
    sys.stdout.buffer.flush()
elif case == "stderr_flood":
    for _ in range(64):
        sys.stderr.buffer.write(b"x" * 4096)
        sys.stderr.buffer.flush()
elif case == "memory_pressure":
    cgroup = Path("/sys/fs/cgroup/memory.events")
    before = fields(cgroup)
    emit({"case": case, "started": True})
    code = "import time; blocks=[bytearray(4*1024*1024) for _ in range(64)]; time.sleep(2)"
    child = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", code],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        returned = child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        returned = child.wait(timeout=2)
    after = fields(cgroup)
    emit({
        "case": case, "child_exit": returned,
        "oom_kills": int(after["oom_kill"]) - int(before["oom_kill"]),
        "memory_limit_events": int(after["max"]) - int(before["max"]),
    })
elif case == "pid_pressure":
    children = []
    denied = False
    try:
        for _ in range(initial["pids"] * 2):
            try:
                child = os.fork()
            except OSError as error:
                denied = error.errno == errno.EAGAIN
                break
            if child == 0:
                time.sleep(5)
                os._exit(0)
            children.append(child)
    finally:
        for child in children:
            os.kill(child, signal.SIGKILL)
        for child in children:
            os.waitpid(child, 0)
    emit({"case": case, "denied": denied, "spawned": len(children)})
else:
    raise RuntimeError("unknown isolated probe case")
"""


class ProbeFailure(Exception):
    """Only fixed probe reason codes are exposed in evidence."""


def require(value, reason):
    if not value:
        raise ProbeFailure(reason)


def control(docker, endpoint, args, *, missing=False):
    result = subprocess.run(
        [docker, "--host", endpoint, *args],
        capture_output=True,
        check=False,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if missing:
        require(result.returncode != 0, "owned_container_still_exists")
        listing = control(
            docker,
            endpoint,
            [
                "container",
                "ls",
                "-a",
                "--no-trunc",
                "--format",
                "{{.ID}}",
                "--filter",
                "id=" + args[-1],
            ],
        )
        require(not listing.strip(), "owned_container_still_listed")
        return None
    require(result.returncode == 0, "probe_control_failed")
    require(len(result.stdout) < 1024 * 1024, "probe_control_oversized")
    return result.stdout


def main():
    runtime = _load(ENVIRONMENT.read_bytes())
    docker = shutil.which("docker")
    require(docker is not None, "docker_unavailable")
    endpoint = _endpoint(docker)
    image = runtime["image_id"]
    image_environment = tuple(item.split("=", 1) for item in runtime["config"]["Env"])
    image_environment = tuple((key, value) for key, value in image_environment)
    info = json.loads(control(docker, endpoint, ["info", "--format", "{{json .}} "]))
    evidence = {
        "format": "buddha.review.nb02c3-executor-confinement.v1",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "image_id": image,
        "engine": {
            key: info[key]
            for key in (
                "ID",
                "ServerVersion",
                "OSType",
                "Architecture",
                "KernelVersion",
                "CgroupVersion",
                "SecurityOptions",
            )
        },
        "docker_sha256": file_hash(Path(docker)),
        "endpoint_sha256": hashlib.sha256(endpoint.encode()).hexdigest(),
        "sources": {
            str(path.relative_to(ROOT)): file_hash(path)
            for path in (
                Path(__file__).resolve(),
                ENVIRONMENT,
                ROOT / "buddha/executor.py",
                ROOT / "buddha/channel.py",
            )
        },
        "worker_sha256": hashlib.sha256(WORKER.encode()).hexdigest(),
        "cases": [],
        "scope": (
            "real bounded Linux Docker executor fixtures; no paid calls, native evaluator/agent "
            "conformance, full scientific readiness or universal host-escape claim"
        ),
        "limitations": [
            "Docker daemon/CLI and host kernel trusted",
            "network failures plus loopback-only interfaces, not an exploit audit",
            "worker wall time does not bound synchronous host financial finalization",
            "resource cases exercise cgroup limits, not exhaustive denial-of-service resistance",
        ],
    }

    def save():
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_bytes(_json(evidence) + b"\n")

    save()
    base_limits = Limits(
        wall_seconds=8,
        memory_mib=128,
        scratch_mib=8,
        pids=16,
        cpus=0.5,
        max_stdout_bytes=2 * 1024**2,
        max_stderr_bytes=8192,
        max_frames=100,
    )
    synthetic = {
        "OPENAI_API_KEY": "offline-host-openai-not-a-real-key",
        "ANTHROPIC_API_KEY": "offline-host-anthropic-not-a-real-key",
        "BUDDHA_HOST_PRIVATE_SENTINEL": "offline-host-only-sentinel",
        "HTTP_PROXY": "http://offline-user:offline-password@invalid.example:8888",
        "HTTPS_PROXY": "http://offline-user:offline-password@invalid.example:8888",
    }
    with tempfile.TemporaryDirectory(prefix="buddha-executor-probe-") as temporary:
        root = Path(temporary)
        runner, inputs, official, agent, private = (
            root / name for name in ("runner", "inputs", "official", "agent", "host-private")
        )
        for path in (runner, inputs, official, agent, private):
            path.mkdir()
        (runner / "probe.py").write_text(WORKER, encoding="utf-8", newline="\n")
        helper = runner / "helper.py"
        helper.write_text("VALUE = 'poison'\n", encoding="utf-8", newline="\n")
        original = helper.stat()
        cache = runner / "__pycache__" / ("helper." + sys.implementation.cache_tag + ".pyc")
        cache.parent.mkdir()
        # Compile this trusted constant without importing or executing it on the host.
        py_compile.compile(
            str(helper),
            cfile=str(cache),
            dfile="/runner/helper.py",
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
        )
        helper.write_text("VALUE = 'source'\n", encoding="utf-8", newline="\n")
        os.utime(helper, ns=(original.st_atime_ns, original.st_mtime_ns))
        require(helper.stat().st_size == original.st_size, "cache_fixture_size")
        evidence["source_cache_fixture"] = {
            "host_cache_tag": sys.implementation.cache_tag,
            "source_sha256": file_hash(helper),
            "adjacent_cache_sha256": file_hash(cache),
            "timestamp_and_size_collide": True,
            "scope": "trusted literal compiled only; no host import or execution",
        }
        (inputs / "task.json").write_text(
            '{"id":"fixture-one","prompt":"offline fixture","count":2}', encoding="utf-8"
        )
        for path in (official, agent):
            (path / "public.txt").write_text("public fixture", encoding="utf-8")
        (private / "final-data.txt").write_text(
            "offline host-only final sentinel", encoding="utf-8"
        )
        before = {
            path: file_hash(path)
            for path in (
                runner / "probe.py",
                helper,
                cache,
                inputs / "task.json",
                official / "public.txt",
                agent / "public.txt",
                private / "final-data.txt",
            )
        }

        def spec(role="evaluator", entrypoint="probe.py"):
            selected = official if role == "evaluator" else agent
            return ContainerSpec(
                image_id=image,
                role=role,
                mounts=(
                    ("/runner", runner),
                    ("/inputs", inputs),
                    ("/" + ("official" if role == "evaluator" else "agent"), selected),
                ),
                runner_entrypoint=entrypoint,
                image_environment=image_environment,
            )

        canary_ready = threading.Event()
        canary_release = threading.Event()
        canary_outcome = []
        canary_name = "canary-" + uuid.uuid4().hex + ".py"
        (runner / canary_name).write_text(WORKER, encoding="utf-8", newline="\n")

        def canary_handle(frame):
            require(frame == {"case": "canary", "ready": True}, "canary_protocol")
            canary_ready.set()
            require(canary_release.wait(55), "canary_release_deadline")
            return {"release": True}

        def canary_run():
            try:
                canary_outcome.append(
                    run_container(
                        spec(entrypoint=canary_name),
                        initial={"case": "canary"},
                        handle=canary_handle,
                        limits=Limits(
                            wall_seconds=55, memory_mib=64, scratch_mib=4, pids=8, cpus=0.25
                        ),
                        docker=docker,
                        docker_endpoint=endpoint,
                    )
                )
            except BaseException:
                canary_outcome.append(None)

        def canary_id():
            listing = control(
                docker,
                endpoint,
                ["container", "ls", "-q", "--no-trunc", "--filter", "label=org.buddha.executor"],
            )
            found = []
            for identity in listing.decode().split():
                command = json.loads(
                    control(
                        docker, endpoint, ["inspect", "--format", "{{json .Config.Cmd}}", identity]
                    )
                )
                if command == [
                    "-I",
                    "-B",
                    "-X",
                    "pycache_prefix=/__absent_bytecode_cache",
                    "/runner/" + canary_name,
                ]:
                    found.append(identity)
            require(len(found) == 1, "canary_identity")
            return found[0]

        def alive(identity):
            return (
                control(
                    docker, endpoint, ["inspect", "--format", "{{json .State.Running}}", identity]
                ).strip()
                == b"true"
            )

        def run_case(name, *, role="evaluator", limits=base_limits, expected_error=None):
            observed = []
            record = {"name": name, "role": role, "limits": asdict(limits)}
            initial = {
                "case": name,
                "role": role,
                "scratch_mib": limits.scratch_mib,
                "pids": limits.pids,
                "forbidden_paths": [
                    str(private),
                    str(Path.home()),
                    "/host-home",
                    "/final-data",
                    "/run/desktop/mnt/host/c/Users/arvik",
                ],
            }
            try:
                result = run_container(
                    spec(role),
                    initial=initial,
                    handle=lambda frame: observed.append(frame),
                    limits=limits,
                    docker=docker,
                    docker_endpoint=endpoint,
                )
                record.update(
                    exit_code=result.exit_code,
                    cleanup_status=result.cleanup_status,
                    container_id=result.container_id,
                    elapsed_seconds=result.elapsed_seconds,
                    stdout_bytes=result.stdout_bytes,
                    stderr_bytes=result.stderr_bytes,
                    frame_count=result.frame_count,
                    configuration_sha256=hashlib.sha256(_json(result.configuration)).hexdigest(),
                )
            except ExecutorError as error:
                record.update(
                    error=error.reason,
                    cleanup_status=error.cleanup_status,
                    container_id=error.container_id,
                )
            require(record["cleanup_status"] == "removed", "owned_cleanup_incomplete")
            require(record["container_id"] is not None, "owned_identity_missing")
            control(docker, endpoint, ["inspect", record["container_id"]], missing=True)
            require(alive(canary), "unrelated_canary_terminated")
            require(
                all(file_hash(path) == digest for path, digest in before.items()),
                "host_fixture_mutated",
            )
            record["observations"] = observed
            record["owned_container_absent"] = True
            record["unrelated_canary_alive"] = True
            evidence["cases"].append(record)
            save()
            if "error" in record:
                require(record["error"] == expected_error, "unexpected_executor_stop")
            else:
                require(expected_error is None, "expected_stop_not_observed")
                require(record["exit_code"] == 0, "unexpected_worker_exit")
            print(
                json.dumps({"case": name, "status": "completed", "count": len(evidence["cases"])}),
                flush=True,
            )
            return observed

        canary = None
        thread = threading.Thread(target=canary_run, name="host-executor-canary")
        with patch.dict(os.environ, synthetic):
            thread.start()
            try:
                require(canary_ready.wait(10), "canary_start")
                canary = canary_id()
                for role in ("evaluator", "agent"):
                    row = run_case(role + "_boundary", role=role)[0]
                    for field in (
                        "root_write_denied",
                        "runner_write_denied",
                        "inputs_write_denied",
                        "role_write_denied",
                        "selected_role_fixture_readable",
                        "opposite_role_absent",
                        "private_env_absent",
                        "proxy_values_empty",
                        "home_is_private_scratch",
                        "docker_socket_absent",
                        "host_paths_absent",
                        "host_mounts_absent",
                        "input_is_single_task",
                    ):
                        require(row[field], "boundary_" + field)
                    require(row["uid"] == row["gid"] == 65532, "nonroot_identity")
                    require(
                        row["caps_effective"] == 0
                        and row["no_new_privileges"] == 1
                        and row["seccomp"] == 2,
                        "process_security",
                    )
                    require(
                        row["memory_max"] == 128 * 1024**2
                        and row["swap_max"] == 0
                        and row["pids_max"] == 16,
                        "cgroup_limits",
                    )
                    quota, period = map(int, row["cpu_max"])
                    require(quota / period == base_limits.cpus, "cpu_cgroup_limit")
                row = run_case("source_bytecode")[0]
                require(row["cache_tag"] == sys.implementation.cache_tag, "cache_tag_incompatible")
                require(row["source_value"] == "source", "stale_bytecode_executed")
                require(row["adjacent_poison_cache_present"], "cache_fixture_missing")
                require(
                    row["prefix_absent"]
                    and row["cached_path"].startswith("/__absent_bytecode_cache/"),
                    "source_cache_prefix_not_enforced",
                )
                row = run_case("network")[0]
                require(row["interfaces"] == ["lo"], "unexpected_network_interface")
                require(
                    all(value["denied"] for value in row["outcomes"].values()),
                    "outbound_network_succeeded",
                )
                row = run_case("scratch")[0]
                require(
                    row["space_denied"] and row["written"] <= 8 * 1024**2 and row["noexec"],
                    "scratch_limit",
                )
                row = run_case("cpu_throttle")[0]
                require(row["throttled_periods"] > 0, "cpu_not_throttled")
                rows = run_case(
                    "descendant_timeout",
                    limits=Limits(wall_seconds=1.5, memory_mib=64, scratch_mib=4, pids=8, cpus=0.5),
                    expected_error="timeout",
                )
                require(rows and rows[0]["descendant_created"], "descendant_not_exercised")
                run_case("stdout_unterminated", expected_error="output")
                run_case("stderr_flood", expected_error="diagnostics")
                rows = run_case("memory_pressure")
                row = rows[-1]
                require(
                    row["child_exit"] == -9
                    and row["oom_kills"] >= 1
                    and row["memory_limit_events"] >= 1,
                    "memory_limit_not_exercised",
                )
                row = run_case("pid_pressure")[0]
                require(
                    row["denied"] and 0 < row["spawned"] < base_limits.pids * 2,
                    "pid_limit_not_exercised",
                )
            except BaseException as error:
                evidence["status"] = "failed"
                evidence["failure"] = (
                    str(error)
                    if isinstance(error, ProbeFailure)
                    else "probe_interrupted_or_unavailable"
                )
                save()
                raise
            finally:
                canary_release.set()
                thread.join(timeout=15)
                require(not thread.is_alive(), "canary_owner_not_reaped")
                require(
                    len(canary_outcome) == 1 and canary_outcome[0] is not None,
                    "canary_cleanup_failed",
                )
                require(
                    canary_outcome[0].container_id == canary
                    and canary_outcome[0].cleanup_status == "removed",
                    "canary_cleanup_identity",
                )
                control(docker, endpoint, ["inspect", canary], missing=True)
                evidence["canary"] = {
                    "id": canary,
                    "untouched_during_cases": True,
                    "final_cleanup": "removed",
                }
                save()
    evidence["status"] = "pass"
    evidence["case_count"] = len(evidence["cases"])
    save()
    print(
        json.dumps(
            {
                "status": "pass",
                "cases": evidence["case_count"],
                "evidence": str(EVIDENCE.relative_to(ROOT)),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        print('{"status":"failed","details":"sanitized evidence retained"}', flush=True)
        raise SystemExit(1) from None
