# Slice 3: bounded policy optimization

This records the original offline checkpoint; costs and pending checks below describe that historical state. The [CLI progress follow-up](CLI-PROGRESS.md) records the first interruption and the added observation tools. The subsequent recovery pilot is now complete; see [verified results](FIRST-LIVE-RESULTS.md). [PLAN.md](PLAN.md) owns the consolidated current status and next slice.

Implementation date: October 19, 2026. The latest official NoveltyBench code, metric v1.1 at commit `64a23be6b18ec1dacc298830aab276061b6e143c`, remains normative. This slice implements a fixed proposer that changes declarative generation policies. It does not execute generated Python, evolve the improver, establish held-out gains, or reproduce Novamine's results. No paid call has occurred.

## Implemented behavior

A search freezes verified source bytes, a complete development/validation/final ID partition, model/rate/limit settings, common development screen, parent-selection seed and method, proposer prompt/schema, and critical implementation hashes. Every candidate is evaluated on the same development IDs. The fixed proposer uses the configured generation model. It can change only:

```json
{"instructions": "At most 4000 characters of generation instructions", "sampling": "regenerate"}
```

The second permitted sampling value is `in-context`. Unknown properties, invalid UTF-8, wrong types and longer policies are rejected. A policy has no tools, model selection, filesystem access or executable code. Instruction text can still attempt to influence model behavior or exploit a judge; schema validation is not a semantic safety guarantee or a prompt-injection defense.

The two initial seeds have empty instructions: ten independent samples (`regenerate`) and upstream-style in-context regeneration. In-context turns preserve the original task, then alternate the previous normalized answer with the exact continuation `Can you generate a different answer?`. Empty/refused answers use the same placeholder strings as upstream. Anthropic requests retain the last-user cache marker. Model access, reasoning/output limits and judging remain fixed; in-context sampling can use more input tokens, so equal ceilings are not equal realized spending.

After both seeds complete, each declared iteration selects a parent, makes one structured proposal, validates it and evaluates a unique valid child. Completed invalid/refused/truncated proposals and duplicate policies consume an iteration and remain in the ledger/decision history. Duplicates are not re-evaluated. Instrument, provider or budget failures stop the entire search; an incomplete candidate cannot be admitted or silently dropped to flatter the archive.

| Method | Parent and feedback |
| --- | --- |
| `archive` | Bounded Pareto parent pool; selected parent's common-development evidence |
| `latest` | Most recently admitted candidate; its common-development evidence |
| `uninformed` | Fixed first independent-sampling seed; no scores, examples or other evaluation feedback |

The uninformed condition is a no-feedback proposer baseline, not uniform random sampling over language or policies. These modes are implemented comparisons; no paid ablation experiment has been conducted. Preparing three separate method directories would create three separate spending caps and is outside the one approved first run.

Archive selection maximizes mean utility and distinctiveness separately. The pool retains a crowding-limited nondominated frontier and up to `floor(max_active/5)` dominated candidates. Crowding preserves both objective maxima when they differ. Dominated reserve priority favors fewer direct children, then utility, distinctiveness and ID. Archive parent selection has a 10% uniform exploration branch; otherwise weights are `(2 if frontier else 1)/(1 + direct child count)`. A local seeded RNG and deterministic ties make reconstruction stable. These are allocation heuristics, not semantic novelty measurements or statistically confirmed promotion rules.

## Data and provenance boundaries

Splits group normalized exact duplicates (`whitespace normalization + casefold`) and optional caller-declared families transitively, then allocate approximately 60/20/20 by group count. All three partitions must be nonempty and cover every source ID once. Groups stay together. This does not detect semantic near-duplicates or implement source/task stratification. One source is used per experiment. The common screen takes the first sorted development IDs; a one-prompt screen is an engineering check, not a representative sample.

The host stores the full public source snapshot and all split IDs. The pipeline passes only checked common-development rows to the proposer. Held-out prompts, IDs, split metadata and results are excluded from every proposer packet. This is a controller data-flow boundary, not isolation from the human operator, public benchmark contamination or prior model training.

Feedback is capped at **200,000 canonical serialized JSON bytes**. It is not silently truncated or summarized. Long valid outputs or a large screen can exceed that ceiling after seed evaluation, stopping before a proposer call while retaining the charged seed evidence. Scaling requires a separately specified, frozen feedback-extraction rule.

Candidate IDs hash their exact policy. Each evaluation protocol additionally binds effective generation configuration, source/screen, fixed judges/prompts and implementation template. The comparison key excludes the candidate policy and method but binds shared instrument, population, resource controls and implementation. This allows declared policy interventions while preventing reuse of another candidate's paid responses. Provider operation IDs include run, candidate or proposal occasion, task, stage and answer index.

Every admitted candidate passes complete generation, partitioning, class-head scoring, official v1.1 arithmetic, export and local re-import. The importer verifies full common-screen coverage and cross-stage consistency. Checksums establish local consistency rather than origin authentication or official certification. The normative benchmark protocol and local bounded-execution differences remain documented in [the slice 2 notes](SLICE2-BENCHMARK-NOTES.md).

## Files and recovery

| File | Contract implemented |
| --- | --- |
| `buddha/policy.py` | Validated immutable policy and fixed, bounded structured proposer |
| `buddha/splits.py` | Deterministic group assignment and complete split validation |
| `buddha/archive.py` | Pareto/crowding/reserve allocation and deterministic parent selection |
| `buddha/run.py` | Shared v1.1 evaluation path, exact generation-model guard and candidate-aware operation namespaces |
| `buddha/search.py` | Frozen experiment, shared ledger, guarded proposal/evaluation loop and cached reconstruction |
| `buddha/__main__.py` | Search preparation/demo/run/inspection and hidden local credential entry |
| `tests/test_policy.py`, `test_splits.py`, `test_archive.py`, `test_search.py` | Runnable component, composed, leakage, budget and recovery regressions |
| `tests/test_run.py`, `test_cli.py` | Existing baseline compatibility, generation-boundary and credential regressions |

The source snapshot and manifest sit beside **one** `operations.sqlite3` for all stages. `candidates/<policy-hash>/` contains immutable policy and complete upstream-compatible evaluation files. `decisions/` preserves seed admissions and completed iteration outcomes; `report.json` records the exploratory archive and spending breakdown after all declared iterations complete. Partial work remains in durable receipts and candidate policy files even when no final report exists.

Writes use fsynced temporary files and exclusive hard-link publication, with equality checks on replay and no replacement of conflicting evidence. A cooperating `.search.lock` prevents simultaneous controllers. Offline `search-inspect` reconstructs from completed receipts and can restore derived artifacts; it neither reserves missing work nor contacts providers. It is therefore not a byte-preserving forensic reader. Unknown operations remain incomplete and retain reservations.

After abrupt process termination, review a stale `.search.lock` only after proving that no writer is active. An abrupt export can similarly leave its own sibling lock as described in [slice 2 recovery](SLICE2.md#accounting-and-recovery). Temp-only candidate directories from interrupted publication are nonauthoritative; recovery can recreate the expected policy without deleting the orphan temp files. Do not delete or edit SQLite records to clear a failure. Changed frozen implementation bytes require the original matching checkout for replay; do not bypass the source-hash check.

## First live experiment and keys

The user approved **up to $50 total** for one first live experiment. The prepared run `runs/first-live-search` freezes one common development prompt, two seed evaluations, one proposal occasion, at most one unique child evaluation, archive capacity eight, seed seven and a 128-call allowance. The maximum planned call count is 64: three candidate screens at up to 21 calls each, plus one proposal. The actual number of class-head judgments and costs depends on the answers. There is no final/validation evaluation, extra comparator run or leaderboard submission in this budget.

Preparation uses public data and no model requests:

```powershell
python -m buddha check-upstream
python -m buddha fetch --dataset curated --out runs/datasets/curated.jsonl
python -m buddha search-prepare --dataset curated --data runs/datasets/curated.jsonl --config examples/live-config.json --budget-usd 50 --iterations 1 --screen-size 1 --seed 7 --out runs/first-live-search
python -m buddha search-inspect --run runs/first-live-search
```

Preparation refuses an existing directory; use the already prepared one rather than creating additional paid runs. A dollar cap does not guarantee completion: whole-context reservations, unknown outcomes or instrument errors can stop work early. Recorded usage charges are conservative maximum-rate calculations, not invoices. Rates/context limits must have been verified within seven days. The [historical baseline estimates](SLICE2.md#cost-planning) exclude search and should not be treated as this experiment's measured cost.

Enter your OpenAI and Anthropic keys locally at hidden prompts:

```powershell
python -m buddha search-run --run runs/first-live-search --live --prompt-keys
```

See [API-KEYS.md](API-KEYS.md) for creation, process-local environment handling, provider controls and rotation. Keys must not be pasted into chat. A provider timeout never authorizes an automatic retry or a fresh run under another ID.

## Verification and checkpoint

All model transports used during verification were canned or mocked; no live quality score or optimization gain is claimed. New component and composed checks were observed failing before implementation. Review also reproduced and corrected a generation-model provenance mismatch, delayed malformed-Unicode rejection and incorrect in-context empty/refusal history.

| Check | Observed result |
| --- | --- |
| Complete unit, CLI, concurrency, boundary and fault suite | **207 passed** |
| Ruff lint and formatting | Passed across all 21 Python files |
| Strict mypy | Passed across all 11 runtime modules |
| Bandit | No issues; two narrow non-security RNG suppressions for protocol shuffling and parent allocation |
| Runtime dependency audit | No known vulnerabilities; runtime remains standard-library-only |
| Python compilation | Passed |
| Latest upstream check | Pinned v1.1 commit still matches current HEAD |
| Persisted search demo, repeated | Four candidates, two proposal decisions, 98 operations; identical report on resume |
| Old persisted slice 2 artifact verification | Passed after shared evaluator refactor |
| First live preparation and offline inspection | $50 frozen, `curated-0` development screen; zero operations/spending/reservations |
| Real API/judge validation | Pending local credentials; not run |

The synthetic demo at `runs/slice3-demo` records 1,470 micro-USD of simulated charges from canned usage, not paid expenditure. Interruption tests after a proposal receipt and during child generation recover without duplicate calls. Dummy-key sentinel checks cover request bodies, stdout, manifests, SQLite and exports; network/error tests cover header-only credentials and sanitized errors. Held-out canaries are absent from every proposer request. An independent delegated review found no blocking issue after the fixes; that review does not establish external judge validity or sandbox readiness.

The prepared live manifest is `runs/first-live-search/manifest.json`, run ID `a1257f96467b490b910b559437a71258`. No third-party runtime dependency, generated-source executor, Git commit, hosted CI, deployment or submission was added. This workspace has no Git repository/remote, so verification is local.

This slice stops at the required check-in. The capped live pilot is pending user-supplied credentials. Genuine source self-modification, isolated execution, finalization/validation controllers, independent judgment/human audits and scientific improvement claims remain later work. The original full-agent objective is not complete.
