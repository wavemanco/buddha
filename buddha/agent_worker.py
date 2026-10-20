"""One frozen seed task over the host channel; confinement belongs to the executor."""

import base64
import hashlib
import os
import sys
import sysconfig
from pathlib import Path
from types import ModuleType
from typing import BinaryIO

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from buddha.channel import read_frame, write_frame  # noqa: E402
from buddha.releases import (  # noqa: E402
    ReleaseError,
    _digest,
    _inventory,
    _json,
    _load,
    _object,
    _path,
    _root,
    _text,
    file_hash,
    inventory,
)
from buddha.wire import MAX_BODY_BYTES, RawEnvelope, _integer, decoded_body  # noqa: E402

ROOTS = {"agent": Path("/agent"), "runner": Path("/runner")}
SCRATCH = Path("/scratch")
PYCACHE_PREFIX = "/__absent_bytecode_cache"
RUNNER_FILES = {
    f"buddha/{name}.py" for name in ("__init__", "channel", "releases", "wire", "agent_worker")
}
STOP_REASONS = {"authority", "unknown", "protocol", "cancelled"}


class AgentWorkerError(ReleaseError):
    """The worker configuration, source or channel contract is unsupported."""


class _Stop(BaseException):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _literal(value: object) -> str:
    if type(value) is not str:
        raise ValueError("expected literal task or answer text")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("text must be valid UTF-8") from None
    return value


def _safe_environment() -> dict[str, str]:
    return {
        "HOME": str(SCRATCH / "home"),
        # The executor owns this bounded container tmpfs.
        "TMPDIR": "/tmp",  # nosec B108
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONNOUSERSITE": "1",
    }


class AgentWorker:
    def __init__(self, initial: dict[str, object], reader: BinaryIO, writer: BinaryIO) -> None:
        try:
            self._initial = _json(initial)
            record = _object(
                _load(self._initial),
                {
                    "type",
                    "format",
                    "roots",
                    "inventories",
                    "entrypoint",
                    "agent_sha256",
                    "config",
                    "task",
                    "task_index",
                },
            )
            if record["type"] != "configure" or record["format"] != "buddha.agent-worker.v1":
                raise AgentWorkerError("unsupported agent worker configuration")
            roots = _object(record["roots"], {"agent", "runner"})
            self.roots = {name: Path(_text(value)) for name, value in roots.items()}
            if self.roots != ROOTS:
                raise AgentWorkerError("worker roots differ from the assigned mounts")
            self.inventories = _object(record["inventories"], {"agent", "runner"})
            for value in self.inventories.values():
                _inventory(value)
            if set(_object(self.inventories["runner"])) != RUNNER_FILES:
                raise AgentWorkerError("runner differs from the minimal worker closure")
            self.entrypoint = _path(record["entrypoint"])
            if (
                not self.entrypoint.endswith(".py")
                or self.entrypoint not in _object(self.inventories["agent"])
                or any(
                    Path(name).suffix.lower() in {".pyc", ".pyo"}
                    for component in self.inventories.values()
                    for name in _object(component)
                )
            ):
                raise AgentWorkerError("agent entry or selected bytecode is unsupported")
            if (
                _digest(record["agent_sha256"])
                != hashlib.sha256(_json(self.inventories["agent"])).hexdigest()
            ):
                raise AgentWorkerError("agent inventory differs from its identity")
            self.config = _object(
                record["config"],
                {"provider", "model", "max_output_tokens", "instructions", "sampling"},
            )
            if self.config["provider"] not in ("openai", "anthropic"):
                raise AgentWorkerError("unsupported generation provider")
            _text(self.config["model"])
            _integer(self.config["max_output_tokens"], 1)
            if len(_literal(self.config["instructions"])) > 4000 or self.config["sampling"] not in (
                "regenerate",
                "in-context",
            ):
                raise AgentWorkerError("unsupported generation configuration")
            self.task = _object(record["task"], {"id", "prompt", "count"})
            identifier = self.task["id"]
            if type(identifier) is int:
                _integer(identifier, -(2**63))
            else:
                _text(identifier)
            _literal(self.task["prompt"])
            self.count = _integer(self.task["count"], 1, 1000)
            _integer(record["task_index"], 0, 2**31 - 1)
        except (ReleaseError, TypeError, ValueError):
            raise AgentWorkerError("invalid agent worker configuration") from None
        self.reader, self.writer = reader, writer
        self.sequence = 0
        self.stopped: str | None = None
        self.poisoned = False
        self.started = False

    @property
    def initial(self) -> dict[str, object]:
        return _load(self._initial)

    def _sources(self) -> None:
        cache = Path(PYCACHE_PREFIX)
        safe = _safe_environment()
        if (
            not sys.flags.isolated
            or not sys.dont_write_bytecode
            or sys.pycache_prefix != PYCACHE_PREFIX
            or cache.exists()
            or cache.is_symlink()
            or any(os.environ.get(key) != value for key, value in safe.items())
            or set(os.environ) - set(safe) - {"PATH", "LANG"}
        ):
            raise AgentWorkerError("private worker environment is not active")
        record = self.initial
        if (
            record["roots"] != {name: str(path) for name, path in self.roots.items()}
            or record["inventories"] != self.inventories
            or record["config"] != self.config
            or record["task"] != self.task
            or record["entrypoint"] != self.entrypoint
            or self.roots != ROOTS
        ):
            raise AgentWorkerError("worker configuration changed")
        for name, root in self.roots.items():
            if inventory(root) != self.inventories[name]:
                raise AgentWorkerError("selected source tree changed")
        expected = self.roots["runner"] / "buddha/agent_worker.py"
        if Path(__file__).resolve(strict=True) != expected.resolve(strict=True):
            raise AgentWorkerError("executing worker is outside the selected runner")
        for name in ("buddha", "buddha.channel", "buddha.releases", "buddha.wire"):
            module = sys.modules[name]
            relative = "buddha/__init__.py" if name == "buddha" else name.replace(".", "/") + ".py"
            if Path(module.__file__ or "").resolve(strict=True) != (
                self.roots["runner"] / relative
            ).resolve(strict=True):
                raise AgentWorkerError("loaded runner component has an unexpected origin")

    def _imports(self) -> None:
        stdlib = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
        extensions = Path(
            sysconfig.get_config_var("DESTSHARED") or Path(sys.base_prefix) / "DLLs"
        ).resolve()
        for module in tuple(sys.modules.values()):
            if module is None:
                continue
            namespace = vars(module)
            if getattr(namespace.get("__spec__"), "origin", None) in {"built-in", "frozen"}:
                continue
            file = namespace.get("__file__")
            if type(file) is not str:
                raise AgentWorkerError("imported module has no attributable source")
            path = Path(file).resolve(strict=True)
            for role, root in self.roots.items():
                if path.is_relative_to(root):
                    relative = path.relative_to(root).as_posix()
                    if file_hash(path) != _object(self.inventories[role]).get(relative):
                        raise AgentWorkerError("imported selected source changed")
                    break
            else:
                if not any(path.is_relative_to(root) for root in (stdlib, extensions)) or any(
                    part in {"site-packages", "dist-packages"} for part in path.parts
                ):
                    raise AgentWorkerError("import is outside selected source and base stdlib")

    def _complete(self, provider: str, body: bytes) -> object:
        if self.stopped is not None:
            raise _Stop(self.stopped)
        try:
            if self.poisoned:
                raise AgentWorkerError("worker channel has already failed")
            self._sources()
            self._imports()
            if (
                type(provider) is not str
                or provider != self.config["provider"]
                or type(body) is not bytes
                or len(body) > MAX_BODY_BYTES
                or self.sequence >= self.count
            ):
                raise AgentWorkerError("unsupported agent request")
            _load(body)
            sequence = self.sequence
            self.sequence += 1
            write_frame(
                self.writer,
                {
                    "type": "request",
                    "sequence": sequence,
                    "provider": provider,
                    "body_base64": base64.b64encode(body).decode("ascii"),
                },
            )
            response = read_frame(self.reader)
            kind = response.get("type")
            fields = {"type", "sequence", "reason" if kind == "stop" else "envelope"}
            _object(response, fields)
            if type(response["sequence"]) is not int or response["sequence"] != sequence:
                raise AgentWorkerError("host response differs from the pending request")
            if kind == "stop":
                reason = response["reason"]
                if type(reason) is not str or reason not in STOP_REASONS:
                    raise AgentWorkerError("unsupported host stop reason")
                self.stopped = reason
                raise _Stop(reason)
            if kind != "response":
                raise AgentWorkerError("unsupported host frame")
            envelope = RawEnvelope.from_record(response["envelope"])
            if envelope.provider != provider or envelope.status != 200:
                raise AgentWorkerError("host reply differs from the selected provider")
            return _load(decoded_body(envelope))
        except Exception:
            self.poisoned = True
            raise AgentWorkerError("agent request or host response is invalid") from None

    def run(self) -> dict[str, object]:
        if self.started:
            raise AgentWorkerError("worker may execute only one task")
        self.started = True
        answers: list[str] = []
        status, reason = "failed", "protocol"
        try:
            self._sources()
            path = self.roots["agent"] / self.entrypoint
            source = path.read_bytes()
            if (
                hashlib.sha256(source).hexdigest()
                != _object(self.inventories["agent"])[self.entrypoint]
            ):
                raise AgentWorkerError("consumed agent source changed")
            agent = ModuleType("_buddha_frozen_seed")
            agent.__file__ = str(path)
            sys.modules[agent.__name__] = agent
            try:
                # Execute only the consumed sealed bytes inside the confined worker.
                exec(compile(source, str(path), "exec"), vars(agent))  # nosec B102
            except (Exception, SystemExit):
                status, reason = "failed", "agent_error"
            else:
                self._imports()
                self._sources()
                write_frame(
                    self.writer,
                    {
                        "type": "ready",
                        "agent_sha256": self.initial["agent_sha256"],
                        "task_sha256": hashlib.sha256(_json(self.task)).hexdigest(),
                    },
                )
                generate = vars(agent).get("generate")
                if not callable(generate):
                    raise ValueError("agent entry point is not callable")
                value: object = generate(
                    _load(_json(self.task)), _load(_json(self.config)), self._complete
                )
                if self.stopped is not None:
                    raise _Stop(self.stopped)
                if self.poisoned:
                    raise AgentWorkerError("worker channel failed")
                if type(value) is not list or len(value) != self.count:
                    raise ValueError("agent did not return the exact answer count")
                answers = [_literal(item) for item in value]
                status, reason = "complete", "complete"
        except _Stop as stop:
            status, reason = "stopped", stop.reason
        except AgentWorkerError:
            status, reason = "failed", "protocol"
        except (Exception, SystemExit):
            status, reason = "failed", "agent_error"
        try:
            self._sources()
            self._imports()
        except Exception:
            status, reason = "failed", "protocol"
        done: dict[str, object] = {
            "type": "done",
            "status": status,
            "reason": reason,
            "answers": answers if status == "complete" else [],
        }
        write_frame(self.writer, done)
        return done


def main() -> None:
    """Reserve host-channel descriptors and private working state before loading the seed."""
    reader_fd, writer_fd = os.dup(0), os.dup(1)
    os.set_inheritable(reader_fd, False)
    os.set_inheritable(writer_fd, False)
    os.dup2(2, 1)
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    with os.fdopen(reader_fd, "rb") as reader, os.fdopen(writer_fd, "wb", buffering=0) as writer:
        try:
            safe = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG"}}
            os.environ.clear()
            os.environ.update(safe | _safe_environment())
            for name in ("home", "work"):
                (SCRATCH / name).mkdir(parents=True, exist_ok=True)
                _root(SCRATCH / name)
            os.chdir(SCRATCH / "work")
            AgentWorker(read_frame(reader), reader, writer).run()
        except KeyboardInterrupt:
            raise SystemExit(130) from None
        except (Exception, _Stop):
            write_frame(
                writer,
                {
                    "type": "done",
                    "status": "failed",
                    "reason": "protocol",
                    "answers": [],
                },
            )


if __name__ == "__main__":
    main()
