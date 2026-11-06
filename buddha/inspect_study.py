"""Inspect observation of one trusted offline operation; no execution authority.

The operation stays synchronous on its calling thread. An external process
owner, not Inspect's async cancellation, must enforce its lifetime.
"""

import importlib
import importlib.metadata
import json
import logging
import os
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from buddha import launch_common
from buddha.releases import ReleaseError, _root, file_hash

_STAGES = frozenset(
    "operation launcher restore forward_read prepare_common common_ineligible plan "
    "prepare_proposal proposal proposal_capacity prepare_child screen witness decision "
    "freeze publish".split()
)
_INCOMPLETE = frozenset({"incomplete", "partial", "stopped", "cancelled"})


def _safe_status(record: dict[str, object]) -> str:
    if record.get("stop_code") is not None:
        return "stopped"
    value = record.get("status")
    return (
        value
        if isinstance(value, str) and value in _INCOMPLETE | {"complete", "checked"}
        else "returned"
    )


class _ObservedFailure(RuntimeError):
    """Only a fixed public category, never the original error text or traceback."""


def _family(error: BaseException) -> str:
    for kind in (KeyboardInterrupt, TimeoutError, ReleaseError, ValueError, TypeError, OSError):
        if isinstance(error, kind):
            return kind.__name__
    return "Exception" if isinstance(error, Exception) else "BaseException"


def _redacted(error: BaseException) -> BaseException:
    if isinstance(error, KeyboardInterrupt):
        return KeyboardInterrupt("Buddha cancellation")
    if isinstance(error, TimeoutError):
        return TimeoutError("Buddha timeout")
    return _ObservedFailure(_family(error))


def _framework() -> tuple[Any, Any, Any, Any, Any]:
    if importlib.metadata.version("inspect-ai") != "0.3.287":
        raise RuntimeError("the selected Inspect version differs from the pinned integration")
    if importlib.metadata.version("platformdirs") != "4.14.3":
        raise RuntimeError("the selected platformdirs version differs from the pinned integration")
    directories = importlib.import_module("platformdirs")
    if any(
        not path.resolve().is_relative_to(Path.cwd())
        for path in (
            directories.user_data_path("inspect_ai"),
            directories.user_cache_path("inspect_ai"),
        )
    ):
        raise RuntimeError("Inspect application paths leave the owned observation directory")
    return (
        importlib.import_module("inspect_ai"),
        importlib.import_module("inspect_ai.dataset"),
        importlib.import_module("inspect_ai.solver"),
        importlib.import_module("inspect_ai.log"),
        importlib.import_module("inspect_ai.util"),
    )


def run(operation: Callable[[], dict[str, object]], *, log_dir: Path) -> dict[str, object]:
    """Observe one trusted offline call; preserve its canonical return or exception.

    The caller must already be in its owned empty-dotenv runtime, with
    platformdirs data/cache overrides and locals logging disabled. This call
    changes neither the caller's working directory nor its environment.
    Only fixed stage categories, numeric positions and public source hashes are
    recorded. Gateway calls and canonical accounting do not go through Inspect.
    """
    if any(name == "inspect_ai" or name.startswith("inspect_ai.") for name in sys.modules):
        raise ValueError("Inspect observation requires a fresh process")
    if not callable(operation) or not isinstance(log_dir, Path):
        raise ValueError("Inspect observation needs a callable and a fresh absolute Path")
    if launch_common._INSPECT_STAGE.get() is not None:
        raise ValueError("Inspect observation cannot be nested")
    log_dir = launch_common._path(str(log_dir))
    _root(log_dir.parent)
    if Path.cwd() != log_dir.parent or file_hash(Path.cwd() / ".env", max_bytes=0) != (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ):
        raise ValueError("Inspect requires an owned runtime with an empty dotenv")
    if os.environ.get("INSPECT_TRACEBACK_LOCALS") != "0":
        raise ValueError("Inspect locals logging must be explicitly disabled")
    if os.environ.get("INSPECT_TRACE_LEVEL", "TRACE") != "TRACE":
        raise ValueError("Inspect stage tracing must not be filtered out")
    for name in ("INSPECT_TRACE_FILE", "INSPECT_PY_LOGGER_FILE"):
        if value := os.environ.get(name):
            path = launch_common._path(value)
            if not path.is_relative_to(Path.cwd()) or os.path.lexists(path):
                raise ValueError("Inspect file overrides must be new paths in its owned runtime")
            _root(path.parent)
    log_dir.mkdir()
    observation = uuid4().hex
    sources = {
        name: file_hash(Path(__file__).with_name(name))
        for name in ("inspect_study.py", "improver_study.py", "launch_common.py")
    }
    results: list[dict[str, object]] = []
    failures: list[BaseException] = []
    inspect, dataset, solvers, logs, util = _framework()

    @contextmanager
    def stage(name: str, position: Mapping[str, object] | None) -> Iterator[None]:
        details = {"observation_id": observation, "stage": name if name in _STAGES else "other"}
        coordinates = {
            key: value
            for key, value in (position or {}).items()
            if key in {"start", "repetition", "arm", "slot"}
            and (value is None or type(value) is int and 0 <= value < 1_000_000)
        }
        error: BaseException | None = None
        try:
            with util.trace_action(logging.getLogger(__name__), "Buddha", json.dumps(details)):
                logs.transcript().info(details | {"event": "enter", "position": coordinates})
                try:
                    yield
                except BaseException as caught:
                    error = caught
                if error is not None:
                    logs.transcript().info(
                        details
                        | {
                            "event": "error",
                            "family": _family(error),
                            "diagnostic": launch_common._stop_diagnostic(error),
                        }
                    )
                    raise _redacted(error) from None
                logs.transcript().info(details | {"event": "exit"})
        except BaseException:
            if error is None:
                raise
        if error is not None:
            raise error

    def observed() -> Any:
        async def solve(state: Any, generate: Any) -> Any:
            async with util.span("Buddha offline operation"):
                token = launch_common._INSPECT_STAGE.set(stage)
                try:
                    with stage("operation", None):
                        results.append(operation())
                except BaseException as caught:
                    failures.append(caught)
                finally:
                    launch_common._INSPECT_STAGE.reset(token)
                if failures:
                    raise _redacted(failures[0]) from None
                safe_status = _safe_status(results[0])
                state.metadata["canonical_status"] = safe_status
                if safe_status in _INCOMPLETE:
                    raise _ObservedFailure("canonical operation incomplete")
            return state

        return solve

    task = inspect.Task(
        dataset=[
            dataset.Sample(
                id=observation,
                input="Buddha offline observation",
                metadata={"observer_sources_sha256": sources},
            )
        ],
        solver=solvers.solver(observed)(),
        model=None,
        scorer=None,
        checkpoint=False,
        name="buddha_observed",
        fail_on_error=True,
    )
    try:
        evaluations = inspect.eval(
            task,
            model=None,
            score=False,
            max_samples=1,
            max_tasks=1,
            epochs=1,
            fail_on_error=True,
            retry_on_error=0,
            task_retry_attempts=0,
            max_retries=0,
            checkpoint=False,
            acp_server=False,
            ctl_server=False,
            notification=False,
            display="none",
            debug_errors=False,
            log_dir=str(log_dir),
            log_samples=True,
            log_realtime=True,
            log_images=False,
            log_model_api=False,
            log_buffer=1,
            log_level="warning",
            log_level_transcript="warning",
        )
    except BaseException:
        if not failures:
            raise
    if failures:
        raise failures[0]
    if not results:
        raise RuntimeError("Inspect did not execute the selected operation")
    expected = "error" if _safe_status(results[0]) in _INCOMPLETE else "success"
    if len(evaluations) != 1 or evaluations[0].status != expected:
        raise RuntimeError("Inspect observation did not complete as expected")
    return results[0]
