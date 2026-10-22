"""One selected source program inside the SRC runtime; the host enforces authority.

Source and environment checks provide consistency, not a Python security sandbox.
The candidate can be hostile. Its frames, counters and completion remain untrusted
until the separate host session validates them and the executor confirms cleanup.
"""

import base64
import hashlib
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import BinaryIO

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from buddha.channel import ChannelError, _depth, read_frame, write_frame  # noqa: E402
from buddha.releases import (  # noqa: E402
    MAX_FEEDBACK_BYTES,
    MAX_JSON_BYTES,
    MAX_SOURCE_BYTES,
    ReleaseError,
    _digest,
    _inventory,
    _json,
    _load,
    _object,
    _path,
    _proposal_capture,
    _root,
    _source_proposal,
    _text,
    file_hash,
    inventory,
)
from buddha.wire import MAX_BODY_BYTES, RawEnvelope, _integer, decoded_body  # noqa: E402

ROOTS = {"agent": Path("/agent"), "runner": Path("/runner")}
SCRATCH = Path("/scratch")
PYCACHE_PREFIX = "/__absent_bytecode_cache"
RUNTIME_HELPER = Path("/opt/runtime-audit.py")
RUNTIME_MANIFEST = Path("/opt/runtime-manifest.json")
RUNNER_FILES = {
    f"buddha/{name}.py" for name in ("__init__", "channel", "releases", "wire", "candidate_worker")
}
STOP_REASONS = {"authority", "unknown", "protocol", "quota", "cancelled"}


class CandidateWorkerError(ReleaseError):
    """The selected source, runtime or worker protocol is invalid."""


class _Stop(BaseException):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _literal(value: object) -> str:
    if type(value) is not str:
        raise ValueError("expected literal UTF-8 text")
    value.encode("utf-8")
    return value


def _safe_environment() -> dict[str, str]:
    return {
        "HOME": str(SCRATCH / "home"),
        # Private bounded tmpfs created by the executor, never a host directory.
        "TMPDIR": "/tmp",  # nosec B108
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONNOUSERSITE": "1",
    }


def _consume(path: Path, expected: object) -> bytes:
    """Hash-check the exact bounded bytes consumed, with no executable cache loader."""
    digest = _digest(expected)
    if file_hash(path, max_bytes=MAX_JSON_BYTES) != digest:
        raise CandidateWorkerError("selected file hash differs")
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise CandidateWorkerError("selected bytes changed while consumed")
    return raw


class CandidateWorker:
    def __init__(self, initial: dict[str, object], reader: BinaryIO, writer: BinaryIO) -> None:
        try:
            self._initial = _json(initial)
            record = _load(self._initial)
            self.improvement = record.get("format") == "buddha.candidate-improvement-worker.v1"
            record = _object(
                record,
                {
                    "type",
                    "format",
                    "roots",
                    "inventories",
                    "entrypoint",
                    "agent_sha256",
                    "config",
                    "max_callbacks",
                    "runtime",
                }
                | ({"feedback"} if self.improvement else {"task"}),
            )
            if record["type"] != "configure" or record["format"] not in {
                "buddha.candidate-worker.v1",
                "buddha.candidate-improvement-worker.v1",
            }:
                raise CandidateWorkerError("unsupported worker configuration")
            roots = _object(record["roots"], {"agent", "runner"})
            self.roots = {name: Path(_text(value)) for name, value in roots.items()}
            if self.roots != ROOTS:
                raise CandidateWorkerError("worker roots differ from assigned mounts")
            self.inventories = _object(record["inventories"], {"agent", "runner"})
            for component in self.inventories.values():
                _inventory(component)
            self.entrypoint = _path(record["entrypoint"])
            # shortcut: one selected source file; inherited versioned bundles belong to SRC-02.
            if (
                not self.entrypoint.endswith(".py")
                or set(_object(self.inventories["agent"])) != {self.entrypoint}
                or set(_object(self.inventories["runner"])) != RUNNER_FILES
                or any(
                    Path(name).suffix.lower() in {".pyc", ".pyo"}
                    or "__pycache__" in Path(name).parts
                    for component in self.inventories.values()
                    for name in _object(component)
                )
                or _digest(record["agent_sha256"])
                != hashlib.sha256(_json(self.inventories["agent"])).hexdigest()
            ):
                raise CandidateWorkerError("selected source inventory differs")
            self.config = _object(
                record["config"],
                {"provider", "model", "max_output_tokens", "instructions", "sampling"},
            )
            if self.config["provider"] not in ("openai", "anthropic"):
                raise CandidateWorkerError("unsupported provider")
            _text(self.config["model"])
            _integer(self.config["max_output_tokens"], 1)
            if len(_literal(self.config["instructions"])) > 4000 or self.config["sampling"] not in (
                "regenerate",
                "in-context",
            ):
                raise CandidateWorkerError("unsupported candidate configuration")
            if self.improvement:
                feedback = record["feedback"]
                if (
                    type(feedback) is not list
                    or not 1 <= len(feedback) <= 1000
                    or len(_json(feedback)) > MAX_FEEDBACK_BYTES
                ):
                    raise CandidateWorkerError("invalid improvement feedback")
                seen: set[str | int] = set()
                for value in feedback:
                    item = _object(value, {"task", "note"})
                    task = _object(item["task"], {"id", "prompt", "count"})
                    identifier = task["id"]
                    if type(identifier) is int:
                        checked_id: str | int = _integer(identifier, -(2**63), 2**63 - 1)
                    else:
                        checked_id = _text(identifier)
                    if checked_id in seen:
                        raise CandidateWorkerError("feedback repeats a task")
                    seen.add(checked_id)
                    _literal(task["prompt"])
                    _integer(task["count"], 1, 1000)
                    note = _literal(item["note"])
                    if not note.strip() or len(note.encode()) > 4096:
                        raise CandidateWorkerError("invalid feedback note")
                self.feedback = feedback
            else:
                self.task = _object(record["task"], {"id", "prompt", "count"})
                identifier = self.task["id"]
                if type(identifier) is int:
                    _integer(identifier, -(2**63))
                else:
                    _text(identifier)
                _literal(self.task["prompt"])
                self.count = _integer(self.task["count"], 1, 1000)
            self.max_callbacks = _integer(record["max_callbacks"])
            self.runtime = _object(
                record["runtime"], {"sha256", "helper_sha256", "manifest_sha256"}
            )
            for digest in self.runtime.values():
                _digest(digest)
        except (ReleaseError, KeyError, TypeError, ValueError):
            raise CandidateWorkerError("invalid candidate worker configuration") from None
        self.reader, self.writer = reader, writer
        self.sequence = 0
        self.stopped: str | None = None
        self.poisoned = self.started = False

    @property
    def initial(self) -> dict[str, object]:
        return _load(self._initial)

    def _sources(self) -> None:
        try:
            cache, safe = Path(PYCACHE_PREFIX), _safe_environment()
            record = self.initial
            if (
                not sys.flags.isolated
                or not sys.dont_write_bytecode
                or sys.pycache_prefix != PYCACHE_PREFIX
                or cache.exists()
                or cache.is_symlink()
                or any(os.environ.get(key) != value for key, value in safe.items())
                or set(os.environ) - set(safe) - {"PATH", "LANG"}
                or self.roots != ROOTS
                or record["roots"] != {name: str(path) for name, path in self.roots.items()}
                or record["inventories"] != self.inventories
                or record["config"] != self.config
                or (
                    record["feedback"] != self.feedback
                    if self.improvement
                    else record["task"] != self.task
                )
                or record["entrypoint"] != self.entrypoint
                or record["max_callbacks"] != self.max_callbacks
                or record["runtime"] != self.runtime
            ):
                raise CandidateWorkerError("private environment or selected configuration changed")
            for name, root in self.roots.items():
                if inventory(root) != self.inventories[name]:
                    raise CandidateWorkerError("selected source changed")
            expected = self.roots["runner"] / "buddha/candidate_worker.py"
            if Path(__file__).resolve(strict=True) != expected.resolve(strict=True):
                raise CandidateWorkerError("executing worker has an unexpected origin")
            for name in ("buddha", "buddha.channel", "buddha.releases", "buddha.wire"):
                module = sys.modules[name]
                relative = (
                    "buddha/__init__.py" if name == "buddha" else name.replace(".", "/") + ".py"
                )
                if Path(module.__file__ or "").resolve(strict=True) != (
                    self.roots["runner"] / relative
                ).resolve(strict=True):
                    raise CandidateWorkerError("loaded runner has an unexpected origin")
        except (ReleaseError, OSError, KeyError, TypeError, ValueError):
            raise CandidateWorkerError("source or environment check failed") from None

    def _runtime(self) -> None:
        try:
            source = _consume(RUNTIME_HELPER, self.runtime["helper_sha256"])
            manifest = _consume(RUNTIME_MANIFEST, self.runtime["manifest_sha256"])
            namespace: dict[str, object] = {"__name__": "_buddha_candidate_runtime"}
            # Reviewed hash-bound image helper only; this is inside the confined worker.
            exec(compile(source, str(RUNTIME_HELPER), "exec"), namespace)  # nosec B102
            collect = namespace.get("collect_audit")
            if not callable(collect) or _json(_object(collect())) + b"\n" != manifest:
                raise CandidateWorkerError("fresh runtime inventory differs")
        except Exception:
            raise CandidateWorkerError("runtime check failed") from None

    def _complete(self, provider: str, body: bytes) -> object:
        if self.stopped is not None:
            raise _Stop(self.stopped)
        try:
            if self.poisoned:
                raise CandidateWorkerError("candidate channel already failed")
            self._sources()
            if (
                type(provider) is not str
                or provider != self.config["provider"]
                or (type(body) is not bytes or len(body) > MAX_BODY_BYTES)
            ):
                raise CandidateWorkerError("unsupported candidate callback")
            _load(body)
            sequence = self.sequence
            self.sequence += 1
            # The host alone enforces quota; send even the first over-quota callback.
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
            _object(response, {"type", "sequence", "reason" if kind == "stop" else "envelope"})
            if type(response["sequence"]) is not int or response["sequence"] != sequence:
                raise CandidateWorkerError("reply does not match pending callback")
            if kind == "stop":
                reason = response["reason"]
                if type(reason) is not str or reason not in STOP_REASONS:
                    raise CandidateWorkerError("unsupported host stop reason")
                self.stopped = reason
                raise _Stop(reason)
            if kind != "response":
                raise CandidateWorkerError("unsupported host frame")
            envelope = RawEnvelope.from_record(response["envelope"])
            if envelope.provider != provider or envelope.status != 200:
                raise CandidateWorkerError("reply differs from selected provider")
            return _load(decoded_body(envelope))
        except Exception:
            self.poisoned = True
            raise CandidateWorkerError("candidate callback or host response is invalid") from None

    def run(self) -> dict[str, object]:
        if self.started:
            raise CandidateWorkerError("worker may execute only one task")
        self.started = True
        answers: list[str] = []
        proposal: dict[str, object] = {
            "status": "not_returned",
            "value": None,
            "sha256": None,
            "bytes": None,
        }
        status, reason = "failed", "protocol"
        try:
            self._sources()
            self._runtime()
            path = self.roots["agent"] / self.entrypoint
            source = _consume(path, _object(self.inventories["agent"])[self.entrypoint])
            if self.improvement and len(source) > MAX_SOURCE_BYTES:
                raise CandidateWorkerError("parent source exceeds its byte ceiling")
            try:
                source.decode("utf-8")
            except UnicodeError:
                raise CandidateWorkerError("candidate source is not UTF-8") from None
            candidate = ModuleType("_buddha_candidate")
            candidate.__file__ = str(path)
            sys.modules[candidate.__name__] = candidate
            # Candidate bytes are executed only in the separately confined worker.
            exec(compile(source, str(path), "exec"), vars(candidate))  # nosec B102
            self._sources()
            input_key = "feedback_sha256" if self.improvement else "task_sha256"
            write_frame(
                self.writer,
                {
                    "type": "ready",
                    "agent_sha256": self.initial["agent_sha256"],
                    input_key: hashlib.sha256(
                        _json(self.feedback if self.improvement else self.task)
                    ).hexdigest(),
                    "runtime_sha256": self.runtime["sha256"],
                },
            )
            if self.improvement:
                improve = vars(candidate).get("propose_improvement")
                if not callable(improve) or not callable(vars(candidate).get("generate")):
                    raise ValueError("inherited entry points are unavailable")
                detached = _load(_json({"feedback": self.feedback, "config": self.config}))
                value: object = improve(
                    {
                        "entrypoint": self.entrypoint,
                        "source": source.decode("utf-8"),
                        "agent_sha256": self.initial["agent_sha256"],
                    },
                    detached["feedback"],
                    detached["config"],
                    self._complete,
                )
                proposal = _proposal_capture(value)
            else:
                generate = vars(candidate).get("generate")
                if not callable(generate):
                    raise ValueError("candidate entry point is not callable")
                value = generate(_load(_json(self.task)), _load(_json(self.config)), self._complete)
            if self.stopped is not None:
                raise _Stop(self.stopped)
            if self.poisoned:
                raise CandidateWorkerError("candidate channel failed")
            if self.improvement:
                if proposal["status"] != "captured":
                    status, reason = "failed", "proposal_" + str(proposal["status"])
                else:
                    try:
                        # Check the actual Python return before JSON normalizes subclasses.
                        checked = _source_proposal(value)
                        if checked["source"].encode("utf-8") == source:
                            raise ReleaseError("unchanged source")
                        status, reason = "complete", "complete"
                    except ReleaseError:
                        status, reason = "failed", "invalid_proposal"
            else:
                if type(value) is not list or len(value) != self.count:
                    raise ValueError("candidate did not return exact answer count")
                answers = [_literal(item) for item in value]
                status, reason = "complete", "complete"
        except _Stop as stop:
            status, reason = "stopped", stop.reason
        except CandidateWorkerError:
            status, reason = "failed", "protocol"
        except (Exception, SystemExit):
            status, reason = "failed", "agent_error"
        try:
            self._sources()
        except Exception:
            status, reason = "failed", "protocol"
        if self.stopped is not None:
            status, reason = "stopped", self.stopped
        elif self.poisoned:
            status, reason = "failed", "protocol"
        done: dict[str, object] = {
            "type": "done",
            "status": status,
            "reason": reason,
            **(
                {"proposal": proposal}
                if self.improvement
                else {"answers": answers if status == "complete" else []}
            ),
        }
        if self.improvement:
            try:
                _depth(done)
            except ChannelError:
                # Preserve known serialization identity, but omit a value the framed
                # channel cannot carry. Omitted-body metadata stays worker-declared.
                done["proposal"] = proposal | {"status": "omitted", "value": None}
                if reason in {"complete", "invalid_proposal"}:
                    done.update(status="failed", reason="proposal_unavailable")
        write_frame(self.writer, done)
        return done


def main() -> None:
    """Reserve the framed channel; candidate stdout becomes bounded stderr instead."""
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
            CandidateWorker(read_frame(reader), reader, writer).run()
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
