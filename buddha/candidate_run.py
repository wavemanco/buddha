"""Selected source generation or improvement with confined, host-owned model calls.

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
from buddha.answers import Answers, TaskSet, _id, _source, _utf8
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
    MAX_FEEDBACK_BYTES,
    MAX_JSON_BYTES,
    MAX_SOURCE_BYTES,
    Release,
    ReleaseError,
    Selection,
    _checked_proposal_capture,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _root,
    _source_proposal,
    _text,
    file_hash,
    inventory,
)

RUNNER_FILES = ("__init__", "channel", "releases", "wire", "candidate_worker")
HOST_FILES = (*RUNNER_FILES, "executor", "answers", "candidate_run")
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
        self.proposal_frame: dict[str, object] | None = None
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
            description = _load(raw)
            self.improvement = description.get("format") == "buddha.candidate-improvement.v1"
            self._improvement = self.improvement
            self.generation_v2 = description.get("format") == "buddha.candidate-generation.v2"
            _object(
                description,
                {
                    "format",
                    "config",
                    "entrypoint",
                    "executor",
                    "profile",
                    "runtime",
                    "max_callbacks",
                }
                | ({"parent_agent_sha256", "feedback"} if self.improvement else {"tasks"}),
            )
            if description["format"] not in {
                "buddha.candidate-generation.v1",
                "buddha.candidate-generation.v2",
                "buddha.candidate-improvement.v1",
            }:
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
            parent_source = _read(
                roots["agent"] / self.entrypoint, _digest(agent[self.entrypoint]), MAX_SOURCE_BYTES
            )
            parent_source.decode("utf-8")
            self.parent_source_sha256 = hashlib.sha256(parent_source).hexdigest()
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
            self.release = Release.from_record(selection["release"])
            if self.improvement:
                if _digest(description["parent_agent_sha256"]) != self.agent_sha256:
                    raise CandidateRunError("improvement parent differs from selected source")
                # Bind the improvement-only helper before importing it; v1 has no new import.
                consume(package / "policy_study.py")
                from buddha import policy_study

                if Path(_text(policy_study.__file__)).absolute() != package / "policy_study.py":
                    raise CandidateRunError("improvement imports a different split validator")
                reference = _object(description["feedback"], {"path", "sha256"})
                feedback_path = Path(_text(reference["path"]))
                if not feedback_path.is_absolute() or ".." in feedback_path.parts:
                    raise CandidateRunError("feedback needs an absolute nontraversing path")
                feedback_raw = consume(feedback_path)
                self.feedback_file_sha256 = hashlib.sha256(feedback_raw).hexdigest()
                if len(feedback_raw) > MAX_FEEDBACK_BYTES or self.feedback_file_sha256 != _digest(
                    reference["sha256"]
                ):
                    raise CandidateRunError("feedback differs from its reviewed bytes")
                packet = _object(_load(feedback_raw), {"format", "source", "split", "records"})
                if packet["format"] not in {
                    "buddha.candidate-development-feedback.v1",
                    "buddha.candidate-development-feedback.v2",
                }:
                    raise CandidateRunError("unsupported development feedback")
                self.feedback_v2 = packet["format"] == "buddha.candidate-development-feedback.v2"
                values = {}
                for name in ("source", "split"):
                    ref = _object(packet[name], {"path", "sha256"})
                    path = Path(_text(ref["path"]))
                    if not path.is_absolute() or ".." in path.parts:
                        raise CandidateRunError("feedback references need absolute paths")
                    data = consume(path)
                    if hashlib.sha256(data).hexdigest() != _digest(ref["sha256"]):
                        raise CandidateRunError("feedback source differs from reviewed bytes")
                    values[name] = data
                source = TaskSet.from_bytes(values["source"])
                release, dataset = _source(source.to_record())
                full = TaskSet.from_dataset(release, dataset)
                if source.release_sha256 != selected.release_sha256 or {
                    task.id for task in source.tasks
                } != {task.id for task in full.tasks}:
                    raise CandidateRunError("feedback needs the complete selected release source")
                development = policy_study._split(_load(values["split"]), full)
                records = packet["records"]
                if type(records) is not list or not 1 <= len(records) <= 1000:
                    raise CandidateRunError("feedback needs bounded development records")
                tasks = {task.id: task for task in full.tasks}
                seen: set[str | int] = set()
                self.feedback = []
                for value in records:
                    item = _object(value, {"task_id", "note"})
                    identifier, note = _id(item["task_id"]), _utf8(item["note"])
                    if (
                        identifier not in development
                        or identifier in seen
                        or not note.strip()
                        or len(note.encode()) > (MAX_FEEDBACK_BYTES if self.feedback_v2 else 4096)
                    ):
                        raise CandidateRunError("feedback is not unique bounded development data")
                    seen.add(identifier)
                    self.feedback.append({"task": tasks[identifier].to_record(), "note": note})
                projected = _json(self.feedback)
                if len(projected) > MAX_FEEDBACK_BYTES:
                    raise CandidateRunError("projected feedback exceeds its byte ceiling")
                self.feedback_sha256 = hashlib.sha256(projected).hexdigest()
            else:
                tasks_raw = consume(Path(_text(description["tasks"])))
                self.tasks = TaskSet.from_bytes(tasks_raw)
                if (
                    len(self.tasks.tasks) != 1
                    or self.tasks.release_sha256 != selected.release_sha256
                ):
                    raise CandidateRunError("candidate needs exactly one selected release task")
                self.task = self.tasks.tasks[0]
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
                "max_callbacks": self.max_callbacks,
                "runtime": {
                    "sha256": self.runtime_sha256,
                    "helper_sha256": helper_sha,
                    "manifest_sha256": manifest_sha,
                },
            }
            if self.improvement:
                self.worker.update(
                    format=(
                        "buddha.candidate-improvement-worker.v2"
                        if self.feedback_v2
                        else "buddha.candidate-improvement-worker.v1"
                    ),
                    feedback=self.feedback,
                )
            else:
                self.worker["task"] = self.task.to_record()
            self._worker_bytes = _json(self.worker)
            self._frozen = self._configuration()
            with gateway.work(
                directory=self.output,
                kind="improvement" if self._improvement else "generation",
            ):
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
                **({"generation_mode": "v2"} if self.generation_v2 else {}),
                **(
                    {
                        "mode": "improve",
                        **({"feedback_mode": "v2"} if self.feedback_v2 else {}),
                        "feedback": self.feedback,
                        "feedback_file": self.feedback_file_sha256,
                        "feedback_sha256": self.feedback_sha256,
                        "parent_source_sha256": self.parent_source_sha256,
                    }
                    if self.improvement
                    else {"tasks": self.tasks.fingerprint()}
                ),
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
        if self.improvement != self._improvement:
            raise CandidateRunError("candidate mode changed after validation")
        if self._configuration() != self._frozen or _json(self.worker) != self._worker_bytes:
            raise CandidateRunError("candidate configuration changed after validation")
        execution_identity(self.gateway.directory)

    def _operation_coverage(self) -> bool:
        # Each delivered ordinal names one distinct completed operation. The
        # dedicated owner must have no retained prefix this execution skipped.
        return self.gateway.ledger.totals()["operation_count"] == self.delivered

    def handle(self, frame: dict[str, object]) -> dict[str, object] | None:
        self.gateway.assert_work(
            directory=self.output,
            kind="improvement" if self._improvement else "generation",
        )
        try:
            if (
                self.improvement
                and self.proposal_frame is None
                and isinstance(frame, dict)
                and frame.get("type") == "done"
            ):
                # Retain the received bounded JSON even when validation/cleanup later fails.
                channel._depth(frame)
                raw_frame = _json(frame)
                if len(raw_frame) + 1 > channel.MAX_FRAME_BYTES:
                    raise CandidateRunError("proposal frame exceeds its byte ceiling")
                self.proposal_frame = _load(raw_frame)
            self._unchanged()
            _object(frame)
            if self.broken or self.done is not None:
                raise CandidateRunError("candidate worker already ended")
            if frame.get("type") == "ready":
                input_key = "feedback_sha256" if self.improvement else "task_sha256"
                _object(frame, {"type", "agent_sha256", input_key, "runtime_sha256"})
                if (
                    self.ready
                    or frame["agent_sha256"] != self.agent_sha256
                    or frame[input_key]
                    != (self.feedback_sha256 if self.improvement else _sha(self.task.to_record()))
                    or frame["runtime_sha256"] != self.runtime_sha256
                ):
                    raise CandidateRunError("candidate ready identity differs")
                self.ready = True
                return None
            if frame.get("type") == "done":
                if self.improvement:
                    _object(frame, {"type", "status", "reason", "proposal"})
                    capture = _checked_proposal_capture(frame["proposal"])
                    status, reason = frame["status"], frame["reason"]
                    if not self.ready:
                        raise CandidateRunError("improver has not established its identity")
                    if status == "complete":
                        proposal = _source_proposal(capture["value"])
                        if (
                            capture["status"] != "captured"
                            or reason != "complete"
                            or self.stop_reason is not None
                            or self.delivered != self.sequence
                            or not self._operation_coverage()
                            or hashlib.sha256(proposal["source"].encode()).hexdigest()
                            == self.parent_source_sha256
                        ):
                            raise CandidateRunError("improvement completion is unsupported")
                    elif not (
                        status == "stopped"
                        and reason == self.stop_reason
                        and reason is not None
                        or status == "failed"
                        and reason
                        in {
                            "protocol",
                            "agent_error",
                            "invalid_proposal",
                            "proposal_oversized",
                            "proposal_unavailable",
                        }
                    ):
                        raise CandidateRunError("invalid improvement terminal result")
                    self.done = _load(_json(frame))
                    return None
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
                    or (
                        not self.ready
                        and not (
                            self.generation_v2
                            and status == "failed"
                            and reason == "agent_error"
                            and self.stop_reason is None
                            and type(self.sequence) is int
                            and type(self.delivered) is int
                            and self.sequence == self.delivered == 0
                            and all(type(value) is int for value in self.calls.values())
                            and self.calls == {"requested": 0, "completed": 0, "stopped": 0}
                            and self._operation_coverage()
                        )
                    )
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
                            "buddha.candidate-improvement-call.v1"
                            if self.improvement
                            else "buddha.candidate-call.v1",
                            self.descriptor_sha256,
                            self.agent_sha256,
                            self.feedback_sha256 if self.improvement else self.tasks.fingerprint(),
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
        with self.gateway.work(
            directory=self.output,
            kind="improvement" if self._improvement else "generation",
        ):
            return self._run()

    def _run(self) -> dict[str, object]:
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
                if status == "complete" and not self.improvement:
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
        improvement_artifacts: dict[str, str] = {}
        if self.improvement:
            try:
                if self.proposal_frame is not None:
                    self._write("proposal.json", self.proposal_frame)
                    improvement_artifacts["proposal.json"] = file_hash(
                        self.output / "proposal.json"
                    )
                if status == "complete":
                    self._unchanged()
                    if not self._operation_coverage() or self.done is None:
                        raise CandidateRunError("improver skipped retained owner operations")
                    proposal = _source_proposal(
                        _checked_proposal_capture(self.done["proposal"])["value"]
                    )
                    child = self.output / "child"
                    _root(self.output)
                    child.mkdir()
                    raw = proposal["source"].encode("utf-8")
                    _root(child)
                    with (child / "candidate.py").open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    expected = {"candidate.py": hashlib.sha256(raw).hexdigest()}
                    if inventory(child) != expected:
                        raise CandidateRunError("materialized child differs from proposal")
                    self._unchanged()
                    self._write(
                        "lineage.json",
                        {
                            "format": "buddha.source-lineage.v1",
                            "parent": {
                                "entrypoint": self.entrypoint,
                                "source_sha256": self.parent_source_sha256,
                                "agent_sha256": self.agent_sha256,
                            },
                            "child": {
                                "entrypoint": "candidate.py",
                                "source_sha256": expected["candidate.py"],
                                "agent_sha256": _sha(expected),
                            },
                            "descriptor_sha256": self.descriptor_sha256,
                            "feedback": {
                                "file_sha256": self.feedback_file_sha256,
                                "input_sha256": self.feedback_sha256,
                            },
                            "proposal_sha256": improvement_artifacts["proposal.json"],
                            "owner": {
                                "path": str(self.gateway.directory),
                                "manifest_sha256": self.gateway.manifest_sha256,
                            },
                        },
                    )
                    for name in ("child/candidate.py", "lineage.json"):
                        improvement_artifacts[name] = file_hash(self.output / name)
            except (ReleaseError, KeyError, TypeError, ValueError, OSError):
                status, reason = "failed", "materialization"
        totals = self.gateway.ledger.totals()
        report: dict[str, object] = {
            "format": "buddha.candidate-improvement-report.v1"
            if self.improvement
            else "buddha.candidate-generation-report.v1",
            "status": status,
            "reason": reason,
            "host_stop_reason": self.stop_reason,
            "descriptor_sha256": self.descriptor_sha256,
            "runtime_sha256": self.runtime_sha256,
            **(
                {
                    "parent_agent_sha256": self.agent_sha256,
                    "feedback_file_sha256": self.feedback_file_sha256,
                    "feedback_sha256": self.feedback_sha256,
                }
                if self.improvement
                else {"agent_sha256": self.agent_sha256, "tasks_sha256": self.tasks.fingerprint()}
            ),
            "config_sha256": _sha(self.config),
            "max_callbacks": self.max_callbacks,
            "calls": self.calls.copy(),
            "execution": execution,
            "gateway_manifest_sha256": self.gateway.manifest_sha256,
            "gateway_totals": totals,
            "owner_operation_coverage_complete": totals["operation_count"] == self.delivered,
            "call_counter_scope": "delivered replies include same-owner receipt replay",
            "gateway_totals_scope": "entire original owner, including earlier operations/holds",
            "artifacts": improvement_artifacts
            if self.improvement
            else (
                {"answers.json": file_hash(self.output / "answers.json")}
                if status == "complete"
                else {}
            ),
            "claim": (
                "materialized source only; not archive viability, "
                "mutation competence or improvement"
                if self.improvement
                else "single source-task execution; no source evolution or improvement claim"
            ),
        }
        if self.improvement:
            report["proposal_evidence"] = (
                "received bounded JSON frame; omitted-body metadata is worker-declared"
                if self.proposal_frame is not None
                else "unavailable: no bounded proposal frame received"
            )
        self._write("report.json", report)
        if interrupted:
            raise KeyboardInterrupt
        return report
