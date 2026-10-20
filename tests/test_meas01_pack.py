"""Blinded audit packs preserve sealed answers without inventing semantic labels."""

import builtins
import copy
import hashlib
import json
import os
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[1] / "docs/conformance/meas01-pack.py"
namespace = {"__name__": "meas01_pack_test", "__file__": str(HELPER)}
exec(compile(HELPER.read_bytes(), str(HELPER), "exec"), namespace)  # nosec B102: reviewed helper source, never pyc.
build = namespace["build"]
validate_submission = namespace["validate_submission"]


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def readonly():
    def forbidden(*args, **kwargs):
        raise AssertionError("audit pack attempted a write, execution, key or network operation")

    original = Path.open
    builtin_open = builtins.open

    def read(path, mode="r", *args, **kwargs):
        if any(part in mode for part in "wax+"):
            forbidden()
        return original(path, mode, *args, **kwargs)

    def read_builtin(file, mode="r", *args, **kwargs):
        if any(part in mode for part in "wax+"):
            forbidden()
        return builtin_open(file, mode, *args, **kwargs)

    with ExitStack() as stack:
        for target in (
            "pathlib.Path.write_bytes",
            "pathlib.Path.write_text",
            "pathlib.Path.mkdir",
            "pathlib.Path.unlink",
            "pathlib.Path.replace",
            "pathlib.Path.rename",
            "os.open",
            "os.mkdir",
            "os.remove",
            "os.unlink",
            "os.rename",
            "os.replace",
            "os.environ.get",
            "socket.create_connection",
            "socket.socket.connect",
            "http.client.HTTPSConnection",
            "subprocess.run",
            "subprocess.Popen",
            "builtins.exec",
        ):
            stack.enter_context(patch(target, side_effect=forbidden))
        stack.enter_context(patch.object(Path, "open", read))
        stack.enter_context(patch("builtins.open", side_effect=read_builtin))
        yield


class MeasurementPackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.inventory_path = self.root / "inventory.json"
        self.controls_path = self.root / "controls.json"
        self.prompt = "Give two alternatives about a café."
        self.prompt_id = "PROMPT-METADATA-CANARY"
        rule = (
            "Equivalent responses add no new central content; "
            "different central content is distinct."
        )
        self.inventory = {
            "format": "buddha.meas01-source-inventory.v1",
            "official_rule": {
                "exact_text": rule,
                "text_utf8_sha256": sha(rule.encode()),
                "upstream_commit": "a" * 40,
                "metric_version": "1.1",
            },
            "candidates": {},
            "answers": {},
            "existing_concerns": [],
            "shared_subject_control_candidates": [],
        }
        self.source_paths = []
        for label, answers in (
            ("A", ["  Same Ω\nliteral  ", "  Same Ω\nliteral  "]),
            ("B", ["", "[refused]"]),
        ):
            path = self.root / (label + ".jsonl")
            raw = (
                encode(
                    {"prompt": "Unselected first row", "generations": ["never selected"]}
                ).replace(b"\n", b"")
                + b"\n"
            )
            raw += (
                json.dumps(
                    {
                        "id": self.prompt_id,
                        "protocol_fingerprint": sha(label.encode()),
                        "prompt": self.prompt,
                        "generations": answers,
                    },
                    ensure_ascii=False,
                ).encode()
                + b"\n"
            )
            path.write_bytes(raw)
            self.source_paths.append(path)
            references = []
            for index, answer in enumerate(answers):
                reference = f"ORIGINAL-SET-{label}:{index}"
                references.append(reference)
                self.inventory["answers"][reference] = {
                    "reference_id": reference,
                    "prompt": self.prompt,
                    "answer_index_0based": index,
                    "answer_index_1based": index + 1,
                    "answer_utf8_sha256": sha(answer.encode()),
                    "answer_utf8_bytes": len(answer.encode()),
                    "answer_source": {
                        "path": path.name,
                        "file_sha256": sha(raw),
                        "jsonl_line_1based": 2,
                        "json_pointer": f"/generations/{index}",
                    },
                    "run_id": "RUN-METADATA-CANARY",
                    "candidate_id": "CANDIDATE-METADATA-CANARY-" + label,
                    "prompt_id": self.prompt_id,
                    "recorded_partition": {"class_id": 9},
                    "recorded_quality": {"value": 7},
                }
            self.inventory["candidates"]["ORIGINAL-SET-" + label] = {
                "answer_references": references,
                "candidate_id": "CANDIDATE-METADATA-CANARY-" + label,
                "run_id": "RUN-METADATA-CANARY",
                "prompt_id": self.prompt_id,
                "protocol_fingerprint": sha(label.encode()),
                "protocol": {
                    "k": 2,
                    "partition_prompt_sha256": sha(rule.encode()),
                    "metric_version": "1.1",
                    "partition_model": "MODEL-METADATA-CANARY",
                },
                "policy": {"instructions": "POLICY-METADATA-CANARY"},
            }
        self.inventory["existing_concerns"] = [
            {
                "case_id": "CONCERN-METADATA-CANARY",
                "answer_references": ["ORIGINAL-SET-A:0", "ORIGINAL-SET-B:0"],
                "existing_observation": "SELECTION-REASON-CANARY",
                "new_semantic_label": None,
            }
        ]
        self.controls = [
            {
                "id": "AUTHORED-CONTROL-METADATA",
                "prompt": "Reply with a single digit.",
                "answers": ["1", "7"],
                "purpose": "PURPOSE-METADATA-CANARY",
                "author": "AUTHOR-METADATA-CANARY",
                "provenance": "PROVENANCE-METADATA-CANARY",
            }
        ]
        self.write_inputs()

    def write_inputs(self):
        self.inventory_path.write_bytes(encode(self.inventory))
        self.controls_path.write_bytes(encode(self.controls))
        self.inventory_sha = sha(self.inventory_path.read_bytes())

    def build(self, seed=17):
        before = {
            path: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
            if path.is_file()
        }
        with readonly():
            result = build(
                self.root, self.inventory_path, self.inventory_sha, self.controls_path, seed
            )
        self.assertEqual(
            before,
            {
                path: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*")
                if path.is_file()
            },
        )
        self.assertEqual(
            set(result),
            {
                "reviewer/pack.json",
                "reviewer/REVIEW.md",
                "reviewer/response-template.json",
                "private/provenance.json",
                "private/adjudication-template.json",
                "private/coverage.json",
            },
        )
        self.assertTrue(all(type(value) is bytes for value in result.values()))
        return result

    def records(self):
        artifacts = self.build()
        return (
            artifacts,
            json.loads(artifacts["reviewer/pack.json"]),
            json.loads(artifacts["reviewer/response-template.json"]),
        )

    def submission(self, template):
        result = copy.deepcopy(template)
        result["reviewer"] = {
            "id": "reviewer-1",
            "type": "human",
            "prior_exposure": "No previous exposure to these answers.",
        }
        for item in result["items"]:
            item["groups"] = [[answer["id"]] for answer in item["answers"]]
            item["uncertain_pairs"] = []
            item["rationale"] = "Tentative central-content assessment, not adjudicated gold."
            for answer in item["answers"]:
                answer.update(
                    compliance="uncertain",
                    compliance_rationale="Literal constraints require independent review.",
                    craft_notes="",
                    uncertainty="Uncertainty retained.",
                )
        return result

    def assert_bad_inventory(self, mutate):
        original = copy.deepcopy(self.inventory)
        try:
            mutate(self.inventory)
            self.write_inputs()
            with self.assertRaises(ValueError):
                self.build()
        finally:
            self.inventory = original
            self.write_inputs()

    def test_exact_population_and_private_reference_roundtrip_preserve_poor_literal_answers(self):
        artifacts, pack, _ = self.records()
        key = json.loads(artifacts["private/provenance.json"])
        coverage = json.loads(artifacts["private/coverage.json"])
        self.assertEqual(pack["format"], "buddha.meas01-pack.v1")
        self.assertEqual(set(pack), {"format", "rule", "items"})
        self.assertEqual(key["inventory_sha256"], self.inventory_sha)
        self.assertEqual(key["controls_sha256"], sha(self.controls_path.read_bytes()))
        self.assertEqual(key["pack_sha256"], sha(artifacts["reviewer/pack.json"]))
        self.assertEqual(key["seed"], 17)
        self.assertEqual(
            {
                field: coverage[field]
                for field in (
                    "historical_sets",
                    "historical_answers",
                    "comparison_cards",
                    "authored_cards",
                    "response_items",
                    "response_answers",
                )
            },
            {
                "historical_sets": 2,
                "historical_answers": 4,
                "comparison_cards": 1,
                "authored_cards": 1,
                "response_items": 4,
                "response_answers": 8,
            },
        )
        historical = []
        for item in pack["items"]:
            source = key["items"][item["id"]]
            for answer in item["answers"]:
                reference = source["answers"][answer["id"]]
                if source["kind"] == "authored_control":
                    self.assertEqual(
                        answer["text"], self.controls[0]["answers"][reference["original_index"]]
                    )
                    self.assertTrue(reference["reference_id"].startswith("authored:"))
                else:
                    original = self.inventory["answers"][reference["reference_id"]]
                    self.assertEqual(reference["source"], original)
                    self.assertEqual(reference["original_index"], original["answer_index_0based"])
                    self.assertEqual(sha(answer["text"].encode()), original["answer_utf8_sha256"])
                    if source["kind"] == "historical_set":
                        historical.append(answer["text"])
        self.assertCountEqual(
            historical, ["  Same Ω\nliteral  ", "  Same Ω\nliteral  ", "", "[refused]"]
        )

    def test_seed_replays_exact_bytes_and_changes_only_presentation_and_private_order(self):
        first = self.build(17)
        self.assertEqual(first, self.build(17))
        second = self.build(18)
        self.assertNotEqual(first["reviewer/pack.json"], second["reviewer/pack.json"])

        def content(artifact):
            return sorted(
                (item["prompt"], sorted(answer["text"] for answer in item["answers"]))
                for item in json.loads(artifact)["items"]
            )

        self.assertEqual(
            content(first["reviewer/pack.json"]), content(second["reviewer/pack.json"])
        )

    def test_public_material_masks_metadata_and_retains_exact_official_rule_and_blank_template(
        self,
    ):
        artifacts, pack, template = self.records()
        public = b"\n".join(
            value for name, value in artifacts.items() if name.startswith("reviewer/")
        ).decode()
        for secret in (
            "METADATA",
            "ORIGINAL-SET",
            "SELECTION-REASON",
            str(self.root),
            "recorded_partition",
            "recorded_quality",
            "class_id",
            "expected_label",
        ):
            self.assertNotIn(secret, public)
        rule = self.inventory["official_rule"]
        self.assertEqual(
            pack["rule"],
            {
                "text": rule["exact_text"],
                "sha256": rule["text_utf8_sha256"],
                "upstream_commit": rule["upstream_commit"],
                "metric_version": "1.1",
            },
        )
        self.assertEqual(template["format"], "buddha.meas01-submission.v1")
        self.assertEqual(template["pack_sha256"], sha(artifacts["reviewer/pack.json"]))
        with self.assertRaises(ValueError):
            validate_submission(pack, template)
        for item in template["items"]:
            self.assertIsNone(item["groups"])
            self.assertEqual(item["uncertain_pairs"], [])
            self.assertEqual(item["rationale"], "")
            self.assertTrue(all(answer["compliance"] is None for answer in item["answers"]))

    def test_wrong_inventory_pin_and_drifted_source_fail_without_outputs(self):
        with readonly(), self.assertRaises(ValueError):
            build(self.root, self.inventory_path, "0" * 64, self.controls_path, 17)
        path = self.source_paths[0]
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.build()

    def test_exact_reference_population_rejects_missing_extra_duplicate_and_wrong_count(self):
        mutations = (
            lambda v: v["answers"].pop("ORIGINAL-SET-A:0"),
            lambda v: v["answers"].update(extra=copy.deepcopy(v["answers"]["ORIGINAL-SET-A:0"])),
            lambda v: v["candidates"]["ORIGINAL-SET-A"]["answer_references"].__setitem__(
                1, "ORIGINAL-SET-A:0"
            ),
            lambda v: v["candidates"]["ORIGINAL-SET-A"]["protocol"].update(k=3),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.assert_bad_inventory(mutate)

    def test_reference_positions_prompt_hash_and_text_are_verified_against_consumed_jsonl(self):
        for field, bad in (
            ("reference_id", "FOREIGN"),
            ("prompt", "Another prompt"),
            ("answer_index_0based", 1),
            ("answer_index_0based", False),
            ("answer_utf8_sha256", "0" * 64),
            ("answer_utf8_bytes", 999),
        ):
            with self.subTest(field=field):
                self.assert_bad_inventory(
                    lambda v, field=field, bad=bad: v["answers"]["ORIGINAL-SET-A:0"].update(
                        {field: bad}
                    )
                )
        for field, bad in (
            ("jsonl_line_1based", 1),
            ("jsonl_line_1based", True),
            ("json_pointer", "/generations/1"),
            ("json_pointer", "/generations/99"),
        ):
            with self.subTest(field=field, bad=bad):
                self.assert_bad_inventory(
                    lambda v, field=field, bad=bad: v["answers"]["ORIGINAL-SET-A:0"][
                        "answer_source"
                    ].update({field: bad})
                )

    def test_declared_candidate_answer_and_source_row_identity_cannot_diverge(self):
        for field in ("candidate_id", "run_id", "prompt_id"):
            with self.subTest(answer_field=field):
                self.assert_bad_inventory(
                    lambda v, field=field: v["answers"]["ORIGINAL-SET-A:0"].update(
                        {field: "FOREIGN-PROVENANCE"}
                    )
                )
        path = self.source_paths[0]
        original_raw = path.read_bytes()
        original_inventory = copy.deepcopy(self.inventory)
        for field in ("id", "protocol_fingerprint"):
            try:
                row = json.loads(original_raw.splitlines()[1])
                row[field] = "FOREIGN-PROVENANCE"
                raw = (
                    original_raw.splitlines()[0]
                    + b"\n"
                    + json.dumps(row, ensure_ascii=False).encode()
                    + b"\n"
                )
                path.write_bytes(raw)
                for index in range(2):
                    self.inventory["answers"][f"ORIGINAL-SET-A:{index}"]["answer_source"][
                        "file_sha256"
                    ] = sha(raw)
                self.write_inputs()
                with self.subTest(row_field=field), self.assertRaises(ValueError):
                    self.build()
            finally:
                path.write_bytes(original_raw)
                self.inventory = copy.deepcopy(original_inventory)
                self.write_inputs()

    def test_finite_json_number_overflow_cannot_generate_nonfinite_pack_bytes(self):
        raw = self.inventory_path.read_bytes().replace(
            b'"metric_version": "1.1"', b'"metric_version": 1e999'
        )
        self.assertIn(b"1e999", raw)
        self.inventory_path.write_bytes(raw)
        with readonly(), self.assertRaises(ValueError):
            build(self.root, self.inventory_path, sha(raw), self.controls_path, 17)

    def test_rule_hash_and_protocol_rule_link_are_consistent(self):
        self.assert_bad_inventory(
            lambda v: v["official_rule"].update(exact_text="A private replacement rule")
        )
        self.assert_bad_inventory(
            lambda v: v["candidates"]["ORIGINAL-SET-A"]["protocol"].update(
                partition_prompt_sha256="0" * 64
            )
        )

    def test_pinned_malformed_source_json_is_rejected_before_extracting_answers(self):
        path = self.source_paths[0]
        original_raw = path.read_bytes()
        original_inventory = copy.deepcopy(self.inventory)
        row = {"prompt": self.prompt, "generations": ["  Same Ω\nliteral  "] * 2}
        valid = json.dumps(row, ensure_ascii=False).encode()
        duplicate_prompt = valid[:-1] + b',"prompt":' + json.dumps(self.prompt).encode() + b"}"
        cases = (
            duplicate_prompt,
            b"\xff",
            json.dumps(row | {"generations": [7, 8]}).encode(),
            json.dumps(row | {"generations": ["extra"] * 3}).encode(),
        )
        try:
            for selected in cases:
                raw = b"{}\n" + selected + b"\n"
                path.write_bytes(raw)
                for index in range(2):
                    self.inventory["answers"][f"ORIGINAL-SET-A:{index}"]["answer_source"][
                        "file_sha256"
                    ] = sha(raw)
                self.write_inputs()
                with self.subTest(selected=selected[:25]), self.assertRaises(ValueError):
                    self.build()
        finally:
            path.write_bytes(original_raw)
            self.inventory = original_inventory
            self.write_inputs()

    def test_source_paths_cannot_escape_or_alias_sealed_files(self):
        for path in ("../outside.jsonl", str(self.source_paths[0]), "A.jsonl/../B.jsonl"):
            with self.subTest(path=path):
                self.assert_bad_inventory(
                    lambda v, path=path: v["answers"]["ORIGINAL-SET-A:0"]["answer_source"].update(
                        path=path
                    )
                )
        alias = self.root / "alias.jsonl"
        os.link(self.source_paths[0], alias)
        with self.assertRaises(ValueError):
            self.build()

    def test_top_level_parent_paths_are_rejected_before_opening_outside_inputs(self):
        child = self.root / "child"
        child.mkdir()
        outside = self.root.parent / (self.root.name + "-outside.json")
        self.addCleanup(outside.unlink)
        escaped = child / ".." / ".." / outside.name
        for field in ("controls", "inventory", "root"):
            outside.write_bytes(
                self.controls_path.read_bytes()
                if field == "controls"
                else self.inventory_path.read_bytes()
            )
            arguments = [self.root, self.inventory_path, self.inventory_sha, self.controls_path, 17]
            if field == "controls":
                arguments[3] = escaped
            elif field == "inventory":
                arguments[1] = escaped
            else:
                arguments[0] = child / ".."
            with self.subTest(field=field), readonly():
                base = Path.open

                def no_parent_open(path, *args, _base=base, **kwargs):
                    if ".." in path.parts:
                        raise AssertionError("parent-bearing input reached filesystem open")
                    return _base(path, *args, **kwargs)

                with patch.object(Path, "open", no_parent_open), self.assertRaises(ValueError):
                    build(*arguments)

    def test_authored_controls_reject_missing_duplicate_nonstring_and_presupplied_gold(self):
        original = copy.deepcopy(self.controls)
        cases = [
            original + copy.deepcopy(original),
            [original[0] | {"answers": ["1", 7]}],
            [original[0] | {"answers": []}],
            [original[0] | {"author": ""}],
            [original[0] | {"expected_label": "distinct"}],
        ]
        for value in cases:
            self.controls = value
            self.write_inputs()
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.build()

    def test_valid_human_and_model_submissions_preserve_raw_groups_and_uncertainty(self):
        _, pack, template = self.records()
        submission = self.submission(template)
        item = submission["items"][0]
        item["uncertain_pairs"] = [
            {
                "left": item["answers"][0]["id"],
                "right": item["answers"][1]["id"],
                "rationale": "A central-content boundary remains uncertain.",
            }
        ]
        for kind in ("human", "model"):
            submission["reviewer"]["type"] = kind
            before = copy.deepcopy(submission)
            self.assertIsNone(validate_submission(pack, submission))
            self.assertEqual(submission, before)
        # Structural validation does not overrule a reviewer merely because
        # duplicate strings were placed in distinct tentative groups.
        self.assertTrue(all(len(group) == 1 for group in item["groups"]))

    def test_submission_requires_exact_items_exhaustive_groups_and_answer_compliance(self):
        _, pack, template = self.records()
        original = self.submission(template)
        mutations = (
            lambda v: v["items"].pop(),
            lambda v: v["items"].append(copy.deepcopy(v["items"][0])),
            lambda v: v["items"][0].update(id="UNKNOWN"),
            lambda v: v["items"][0].update(groups=[]),
            lambda v: v["items"][0]["groups"].append(v["items"][0]["groups"][0]),
            lambda v: v["items"][0]["groups"][0].append("UNKNOWN"),
            lambda v: v["items"][0]["answers"].pop(),
            lambda v: v["items"][0]["answers"][0].update(compliance="good"),
            lambda v: v["items"][0]["answers"][0].update(compliance_rationale=""),
            lambda v: v["items"][0].update(rationale=""),
        )
        for mutate in mutations:
            bad = copy.deepcopy(original)
            mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                validate_submission(pack, bad)

    def test_uncertain_pairs_reject_reversed_duplicates_foreign_self_and_empty_rationale(self):
        _, pack, template = self.records()
        original = self.submission(template)
        left, right = [answer["id"] for answer in original["items"][0]["answers"]]
        good = {"left": left, "right": right, "rationale": "Uncertain central equivalence."}
        for pairs in (
            [good, good | {"left": right, "right": left}],
            [good | {"right": left}],
            [good | {"left": "UNKNOWN"}],
            [good | {"rationale": ""}],
        ):
            bad = copy.deepcopy(original)
            bad["items"][0]["uncertain_pairs"] = pairs
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                validate_submission(pack, bad)

    def test_submission_requires_pack_digest_and_declared_reviewer_identity_exposure(self):
        _, pack, template = self.records()
        original = self.submission(template)
        for field, bad in (("id", ""), ("type", "unknown"), ("prior_exposure", "")):
            submission = copy.deepcopy(original)
            submission["reviewer"][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_submission(pack, submission)
        submission = copy.deepcopy(original)
        submission["pack_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_submission(pack, submission)

    def test_validator_rejects_duplicate_public_pack_ids_without_collapsing_them(self):
        _, pack, template = self.records()
        submission = self.submission(template)
        for field in ("item", "answer"):
            malformed = copy.deepcopy(pack)
            if field == "item":
                malformed["items"].append(copy.deepcopy(malformed["items"][0]))
            else:
                malformed["items"][0]["answers"].append(
                    copy.deepcopy(malformed["items"][0]["answers"][0])
                )
            submitted = copy.deepcopy(submission)
            submitted["pack_sha256"] = sha(encode(malformed))
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_submission(malformed, submitted)


if __name__ == "__main__":
    unittest.main()
