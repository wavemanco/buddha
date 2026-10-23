# First model-authored Python evolution: results

The approved source experiment completed on October 22, 2026. Buddha produced and executed three successive model-written Python descendants. An evolved improvement function also ran and produced a further child. **The mechanism worked in this observed chain; the scores did not improve.** The starter scored higher than every child on both average official utility and distinctiveness.

No further command is needed from the user now. Keep the original run and runtime intact; do not repeat the historical launch command. The [living plan](PLAN.md) owns the next work and the [machine-readable evidence](conformance/src02-live-results.json) records exact identities, measurements and review limits.

## What actually ran

The frozen [protocol](SOURCE-EXPERIMENT.md) used unchanged NoveltyBench 1.1, three development tasks and three proposal iterations. Each source produced ten answers per task, followed by the official partition, quality-score and summary commands. There were four sources, twelve complete answer sets and 120 answers in total.

The lineage was starter → first child → second child → third child. Every proposal request contained its immediate parent's full Python file and the three ordered development notes. The saved model reply's source text exactly matches the corresponding materialized child. Each child subsequently generated answers in the restricted source runtime. These are actual model replies, unlike the supplied programs and simulated replies used in the earlier rehearsal.

The declared search method was `latest`: each eligible new child became the next parent. **Eligible** means its common development screen completed with usable measurements. It does not mean better. The last child is therefore the report's selected source, while the starter is the only source on its numerical frontier: no child exceeds the starter on either average metric.

## Official results

Each mean below gives the three tasks equal weight. Values are rounded here; the evidence file preserves the saved precision. Distinctiveness is the number of official answer groups among ten answers. Utility is NoveltyBench's separate usefulness-and-diversity measure, calculated by its official implementation; it is not just an average writing-quality rating.

| Source | Mean utility | Mean distinctiveness | Generation calls across three tasks |
| --- | ---: | ---: | ---: |
| Starter | 5.9172 | 7.3333 | 30 |
| First child | 5.2022 | 5.6667 | 33 |
| Second child | 4.1324 | 5.6667 | 6 |
| Third child | 5.0455 | 7.0000 | 9 |

| Task | Starter U / D | First child U / D | Second child U / D | Third child U / D |
| --- | ---: | ---: | ---: | ---: |
| Five-sentence girl-and-dog story (`curated-0`) | 7.6972 / 10 | 6.8641 / 10 | 6.5896 / 10 | 6.4608 / 10 |
| Choose glass half full or half empty (`curated-47`) | 2.7962 / 2 | 3.0472 / 2 | 3.2264 / 2 | 2.9396 / 2 |
| Exactly one password digit (`curated-97`) | 7.2582 / 10 | 5.6952 / 5 | 2.5811 / 5 | 5.7361 / 9 |

All glass answers were permitted choices and all digit answers were exactly one ASCII digit. All forty stories had five sentence endings in the mechanical check; the reviewer also read their full text. Those checks do not establish overall literary quality or correctness. Glass distinctiveness of two is the ceiling when following the task's two legal choices. Repetition is unavoidable there; inventing extra choices would break the task.

This is a negative development-score observation, not a controlled causal estimate that changing code makes performance worse. There was one generation/evaluation occasion per source, three already exposed diagnostic tasks, changing procedures and different actual inference usage. No held-out tasks, repeated fixed-source comparison, human evaluation, significance test or leaderboard comparison ran.

## What changed in the Python

| Child | Observed generation change | Inherited improvement procedure |
| --- | --- | --- |
| First | Plans answer briefs once, then realizes ten answers separately: eleven calls per task here. | Rewrites the actual `propose_improvement` function; this changed function later produces the second child. |
| Second | Produces batches of complete answers: two calls per task here. | Retains that function text and changes its proposal-prompt constant; this source later produces the third child. |
| Third | Samples a pilot answer, then adjusts batching using observed serialized answer size: three calls per task here. | Retains the function; its ability to produce another child was not exercised within the three-iteration schedule. |

The foundation models, benchmark, host safety controls and budget rules stayed fixed. Source rewriting is now observed, including a changed and used improver. This does not establish that every possible child preserves mutation competence, that the final child can successfully mutate again, or that an evolved improver is more effective. Those are separate existing SRC-02/03 and IMP-01 gates.

Generation cost fell for the batched descendants, but that is not established cost-adjusted superiority. Recorded generation costs were $0.008751, $0.013132, $0.003377 and $0.004388 respectively. Their mean task scores also fell below the starter. Research costs below include proposals and evaluation as well as generation.

## Findings for the harness

These are bounded observations and proposed interventions. They preserve the official scores and are inputs to the existing plan, not a replacement benchmark or a second roadmap.

| ID | Observation and implication | Existing gate |
| --- | --- | --- |
| SRC2-L1 | Story feedback supplied at most 64 UTF-8 bytes from the start of each answer. All ten positions were represented, but most conflict, actions and endings were unavailable to the proposer. Full answers remained saved. This is an information limit in the feedback design, not missing experiment data or parser repair. Prospectively review a bounded representation that covers substantive developments and outcomes. | SRC-02; POL-03 feedback feasibility |
| SRC2-L2 | Digit distinctiveness fell 10 → 5 → 5 → 9. The first child's planner returned five briefs and its code cycled them; the second child's first batch contained five copies of `7`; the third repeated `7` and omitted `0`. Official digit groups exactly matched literal equality. This is direct evidence of generator repetition. | SRC-02; controlled procedure comparison |
| SRC2-L3 | Each story set received official distinctiveness 10, while unblinded full-text review flags potentially repeated causal arcs: first-child answers 2/10 comfort noise fear with blankets/companionship; second-child answers 2/8 recover another child's displaced toy; third-child answers 1/2 find/care for a dog, relinquish it and keep visiting. These are candidate similarities, not adjudicated equivalent classes. The required girl/dog subject alone is not a defect. | Agent feedback and EVAL-02 review; no new general judge audit |
| SRC2-L4 | The second child's answer 2 returns a toy boat to its owner but ends with the dog carrying it home. The third child's answer 7 introduces a hiker only when guiding that person back. These are qualitative coherence concerns. Five sentences and high distinctiveness do not establish usefulness or coherent development. | Task quality and later independent evaluation |
| SRC2-L5 | All children were admitted and the latest was selected despite the starter leading both means. This follows the frozen latest-parent experiment; it is not promotion or an instruction to deploy the last child. Lower callback counts also do not establish better useful diversity per budget. | SRC-02 competence; POL-03 selection; EVAL-01/02 claims |

Story answer positions above are one-based within each ten-answer set. Similarity across different sources is not what NoveltyBench scores: grouping occurs within each source's answer set. The review was neither blinded nor an independent human/model semantic adjudication. No revised partition, supplemental replacement score or claim of judge error follows from these examples.

The next source work is offline: define and verify the remaining child-improver competence/admission checks, and review feedback coverage and quality/resource tradeoffs before freezing another experiment. A broader, repeated, matched-resource comparison would need its own protocol and allocation. EVAL-01's prospective evaluation/finalization safeguards continue independently. No new run is requested now.

## Accounting and completion

The final launch receipt records `complete` / `finished`. The search report records `complete` with reason `bounded_iterations_complete`, three admitted decisions, four complete screens and no recorded failures. All 51 original stage owners are inactive; all 170 attempt records completed. Held liability is zero.

| Stage | Attempt records | Recorded cost |
| --- | ---: | ---: |
| Python proposals | 3 | $0.205283 |
| Answer generation | 78 | $0.029648 |
| Official partitioning | 12 | $0.005397 |
| Official quality scoring | 77 | $0.918668 |
| Total | 170 | **$1.158996** |

The approved cap was $25 and 512 attempts. Its unused $23.841004 and 342 attempts do not authorize another experiment. These are calculations from retained model usage and frozen local prices, not reconciled provider invoices. Attempt counts measure recorded physical operations; they are separate from answers, distinct groups, owners and workers.

The 51 retained worker reports cover twelve source generation workers, three proposal workers and thirty-six native evaluator workers. Each records exit zero and removal of its container. Review checked those saved reports and pinned image identities; it did not start workers or newly inspect the Docker daemon.

## Evidence and review limits

Original local records remain under:

- Search: `C:\Users\arvik\code\buddha\runs\src02-first-source-20261022-live-v1`
- Handoff and authority: `C:\Users\arvik\code\buddha\runs\src02-first-source-20261022-handoff-v1`
- Frozen executing checkout: `C:\Users\arvik\code\buddha\runs\reviews\src02-full-rehearsal`, commit `d4b548292b202ac20bad61d5476d5dacf8e938b0`

The [published evidence projection](conformance/src02-live-results.json) includes the report, launch and proposal hashes, all four source identities, exact scores, literal proposal lineage, usage/accounting totals, resource counts and qualitative findings. The original full evidence tree is local; this publication does not claim that every raw artifact is bundled in Git.

The original passive search inspector reproduced the saved report. Separate raw review checked all 170 usage/cost joins, original owner identities, literal parent/request/reply/child links and all worker reports. The final review snapshotted all 606 search files and seven handoff files before and after; their contents and directory inventories stayed unchanged, as did all 56 original proposal source pins. Review made no provider calls, started no workers, read no API keys, wrote no original artifacts and used no file-backed SQL connections. SQLite snapshots were queried only in memory.

Review-wrapper corrections are retained separately from the successful experiment. Early wrappers stopped on mistaken assumptions about the passive accounting projection, the inherited request separator and a nonexistent proposal packet field. The original inspector had passed before downstream extraction failed. The final v4 raw-join pass reused that recorded inspector success; it did not invoke the inspector again. An independent reader likewise corrected an assumed feedback shape before completing its own review. These were analysis-tool failures, not paid retries or changes to the run. Their retained hashes and exact scopes are in the evidence file.

The results close the observation and accounting task for this frozen first experiment. They leave useful-diversity improvement, universal mutation competence, improved-improver effectiveness and held-out/human validity open.
