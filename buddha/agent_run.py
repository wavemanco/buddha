"""Host-owned fixed-seed execution; tasks and raw spending stay outside the agent.

This route imports no agent implementation or benchmark algorithm on the host.
Completed raw receipts replay through the original immutable Gateway owner.
"""

import base64
import hashlib
import os
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any, cast

from buddha import answers as answer_module
from buddha import channel, executor, releases, wire
from buddha.answers import Answers, TaskSet
from buddha.gateway import (
    CAPABILITIES,
    Gateway,
    GatewayCall,
    GatewayError,
    _read_manifest,
    execution_identity,
)
from buddha.ledger import BudgetExceeded, OperationConflict
from buddha.provider import BoundBreach, PendingOperation, ProviderUncertain
from buddha.releases import (
    MAX_JSON_BYTES,
    Release,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _root,
    _text,
    file_hash,
    inventory,
)

RUNNER_FILES = ("__init__", "channel", "releases", "wire", "agent_worker")
HOST_FILES = (*RUNNER_FILES, "executor", "answers", "agent_run")
# This route is only for the reviewed C3C1 seed. Evolved source requires SRC-01's
# separate minimal image and isolation gate, not this fixed-seed runtime.
FROZEN_SEED_SHA256 = "2b87bfe0d3c97ee45db2d45260985ffe0234eca93967f4689fb7c59f82603921"


class AgentRunError(ReleaseError):
    """The frozen generation owner, protocol or evidence is invalid."""


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _literal(value: object) -> str:
    if type(value) is not str:
        raise AgentRunError("agent output and instructions must be literal text")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise AgentRunError("agent text is not UTF-8") from None
    return value


class AgentSession:
    def __init__(self, gateway: Gateway, *, descriptor: Path, output: Path) -> None:
        self.gateway = gateway
        self.ran = self.ready = self.broken = False
        self.done: dict[str, object] | None = None
        self.stop_reason: str | None = None
        self.calls = {"requested": 0, "completed": 0, "stopped": 0}
        self.outputs: list[dict[str, object]] = []
        self.artifacts: dict[str, str] = {}
        self.partial = None
        try:
            if not isinstance(gateway, Gateway) or not isinstance(descriptor, Path):
                raise AgentRunError("generation needs a frozen Gateway and descriptor")
            if not isinstance(output, Path):
                raise AgentRunError("generation output must be a Path")
            self.output = output.absolute()
            record = _read_manifest(gateway.directory)
            if _sha(record) != gateway.manifest_sha256:
                raise AgentRunError("generation Gateway owner changed")
            execution_identity(gateway.directory, record)
            bindings = {
                _text(item["path"]): _digest(item["sha256"])
                for item in cast(list[dict[str, object]], _object(record["invocation"])["inputs"])
            }

            def consume(path: Path, maximum: int = MAX_JSON_BYTES) -> bytes:
                path = path.absolute()
                digest = file_hash(path, max_bytes=maximum)
                if bindings.get(str(path)) != digest:
                    raise AgentRunError("executing generation source or input is not frozen")
                with path.open("rb") as stream:
                    raw = stream.read(maximum + 1)
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise AgentRunError("generation input changed while consumed")
                return raw

            raw_descriptor = consume(descriptor)
            self.descriptor_sha256 = hashlib.sha256(raw_descriptor).hexdigest()
            description = _object(
                _load(raw_descriptor),
                {"format", "tasks", "config", "entrypoint", "executor", "profile"},
            )
            if description["format"] != "buddha.frozen-generation.v1":
                raise AgentRunError("unsupported generation descriptor")
            package = Path(__file__).absolute().parent
            for module in (answer_module, channel, executor, releases, wire):
                if Path(_text(module.__file__)).absolute() != package / (
                    module.__name__.split(".")[-1] + ".py"
                ):
                    raise AgentRunError("generation imports a different host implementation")
            for name in HOST_FILES:
                consume(package / (name + ".py"))
            trusted_seed = consume(package.parent / "agents/frozen_seed.py")
            if hashlib.sha256(trusted_seed).hexdigest() != FROZEN_SEED_SHA256:
                raise AgentRunError("trusted fixed seed differs from its reviewed source")
            task_bytes = consume(Path(_text(description["tasks"])))
            self.tasks_file_sha256 = hashlib.sha256(task_bytes).hexdigest()
            self.tasks = TaskSet.from_bytes(task_bytes)
            selected = Selection.from_bytes(_json(record["selection"]))
            if self.tasks.release_sha256 != selected.release_sha256:
                raise AgentRunError("generation tasks differ from the selected release")
            self.release = Release.from_record(selected.to_record()["release"])
            self.agent_sha256 = selected.agent_sha256
            self.config = _object(
                description["config"],
                {"provider", "model", "max_output_tokens", "instructions", "sampling"},
            )
            provider, maximum = self.config["provider"], self.config["max_output_tokens"]
            if (
                type(provider) is not str
                or provider not in {"openai", "anthropic"}
                or type(maximum) is not int
                or not 1 <= maximum <= 2**63 - 1
                or self.config["sampling"] not in {"regenerate", "in-context"}
                or len(_literal(self.config["instructions"])) > 4000
            ):
                raise AgentRunError("unsupported frozen generation configuration")
            _text(self.config["model"])
            self.profile = _object(description["profile"], {"capability", "profile_id"})
            capability, profile_id = (
                _text(self.profile["capability"]),
                _text(self.profile["profile_id"]),
            )
            if capability not in CAPABILITIES or CAPABILITIES[capability][0] != provider:
                raise AgentRunError("generation capability differs from the frozen provider")
            choices = _object(_object(record["profiles"])[capability])
            profile = _object(_object(choices["profiles"])[profile_id])
            spec = _object(profile["spec"])
            if any(
                spec[key] != self.config[key] for key in ("provider", "model", "max_output_tokens")
            ):
                raise AgentRunError("generation role differs from its host-owned model profile")
            self.entrypoint = _path(description["entrypoint"])
            if PurePosixPath(self.entrypoint).suffix != ".py":
                raise AgentRunError("agent entrypoint must be selected Python source")
            settings = _object(
                description["executor"],
                {
                    "image_id",
                    "role",
                    "mounts",
                    "runner_entrypoint",
                    "image_environment",
                    "limits",
                    "docker_endpoint",
                },
            )
            mounts, environment = settings["mounts"], settings["image_environment"]
            if (
                settings["role"] != "agent"
                or type(mounts) is not list
                or len(mounts) != 2
                or type(environment) is not list
                or any(type(pair) is not list or len(pair) != 2 for pair in [*mounts, *environment])
            ):
                raise AgentRunError("generation permits only agent and runner mounts")
            self.spec = executor.ContainerSpec(
                _text(settings["image_id"]),
                "agent",
                tuple((_text(pair[0]), Path(_text(pair[1]))) for pair in mounts),
                _path(settings["runner_entrypoint"]),
                tuple((_text(pair[0]), _text(pair[1])) for pair in environment),
            )
            roots = dict(self.spec.mounts)
            if set(roots) != {"/agent", "/runner"} or self.spec.runner_entrypoint != (
                "buddha/agent_worker.py"
            ):
                raise AgentRunError("generation uses the fixed isolated worker only")
            self.limits = executor.Limits(
                **cast(
                    dict[str, Any],
                    _object(settings["limits"], set(executor.Limits.__dataclass_fields__)),
                )
            )
            self.endpoint = executor._local_endpoint(settings["docker_endpoint"])
            self.inventories = {}
            owner_roots, components = (
                _object(record["roots"]),
                _object(selected.to_record()["components"]),
            )
            for role in ("agent", "runner"):
                root = roots["/" + role]
                found = inventory(root)
                if str(root) != owner_roots[role] or found != components[role]:
                    raise AgentRunError("actual generation mounts differ from their selection")
                if any(
                    PurePosixPath(name).suffix.lower() in {".pyc", ".pyo"}
                    or "__pycache__" in PurePosixPath(name).parts
                    for name in found
                ):
                    raise AgentRunError("generation source contains executable bytecode caches")
                self.inventories[role] = found
            expected_runner = {
                "buddha/" + name + ".py": file_hash(package / (name + ".py"))
                for name in RUNNER_FILES
            }
            if self.inventories["runner"] != expected_runner or self.inventories["agent"] != {
                self.entrypoint: FROZEN_SEED_SHA256
            }:
                raise AgentRunError("generation runner or seed source differs")
            self._frozen_configuration = self._configuration()
            self._activate(0)
            _root(self.output.parent)
            _path(self.output.name)
            with gateway.work(directory=self.output, kind="generation"):
                self.output.mkdir()
                self.partial = (self.output / "partial.jsonl").open("xb")
        except (ReleaseError, KeyError, TypeError, ValueError, OSError):
            raise AgentRunError(
                "generation owner, configuration or destination is invalid"
            ) from None

    def _configuration(self) -> bytes:
        return _json(
            {
                "gateway": [str(self.gateway.directory), self.gateway.manifest_sha256],
                "descriptor": self.descriptor_sha256,
                "tasks": self.tasks.fingerprint(),
                "tasks_file": self.tasks_file_sha256,
                "agent": self.agent_sha256,
                "config": self.config,
                "profile": self.profile,
                "entrypoint": self.entrypoint,
                "inventories": self.inventories,
                "output": str(self.output),
                "spec": {
                    "image": self.spec.image_id,
                    "role": self.spec.role,
                    "mounts": [[name, str(path)] for name, path in self.spec.mounts],
                    "entrypoint": self.spec.runner_entrypoint,
                    "environment": self.spec.image_environment,
                },
                "limits": asdict(self.limits),
                "endpoint": self.endpoint,
            }
        )

    def _activate(self, index: int) -> None:
        self.task_index = index
        task = self.tasks.tasks[index]
        self.worker = _load(
            _json(
                {
                    "type": "configure",
                    "format": "buddha.agent-worker.v1",
                    "roots": {"agent": "/agent", "runner": "/runner"},
                    "inventories": self.inventories,
                    "entrypoint": self.entrypoint,
                    "agent_sha256": self.agent_sha256,
                    "config": self.config,
                    "task": task.to_record(),
                    "task_index": index,
                }
            )
        )
        self._worker_bytes = _json(self.worker)
        self.sequence = self.delivered = 0
        self.ready = False
        self.done = None

    def _unchanged(self) -> None:
        if (
            self._configuration() != self._frozen_configuration
            or _json(self.worker) != self._worker_bytes
        ):
            raise AgentRunError("generation configuration changed after validation")
        execution_identity(self.gateway.directory)

    def handle(self, frame: dict[str, object]) -> dict[str, object] | None:
        self.gateway.assert_work(directory=self.output, kind="generation")
        try:
            self._unchanged()
            _object(frame)
            if self.broken or self.done is not None:
                raise AgentRunError("generation worker already ended")
            task = self.tasks.tasks[self.task_index]
            if frame.get("type") == "ready":
                _object(frame, {"type", "agent_sha256", "task_sha256"})
                if (
                    self.ready
                    or frame["agent_sha256"] != self.agent_sha256
                    or frame["task_sha256"] != _sha(task.to_record())
                ):
                    raise AgentRunError("generation ready identity differs")
                self.ready = True
                return None
            if frame.get("type") == "done":
                _object(frame, {"type", "status", "reason", "answers"})
                status, reason, values = frame["status"], frame["reason"], frame["answers"]
                if type(values) is not list:
                    raise AgentRunError("generation answers must be a literal ordered list")
                if status == "complete":
                    if (
                        not self.ready
                        or self.stop_reason is not None
                        or reason != "complete"
                        or self.delivered != task.count
                        or self.sequence != task.count
                        or len(values) != task.count
                    ):
                        raise AgentRunError("generation completion has incomplete call coverage")
                    result: dict[str, object] = {
                        "task_id": task.id,
                        "answers": [_literal(value) for value in values],
                    }
                    if len(self.outputs) != self.task_index:
                        raise AgentRunError("generation task order differs")
                    _root(self.output)
                    if self.partial is None:
                        raise AgentRunError("generation output stream is closed")
                    self.partial.write(_json(result) + b"\n")
                    self.partial.flush()
                    os.fsync(self.partial.fileno())
                    self.outputs.append(result)
                elif (
                    values
                    or (status == "stopped" and (reason != self.stop_reason or reason is None))
                    or (status == "failed" and reason not in {"protocol", "agent_error"})
                    or status not in {"failed", "stopped"}
                ):
                    raise AgentRunError("invalid generation terminal result")
                self.done = frame.copy()
                return None
            _object(frame, {"type", "sequence", "provider", "body_base64"})
            sequence = frame["sequence"]
            if (
                not self.ready
                or frame["type"] != "request"
                or type(sequence) is not int
                or sequence != self.sequence
                or sequence >= task.count
                or frame["provider"] != self.config["provider"]
            ):
                raise AgentRunError("generation request exceeds its frozen task or role")
            encoded = frame["body_base64"]
            if type(encoded) is not str or len(encoded) > 4 * ((wire.MAX_BODY_BYTES + 2) // 3):
                raise AgentRunError("generation body exceeds its byte ceiling")
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > wire.MAX_BODY_BYTES or base64.b64encode(raw).decode("ascii") != encoded:
                raise AgentRunError("generation body encoding differs")
            body = _load(raw)
            cap = (
                "max_tokens" if self.config["provider"] == "anthropic" else "max_completion_tokens"
            )
            if (
                body.get("model") != self.config["model"]
                or type(body.get(cap)) is not int
                or body[cap] != self.config["max_output_tokens"]
                or ("max_tokens" in body and "max_completion_tokens" in body)
            ):
                raise AgentRunError("generation body changes its selected model or cap")
            self.sequence += 1
            self.calls["requested"] += 1
            if self.stop_reason is None:
                call = GatewayCall(
                    _text(self.profile["capability"]),
                    _text(self.profile["profile_id"]),
                    _sha(
                        [
                            "buddha.seed-call.v1",
                            self.agent_sha256,
                            _sha(self.config),
                            self.task_index,
                            task.to_record(),
                            sequence,
                        ]
                    ),
                    0,
                    raw,
                )
                try:
                    envelope = self.gateway.execute(call)
                except (ProviderUncertain, PendingOperation):
                    self.stop_reason = "unknown"
                except (BudgetExceeded, BoundBreach):
                    self.stop_reason = "authority"
                except (GatewayError, OperationConflict):
                    self.stop_reason = "protocol"
            if self.stop_reason is not None:
                self.calls["stopped"] += 1
                return {"type": "stop", "sequence": sequence, "reason": self.stop_reason}
            self.calls["completed"] += 1
            self.delivered += 1
            return {"type": "response", "sequence": sequence, "envelope": envelope.to_record()}
        except (ReleaseError, KeyError, ValueError, TypeError, OSError):
            self.broken = True
            raise AgentRunError("generation worker protocol is invalid") from None

    def _write(self, name: str, value: object) -> None:
        _root(self.output)
        with (self.output / name).open("xb") as stream:
            stream.write(_json(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.artifacts[name] = file_hash(self.output / name, max_bytes=MAX_JSON_BYTES + 1)

    def close(self) -> None:
        if self.partial is not None:
            self.partial.close()
            self.partial = None

    def run(self) -> dict[str, object]:
        with self.gateway.work(directory=self.output, kind="generation"):
            return self._run()

    def _run(self) -> dict[str, object]:
        if self.ran or self.ready or self.broken or self.done is not None:
            raise AgentRunError("generation session already started")
        self._unchanged()
        self.ran = True
        executions = []
        status, reason = "failed", "protocol"
        try:
            for index in range(len(self.tasks.tasks)):
                self._activate(index)
                status, reason = "failed", "protocol"
                try:
                    result = executor.run_container(
                        self.spec,
                        initial=self.worker,
                        handle=self.handle,
                        limits=self.limits,
                        docker_endpoint=self.endpoint,
                    )
                except executor.ExecutorError as error:
                    executions.append(
                        {
                            "container_id": error.container_id,
                            "cleanup_status": error.cleanup_status,
                            "reason": error.reason,
                        }
                    )
                    break
                executions.append(
                    {key: value for key, value in asdict(result).items() if key != "_configuration"}
                    | {"configuration": result.configuration}
                )
                if result.exit_code != 0 or result.cleanup_status != "removed" or self.done is None:
                    break
                status, reason = _text(self.done["status"]), _text(self.done["reason"])
                if status != "complete":
                    break
            else:
                answers = Answers.from_results(
                    self.release,
                    self.tasks,
                    self.outputs,
                    agent_sha256=self.agent_sha256,
                    metadata={},
                )
                self._write("answers.json", answers.to_record())
                status, reason = "complete", "complete"
        finally:
            self.close()
        if len(self.outputs) != len(self.tasks.tasks) and status == "complete":
            status, reason = "failed", "protocol"
        self.artifacts["partial.jsonl"] = file_hash(
            self.output / "partial.jsonl", max_bytes=MAX_JSON_BYTES
        )
        report: dict[str, object] = {
            "format": "buddha.generation-report.v1",
            "status": status,
            "reason": reason,
            "descriptor_sha256": self.descriptor_sha256,
            "agent_sha256": self.agent_sha256,
            "seed_source_sha256": self.inventories["agent"][self.entrypoint],
            "config_sha256": _sha(self.config),
            "tasks_sha256": self.tasks.fingerprint(),
            "tasks_file_sha256": self.tasks_file_sha256,
            "expected_tasks": len(self.tasks.tasks),
            "completed_tasks": len(self.outputs),
            "calls": self.calls,
            "call_counter_scope": "raw replies delivered, including cached replay",
            "gateway_manifest_sha256": self.gateway.manifest_sha256,
            "gateway_totals": self.gateway.ledger.totals(),
            "gateway_totals_scope": (
                "entire original owner, including earlier calls and unknown holds"
            ),
            "normalization": (
                "selected seed source; effective [empty]/[refused] "
                "may differ from durable raw receipts"
            ),
            "artifacts": self.artifacts.copy(),
            "executions": executions,
            "claim": (
                "frozen generation and C1 answer provenance; "
                "native evaluation and promotion remain separate"
            ),
        }
        self._write("report.json", report)
        return report
