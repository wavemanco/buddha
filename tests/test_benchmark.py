"""V1.1 adapter acceptance tests: no network, judges, or credentials required."""

import hashlib
import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from buddha.benchmark import (
    DEFAULT_PARTITION_MODEL,
    DEFAULT_QUALITY_MODEL,
    METRIC_VERSION,
    PARTITION_SYSTEM,
    SCORE_SYSTEM,
    UPSTREAM_COMMIT,
    Prompt,
    export_evaluation,
    fold_partition,
    import_evaluation,
    load_prompts,
    partition_order,
    prompt_manifest,
    render_responses,
)
from buddha.evaluation import EvaluationProtocol, ValidationError


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


GENERATION_CONFIG = {"model": "replay-test-model", "sampling": "regenerate"}


def protocol():
    return EvaluationProtocol(
        upstream_commit=UPSTREAM_COMMIT,
        metric_version=METRIC_VERSION,
        dataset_sha256=digest("dataset"),
        split_sha256=digest("split"),
        partition_model=DEFAULT_PARTITION_MODEL,
        quality_model=DEFAULT_QUALITY_MODEL,
        partition_prompt_sha256=digest(PARTITION_SYSTEM),
        quality_prompt_sha256=digest(SCORE_SYSTEM),
        generation_config_sha256=digest(canonical(GENERATION_CONFIG)),
        fallback_policy_sha256=digest("no fallback"),
        ordering_seed=7,
        k=3,
    )


def row(selected):
    return {
        "id": "one",
        "prompt": "Offer an alternative.",
        "model": "replay-test-model",
        "generations": ["First", "First again", "Second"],
        "partition": [0, 0, 1],
        "generation_scores": [10, None, 5],
        "distinct": 2,
        "utility": 330 / 61,
        "protocol_fingerprint": selected.fingerprint(),
    }


def write_jsonl(path, rows):
    path.write_bytes(b"".join(canonical(item) + b"\n" for item in rows))


def reseal(directory):
    """An attacker can rewrite hashes; semantic consistency must still be checked."""
    path = directory / "provenance.json"
    provenance = json.loads(path.read_bytes())
    provenance["artifact_hashes"] = {
        name: digest((directory / name).read_bytes()) for name in provenance["artifact_hashes"]
    }
    provenance.pop("provenance_sha256")
    provenance["provenance_sha256"] = digest(canonical(provenance))
    path.write_bytes(canonical(provenance) + b"\n")


class PromptTests(unittest.TestCase):
    def test_pinned_prompt_strings_match_independent_upstream_hashes(self):
        self.assertEqual(UPSTREAM_COMMIT, "64a23be6b18ec1dacc298830aab276061b6e143c")
        self.assertEqual(METRIC_VERSION, "1.1")
        self.assertEqual(DEFAULT_PARTITION_MODEL, "gpt-5.6-luna")
        self.assertEqual(DEFAULT_QUALITY_MODEL, "claude-opus-5")
        self.assertEqual(
            digest(PARTITION_SYSTEM),
            "5df0b3a31c86ea37e15b17348a34ad064790b670be345dd93fcd0a4d18385eca",
        )
        self.assertEqual(
            digest(SCORE_SYSTEM),
            "c733873476ded31b4d24fc60241129ce345544795663d2ed3940f4ca2441a24d",
        )

    def test_prompt_load_verifies_exact_bytes_before_parsing(self):
        raw = b'{"id":"one","prompt":"An idea?","category":"extra"}\r\n'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data.jsonl"
            path.write_bytes(raw)
            prompts = load_prompts(path, expected_sha256=digest(raw))
            self.assertEqual(prompts, (Prompt("one", "An idea?"),))
            self.assertEqual(prompt_manifest(prompts), {"one": digest("An idea?")})
            with self.assertRaises(FrozenInstanceError):
                prompts[0].id = "changed"
            with self.assertRaises(ValidationError):
                load_prompts(path, expected_sha256=digest(raw.replace(b"\r\n", b"\n")))

    def test_malformed_and_ambiguous_datasets_fail_with_typed_error(self):
        invalid = [
            b"",
            b"\xff",
            b"[]\n",
            b'{"id":"one","id":"two","prompt":"p"}\n',
            b'{"id":"one","prompt":"p"}\n{"id":"one","prompt":"q"}\n',
            b'{"id":"one","prompt":" "}\n',
            b'{"id":3,"prompt":"p"}\n',
            b'{"id":"one","prompt":"p"}\n\n',
            b'{"id":"one","prompt":"p","other":NaN}\n',
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data.jsonl"
            for raw in invalid:
                with self.subTest(raw=raw):
                    path.write_bytes(raw)
                    with self.assertRaises(ValidationError):
                        load_prompts(path, expected_sha256=digest(raw))
        with self.assertRaises(ValidationError):
            prompt_manifest((Prompt("one", "p"), Prompt("one", "q")))

    def test_upstream_rendering_preserves_literal_response_text(self):
        self.assertEqual(
            render_responses("P<&>", ["A\nB", "[empty]"]),
            '<prompt>\nP<&>\n</prompt>\n\n<response index="0">\nA\nB\n</response>'
            '\n\n<response index="1">\n[empty]\n</response>',
        )
        with self.assertRaises(ValidationError):
            render_responses("p", ["\ud800"])

    def test_order_and_partition_fold_match_pinned_upstream_semantics(self):
        self.assertEqual(partition_order("A prompt", 5, None), [0, 1, 2, 3, 4])
        self.assertEqual(partition_order("A prompt", 5, 7), [0, 2, 4, 3, 1])
        self.assertEqual(partition_order("A prompt", 5, 0), [0, 4, 1, 3, 2])
        for groups in ([[0, 4], [1, 2], [3]], [[3], [1, 2], [0, 4]]):
            self.assertEqual(
                fold_partition(groups, prompt="A prompt", n=5, seed=7),
                [0, 0, 1, 2, 1],
            )

    def test_incomplete_or_invalid_judge_partition_is_never_repaired(self):
        invalid = [
            None,
            "012",
            [],
            [[0, 1]],
            [[], [0, 1, 2]],
            [[0, 1], [1, 2]],
            [[0, 1, 3]],
            [[0, 1, -1]],
            [[0, True, 2]],
            [[0, 1.0, 2]],
        ]
        for groups in invalid:
            with self.subTest(groups=groups):
                with self.assertRaises(ValidationError):
                    fold_partition(groups, prompt="p", n=3, seed=None)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.destination = Path(self.temporary.name) / "evaluation"
        self.protocol = protocol()
        self.row = row(self.protocol)
        self.manifest = {"one": digest(self.row["prompt"])}

    def export(self, **changes):
        arguments = {
            "protocol": self.protocol,
            "rows": [self.row],
            "generation_config": GENERATION_CONFIG,
        }
        arguments.update(changes)
        export_evaluation(self.destination, **arguments)

    def read(self):
        return import_evaluation(
            self.destination, protocol=self.protocol, expected_prompt_hashes=self.manifest
        )

    def test_roundtrip_retains_upstream_evidence_and_recomputes_metrics(self):
        self.export()
        summary, imported = self.read()
        self.assertEqual(summary.expected_count, 1)
        self.assertEqual(summary.scored_count, 1)
        self.assertAlmostEqual(summary.mean_utility, 330 / 61)
        self.assertEqual(imported[0]["partition_scores"], [10, 5])
        self.assertEqual(imported[0]["generations"], self.row["generations"])
        provenance = json.loads((self.destination / "provenance.json").read_bytes())
        self.assertEqual(provenance["protocol_fingerprint"], self.protocol.fingerprint())
        self.assertEqual(provenance["generation_config"], GENERATION_CONFIG)
        self.assertEqual(
            set(provenance["artifact_hashes"]),
            {
                "generations.jsonl",
                "v1.1/partitions.jsonl",
                "v1.1/scores.jsonl",
                "v1.1/summary.json",
            },
        )
        for name, expected in provenance["artifact_hashes"].items():
            self.assertEqual(digest((self.destination / name).read_bytes()), expected)

    def test_non_v11_wrong_commit_and_wrong_prompt_hashes_reject(self):
        for changes in (
            {"metric_version": "1.0"},
            {"upstream_commit": "a" * 40},
            {"partition_prompt_sha256": "a" * 64},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.export(protocol=replace(self.protocol, **changes))
        self.export()
        with self.assertRaises(ValidationError):
            import_evaluation(
                self.destination,
                protocol=self.protocol,
                expected_prompt_hashes={"one": digest("wrong")},
            )

    def test_export_rejects_wrong_config_scored_duplicates_and_invalid_metrics(self):
        with self.assertRaises(ValidationError):
            self.export(generation_config={"model": "different"})
        for changes in (
            {"generation_scores": [10, 9, 5]},
            {"utility": 10},
            {"partition": [1, 1, 0]},
            {"unscored": "judge_refusal"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.export(rows=[self.row | changes])
        self.assertFalse(self.destination.exists())

    def test_matching_export_is_idempotent_and_conflict_preserves_existing_bytes(self):
        self.export()
        original = {
            str(p.relative_to(self.destination)): p.read_bytes()
            for p in self.destination.rglob("*")
            if p.is_file()
        }
        self.export()
        with self.assertRaises(ValidationError):
            self.export(rows=[self.row | {"generations": ["Changed", "again", "next"]}])
        self.assertEqual(
            original,
            {
                str(p.relative_to(self.destination)): p.read_bytes()
                for p in self.destination.rglob("*")
                if p.is_file()
            },
        )
        (self.destination / "extra.txt").write_text("preserve me")
        with self.assertRaises(ValidationError):
            self.export()
        self.assertEqual((self.destination / "extra.txt").read_text(), "preserve me")

    def test_existing_empty_directory_and_another_export_lock_are_preserved(self):
        self.destination.mkdir()
        with self.assertRaises(ValidationError):
            self.export()
        self.assertEqual(list(self.destination.iterdir()), [])
        self.destination.rmdir()
        lock = self.destination.parent / f".{self.destination.name}.export.lock"
        lock.write_bytes(b"another owner")
        with self.assertRaises(ValidationError):
            self.export()
        self.assertEqual(lock.read_bytes(), b"another owner")

    def test_failed_publish_leaves_no_partial_destination(self):
        with patch("buddha.benchmark.os.rename", side_effect=OSError("disk failure")):
            with self.assertRaises((OSError, ValidationError)):
                self.export()
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.destination.parent.iterdir()), [])

    def test_cleanup_never_recursively_deletes_a_resolved_foreign_directory(self):
        foreign = self.destination.parent / "unrelated" / ".evaluation.foreign"
        foreign.mkdir(parents=True)
        sentinel = foreign / "preserve.txt"
        sentinel.write_bytes(b"keep")
        with (
            patch("buddha.benchmark.tempfile.mkdtemp", return_value=str(foreign)),
            patch("buddha.benchmark.os.rename", side_effect=OSError("publish failed")),
            self.assertRaises(ValidationError),
        ):
            self.export()
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertFalse((self.destination.parent / ".evaluation.export.lock").exists())

    def test_tampered_file_and_provenance_fail_before_row_trust(self):
        self.export()
        path = self.destination / "generations.jsonl"
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        with self.assertRaises(ValidationError):
            self.read()
        path.write_bytes(original)
        provenance_path = self.destination / "provenance.json"
        provenance = json.loads(provenance_path.read_bytes())
        provenance["protocol_fingerprint"] = "a" * 64
        provenance_path.write_bytes(canonical(provenance))
        with self.assertRaises(ValidationError):
            self.read()

    def test_resealed_unknown_or_missing_origin_is_not_a_local_format(self):
        self.export()
        path = self.destination / "provenance.json"
        original = json.loads(path.read_bytes())
        for origin in ("official-certification", None):
            with self.subTest(origin=origin):
                modified = dict(original)
                if origin is None:
                    modified.pop("origin")
                else:
                    modified["origin"] = origin
                path.write_bytes(canonical(modified) + b"\n")
                reseal(self.destination)
                with self.assertRaises(ValidationError):
                    self.read()

    def test_rehashed_cross_stage_text_partition_and_id_forgery_fail(self):
        self.export()
        path = self.destination / "v1.1" / "scores.jsonl"
        original = json.loads(path.read_bytes())
        mutations = [
            [{"generations": ["Second", "First again", "First"]}],
            [{"partition": [0, 1, 1]}],
            [{"id": "extra"}],
            [{}, {}],
        ]
        for replacements in mutations:
            with self.subTest(replacements=replacements):
                write_jsonl(path, [original | changes for changes in replacements])
                reseal(self.destination)
                with self.assertRaises(ValidationError):
                    self.read()

    def test_rehashed_summary_forgery_and_missing_expected_prompt_fail(self):
        self.export()
        summary_path = self.destination / "v1.1" / "summary.json"
        summary = json.loads(summary_path.read_bytes())
        summary_path.write_bytes(canonical(summary | {"mean_utility": 10}))
        reseal(self.destination)
        with self.assertRaises(ValidationError):
            self.read()
        with self.assertRaises(ValidationError):
            import_evaluation(
                self.destination,
                protocol=self.protocol,
                expected_prompt_hashes=self.manifest | {"missing": digest("x")},
            )

    def test_rehashed_numeric_type_substitutions_do_not_match_protocol(self):
        self.export()
        for name in ("partitions.jsonl", "scores.jsonl"):
            path = self.destination / "v1.1" / name
            evidence = json.loads(path.read_bytes())
            evidence["partition_config"]["seed"] = 7.0
            write_jsonl(path, [evidence])
        reseal(self.destination)
        with self.assertRaises(ValidationError):
            self.read()

    def test_secret_bearing_configuration_is_rejected_without_echo(self):
        config = GENERATION_CONFIG | {"api_key": "never-print-this-key"}
        selected = replace(self.protocol, generation_config_sha256=digest(canonical(config)))
        with self.assertRaises(ValidationError) as caught:
            self.export(protocol=selected, generation_config=config, rows=[row(selected)])
        self.assertNotIn("never-print-this-key", str(caught.exception))

    def test_export_rejects_unsupported_judge_outcomes_before_dropping_metadata(self):
        for field, value in (
            ("fallback_judge", "different-judge"),
            ("fallback_calls", [0]),
            ("unscored", "judge_refusal"),
        ):
            self.destination = Path(self.temporary.name) / field
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.export(rows=[self.row | {field: value}])
                self.assertFalse(self.destination.exists())

    def test_export_validates_supplied_configs_before_replacing_them(self):
        self.export()
        original = json.loads((self.destination / "v1.1/scores.jsonl").read_bytes())
        for field in ("generation_config", "partition_config", "score_config"):
            self.destination = Path(self.temporary.name) / field
            supplied = dict(original[field])
            supplied["model" if field == "generation_config" else "judge_model"] = "other"
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.export(rows=[self.row | {field: supplied}])
                self.assertFalse(self.destination.exists())

    def test_matching_optional_configs_roundtrip_without_changes(self):
        self.export()
        original = json.loads((self.destination / "v1.1/scores.jsonl").read_bytes())
        self.destination = Path(self.temporary.name) / "matching"
        self.export(rows=[original])
        _, imported = self.read()
        self.assertEqual(imported[0], original)

    def test_import_rejects_rehashed_unsupported_outcomes_in_every_stage(self):
        self.export()
        for name in ("generations.jsonl", "v1.1/partitions.jsonl", "v1.1/scores.jsonl"):
            path = self.destination / name
            original = path.read_bytes()
            for field, value in (
                ("fallback_judge", "different-judge"),
                ("fallback_calls", [0]),
                ("unscored", "judge_refusal"),
            ):
                write_jsonl(path, [json.loads(original) | {field: value}])
                reseal(self.destination)
                before = {p: p.read_bytes() for p in self.destination.rglob("*") if p.is_file()}
                with self.subTest(name=name, field=field), self.assertRaises(ValidationError):
                    self.read()
                self.assertEqual(
                    before, {p: p.read_bytes() for p in self.destination.rglob("*") if p.is_file()}
                )
            path.write_bytes(original)
            reseal(self.destination)


if __name__ == "__main__":
    unittest.main()
