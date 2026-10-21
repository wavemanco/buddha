"""Frozen audit inputs become native rows without generation or scientific relabeling."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_meas01_pack import encode, readonly, sha

HELPER = Path(__file__).resolve().parents[1] / "docs/conformance/meas02-materialize.py"
namespace = {"__name__": "meas02_materialize_test", "__file__": str(HELPER)}
exec(compile(HELPER.read_bytes(), str(HELPER), "exec"), namespace)  # nosec B102: reviewed engineering source, never pyc.
materialize = namespace["materialize"]
MaterializationError = namespace["MaterializationError"]
ROOT = HELPER.parents[2]
OCCASIONS = ["baseline", "same-order-repeat", "order-seed-0", "order-seed-20261020"]


class MaterializationTests(unittest.TestCase):
    def setUp(self):
        self.pack_raw = (ROOT / "docs/conformance/meas01-study/pack.json").read_bytes()
        self.proposal_raw = (ROOT / "docs/conformance/meas02-target-proposal.json").read_bytes()
        self.pack = json.loads(self.pack_raw)
        self.proposal = json.loads(self.proposal_raw)

    def structural(self, *, pack=None, proposal=None, pack_raw=None, proposal_raw=None):
        """Test structural guards after isolated test pins, never a public pin override."""
        pack_raw = encode(self.pack if pack is None else pack) if pack_raw is None else pack_raw
        proposal = copy.deepcopy(self.proposal if proposal is None else proposal)
        proposal["input_sha256"]["docs/conformance/meas01-study/pack.json"] = sha(pack_raw)
        proposal_raw = encode(proposal) if proposal_raw is None else proposal_raw
        with patch.dict(
            namespace, {"PACK_SHA256": sha(pack_raw), "PROPOSAL_SHA256": sha(proposal_raw)}
        ):
            return materialize(pack_raw, proposal_raw)

    def test_frozen_exact_forty_target_roundtrip(self):
        batches = materialize(self.pack_raw, self.proposal_raw)
        self.assertEqual([batch["occasion"] for batch in batches], OCCASIONS)
        self.assertEqual([batch["seed"] for batch in batches], [None, None, 0, 20261020])
        self.assertEqual([len(batch["targets"]) for batch in batches], [22, 6, 6, 6])
        self.assertEqual(
            [target for batch in batches for target in batch["targets"]], self.proposal["targets"]
        )
        items = {item["id"]: item for item in self.pack["items"]}
        row_ids, counts = [], set()
        for batch in batches:
            self.assertEqual(batch["input_kind"], "supplied audit controls")
            self.assertIsInstance(batch["native_bytes"], bytes)
            self.assertTrue(batch["native_bytes"].endswith(b"\n"))
            rows = [json.loads(line) for line in batch["native_bytes"].splitlines()]
            self.assertEqual(len(rows), len(batch["targets"]))
            for target, row in zip(batch["targets"], rows, strict=True):
                item = items[target["item_id"]]
                self.assertEqual(
                    row,
                    {
                        "id": target["target_id"],
                        "prompt": item["prompt"],
                        "generations": [answer["text"] for answer in item["answers"]],
                    },
                )
                self.assertEqual(
                    target["answer_ids_in_pack_order"], [answer["id"] for answer in item["answers"]]
                )
                row_ids.append(row["id"])
                counts.add(len(row["generations"]))
        self.assertEqual(len(set(row_ids)), 40)
        self.assertEqual(counts, {2, 4, 10})

    def test_fresh_occasion_ids_preserve_body_and_do_not_preshuffle(self):
        batches = materialize(self.pack_raw, self.proposal_raw)
        baseline = {
            target["item_id"]: row
            for target, row in zip(
                batches[0]["targets"],
                map(json.loads, batches[0]["native_bytes"].splitlines()),
                strict=True,
            )
        }
        for batch in batches[1:]:
            for target, line in zip(
                batch["targets"], batch["native_bytes"].splitlines(), strict=True
            ):
                row, original = json.loads(line), baseline[target["item_id"]]
                self.assertNotEqual(row["id"], original["id"])
                self.assertEqual(row["prompt"], original["prompt"])
                self.assertEqual(row["generations"], original["generations"])
                if batch["seed"] is None:
                    self.assertEqual(target["official_display_order"], list(range(10)))
                else:
                    self.assertNotEqual(target["official_display_order"], list(range(10)))

    def test_deterministic_defensive_output_and_no_io_execution_keys_or_network(self):
        expected = materialize(self.pack_raw, self.proposal_raw)
        with (
            readonly(),
            patch("builtins.open", side_effect=AssertionError("file read")),
            patch.object(Path, "open", side_effect=AssertionError("file read")),
            patch("builtins.__import__", side_effect=AssertionError("runtime import")),
        ):
            result = materialize(self.pack_raw, self.proposal_raw)
        self.assertEqual(result, expected)
        result[0]["targets"][0]["answer_ids_in_pack_order"].clear()
        result[0]["targets"][0]["occasion"] = "changed"
        result[0]["native_bytes"] = b"changed"
        self.assertEqual(materialize(self.pack_raw, self.proposal_raw), expected)
        self.assertEqual(
            self.pack_raw, (ROOT / "docs/conformance/meas01-study/pack.json").read_bytes()
        )

    def test_physical_pins_reject_even_valid_json_or_whitespace_changes(self):
        for pack_raw, proposal_raw in (
            (self.pack_raw + b"\n", self.proposal_raw),
            (self.pack_raw, self.proposal_raw + b"\n"),
            (self.pack_raw.replace(b"dog", b"cat", 1), self.proposal_raw),
            (
                self.pack_raw,
                self.proposal_raw.replace(b'"answer_count": 2', b'"answer_count": 3', 1),
            ),
        ):
            with self.subTest(pack_changed=pack_raw != self.pack_raw):
                self.assertNotEqual((pack_raw, proposal_raw), (self.pack_raw, self.proposal_raw))
                with self.assertRaises(MaterializationError):
                    materialize(pack_raw, proposal_raw)

    def test_bytes_size_and_strict_json_fail_as_typed_errors(self):
        for value in (None, "{}", bytearray(b"{}"), b"", b"x" * (5 * 1024 * 1024 + 1)):
            for position in (0, 1):
                args = [self.pack_raw, self.proposal_raw]
                args[position] = value
                with self.subTest(value_type=type(value).__name__, position=position):
                    with self.assertRaises(MaterializationError):
                        materialize(*args)
        for raw in (b"\xff", b"{}{}", b'{"items":[],"items":[]}', b"NaN", b"1e999", b"[" * 2000):
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(MaterializationError):
                    self.structural(pack_raw=raw)
                with self.assertRaises(MaterializationError):
                    self.structural(proposal_raw=raw)

    def test_pack_population_and_unique_answer_id_guards(self):
        for mode in ("missing", "extra", "duplicate_item", "duplicate_answer", "extra_field"):
            pack = copy.deepcopy(self.pack)
            if mode == "missing":
                pack["items"].pop()
            elif mode == "extra":
                pack["items"].append(copy.deepcopy(pack["items"][0]))
            elif mode == "duplicate_item":
                pack["items"][1]["id"] = pack["items"][0]["id"]
            elif mode == "duplicate_answer":
                pack["items"][1]["answers"][0]["id"] = pack["items"][0]["answers"][0]["id"]
            else:
                pack["items"][0]["rating"] = "gold"
            with self.subTest(mode=mode), self.assertRaises(MaterializationError):
                self.structural(pack=pack)

    def test_target_population_and_order_guards(self):
        for mode in (
            "missing",
            "extra",
            "duplicate_target",
            "duplicate_item",
            "reorder",
            "occasion",
        ):
            proposal = copy.deepcopy(self.proposal)
            targets = proposal["targets"]
            if mode == "missing":
                targets.pop()
            elif mode == "extra":
                targets.append(copy.deepcopy(targets[0]))
            elif mode == "duplicate_target":
                targets[1]["target_id"] = targets[0]["target_id"]
            elif mode == "duplicate_item":
                targets[1] = copy.deepcopy(targets[0])
                targets[1]["target_id"] = "0" * 64
            elif mode == "reorder":
                targets[0], targets[1] = targets[1], targets[0]
            else:
                targets[22]["occasion"] = "baseline"
            with self.subTest(mode=mode), self.assertRaises(MaterializationError):
                self.structural(proposal=proposal)

    def test_target_answer_identity_kind_count_and_seed_guards(self):
        for field, value in (
            ("answer_count", True),
            ("answer_count", 10),
            ("answer_ids_in_pack_order", ["0" * 32, "1" * 32]),
            ("kind", "historical_set"),
            ("official_display_seed", 0),
            ("official_display_order", [1, 1]),
            ("official_display_order", [False, 1]),
            ("official_display_order", [1, 0]),
            ("target_id", "bad"),
            ("rendered_call_sha256", "bad"),
        ):
            proposal = copy.deepcopy(self.proposal)
            proposal["targets"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(MaterializationError):
                self.structural(proposal=proposal)
        proposal = copy.deepcopy(self.proposal)
        proposal["targets"][22]["kind"] = "authored_control"
        with self.assertRaises(MaterializationError):
            self.structural(proposal=proposal)

    def test_rule_and_consumed_schema_are_checked(self):
        for mode in ("pack_format", "proposal_format", "rule_hash", "null_items", "null_targets"):
            pack, proposal = copy.deepcopy(self.pack), copy.deepcopy(self.proposal)
            if mode == "pack_format":
                pack["format"] = "future"
            elif mode == "proposal_format":
                proposal["format"] = "future"
            elif mode == "rule_hash":
                pack["rule"]["sha256"] = "0" * 64
            elif mode == "null_items":
                pack["items"] = None
            else:
                proposal["targets"] = None
            with self.subTest(mode=mode), self.assertRaises(MaterializationError):
                self.structural(pack=pack, proposal=proposal)

    def test_literal_empty_refused_duplicate_whitespace_and_unicode_are_not_filtered(self):
        pack = copy.deepcopy(self.pack)
        full = next(item for item in pack["items"] if len(item["answers"]) == 10)
        texts = ["", "[refused]", "  café Ω\n", "same", "same", "[empty]", "x", "y", "z", "q"]
        full["prompt"] = "  Literal prompt Ω\n"
        for answer, text in zip(full["answers"], texts, strict=True):
            answer["text"] = text
        batches = self.structural(pack=pack)
        for batch in batches:
            for target, line in zip(
                batch["targets"], batch["native_bytes"].splitlines(), strict=True
            ):
                if target["item_id"] == full["id"]:
                    row = json.loads(line)
                    self.assertEqual(row["prompt"], full["prompt"])
                    self.assertEqual(row["generations"], texts)


if __name__ == "__main__":
    unittest.main()
