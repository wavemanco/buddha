"""Prospective supplied scale history; no paid run or edited historical records."""

import copy
import hashlib
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from scale_native_environment import INVENTORY_COUNT, build_environment
from test_improver_study import FiniteImproverStudyTests, ImproverStudyCapacityTests
from test_source_screen_local_reuse import SourceScreenLocalReuseTests

from buddha.answers import TaskSet
from buddha.releases import Release, _json, inventory, prepare_selection

TASK_IDS = ("1", "synthetic-0", "synthetic-1")
DATASET_BYTES = 645_466
TASK_SOURCE_BYTES = 1_113_890
SCREEN_BYTES_FLOOR = 5_315_388
OWNER_COUNT = 193
OPERATION_COUNT = 660


def _distribute(rows, key, total):
    quotient, remainder = divmod(total, len(rows))
    for index, row in enumerate(rows):
        row[key] += "x" * (quotient + (index < remainder))


def _source(h, *, sized=True):
    """Size real dataset/task records before their prospective owners exist."""
    rows = copy.deepcopy(h.rows)
    for row in rows:
        row["scale_metadata"] = ""
    release_record = copy.deepcopy(h.engine.fixture.release_record)
    release_record["task"]["count"] = 10

    def derive():
        raw = b"".join(_json(row) + b"\n" for row in rows)
        release_record["source"]["data/tasks.jsonl"] = hashlib.sha256(raw).hexdigest()
        return raw, TaskSet.from_dataset(Release.from_record(release_record), raw)

    raw, _ = derive()
    metadata_size = DATASET_BYTES - len(raw)
    if not sized:
        metadata_size = 0
    if metadata_size < 0:
        raise AssertionError("base supplied source exceeds the declared footprint")
    _distribute(rows, "scale_metadata", metadata_size)
    _, tasks = derive()
    prompt_size = TASK_SOURCE_BYTES - len(tasks.to_bytes()) if sized else 0
    if not 0 <= prompt_size <= metadata_size:
        raise AssertionError("source footprint needs an unsupported record shape")
    for row in rows:
        row["scale_metadata"] = ""
    _distribute(rows, "prompt", prompt_size)
    _distribute(rows, "scale_metadata", metadata_size - prompt_size)
    raw, tasks = derive()
    if sized and (len(raw) != DATASET_BYTES or len(tasks.to_bytes()) != TASK_SOURCE_BYTES):
        raise AssertionError("supplied source footprint differs from its declaration")
    supplied = h.engine.fixture
    (supplied.roots["official"] / "data/tasks.jsonl").write_bytes(raw)
    supplied.release_record = release_record
    if inventory(supplied.roots["official"]) != release_record["source"]:
        raise AssertionError("prospective source files differ from the actual release")
    h.rows, h.source = rows, tasks


def harness(case, *, inventory_count=INVENTORY_COUNT, sized_source=True, native_callbacks=(1, 10)):
    """Reuse the existing 1000-row harness, then freeze scale inputs pre-bootstrap."""
    reuse = SourceScreenLocalReuseTests("runTest")
    case.addCleanup(reuse.doCleanups)
    h = reuse.fixture(thousand=True)
    if not sized_source:
        h.rows = h.rows[:6]
    _source(h, sized=sized_source)
    e, supplied = h.engine, h.engine.fixture
    e.native_callback_counts = native_callbacks
    e.candidate.release = Release.from_record(supplied.release_record)
    e.candidate.tasks = h.source.select([TASK_IDS[0]])
    e.candidate.task_path.write_bytes(e.candidate.tasks.to_bytes())
    capabilities = supplied.selection.to_record()["capabilities"]
    supplied.selection = prepare_selection(
        e.candidate.release,
        supplied.roots,
        capabilities=capabilities,
    )
    native_roots = {name: Path(path) for name, path in e.native["roots"].items()}
    e.native["selection"] = prepare_selection(
        e.candidate.release,
        native_roots,
        capabilities=e.native["selection"]["capabilities"],
    ).to_record()
    e.native["environment"] = build_environment(
        h.root / "scale-native-image", inventory_count=inventory_count
    )
    h.record["source"] = h.source.to_record()
    h.record["generation"]["selection"] = supplied.selection.to_record()
    h.record["native"] = copy.deepcopy(e.native)
    split = h.record["split"]
    split.update(release_sha256=h.source.release_sha256, dataset_sha256=h.source.dataset_sha256)
    split["families"] = [
        {"id": task.id, "family": "family-" + str(index)}
        for index, task in enumerate(h.source.tasks)
    ]
    split["partitions"] = {
        "development": list(TASK_IDS),
        "validation": ["private"],
        "final": [task.id for task in h.source.tasks if task.id not in {*TASK_IDS, "private"}],
    }
    original_screen = h.screen

    def screen(record=None):
        prospective = copy.deepcopy(h.record if record is None else record)
        if inventory_count == INVENTORY_COUNT:
            families = prospective["split"]["families"]
            missing = max(0, SCREEN_BYTES_FLOOR - len(_json(prospective)))
            _distribute(families, "family", missing)
        return original_screen(prospective)

    h.screen = screen
    return h


def prepare(
    case,
    *,
    inventory_count=INVENTORY_COUNT,
    sized_source=True,
    generation_callbacks=4,
    native_callbacks=(1, 10),
):
    """Return a genuine v4 fixture/declaration, without starting its study owners."""
    f = FiniteImproverStudyTests("runTest")
    case.addCleanup(f.doCleanups)
    f.fixture_before_new_api(
        proposal_capacity=True,
        harness_factory=lambda: harness(
            case,
            inventory_count=inventory_count,
            sized_source=sized_source,
            native_callbacks=native_callbacks,
        ),
        task_ids=TASK_IDS,
        generation_callbacks=generation_callbacks,
        unique_children=True,
    )
    capacity = ImproverStudyCapacityTests("runTest")
    case.addCleanup(capacity.doCleanups)
    _, record = capacity.fixture(finite_fixture=f)
    record.update(starts=copy.deepcopy(f.starts), repetitions=2, descendant_opportunities=2)
    record["selection"]["finalist_iteration"] = 2
    f.recompute_limits(record)
    return f, record


class _CutReached(Exception):
    pass


def produce(f, record):
    """Use the real scheduler, stopping at the declared next SCREEN before its worker."""
    directory, declaration, authority = f.prepare_study("scale-replay", record)
    ordinary = f.api._advance_action
    steps, observed = Counter(), {}

    def advance(reader, state, funded, transport):
        action = state["action"]
        if len(state["decisions"]) == 9 and action["kind"] == "screen":
            f.api._check_current(state)
            reader.finish()
            actual = {
                key: state["authorization"][key]
                for key in ("operation_count", "spent_microusd", "reserved_microusd")
            }
            if (
                len(state["owner_paths"]) != OWNER_COUNT
                or actual["operation_count"] != OPERATION_COUNT
            ):
                raise AssertionError("genuine retained history misses the prospective arithmetic")
            if any(row["status"] != "admitted" for row in state["decisions"]):
                raise AssertionError("scale history contains an unexpected skipped/failed child")
            observed.update(
                directory=str(directory),
                declaration=str(declaration),
                authorization=str(authority.path),
                owners=len(state["owner_paths"]),
                totals=actual,
                position=action["position"],
                steps=dict(steps),
            )
            raise _CutReached
        steps[action["kind"]] += 1
        return ordinary(reader, state, funded, transport)

    try:
        with f.supplied(), patch.object(f.api, "_advance_action", side_effect=advance):
            f.api.run_improver_study(directory, transport=f.transport())
    except _CutReached:
        return observed
    raise AssertionError("producer completed or stopped before its declared retained boundary")
