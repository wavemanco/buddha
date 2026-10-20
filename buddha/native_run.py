"""Host-only native command supervision, frozen inputs and funded stdio replies.

No benchmark formula, version-specific hook target or SDK is imported here.
Native artifacts and the separate host completeness report have distinct paths.
"""

import base64
import hashlib
import os
import tempfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, cast

from buddha import channel, executor
from buddha.gateway import (
    CAPABILITIES,
    Gateway,
    GatewayCall,
    GatewayError,
    _read_manifest,
    execution_identity,
)
from buddha.ledger import BudgetExceeded, OperationConflict
from buddha.native_transport import NativeRequest
from buddha.provider import BoundBreach, PendingOperation, ProviderUncertain
from buddha.releases import (
    MAX_JSON_BYTES,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _path,
    _paths,
    _root,
    _text,
    file_hash,
    inventory,
)

MAX_FILES = 128
MAX_FILE_BYTES = 64 * 1024**2
MAX_TOTAL_BYTES = 128 * 1024**2
CHUNK_BYTES = 64 * 1024
RUNNER_FILES = (
    "__init__",
    "channel",
    "native_worker",
    "native_context",
    "native_transport",
    "releases",
    "wire",
)


class NativeRunError(ReleaseError):
    """The host cannot establish a valid native execution or artifact transition."""


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _decode(value: object, maximum: int) -> bytes:
    if type(value) is not str or len(value) > 4 * ((maximum + 2) // 3):
        raise NativeRunError("invalid bounded binary field")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError):
        raise NativeRunError("invalid binary field") from None
    if len(raw) > maximum or base64.b64encode(raw).decode() != value:
        raise NativeRunError("noncanonical binary field")
    return raw


class NativeSession:
    def __init__(self, gateway: Gateway, *, descriptor: Path, output: Path) -> None:
        if not isinstance(output, Path):
            raise NativeRunError("native output must be a Path")
        self.gateway = gateway
        self.output = output.absolute()
        self.pending: tuple[str, Path, BinaryIO, int] | None = None
        self.artifacts: dict[str, str] = {}
        self.paths: list[str] = []
        self.total_bytes = 0
        self.ready = False
        self.broken = False
        self.ran = False
        self.done: dict[str, object] | None = None
        self.stop_reason: str | None = None
        self.sequence = 0
        self.calls = {"requested": 0, "completed": 0, "stopped": 0}
        self.aliases: list[object] = []
        self.ready_audit_sha256: str | None = None
        try:
            if not isinstance(gateway, Gateway) or not isinstance(descriptor, Path):
                raise NativeRunError("invalid host native session")
            record = _read_manifest(gateway.directory)
            if _sha(record) != gateway.manifest_sha256:
                raise NativeRunError("native gateway owner changed")
            execution_identity(gateway.directory, record)
            bindings = {
                _text(item["path"]): _digest(item["sha256"])
                for item in cast(list[dict[str, object]], _object(record["invocation"])["inputs"])
            }

            def bound(path: Path) -> str:
                path = path.absolute()
                actual = file_hash(path, max_bytes=256 * 1024**2)
                if bindings.get(str(path)) != actual:
                    raise NativeRunError("actual native input or controller is not frozen")
                return actual

            self.descriptor_sha256 = bound(descriptor)
            package = Path(__file__).absolute().parent
            for module in (channel, executor):
                if Path(_text(module.__file__)).absolute() != package / (
                    module.__name__.split(".")[-1] + ".py"
                ):
                    raise NativeRunError("native controller imports an unbound implementation")
            for name in (*RUNNER_FILES, "executor", "native_run"):
                bound(package / (name + ".py"))
            with descriptor.open("rb") as stream:
                consumed = stream.read(MAX_JSON_BYTES + 1)
            if hashlib.sha256(consumed).hexdigest() != self.descriptor_sha256:
                raise NativeRunError("consumed native descriptor differs from its owner")
            description = _object(_load(consumed), {"format", "worker", "executor", "profiles"})
            if description["format"] != "buddha.native-command.v1":
                raise NativeRunError("unsupported native command descriptor")
            self.worker = _object(
                description["worker"],
                {
                    "type",
                    "format",
                    "command",
                    "release_sha256",
                    "answers_sha256",
                    "roots",
                    "inventories",
                    "inputs",
                    "hooks",
                },
            )
            if (
                self.worker["type"] != "configure"
                or self.worker["format"] != "buddha.native-worker.v1"
                or self.worker["roots"]
                != {
                    "official": "/official",
                    "runner": "/runner",
                    "environment": "/opt/venv",
                    "inputs": "/inputs",
                    "artifacts": "/scratch/artifacts",
                }
            ):
                raise NativeRunError("unsupported native worker envelope")
            self.profiles = _object(description["profiles"])
            self.owned_profiles = _object(record["profiles"])
            for provider, raw in self.profiles.items():
                if provider not in {"openai", "anthropic"}:
                    raise NativeRunError("unsupported host model role")
                capability = next(key for key, item in CAPABILITIES.items() if item[0] == provider)
                choices = _object(_object(self.owned_profiles[capability])["profiles"])
                for model, profile in _object(raw).items():
                    _text(model)
                    if _object(_object(choices[_text(profile)])["spec"])["model"] != model:
                        raise NativeRunError("model mapping differs from the frozen profile")
            selected = Selection.from_bytes(_json(record["selection"]))
            if self.worker["release_sha256"] != selected.release_sha256:
                raise NativeRunError("native release differs from its owner")
            if _digest(self.worker["answers_sha256"]) not in bindings.values():
                raise NativeRunError("answer identity is not a frozen host input")
            command = _object(self.worker["command"], {"index", "module", "argv", "sha256"})
            index = command["index"]
            commands = cast(
                list[dict[str, object]], _object(selected.to_record()["release"])["commands"]
            )
            if type(index) is not int or not 0 <= index < len(commands):
                raise NativeRunError("native command index differs from the release")
            expected = commands[index]
            argv = [
                "/scratch/artifacts" if item == "{artifacts}" else item
                for item in cast(list[object], expected["argv"])
            ]
            if command != {
                "index": index,
                "module": expected["module"],
                "argv": argv,
                "sha256": _sha({"index": index, "module": expected["module"], "argv": argv}),
            }:
                raise NativeRunError("native entry point differs from its frozen release")
            self.command = command
            spec = _object(
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
            if spec["role"] != "evaluator":
                raise NativeRunError("this host route supports evaluator workers only")
            mounts = spec["mounts"]
            env = spec["image_environment"]
            if type(mounts) is not list or type(env) is not list:
                raise NativeRunError("native mounts and environment require explicit inventories")
            self.spec = executor.ContainerSpec(
                _text(spec["image_id"]),
                "evaluator",
                tuple(
                    (_text(pair[0]), Path(_text(pair[1])))
                    for pair in mounts
                    if type(pair) is list and len(pair) == 2
                ),
                _path(spec["runner_entrypoint"]),
                tuple(
                    (_text(pair[0]), _text(pair[1]))
                    for pair in env
                    if type(pair) is list and len(pair) == 2
                ),
            )
            if self.spec.runner_entrypoint != "buddha/native_worker.py":
                raise NativeRunError("fixed native protocol requires its bound worker entrypoint")
            if len(self.spec.mounts) != len(mounts) or len(self.spec.image_environment) != len(env):
                raise NativeRunError("invalid native component inventory")
            self.limits = executor.Limits(
                **cast(
                    dict[str, Any],
                    _object(spec["limits"], set(executor.Limits.__dataclass_fields__)),
                )
            )
            self.endpoint = executor._local_endpoint(spec["docker_endpoint"])
            roots = dict(self.spec.mounts)
            owner_roots = _object(record["roots"])
            inventories = _object(self.worker["inventories"])
            components = _object(selected.to_record()["components"])
            for role in ("official", "runner"):
                root = roots["/" + role]
                if (
                    str(root) != owner_roots[role]
                    or inventory(root) != inventories[role]
                    or inventories[role] != components[role]
                ):
                    raise NativeRunError("actual native components differ from selection")
            for role in ("official", "runner"):
                if any(
                    Path(path).suffix.lower() in {".pyc", ".pyo"}
                    or "__pycache__" in PurePosixPath(path).parts
                    for path in _object(inventories[role])
                ):
                    raise NativeRunError("selected code contains executable bytecode caches")
            for name in RUNNER_FILES:
                relative = "buddha/" + name + ".py"
                if _object(inventories["runner"]).get(relative) != file_hash(
                    package / (name + ".py")
                ):
                    raise NativeRunError("native runner is a different installed implementation")
            self.inventories = inventories
            inputs = self.worker["inputs"]
            if type(inputs) is not list or len(inputs) > MAX_FILES:
                raise NativeRunError("invalid native input population")
            sources, destinations = {}, []
            for item in inputs:
                item = _object(item, {"source", "destination", "sha256"})
                source, destination = _path(item["source"]), _path(item["destination"])
                if source in sources or bound(roots["/inputs"] / source) != item["sha256"]:
                    raise NativeRunError("native artifact source is not frozen")
                sources[source] = item["sha256"]
                destinations.append(destination)
            if destinations:
                _paths(destinations)
            if inventory(roots["/inputs"]) != sources:
                raise NativeRunError("unselected files would enter the native input mount")
            self.expected_aliases = self._expected_aliases()
            self._frozen_configuration = self._configuration()
            _root(self.output.parent)
            _path(self.output.name)
            self.output.mkdir()
            (self.output / "artifacts").mkdir()
            (self.output / ".receive").mkdir()
        except (ReleaseError, KeyError, TypeError, ValueError, OSError):
            raise NativeRunError("native owner, configuration or destination is invalid") from None

    def _configuration(self) -> bytes:
        return _json(
            {
                "worker": self.worker,
                "profiles": self.profiles,
                "command": self.command,
                "inventories": self.inventories,
                "aliases": self.expected_aliases,
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
                "descriptor": self.descriptor_sha256,
                "gateway": [str(self.gateway.directory), self.gateway.manifest_sha256],
            }
        )

    def _unchanged(self) -> None:
        if self._configuration() != self._frozen_configuration:
            raise NativeRunError("native session configuration changed after validation")

    def _expected_aliases(self) -> dict[str, str]:
        hooks = _object(self.worker["hooks"])
        expected = {}
        if hooks["cache"] is not None:
            expected[_text(_object(hooks["cache"])["target"])] = "cache"
        for entry in cast(list[object], hooks["calls"]):
            entry = _object(entry)
            path = _text(entry["target"])
            if path in expected:
                raise NativeRunError("overlapping native hooks")
            expected[path] = _text(entry["label"])
        for entry in cast(list[object], hooks["sdk"]):
            entry = _object(entry)
            for alias_value in cast(list[object], entry["module_slots"]):
                path = _text(alias_value)
                if path in expected:
                    raise NativeRunError("overlapping SDK hook")
                expected[path] = "sdk:" + _text(entry["provider"])
        return expected

    def _audit(self, value: object, *, require_command: bool = True) -> str:
        audit = _object(value)
        if not audit or len(audit) > 100000:
            raise NativeRunError("native import audit is unavailable")
        env = _object(self.inventories["environment"])
        for name, raw in audit.items():
            _text(name)
            entry = _object(raw)
            kind = entry.get("kind")
            if kind in {"built-in", "frozen"}:
                _object(entry, {"kind"})
            elif kind == "image-synthetic":
                if name not in cast(list[object], env.get("synthetic_modules", [])) or set(
                    entry
                ) - {"kind", "loader_owner"}:
                    raise NativeRunError("unreviewed fileless native module")
                if "loader_owner" in entry:
                    self._audit({"loader": entry["loader_owner"]}, require_command=False)
                    if _object(entry["loader_owner"]).get("kind") != "environment":
                        raise NativeRunError("unsealed synthetic loader")
            elif kind == "namespace":
                _object(entry, {"kind", "paths"})
                paths = entry["paths"]
                if (
                    type(paths) is not list
                    or not paths
                    or any(not self._selected_path(path) for path in paths)
                ):
                    raise NativeRunError("native namespace escapes selected roots")
            else:
                _object(entry, {"kind", "path", "sha256"})
                path, digest = _text(entry["path"]), _digest(entry["sha256"])
                pure = PurePosixPath(path)
                if not pure.is_absolute() or ".." in pure.parts:
                    raise NativeRunError("invalid native import path")
                if kind in {"official", "runner", "environment"}:
                    root = "/opt/venv/" if kind == "environment" else "/" + str(kind) + "/"
                    if not path.startswith(root):
                        raise NativeRunError("native import role differs from its path")
                    relative = path[len(root) :]
                    expected = (
                        _object(env["inventory"]).get(relative)
                        if kind == "environment"
                        else _object(self.inventories[str(kind)]).get(relative)
                    )
                    if kind == "environment":
                        expected = _object(expected).get("sha256")
                    if digest != expected:
                        raise NativeRunError("native import bytes differ from their owner")
                elif kind == "image-helper":
                    if path != "/opt/runtime-prepare.py" or digest != env["helper_sha256"]:
                        raise NativeRunError("unsealed native runtime helper")
                elif kind == "base-image":
                    version = dict(self.spec.image_environment).get("PYTHON_VERSION", "")
                    prefix = "/usr/local/lib/python" + ".".join(version.split(".")[:2]) + "/"
                    if not path.startswith(prefix) or "site-packages" in pure.parts:
                        raise NativeRunError("unexpected base-image import")
                else:
                    raise NativeRunError("unknown native import kind")
        if require_command:
            for module in cast(list[str], _object(self.worker["hooks"])["modules"]):
                command = _object(audit.get(module))
                paths = {
                    "/official/" + module.replace(".", "/") + suffix
                    for suffix in (".py", "/__init__.py")
                }
                if command.get("kind") != "official" or command.get("path") not in paths:
                    raise NativeRunError("native module has no matching official import evidence")
        return _sha(audit)

    def _selected_path(self, value: object) -> bool:
        if type(value) is not str or ".." in PurePosixPath(value).parts:
            return False
        for role, root in (
            ("official", "/official"),
            ("runner", "/runner"),
            ("environment", "/opt/venv"),
        ):
            if value == root or value.startswith(root + "/"):
                relative = value[len(root) :].strip("/")
                files = (
                    _object(_object(self.inventories["environment"])["inventory"])
                    if role == "environment"
                    else _object(self.inventories[role])
                )
                return bool(files) and (
                    not relative or any(path.startswith(relative + "/") for path in files)
                )
        return False

    def _request(self, frame: dict[str, object]) -> dict[str, object]:
        _object(frame, {"type", "seq", "request"})
        seq = frame["seq"]
        if type(seq) is not int or seq != self.sequence:
            raise NativeRunError("native response sequence differs")
        self.sequence += 1
        raw = _object(
            frame["request"],
            {"provider", "method", "url", "body_base64", "headers", "logical_id", "attempt"},
        )
        headers = raw["headers"]
        if type(headers) is not list or any(
            type(pair) is not list or len(pair) != 2 for pair in headers
        ):
            raise NativeRunError("invalid native request headers")
        request = NativeRequest(
            _text(raw["provider"]),
            _text(raw["method"]),
            _text(raw["url"]),
            _decode(raw["body_base64"], 16 * 1024**2),
            tuple(tuple(pair) for pair in headers),
            _digest(raw["logical_id"]),
            cast(int, raw["attempt"]),
        )
        if self.stop_reason is not None:
            return {"type": "stop", "seq": seq, "reason": self.stop_reason}
        model = _text(_load(request.body)["model"])
        profile = _text(_object(self.profiles[request.provider])[model])
        capability = next(
            key for key, value in CAPABILITIES.items() if value[0] == request.provider
        )
        call = GatewayCall(
            capability, profile, request.logical_id, request.attempt, request.body, request.headers
        )
        self.calls["requested"] += 1
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
            return {"type": "stop", "seq": seq, "reason": self.stop_reason}
        self.calls["completed"] += 1
        return {"type": "response", "seq": seq, "envelope": envelope.to_record()}

    def _file(self, frame: dict[str, object]) -> None:
        _object(frame, {"type", "path", "offset", "data_base64", "eof"})
        path = _path(frame["path"])
        offset, eof = frame["offset"], frame["eof"]
        if type(offset) is not int or offset < 0 or type(eof) is not bool:
            raise NativeRunError("invalid native artifact position")
        raw = _decode(frame["data_base64"], CHUNK_BYTES)
        if not eof and len(raw) != CHUNK_BYTES:
            raise NativeRunError("native artifact has a short nonterminal chunk")
        _root(self.output / "artifacts")
        _root(self.output / ".receive")
        if self.pending is None:
            if offset or path in self.artifacts or len(self.paths) >= MAX_FILES:
                raise NativeRunError("invalid native artifact start")
            _paths([*self.paths, path])
            self.paths.append(path)
            descriptor, temp_name = tempfile.mkstemp(dir=self.output / ".receive")
            self.pending = (path, Path(temp_name), os.fdopen(descriptor, "wb"), 0)
        name, temporary, stream, received = self.pending
        if (
            path != name
            or offset != received
            or received + len(raw) > MAX_FILE_BYTES
            or self.total_bytes + len(raw) > MAX_TOTAL_BYTES
        ):
            raise NativeRunError("native artifact exceeds its ordered bounds")
        stream.write(raw)
        self.total_bytes += len(raw)
        self.pending = (path, temporary, stream, received + len(raw))
        if eof:
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            target = self.output / "artifacts" / path
            # Validate every parent before mkdir or publication can follow a host link.
            parent = self.output / "artifacts"
            for part in PurePosixPath(path).parts[:-1]:
                parent = parent / part
                if not parent.exists():
                    parent.mkdir()
                _root(parent)
            try:
                os.link(temporary, target)  # Atomic publication refuses any existing target.
            finally:
                temporary.unlink()
            self.pending = None
            self.artifacts[path] = file_hash(target, max_bytes=MAX_FILE_BYTES)

    def close(self) -> None:
        if self.pending is not None:
            self.pending[2].close()

    def handle(self, frame: dict[str, object]) -> dict[str, object] | None:
        try:
            self._unchanged()
            if self.broken or self.done is not None:
                raise NativeRunError("native worker spoke after completion")
            kind = frame.get("type")
            if kind == "ready":
                _object(frame, {"type", "aliases", "audit"})
                if self.ready or type(frame["aliases"]) is not list:
                    raise NativeRunError("duplicate native readiness")
                found = {}
                modules = cast(list[object], _object(self.worker["hooks"])["modules"])
                for entry in frame["aliases"]:
                    entry = _object(entry, {"path", "label"})
                    path, label = _text(entry["path"]), _text(entry["label"])
                    if (
                        path in found
                        or path.split(":")[0] not in modules
                        or label not in self.expected_aliases.values()
                    ):
                        raise NativeRunError("unexpected native hook alias")
                    found[path] = label
                if any(found.get(path) != label for path, label in self.expected_aliases.items()):
                    raise NativeRunError("native hook installation is incomplete")
                self.ready_audit_sha256 = self._audit(frame["audit"])
                self._evidence("imports-ready.json", frame["audit"])
                self.aliases = frame["aliases"]
                self.ready = True
            elif not self.ready:
                raise NativeRunError("native worker was not ready")
            elif kind == "request":
                return self._request(frame)
            elif kind == "file":
                self._file(frame)
            elif kind == "done":
                _object(frame, {"type", "status", "reason", "audit"})
                status, reason = frame["status"], frame["reason"]
                if self.pending is not None or status not in {"complete", "stopped", "failed"}:
                    raise NativeRunError("incomplete native publication")
                if (
                    (status == "complete" and (reason != "complete" or self.stop_reason))
                    or (status == "stopped" and reason != self.stop_reason)
                    or reason
                    not in {
                        "complete",
                        "unknown",
                        "authority",
                        "protocol",
                        "cancelled",
                        "native_error",
                    }
                ):
                    raise NativeRunError("native completion contradicts its host stop")
                self._audit(frame["audit"])
                self._evidence("imports-final.json", frame["audit"])
                self.done = _load(_json(frame))
            else:
                raise NativeRunError("unsupported native worker frame")
            return None
        except (ReleaseError, KeyError, TypeError, ValueError, OSError):
            self.broken = True
            self.stop_reason = self.stop_reason or "protocol"
            self.close()
            raise NativeRunError("native worker protocol or evidence is invalid") from None

    def _evidence(self, name: str, value: object) -> None:
        _root(self.output)
        with (self.output / name).open("xb") as stream:
            stream.write(_json(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def run(self) -> dict[str, object]:
        if self.ran or self.ready or self.broken:
            raise NativeRunError("native session has already started")
        self._unchanged()
        self.ran = True
        result: executor.ExecutionResult | None = None
        failure: str | None = None
        failed_execution: dict[str, object] = {}
        try:
            execution_identity(self.gateway.directory)
            result = executor.run_container(
                self.spec,
                initial=self.worker,
                handle=self.handle,
                limits=self.limits,
                docker_endpoint=self.endpoint,
            )
        except executor.ExecutorError as error:
            failure = error.reason
            failed_execution = {
                "exit_code": None,
                "image_id": self.spec.image_id,
                "container_id": error.container_id,
                "cleanup_status": error.cleanup_status,
                "reason": failure,
            }
        finally:
            self.close()
        worker = self.done or {"status": "failed", "reason": failure or "protocol", "audit": {}}
        status = (
            worker["status"]
            if result and result.exit_code == 0 and result.cleanup_status == "removed" and self.done
            else "failed"
        )
        report: dict[str, object] = {
            "format": "buddha.native-command-report.v1",
            "status": status,
            "descriptor_sha256": self.descriptor_sha256,
            "gateway_manifest_sha256": self.gateway.manifest_sha256,
            "command_sha256": self.command["sha256"],
            "worker": {
                "status": worker["status"],
                "reason": worker["reason"],
                "audit_sha256": _sha(worker["audit"]),
            },
            "ready_audit_sha256": self.ready_audit_sha256,
            "aliases": self.aliases,
            "calls": self.calls,
            "call_counter_scope": (
                "worker requests and delivered raw responses, including cached replay"
            ),
            "gateway_totals": self.gateway.ledger.totals(),
            "gateway_totals_scope": (
                "entire owning gateway ledger, including prior calls and unknown holds"
            ),
            "artifacts": self.artifacts,
            "execution": (
                {key: value for key, value in asdict(result).items() if key != "_configuration"}
                | {"configuration": result.configuration}
            )
            if result
            else failed_execution,
            "claim": "native command artifacts; experiment coverage and promotion remain separate",
        }
        self._evidence("report.json", report)
        return _load(_json(report))
