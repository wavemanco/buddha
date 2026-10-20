# NoveltyBench 1.1 conformance audit

October 20, 2026. NB-01 in the [living plan](PLAN.md). The official benchmark remains the yardstick. This report audits its implementation; it does not introduce a replacement diversity measure.

**Verdict: the ordinary successful scoring path matches the pinned official functions. Full native execution parity is not established and is contradicted by the explicit differences below.** Calling our historical bounded adapter an exact upstream implementation would overstate the evidence. Its recorded results remain unchanged and retain their original configuration.

The current official HEAD was checked again and remains [`64a23be6b18ec1dacc298830aab276061b6e143c`](https://github.com/novelty-bench/novelty-bench/tree/64a23be6b18ec1dacc298830aab276061b6e143c), metric 1.1. This source, its [README](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/README.md) and the [submission instructions](https://novelty-bench.github.io/submit.html) govern new work. The original paper is historical context. No model calls or API keys were used in this audit.

## NB-C1: successful calculations and requests conform within the declared profile

Direct comparisons executed selected unchanged functions from downloaded, hash-verified official source. They used actual NumPy/Pandas for numerical comparisons and actual installed Pydantic/OpenAI schema conversion for request comparisons. They did not substitute a homemade numerical oracle, execute supplied run archives, instantiate paid clients, or run the upstream CLI. Fake clients and immediate fixture coroutines tested request construction without testing real concurrency.

| Check | Evidence |
| --- | --- |
| Both complete judge instruction strings | Byte-identical to official source |
| Partition display and inverse mapping | 6,060 differential cases, including Unicode, original-order restoration and four ordering seeds |
| Head selection, duplicate zero credit, all-position denominator and geometric weighting | 1,515 differential cases at patience 0, 0.8 and 1; maximum observed difference `8.88e-16` |
| Both completed pilots | All six candidate metrics and summaries reproduced by official functions, within ordinary floating precision |
| Recorded operation reconstruction | All 114 completed physical requests: 63 fresh-recovery and 51 continuation; nine inherited replies checked separately |
| Six partition requests | Exact task, full ordered answers, official system text and closed structured-output schema; cap/tier differences below |
| Fifty-five quality requests | Exact original class head, full answer, official system text, high/adaptive effort and schema; tier difference below |
| Generation | Both independent and in-context request histories match explicit upstream 2048/low configuration, apart from tier and disclosed candidate instructions |
| Official datasets | Fresh downloads match both pinned hashes: 100 curated and 1,000 WildChat prompts with unique IDs |

The upstream executable scores **class heads**, despite a stale opening comment in `score.py` saying otherwise. We follow the executable function. Actual partition seeds were null, preserving generation order. Quality judges see the original prompt and one original response, without the policy, siblings, source, review feedback or an additional novelty rubric. [Official partition functions](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/partition.py), [head scoring and utility](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/score.py).

| Run | Candidate prefix | Distinct | Saved utility |
| --- | --- | ---: | ---: |
| Fresh recovery | `2cad4fc7` | 9 | 7.183934838498671 |
| Fresh recovery | `68608e69` | 10 | 7.480236373570919 |
| Fresh recovery | `34cecdbd` | 10 | 8.5672732825065 |
| Linked continuation | `2cad4fc7` | 6 | 5.304218778625656 |
| Linked continuation | `68608e69` | 10 | 7.117946910703382 |
| Linked continuation | `12a952c2` | 10 | 8.252794839170917 |

The ten-distinct counts come from the stored judge's ten singleton groups. They are not produced by a local lexical-difference rule or an arithmetic/mapping error. This does not prove that the judge understood the plots correctly.

## NB-C2: a reproduced provenance defect is fixed

Adversarial temporary exports showed that supplied conflicting generation, partition and quality settings could be overwritten by the declared settings without rejection. Fallback metadata could also be discarded on export or accepted in rehashed imports despite the local adapter supporting no fallback. This could misdescribe an externally supplied row's judging history. It is an integrity defect, not evidence that another judge was used in the pilots.

The shared validator now checks supplied configurations before serialization and rejects `fallback_judge`, `fallback_calls` or `unscored` outcome markers in every imported stage. Matching optional configurations still round-trip. Invalid inputs fail before publication; rejected imports preserve all input bytes. Hashes alone cannot make contradictory evidence acceptable.

Four acceptance tests with adversarial subcases were added after observing 13 failing assertions against the original implementation. They now pass. Existing tests continue to reject incomplete coverage, malformed/duplicate/out-of-range groups, forged cross-stage evidence, missing class-head scores, invalid score types and inconsistent arithmetic. There is no new scoring heuristic.

Historical source compatibility remains bounded. `continuation._science` permits one explicit reviewed old/new `benchmark.py` hash pair for this validation-only tightening:

- Before: `9e131a9f4fd92197b256518ea778984875d9aee2a58efb3ccc759d6553a79ae2`
- After: `15b57b974c702d69c7b9e172c73798bd555db5eedb3286bd8c792d1fe0568763`

Other core modules still require exact bytes. An additional unreviewed benchmark revision and the reversed pair are rejected. Frozen/current executable comparisons still match valid request/scoring/archive behavior. This exception permits reading the reviewed original source; it does not bypass a saved run's runtime binding or alter a frozen ZIP, manifest, receipt or result.

## NB-C3: request and execution differences remain open

| Boundary | Pinned official behavior | Historical local adapter |
| --- | --- | --- |
| Partition output allowance | OpenAI judge request omits an explicit cap | Adds `max_completion_tokens=16000` |
| Service tier | Judge/generation helpers omit a tier | Explicit OpenAI `default` / Anthropic `standard_only` |
| Provider retry | Judge client sets SDK retries to eight | One physical attempt; uncertain operation remains held |
| Invalid partition fold | Shared stage retries fold errors three times, then can repair omitted members into singleton groups | Stops incomplete; no repair |
| Judge refusal/fallback | Configurable fallback; score CLI default is Sonnet; generic score stage can produce an unscored row | Stops incomplete, no automatic fallback |
| Summary with unscored rows | Official summarizer excludes those rows from both means and reports counts | Requires complete declared coverage before a complete local result |

All six recorded partition receipts ended normally; all 55 quality receipts ended with `end_turn`; none was marked refused. Maximum recorded output was 549 partition tokens and 245 quality tokens, below the 16,000 caps. No observed truncation or malformed/refused stored judgment explains the suspicious singleton labels. This is not a counterfactual proof that omitted caps or tiers would yield identical stochastic judgments. [Official request and recovery implementation](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/judge.py), [official summary](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/summarize.py).

Upstream has more than one execution path. Its live score CLI calls `score_llm()` directly; it does not necessarily reach the generic Stage refusal callback. Likewise, the shared bare CLI judge default is Opus, while the README describes Luna partitioning and published reference configurations explicitly select it. Our Luna/Opus choice is an explicit reference profile, not the result of running bare CLI defaults. Submission generation specifies ten answers at 2048/low; inference's bare CLI still defaults to 512/no effort. These distinctions must remain visible when freezing the exact path.

NB-02 must align the selected upstream path without sacrificing the hard spending cap. An omitted output cap requires reserving against the verified provider maximum. Every potentially billed retry/fallback requires separately recorded liability and authority. An unknown attempt cannot be declared free to imitate upstream retry behavior. If a prescribed operation cannot be bounded safely, stop and disclose the limitation; do not quietly change its prompt or score.

## NB-C4: parser differences are reproduced

Upstream's installed Pydantic parsing accepts some score strings, booleans, integral floats, extra keys and repeated keys; the local JSON/type checks reject them. The Anthropic judge parser reads the first text block, while our shared transport concatenates text blocks for generation and judging. A first valid JSON score followed by another text block therefore passes upstream and fails locally. These differences concern acceptance and recovery, even when ordinary valid scores match. They belong in NB-02.

Raw provider content-block boundaries were not retained in the historical replies. We can reparse their saved text, but cannot retrospectively prove single-block delivery. Request fingerprints are reconstructed local evidence, not independently authenticated wire captures. Installed SDK versions used for this audit are not an attestation of the exact historical upstream dependency environment.

## NB-C5: judge semantic accuracy is not yet established

The official equivalence rule already groups answers that repeat their central content with only minor variations. It therefore already addresses the central-plot concern; we must not redefine distinctiveness to repair these results. Shared required characters alone are legitimate. The continuation's blocked-water-source stories, especially C7/C10 in the content review, are candidates for checking the official rule's application, not adjudicated proof of a different true count.

Next live semantic controls should include exact duplicate answers, paraphrased central plots, genuine different outcomes, required-commonality controls and closed-answer prompts. Freeze expected labels through independent review before judging. Preserve the complete set, order, every judge receipt and any disagreement. Blinded reassessment and order sensitivity must be reported separately from the original benchmark result; they cannot silently overwrite it. No live semantic adversarial judging occurred in this offline audit.

## NB-C6: measurement limits stay explicit

Both implementations place raw answer text inside XML-like delimiters without escaping it. Literal delimiter/instruction-like content is preserved in offline rendering checks. This establishes faithful construction, not resistance to prompt injection by the judge. Such controls require live measurement under the unchanged official prompt; adding a private wrapper would change the instrument.

One development prompt, three candidates per run and a single proposal are not a full 1,100-prompt benchmark result, a leaderboard comparison or independent semantic calibration. The related broader-premise concentration diagnostic remains supplemental. No corrected ranking, historical originality claim or official certification follows from this audit.

## Evidence and reproduction

Committed machine evidence and preserved probes:

- [Scoring evidence](conformance/noveltybench-scoring-conformance.json) and [probe](conformance/noveltybench-scoring-probe.py).
- [Request/failure evidence](conformance/noveltybench-request-conformance.json) and [probe](conformance/noveltybench-request-conformance.py).
- [Dataset seals](conformance/noveltybench-dataset-seals.json); upstream source hashes are also recorded in request evidence.
- [Preservation and local checks](conformance/nb01-preservation.json): all 287 protected historical/authority input files retained their exact hashes.

Run the local artifact-boundary checks once from the repository folder. They use temporary fixtures, need no keys/network, spend nothing and can run in the existing PowerShell window:

```powershell
python -m unittest discover -s tests -p test_benchmark.py
python -m unittest discover -s tests -p test_continuation_source.py
python -m unittest discover -s tests -p test_continuation_science.py
```

The first checks import/export integrity and benchmark helpers. The second checks source/receipt compatibility and source-drift rejection. The third compares fixed archived and current valid request/scoring/archive behavior in isolated processes; it does not rejudge stories.

Optional historical research probes run once, spend nothing and request no keys. They read the original ignored pilot files and hash-verified public source under `runs/references/noveltybench-conformance/<commit>/`; they write review JSON under `runs/reviews/`. Use the same window. They need the locally installed research libraries used above: NumPy 2.3.5/Pandas 3.0.0 for scoring, Pydantic 2.12.5/OpenAI 2.33.0 for request/schema checks. They are not application dependencies or part of normal CI, and require those local evidence files rather than a clean repository alone.

```powershell
python docs/conformance/noveltybench-scoring-probe.py
python docs/conformance/noveltybench-request-conformance.py
```

The first executes selected official numerical functions against local results. The second reconstructs recorded requests and exercises canned parser/recovery cases with real network dispatch blocked. They do not run the paid upstream judging commands. Source files are downloaded from the exact commit, and the request probe also requires its `download-seals.json` hash inventory; no arbitrary supplied ZIP is executed.

Local verification passed 387 tests in 106.404 seconds, with one Windows symlink-privilege skip; Ruff lint/format, strict mypy, Bandit, runtime dependency audit, compilation and whitespace checks passed. The source-compatibility and provenance fixes are covered by runnable regression checks; hosted CI is reported separately after publication. Broader native-profile alignment remains NB-02 in the living plan; calibration remains MEAS-01/02. These gates are deliberately open.

BENCH-01 passed hosted Windows and Ubuntu checks at [commit 55afd62](https://github.com/wavemanco/buddha/actions/runs/39421695770). The subsequent [BENCH-02A reference profile](BENCHMARK-REFERENCE-PROFILE.md) repeats the checks with upstream-locked dependencies and captures actual SDK JSON, including OpenAI stream=false. The earlier request-kwargs comparison alone did not establish that serialization detail. BENCH-02B/C remain open.
