"""Pure materialization of the exact frozen MEAS-02 supplied audit controls.

This creates no agent-generated Answers artifact, native judgment or funding authority.
Native rows retain pack order: the unchanged evaluator applies the batch seed itself.
"""

import hashlib
import json
import math
import re

PACK_SHA256 = "8a29cded45e11f62eaecba52e5d9c30a88e2733b28cc8138aa2fdb38d025bf15"
PROPOSAL_SHA256 = "efa7071f37ffa18d5d7909969258b4fb378939cc768537de10a9555599213cce"
MAX_INPUT_BYTES = 5 * 1024 * 1024
OCCASIONS = (
    ("baseline", None),
    ("same-order-repeat", None),
    ("order-seed-0", 0),
    ("order-seed-20261020", 20261020),
)
TARGET_FIELDS = {
    "target_id",
    "item_id",
    "kind",
    "occasion",
    "answer_count",
    "answer_ids_in_pack_order",
    "official_display_order",
    "official_display_seed",
    "rendered_call_sha256",
}


class MaterializationError(ValueError):
    """Frozen input bytes or their declared native-row mapping are invalid."""


def _fail():
    raise MaterializationError("invalid frozen audit input or target mapping")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _finite(value):
    result = float(value)
    if not math.isfinite(result):
        _fail()
    return result


def _reject(value):
    _fail()


def _parse(raw, expected):
    if type(raw) is not bytes or not raw or len(raw) > MAX_INPUT_BYTES:
        _fail()
    if hashlib.sha256(raw).hexdigest() != expected:
        _fail()
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_float=_finite,
        parse_constant=_reject,
    )


def _record(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        _fail()


def _text(value):
    if not isinstance(value, str):
        _fail()
    value.encode("utf-8")
    return value


def _hex(value, length):
    if not isinstance(value, str) or re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None:
        _fail()
    return value


def _items(pack):
    _record(pack, {"format", "rule", "items"})
    if pack["format"] != "buddha.meas01-pack.v1":
        _fail()
    rule = pack["rule"]
    _record(rule, {"text", "sha256", "upstream_commit", "metric_version"})
    if hashlib.sha256(_text(rule["text"]).encode("utf-8")).hexdigest() != _hex(rule["sha256"], 64):
        _fail()
    _hex(rule["upstream_commit"], 40)
    if rule["metric_version"] != "1.1":
        _fail()
    if not isinstance(pack["items"], list) or len(pack["items"]) != 22:
        _fail()
    result, answer_ids = {}, set()
    for item in pack["items"]:
        _record(item, {"id", "prompt", "answers"})
        identity = _hex(item["id"], 32)
        _text(item["prompt"])
        if identity in result or not isinstance(item["answers"], list):
            _fail()
        if len(item["answers"]) not in (2, 4, 10):
            _fail()
        for answer in item["answers"]:
            _record(answer, {"id", "text"})
            answer_id = _hex(answer["id"], 32)
            if answer_id in answer_ids:
                _fail()
            answer_ids.add(answer_id)
            _text(answer["text"])
        result[identity] = item
    return result


def _materialize(pack, proposal):
    items = _items(pack)
    if (
        not isinstance(proposal, dict)
        or proposal.get("format") != "buddha.meas02-target-proposal.v1"
    ):
        _fail()
    if proposal["input_sha256"]["docs/conformance/meas01-study/pack.json"] != PACK_SHA256:
        _fail()
    if proposal["counts"] != {
        "additional_order_fullsets": 12,
        "baseline_items": 22,
        "nominal_max_semantic_folds_without_SDK_retries": 120,
        "same_order_fullset_repeats": 6,
        "targets": 40,
    }:
        _fail()
    targets = proposal["targets"]
    if not isinstance(targets, list) or len(targets) != 40:
        _fail()
    baseline, target_ids, result, offset = {}, set(), [], 0
    orders = {}
    for occasion, seed in OCCASIONS:
        selected = list(items) if occasion == "baseline" else list(baseline)
        if len(selected) != (22 if occasion == "baseline" else 6):
            _fail()
        batch_targets, rows = [], []
        for item_id in selected:
            target, item = targets[offset], items[item_id]
            offset += 1
            _record(target, TARGET_FIELDS)
            target_id = _hex(target["target_id"], 64)
            if target_id in target_ids:
                _fail()
            target_ids.add(target_id)
            answers = item["answers"]
            if (
                target["item_id"] != item_id
                or target["occasion"] != occasion
                or type(target["answer_count"]) is not int
                or target["answer_count"] != len(answers)
                or target["answer_ids_in_pack_order"] != [answer["id"] for answer in answers]
                or type(target["official_display_seed"]) is not type(seed)
                or target["official_display_seed"] != seed
            ):
                _fail()
            kind = target["kind"]
            if kind not in ("historical_set", "historical_comparison", "authored_control"):
                _fail()
            if (kind == "historical_set") != (len(answers) == 10) or (
                kind == "historical_comparison" and len(answers) != 2
            ):
                _fail()
            _hex(target["rendered_call_sha256"], 64)
            order = target["official_display_order"]
            if (
                not isinstance(order, list)
                or any(type(index) is not int for index in order)
                or sorted(order) != list(range(len(answers)))
                or (seed is None and order != list(range(len(answers))))
            ):
                _fail()
            if seed is not None:
                if order == list(range(10)) or (seed in orders and order != orders[seed]):
                    _fail()
                orders[seed] = order
            if occasion == "baseline" and kind == "historical_set":
                baseline[item_id] = target
            elif occasion != "baseline":
                if kind != "historical_set" or (
                    seed is None
                    and target["rendered_call_sha256"] != baseline[item_id]["rendered_call_sha256"]
                ):
                    _fail()
            batch_targets.append(target)
            rows.append(
                {
                    "id": target_id,
                    "prompt": item["prompt"],
                    "generations": [a["text"] for a in answers],
                }
            )
        native_bytes = b"".join(
            (
                json.dumps(
                    row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
                )
                + "\n"
            ).encode("utf-8")
            for row in rows
        )
        result.append(
            {
                "occasion": occasion,
                "seed": seed,
                "input_kind": "supplied audit controls",
                "targets": batch_targets,
                "native_bytes": native_bytes,
            }
        )
    if offset != 40 or orders[0] == orders[20261020]:
        _fail()
    return result


def materialize(pack_raw, proposal_raw):
    """Return four fresh input batches from the two exact, pinned physical artifacts.

    Target metadata retains original opaque item/answer IDs and recorded display maps.
    Only target ID, literal prompt and literal answers enter native JSONL. This pure
    function performs no file, environment, network, evaluator or provider operations.
    """
    try:
        return _materialize(_parse(pack_raw, PACK_SHA256), _parse(proposal_raw, PROPOSAL_SHA256))
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        UnicodeError,
        RecursionError,
        OverflowError,
    ) as exc:
        raise MaterializationError("invalid frozen audit input or target mapping") from exc
