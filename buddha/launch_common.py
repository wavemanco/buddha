"""Shared passive launch checks and observer-only progress reporting."""

import hashlib
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from types import GetSetDescriptorType, ModuleType, TracebackType
from typing import TYPE_CHECKING, Protocol, cast

from buddha import credentials, gateway
from buddha import native_pipeline as pipeline
from buddha.doctor import _Busy, _Unsupported
from buddha.gateway_history import MAX_LEDGER_BYTES
from buddha.provider import ModelSpec
from buddha.releases import (
    MAX_JSON_BYTES,
    ROLES,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _root,
    _text,
)
from buddha.search_evidence import (
    EvidenceFieldLimitError,
    EvidencePathLimitError,
    EvidenceTotalLimitError,
    _read,
    _sidecars,
    read_authority,
)

if TYPE_CHECKING:
    from buddha.source_screen import SourceScreen

# Frozen v1 coverage; future source-inventory additions cannot expand this profile.
_UNIFIED_HELPERS_V1 = frozenset(
    """__init__.py agent_run.py agent_worker.py answers.py archive.py authorization.py
    baseline.py baseline_results.py baseline_state.py candidate_generation.py
    candidate_improvement.py candidate_improvement_results.py candidate_run.py candidate_worker.py
    channel.py common.py comparison_observation.py credentials.py doctor.py evaluation.py
    executor.py
    final_evaluation.py gateway.py gateway_history.py history.py improvement_rule.py
    improver_analysis.py improver_assessment.py improver_handoff.py improver_launch.py
    improver_launch_state.py improver_study.py launch_common.py ledger.py native_context.py
    native_evaluation.py native_evidence.py native_pipeline.py native_run.py native_transport.py
    native_worker.py noveltybench_results.py plain_comparison.py policy_panel.py policy_results.py
    policy_study.py process_observation.py provider.py reference.py releases.py search_evidence.py
    source_capacity.py source_feedback.py source_review.py source_review_handoff.py
    source_review_results.py source_screen.py source_screen_results.py source_search.py
    trial_fence.py unified_funding.py unified_launch.py validation_analysis.py validation_study.py
    wire.py""".split()
)
_UNIFIED_OUTER_V1 = (
    "agents/frozen_seed.py",
    "docs/conformance/imp01-run.py",
    "docs/conformance/unified-run.py",
)
_UNIFIED_ROLES_V1 = frozenset("buddha/" + name for name in _UNIFIED_HELPERS_V1) | frozenset(
    _UNIFIED_OUTER_V1
)

_WITNESS_CONTINUATION: ContextVar[
    Callable[[Path, Path, "SourceScreen", Mapping[Path, str], Path | None], dict[Path, str]] | None
] = ContextVar("witness_continuation", default=None)

_STUDY_CONTINUATION: ContextVar[
    Callable[[Path, Path, Mapping[Path, str]], dict[Path, str]] | None
] = ContextVar("study_continuation", default=None)


class _SourceResolver(Protocol):
    def __call__(self, current: Mapping[str, str], *, relative: bool) -> dict[str, str]: ...


_PHASE_CONTINUATION: ContextVar[
    tuple[
        _SourceResolver,
        Callable[[Path, str, Mapping[Path, str]], dict[Path, str]],
        Callable[[Path], None] | None,
    ]
    | None
] = ContextVar("phase_continuation", default=None)


@contextmanager
def _phase_continuation(
    source_resolver: _SourceResolver,
    controls_resolver: Callable[[Path, str, Mapping[Path, str]], dict[Path, str]],
    *,
    before_start: Callable[[Path], None] | None = None,
) -> Iterator[None]:
    """Use explicit checked phase projections; this supplies no funding authority."""
    if (
        not callable(source_resolver)
        or not callable(controls_resolver)
        or before_start is not None
        and not callable(before_start)
        or _PHASE_CONTINUATION.get() is not None
    ):
        raise ReleaseError("phase continuation needs one explicit unnested scope")
    token = _PHASE_CONTINUATION.set((source_resolver, controls_resolver, before_start))
    try:
        yield
    finally:
        _PHASE_CONTINUATION.reset(token)


def _historical_sources(current: Mapping[str, str], *, relative: bool = False) -> dict[str, str]:
    """Join actual installed roles to their exact original approval references."""
    if type(relative) is not bool:
        raise ReleaseError("source projection needs an explicit relative-key mode")
    scope = _PHASE_CONTINUATION.get()
    original = dict(current)
    result = original if scope is None else dict(scope[0](original, relative=relative))
    if len(result) != len(current):
        raise ReleaseError("source projection changes its exact role coverage")
    if relative and result.keys() != current.keys():
        raise ReleaseError("relative source projection changes its exact role coverage")
    return {name: _digest(pin) for name, pin in _object(result).items()}


def _continued_phase_controls(
    trial: Path, phase: str, controls: Mapping[Path, str]
) -> dict[Path, str]:
    """Project one complete collected final/plain union, preserving old state."""
    scope = _PHASE_CONTINUATION.get()
    pins = dict(controls)
    if scope is None:
        return pins
    if phase not in {"final", "plain"}:
        raise ReleaseError("phase continuation supports only final and plain controls")
    return dict(scope[1](trial, phase, pins))


def _phase_before_start(trial: Path) -> None:
    """Rejoin checked continuation evidence at the coordinator's writer boundary."""
    scope = _PHASE_CONTINUATION.get()
    if scope is not None and scope[2] is not None:
        scope[2](trial)


@contextmanager
def _study_continuation(
    resolver: Callable[[Path, Path, Mapping[Path, str]], dict[Path, str]],
) -> Iterator[None]:
    """Use one explicitly checked development adapter in its consuming thread."""
    if (
        not callable(resolver)
        or _STUDY_CONTINUATION.get() is not None
        or _WITNESS_CONTINUATION.get() is not None
    ):
        raise ReleaseError("study continuation needs one explicit unnested scope")
    token = _STUDY_CONTINUATION.set(resolver)
    try:
        yield
    finally:
        _STUDY_CONTINUATION.reset(token)


def _continued_study_controls(
    root: Path, owner: Path, controls: Mapping[Path, str]
) -> dict[Path, str]:
    resolver = _STUDY_CONTINUATION.get()
    return dict(controls) if resolver is None else resolver(root, owner, controls)


@contextmanager
def _witness_continuation(
    resolver: Callable[
        [Path, Path, "SourceScreen", Mapping[Path, str], Path | None], dict[Path, str]
    ],
) -> Iterator[None]:
    """A pinned adapter explicitly scopes one checked witness; never discover one."""
    if not callable(resolver) or _WITNESS_CONTINUATION.get() is not None:
        raise ReleaseError("witness continuation needs one explicit unnested scope")
    token = _WITNESS_CONTINUATION.set(resolver)
    try:
        yield
    finally:
        _WITNESS_CONTINUATION.reset(token)


def _continued_witness_controls(
    root: Path, directory: Path, screen: "SourceScreen", controls: Mapping[Path, str]
) -> dict[Path, str]:
    resolver = _WITNESS_CONTINUATION.get()
    return dict(controls) if resolver is None else resolver(root, directory, screen, controls, None)


def _continued_witness_parent_controls(
    root: Path, directory: Path, screen: "SourceScreen", controls: Mapping[Path, str], parent: Path
) -> dict[Path, str]:
    resolver = _WITNESS_CONTINUATION.get()
    return (
        dict(controls) if resolver is None else resolver(root, directory, screen, controls, parent)
    )


def _stop_reason(error: BaseException) -> str:
    """Expose only fixed trusted reasons through bounded redacting error chains."""
    reasons = {
        EvidenceTotalLimitError: "evidence_total_bytes_limit",
        EvidenceFieldLimitError: "evidence_field_bytes_limit",
        EvidencePathLimitError: "evidence_path_count_limit",
    }
    keys = {"key_terminal_required", "key_input_unavailable", "key_input_invalid"}
    pending = [error]
    seen: set[int] = set()
    while pending and len(seen) < 32:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        reason = reasons.get(type(current))
        if reason is not None:
            return reason
        if type(current) is credentials.KeyInputError:
            code = current.code
            if type(code) is str and code in keys:
                return code
        for nested in (current.__context__, current.__cause__):
            if nested is not None:
                pending.append(nested)
    return "launch_stopped"


def _stop_diagnostic(error: BaseException) -> dict[str, object]:
    """Bounded public-code locations only; never inspect exception text or locals."""
    kinds = {
        OSError: "os_error",
        ValueError: "value_error",
        TypeError: "type_error",
        KeyError: "key_error",
        RuntimeError: "runtime_error",
        ReleaseError: "validation_error",
        pipeline.PipelineError: "validation_error",
        _Busy: "evidence_busy",
        _Unsupported: "evidence_unsupported",
        credentials.KeyInputError: "key_input",
        EvidenceTotalLimitError: "evidence_total_limit",
        EvidenceFieldLimitError: "evidence_field_limit",
        EvidencePathLimitError: "evidence_path_limit",
    }
    package = Path(__file__).absolute().parent
    sources = {
        str(package / name): name for name in _UNIFIED_HELPERS_V1 | {"unified_continuation.py"}
    }
    chain: list[dict[str, object]] = []
    pending = [error]
    seen: set[int] = set()
    while pending and len(seen) < 8:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        frames: list[dict[str, object]] = []
        traceback = cast(
            TracebackType | None,
            cast(GetSetDescriptorType, vars(BaseException)["__traceback__"]).__get__(current),
        )
        for _ in range(64):
            if traceback is None:
                break
            frame = traceback.tb_frame
            name = sources.get(frame.f_code.co_filename)
            module = None if name is None else sys.modules.get("buddha." + name[:-3])
            line = traceback.tb_lineno
            if (
                isinstance(module, ModuleType)
                and frame.f_globals is vars(module)
                and type(line) is int
                and 0 < line <= 1_000_000
            ):
                frames.append({"file": name, "line": line})
                frames = frames[-8:]
            traceback = traceback.tb_next
        chain.append({"kind": kinds.get(type(current), "other"), "frames": frames})
        for attribute in ("__context__", "__cause__"):
            nested = cast(
                BaseException | None,
                cast(GetSetDescriptorType, vars(BaseException)[attribute]).__get__(current),
            )
            if nested is not None and len(pending) < 16:
                pending.append(nested)
    return {
        "format": "buddha.launch-stop-diagnostic.v1",
        "reason": _stop_reason(error),
        "chain": chain,
    }


def _path(value: object, *, error: type[ReleaseError] = ReleaseError) -> Path:
    # Leaves need not exist yet; callers separately check input reads/parents.
    path = pipeline._absolute(value)
    if str(path) != value or ".." in path.parts or str(value).startswith(("//", "\\\\")):
        raise error("launch paths must have one canonical spelling")
    return path


def _helper_role_relation(
    raw: bytes,
    *,
    original_source_manifest: bytes,
    expected_overlay: Mapping[str, str],
    screen: "SourceScreen",
    before_context: object,
    before_controls: Mapping[Path, str],
    after_context: object,
    after_controls: Mapping[Path, str],
) -> dict[Path, str]:
    """Check a bound handoff's frozen 68-role projection for one planned screen.

    No I/O or launcher uses this relation. An outer loader must still join all
    original actors, grants and the cut, verify actual files and review repair
    semantics. Keeping metadata consistent does not establish those facts.
    """
    from buddha import candidate_generation, candidate_improvement
    from buddha.source_screen import SourceScreen, _comparison_controls, _version

    spellings: dict[str, str] = {}

    def remember(path: Path) -> Path:
        # Check before Windows Path keys can coalesce differently spelled inputs.
        alias = str(path).casefold()
        if alias in spellings and spellings[alias] != str(path):
            raise ReleaseError("helper role paths have conflicting canonical spellings")
        spellings[alias] = str(path)
        return path

    def reference(value: object) -> tuple[Path, str]:
        row = _object(value, {"path", "sha256"})
        return remember(_path(row["path"])), _digest(row["sha256"])

    if not isinstance(expected_overlay, Mapping) or len(expected_overlay) != 2:
        raise ReleaseError("helper relation requires an explicit overlay reference")
    overlay, overlay_sha = reference(dict(expected_overlay))
    if (
        type(raw) is not bytes
        or len(raw) > MAX_JSON_BYTES
        or hashlib.sha256(raw).hexdigest() != overlay_sha
    ):
        raise ReleaseError("helper relation bytes differ from their explicit reference")
    relation = _object(_load(raw), {"format", "source_manifest", "roles"})
    if relation["format"] != "buddha.helper-role-relation.v1" or type(screen) is not SourceScreen:
        raise ReleaseError("unsupported helper relation or planned screen")

    def controls(value: object, *, strings: bool = False) -> dict[Path, str]:
        if not isinstance(value, Mapping) or len(value) > 1024:
            raise ReleaseError("helper relation controls exceed the original path boundary")
        result: dict[Path, str] = {}
        aliases = set()
        for key, pin in value.items():
            if not strings and not isinstance(key, Path):
                raise ReleaseError("helper relation controls need explicit Paths")
            path = remember(_path(key if strings else str(key)))
            alias = str(path).casefold()
            if alias in aliases:
                raise ReleaseError("helper relation controls have path aliases")
            aliases.add(alias)
            result[path] = _digest(pin)
        return result

    planned = screen.to_record()
    runtime = _object(_object(planned["generation"])["runtime"])
    supplied = [controls(before_controls), controls(after_controls)]
    source_path, source_sha = reference(relation["source_manifest"])
    if (
        supplied[0].get(source_path) != source_sha
        or type(original_source_manifest) is not bytes
        or len(original_source_manifest) > MAX_JSON_BYTES
        or hashlib.sha256(original_source_manifest).hexdigest() != source_sha
    ):
        raise ReleaseError("original source manifest differs from its bound reference")
    original = _object(
        _load(original_source_manifest),
        {"format", "assessment", "expected_runtime_sha256", "directory", "source_sha256"},
    )
    assessment_path, assessment_sha = reference(original["assessment"])
    remember(_path(original["directory"]))
    if (
        original["format"] != "buddha.improver-handoff.v1"
        or original["expected_runtime_sha256"] != runtime["sha256"]
        or supplied[0].get(assessment_path) != assessment_sha
    ):
        raise ReleaseError("original source manifest changes its frozen handoff")
    recorded = controls(_object(original["source_sha256"]), strings=True)
    if (
        not recorded
        or len(recorded) > 1023
        or any(supplied[0].get(path) != pin for path, pin in recorded.items())
    ):
        raise ReleaseError("original source manifest omitted bound source/control pins")
    sources = []
    for context, pins in zip((before_context, after_context), supplied, strict=True):
        checked = _object(
            context,
            {
                "format",
                "screen_sha256",
                "expected_runtime_sha256",
                "controls",
                "comparison_controls",
            },
        )
        if (
            checked["format"] != _version(screen, "source-screen-context")
            or checked["screen_sha256"] != screen.fingerprint()
            or checked["expected_runtime_sha256"] != runtime["sha256"]
            or controls(_object(checked["controls"]), strings=True) != pins
        ):
            raise ReleaseError("helper context changes its exact planned screen or controls")
        comparison = _object(checked["comparison_controls"], {"sources", "external"})
        members = _object(comparison["sources"])
        if len(members) > 1024 or len(_object(comparison["external"])) > 1024:
            raise ReleaseError("helper context exceeds its original path boundary")
        controls(_object(comparison["external"]), strings=True)
        _comparison_controls(checked, pins, screen)
        sources.append({name: reference(value) for name, value in members.items()})
    screen_before, screen_after = sources
    old_package = next(iter(screen_before.values()))[0].parent
    new_package = next(iter(screen_after.values()))[0].parent
    before = {}
    for role in _UNIFIED_ROLES_V1:
        path = remember(old_package.parent / role)
        if path not in recorded:
            raise ReleaseError("original source manifest lacks the frozen unified helper profile")
        before[role] = (path, recorded[path])
    if any(before.get(role) != ref for role, ref in screen_before.items()):
        raise ReleaseError("original screen helpers differ from the anchored source manifest")
    pairs = _object(relation["roles"])
    if len(pairs) != len(before) or set(pairs) != set(before):
        raise ReleaseError("helper relation omits or adds a closed source role")
    after = {}
    for name, value in pairs.items():
        pair = _object(value, {"before", "after"})
        after[name] = reference(pair["after"])
        if (
            reference(pair["before"]) != before[name]
            or after[name][0] != remember(new_package.parent / name)
            or supplied[1].get(after[name][0]) != after[name][1]
        ):
            raise ReleaseError("helper relation differs from its actual context roles")
    if any(after.get(role) != ref for role, ref in screen_after.items()):
        raise ReleaseError("new screen helpers differ from the complete source projection")
    for name in gateway.CORE:
        role = "buddha/" + ("__init__.py" if name == "buddha" else name.rsplit(".", 1)[1] + ".py")
        if before[role][1] != after[role][1]:
            raise ReleaseError("helper relation changes a core source role")

    protected = {reference(runtime)[0]: _digest(runtime["sha256"])}
    for role in _UNIFIED_OUTER_V1:
        path, pin = before[role]
        protected[path] = pin
    if before["agents/frozen_seed.py"][1] != after["agents/frozen_seed.py"][1]:
        raise ReleaseError("helper relation changes the frozen plain generator")
    if planned["lineage"] is not None:
        path, pin = reference(planned["lineage"])
        protected[path] = pin
    for kind in ("generation", "native"):
        section = _object(planned[kind])
        roots = _object(section["roots"], set(ROLES))
        selected = Selection.from_bytes(_json(section["selection"])).to_record()
        for component, component_files in _object(selected["components"]).items():
            root = remember(_path(roots[component]))
            for name, component_pin in _object(component_files).items():
                path, digest = remember(root / name), _digest(component_pin)
                if path in protected and protected[path] != digest:
                    raise ReleaseError("selected inputs have conflicting immutable roles")
                protected[path] = digest
    for pins in supplied:
        if any(path in pins and pins[path] != digest for path, digest in protected.items()):
            raise ReleaseError("helper controls change a selected immutable input")
    for path, pin in after.values():
        if path in supplied[0] and supplied[0][path] != pin:
            raise ReleaseError("helper replacement conflicts with an original input path")
    if (
        overlay in supplied[0]
        or overlay in protected
        or overlay in {path for path, _ in after.values()}
    ):
        raise ReleaseError("helper relation reference overlaps an original or source input")
    expected = dict(supplied[0])
    for path, _ in before.values():
        if path not in protected:
            del expected[path]
    expected.update(after.values())
    expected[overlay] = overlay_sha
    closures = (
        ("source_screen.py", _UNIFIED_HELPERS_V1),
        (
            "candidate_generation.py",
            {
                path.name
                for path in candidate_generation._sources(_version(screen, "candidate-generation"))
            },
        ),
        ("candidate_improvement.py", {path.name for path in candidate_improvement._sources()}),
    )
    for anchor, names in closures:
        prefixes = {
            path.parent
            for path in expected
            if path.name == anchor and all(path.parent / name in expected for name in names)
        }
        if not names <= _UNIFIED_HELPERS_V1 or prefixes != {new_package}:
            raise ReleaseError("helper projection retains ambiguous producer source roles")
    if len(expected) > 1024 or expected != supplied[1]:
        raise ReleaseError(
            "helper projection changes fixed inputs or retains ambiguous source roles"
        )
    return expected


def _snapshot(path: Path) -> tuple[dict[str, object], bytes]:
    _sidecars(path)
    raw = _read(path, MAX_LEDGER_BYTES)
    result = read_authority(raw)
    _sidecars(path)
    return result, raw


def _finish_snapshot(path: Path, raw: bytes, *, error: type[ReleaseError] = ReleaseError) -> None:
    _sidecars(path)
    if _read(path, len(raw)) != raw:
        raise error("funding changed while checking")
    _sidecars(path)


def _notice(prefix: str, message: str) -> None:
    print("[" + prefix + "] " + message, file=sys.stderr, flush=True)


def _emit(notice: Callable[[str], None], message: str) -> None:
    try:
        notice(message)
    except Exception:
        # Observer failures must not change execution or emit a background trace.
        return


@contextmanager
def _heartbeat(
    notice: Callable[[str], None],
    phase: list[str],
    authority: list[Path | None],
    seconds: float,
    *,
    thread_name: str = "launch-progress",
) -> Iterator[None]:
    stop = threading.Event()
    started = time.monotonic()

    def accounting() -> str:
        if authority[0] is None:
            return "recorded accounting unknown"
        try:
            funding, raw = _snapshot(authority[0])
            _finish_snapshot(authority[0], raw)
            config, totals = _object(funding["config"]), _object(funding["totals"])
            return (
                f"recorded attempts {totals['operation_count']}; "
                f"recorded cost ${cast(int, totals['spent_microusd']) / 1_000_000:.6f}; "
                f"held ${cast(int, totals['reserved_microusd']) / 1_000_000:.6f}; "
                f"cap ${cast(int, config['budget_microusd']) / 1_000_000:.6f}"
            )
        except Exception:
            return "recorded accounting unavailable"

    def tick() -> None:
        while not stop.wait(seconds):
            if phase[0] != "keys":
                _emit(
                    notice,
                    f"Phase: {phase[0]}; elapsed {int(time.monotonic() - started)}s; "
                    + accounting(),
                )

    worker = threading.Thread(target=tick, name=thread_name, daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=0.5)


def _receipt_path(path: Path, *, error: type[ReleaseError] = ReleaseError) -> Path:
    if not isinstance(path, Path):
        raise error("receipt needs an explicit new Path")
    result = _path(str(path.absolute()), error=error)
    _root(result.parent)
    if result.exists():
        raise error("receipt already exists; nothing overwritten")
    return result


def _receipt_roots(path: Path, expected_sha256: str) -> list[Path]:
    """Derive exclusions from trusted bytes before arming even a failure receipt.

    No funding/state/credential checks or writes. Only known pinned descriptor
    references are opened; other declared paths are exclusions, never reads.
    A wrong pin or malformed descriptor cannot authorize any receipt write.
    """
    references = {
        "buddha.source-launch.v1": ("proposal", "approval"),
        "buddha.policy-launch.v1": ("proposal", "approval", "execution"),
        "buddha.policy-handoff.v1": ("study", "baseline"),
        "buddha.policy-execution.v1": ("study", "baseline"),
        "buddha.improver-launch.v1": ("proposal", "approval"),
        "buddha.improver-handoff.v1": ("assessment",),
        "buddha.improver-assessment-trial.v4": (
            "development",
            "tasks",
            "custody",
            "analysis_plan",
            "improvement_rule",
        ),
    }
    path, expected_sha256 = _path(str(path.absolute())), _digest(expected_sha256)
    first = _load(pipeline._read(path, expected_sha256))
    if _text(first["format"]) not in {
        "buddha.source-launch.v1",
        "buddha.policy-launch.v1",
        "buddha.improver-launch.v1",
    }:
        raise ReleaseError("receipt exclusions require a known pinned launch")
    roots, seen = {path}, {path: expected_sha256}
    pending = [first]
    while pending:
        record = pending.pop()
        nodes: list[object] = [record]
        while nodes:
            value = nodes.pop()
            if type(value) is list:
                nodes.extend(value)
            elif type(value) is dict:
                item = _object(value)
                nodes.extend(item.values())
                for name in ("directory", "review", "authorization_path", "path"):
                    if name in item:
                        candidate = item[name]
                        if type(candidate) is str and Path(candidate).is_absolute():
                            roots.add(_path(candidate))
                for name in ("roots", "source_sha256"):
                    if name in item:
                        values = _object(item[name])
                        for candidate in values.values() if name == "roots" else values:
                            roots.add(_path(candidate))
        for name in references.get(cast(str, record.get("format")), ()):
            reference = _object(record[name], {"path", "sha256"})
            source, digest = _path(reference["path"]), _digest(reference["sha256"])
            roots.add(source)
            if source in seen:
                if seen[source] != digest:
                    raise ReleaseError("conflicting receipt exclusion references")
                continue
            if len(seen) >= 16:
                raise ReleaseError("receipt descriptor closure exceeds its boundary")
            seen[source] = digest
            pending.append(_load(pipeline._read(source, digest)))
    return sorted(roots)


def _model_specs(
    generation: dict[str, object],
    native: dict[str, object],
    template: dict[str, object] | None = None,
) -> dict[str, list[ModelSpec]]:
    selected = {
        name: gateway._profiles(
            Selection.from_bytes(_json(section["selection"])),
            {name: pipeline._absolute(path) for name, path in _object(section["roots"]).items()},
        )
        for name, section in (("generation", generation), ("native", native))
    }

    def choice(section: dict[str, object]) -> ModelSpec:
        role = _object(section["profile"])
        choices = _object(
            _object(selected["generation"][cast(str, role["capability"])])["profiles"]
        )
        return gateway._spec(_object(choices[cast(str, role["profile_id"])])["spec"])

    result = {"generation": [choice(generation)], "native": []}
    if template is not None:
        result["proposal"] = [choice(template)]
    for provider, models in _object(native["profiles"]).items():
        capability = next(
            key for key, value in gateway.CAPABILITIES.items() if value[0] == provider
        )
        choices = _object(_object(selected["native"][capability])["profiles"])
        for profile_id in _object(models).values():
            spec = gateway._spec(_object(choices[_text(profile_id)])["spec"])
            if spec not in result["native"]:
                result["native"].append(spec)
    return result
