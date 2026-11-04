"""Checked witness and remaining-development continuations; no operator CLI.

Original owners remain passive evidence. Only the cut's one absent witness may
acquire new ordinary owners, with actual installed helper pins and this external
descriptor. The original controller, scientific definitions and grants are not
rewritten. A passing check is not a paid-run handoff or account certification.
"""

import hashlib
import os
import re
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from buddha import gateway, improver_study, source_screen, source_search, trial_fence
from buddha import launch_common as common
from buddha import native_pipeline as pipeline
from buddha.authorization import Authorization
from buddha.doctor import _Busy, _Capture, _observation_policy, _Unsupported
from buddha.gateway_history import MAX_LEDGER_BYTES
from buddha.native_evidence import NativeEvidence
from buddha.releases import (
    MAX_JSON_BYTES,
    ReleaseError,
    Selection,
    _digest,
    _json,
    _load,
    _object,
    _path,
)
from buddha.search_evidence import MAX_FILE_BYTES
from buddha.unified_funding import _limits, reference_scope
from buddha.wire import _integer

_PHASES = ("search", "validation", "final", "shared_plain_references")
_REMAINING = ("search", "freeze", "final", "plain-regenerate", "plain-in-context", "comparison")
_TOTALS = ("spent_microusd", "reserved_microusd", "operation_count")
# Existing Gateway._input_records and active control checks cap component files
# at 256 MiB. JSON and ledgers retain their separate role-specific boundaries.
_MAX_COMPONENT_BYTES = 256 * 1024**2
_FIXED_SCIENCE = frozenset(
    "buddha/" + name + ".py"
    for name in (
        "improvement_rule",
        "improver_analysis",
        "validation_analysis",
        "noveltybench_results",
        "source_screen_results",
        "archive",
    )
)


class WitnessContinuationError(ReleaseError):
    """The exact original cut or the explicitly approved witness differs."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _field_limit(path: Path, databases: frozenset[Path], components: frozenset[Path]) -> int:
    if path in databases:
        return MAX_LEDGER_BYTES
    if path.suffix.lower() in {".json", ".jsonl"}:
        return MAX_JSON_BYTES
    return _MAX_COMPONENT_BYTES if path in components else MAX_FILE_BYTES


def _ref(value: object) -> tuple[Path, str]:
    row = _object(value, {"path", "sha256"})
    return common._path(row["path"]), _digest(row["sha256"])


def _pins(value: object) -> dict[Path, str]:
    record = _object(value)
    if not 1 <= len(record) <= 1024:
        raise WitnessContinuationError("continuation pins exceed their original boundary")
    result, spellings = {}, set()
    for name, digest in record.items():
        path = common._path(name)
        alias = str(path).casefold()
        if alias in spellings:
            raise WitnessContinuationError("continuation pins have aliases")
        spellings.add(alias)
        result[path] = _digest(digest)
    return result


def _context(
    screen: source_screen.SourceScreen, pins: Mapping[Path, str], roles: Mapping[str, Any]
) -> dict[str, Any]:
    record: dict[str, Any] = screen.to_record()
    runtime = common._path(record["generation"]["runtime"]["path"])
    members = {"buddha/" + p.name: roles["buddha/" + p.name] for p in source_screen._sources()}
    paths = {_ref(value)[0] for value in members.values()}
    excluded = paths | {runtime}
    if record["lineage"] is not None:
        excluded.add(_ref(record["lineage"])[0])
    return {
        "format": source_screen._version(screen, "source-screen-context"),
        "screen_sha256": screen.fingerprint(),
        "expected_runtime_sha256": record["generation"]["runtime"]["sha256"],
        "controls": {str(p): d for p, d in pins.items()},
        "comparison_controls": {
            "sources": members,
            "external": {str(p): d for p, d in pins.items() if p not in excluded},
        },
    }


@dataclass(frozen=True)
class CheckedWitnessContinuation:
    """Detached immutable metadata, bound to its checking process and thread."""

    path: Path
    sha256: str
    study: Path
    witness: Path
    _parent: Path
    runtime_sha256: str
    _before: tuple[tuple[Path, str], ...]
    _after: tuple[tuple[Path, str], ...]
    _screen_sha256: str
    _policy: bytes
    _summary: bytes
    _pid: int
    _thread: int

    def summary(self) -> dict[str, object]:
        return _load(self._summary)

    def _resolve(
        self,
        root: Path,
        directory: Path,
        screen: source_screen.SourceScreen,
        controls: Mapping[Path, str],
        parent: Path | None,
    ) -> dict[Path, str]:
        if self._pid != os.getpid() or self._thread != threading.get_ident() or root != self.study:
            raise WitnessContinuationError("continuation differs from its checked root or thread")
        if directory != self.witness:
            if dict(controls) != dict(self._before):
                raise WitnessContinuationError("continuation replaces original study controls")
            return dict(controls)
        if screen.fingerprint() != self._screen_sha256:
            raise WitnessContinuationError("continuation changes the original witness screen")
        if parent is not None:
            if parent != self._parent or dict(controls) != dict(self._after):
                raise WitnessContinuationError(
                    "continuation changes the original historical parent"
                )
            return dict(self._before)
        if dict(controls) != dict(self._before):
            raise WitnessContinuationError("continuation replaces original study controls")
        return dict(self._after)

    @contextmanager
    def _scope(self) -> Iterator[None]:
        if self._pid != os.getpid() or self._thread != threading.get_ident():
            raise WitnessContinuationError("continuation cannot move to another process or thread")
        with _observation_policy(_load(self._policy)), common._witness_continuation(self._resolve):
            yield


@dataclass(frozen=True)
class CheckedStudyContinuation(CheckedWitnessContinuation):
    """A separate counted-cell-cut scope; historical v1 stays witness-only."""

    _old_owners: frozenset[str]
    _cells: tuple[Path, ...]
    _screens: frozenset[str]
    _authorization: Path
    _profiles: tuple[str, str]

    def _check_thread(self, root: Path) -> None:
        if (
            self._pid != os.getpid()
            or self._thread != threading.get_ident()
            or str(root) != str(self.study)
        ):
            raise WitnessContinuationError("study continuation differs from its root or thread")

    def _owner_controls(self, owner: Path) -> dict[Path, str]:
        relative = owner.relative_to(self.study).as_posix()
        integer = r"(?:0|[1-9][0-9]*)"
        if str(owner) != str(self.study / relative) or not re.fullmatch(
            rf"(?:common/{integer}/{integer}/(?:screen/tasks/0/generation|witness/proposal)|"
            rf"cells/{integer}/{integer}/(?:0|1)/{integer}/"
            r"(?:proposal|screen/tasks/0/generation|witness/proposal))/owners/0",
            relative,
        ):
            raise WitnessContinuationError("continuation owner has an undeclared control role")
        if str(owner) in self._old_owners:
            return dict(self._before)
        if owner == self.witness / "proposal/owners/0" or any(
            owner.is_relative_to(cell) for cell in self._cells
        ):
            return dict(self._after)
        raise WitnessContinuationError("continuation cannot replace or invent an earlier owner")

    def _controls(self, root: Path, owner: Path, controls: Mapping[Path, str]) -> dict[Path, str]:
        self._check_thread(root)
        if dict(controls) != dict(self._before):
            raise WitnessContinuationError("continuation replaces original study controls")
        return self._owner_controls(owner)

    def _resolve(
        self,
        root: Path,
        directory: Path,
        screen: source_screen.SourceScreen,
        controls: Mapping[Path, str],
        parent: Path | None,
    ) -> dict[Path, str]:
        self._check_thread(root)
        if screen.fingerprint() not in self._screens:
            raise WitnessContinuationError("continuation changes an original witness base")
        expected = self._owner_controls(directory / "proposal/owners/0")
        if parent is not None:
            if dict(controls) != expected:
                raise WitnessContinuationError("witness differs from its actual helper profile")
            return self._owner_controls(parent / "tasks/0/generation/owners/0")
        if dict(controls) != dict(self._before):
            raise WitnessContinuationError("continuation replaces original study controls")
        return expected

    def _relation(self) -> dict[str, object]:
        return {
            "format": "buddha.host-control-relation.v1",
            "continuation": {"path": str(self.path), "sha256": self.sha256},
            "before_controls_sha256": self._profiles[0],
            "after_controls_sha256": self._profiles[1],
        }

    @contextmanager
    def _scope(self) -> Iterator[None]:
        self._check_thread(self.study)
        with (
            _observation_policy(_load(self._policy)),
            common._study_continuation(self._controls),
            common._witness_continuation(self._resolve),
            source_screen._screen_control_profiles(
                self.study,
                self._authorization,
                before=self._profiles[0],
                after=self._profiles[1],
                continuation={"path": str(self.path), "sha256": self.sha256},
            ),
        ):
            source_screen._checked_control_marker(self._relation())
            yield


@dataclass(frozen=True)
class CheckedTrialContinuation(CheckedStudyContinuation):
    """Original trial and plan identities with separately checked execution pins."""

    _trial: Path
    _launch: tuple[Path, str]
    _roles: tuple[tuple[str, Path, str, Path, str], ...]

    def _historical_sources(self, current: Mapping[str, str], *, relative: bool) -> dict[str, str]:
        self._check_thread(self.study)
        roles = {
            name if relative else str(after_path): (before_path, before_sha, after_sha)
            for name, before_path, before_sha, after_path, after_sha in self._roles
        }
        result: dict[str, str] = {}
        for name, digest in current.items():
            if name not in roles or _digest(digest) != roles[name][2]:
                raise WitnessContinuationError(
                    "phase source differs from its exact checked installed role"
                )
            before_path, before_sha, _ = roles[name]
            original = name if relative else str(before_path)
            if original in result:
                raise WitnessContinuationError("phase sources repeat a historical role")
            result[original] = before_sha
        return result

    def _phase_controls(
        self, trial: Path, phase: str, controls: Mapping[Path, str]
    ) -> dict[Path, str]:
        self._check_thread(self.study)
        if str(trial) != str(self._trial) or phase not in {"final", "plain"}:
            raise WitnessContinuationError("phase controls change the original trial or role")
        before, after = dict(self._before), dict(self._after)
        result = dict(controls)
        for path in before.keys() - after.keys():
            if path in result and result.pop(path) != before[path]:
                raise WitnessContinuationError("phase union changes a historical helper")
        for path, digest in after.items():
            if path in result and result[path] != digest:
                raise WitnessContinuationError("phase union changes a checked execution input")
            result[path] = digest
        if len(result) > 1024:
            raise WitnessContinuationError("phase union exceeds its original input boundary")
        return result

    @contextmanager
    def _scope(self, *, before_start: Callable[[Path], None] | None = None) -> Iterator[None]:
        with (
            super()._scope(),
            common._phase_continuation(
                self._historical_sources, self._phase_controls, before_start=before_start
            ),
        ):
            yield


@dataclass(frozen=True)
class _CheckedState:
    checked: CheckedWitnessContinuation
    trial: Path
    search_grant: Path
    action: dict[str, Any]
    files: tuple[tuple[Path, int, str], ...]
    databases: frozenset[Path]
    components: frozenset[Path]
    entries: frozenset[str]
    directories: frozenset[str]
    grants: tuple[tuple[Path, str], ...]
    witness_result: bytes | None = None
    state: dict[str, Any] | None = None
    study_result: bytes | None = None

    def after_locks(
        self,
        *,
        owned_locks: frozenset[str] = frozenset(
            {".trial-running.lock", "search/study/running.lock"}
        ),
    ) -> None:
        """Fresh exact bytes/funding after normal leases, without a second replay."""
        capture = _Capture(self.trial)
        if set(capture.entries) != self.entries | owned_locks:
            raise WitnessContinuationError("original tree changed before the witness lease")
        if (
            frozenset(name for name in capture.entries if (self.trial / name).is_dir())
            != self.directories
        ):
            raise WitnessContinuationError(
                "original tree entry kinds changed before the witness lease"
            )
        for path, size, digest in self.files:
            maximum = _field_limit(path, self.databases, self.components)
            _integer(size, 0, maximum)
            raw = capture.database(path) if path in self.databases else capture.read(path, maximum)
            if len(raw) != size or _sha(raw) != digest:
                raise WitnessContinuationError("checked original evidence changed before dispatch")
        for path, digest in self.grants:
            _, raw = common._snapshot(path)
            if _sha(raw) != digest:
                raise WitnessContinuationError(
                    "checked grant identity or joins changed before dispatch"
                )
        capture.finish()


def _check(
    path: Path,
    expected: str,
    *,
    study_continuation: bool = False,
    trial_continuation: bool = False,
) -> _CheckedState:
    study_continuation = study_continuation or trial_continuation
    path, expected = common._path(str(path.absolute())), _digest(expected)
    raw = pipeline._read(path, expected)
    record: dict[str, Any] = _object(
        _load(raw),
        {
            "format",
            "original_launch",
            "cut",
            "helper_relation",
            "driver_source",
            "grants",
            "observation_policy",
            "remaining_phases",
        },
    )
    wanted = (
        "buddha.trial-continuation.v1"
        if trial_continuation
        else (
            "buddha.study-continuation.v1"
            if study_continuation
            else "buddha.witness-continuation.v1"
        )
    )
    remaining = (
        ("search", "freeze", "publication")
        if study_continuation and not trial_continuation
        else _REMAINING
    )
    if record["format"] != wanted or record["remaining_phases"] != list(remaining):
        raise WitnessContinuationError("unsupported bounded witness continuation")
    # Validate policy before constructing any capture in the actual reader thread.
    with _observation_policy(record["observation_policy"]):
        cut_path, cut_sha = _ref(record["cut"])
        cut_raw = pipeline._read(cut_path, cut_sha)
        cut: dict[str, Any] = _object(
            _load(cut_raw),
            {
                "format",
                "trial",
                "study",
                "witness",
                "position",
                "parent",
                "attempted",
                "decisions",
                "owners",
                "files",
                "entries",
                "totals",
            },
        )
        if cut["format"] != "buddha.witness-continuation-cut.v1":
            raise WitnessContinuationError("unsupported original witness cut")
        trial, study, witness = (common._path(cut[k]) for k in ("trial", "study", "witness"))
        if str(study) != str(trial / "search/study") or not witness.is_relative_to(study):
            raise WitnessContinuationError("cut changes its original trial or study root")
        capture = _Capture(trial)
        seen: dict[str, str] = {}

        def bound(reference: object) -> tuple[Path, str, bytes]:
            source, digest = _ref(reference)
            alias = str(source).casefold()
            if alias in seen and seen[alias] != str(source):
                raise WitnessContinuationError("continuation references have conflicting spellings")
            seen[alias] = str(source)
            value = capture.read(source, MAX_JSON_BYTES)
            if _sha(value) != digest:
                raise WitnessContinuationError("continuation reference bytes changed")
            return source, digest, value

        bound({"path": str(path), "sha256": expected})
        bound(record["cut"])
        outer_path, outer_sha, outer_raw = bound(record["original_launch"])
        outer = _object(
            _load(outer_raw),
            {
                "format",
                "primary_launch",
                "comparison_plan",
                "reference_grant",
                "total_limits",
                "directory",
                "source_sha256",
            },
        )
        if outer["format"] != "buddha.unified-launch.v1":
            raise WitnessContinuationError("continuation needs its original combined launch")
        primary_path, primary_sha, primary_raw = bound(outer["primary_launch"])
        primary = _object(
            _load(primary_raw),
            {
                "format",
                "proposal",
                "approval",
                "directory",
                "review",
                "source_sha256",
                "timeout_seconds",
            },
        )
        if primary["format"] != "buddha.improver-launch.v1" or primary["directory"] != str(trial):
            raise WitnessContinuationError("continuation replaces its original primary launch")
        handoff_path, handoff_sha, handoff_raw = bound(primary["proposal"])
        handoff = _object(
            _load(handoff_raw),
            {"format", "assessment", "expected_runtime_sha256", "directory", "source_sha256"},
        )
        if handoff["format"] != "buddha.improver-handoff.v1" or handoff["directory"] != str(trial):
            raise WitnessContinuationError("continuation replaces its original handoff")
        definition_path, definition_sha, definition_raw = bound(handoff["assessment"])
        if pipeline._read(trial / "definition.json", definition_sha) != definition_raw:
            raise WitnessContinuationError(
                "continuation changes the original scientific definition"
            )
        definition: dict[str, Any] = _object(
            _load(definition_raw),
            {
                "format",
                "experiment_id",
                "development",
                "tasks",
                "custody",
                "final_ids",
                "sealed_repetitions",
                "generation",
                "native",
                "stages",
                "analysis_plan",
                "improvement_rule",
                "selection_policy",
                "phase_limits",
                "consumer_sources",
            },
        )
        if definition["format"] != "buddha.improver-assessment-trial.v4":
            raise WitnessContinuationError(
                "witness continuation supports original assessment v4 only"
            )
        development_path, development_sha, development_raw = bound(definition["development"])
        runtime = _digest(handoff["expected_runtime_sha256"])
        development, screens = improver_study._declaration(_load(development_raw), runtime)
        if development["format"] != improver_study._CAPACITY_FORMAT:
            raise WitnessContinuationError(
                "witness continuation supports original development v4 only"
            )
        plan_path, plan_sha, plan_raw = bound(outer["comparison_plan"])
        plan = _object(
            _load(plan_raw),
            {"format", "method", "trial", "definition_sha256", "references", "consumer_sources"},
        )
        if (
            plan["format"] != "buddha.plain-comparison-plan.v1"
            or plan["method"] != "all_conditions_then_equal_prompts_descriptive.v1"
            or plan["trial"] != str(trial)
            or plan["definition_sha256"] != definition_sha
        ):
            raise WitnessContinuationError("continuation changes its original plain plan")
        approval_path, approval_sha, approval_raw = bound(primary["approval"])
        approval = _object(
            _load(approval_raw),
            {
                "format",
                "proposal_sha256",
                "definition_sha256",
                "directory",
                "review",
                "account_scope",
                "authorizations",
            },
        )
        if (
            approval["format"] != "buddha.improver-approval.v1"
            or approval["proposal_sha256"] != handoff_sha
            or approval["definition_sha256"] != definition_sha
            or approval["directory"] != str(trial)
            or approval["review"] != primary["review"]
        ):
            raise WitnessContinuationError("continuation changes its original approval")
        review_path = common._path(primary["review"])
        review_raw = capture.read(review_path, MAX_JSON_BYTES)
        review = gateway._review(_load(review_raw))
        if (
            review.get("format") != "buddha.account-review.v2"
            or review["credential_context"] != primary_sha
            or review["account_scope"] != approval["account_scope"]
        ):
            raise WitnessContinuationError("continuation replaces its original key-review context")
        grants: dict[str, Any] = _object(record["grants"], set(_PHASES))
        originals = _object(approval["authorizations"], set(_PHASES[:3])) | {
            "shared_plain_references": outer["reference_grant"]
        }
        if _json(grants) != _json(originals):
            raise WitnessContinuationError("continuation changes its original grant declarations")
        snapshots, paths = {}, {}
        funding: dict[str, Any] = {}
        for phase in _PHASES:
            row = _object(
                grants[phase],
                {"path", "id", "terms_sha256", "scope", "budget_microusd", "max_calls"},
            )
            authority = common._path(row["path"])
            observed_value, snapshot = common._snapshot(authority)
            observed: dict[str, Any] = observed_value
            config = _object(observed["config"])
            if (
                any(
                    config[k] != row[k]
                    for k in ("terms_sha256", "scope", "budget_microusd", "max_calls")
                )
                or config["authorization_id"] != row["id"]
            ):
                raise WitnessContinuationError("continuation changes original grant terms")
            caps = _limits({k: row[k] for k in ("budget_microusd", "max_calls")})
            if phase != "shared_plain_references":
                expected_scope = trial_fence._scope_text(
                    trial_fence._TrialScope(trial, definition_sha, phase)
                )
                if row["scope"] != expected_scope or caps != definition["phase_limits"][phase]:
                    raise WitnessContinuationError(
                        "continuation grant differs from the original phase"
                    )
            elif row["scope"] != reference_scope(plan_sha):
                raise WitnessContinuationError(
                    "continuation changes the plain grant's plan identity"
                )
            if any(r["status"] in {"unknown", "dispatched"} for r in observed["auth_operations"]):
                raise WitnessContinuationError(
                    "uncertain original or continuation liability blocks work"
                )
            if (phase == "validation" or phase != "search" and not trial_continuation) and any(
                observed[k]
                for k in ("auth_runs", "auth_operations", "auth_acceptances", "auth_deactivations")
            ):
                raise WitnessContinuationError(
                    "later-phase work is outside this witness continuation"
                )
            snapshots[authority], funding[phase], paths[phase] = snapshot, observed, authority
        if len(snapshots) != 4 or len({r["id"] for r in grants.values()}) != 4:
            raise WitnessContinuationError("continuation needs four distinct original grants")
        limits = _limits(outer["total_limits"])
        if limits != {k: sum(_integer(r[k]) for r in grants.values()) for k in limits}:
            raise WitnessContinuationError("continuation allocations change the original total")
        context_path = study / "context.json"
        study_context_raw = capture.read(context_path, MAX_JSON_BYTES)
        study_context = _object(
            _load(study_context_raw),
            {
                "format",
                "declaration",
                "declaration_sha256",
                "expected_runtime_sha256",
                "authorization",
                "review",
                "controls",
            },
        )
        if (
            study_context["format"] != improver_study._CONTEXT
            or study_context["declaration"] != str(development_path)
            or study_context["declaration_sha256"] != development_sha
            or study_context["expected_runtime_sha256"] != runtime
            or study_context["authorization"] != str(paths["search"])
            or study_context["review"] != review
        ):
            raise WitnessContinuationError("continuation changes its original study context")
        before = _pins(study_context["controls"]) | {context_path: _sha(study_context_raw)}
        original_bindings = {
            outer_path: outer_sha,
            primary_path: primary_sha,
            handoff_path: handoff_sha,
            definition_path: definition_sha,
            approval_path: approval_sha,
            plan_path: plan_sha,
            review_path: _sha(review_raw),
        }
        for p, d in original_bindings.items():
            if p != outer_path and before.get(p) != d:
                raise WitnessContinuationError("original first owner lacks an outer control")
        for pins in (
            outer["source_sha256"],
            primary["source_sha256"],
            handoff["source_sha256"],
            plan["consumer_sources"],
        ):
            if any(before.get(p) != d for p, d in _pins(pins).items()):
                raise WitnessContinuationError("original helper approval is not first-owner bound")
        relation_path, relation_sha, relation_raw = bound(record["helper_relation"])
        relation = _object(_load(relation_raw), {"format", "source_manifest", "roles"})
        if relation["source_manifest"] != primary["proposal"]:
            raise WitnessContinuationError("helper relation changes its original source manifest")
        pairs = _object(relation["roles"], set(common._UNIFIED_ROLES_V1))
        old_roles = {k: _object(v, {"before", "after"})["before"] for k, v in pairs.items()}
        new_roles = {k: _object(v, {"before", "after"})["after"] for k, v in pairs.items()}
        package = Path(__file__).absolute().parent.parent
        selected_paths: set[Path] = set()
        selected_roots: set[Path] = set()
        actors = [s.to_record()["generation"] for s in screens] + list(development["improvers"])
        for section in [*actors, *(s.to_record()["native"] for s in screens)]:
            section = _object(section)
            selection: dict[str, Any] = Selection.from_bytes(
                _json(section["selection"])
            ).to_record()
            for role, inventory in selection["components"].items():
                root = common._path(_object(section["roots"])[role])
                selected_roots.add(root)
                for name, digest in inventory.items():
                    source = root / _path(name)
                    selected_paths.add(source)
                    if (
                        _sha(
                            capture.read(
                                source, _field_limit(source, frozenset(), frozenset({source}))
                            )
                        )
                        != digest
                    ):
                        raise WitnessContinuationError("an original selected component changed")
        helper_roots = {
            _ref(v)[0].parent.parent for k, v in old_roles.items() if k.startswith("buddha/")
        } | {package}
        external = (path, cut_path, relation_path, _ref(record["driver_source"])[0])
        if len({str(p).casefold() for p in external}) != 4 or any(
            p.is_relative_to(trial)
            or trial.is_relative_to(p)
            or any(p.is_relative_to(r) or r.is_relative_to(p) for r in selected_roots)
            or p in paths.values()
            for p in external
        ):
            raise WitnessContinuationError(
                "continuation references are not distinct external inputs"
            )
        if any(
            r.is_relative_to(h) or h.is_relative_to(r) for r in selected_roots for h in helper_roots
        ):
            raise WitnessContinuationError("selected actor/component roots overlap host helpers")
        after = dict(before)
        for role, value in old_roles.items():
            source, _ = _ref(value)
            if role not in common._UNIFIED_OUTER_V1 and source not in selected_paths:
                after.pop(source, None)
        for role, value in new_roles.items():
            source, digest = _ref(value)
            if (
                str(source) != str(package / role)
                or _sha(
                    capture.read(source, _field_limit(source, frozenset(), frozenset({source})))
                )
                != digest
            ):
                raise WitnessContinuationError(
                    "continuation lacks its actual complete installed helper closure"
                )
            after[source] = digest
        after[relation_path] = relation_sha
        position = _object(cut["position"], {"start", "repetition", "arm", "slot", "stage"})
        start = _integer(position["start"], 0, len(screens) - 1)
        repetition = _integer(position["repetition"], 0, development["repetitions"] - 1)
        if position["arm"] is None and position["slot"] is None:
            scheduled = study / "common" / str(start) / str(repetition) / "witness"
        else:
            arm = _integer(position["arm"], 0, 1)
            slot = _integer(position["slot"], 0, development["descendant_opportunities"] - 1)
            scheduled = (
                study / "cells" / str(start) / str(repetition) / str(arm) / str(slot) / "witness"
            )
        if str(witness) != str(scheduled):
            raise WitnessContinuationError(
                "cut witness path differs from its literal scheduled coordinate"
            )
        base = screens[start]
        projected = common._helper_role_relation(
            relation_raw,
            original_source_manifest=handoff_raw,
            expected_overlay=cast(Mapping[str, str], record["helper_relation"]),
            screen=base,
            before_context=_context(base, before, old_roles),
            before_controls=before,
            after_context=_context(base, after, new_roles),
            after_controls=after,
        )
        driver_path, driver_sha, _ = bound(record["driver_source"])
        if str(driver_path) != str(Path(__file__).absolute()):
            raise WitnessContinuationError("continuation driver is not its actual installed source")
        for source, digest in ((path, expected), (driver_path, driver_sha)):
            if source in projected or source.is_relative_to(trial) or trial.is_relative_to(source):
                raise WitnessContinuationError(
                    "continuation outer/driver reference overlaps protected inputs"
                )
            projected[source] = digest
        if trial_continuation:
            if cut_path in projected:
                raise WitnessContinuationError("continuation cut overlaps protected inputs")
            projected[cut_path] = cut_sha
            for name in sorted(_FIXED_SCIENCE):
                if _ref(old_roles[name])[1] != _ref(new_roles[name])[1]:
                    raise WitnessContinuationError(
                        "continuation changes a fixed numerical or selection module"
                    )
        if len(projected) > 1024 or len({str(p).casefold() for p in projected}) != len(projected):
            raise WitnessContinuationError(
                "continuation effective inputs exceed their original boundary"
            )
        parent = common._path(
            _object(cut["parent"], {"directory", "authorization", "report_sha256"})["directory"]
        )
        checked: CheckedWitnessContinuation = CheckedWitnessContinuation(
            path,
            expected,
            study,
            witness,
            parent,
            runtime,
            tuple(before.items()),
            tuple(projected.items()),
            base.fingerprint(),
            _json(record["observation_policy"]),
            b"{}",
            os.getpid(),
            threading.get_ident(),
        )
        component_paths = selected_paths | {
            _ref(v)[0] for v in (*old_roles.values(), *new_roles.values())
        }
        if study_continuation:
            if position["arm"] is None or position["slot"] is None:
                raise WitnessContinuationError("study continuation needs a counted-cell cut")
            owners = cut["owners"]
            if type(owners) is not list or not 1 <= len(owners) <= 4096:
                raise WitnessContinuationError("original owner cut exceeds its finite boundary")
            old_paths = []
            for value in owners:
                row = _object(
                    value,
                    {
                        "directory",
                        "run_id",
                        "manifest_sha256",
                        "manifest_raw_sha256",
                        "ledger_sha256",
                    },
                )
                owner_path = common._path(row["directory"])
                if not owner_path.is_relative_to(study):
                    raise WitnessContinuationError("original owner is outside the study")
                old_paths.append(owner_path)
                for filename, key in (
                    ("manifest.json", "manifest_raw_sha256"),
                    ("operations.sqlite3", "ledger_sha256"),
                ):
                    if _object(_object(cut["files"]).get(str(owner_path / filename))).get(
                        "sha256"
                    ) != _digest(row[key]):
                        raise WitnessContinuationError("cut omits an original owner raw anchor")
            if len({str(p).casefold() for p in old_paths}) != len(old_paths):
                raise WitnessContinuationError("original owner cut repeats an alias")
            early_files = _object(cut["files"])
            if not 1 <= len(early_files) <= 65_536:
                raise WitnessContinuationError("original file cut exceeds its finite boundary")
            old_databases = frozenset(p / "operations.sqlite3" for p in old_paths)
            spellings = set()
            for name, value in early_files.items():
                source = common._path(name)
                row = _object(value, {"bytes", "sha256"})
                maximum = _field_limit(source, old_databases, frozenset(component_paths))
                size = _integer(row["bytes"], 0, maximum)
                alias = str(source).casefold()
                if alias in spellings or source in snapshots or source.is_relative_to(witness):
                    raise WitnessContinuationError("original cut aliases mutable or future data")
                spellings.add(alias)
                data = (
                    capture.database(source)
                    if source in old_databases
                    else capture.read(source, maximum)
                )
                if len(data) != size or _sha(data) != _digest(row["sha256"]):
                    raise WitnessContinuationError("an immutable original cut file changed")
            anchor_reader = NativeEvidence(
                study, paths["search"], error_type=WitnessContinuationError
            )
            anchor = anchor_reader.owner(improver_study._first(study))
            if (
                anchor.manifest["core"] != gateway._core_sources()
                or anchor.manifest["runtime"] != gateway._runtime()
            ):
                raise WitnessContinuationError("continuation changes original CORE or host runtime")
            profiles = tuple(
                pipeline._sha(
                    {
                        "files": source_screen._comparison_controls(
                            _context(base, pins, roles),
                            dict(pins),
                            base,
                            core=anchor.manifest["core"],
                        ),
                        "core": anchor.manifest["core"],
                        "runtime": anchor.manifest["runtime"],
                    }
                )
                for pins, roles in ((before, old_roles), (projected, new_roles))
            )
            anchor_reader.finish()
            capture.adopt(anchor_reader.capture)
            capture.finish()
            coordinates = list(improver_study._coordinates(development))
            coordinate = cast(
                tuple[int, int, int, int],
                tuple(position[k] for k in ("start", "repetition", "arm", "slot")),
            )
            following = coordinates[coordinates.index(coordinate) + 1 :]
            checked = CheckedStudyContinuation(
                **vars(checked),
                _old_owners=frozenset(str(p) for p in old_paths),
                _cells=tuple(improver_study._location(study, c) for c in following),
                _screens=frozenset(s.fingerprint() for s in screens),
                _authorization=paths["search"],
                _profiles=(profiles[0], profiles[1]),
            )
            if trial_continuation:
                checked = CheckedTrialContinuation(
                    **vars(checked),
                    _trial=trial,
                    _launch=(outer_path, outer_sha),
                    _roles=tuple(
                        (name, *_ref(old_roles[name]), *_ref(new_roles[name]))
                        for name in sorted(old_roles)
                    ),
                )
        with checked._scope():
            reader, state = improver_study._restore(study, paths["search"])
        if (
            state["record"] != development
            or state["review"] != review
            or state["controls"] != before
        ):
            raise WitnessContinuationError("continuation replaces the original study treatment")
        if (
            state["attempted"] < _integer(cut["attempted"])
            or len(state["decisions"]) < _integer(cut["decisions"])
            or not study_continuation
            and (
                state["attempted"] != cut["attempted"]
                or len(state["decisions"]) != cut["decisions"]
            )
        ):
            raise WitnessContinuationError("continuation advances beyond its one original witness")
        owners = cut["owners"]
        if type(owners) is not list or not 1 <= len(owners) <= 4096:
            raise WitnessContinuationError("original owner cut exceeds its finite boundary")
        known = set()
        raw_manifests = {}
        inactive = {r["run_id"] for r in funding["search"]["auth_deactivations"]}
        totals = dict.fromkeys(_TOTALS, 0)
        for value in owners:
            row = _object(
                value,
                {"directory", "run_id", "manifest_sha256", "manifest_raw_sha256", "ledger_sha256"},
            )
            owner_path = common._path(row["directory"])
            owner = reader.owner(owner_path)
            if (
                owner_path in known
                or str(owner_path) != str(owner.directory)
                or owner.run_id != row["run_id"]
                or owner.manifest_sha256 != _digest(row["manifest_sha256"])
                or owner.ledger_sha256 != _digest(row["ledger_sha256"])
                or owner.run_id not in inactive
            ):
                raise WitnessContinuationError(
                    "an original cut owner is changed, active or repeated"
                )
            known.add(owner_path)
            raw_manifests[owner_path] = _digest(row["manifest_raw_sha256"])
            amounts = owner.accounting()
            for key in totals:
                totals[key] += _integer(amounts[key])
        if totals != _object(cut["totals"], set(_TOTALS)) or totals["reserved_microusd"]:
            raise WitnessContinuationError("original cut accounting is incomplete or held")
        allowed = {witness / role / "owners/0" for role in ("proposal", "generation")}
        if not known <= state["owner_paths"] or (
            not study_continuation and not state["owner_paths"] - known <= allowed
        ):
            raise WitnessContinuationError("continuation has an unscheduled or replaced owner")
        if study_continuation and {
            str(row["directory"]) for row in funding["search"]["auth_runs"]
        } != {str(p) for p in state["owner_paths"]}:
            raise WitnessContinuationError("development grant contains work outside its study")
        files: dict[str, Any] = _object(cut["files"])
        if not 1 <= len(files) <= 65_536:
            raise WitnessContinuationError("original file cut exceeds its finite boundary")
        names = set()
        for name, value in files.items():
            source = common._path(name)
            alias = str(source).casefold()
            row = _object(value, {"bytes", "sha256"})
            maximum = _field_limit(
                source, frozenset(reader.capture.databases), frozenset(component_paths)
            )
            size = _integer(row["bytes"], 0, maximum)
            if alias in names or source in snapshots or source.is_relative_to(witness):
                raise WitnessContinuationError(
                    "original file cut has aliases, mutable funding or future data"
                )
            names.add(alias)
            data = (
                reader.capture.database(source)
                if source in reader.capture.databases
                else reader.capture.read(source, maximum)
            )
            if len(data) != size or _sha(data) != _digest(row["sha256"]):
                raise WitnessContinuationError("an immutable original cut file changed")
        entries = cut["entries"]
        if (
            type(entries) is not list
            or not 1 <= len(entries) <= 100_000
            or len(set(entries)) != len(entries)
        ):
            raise WitnessContinuationError("original tree cut has invalid entries")
        old_entries = {str(_path(name)) for name in entries}
        if old_entries != set(entries) or not old_entries <= reader.capture.entries.keys():
            raise WitnessContinuationError("an original cut entry disappeared")
        required_files = set(before) | {
            study / _path(name) for name in old_entries if (study / _path(name)).is_file()
        }
        if not {str(p) for p in required_files} <= files.keys():
            raise WitnessContinuationError("cut omits an original file or original control")
        prefix = witness.relative_to(study).as_posix()
        roots = [prefix]
        new_files: set[str] = set()
        if isinstance(checked, CheckedStudyContinuation):
            roots += [p.relative_to(study).as_posix() for p in checked._cells]
            roots += ["freeze", "observations"]
            new_files = {
                "report.json",
                str(Path(prefix).parent / "decision.json").replace("\\", "/"),
            }
        ancestors = {
            parent.as_posix()
            for root in roots
            for parent in Path(root).parents
            if parent.as_posix() != "."
        }
        if any(
            name not in new_files
            and not any(name == root or name.startswith(root + "/") for root in roots)
            and not (study_continuation and name in ancestors and (study / name).is_dir())
            for name in reader.capture.entries.keys() - old_entries
        ):
            raise WitnessContinuationError("new work appears outside the one declared witness")
        for owner_path in known:
            for name, digest in (
                ("manifest.json", raw_manifests[owner_path]),
                ("operations.sqlite3", reader.owner(owner_path).ledger_sha256),
            ):
                if files.get(str(owner_path / name), {}).get("sha256") != digest:
                    raise WitnessContinuationError("cut omits an original owner raw anchor")
        with checked._scope():
            treatment, progress = improver_study._witness(
                reader, state, cut["parent"], witness, base
            )
        action = state["action"]
        if position["stage"] not in {"common_witness_feedback", "witness_feedback"}:
            raise WitnessContinuationError("cut is not an absent witness preparation boundary")
        if progress["result"] is None and (
            action["kind"] != "witness"
            or action["directory"] != witness
            or any(
                action["position"][key] != position[key]
                for key in ("start", "repetition", "arm", "slot")
            )
            or _json(action["treatment"].to_record()["parent"]) != _json(cut["parent"])
        ):
            raise WitnessContinuationError("cut is not the original next scheduled witness")
        study_result = None
        pools = []
        if isinstance(checked, CheckedStudyContinuation):
            with checked._scope():
                if (study / "report.json").is_file():
                    study_result = improver_study._complete_report(
                        reader, state, _sha(reader.raw(study / "report.json"))
                    )
            for key, decisions in state["cell_decisions"].items():
                pool = []
                for decision in decisions:
                    if decision["status"] == "admitted":
                        reference = decision["screen"]
                        report = reader.record(
                            common._path(reference["directory"]) / "report.json",
                            reference["report_sha256"],
                        )
                        pool.append(
                            {
                                "reference": reference,
                                "candidate_id": decision["candidate_id"],
                                "controls_sha256": _digest(report["controls_sha256"]),
                            }
                        )
                pools.append(
                    dict(zip(("start", "repetition", "arm"), key, strict=True)) | {"screens": pool}
                )
        trial_checked = None
        if isinstance(checked, CheckedTrialContinuation):
            from buddha import unified_launch

            with checked._scope():
                trial_checked = unified_launch.check_launch(outer_path, expected_sha256=outer_sha)
        reader.finish()
        for authority, snapshot in snapshots.items():
            common._finish_snapshot(authority, snapshot, error=WitnessContinuationError)
        capture.finish()
        summary = {
            "format": "buddha.witness-continuation-check.v1",
            "status": "checked",
            "study": str(study),
            "witness": str(witness),
            "old_owner_count": len(known),
            "all_old_owners_inactive": True,
            "old_totals": totals,
            "new_owner_count": len(state["owner_paths"] - known),
            "effective_control_count": len(projected),
            "continuation_sha256": expected,
            "witness_complete": progress["result"] is not None,
            "witness_status": None if progress["result"] is None else progress["result"]["status"],
            "scope": "one_witness_only_not_operator_ready",
        }
        if isinstance(checked, CheckedStudyContinuation):
            summary.update(
                format="buddha.study-continuation-check.v1",
                scope="remaining_development_only_not_operator_ready",
                continuation={"path": str(path), "sha256": expected},
                host_control_relation=checked._relation(),
                c_only_pools=pools,
                coverage=state["coverage"],
                study_complete=study_result is not None,
            )
        if trial_checked is not None:
            summary.update(
                format="buddha.trial-continuation-check.v1",
                scope="original_development_final_plain_comparison",
                phase=trial_checked["phase"],
                stop_code=trial_checked["stop_code"],
                original_launch={"path": str(outer_path), "sha256": outer_sha},
                original_plain_plan={"path": str(plan_path), "sha256": plan_sha},
                ready_for_comparison=trial_checked["phase"] == "comparison"
                and trial_checked["stop_code"] is None,
            )
        complete = replace(checked, _summary=_json(summary))
        directories = frozenset(name for name in capture.entries if (trial / name).is_dir())
        fingerprints = capture.fingerprints() | reader.fingerprints()
        grant_paths = set(snapshots)
        return _CheckedState(
            complete,
            trial,
            paths["search"],
            state["action"],
            tuple(
                (Path(p), Path(p).stat().st_size, d)
                for p, d in fingerprints.items()
                if Path(p) not in grant_paths
            ),
            frozenset(capture.databases | reader.capture.databases) - grant_paths,
            frozenset(component_paths),
            frozenset(capture.entries),
            directories,
            tuple((p, _sha(b)) for p, b in snapshots.items()),
            None if progress["result"] is None else _json(progress["result"]),
            state if study_continuation else None,
            None if study_result is None else _json(study_result),
        )


def _checked_state(
    path: Path,
    expected_sha256: str,
    *,
    study_continuation: bool = False,
    trial_continuation: bool = False,
) -> _CheckedState:
    if not isinstance(path, Path):
        raise WitnessContinuationError("continuation requires an explicit external Path")
    try:
        if trial_continuation:
            return _check(path, expected_sha256, trial_continuation=True)
        return (
            _check(path, expected_sha256, study_continuation=True)
            if study_continuation
            else _check(path, expected_sha256)
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        RecursionError,
        OverflowError,
        _Busy,
        _Unsupported,
    ):
        raise WitnessContinuationError(
            "witness continuation checks failed; original evidence retained"
        ) from None


def check_witness_continuation(path: Path, *, expected_sha256: str) -> CheckedWitnessContinuation:
    """Check exact original evidence without keys, writes, SQL on disk or workers."""
    return _checked_state(path, expected_sha256).checked


def check_study_continuation(path: Path, *, expected_sha256: str) -> CheckedStudyContinuation:
    """Check a separate development descriptor, with no keys, writes or workers."""
    checked = _checked_state(path, expected_sha256, study_continuation=True).checked
    if type(checked) is not CheckedStudyContinuation:
        raise WitnessContinuationError("study continuation needs its distinct checked scope")
    return checked


def check_trial_continuation(path: Path, *, expected_sha256: str) -> CheckedTrialContinuation:
    """Check the unchanged funded trial and all phase joins, without keys or writes."""
    checked = _checked_state(path, expected_sha256, trial_continuation=True).checked
    if type(checked) is not CheckedTrialContinuation:
        raise WitnessContinuationError("trial continuation needs its exact checked scope")
    return checked


def launch_trial_continuation(
    path: Path,
    *,
    expected_sha256: str,
    live: bool = False,
    prompt_keys: bool = False,
    confirm_project_keys: bool = False,
    transport: gateway.RawHTTPTransport | None = None,
    notice: Callable[[str], None] | None = None,
    heartbeat_seconds: float = 10,
) -> dict[str, object]:
    """Run the original coordinator under its checked execution overlay.

    Original key-review contexts, phase order, grants, partial observations and
    canonical comparison publication stay owned by that coordinator.
    """
    from buddha import unified_launch

    prepared = _checked_state(path, expected_sha256, trial_continuation=True)
    checked = prepared.checked
    if type(checked) is not CheckedTrialContinuation:
        raise WitnessContinuationError("trial continuation needs its exact checked scope")

    def before_start(trial: Path) -> None:
        checked._check_thread(checked.study)
        if str(trial) != str(checked._trial):
            raise WitnessContinuationError("continuation writer changes the checked trial")
        # The original coordinator owns its separate workspace lease here. Its
        # phase controllers acquire the original trial/study leases themselves.
        prepared.after_locks(owned_locks=frozenset())

    with checked._scope(before_start=before_start):
        return unified_launch.launch(
            checked._launch[0],
            expected_sha256=checked._launch[1],
            live=live,
            prompt_keys=prompt_keys,
            confirm_project_keys=confirm_project_keys,
            transport=transport,
            notice=unified_launch._notice if notice is None else notice,
            heartbeat_seconds=heartbeat_seconds,
        )


def advance_study(
    checked: CheckedStudyContinuation, *, transport: gateway.RawHTTPTransport
) -> dict[str, object]:
    """One ordinary development action; final/plain controllers are never routed."""
    if type(checked) is not CheckedStudyContinuation or not isinstance(
        transport, gateway.RawHTTPTransport
    ):
        raise WitnessContinuationError("development advancement needs its exact checked context")
    checked._check_thread(checked.study)
    prepared = _checked_state(checked.path, checked.sha256, study_continuation=True)
    return _advance_prepared(prepared, transport=transport)


def advance_study_descriptor(
    path: Path, *, expected_sha256: str, transport: gateway.RawHTTPTransport
) -> dict[str, object]:
    """Check once, then advance one development action with fresh lease checks.

    Unlike a separate preflight followed by checked-token advancement, this
    descriptor entry avoids reconstructing the same history twice. It retains
    the complete check and the identical post-lock file/grant verification.
    """
    if not isinstance(transport, gateway.RawHTTPTransport):
        raise WitnessContinuationError("development advancement needs an explicit transport")
    prepared = _checked_state(path, expected_sha256, study_continuation=True)
    return _advance_prepared(prepared, transport=transport)


def _advance_prepared(
    prepared: _CheckedState, *, transport: gateway.RawHTTPTransport
) -> dict[str, object]:
    """Dispatch the same freshly checked state; never accept an unchecked token."""
    current = cast(CheckedStudyContinuation, prepared.checked)
    if prepared.state is None:
        raise WitnessContinuationError("development advancement lacks its validated state")
    with current._scope():
        authority = Authorization(prepared.search_grant)
        with (
            trial_fence.work(
                authority.path, authority._terms(), directory=current.study, kind="search"
            ),
            pipeline._exclusive(current.study),
        ):
            prepared.after_locks()
            if prepared.study_result is not None:
                return {"action": "complete", "role": None, "result": _load(prepared.study_result)}
            improver_study._check_current(prepared.state)
            reader = NativeEvidence(
                current.study, authority.path, error_type=WitnessContinuationError
            )
            result = improver_study._advance_action(reader, prepared.state, authority, transport)
            return {"action": prepared.action["kind"], "role": None, "result": result}


def advance_witness(
    checked: CheckedWitnessContinuation, *, transport: gateway.RawHTTPTransport
) -> dict[str, object]:
    """Advance one normal role only; never run the study or later phases."""
    if type(checked) is not CheckedWitnessContinuation or not isinstance(
        transport, gateway.RawHTTPTransport
    ):
        raise WitnessContinuationError(
            "witness advancement needs an exact checked context and transport"
        )
    if checked._pid != os.getpid() or checked._thread != threading.get_ident():
        raise WitnessContinuationError("witness advancement differs from its checked thread")
    # No cache/token bypass: every invocation freshly checks original evidence.
    prepared = _checked_state(checked.path, checked.sha256)
    current = prepared.checked
    with current._scope():
        authorization = prepared.search_grant
        authority = Authorization(authorization)
        with (
            trial_fence.work(
                authorization, authority._terms(), directory=current.study, kind="search"
            ),
            pipeline._exclusive(current.study),
        ):
            prepared.after_locks()
            if prepared.witness_result is not None:
                return {
                    "action": "complete",
                    "role": None,
                    "result": _load(prepared.witness_result),
                }
            action = prepared.action
            if action["kind"] != "witness" or action["directory"] != current.witness:
                raise WitnessContinuationError(
                    "the one checked witness has no further allowed action"
                )
            reader = NativeEvidence(
                current.study, authorization, error_type=WitnessContinuationError
            )
            return source_search._advance_witness(
                reader, action["treatment"], authorization=authority, transport=transport
            )
