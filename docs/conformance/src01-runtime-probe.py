"""Build/probe the local SRC-01 stdlib image without downloads or model calls.

See docs/SOURCE-RUNTIME.md. Build creates a new private directory. Probe requires
an unused output path and reuses the byte-sealed original eleven-case harness.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.executor import (  # noqa: E402
    ContainerSpec,
    Limits,
    _endpoint,
    run_container,
)
from buddha.releases import _root  # noqa: E402

BASE = "python@sha256:3121f8b0804aa3698ab750d9a39ea4a42657a385c9b133722b915e55c51551a6"
OLD_PROBE_SHA = "d9fba9037c228b5b8f72c718f2245c65ef91cf955e6615c32a78bb1787d2d797"
HERE = ROOT / "docs/conformance"


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def save(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)


def control(command, *, environment=None, timeout=15):
    result = subprocess.run(  # nosec B603
        command,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    require(len(result.stdout) + len(result.stderr) <= 32 * 1024**2, "control_output")
    return result


def docker():
    executable = shutil.which("docker")
    require(executable is not None, "docker_unavailable")
    executable = str(Path(executable).resolve())
    return executable, _endpoint(executable)


AUDIT_WORKER = """import hashlib,json,sys
from pathlib import Path
initial=json.loads(sys.stdin.buffer.readline())
raw=Path("/opt/runtime-audit.py").read_bytes()
if hashlib.sha256(raw).hexdigest()!=initial["helper_sha256"]:
    raise RuntimeError("audit_source")
namespace={"__name__":"runtime_audit"}
exec(compile(raw,"/opt/runtime-audit.py","exec"),namespace)
audit=namespace["collect_audit"]()
measured=(json.dumps(audit,sort_keys=True,separators=(",",":"))+"\\n").encode()
stored=Path("/opt/runtime-manifest.json").read_bytes()
if measured!=stored:
    raise RuntimeError("fresh_inventory_changed")
print(json.dumps({"audit":audit,"manifest_sha256":hashlib.sha256(stored).hexdigest()}),flush=True)
"""

TEST_WORKER = """import io,json,runpy,sys,unittest
sys.stdin.buffer.readline()
namespace=runpy.run_path("/runner/tests/test_src01_runtime.py",run_name="runtime_test_fixture")
suite=unittest.defaultTestLoader.loadTestsFromTestCase(namespace["SourceRuntimeTests"])
result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=2).run(suite)
print(json.dumps({"tests":result.testsRun,"skipped":len(result.skipped),
                 "failures":len(result.failures),"errors":len(result.errors)}),flush=True)
if not result.wasSuccessful():
    raise SystemExit(1)
"""

SOURCE_WORKER = """import hashlib,importlib.util,json,sys
from pathlib import Path
initial=json.loads(sys.stdin.buffer.readline())
raw=Path("/agent/candidate.py").read_bytes()
if hashlib.sha256(raw).hexdigest()!=initial["source_sha256"]:
    raise RuntimeError("candidate_source")
namespace={"__name__":"literal_runtime_fixture"}
exec(compile(raw,"/agent/candidate.py","exec"),namespace)
task=json.loads(Path("/inputs/task.json").read_bytes())
answer=namespace["generate"](task)
print(json.dumps({"source_sha256":hashlib.sha256(raw).hexdigest(),"answer":answer,
                 "selected_task":task,"third_party_found":[name for name in
                 ("pip","setuptools","openai","anthropic","torch","numpy")
                 if importlib.util.find_spec(name) is not None]}),flush=True)
"""


def single(runtime, runner, entrypoint, *, initial, mounts=()):
    observed = []
    result = run_container(
        ContainerSpec(
            runtime["image_id"],
            "agent",
            (("/runner", runner), *mounts),
            entrypoint,
            tuple(tuple(value.split("=", 1)) for value in runtime["config"]["Env"]),
        ),
        initial=initial,
        handle=lambda frame: observed.append(frame),
        limits=Limits(
            wall_seconds=15,
            memory_mib=128,
            scratch_mib=16,
            pids=16,
            cpus=0.5,
            max_stdout_bytes=16 * 1024**2,
            max_stderr_bytes=8192,
            max_frames=2,
        ),
    )
    require(result.exit_code == 0 and result.cleanup_status == "removed", "worker_exit")
    require(len(observed) == 1, "worker_frames")
    report = asdict(result)
    report.pop("_configuration")
    report["configuration"] = result.configuration
    return observed[0], report


def fresh_audit(runtime):
    with tempfile.TemporaryDirectory(prefix="buddha-src-audit-") as temporary:
        runner = Path(temporary)
        (runner / "audit.py").write_text(AUDIT_WORKER, encoding="utf-8")
        return single(
            runtime,
            runner,
            "audit.py",
            initial={"helper_sha256": runtime["audit_helper"]["sha256"]},
        )


def build(directory):
    require(directory.is_absolute(), "absolute_build_directory_required")
    _root(directory.parent)
    directory.mkdir()
    context = directory / "context"
    client = directory / "docker-client"
    context.mkdir()
    client.mkdir()
    sources = {
        "Dockerfile": (HERE / "src01-runtime.Dockerfile").read_bytes(),
        "runtime-audit.py": (HERE / "src01-runtime-audit.py").read_bytes(),
    }
    for name, raw in sources.items():
        save(context / name, raw)
    save(context / ".dockerignore", b"*\n!Dockerfile\n!runtime-audit.py\n")
    executable, endpoint = docker()
    plugins = Path(executable).parent.parent / "cli-plugins"
    if os.name == "nt":
        plugins = Path(os.environ["ProgramFiles"]) / "Docker/cli-plugins"
    require(plugins.is_dir(), "local_buildx_plugins_required")
    save(client / "config.json", encoded({"cliPluginsExtraDirs": [str(plugins)]}))
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    environment["DOCKER_BUILDKIT"] = "1"
    prefix = [executable, "--config", str(client), "--host", endpoint]
    base = control([*prefix, "image", "inspect", BASE], environment=environment)
    require(base.returncode == 0, "pinned_local_base_required")
    save(directory / "base-inspect.json", base.stdout)
    iid = directory / "image-id.txt"
    command = [
        *prefix,
        "build",
        "--pull=false",
        "--network=none",
        "--no-cache",
        "--platform=linux/amd64",
        "--progress=plain",
        "--iidfile",
        str(iid),
    ]
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ):
        command += ["--build-arg", name + "="]
    command += [str(context)]
    result = control(command, environment=environment, timeout=120)
    save(directory / "build.stdout", result.stdout)
    save(directory / "build.stderr", result.stderr)
    save(directory / "build-exit.json", encoded({"exit_code": result.returncode}))
    require(result.returncode == 0, "build_failed")
    image = iid.read_text(encoding="utf-8").strip()
    inspected = control([*prefix, "image", "inspect", image], environment=environment)
    require(inspected.returncode == 0, "image_inspect")
    save(directory / "image-inspect.json", inspected.stdout)
    image_record = json.loads(inspected.stdout)[0]
    require(
        image_record["Id"] == image
        and image_record["Os"] == "linux"
        and image_record["Architecture"] == "amd64",
        "image_identity",
    )
    runtime = {
        "format": "buddha.src01-runtime-environment.v1",
        "image_id": image,
        "base": BASE,
        "config": image_record["Config"],
        "audit_helper": {
            "path": "/opt/runtime-audit.py",
            "sha256": sha(sources["runtime-audit.py"]),
        },
        "build_context_sha256": {name: sha(raw) for name, raw in sources.items()},
        "docker_sha256": sha(Path(executable).read_bytes()),
        "endpoint_sha256": sha(endpoint.encode()),
        "build_network": "none",
        "model_calls": 0,
    }
    row, execution = fresh_audit(runtime)
    inventory = encoded(row["audit"])
    require(sha(inventory) == row["manifest_sha256"], "manifest_identity")
    save(directory / "installed-runtime.json", inventory)
    save(directory / "audit-execution.json", encoded(execution))
    runtime["installed_manifest"] = {
        "sha256": sha(inventory),
        "bytes": len(inventory),
        "base_entries": len(row["audit"]["base_inventory"]),
        "venv_entries": len(row["audit"]["venv_inventory"]),
    }
    require(
        all((context / name).read_bytes() == raw for name, raw in sources.items()),
        "build_context_changed",
    )
    save(directory / "environment.json", encoded(runtime))
    return runtime


def probe(environment, output):
    require(output.is_absolute() and output.is_relative_to(ROOT), "output_must_be_in_checkout")
    _root(output.parent)
    require(not output.exists(), "unused_output_required")
    environment_raw = environment.read_bytes()
    runtime = json.loads(environment_raw)
    sources = {
        path.relative_to(ROOT).as_posix(): sha(path.read_bytes())
        for path in (
            Path(__file__),
            HERE / "src01-runtime-audit.py",
            HERE / "src01-runtime.Dockerfile",
            ROOT / "tests/test_src01_runtime.py",
            ROOT / "buddha/executor.py",
            ROOT / "buddha/channel.py",
            ROOT / "buddha/releases.py",
        )
    }
    require(
        runtime["audit_helper"]["sha256"] == sources["docs/conformance/src01-runtime-audit.py"],
        "environment_helper_identity",
    )
    require(
        runtime["build_context_sha256"]
        == {
            "Dockerfile": sources["docs/conformance/src01-runtime.Dockerfile"],
            "runtime-audit.py": sources["docs/conformance/src01-runtime-audit.py"],
        },
        "environment_recipe_identity",
    )
    row, execution = fresh_audit(runtime)
    require(
        row["manifest_sha256"] == runtime["installed_manifest"]["sha256"],
        "installed_inventory_changed",
    )
    old_path = HERE / "nb02c3-executor-probe.py"
    raw = old_path.read_bytes()
    require(sha(raw) == OLD_PROBE_SHA, "reviewed_hostile_probe_identity")
    hostile_output = output.with_name(output.stem + "-hostile.json")
    require(not hostile_output.exists(), "unused_hostile_output_required")
    module = ModuleType("src01_reused_executor_probe")
    module.__file__ = str(old_path)
    # Only the byte-sealed reviewed engineering harness executes on the host.
    # Candidate source is executed solely by SOURCE_WORKER inside the container.
    exec(compile(raw, str(old_path), "exec"), module.__dict__)  # nosec B102
    module.ENVIRONMENT = environment
    module.EVIDENCE = hostile_output
    module.main()
    hostile = json.loads(hostile_output.read_bytes())
    require(
        hostile["status"] == "pass"
        and hostile["case_count"] == 11
        and hostile["image_id"] == runtime["image_id"],
        "hostile_probe",
    )
    extras = []
    with tempfile.TemporaryDirectory(prefix="buddha-src-source-") as temporary:
        root = Path(temporary)
        runner, agent, inputs = (root / name for name in ("runner", "agent", "inputs"))
        for path in (runner, agent, inputs):
            path.mkdir()
        (runner / "tests").mkdir()
        (runner / "docs/conformance").mkdir(parents=True)
        (runner / "tests/test_src01_runtime.py").write_bytes(
            (ROOT / "tests/test_src01_runtime.py").read_bytes()
        )
        (runner / "docs/conformance/src01-runtime-audit.py").write_bytes(
            (HERE / "src01-runtime-audit.py").read_bytes()
        )
        (runner / "unit.py").write_text(TEST_WORKER, encoding="utf-8")
        tested, result = single(runtime, runner, "unit.py", initial={})
        require(
            tested == {"tests": 10, "skipped": 0, "failures": 0, "errors": 0}, "linux_audit_tests"
        )
        extras.append(
            {"name": "actual_linux_audit_tests", "observations": tested, "execution": result}
        )
        (runner / "source.py").write_text(SOURCE_WORKER, encoding="utf-8")
        task = {"id": "single-offline-task", "prompt": "runtime fixture", "count": 1}
        (inputs / "task.json").write_bytes(encoded(task))
        for index, (source, expected) in enumerate(
            (
                (b'def generate(task):\n    return task["prompt"].upper()\n', "RUNTIME FIXTURE"),
                (b'def generate(task):\n    return task["prompt"][::-1]\n', "erutxif emitnur"),
            )
        ):
            (agent / "candidate.py").write_bytes(source)
            observed, result = single(
                runtime,
                runner,
                "source.py",
                initial={"source_sha256": sha(source)},
                mounts=(("/agent", agent), ("/inputs", inputs)),
            )
            require(
                observed
                == {
                    "source_sha256": sha(source),
                    "answer": expected,
                    "selected_task": task,
                    "third_party_found": [],
                },
                "literal_source",
            )
            require((agent / "candidate.py").read_bytes() == source, "literal_source_mutated")
            extras.append(
                {
                    "name": "literal_source_" + str(index),
                    "observations": observed,
                    "execution": result,
                }
            )
    require(old_path.read_bytes() == raw, "hostile_source_changed")
    require(environment.read_bytes() == environment_raw, "environment_changed")
    require(
        all(sha((ROOT / name).read_bytes()) == value for name, value in sources.items()),
        "probe_sources_changed",
    )
    result = {
        "format": "buddha.src01-runtime-proof.v1",
        "status": "pass",
        "environment_sha256": sha(environment_raw),
        "image_id": runtime["image_id"],
        "sources": sources,
        "audit_execution": execution,
        "installed_manifest_sha256": row["manifest_sha256"],
        "hostile": {
            "source_sha256": OLD_PROBE_SHA,
            "evidence_sha256": sha(hostile_output.read_bytes()),
            "case_count": 11,
            "evidence": hostile,
        },
        "extra_cases": extras,
        "real_model_calls": 0,
        "scope": "Runtime prerequisite only: no model gateway, production arbitrary-agent route, "
        "source evolution or universal host/kernel escape claim.",
    }
    save(output, encoded(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("--directory", type=Path, required=True)
    prover = commands.add_parser("probe")
    prover.add_argument("--environment", type=Path, required=True)
    prover.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        result = build(args.directory.absolute())
        print(
            json.dumps(
                {
                    "image_id": result["image_id"],
                    "environment": str(args.directory / "environment.json"),
                }
            )
        )
    else:
        result = probe(args.environment.absolute(), args.out.absolute())
        print(json.dumps({"status": result["status"], "out": str(args.out)}))
