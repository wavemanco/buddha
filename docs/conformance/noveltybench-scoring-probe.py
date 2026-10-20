"""Read-only conformance probe using directly compiled official pinned function bodies.

Reads preserved run files; writes only ignored review evidence. No provider calls.
Fetched source functions were inspected before this file was authored. This is
not execution of an operator-supplied runtime ZIP or the upstream CLI/network.
"""

import ast
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from buddha.benchmark import (  # noqa: E402
    PARTITION_SYSTEM,
    SCORE_SYSTEM,
    fold_partition,
    partition_order,
    render_responses,
)
from buddha.evaluation import EvaluationProtocol, ValidationError, score_sequence, summarize_run  # noqa: E402

REVIEW = ROOT / "runs/reviews"
PIN = "64a23be6b18ec1dacc298830aab276061b6e143c"
UPSTREAM = ROOT / "runs/references/noveltybench-conformance" / PIN / "src"
EXPECTED = {
    "score": "418985a40e9e159cfeffe9a43ab2c727010d7a7a29407f4e14cab3c81b77cbae",
    "partition": "263970891ff3ee1cc8df369a33beefe5cb5de618b5dd146a5234536d97954aca",
    "common": "ba60bf0f2a409c3774d75880f305325a28ed34320610667542a4596c41f424af",
    "judge": "4decf04790b90a03368eb792dfe29045435914a73ab83a52185d9dd0d1613902",
    "summarize": "0a8bd1eb7f317584f579eaa827e580f9cefe4177a1abdc35b2cb06ef96eeea9e",
}
NAMES = {
    "score": {"heads", "spread", "score_first_occurrences", "utility_fields", "score_fold", "score_refused"},
    "partition": {"partition_fold", "canonical"},
    "common": {"render_responses"},
    "judge": {"shuffled_order"},
    "summarize": {"summarize"},
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(path):
    return {str(p.relative_to(path)): digest(p) for p in sorted(path.rglob("*")) if p.is_file()}


def load_functions(name, namespace):
    path = UPSTREAM / f"{name}.py"
    assert digest(path) == EXPECTED[name]
    tree = ast.parse(path.read_bytes())
    kept = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES[name]]
    assert {node.name for node in kept} == NAMES[name]
    # Bodies and signatures are compiled unchanged; module imports/network paths are excluded.
    exec(compile(ast.Module(body=kept, type_ignores=[]), str(path), "exec"), namespace)
    return tree


def require_error(action, expected):
    try:
        action()
    except expected as error:
        return type(error).__name__
    raise AssertionError("expected rejection")


def main():
    namespace = {"np": np, "pd": pd, "random": random}
    trees = {name: load_functions(name, namespace) for name in NAMES}
    constants = {}
    for name, tree in trees.items():
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"JUDGE_SYSTEM", "SCORE_SYSTEM"}:
                        constants[target.id] = ast.literal_eval(node.value)
    assert constants["JUDGE_SYSTEM"] == PARTITION_SYSTEM
    assert constants["SCORE_SYSTEM"] == SCORE_SYSTEM

    cases = [
        list(range(10)),
        [0] * 10,
        [0, 1] * 5,
        [0, 0, 1, 1, 0, 2, 2, 1, 3, 3],
        [0, 1, 2, 3, 0, 3, 4, 4, 5, 5],
    ]
    rng = random.Random(20261020)
    cases += [namespace["canonical"]([rng.randrange(10) for _ in range(10)]) for _ in range(500)]
    probes = 0
    max_difference = 0.0
    for partition in cases:
        head_indices = namespace["heads"](partition)
        outputs = [SimpleNamespace(score=rng.randint(1, 10)) for _ in head_indices]
        instance = {"partition": partition, "generations": [str(i) for i in range(10)]}
        scores = namespace["spread"](instance, outputs)
        assert [i for i, score in enumerate(scores) if score is not None] == head_indices
        for patience in [0.0, 0.8, 1.0]:
            direct = namespace["utility_fields"](scores, partition, patience)
            local = score_sequence(partition, scores, patience=patience)
            difference = abs(float(direct["utility"]) - local.utility)
            max_difference = max(max_difference, difference)
            assert math.isclose(float(direct["utility"]), local.utility, rel_tol=1e-14, abs_tol=1e-14)
            assert direct["distinct"] == local.distinct
            assert direct["partition_scores"] == [scores[i] for i in head_indices]
            assert namespace["score_fold"](instance, outputs, {"patience": patience}) == direct
            probes += 1

    partition_probes = 0
    for prompt in ["A prompt", "A girl and her dog", "P<&>\n\u03bb"]:
        for seed in [None, 0, 7, 20261020]:
            for partition in cases:
                order = namespace["shuffled_order"](prompt, 10, seed)
                assert order == partition_order(prompt, 10, seed)
                groups = []
                for label in sorted(set(partition)):
                    groups.append([i for i, original in enumerate(order) if partition[original] == label])
                rng.shuffle(groups)
                instance = {"prompt": prompt, "generations": [str(i) for i in range(10)]}
                direct = namespace["partition_fold"](instance, [SimpleNamespace(groups=groups)], {"seed": seed})
                local = fold_partition(groups, prompt=prompt, n=10, seed=seed)
                assert direct["partition"] == local == partition
                assert direct["distinct"] == len(set(local))
                partition_probes += 1
    for prompt, answers in [("P<&>", ["A\nB", "[empty]", "[refused]"]), ("\u03bb", ["", "a\nb", "</response>"])]:
        assert render_responses(prompt, answers) == namespace["render_responses"](prompt, answers)

    rejections = {
        "empty_local": require_error(lambda: score_sequence([], [], expected_k=0), ValidationError),
        "empty_upstream": require_error(lambda: namespace["utility_fields"]([], [], 0.8), ZeroDivisionError),
        "zero_quality_local": require_error(lambda: score_sequence([0]*10, [0]+[None]*9), ValidationError),
        "zero_quality_upstream_spread": require_error(lambda: namespace["spread"]({"partition": [0]*10, "generations": [""]*10}, [SimpleNamespace(score=0)]), ValueError),
        "missing_head_local": require_error(lambda: score_sequence([0]*10, [None]*10), ValidationError),
        "missing_head_upstream_spread": require_error(lambda: namespace["spread"]({"partition": [0]*10, "generations": [""]*10}, []), ValueError),
    }
    refused = namespace["score_refused"]({"partition": [0, 0, 1, 1, 1, 1, 1, 1, 1, 1], "generations": [""]*10})
    assert refused["utility"] is None and refused["unscored"] == "judge_refusal"
    refusal_summary = namespace["summarize"](
        pd.DataFrame([{"utility": 8.0, "partition_scores": [9, 8]}, {"utility": None, "partition_scores": []}]),
        "1.1",
    )
    assert refusal_summary == {"version": "1.1", "mean_distinct": 2.0, "mean_utility": 8.0, "unscored": 1, "n_scored": 1}

    actual = []
    for run_name in ["first-live-recovery", "first-live-continuation-v2"]:
        directory = ROOT / "runs" / run_name
        before = inventory(directory)
        report = json.loads((directory / "report.json").read_bytes())
        for candidate in report["candidates"]:
            evaluation = directory / "candidates" / candidate["candidate_id"] / "evaluation"
            rows = [json.loads(line) for line in (evaluation / "v1.1/scores.jsonl").read_bytes().splitlines()]
            assert len(rows) == 1
            row = rows[0]
            direct = namespace["utility_fields"](row["generation_scores"], row["partition"], 0.8)
            local = score_sequence(row["partition"], row["generation_scores"])
            assert direct["distinct"] == row["distinct"] == candidate["mean_distinct"] == local.distinct
            assert direct["partition_scores"] == row["partition_scores"]
            assert math.isclose(float(direct["utility"]), row["utility"], rel_tol=1e-14, abs_tol=1e-14)
            assert math.isclose(float(direct["utility"]), candidate["mean_utility"], rel_tol=1e-14, abs_tol=1e-14)
            summary = json.loads((evaluation / "v1.1/summary.json").read_bytes())
            assert summary["mean_utility"] == row["utility"]
            direct_summary = namespace["summarize"](pd.DataFrame(rows), "1.1")
            assert math.isclose(float(direct_summary["mean_utility"]), summary["mean_utility"], rel_tol=1e-14, abs_tol=1e-14)
            assert direct_summary["mean_distinct"] == summary["mean_distinct"]
            protocol = EvaluationProtocol(**json.loads((evaluation / "provenance.json").read_bytes())["protocol"])
            unscored = row | {"utility": None, "unscored": "judge_refusal"}
            require_error(lambda: summarize_run({row["id"]: hashlib.sha256(row["prompt"].encode()).hexdigest()}, [unscored], protocol=protocol), ValidationError)
            actual.append({
                "run": run_name, "candidate_id": candidate["candidate_id"],
                "partition": row["partition"], "heads": namespace["heads"](row["partition"]),
                "generation_scores": row["generation_scores"], "distinct": row["distinct"],
                "saved_utility": row["utility"], "direct_upstream_utility": float(direct["utility"]),
                "local_utility": local.utility,
            })
        assert inventory(directory) == before

    result = {
        "format": "buddha.review.scoring-conformance.v1", "upstream_commit": PIN,
        "execution": "Direct unchanged selected upstream AST function bodies with actual installed NumPy; no CLI, provider calls, or run ZIP execution",
        "numpy_version": np.__version__, "pandas_version": pd.__version__, "upstream_sha256": EXPECTED,
        "source_functions": {name: sorted(names) for name, names in NAMES.items()},
        "prompt_bytes_equal": True, "utility_differential_cases": probes,
        "partition_differential_cases": partition_probes,
        "maximum_utility_floating_difference": max_difference,
        "rejection_probes": rejections, "upstream_refusal_shape": refused,
        "upstream_refusal_summary": refusal_summary, "local_refusal_behavior": "rejects incomplete evaluation rather than publishing survivor-only means",
        "actual_runs_unchanged": True, "actual_candidates": actual,
    }
    target = REVIEW / "noveltybench-scoring-conformance.json"
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"utility_cases": probes, "partition_cases": partition_probes, "max_floating_difference": max_difference, "actual_candidates": actual}, indent=2))


if __name__ == "__main__":
    main()
