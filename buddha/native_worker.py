"""One configured full-module native command over a bounded host-owned channel.

The executor supplies filesystem/network/process confinement. This worker never
contains provider credentials or a direct provider HTTP implementation.
"""

import asyncio
import base64
import hashlib
import importlib
import importlib.util
import inspect
import os
import shutil
import stat
import sys
import sysconfig
from contextlib import suppress
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any, BinaryIO

sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from buddha.channel import ChannelError, read_frame, write_frame  # noqa: E402
from buddha.native_context import Contexts, NativeStop  # noqa: E402
from buddha.native_transport import NativeRequest, make_transport  # noqa: E402
from buddha.releases import (  # noqa: E402
    ReleaseError,
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
from buddha.wire import RawEnvelope  # noqa: E402

WORKER_ROOTS = {
    "official": Path("/official"),
    "runner": Path("/runner"),
    "environment": Path("/opt/venv"),
    "inputs": Path("/inputs"),
    "artifacts": Path("/scratch/artifacts"),
}
RUNTIME_HELPER = Path("/opt/runtime-prepare.py")
RUNTIME_MANIFEST = Path("/opt/runtime-manifest.json")
MAX_FILES = 128
MAX_FILE_BYTES = 64 * 1024**2
MAX_TOTAL_BYTES = 128 * 1024**2
CHUNK_BYTES = 64 * 1024
PLACEHOLDER = "native-worker-placeholder-not-a-provider-key"
PYCACHE_PREFIX = "/__absent_bytecode_cache"
SAFE_ENV = {
    "HOME": "/scratch/home",
    "TMPDIR": "/tmp",  # nosec B108 - executor-owned bounded container tmpfs
    "ANTHROPIC_CONFIG_DIR": "/scratch/home/anthropic",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1",
    "PYTHONNOUSERSITE": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}
PARAMETERS = frozenset(
    {"instances", "output_file", "key_field", "config", "compute", "concurrency"}
)


class WorkerError(ReleaseError):
    """The sealed configuration, hook or output contract is unsupported."""


def _sha(value: object) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _texts(value: object, *, empty: bool = False) -> list[str]:
    if type(value) is not list or len(value) > 128 or (not empty and not value):
        raise WorkerError("expected bounded worker text list")
    return [_text(item) for item in value]


def _target(value: object) -> tuple[str, str]:
    text = _text(value)
    parts = text.split(":")
    if (
        len(parts) != 2
        or any(
            not part or any(not name.isidentifier() for name in part.split(".")) for part in parts
        )
        or "." in parts[1]
    ):
        raise WorkerError("hook requires module and direct attribute")
    return parts[0], parts[1]


class _ModuleView:
    def __init__(self, original: ModuleType, name: str, replacement: object) -> None:
        self.original, self.name, self.replacement = original, name, replacement

    def __getattr__(self, name: str) -> object:
        return self.replacement if name == self.name else getattr(self.original, name)


class NativeWorker:
    def __init__(self, config: dict[str, object], reader: BinaryIO, writer: BinaryIO) -> None:
        try:
            self.config = _load(_json(config))
            record = _object(
                self.config,
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
            if record["type"] != "configure" or record["format"] != "buddha.native-worker.v1":
                raise WorkerError("unsupported native worker configuration")
            roots = _object(record["roots"], set(WORKER_ROOTS))
            self.roots = {name: Path(_text(value)) for name, value in roots.items()}
            if self.roots != WORKER_ROOTS:
                raise WorkerError("worker roots differ from the assigned mount contract")
            for name in ("release_sha256", "answers_sha256"):
                _digest(record[name])
            self.command = _object(record["command"], {"index", "module", "argv", "sha256"})
            index = self.command["index"]
            if type(index) is not int or not 0 <= index < 2**31:
                raise WorkerError("invalid native command index")
            module = _text(self.command["module"])
            if any(not name.isidentifier() for name in module.split(".")):
                raise WorkerError("invalid native command module")
            _texts(self.command["argv"], empty=True)
            _digest(self.command["sha256"])
            self.inventories = _object(record["inventories"], {"official", "runner", "environment"})
            self.hooks = _object(record["hooks"], {"modules", "cache", "calls", "sdk"})
            self.module_names = _texts(self.hooks["modules"])
            if (
                len(set(self.module_names)) != len(self.module_names)
                or module not in self.module_names
            ):
                raise WorkerError("native modules must be unique and include the command")
        except (ReleaseError, TypeError, ValueError):
            raise WorkerError("invalid native worker configuration") from None
        self.reader, self.writer = reader, writer
        self.contexts = Contexts()
        self.lock = asyncio.Lock()
        self.sequence = 0
        self.stopped: str | None = None
        self.prepared = False
        self.aliases: list[dict[str, object]] = []
        self.modules: dict[str, ModuleType] = {}
        self.clients: list[Any] = []
        self.expected_environment: dict[str, object] = {}

    def _environment(self) -> dict[str, object]:
        expected = _object(self.inventories["environment"])
        if set(expected) not in (
            {"helper_sha256", "manifest_sha256", "inventory"},
            {"helper_sha256", "manifest_sha256", "inventory", "synthetic_modules"},
        ):
            raise WorkerError("invalid installed runtime contract")
        if file_hash(RUNTIME_HELPER) != _digest(expected["helper_sha256"]) or file_hash(
            RUNTIME_MANIFEST
        ) != _digest(expected["manifest_sha256"]):
            raise WorkerError("installed runtime evidence changed")
        manifest = _load(RUNTIME_MANIFEST.read_bytes())
        if (
            manifest.get("format") != "buddha.review.nb02c3-installed-runtime.v1"
            or manifest.get("inventory") != expected["inventory"]
        ):
            raise WorkerError("installed runtime manifest differs from owner")
        spec = importlib.util.spec_from_file_location("_buddha_runtime_audit", RUNTIME_HELPER)
        if spec is None or spec.loader is None:
            raise WorkerError("runtime audit helper is unavailable")
        helper = importlib.util.module_from_spec(spec)
        sys.modules["_buddha_runtime_audit"] = helper
        spec.loader.exec_module(helper)
        actual = helper.collect_audit()
        if actual.get("inventory") != expected["inventory"]:
            raise WorkerError("actual installed runtime differs from owner")
        if "synthetic_modules" in expected:
            names = _texts(expected["synthetic_modules"], empty=True)
            if len(names) != len(set(names)):
                raise WorkerError("duplicate synthetic module declaration")
        return _object(actual["inventory"])

    def _origin(self, path: Path) -> dict[str, object]:
        path = path.resolve(strict=True)
        for role in ("official", "runner"):
            root = self.roots[role].resolve()
            if path.is_relative_to(root):
                relative = path.relative_to(root).as_posix()
                expected = _object(self.inventories[role]).get(relative)
                if expected is None or file_hash(path) != _digest(expected):
                    raise WorkerError("imported selected source differs from inventory")
                return {"kind": role, "path": str(path), "sha256": expected}
        environment = self.roots["environment"].resolve()
        if path.is_relative_to(environment):
            entry = _object(self.expected_environment.get(path.relative_to(environment).as_posix()))
            if file_hash(path) != _digest(entry.get("sha256")):
                raise WorkerError("imported environment file differs from inventory")
            return {"kind": "environment", "path": str(path), "sha256": entry["sha256"]}
        if path == RUNTIME_HELPER.resolve():
            expected = _object(self.inventories["environment"])["helper_sha256"]
            if file_hash(path) != expected:
                raise WorkerError("runtime helper origin changed")
            return {"kind": "image-helper", "path": str(path), "sha256": expected}
        stdlib = Path(sysconfig.get_path("stdlib")).resolve()
        if path.is_relative_to(stdlib) and "site-packages" not in path.relative_to(stdlib).parts:
            return {"kind": "base-image", "path": str(path), "sha256": file_hash(path)}
        raise WorkerError("imported module is outside the selected runtime")

    def _audit_imports(self) -> dict[str, object]:
        result: dict[str, object] = {}
        environment = _object(self.inventories["environment"])
        synthetic = _texts(environment.get("synthetic_modules", []), empty=True)
        for name, module in tuple(sys.modules.items()):
            if module is None:
                continue
            spec = getattr(module, "__spec__", None)
            origin = getattr(spec, "origin", None)
            file = getattr(module, "__file__", None)
            if origin in {"built-in", "frozen"}:
                result[name] = {"kind": origin}
            elif file:
                result[name] = self._origin(Path(file))
            elif origin is None and name in synthetic:
                loader = getattr(module, "__loader__", None)
                entry: dict[str, object] = {"kind": "image-synthetic"}
                if loader is not None:
                    owner = sys.modules.get(type(loader).__module__)
                    owner_file = getattr(owner, "__file__", None)
                    if not owner_file:
                        raise WorkerError("synthetic loader has no sealed owner")
                    entry["loader_owner"] = self._origin(Path(owner_file))
                    if _object(entry["loader_owner"])["kind"] != "environment":
                        raise WorkerError("synthetic loader owner is outside environment")
                result[name] = entry
            elif getattr(module, "__path__", None) is not None:
                paths = [Path(item).resolve(strict=True) for item in module.__path__]
                allowed = [
                    self.roots[role].resolve() for role in ("official", "runner", "environment")
                ]
                if not paths or any(
                    not any(path.is_relative_to(root) for root in allowed) for path in paths
                ):
                    raise WorkerError("namespace origin is outside selected roots")
                result[name] = {"kind": "namespace", "paths": [str(path) for path in paths]}
            else:
                raise WorkerError("unattributed imported module")
        return result

    def _resolve(self, target: object) -> tuple[ModuleType, str, Any]:
        name, attribute = _target(target)
        if name not in self.modules:
            raise WorkerError("hook target is not a selected official module")
        module = self.modules[name]
        original = getattr(module, attribute)
        if not callable(original) or getattr(original, "__module__", None) != name:
            raise WorkerError("hook target is not owned by its declared module")
        return module, attribute, original

    def _replace(self, original: object, replacement: object, label: str) -> list[str]:
        paths = []
        for name, module in self.modules.items():
            for attribute, value in tuple(vars(module).items()):
                if value is original:
                    setattr(module, attribute, replacement)
                    path = name + ":" + attribute
                    paths.append(path)
                    self.aliases.append({"path": path, "label": label})
        if not paths:
            raise WorkerError("configured hook has no selected binding")
        return paths

    def _cache(self, description: object) -> None:
        record = _object(description, {"target", "key_target", "parameters", "id_field"})
        _, _, original = self._resolve(record["target"])
        _, _, key = self._resolve(record["key_target"])
        if not inspect.iscoroutinefunction(original) or inspect.iscoroutinefunction(key):
            raise WorkerError("unsupported native cache callable kinds")
        mapping = _object(record["parameters"], set(PARAMETERS))
        names = [_text(value) for value in mapping.values()]
        signature = inspect.signature(original)
        if len(set(names)) != len(names) or set(names) - set(signature.parameters):
            raise WorkerError("cache parameter mapping differs from actual callable")
        id_field = _text(record["id_field"])

        @wraps(original)
        async def cached(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            compute = bound.arguments[_text(mapping["compute"])]
            config = bound.arguments[_text(mapping["config"])]
            output = Path(bound.arguments[_text(mapping["output_file"])]).resolve()
            relative = _path(output.relative_to(self.roots["artifacts"].resolve()).as_posix())
            key_field = _text(bound.arguments[_text(mapping["key_field"])])
            if not inspect.iscoroutinefunction(compute):
                raise WorkerError("native cache compute must be async")

            @wraps(compute)
            async def row(instance: dict[str, object]) -> Any:
                identifier = instance[id_field]
                if type(identifier) not in {str, int} or (
                    type(identifier) is int and not -(2**63) <= identifier < 2**63
                ):
                    raise WorkerError("native row ID must be str or int64")
                if type(identifier) is str:
                    _text(identifier)
                identity = _sha(
                    [
                        self.command,
                        self.config["release_sha256"],
                        self.config["answers_sha256"],
                        relative,
                        key_field,
                        key(instance, config),
                        type(identifier).__name__,
                        identifier,
                    ]
                )
                with self.contexts.row(identity):
                    return await compute(instance)

            bound.arguments[_text(mapping["compute"])] = row
            return await original(*bound.args, **bound.kwargs)

        self._replace(original, cached, "cache")

    def _sdk(self, description: object) -> None:
        record = _object(description, {"provider", "constructor", "module_slots"})
        provider = _text(record["provider"])
        constructors = {
            "openai": ("openai", "AsyncOpenAI", "httpx"),
            "anthropic": ("anthropic", "AsyncAnthropic", "httpx2"),
        }
        if provider not in constructors:
            raise WorkerError("unsupported native SDK provider")
        module_name, attribute, http_name = constructors[provider]
        if record["constructor"] != module_name + ":" + attribute:
            raise WorkerError("SDK constructor differs from its supported capability")
        sdk = importlib.import_module(module_name)
        original = getattr(sdk, attribute)
        http = importlib.import_module(http_name)

        def factory(*args: Any, **kwargs: Any) -> Any:
            if args or "http_client" in kwargs or kwargs.get("api_key", PLACEHOLDER) != PLACEHOLDER:
                raise WorkerError(
                    "native SDK constructor attempts unsupported credentials or transport"
                )
            kwargs["api_key"] = PLACEHOLDER
            if provider == "anthropic":
                kwargs.setdefault("webhook_key", PLACEHOLDER)
            client = http.AsyncClient(
                transport=make_transport(provider, contexts=self.contexts, exchange=self.exchange),
                trust_env=False,
            )
            self.clients.append(client)
            value = original(http_client=client, **kwargs)
            self.clients.append(value)
            return value

        paths = (
            self._replace(original, factory, "sdk:" + provider)
            if any(
                value is original
                for module in self.modules.values()
                for value in vars(module).values()
            )
            else []
        )
        if any(value is sdk for module in self.modules.values() for value in vars(module).values()):
            paths += self._replace(sdk, _ModuleView(sdk, attribute, factory), "sdk:" + provider)
        expected = _texts(record["module_slots"])
        if set(paths) != set(expected) or len(expected) != len(set(expected)):
            raise WorkerError("SDK selected alias bindings differ from configuration")

    def prepare(self) -> None:
        if self.prepared:
            return
        try:
            cache = Path(PYCACHE_PREFIX)
            if sys.pycache_prefix != PYCACHE_PREFIX or cache.exists() or cache.is_symlink():
                raise WorkerError("native bytecode cache isolation is not active")
            for role in ("official", "runner"):
                if inventory(self.roots[role]) != self.inventories[role]:
                    raise WorkerError("actual selected source tree differs from inventory")
            self.expected_environment = self._environment()
            _root(self.roots["inputs"])
            _root(self.roots["artifacts"])
            if any(self.roots["artifacts"].iterdir()):
                raise WorkerError("worker artifact directory must start empty")
            inputs = self.config["inputs"]
            if type(inputs) is not list or len(inputs) > MAX_FILES:
                raise WorkerError("invalid bounded native input list")
            destinations = set()
            total = 0
            for raw in inputs:
                entry = _object(raw, {"source", "destination", "sha256"})
                source = self.roots["inputs"] / _path(entry["source"])
                destination = self.roots["artifacts"] / _path(entry["destination"])
                expected = _digest(entry["sha256"])
                if (
                    destination in destinations
                    or file_hash(source, max_bytes=MAX_FILE_BYTES) != expected
                ):
                    raise WorkerError("native input differs from its owner")
                destinations.add(destination)
                total += source.stat().st_size
                if total > MAX_TOTAL_BYTES:
                    raise WorkerError("native inputs exceed aggregate ceiling")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                if file_hash(destination, max_bytes=MAX_FILE_BYTES) != expected:
                    raise WorkerError("native input changed during materialization")
            sys.path.insert(0, str(self.roots["official"]))
            self.modules = {name: importlib.import_module(name) for name in self.module_names}
            for module in self.modules.values():
                file = getattr(module, "__file__", None)
                if not file or not Path(file).resolve().is_relative_to(
                    self.roots["official"].resolve()
                ):
                    raise WorkerError("selected official module has an unexpected origin")
            if self.hooks["cache"] is not None:
                self._cache(self.hooks["cache"])
            calls = self.hooks["calls"]
            if type(calls) is not list or len(calls) > 32:
                raise WorkerError("invalid call-hook list")
            seen = set()
            labels = set()
            for raw in calls:
                entry = _object(raw, {"target", "label"})
                _, _, original = self._resolve(entry["target"])
                label = _text(entry["label"])
                if original in seen or label in labels or not inspect.iscoroutinefunction(original):
                    raise WorkerError("duplicate or nonasync native call hook")
                seen.add(original)
                labels.add(label)
                self._replace(original, self.contexts.wrap(original, label), label)
            sdk = self.hooks["sdk"]
            if type(sdk) is not list or len(sdk) > 2:
                raise WorkerError("invalid SDK hook list")
            for entry in sdk:
                self._sdk(entry)
            self.ready_audit = self._audit_imports()
            self.prepared = True
        except Exception:
            raise WorkerError("native preparation or hook compatibility failed") from None

    async def exchange(self, request: NativeRequest) -> RawEnvelope:
        async with self.lock:
            if self.stopped is not None:
                raise NativeStop(self.stopped)
            sequence = self.sequence
            self.sequence += 1
            try:
                self._audit_imports()
                write_frame(
                    self.writer,
                    {
                        "type": "request",
                        "seq": sequence,
                        "request": {
                            "provider": request.provider,
                            "method": request.method,
                            "url": request.url,
                            "body_base64": base64.b64encode(request.body).decode("ascii"),
                            "headers": [list(pair) for pair in request.headers],
                            "logical_id": request.logical_id,
                            "attempt": request.attempt,
                        },
                    },
                )
                frame = read_frame(self.reader)
                if type(frame.get("seq")) is not int or frame["seq"] != sequence:
                    raise WorkerError("worker response correlation differs")
                if frame.get("type") == "stop":
                    _object(frame, {"type", "seq", "reason"})
                    reason = _text(frame["reason"])
                    NativeStop(reason)
                    self.stopped = reason
                    raise NativeStop(reason)
                _object(frame, {"type", "seq", "envelope"})
                if frame["type"] != "response":
                    raise WorkerError("unexpected worker channel response")
                envelope = RawEnvelope.from_record(frame["envelope"])
                if envelope.provider != request.provider:
                    raise WorkerError("worker response provider differs")
                return envelope
            except NativeStop:
                raise
            except ChannelError:
                self.stopped = "unknown"
                raise NativeStop("unknown") from None
            except Exception:
                self.stopped = "protocol"
                raise NativeStop("protocol") from None

    def _files(self) -> None:
        root = _root(self.roots["artifacts"])
        paths = []
        total = 0
        for parent, directories, files in root.walk(
            on_error=lambda error: (_ for _ in ()).throw(error)
        ):
            for name in (*directories, *files):
                path = parent / name
                info = path.lstat()
                if (
                    path.is_symlink()
                    or info.st_nlink != 1
                    and stat.S_ISREG(info.st_mode)
                    or (not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode))
                ):
                    raise WorkerError("native artifact contains links or special files")
                if stat.S_ISREG(info.st_mode):
                    total += info.st_size
                    paths.append(path)
                    if (
                        info.st_size > MAX_FILE_BYTES
                        or total > MAX_TOTAL_BYTES
                        or len(paths) > MAX_FILES
                    ):
                        raise WorkerError("native artifacts exceed bounded output limits")
        for path in sorted(paths):
            relative = _path(path.relative_to(root).as_posix())
            size = path.stat().st_size
            offset = 0
            with path.open("rb") as stream:
                while True:
                    chunk = stream.read(CHUNK_BYTES)
                    write_frame(
                        self.writer,
                        {
                            "type": "file",
                            "path": relative,
                            "offset": offset,
                            "data_base64": base64.b64encode(chunk).decode("ascii"),
                            "eof": offset + len(chunk) == size,
                        },
                    )
                    offset += len(chunk)
                    if offset == size:
                        break
                    if not chunk or offset > size:
                        raise WorkerError("native artifact changed during collection")

    async def run(self) -> None:
        existing_tasks = asyncio.all_tasks()
        status, reason = "failed", "protocol"
        audit: dict[str, object] = {}
        try:
            self.prepare()
            write_frame(
                self.writer, {"type": "ready", "aliases": self.aliases, "audit": self.ready_audit}
            )
            sys.argv = [_text(self.command["module"]), *_texts(self.command["argv"], empty=True)]
            entry = self.modules[_text(self.command["module"])].main
            if inspect.iscoroutinefunction(entry):
                await entry()
            else:
                value = entry()
                if inspect.isawaitable(value):
                    raise WorkerError("native synchronous entry returned an unexpected awaitable")
            status, reason = "complete", "complete"
        except NativeStop as stop:
            status, reason = "stopped", stop.reason
        except Exception:
            status, reason = "failed", "native_error"
        finally:
            if status != "complete" and self.stopped is None:
                self.stopped = (
                    reason
                    if reason in {"authority", "unknown", "protocol", "cancelled"}
                    else "protocol"
                )
            pending = [task for task in asyncio.all_tasks() if task not in existing_tasks]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for client in reversed(self.clients):
                with suppress(Exception):
                    await client.aclose()
            try:
                audit = self._audit_imports()
            except Exception:
                status, reason = "failed", "protocol"
            try:
                self._files()
            except Exception:
                status, reason = "failed", "protocol"
            write_frame(
                self.writer, {"type": "done", "status": status, "reason": reason, "audit": audit}
            )


def main() -> None:
    """Reserve RPC descriptors before any official import or native diagnostic."""
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
            os.environ.update(safe | SAFE_ENV)
            WORKER_ROOTS["artifacts"].mkdir(parents=True, exist_ok=True)
            _root(WORKER_ROOTS["artifacts"])
            (WORKER_ROOTS["artifacts"].parent / "home").mkdir(exist_ok=True)
            os.chdir(WORKER_ROOTS["artifacts"])
            config = read_frame(reader)
            worker = NativeWorker(config, reader, writer)
            asyncio.run(worker.run())
        except (Exception, NativeStop):
            write_frame(
                writer, {"type": "done", "status": "failed", "reason": "protocol", "audit": {}}
            )


if __name__ == "__main__":
    main()
