# Buddha: consolidated living plan

Revision 6 — October 20, 2026. **This is the single authoritative roadmap for scope, order, status, dependencies and the next work slice.** It combines the original research/design plan, completed implementation, live-pilot findings and the user's request to salvage the interrupted attempt. Update this file as evidence changes; do not start a separate roadmap.

[DESIGN.md](DESIGN.md) supplies the technical and scientific contract. [RESEARCH.md](RESEARCH.md) and [NOVELTYBENCH.md](NOVELTYBENCH.md) supply source-backed context. Run manifests, receipts, results and dated reviews supply evidence. Those documents retain their roles; their old recommendations and slice numbers do not override this plan's current sequence.

## Objective and separate completion claims

Build an agent that improves its procedures for producing ten useful, meaningfully different answers on NoveltyBench or a separately declared related creativity benchmark. Retain the original endpoint: actual task-agent and improvement-procedure source evolution, not only stronger prompts.

| Claim | Required evidence | Current state |
| --- | --- | --- |
| Working experiment infrastructure | Real generation, evaluation, accounting, provenance, interruption and recovery checks within the claimed scope | One live policy-search pilot completed; broader recovery defects remain open |
| Useful diversity improves | Frozen agent on unseen prompts, matched baselines/resources, both metrics, task compliance, independent judgment audit and uncertainty | Not established |
| Source self-modification works | Parent-authored child changes real agent code and runs through a validated isolated executor | Not implemented |
| The improver improves | Initial versus evolved improvers produce descendants from the same starting conditions under equal budgets, assessed on separate sealed tasks | Not implemented or established |

Task-score improvement alone cannot close the last claim. A functioning loop, source mutation or rising best archive score cannot close the useful-diversity claim. Negative or inconclusive experiments remain valid records; they do not become positive claims to satisfy a roadmap milestone.

## Current checkpoint

| Existing work | Status and limits | Evidence / original scope |
| --- | --- | --- |
| Research, reference audit and metric foundation | Complete for the bounded original study; applicable research remains refreshable | Original slice 1; [research](RESEARCH.md), [benchmark audit](NOVELTYBENCH.md), [verification](VERIFICATION.md) |
| Auditable API evaluation and bounded policy search | Implemented; offline checks and one live case passed. Operational follow-ups below remain open | Original slices 2–3; [slice 2](SLICE2.md), [slice 3](SLICE3.md) |
| First attempt | Nine replies retained, tenth request unknown, no complete candidate result | [Incident review](FIRST-LIVE-REVIEW.md); original run `a1257f96467b490b910b559437a71258` |
| Fresh recovery pilot | Complete: 63 calls, three candidates, one prompt and one proposal; no supported general improvement claim | [Results](FIRST-LIVE-RESULTS.md); run `a0946e22ae1e45d6bf8f74cf9f4f30bb` |
| Pilot concerns and matching source preservation | Complete as a review/preservation task; findings remain open until their individual gates pass | [Review](PILOT-REVIEW.md), [evidence](pilot-review-evidence.json), [source snapshot](snapshots/pilot-runtime-2026-10-19.zip) |

The child scores 8.567273 utility / 10 distinct on the observed prompt, but central plots repeat. The baseline also repeats plots. Partition errors affect utility as well as distinctiveness. Preserve the original results and carry these qualifications into subsequent decisions.

## Work order and dependencies

Statuses are **next**, **planned**, **complete**, or **conditional**. “Next” identifies exactly one slice. Complete means the stated deliverable and gate have evidence, not that every broader research claim is true. Stable IDs remain unchanged when order changes.

### 1. Recover the original attempt safely

This adds concrete work to the original paid-operation/resumability requirements. It is driven by pilot findings O1–O7 and the user's explicit recovery request. Keep each item a separate reviewable slice.

| ID | Status | Deliverable / completion gate | Depends on |
| --- | --- | --- | --- |
| REC-01 | Complete | [Recovery contract](RECOVERY-CONTRACT.md), immutable sealed historical reader and tests-first evidence delivered. Both real histories read without changes. Full 260-test suite passes (one host symlink-privilege skip); lint/types/security/audit/compile pass locally. Exact archived reconstruction was verified in the pilot review; no continuation or shared spending authority is claimed yet. | Existing evidence/source snapshot |
| REC-02 | Complete | Shared immutable scope/caps, atomic attached-database transitions, sealed historical imports, run/runtime binding and live CLI/library enforcement implemented. Process races, rollback, altered schemas, inactive/unknown stops and receipt preservation verified. Both real histories reconcile unchanged. Full 307-test suite passes (one host skip); lint/types/security/audit/compile pass locally. [Contract and limits](RECOVERY-CONTRACT.md#rec-02-implementation-and-boundaries); hosted CI reported separately. | REC-01 |
| REC-03 | Complete | Real HTTP execution prepares required local files/connection before dispatch; failures remain reserved/unsent. Stable UUID reuse, concurrent dispatch winner, cleanup, true timeout stops and received-reply interruption accounting verified through the broker. Full 325-test suite passes (one host skip); lint/types/security/audit/compile pass locally. [Contract and evidence](RECOVERY-CONTRACT.md#rec-03-implementation-and-unsent-boundary); hosted CI reported separately. | REC-01; integrate with REC-02 |
| REC-04 | Planned | Aggregate recovery gate, retained in full and delivered through the three items below: verified source, executable linked continuation, and the user's bounded live completion. The original unknown and historical evidence remain intact throughout. | REC-04A/B/L |
| REC-04A | Complete | Read-only verified source and immutable semantic receipt map for nine original replies plus explicit replacement identity. Sealed runtime/index, scientific controls, exact costs/bounds and slot order checked; normalized source and isolated executable scientific comparisons pass. Actual original source verified unchanged. Full 348-test suite and local lint/types/security/audit/compile pass (one host skip). [Evidence](RECOVERY-CONTRACT.md#rec-04a-source-and-receipt-foundation). No continuation or funding allocation created. | REC-01, preserved runtime |
| REC-04B | Complete | Atomic source claim, frozen new runtime/protocol, nine inherited replies without physical operations/double charge, explicit new tenth identity, existing search integration and separate inherited/new/shared accounting implemented. Full 381-test suite and lint/types/security/audit/compile passed locally (one host skip); native mocked-HTTP CLI/replay independently verified. Original seals unchanged. Corrected operational continuation is prepared, verified and awaiting the user; no new model calls. [Contract](RECOVERY-CONTRACT.md#rec-04b-linked-execution-and-accounting), [exact handoff](FIRST-LIVE-CONTINUATION.md). | REC-02/03, REC-04A |
| REC-04L | **Next** | User executes the reviewed linked continuation locally under the shared cap. Verify complete remaining pilot stages, lineage and combined accounting; retain the original unresolved request. This closes REC-04 only with actual live evidence, not infrastructure tests alone. | REC-04B; fresh bounds/source checks |
| REC-05 | Planned | Add a review/doctor path for stale locks and dispatched work, summaries tied to outstanding operations, and a genuinely read-only verification entry point. A dead writer is not reported as proven alive; elapsed time alone never releases liability. Distinguish observation from writable cached reconstruction. Include REC2-F1: preserve and accept a legal completed legacy operation's retained earlier uncertainty receipt in sealed history; no general reconciliation claim before this check. | REC-01; needed before relying on unattended/long-running operation |

Exact original resumption is an alternative only if authentic evidence for the missing original response, identity and usage becomes available. It is not promised by this plan. The practical continuation produces a separately identified complete result linked to the still-interrupted original attempt. Never insert a fresh reply as the old request's receipt. Apply diversity interventions to a new treatment, not to the original pilot's frozen scientific settings.

### 2. Calibrate diversity and task quality

Independent audit and strict task compliance were original requirements. The repeated plots, craft gaps, metric coupling and ceiling effects now make these immediate gates before scaling optimization.

| ID | Status | Deliverable / completion gate | Depends on |
| --- | --- | --- | --- |
| MEAS-01 | Planned | Define the project's central-content criterion alongside the unchanged official equivalence definition. Prepare a shuffled, policy-blinded audit pack with near-duplicate concerns, genuinely different outcomes and required-commonality controls. Include literal constraints, strict single-digit/closed-answer controls, causal/craft quality, equivalent/distinct/uncertain labels and disagreement. Obtain independent review; only adjudicated examples become semantic regression expectations. | Existing M1–M4 cases; offline preparation can be independent of recovery |
| MEAS-02 | Planned | Record an independent supplemental assessment with versioned criteria, reviewer identity/type, uncertainty and exact answer references. Check partition/order sensitivity as budget permits. Explain effects on both metrics; no unsupported “corrected” ranking. Already-inspected cases are development diagnostics, not held-out evidence. | MEAS-01; an explicit allocation if external judging is paid |

Passing this stage means the assessment and its limitations are understood well enough to evaluate the next intervention. It does not require forcing reviewers to agree with this pilot review or replacing official NoveltyBench scores. If disagreement remains material, retain an inconclusive result and narrow the claim.

### 3. Test bounded policy improvements and develop the search baseline

This extends original slice 3 and its baseline/ablation commitments. The precise sampling comparison is a new response to observed repetition.

| ID | Status | Deliverable / completion gate | Depends on |
| --- | --- | --- | --- |
| POL-01 | Planned | Explain independent versus history-aware sampling in a versioned proposer contract. Add only the minimal explicit-policy input needed for controlled evaluation, reusing the evaluator and broker. Preserve literal task form, fixed model access and official instrument. A schema/request-construction test must fail if those contracts drift. | Source preservation; REC-01 runtime/version contract |
| POL-02 | Planned | Freeze and execute a controlled comparison: empty versus child instructions under independent and in-context sampling, varied declared development prompts and repeated complete answer sets. Predeclare task coverage/families, models, limits, total research cost, supplemental review and analysis. Report negative outcomes and regressions. Existing CLI free proposals are not a substitute for evaluating an explicitly fixed policy. | POL-01, MEAS-02, REC-02/03; concrete experiment funding |
| POL-03 | Planned | Specify bounded feedback extraction/feasibility before paying for larger screens; test a declared multi-iteration loop so child failures can inform later proposals. Preserve failed/invalid proposals and complete common-screen coverage. Keep admission, numerical frontier selection and confirmed promotion separate. | POL-02 results; adapt the hypothesis if they are negative |

Reuse the two existing sampling modes first. A planner, critic, semantic archive, routing service, embedding system or new dependency must be justified by a measured failure that simpler existing mechanisms do not address. Same-model generation/proposal/partition dependence and freshly sampled stochastic variation remain explicit evaluation limitations.

### 4. Implement genuine source self-modification

This is the **original slice 4**, retained as an essential goal. Recovery and calibration insert prerequisites; they do not replace source evolution with prompt optimization.

| ID | Status | Deliverable / completion gate | Depends on |
| --- | --- | --- | --- |
| SRC-01 | Planned | Implement the real isolated executor and narrow model gateway. Pin the runtime image; use non-root execution, read-only inputs/root, bounded scratch/processes/CPU/memory/wall clock, no outbound network or raw credentials, and no host/Docker socket access. Adversarial tests must demonstrate filesystem, secret, network, resource and output boundaries, including termination of owned processes. | REC runtime/accounting guards; measurement contract understood before enabling evolutionary search |
| SRC-02 | Planned | Implement inherited, versioned task/improver bundles with `generate` and `propose_improvement`, safe materialization, lineage and mutation-competence checks. Demonstrate a parent-authored child changing real task code, then preserve the ability to author further valid children. Account for every model operation through the host broker. | SRC-01; fixed evaluator/split authority; usable development evidence |
| SRC-03 | Planned | Enable and demonstrate parent-authored changes to the actual inherited improvement procedure, with interface, mutation-competence and protected-boundary checks. Preserve initial and changed improver sources plus their descendant histories. Successful execution demonstrates a changed improver; its improved effectiveness is tested separately in IMP-01. | SRC-02 |

Generated code cannot change the official evaluator, split/final access, credentials, spending authority, promotion rules or host settings. A subprocess, AST allowlist, compile success or available Docker daemon is not evidence that the executor is safe or that the improver remains competent.

### 5. Establish held-out task improvement

This retains the original slice 5 scientific requirements. The controller/analysis contract may be built earlier when needed; no validation or final access happens before its rules are frozen. Policy-only and source-evolving agents must be reported as separate treatments.

| ID | Status | Deliverable / completion gate | Depends on |
| --- | --- | --- | --- |
| EVAL-01 | Planned | Implement limited validation occasions and a one-way finalization controller. Freeze full coverage, compatible controls, semantic prompt-family handling, source/task coverage, finalist count, practical-effect margins, uncertainty method and multiple-comparison/occasion policy before observation. Use complete prompt-level answer sets as units. Separate development, validation, final and independently authored transfer evidence. | MEAS work; variance/cost evidence from POL-02; before any validation-based promotion |
| EVAL-02 | Planned | Freeze finalists and run the declared independent evaluation against matched baselines, preserving failures, literal-form checks, both metrics, uncertainty, cost and independent audit. Report subset coverage and public-benchmark contamination limits. A full NoveltyBench claim requires the reference populations/subsets and declared aggregation; a small sample remains a subset result. Support only the claims the data justify. | EVAL-01; POL-03 for policy-agent claims; SRC-02 for source-agent claims; concrete funding |

Retain the original staged comparator matrix: direct independent and in-context generation; simpler/random or reflective prompt search (such as GEPA) where making a search-efficiency claim; archive versus latest-only and no-feedback conditions; and fixed versus evolved improvers in the next stage. The existing uninformed mode is a no-feedback proposer, not uniform random policy search. Match base-model access and declared resources, and disclose total search/proposal/judging cost as well as inference cost. Do not install a comparison library merely to add its name.

### 6. Test whether the improver itself improved

This is the original separate improvement-competence experiment, not a new requirement invented after the pilot.

| ID | Status | Deliverable / completion gate | Depends on |
| --- | --- | --- | --- |
| IMP-01 | Planned | Freeze initial and evolved improvers. Give them the same starting bundles and development packets, equal descendant budgets and selection rules across several starting conditions/repetitions. Assess selected descendants on a separate sealed task set. Report valid-child rate, target repair, net task gain, regressions, descendant productivity and improvement per budget; charge failed attempts. | SRC-03, EVAL-01/02 infrastructure, independent funding/analysis plan |

A better task agent is not evidence of a better improver. If causal claims concern reflective feedback, declare the appropriate no-feedback or shuffled-feedback comparison. Keep targeted repair, transfer and net held-out gain separate.

## Benchmark, research and delivery requirements that apply throughout

- The current official code/protocol governs new benchmark experiments; the paper is historical context. Existing runs stay on their frozen v1.1 reference. Check upstream before a new experiment; if it changed, review/adapt/pin the new contract without rewriting old evidence. Reverify provider bounds and availability before live execution.
- Continue targeted research from credible primary scientific/academic/engineering sources when a pending decision needs it. Preserve source revisions, licensing and the distinction between published claims, inspected code and project hypotheses. Do not turn the roadmap into an indefinite literature survey.
- HyperAgents remains conceptual inspiration only; no implementation or implementation-specific prompt copying. Dependencies, repository code, papers and datasets have separate permissions. Resolve redistribution questions before distribution; permissive dependency defaults remain in force.
- NoveltyBench and a separately declared sealed transfer benchmark can support different claims. Never describe within-set difference as proof of historical originality or indefinite open-endedness.
- A contemporary Novamine/leaderboard comparison is **conditional later work**: refresh official reference/submission conditions and comparable evidence before making a claim. Full external comparability, reproducible artifacts and honest total cost are required. No leaderboard submission or publication occurs merely because it appears in this plan, and beating a leader is an empirical target rather than an infrastructure acceptance test.
- Keep the local design small. No queue service, Redis, vector database, multi-tenant backend, training framework or persistent multi-agent platform is required by the present evidence. Optional internal critics, adaptive selection, curricula and extra sampling mechanisms remain hypotheses drawn from the research register, not automatically scheduled features.
- Each implementation item starts with spec-defined failing checks, a concrete shape and the minimum correct implementation. The user now authorizes continuing implementation across slices, pausing only for a required live run or user decision. Relay a summary and create a conventional commit/PR for each small slice; then continue authorized work. Keep dependent PRs stacked without silently merging unreviewed work. Frozen experiments and paid scope remain protected.

## Funding snapshot and execution boundary

As of this revision: $50 total authorized for the first live experiment; **$0.301862** combined known recorded cost; **$0.532373** held for the interrupted request; **$49.165765** available and **55** calls left in the original shared 128-call envelope. The corrected continuation `a486d90396934a45940637d77a168304` is prepared under authority `511fe97a08e049a48907c00bad7462df`, with both historical runs imported inactive and zero new operations. Its allowance is the same remaining balance, not additional authorization. The earlier zero-operation preparation is preserved and permanently inactive; [the handoff](FIRST-LIVE-CONTINUATION.md) records explicit supersession. `runs/reviews/rec04b-preparation.json` records verified identities, totals and unchanged original seals. Recorded costs are conservative local calculations, not reconciled invoices.

The user requested salvage of the original attempt. REC-01–04B now supply the reviewable, enforceable continuation; actual user live completion remains REC-04L. The old original stays inactive and unknown throughout. Later comparator/research runs have no allocation from this plan alone; use concrete experiment plans within applicable authorization. Model keys are supplied locally through the existing protected interface and never belong in chat, this plan or run artifacts.

Recompute and link authoritative accounting before paid execution. Never manually decrement a prose balance in place of the ledger or allocate the same remainder twice. Resolve authentic provider evidence separately from replacement attempts.

## Traceability: original plan and new findings

| Source of work | Where it lives in this plan |
| --- | --- |
| Original slices 1–3 | Completed checkpoint; remaining bounded-policy depth in POL-01–03 |
| Original paid-operation and reproducibility contract + user's recovery request | REC-01–05; source preservation already complete |
| Original independent judgment/compliance gates, now made concrete by the pilot | MEAS-01/02 and EVAL-01/02 |
| Original slice 4: real source evolution | SRC-01–03 |
| Original slice 5: scientific evaluation and improver experiment | EVAL-01/02 and IMP-01 |
| Pilot M1–M4: plots, coupled metrics, craft, metric meaning | MEAS-01/02, POL-02, EVAL-02 |
| Pilot E1/E5/E6: sample size, independence, coverage/families | POL-02, MEAS-02, EVAL-01/02 |
| Pilot E2/E3: sampling memory and feedback | POL-01–03 |
| Pilot E4: admission/archive interpretation | POL-03 and EVAL-01; reporting boundary applies now |
| Pilot E7: feedback-size failure after spending | POL-03 |
| Pilot E8: policy optimization is not source evolution | SRC-01–03 and IMP-01 remain open |
| Pilot O1/O4: funding authority and unknown-stop scope | REC-01–03 |
| Pilot O2: unrecovered request | REC-04, conditional exact-receipt reconciliation alternative |
| Pilot O3: provably unsent diagnostic failure | REC-03 |
| Pilot O5/O7: liveness, summaries, read-only verification | REC-05 |
| Pilot O6: source preservation/runtime binding | Snapshot complete; REC-01/02 carry forward full runtime provenance |
| Pilot O8: cost/status scope | This consolidated status and funding snapshot; POL-02 feasibility and all experiment reports |

## Keeping this plan current

For each new finding, record its evidence in the appropriate dated report, give it a stable finding ID, and link it to the affected work item and completion gate here. State whether it is an observation, reproduced defect, untested risk or proposed intervention. Reorder or split tasks when justified; retain stable IDs and a reason in the revision log. Do not treat every concern as a mandate to add a feature.

At each completed slice, update its status, evidence and remaining limits, set exactly one next slice, and summarize the change to the user. Claim states change only with their own evidence. Frozen manifests/receipts/results remain historical records; corrections use an explicit new version or linked assessment. Do not duplicate sequencing in incident reports, review handoffs or a second status file.

Git baseline `eacd68c` preserves the pre-recovery implementation in [wavemanco/buddha](https://github.com/wavemanco/buddha). Existing slices 1–3 were captured together because no earlier Git history existed; future slices have separate branches/PRs. CI is configured for Windows/Linux with pinned checking tools. Slice reports distinguish local checks from observed hosted-CI results.

Pending experiment-specific choices include the supplemental criterion, independent-review arrangement, broader prompt coverage/repetition count, practical-effect thresholds, finalization analysis, and allocations beyond the requested continuation. They are deliberately not invented to fill a table; freeze them at the relevant gate before observation or spending.

## Revision log

| Revision | Date | Change and reason |
| --- | --- | --- |
| 1 | 2026-10-19 | Consolidated the original five-slice design, completed pilot and source preservation, all M/E/O pilot findings, and the requested original-run continuation. Inserted recovery/calibration gates without dropping real source evolution, held-out comparisons or improver evaluation. REC-01 is the next slice. No runtime implementation or paid execution starts with this planning update. |
| 2 | 2026-10-19 | User authorized continuous implementation with slice summaries and PRs until a live-run/decision gate. Established Git baseline and slice branch/CI; REC-01 adds the concrete recovery contract and sealed read-only history foundation after observed failing acceptance tests. REC-02 is next. |
| 3 | 2026-10-19 | REC-02 implements shared scope/caps and atomic paid-operation authority through CLI and library paths. Real histories reconcile unchanged; races/rollback/foreign-schema/source-drift checks pass. Independent review's REC2-F1 legal reconciled-history limitation is explicitly added to REC-05. REC-03 is next. REC-01 hosted Windows/Linux CI passed. |
| 4 | 2026-10-19 | REC-03 establishes the actual unsent preparation boundary, stable diagnostic request reuse, one dispatch winner and terminal accounting before optional tail interruptions. All local checks pass; historical ledgers remain unchanged. REC-04 is next. REC-02 hosted Windows/Linux CI passed. |
| 5 | 2026-10-19 | Split REC-04 into reviewable source (A), execution/accounting (B) and actual user live completion (L), retaining the aggregate gate. REC-04A verifies the real nine receipts without writes/calls and binds scientific behavior to the preserved source with both static guards and isolated executable comparisons. Module/class rebinding counterexamples were closed before delivery. REC-04B is next; REC-03 hosted Windows/Linux CI passed. |
| 6 | 2026-10-20 | REC-04B implements and verifies actual linked execution, atomic allocation, replay and inherited/new/shared accounting; 381 tests and all local checks pass. The original seals and unknown hold remain intact. Review's synthetic-authority, watcher-format, malformed-format and archive-error regressions were closed. An unspent early preparation was deactivated and preserved before publishing the corrected bounded command. Official upstream and public provider bounds were rechecked; no scientific configuration change indicated. REC-04L is next and is the current user-live gate. REC-04A hosted Windows/Linux CI passed; REC-04B hosted results reported separately. |
