# Limited validation rounds

Validation checks a frozen agent after development. Each look at validation results can influence later choices, so the number of checking rounds must be limited in advance. This controller records and consumes those rounds; having money left does not buy extra rounds.

This is an engineering component of EVAL-01. It collects generation and unchanged native benchmark evidence. It does not calculate confidence bounds, promote a champion, finalize an experiment or establish that an agent improved. Those parts of the [living plan](PLAN.md) remain open. No paid validation run or operator launch command is supplied by this slice.

Here, **native evaluation** means running the official evaluator's own code. An **owner** is the original accounting record for an execution stage. An **anchor** links a saved completion to that record and its exact inputs. The round's **ordinal** is its number, starting at zero.

## What one round does

Before generation begins, an original declaration fixes the task population, comparison agents, generation resources, benchmark configuration, repetitions and maximum number of rounds. The caller supplies candidate Python files as data; the controller copies their exact bytes and uses the existing isolated candidate executor. It never imports or executes candidate code on the host.

Every candidate and fixed comparison agent receives the same selected tasks and number of repetitions. A repetition means a complete answer set for a task. Comparison agents generate fresh answers in each round. A candidate may deliberately have the same source as a comparison agent: this is a useful control, and the two roles still receive separate fresh executions.

For every successful generation, the controller passes the anchored saved answers to the existing native evaluator. It preserves the evaluator's output and its original financial owners. A failed generation has no fabricated answers, native score or zero substituted for it.

The prospective limits are explicit inputs, with no scientific defaults:

| Input | Meaning |
| --- | --- |
| `max_candidates` (`C`) | Maximum candidate agents in one round; fixed comparison agents are additional. |
| Comparison agents (`M`) | The fixed, nonempty ordered comparison population. |
| `max_looks` (`L`) | Maximum reserved rounds in this study. |
| `repetitions` (`R`) | Fresh complete answer sets per selected task and agent. |

A round with `C_actual` candidates and `T` selected tasks requires `(C_actual + M) × T × R` generation/evaluation cells. It represents every candidate against every fixed comparison agent. Across the study there are at most `L × C × M` contrasts and twice that many declared utility/distinctiveness bound allocations. This slice records those limits; it does not construct the bounds.

## What is frozen

The declaration binds exact task, custody, analysis-plan, improvement-rule and comparison-source files. It fixes the generation model, instructions, sampling mode, callback/output allowances, executor and resource ceilings. Only each arm's candidate source and its corresponding source directory/mount change. Native assessment settings stay unchanged.

The existing [improvement rule](EVALUATION-RULE.md) must parse before preparation. Its original external bytes and the copied canonical rule remain separate recorded identities. A pinned analysis-plan file records what was supplied; its hash does not certify a sound statistical method.

`prepare_validation_study(...)` checks the inputs and copies the original controls. It needs an independently supplied approved runtime hash; a runtime description cannot approve itself. Preparation creates no financial grant, owner, worker or API call.

The copied declaration is canonical JSON. Its hash defines the authorization scope, `validation study: <canonical declaration SHA256>`. The external declaration's raw-file hash is recorded separately and can differ when its formatting differs. One original authorization funds this version of a study; switching grants cannot reset the round limit.

`run_validation_occasion(...)` is the active library operation. It takes an ordinal, ordered candidate references, the original authorization and review, and a transport. Running it can spend money through the existing bounded gateway. There is no validation CLI in this slice.

## Task custody and its limits

The trusted host checks the complete source task artifact, rather than accepting a selected subset as the whole population. Custody metadata must cover every typed task ID and its content hash. Integer `1` and string `"1"` are different IDs. Declared prompt families and normalized exact duplicate prompts cannot cross development, validation, final and transfer phases.

Selected validation tasks must be declared eligible and undisclosed to the named optimization process. Exposed and unknown members are rejected. The controller records the custodian, basis, evidence references and disclosures; it cannot independently prove those statements or discover undisclosed human exposure. It does not infer semantic near-duplicate families from text. Public benchmark membership cannot prove that a base model never saw a task during training.

The host can read the complete sealed source for verification. The candidate's channel receives only its current task. This is process separation, not encryption of the source from the trusted operator.

## Completion, interruption and recovery

The study lock serializes active work. A round directory consumes its ordinal before task projection or nested preparation. After the original `occasion.json` has been synchronized and reread successfully, the controller creates a separate immutable `reservation.json` receipt. Readable occasion text alone cannot prove that this confirmation succeeded. Missing, truncated or conflicting original reservation evidence stays poisoned: the controller does not quietly reconstruct it and reclaim the round.

Before reserving a new round, the controller also counts the files that generation and every native stage will need. A schedule that would exceed the existing 1,024-input-path limit is rejected before consuming a round. This checks the current file interface; it does not predict token use, output size, runtime or scientific usefulness.

Generation and every native owner consume the original study, rule, custody, analysis and occasion controls. Existing owners retain their identities and accounting. A known saved reply is reused by the same original owner without another request or charge. An unknown request retains its possible bill and stops dependent work; elapsed time is not permission to replace it.

A first timeout can be recorded as `unknown`, while a later blocked continuation says `authority`: the spending guard refused another dispatch because the earlier request remains unresolved. The original unknown record and held amount remain intact.

A new round requires earlier rounds to be complete or to contain a verified terminal source-execution failure. An ordinary unfinished round must be recovered at its original ordinal, even if it made no API calls. New funding cannot bypass it.

Incomplete records retain the reason, stage, agent/task/repetition position, anchored child evidence, completed and missing coverage, and observed financial state. Later success does not overwrite earlier partial observations. A clean candidate-execution failure is an explicit terminal incomplete result, with no native assessment for that cell. A different source can be considered only in another permitted round.

A complete result requires every expected generation/native cell. Here, **complete means the declared measurements were collected**, not that the candidate is better or that the numerical metrics passed a scientific comparison. Identical completed replay verifies saved evidence and returns the original result without new workers, model requests or financial owners.

The file journal uses exclusive creation and file synchronization. Its scope is process interruption and detectable retained corruption. It does not establish tested power-loss durability, prevent a trusted operator from rolling back/deleting the whole study, or provide a global registry of out-of-controller peeking. Final populations, finalist counts, uncertainty/error allocation and one-way finalization must be frozen by the complete controller before its own observations; this partial component cannot acquire those claims retroactively.

## Offline engineering check

From the checkout containing this slice:

```powershell
python -m unittest discover -s tests -p test_validation_study.py -v
```

This runs the focused validation tests once and exits. It uses temporary files/databases, synthetic tasks and simulated worker/API replies; it spends no API money and needs no keys or separate window. It does not run a real benchmark experiment or Docker worker. Press Ctrl+C to stop the check. Passing these tests is bounded engineering evidence, not evidence of scientific improvement.

## Recorded engineering evidence

The [slice delivery](conformance/eval01-validation-study-delivery.json) records the exact code/test cut, 19 passing focused methods, seven passing quality checks and independent static review. One four-cell synthetic fixture checks the actual input-path sets of all 16 original owners. Boundary tests separately reject a schedule whose generation fits but later native inputs exceed the limit, and permit preparation when the largest native set is exactly 1,024. They do not execute a complete near-limit worker. Recovery controls preserve saved replies without rebilling and retain unknown liabilities and historical partials. No real provider call or held-out task was used; hosted full-suite CI is reported separately.
