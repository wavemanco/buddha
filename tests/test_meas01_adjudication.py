"""Only explicitly selected, resolved development judgments become expectations."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_meas01_pack import encode, readonly, sha

HELPER = Path(__file__).resolve().parents[1] / "docs/conformance/meas01-pack.py"
namespace = {"__name__": "meas01_adjudication_test", "__file__": str(HELPER)}
exec(compile(HELPER.read_bytes(), str(HELPER), "exec"), namespace)  # nosec B102: reviewed engineering source, never pyc.
adjudicated_expectations = namespace["adjudicated_expectations"]


class MeasurementAdjudicationTests(unittest.TestCase):
    def setUp(self):
        rule = "Review central content without changing the benchmark."
        self.pack = {
            "format": "buddha.meas01-pack.v1",
            "rule": {
                "text": rule,
                "sha256": sha(rule.encode()),
                "metric_version": "1.1",
                "upstream_commit": "a" * 40,
            },
            "items": [
                {
                    "id": "item-1",
                    "prompt": "Reply with one digit.",
                    "answers": [{"id": "answer-1", "text": "1"}, {"id": "answer-2", "text": "1"}],
                },
                {
                    "id": "item-2",
                    "prompt": "Tell a story about a dog.",
                    "answers": [
                        {"id": "answer-3", "text": "  Lost whistle. Ω\n"},
                        {"id": "answer-4", "text": "A garden grows."},
                    ],
                },
            ],
        }
        self.reviews = [
            self.submission("reviewer-1", together=False),
            self.submission("reviewer-2", together=True),
        ]
        self.response = self.submission("adjudicator-1", together=True)
        self.record = {
            "format": "buddha.meas01-adjudication.v1",
            "pack_sha256": sha(encode(self.pack)),
            "adjudicator": copy.deepcopy(self.response["reviewer"]),
            "submission_sha256": [sha(encode(value)) for value in self.reviews],
            "response_sha256": sha(encode(self.response)),
            "cases": [
                {
                    "item_id": "item-1",
                    "status": "resolved",
                    "rationale": "Explicit development resolution.",
                    "disagreement_resolution": "Keep both reviews; apply the declared resolution.",
                },
                {
                    "item_id": "item-2",
                    "status": "uncertain",
                    "rationale": "Broader uncertainty remains.",
                    "disagreement_resolution": "Disagreement remains unresolved.",
                },
            ],
        }

    def submission(self, identity, *, together):
        items = []
        for item in self.pack["items"]:
            ids = [answer["id"] for answer in item["answers"]]
            items.append(
                {
                    "id": item["id"],
                    "groups": [ids] if together else [[identity] for identity in ids],
                    "uncertain_pairs": [],
                    "rationale": "Synthetic structural test judgment; not a study rating.",
                    "answers": [
                        {
                            "id": identity,
                            "compliance": "complies",
                            "compliance_rationale": "Synthetic declared literal assessment.",
                            "craft_notes": "",
                            "uncertainty": "",
                        }
                        for identity in ids
                    ],
                }
            )
        return {
            "format": "buddha.meas01-submission.v1",
            "pack_sha256": sha(encode(self.pack)),
            "reviewer": {
                "id": identity,
                "type": "model",
                "prior_exposure": "Synthetic unit fixture only.",
            },
            "items": items,
        }

    def raw(self, *, reviews=None, response=None, record=None):
        review_raw = [encode(value) for value in (self.reviews if reviews is None else reviews)]
        response_raw = encode(self.response if response is None else response)
        record_value = copy.deepcopy(self.record if record is None else record)
        record_value["submission_sha256"] = [sha(value) for value in review_raw]
        record_value["response_sha256"] = sha(response_raw)
        return review_raw, response_raw, encode(record_value)

    def call(self, *, selected=None, raw=None, pack=None):
        review_raw, response_raw, record_raw = self.raw() if raw is None else raw
        with readonly():
            return adjudicated_expectations(
                self.pack if pack is None else pack,
                review_raw,
                response_raw,
                record_raw,
                ["item-1"] if selected is None else selected,
            )

    def test_only_explicit_resolved_selection_exports_exact_assessment_and_all_raw_bindings(self):
        raw = self.raw()
        result = self.call(raw=raw)
        self.assertEqual(result["format"], "buddha.meas01-expectations.v1")
        self.assertEqual(result["pack_sha256"], sha(encode(self.pack)))
        self.assertEqual(result["submission_sha256"], [sha(value) for value in raw[0]])
        self.assertEqual(result["response_sha256"], sha(raw[1]))
        self.assertEqual(result["adjudication_sha256"], sha(raw[2]))
        self.assertEqual(result["adjudicator"], self.response["reviewer"])
        self.assertEqual(
            result["cases"],
            [
                {
                    "item": self.pack["items"][0],
                    "assessment": self.response["items"][0],
                    "adjudication": self.record["cases"][0],
                }
            ],
        )
        self.assertEqual(result["unresolved_item_ids"], ["item-2"])
        self.assertTrue(result["limits"])

    def test_result_is_deeply_independent_and_pure_without_file_network_or_credential_access(self):
        original = copy.deepcopy(self.pack)
        raw = self.raw()

        def forbidden(*args, **kwargs):
            raise AssertionError("pure adjudication accessed a file")

        with (
            patch("pathlib.Path.open", side_effect=forbidden),
            patch("builtins.open", side_effect=forbidden),
        ):
            result = self.call(raw=raw)
        self.assertEqual(self.pack, original)
        result["cases"][0]["item"]["answers"][0]["text"] = "MUTATED"
        result["cases"][0]["assessment"]["groups"].clear()
        result["cases"][0]["adjudication"]["status"] = "MUTATED"
        result["adjudicator"]["id"] = "MUTATED"
        self.assertEqual(self.pack, original)
        again = self.call(raw=raw)
        self.assertNotIn("MUTATED", str(again))
        self.assertEqual(raw, self.raw())

    def test_physical_review_order_and_bytes_and_response_bytes_must_match_record(self):
        reviews, response, record = self.raw()
        variants = [
            ([reviews[0] + b" ", reviews[1]], response, record),
            (list(reversed(reviews)), response, record),
            (reviews, response + b" ", record),
        ]
        for raw in variants:
            with (
                self.subTest(raw_hashes=[sha(value) for value in raw[0]]),
                self.assertRaises(ValueError),
            ):
                self.call(raw=raw)
        for field in ("pack_sha256", "response_sha256"):
            altered = copy.deepcopy(self.record)
            altered[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.call(raw=(reviews, response, encode(altered)))

    def test_case_record_requires_exact_known_population_status_and_explanations(self):
        mutations = [
            lambda value: value["cases"].pop(),
            lambda value: value["cases"].append(copy.deepcopy(value["cases"][0])),
            lambda value: value["cases"][0].update(item_id="unknown"),
            lambda value: value["cases"][0].update(status="majority"),
            lambda value: value["cases"][0].update(rationale=""),
            lambda value: value["cases"][0].update(disagreement_resolution=""),
            lambda value: value["cases"][0].update(gold=True),
            lambda value: value.update(unreviewed_extra=True),
        ]
        for mutate in mutations:
            record = copy.deepcopy(self.record)
            mutate(record)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.call(raw=self.raw(record=record))

    def test_study_requires_two_distinct_reviewers_and_a_distinct_matching_adjudicator(self):
        for count in (0, 1, 3):
            reviews = (self.reviews * 2)[:count]
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.call(raw=self.raw(reviews=reviews))
        reviews = copy.deepcopy(self.reviews)
        reviews[1]["reviewer"]["id"] = reviews[0]["reviewer"]["id"]
        with self.assertRaises(ValueError):
            self.call(raw=self.raw(reviews=reviews))
        response = copy.deepcopy(self.response)
        response["reviewer"]["id"] = self.reviews[0]["reviewer"]["id"]
        record = copy.deepcopy(self.record)
        record["adjudicator"] = copy.deepcopy(response["reviewer"])
        with self.assertRaises(ValueError):
            self.call(raw=self.raw(response=response, record=record))
        record = copy.deepcopy(self.record)
        record["adjudicator"]["prior_exposure"] = "Different declaration"
        with self.assertRaises(ValueError):
            self.call(raw=self.raw(record=record))

    def test_resolved_cases_cannot_retain_explicit_pair_or_compliance_uncertainty(self):
        for field in ("pair", "compliance"):
            response = copy.deepcopy(self.response)
            item = response["items"][0]
            if field == "pair":
                item["uncertain_pairs"] = [
                    {"left": "answer-1", "right": "answer-2", "rationale": "Still uncertain."}
                ]
            else:
                item["answers"][0]["compliance"] = "uncertain"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.call(raw=self.raw(response=response))

    def test_broader_uncertainty_without_pairs_stays_unresolved_and_is_never_selected(self):
        result = self.call()
        self.assertEqual(self.response["items"][1]["uncertain_pairs"], [])
        self.assertEqual(result["unresolved_item_ids"], ["item-2"])
        with self.assertRaises(ValueError):
            self.call(selected=["item-1", "item-2"])
        record = copy.deepcopy(self.record)
        record["cases"][0]["status"] = "uncertain"
        inconclusive = self.call(selected=[], raw=self.raw(record=record))
        self.assertEqual(inconclusive["cases"], [])
        self.assertCountEqual(inconclusive["unresolved_item_ids"], ["item-1", "item-2"])

    def test_selection_requires_explicit_unique_known_resolved_ids(self):
        for selected in (["item-1", "item-1"], ["unknown"], ["item-2"], "item-1", [False]):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.call(selected=selected)

    def test_empty_malformed_or_nonbytes_raw_inputs_fail_without_partial_expectations(self):
        originals = self.raw()
        for position in range(4):
            for malformed in (b"", b"null", b"[]", b"{", "{}", bytearray(b"{}")):
                reviews, response, record = copy.deepcopy(originals)
                if position < 2:
                    reviews[position] = malformed
                elif position == 2:
                    response = malformed
                else:
                    record = malformed
                with (
                    self.subTest(position=position, malformed=repr(malformed)),
                    self.assertRaises(ValueError),
                ):
                    self.call(raw=(reviews, response, record))

    def test_each_raw_input_obeys_five_mib_ceiling_with_exact_boundary_preserved(self):
        maximum = 5 * 1024 * 1024
        for position in range(4):
            reviews, response, record = self.raw()
            if position < 2:
                reviews[position] += b" " * (maximum - len(reviews[position]))
            elif position == 2:
                response += b" " * (maximum - len(response))
            rebound = copy.deepcopy(self.record)
            rebound["submission_sha256"] = [sha(value) for value in reviews]
            rebound["response_sha256"] = sha(response)
            record = encode(rebound)
            if position == 3:
                record += b" " * (maximum - len(record))
            with self.subTest(boundary=position):
                self.assertEqual(
                    self.call(raw=(reviews, response, record))["adjudication_sha256"], sha(record)
                )
            oversized = b" " * (maximum + 1)
            if position < 2:
                reviews[position] = oversized
            elif position == 2:
                response = oversized
            else:
                record = oversized
            with self.subTest(oversized=position), self.assertRaises(ValueError):
                self.call(raw=(reviews, response, record))

    def test_explicit_adjudication_is_not_replaced_by_reviewer_majority_or_union(self):
        reviews = [
            self.submission("reviewer-1", together=False),
            self.submission("reviewer-2", together=False),
        ]
        result = self.call(raw=self.raw(reviews=reviews))
        self.assertEqual(result["cases"][0]["assessment"]["groups"], [["answer-1", "answer-2"]])
        self.assertEqual(result["cases"][0]["adjudication"], self.record["cases"][0])

    def test_published_study_seals_raw_reviews_and_reproduces_selected_fixture_exactly(self):
        root = Path(__file__).resolve().parents[1]
        directory = root / "docs/conformance/meas01-study"
        manifest = json.loads((directory / "manifest.json").read_bytes())
        self.assertEqual(manifest["selection_rule"], "all_explicitly_resolved_complete_items")
        self.assertTrue(manifest["files"])
        for relative, expected in manifest["files"].items():
            parts = relative.replace("\\", "/").split("/")
            self.assertTrue(all(part not in ("", ".", "..") and ":" not in part for part in parts))
            self.assertEqual(sha((root / Path(*parts)).read_bytes()), expected, relative)
        pack = json.loads((directory / "pack.json").read_bytes())
        reviews = [(directory / f"review-{index}.json").read_bytes() for index in (1, 2)]
        response = (directory / "adjudicator-response.json").read_bytes()
        record = (directory / "adjudication.json").read_bytes()
        adjudication = json.loads(record)
        decisions = {case["item_id"]: case for case in adjudication["cases"]}
        selected = [
            item["id"] for item in pack["items"] if decisions[item["id"]]["status"] == "resolved"
        ]
        with readonly():
            result = adjudicated_expectations(pack, reviews, response, record, selected)
        fixture = json.loads((root / "tests/fixtures/meas01-expectations.json").read_bytes())
        self.assertEqual(result, fixture)
        self.assertEqual(len(pack["items"]), 22)
        self.assertEqual(sum(len(item["answers"]) for item in pack["items"]), 96)
        self.assertEqual(len(result["cases"]), 17)
        self.assertEqual(len(result["unresolved_item_ids"]), 5)
        for field, expected in (
            ("items", 22),
            ("answer_appearances", 96),
            ("resolved_items", 17),
            ("uncertain_items", 5),
        ):
            self.assertEqual(manifest["counts"][field], expected)
        for index in (1, 2):
            original = json.loads((directory / f"review-{index}-original.json").read_bytes())
            corrected = json.loads(reviews[index - 1])
            for item in original["items"]:
                for pair_index, pair in enumerate(item["uncertain_pairs"]):
                    if "answer_ids" in pair:
                        self.assertEqual(set(pair), {"answer_ids", "reason"})
                        self.assertEqual(len(pair["answer_ids"]), 2)
                        item["uncertain_pairs"][pair_index] = {
                            "left": pair["answer_ids"][0],
                            "right": pair["answer_ids"][1],
                            "rationale": pair["reason"],
                        }
            self.assertEqual(original, corrected)


if __name__ == "__main__":
    unittest.main()
