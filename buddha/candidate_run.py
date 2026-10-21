"""One selected source task in the reviewed container, with host-owned model calls.

Candidate code is data on this host. The caller supplies its independently
reviewed runtime identity; neither the descriptor nor the worker can approve it.
This does not change the fixed-seed route or create spending authorization.
"""

import base64
import hashlib
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from buddha import answers as answer_module
from buddha import channel, executor, releases, wire
from buddha.answers import Answers, TaskSet, _utf8
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

RUNNER_FILES = ("__init__", "channel", "releases", "wire", "candidate_worker")
HOST_FILES = (*RUNNER_FILES, "executor", "answers", "candidate_run")
MAX_SOURCE_BYTES = 1024**2
MAX_CALLBACKS = 1000


class CandidateRunError(ReleaseError):
    """The source task, its approved execution contract or worker evidence is invalid."""


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _read(path: Path, expected: str, maximum: int = MAX_JSON_BYTES) -> bytes:
    if file_hash(path, max_bytes=maximum) != expected:
        raise CandidateRunError("candidate input is not frozen")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum or hashlib.sha256(raw).hexdigest() != expected:
        raise CandidateRunError("candidate input changed while consumed")
    return raw


class CandidateSession:
    def __init__(
        self,
        gateway: Gateway,
        *,
        descriptor: Path,
        output: Path,
        expected_runtime_sha256: str,
    ) -> None:
        self.gateway = gateway
        self.ran = self.ready = self.broken = False
        self.sequence = self.delivered = 0
        self.done: dict[str, object] | None = None
        self.stop_reason: str | None = None
        self.calls = {"requested": 0, "completed": 0, "stopped": 0}
        try:
            if not isinstance(gateway, Gateway) or not isinstance(descriptor, Path):
                raise CandidateRunError("a candidate needs a frozen Gateway and descriptor")
            if not isinstance(output, Path):
                raise CandidateRunError("candidate output needs a new Path")
            self.runtime_sha256 = _digest(expected_runtime_sha256)
            owner = _read_manifest(gateway.directory)
            if _sha(owner) != gateway.manifest_sha256:
                raise CandidateRunError("candidate Gateway owner changed")
            bound = {
                _text(item["path"]): _digest(item["sha256"])
                for item in cast(list[dict[str, object]], _object(owner["invocation"])["inputs"])
            }

            def consume(path: Path) -> bytes:
                path = path.absolute()
                if str(path) not in bound:
                    raise CandidateRunError("candidate host source/input was not frozen")
                return _read(path, bound[str(path)])

            raw = consume(descriptor)
            self.descriptor_sha256 = hashlib.sha256(raw).hexdigest()
            description = _object(
                _load(raw),
                {
                    "format",
                    "tasks",
                    "config",
                    "entrypoint",
                    "executor",
                    "profile",
                    "runtime",
                    "max_callbacks",
                },
            )
            if description["format"] != "buddha.candidate-generation.v1":
                raise CandidateRunError("unsupported candidate descriptor")
            self.max_callbacks = wire._integer(description["max_callbacks"], 0, MAX_CALLBACKS)
            self.entrypoint = _path(description["entrypoint"])
            if not self.entrypoint.endswith(".py"):
                raise CandidateRunError("candidate entrypoint must be Python source")
            selected = Selection.from_bytes(_json(owner["selection"]))
            selection = selected.to_record()
            roots = {key: Path(_text(value)) for key, value in _object(owner["roots"]).items()}
            components = _object(selection["components"])
            agent = _object(components["agent"])
            if set(agent) != {self.entrypoint}:
                raise CandidateRunError("this route accepts one sealed candidate source file")
            # Check the untrusted candidate's size/UTF-8 before a full tree rehash.
            _read(
                roots["agent"] / self.entrypoint, _digest(agent[self.entrypoint]), MAX_SOURCE_BYTES
            ).decode("utf-8")
            self.agent_sha256 = selected.agent_sha256
            package = Path(__file__).absolute().parent
            for module in (answer_module, channel, executor, releases, wire):
                if Path(_text(module.__file__)).absolute() != package / (
                    module.__name__.split(".")[-1] + ".py"
                ):
                    raise CandidateRunError("candidate imports a different host implementation")
            for name in HOST_FILES:
                consume(package / (name + ".py"))
            expected_runner = {
                "buddha/" + name + ".py": file_hash(package / (name + ".py"))
                for name in RUNNER_FILES
            }
            if _object(components["runner"]) != expected_runner:
                raise CandidateRunError("candidate runner differs from installed source")
            tasks_raw = consume(Path(_text(description["tasks"])))
            self.tasks = TaskSet.from_bytes(tasks_raw)
            if len(self.tasks.tasks) != 1 or self.tasks.release_sha256 != selected.release_sha256:
                raise CandidateRunError("candidate needs exactly one selected release task")
            self.task = self.tasks.tasks[0]
            self.release = Release.from_record(selection["release"])
            self.config = _object(
                description["config"],
                {"provider", "model", "max_output_tokens", "instructions", "sampling"},
            )
            provider = _text(self.config["provider"])
            if provider not in {"openai", "anthropic"}:
                raise CandidateRunError("unsupported candidate provider")
            _text(self.config["model"])
            wire._integer(self.config["max_output_tokens"], 1)
            if len(_utf8(self.config["instructions"])) > 4000 or self.config["sampling"] not in {
                "regenerate",
                "in-context",
            }:
                raise CandidateRunError("invalid candidate config")
            self.profile = _object(description["profile"], {"capability", "profile_id"})
            capability, profile_id = (
                _text(self.profile["capability"]),
                _text(self.profile["profile_id"]),
            )
            if capability not in CAPABILITIES or CAPABILITIES[capability][0] != provider:
                raise CandidateRunError("candidate capability differs from its provider")
            profile = _object(_object(_object(owner["profiles"])[capability])["profiles"])[
                profile_id
            ]
            spec = _object(_object(profile)["spec"])
            if any(
                spec[key] != self.config[key] for key in ("provider", "model", "max_output_tokens")
            ):
                raise CandidateRunError("candidate config differs from its host-owned profile")
            runtime_reference = _object(description["runtime"], {"path", "sha256"})
            if runtime_reference["sha256"] != self.runtime_sha256:
                raise CandidateRunError("candidate cannot approve its own runtime")
            runtime_path = Path(_text(runtime_reference["path"]))
            if not runtime_path.is_absolute() or not runtime_path.is_relative_to(
                roots["environment"]
            ):
                raise CandidateRunError("runtime artifact is outside its selected component")
            relative = runtime_path.relative_to(roots["environment"]).as_posix()
            if _object(components["environment"]).get(relative) != self.runtime_sha256:
                raise CandidateRunError("runtime artifact differs from its selected component")
            runtime_raw = consume(runtime_path)
            if hashlib.sha256(runtime_raw).hexdigest() != self.runtime_sha256:
                raise CandidateRunError("runtime artifact differs from trusted approval")
            runtime = _load(runtime_raw)
            if runtime["format"] != "buddha.src01-runtime-environment.v1":
                raise CandidateRunError("unsupported source runtime")
            helper = _object(runtime["audit_helper"], {"path", "sha256"})
            if helper["path"] != "/opt/runtime-audit.py":
                raise CandidateRunError("unsupported source runtime helper")
            helper_sha = _digest(helper["sha256"])
            manifest_sha = _digest(_object(runtime["installed_manifest"])["sha256"])
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
                raise CandidateRunError("candidate permits only the agent and runner mounts")
            self.spec = executor.ContainerSpec(
                _text(settings["image_id"]),
                "agent",
                tuple((_text(pair[0]), Path(_text(pair[1]))) for pair in mounts),
                _path(settings["runner_entrypoint"]),
                tuple((_text(pair[0]), _text(pair[1])) for pair in environment),
            )
            if (
                dict(self.spec.mounts) != {"/agent": roots["agent"], "/runner": roots["runner"]}
                or self.spec.runner_entrypoint != "buddha/candidate_worker.py"
                or self.spec.image_id != runtime["image_id"]
                or dict(self.spec.image_environment)
                != dict(
                    value.split("=", 1)
                    for value in cast(list[str], _object(runtime["config"])["Env"])
                )
            ):
                raise CandidateRunError("candidate runtime/image/mount selection differs")
            self.limits = executor.Limits(
                **cast(
                    dict[str, Any],
                    _object(settings["limits"], set(executor.Limits.__dataclass_fields__)),
                )
            )
            self.endpoint = executor._local_endpoint(settings["docker_endpoint"])
            self.inventories = {"agent": agent, "runner": expected_runner}
            if inventory(roots["runner"]) != expected_runner:
                raise CandidateRunError("candidate runner mount contains unselected source")
            execution_identity(gateway.directory, owner)
            proposed_output = output.absolute()
            if ".." in proposed_output.parts:
                raise CandidateRunError("candidate output cannot traverse parents")
            _root(proposed_output.parent)
            self.output = proposed_output.parent.resolve(strict=True) / _path(proposed_output.name)
            protected = [
                *(root.resolve(strict=True) for root in roots.values()),
                gateway.directory.resolve(strict=True),
                package.resolve(strict=True),
            ]
            if self.output.exists() or any(
                self.output.is_relative_to(root) or root.is_relative_to(self.output)
                for root in protected
            ):
                raise CandidateRunError("candidate output overlaps protected input/owner source")
            self.worker = {
                "type": "configure",
                "format": "buddha.candidate-worker.v1",
                "roots": {"agent": "/agent", "runner": "/runner"},
                "inventories": self.inventories,
                "entrypoint": self.entrypoint,
                "agent_sha256": self.agent_sha256,
                "config": self.config,
                "task": self.task.to_record(),
                "max_callbacks": self.max_callbacks,
                "runtime": {
                    "sha256": self.runtime_sha256,
                    "helper_sha256": helper_sha,
                    "manifest_sha256": manifest_sha,
                },
            }
            self._worker_bytes = _json(self.worker)
            self._frozen = self._configuration()
            self.output.mkdir()
        except (ReleaseError, KeyError, TypeError, ValueError, OSError):
            raise CandidateRunError(
                "candidate contract, source, runtime or destination is invalid"
            ) from None

    def _configuration(self) -> bytes:
        return _json(
            {
                "gateway": [str(self.gateway.directory), self.gateway.manifest_sha256],
                "descriptor": self.descriptor_sha256,
                "runtime": self.runtime_sha256,
                "tasks": self.tasks.fingerprint(),
                "agent": self.agent_sha256,
                "profile": self.profile,
                "config": self.config,
                "entrypoint": self.entrypoint,
                "max_callbacks": self.max_callbacks,
                "inventories": self.inventories,
                "spec": {
                    "image": self.spec.image_id,
                    "role": self.spec.role,
                    "mounts": [[name, str(path)] for name, path in self.spec.mounts],
                    "entrypoint": self.spec.runner_entrypoint,
                    "environment": self.spec.image_environment,
                },
                "limits": asdict(self.limits),
                "endpoint": self.endpoint,
                "output": str(self.output),
            }
        )

    def _unchanged(self) -> None:
        if self._configuration() != self._frozen or _json(self.worker) != self._worker_bytes:
            raise CandidateRunError("candidate configuration changed after validation")
        execution_identity(self.gateway.directory)

    def _operation_coverage(self) -> bool:
        # Each delivered ordinal names one distinct completed operation. The
        # dedicated owner must have no retained prefix this execution skipped.
        return self.gateway.ledger.totals()["operation_count"] == self.delivered

    def handle(self, frame: dict[str, object]) -> dict[str, object] | None:
        try:
            self._unchanged()
            _object(frame)
            if self.broken or self.done is not None:
                raise CandidateRunError("candidate worker already ended")
            if frame.get("type") == "ready":
                _object(frame, {"type", "agent_sha256", "task_sha256", "runtime_sha256"})
                if (
                    self.ready
                    or frame["agent_sha256"] != self.agent_sha256
                    or frame["task_sha256"] != _sha(self.task.to_record())
                    or frame["runtime_sha256"] != self.runtime_sha256
                ):
                    raise CandidateRunError("candidate ready identity differs")
                self.ready = True
                return None
            if frame.get("type") == "done":
                _object(frame, {"type", "status", "reason", "answers"})
                status, reason, values = frame["status"], frame["reason"], frame["answers"]
                if type(values) is not list:
                    raise CandidateRunError("candidate answers must be an ordered list")
                if status == "complete":
                    if (
                        not self.ready
                        or self.stop_reason is not None
                        or reason != "complete"
                        or self.delivered != self.sequence
                        or not self._operation_coverage()
                        or len(values) != self.task.count
                    ):
                        raise CandidateRunError("candidate completion is unsupported")
                    [_utf8(value) for value in values]
                elif (
                    values
                    or not self.ready
                    or (status == "stopped" and (reason != self.stop_reason or reason is None))
                    or (status == "failed" and reason not in {"protocol", "agent_error"})
                    or status not in {"failed", "stopped"}
                ):
                    raise CandidateRunError("candidate terminal result is invalid")
                self.done = _load(_json(frame))
                return None
            _object(frame, {"type", "sequence", "provider", "body_base64"})
            if (
                not self.ready
                or frame["type"] != "request"
                or type(frame["sequence"]) is not int
                or frame["sequence"] != self.sequence
                or frame["provider"] != self.config["provider"]
            ):
                raise CandidateRunError("candidate request sequence or provider differs")
            encoded = frame["body_base64"]
            if type(encoded) is not str or len(encoded) > 4 * ((wire.MAX_BODY_BYTES + 2) // 3):
                raise CandidateRunError("candidate request exceeds its byte ceiling")
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > wire.MAX_BODY_BYTES or base64.b64encode(raw).decode() != encoded:
                raise CandidateRunError("candidate request encoding differs")
            body = _load(raw)
            cap = (
                "max_tokens" if self.config["provider"] == "anthropic" else "max_completion_tokens"
            )
            if (
                body.get("model") != self.config["model"]
                or type(body.get(cap)) is not int
                or not 1 <= cast(int, body[cap]) <= cast(int, self.config["max_output_tokens"])
                or ("max_tokens" in body and "max_completion_tokens" in body)
            ):
                raise CandidateRunError("candidate cannot change the selected model or cap")
            sequence = self.sequence
            self.sequence += 1
            self.calls["requested"] += 1
            if self.stop_reason is None and sequence >= self.max_callbacks:
                self.stop_reason = "quota"
            if self.stop_reason is None:
                call = GatewayCall(
                    _text(self.profile["capability"]),
                    _text(self.profile["profile_id"]),
                    _sha(
                        [
                            "buddha.candidate-call.v1",
                            self.descriptor_sha256,
                            self.agent_sha256,
                            self.tasks.fingerprint(),
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
            self.delivered += 1
            self.calls["completed"] += 1
            return {"type": "response", "sequence": sequence, "envelope": envelope.to_record()}
        except (ReleaseError, KeyError, TypeError, ValueError, OSError):
            self.broken = True
            raise CandidateRunError("candidate worker protocol is invalid") from None

    def _write(self, name: str, value: object) -> None:
        _root(self.output)
        with (self.output / name).open("xb") as stream:
            stream.write(_json(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def run(self) -> dict[str, object]:
        if self.ran or self.ready or self.broken or self.done is not None:
            raise CandidateRunError("candidate session already started")
        self._unchanged()
        self.ran = True
        status, reason = "failed", "protocol"
        execution: dict[str, object] | None = None
        interrupted = False
        try:
            result = executor.run_container(
                self.spec,
                initial=_load(self._worker_bytes),
                handle=self.handle,
                limits=self.limits,
                docker_endpoint=self.endpoint,
            )
            execution = {
                key: value for key, value in asdict(result).items() if key != "_configuration"
            } | {"configuration": result.configuration}
            self._unchanged()
            if (
                result.exit_code == 0
                and result.cleanup_status == "removed"
                and result.image_id == self.spec.image_id
                and self.done is not None
            ):
                status, reason = _text(self.done["status"]), _text(self.done["reason"])
                if self.stop_reason is not None:
                    status, reason = "stopped", self.stop_reason
                if status == "complete":
                    if not self._operation_coverage():
                        raise CandidateRunError("candidate skipped retained owner operations")
                    answers = Answers.from_results(
                        self.release,
                        self.tasks,
                        [{"task_id": self.task.id, "answers": self.done["answers"]}],
                        agent_sha256=self.agent_sha256,
                        metadata={},
                    )
                    self._write("answers.json", answers.to_record())
        except executor.ExecutorError as error:
            execution = {
                "container_id": error.container_id,
                "cleanup_status": error.cleanup_status,
                "reason": error.reason,
            }
            reason = "execution"
        except KeyboardInterrupt:
            status, reason, interrupted = "stopped", "cancelled", True
        except (ReleaseError, KeyError, TypeError, ValueError, OSError):
            status, reason = "failed", "protocol"
        if self.stop_reason is not None:
            status, reason = "stopped", self.stop_reason
        totals = self.gateway.ledger.totals()
        report: dict[str, object] = {
            "format": "buddha.candidate-generation-report.v1",
            "status": status,
            "reason": reason,
            "host_stop_reason": self.stop_reason,
            "descriptor_sha256": self.descriptor_sha256,
            "runtime_sha256": self.runtime_sha256,
            "agent_sha256": self.agent_sha256,
            "tasks_sha256": self.tasks.fingerprint(),
            "config_sha256": _sha(self.config),
            "max_callbacks": self.max_callbacks,
            "calls": self.calls.copy(),
            "execution": execution,
            "gateway_manifest_sha256": self.gateway.manifest_sha256,
            "gateway_totals": totals,
            "owner_operation_coverage_complete": totals["operation_count"] == self.delivered,
            "call_counter_scope": "delivered replies include same-owner receipt replay",
            "gateway_totals_scope": "entire original owner, including earlier operations/holds",
            "artifacts": (
                {"answers.json": file_hash(self.output / "answers.json")}
                if status == "complete"
                else {}
            ),
            "claim": "single source-task execution; no source evolution or improvement claim",
        }
        self._write("report.json", report)
        if interrupted:
            raise KeyboardInterrupt
        return report
