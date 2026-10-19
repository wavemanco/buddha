# Slice 1 verification record

Verified October 18, 2026, in `C:\Users\arvik\code\buddha` on Windows, Python 3.13.12. The starting directory had no repository files or Git metadata. No upstream project was installed as a dependency; research snapshots were read separately from temporary directories.

## Local acceptance checks

The acceptance suite was written before production code. Its initial run failed with `ModuleNotFoundError: No module named 'buddha'`. After implementing the kernel, 28 original tests passed; four additional checks cover pinned published vectors, malformed containers, and invalid UTF-8 prompt input. The final suite has **32 passing test methods**, with additional malformed-input combinations exercised as subtests.

| Command | Result | Tool version |
| --- | --- | --- |
| `python -m unittest discover -s tests -v` | 32 passed | Python 3.13.12 standard library |
| `python -m ruff check buddha tests` | Passed | Ruff 0.15.12 |
| `python -m ruff format --check buddha tests` | Passed | Ruff 0.15.12 |
| `python -m mypy --strict buddha` | Passed, 2 source files | mypy 2.1.0 |
| `python -m bandit -r buddha` | No issues; no suppressed checks | Bandit 1.9.4 |
| `python -m pip_audit --no-deps -r requirements.txt` | No known vulnerabilities found | pip-audit 2.10.1 |
| `python -m compileall -q buddha tests` | Passed | Python 3.13.12 |

The requirements file contains no third-party runtime dependencies. The dependency audit therefore says nothing about the host's unrelated installed packages, future provider SDKs, official evaluator dependencies, or a future container image. No hosted CI ran because no Git repository or CI configuration existed.

## Published-artifact arithmetic conformance

Downloaded saved official Novamine v1.1 score records at NoveltyBench commit `64a23be6b18ec1dacc298830aab276061b6e143c`. Recomputed each scored row with `score_sequence(partition, generation_scores)`, checked distinctness against the number of saved partition scores, and checked utility with both relative and absolute tolerance `1e-12`. No prompts were generated and no judge/model API was invoked.

| Artifact | Rows | Scored | Unscored | Recomputed mean distinct | Recomputed mean utility |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Curated](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/evaluation/2026-08-19_novamine-ai/nb-curated/v1.1/scores.jsonl) | 100 | 100 | 0 | 9.9 | 7.791406025135342 |
| [WildChat](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/evaluation/2026-08-19_novamine-ai/nb-wildchat/v1.1/scores.jsonl) | 1000 | 999 | 1 | 9.243243243243244 | 6.537160463257586 |

All **1,099 scored rows** matched. Means match saved summaries within floating-point rounding. The WildChat missing row remains visible here; its omission is not accepted as complete evidence by `summarize_run`.

Source file byte hashes:

- Curated `scores.jsonl`: `1c9583c7d7a52fbc7008934174b4b34bf6cee2f3f2fa1cb46243fa9978974e28`.
- WildChat `scores.jsonl`: `5c1b6abe28e9e5d645607f743037c53a4fc4c5e79f203d21173c8063ab8c6b1c`.

Three minimal numeric Curated vectors, with source URL and full source-file hash, are retained in `tests/fixtures/published_metrics.json` for offline regression checks. They contain labels and numeric scores, not full generated responses. Independent hand-derived edge cases remain in the tests; published vectors are additional conformance evidence.

A separate reviewer independently checked the 100 Curated rows using the same kernel and found no mismatch. This is independent verification of the arithmetic procedure, not independent evaluation of the agent or semantics.

Dataset Git-blob bytes and the evaluated `JUDGE_SYSTEM`/`SCORE_SYSTEM` string hashes were independently checked against the table in [NOVELTYBENCH.md](NOVELTYBENCH.md). No judge source was executed to extract those strings; Python AST parsing and literal evaluation were used.

## Design review and practical limits

An independent review found no blocking first-slice metric or ordinary JSON-input validation issue. One distinction was clarified: full provenance fingerprints differ across candidate policies, while fair comparisons share fixed measurement and resource controls. Matching one's own manifest is not the same as demanding identical candidate policies.

Docker reported a Linux server, version 29.5.3. No sandbox adversarial or runtime test has been run. Availability does not establish filesystem, network, credential, resource, or evaluator isolation.

This slice verifies a small offline library. It does not verify semantic partition correctness, quality-judge validity, artifact authenticity, provider costs, retry/resume behavior, sealed-split enforcement, archive search, source execution, genuine self-modification, improvement competence, or any gain over a baseline. Those have explicit acceptance gates in [DESIGN.md](DESIGN.md).
