# Proposed matched P/C improver experiment

October 25, 2026. **Unfunded proposal, not a frozen study or a launch guide.**
[PLAN.md](PLAN.md) remains the only roadmap. The [checked arithmetic and source
record](conformance/imp01-protocol-proposal-feasibility.json) supports this proposal;
it does not establish scientific eligibility, live readiness or a spending cap.

## What this would answer

Does the original evolved improver C produce more useful, distinctive descendants
than the original improver P when both receive the same starting agents, complete
development feedback, opportunities and resource limits? This studies Buddha's
improvement procedure. It does not retest or modify NoveltyBench's evaluator.

P and C stay frozen. Each may change the task agent it is improving, but a new
child never replaces the fixed experimental improver. Official NoveltyBench 1.1
partitioning and utility scoring remain the yardstick. Keep negative results,
invalid children, repeated answers, failed witnesses and missing outcomes.
A negative or inconclusive result is a valid experiment, not a failed milestone.

## Who sees which information

| Role | Information it needs |
| --- | --- |
| Generator | The current task prompt and any earlier answers permitted by the declared sampling procedure. It must see the task to answer it. |
| Improver | Development task prompts, complete development answers, measured feedback and actual parent source. Reserved final tasks/results must not become tuning feedback before final assessment. |
| Partition judge | The task prompt and generated answers, through the unchanged official distinctiveness procedure. |
| Utility judge | The task prompt and generated answer material required by the unchanged official scoring procedure. |

The selected generator model is configurable and can vary across separately
recorded comparisons. Freeze it within a matched comparison so a model change
is not confused with a harness change. Evaluation models/settings are separately
pinned to the adopted official protocol and stay outside editable agent code.
These roles remain separate even when two happen to use the same vendor/model.
The reserved-task restriction concerns learning and selection, not withholding
the current task from the generator or judges during final inference/scoring.

## Development comparison versus leaderboard submission

The population choice below concerns the next bounded Buddha development
comparison. It is not a permanent choice of which NoveltyBench subset to use.
The [official submission instructions](https://novelty-bench.github.io/submit.html)
require both NB-Curated and NB-WildChat, ten responses per prompt, the v1.1
2048-token generation setting and low reasoning effort where applicable, with
independent versus in-context sampling declared. Preserve the official
provider-specific handling of those settings. The leaderboard also separates
systems with different inference budgets; a scaffold is not one bare model.

The [official metric description](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/README.md#metric-versions)
uses GPT-5.6-luna to read all ten responses for partitioning and Claude Opus 5
to score one representative per distinct group. Both need the original prompt.
Those evaluation roles are separate from the configurable generation backbone
and from the model authoring agent changes.

The earlier 4,096-token source configuration below is an inherited development
setting, not a claim of leaderboard generation-protocol compliance. A later
submission must adopt the published generation protocol and disclose the
scaffold's actual calls/tokens/costs. Within a matched comparison, hold the
backbone/settings fixed and check total-resource fairness, including the
observed difference between P's separate calls and C's batched answers. Repeat
across backbones as separately declared comparisons rather than silently
changing models within an arm. No old run is relabeled as a submission.

## Original treatments and proposed conditions

| Item | Proposal |
| --- | --- |
| Initial improver P | Original 13,455-byte Python file; SHA256 `77cfa68f6b3c6996fd503e1ce6f7a964eb57abdb8bde98f6761de5f6e298ff4f` |
| Evolved improver C | Original 13,084-byte Python file; SHA256 `4196cd29ffa76c6959e6f678a8286b1fde5b56e6a34a97dcf68787e1f22b3a43` |
| Common starting task agents | The same original P and C bundles, each supplied to both improvers |
| Development | Three tasks; two repeated occasions per start; two counted opportunities per arm and occasion |
| Feedback | Explicit study v3 comparison policy; full literal answers, actual-parent deltas, null common roots and retained failed-child history; witnesses retain absolute notes |
| Selection | Existing archive method, `max_active=8`, selection seed 7, `finalist_iteration=2`; select only admitted descendants, never a replacement starter |
| Final | Proposed 26 tasks, one answer-set occasion per frozen role/task; fresh starter plus initial/evolved descendants for each condition |
| Execution | Existing isolated source worker and unchanged official native evaluator; every callback and failed physical attempt remains accounted |

The exact original files remain in the closed current-source experiment; their
paths and hashes are in the linked record. C's convenience index reads only the
task ID from the new nested notes. Its complete original notes still enter the
emitted model request, as the [actual isolated C check](conformance/imp01-comparison-consumer-delivery.json)
shows. Retain that treatment limitation. Repairing C would create a different
treatment, not a correction to this experiment.

Two repeated occasions are proposed to observe stochastic variation; they are
not independent task families or controlled provider seeds. Selection seed 7
controls the existing archive choice. This finite population does not establish
performance across arbitrary starts, search seeds or future searches.

## Choose the task population before declaring eligibility

**The selected Curated separation check is complete at its bounded scope.**
The [review](IMPROVER-CURATED-SEPARATION.md) finds development-only recorded
improver requests and no demonstrated reserved-task leak, while complete
historical host/source-author separation remains unknown. The original26
are not certified eligible. No dataset switch is adopted by this finding.

The recorded prompt inspection involved two AI source-review contexts grouping
related tasks before split assignment. They were not independent human
evaluators. Such preparation can legitimately involve reading every prompt.
The important boundary is whether reserved prompt content or results then
influenced the agent-improvement process. A family reviewer seeing a prompt does
not, by itself, establish that boundary was crossed.

The historical protocol explicitly declined to certify the reserved population
as unseen or eligible. It did not report a demonstrated final-prompt disclosure
to an improver callback or tuning using final results. Family maps and substantive
boundary notes returned to the host, so fresh review contexts alone also do not
prove complete separation. Check that information flow before adopting a named
custody claim. Original [review roles and scope](POLICY-COMPARISON.md#which-prompts-are-included-and-why)
remain unchanged.

This qualifies claims about held-out performance and generalization. It does
not alter official NoveltyBench score calculations or prevent explicitly
qualified development measurements. WildChat is an alternative official
population, with its own unresolved exposure and task-separation checks; local
availability is not evidence that its prompts are unseen.

| Candidate | What is known | Consequence |
| --- | --- | --- |
| Existing Curated source | Ordered diagnostic development tasks are curated-0, curated-47, curated-97. The existing final partition has 26 tasks in 17 families. All 100 Curated prompt texts were previously read by two development source reviewers; known measured/feedback exposure is a separate, smaller population. | Neither prompt review nor lack of recorded final outcomes establishes eligibility. The bounded check supports actual development-only callbacks, but not complete historical source-author separation. Keep original26 eligibility unknown; Curated remains usable for qualified development measurements. It does not close the strict sealed-task requirement. No guard is bypassed. |
| Entirely official WildChat source | The original wildchat-1k.jsonl is sealed at upstream 64a23be6b18ec1dacc298830aab276061b6e143c; its 645,466 bytes hash to 8534288089508df3f413c1151a58d5fa5bda9d8f8385ae2815384d4e310a54ca. Existing records identify 1,000 unique IDs. Prior research sealed its bytes and read published summaries/counts. No exhaustive per-ID exposure record or eligible family/split custody was established by this review. | Prepare a new prospective family map, three development IDs, 26 final IDs and exposure record without disclosing final prompts/results to optimization decision makers. Preserve original task text and typed IDs. Exact IDs are deliberately not adopted here. |

The current assessment requires the **same complete original task source** for
development and final assessment, and every assigned final member must be used.
Keeping Curated development while using a separate WildChat final population is
not supported by this interface. Do not concatenate two files and label the
result an official combined dataset. Using WildChat for both phases changes
configuration and experimental population, not the scoring algorithm.

A custodian must document actual visibility, family separation and the eligible
channel before freezing final IDs. Prior operator/reviewer visibility and
model-training uncertainty stay explicit. A new process name is not evidence
that exposure never happened. [DESIGN section 7](DESIGN.md)
and the [custody checks](IMPROVER-ASSESSMENT.md#what-is-fixed-before-work-starts)
remain binding. The check does not ask the user to attest missing historical
context. The remaining choice is prospective official WildChat custody for a strict sealed
comparison, or explicitly qualified Curated development work without closing
the held-out gate. [The result and recommendation](IMPROVER-CURATED-SEPARATION.md#what-remains-usable)
keep these different claims explicit.

## Planned workload and spending boundary

| Maximum planned work | Two repeated occasions | Smaller one-occasion candidate |
| --- | ---: | ---: |
| Shared starting conditions |4|2|
| Counted proposal opportunities |16|8|
| Full development task assessments |60|30|
| First-task validity-only generations |20|10|
| Proposal workers, including witnesses |36|18|
| Development answer positions |800|400|
| Final source-role slots |12|6|
| Final task assessments |312|156|
| Total answer positions |3920|1960|

Counts assume three development tasks, 26 final tasks and ten answers per task.
Conditional downstream work may be skipped after a failure; the planned
denominator never shrinks. Identical source bytes in different roles remain
separate roles. The smaller candidate trades away repeated occasions and would
need separate prospective adoption; it is not a quietly shortened completed run.

Reuse the recorded source configuration as the starting point: generation uses
gpt-5.6-luna with 4,096 output tokens and 12 callbacks/attempts; proposals use
gpt-6.1-sol with 32,768 output tokens and three callbacks/attempts. Partitioning
uses gpt-5.6-luna; quality uses claude-opus-5 with the official claude-sonnet-5
fallback, patience 0.8 and concurrency 2. The linked record retains exact profile
hashes, historical bounds and instructions. Fresh source/release identities,
prices/account checks and feasible limits must be bound before any live handoff.

**No new budget is requested or approved here.** Old per-owner $25 ceilings add
to enormous theoretical maxima; these are not expected bills. Existing study v3
supports smaller positive development/final aggregate caps while preserving
individual ceilings. Choose the actual caps and attempt allocations after the
population, request bounds and runtime are checked. Do not lower financial input
ceilings merely to make the sum attractive. Equal nominal opportunities and
per-arm limits do not guarantee equal consumed dollars when treatment behavior
differs; report both. A shared-cap stop can leave unequal coverage and must be
reported as partial with stage, reason, full denominator, costs and holds.

Historical easy-task costs are a poor estimate for unknown final tasks: binary
choices, collapsed integer answers and fewer distinct classes reduced judging
work. The new bounded six-cell software check took 1,197.903 seconds; earlier local
lifecycle checks took 20–41 minutes. These are measured software-check times, not
an actual-grid runtime estimate or a promise of linear scaling.

## Capacity, uncertainty and review

The [bounded original P/C checks](conformance/imp01-both-consumers-delivery.json)
now verify each frozen actor's complete root/own-edge request forwarding. Actual
future requests still need checks at the chosen configuration, including context
and replacement-output headroom. The supplied fixtures do not establish model
attention or certify a returned future replacement. Preserve full text; stop on capacity failure rather than
truncating answers or feedback.

There is a specific integration limit: study v3 does **not** currently carry the
source-handoff v4 proposal-capacity policy or its before-child capacity barrier.
Existing byte, token-usage, request and callback guards still apply. Reuse the
existing capacity assessor and original-call evidence for the adopted route;
if every future counted/witness proposal needs that barrier, connect those
existing helpers in a small explicit slice before live use. Do not describe the
handoff feature as already enforced by this study.

Proposed numerical settings use the existing
`fixed_panel_family_hoeffding_shared_starter.v1` method
([meaning and assumptions](IMPROVER-ANALYSIS.md#what-the-uncertainty-calculation-means)),
alpha 0.05, six equal positive tail allowances 1/120, utility as primary metric,
minimum gain 0 and permitted distinct-count loss 0. Both official metrics and all
three contrasts stay visible. These settings are proposed, not silently adopted.

For the reserved Curated 26, equal task weighting gives squared family weights
27/338. The independent formula check yields conservative radii 8.745659 utility
and 7.871093 distinct count. With those margins, rule satisfaction would need an
evolved-minus-initial mean difference above 8.745659 utility and at least 7.871093
distinct answers. Even 26 equally weighted independent families would give radii
6.068514 and5.461662. Repeating starts/generations does not shrink this method's
family radius. It is poorly sensitive to modest effects; an inconclusive result
would not establish absence of an effect. Family labels do not prove independent
blocks. WildChat's actual calculation must use its adopted families and weights,
not reuse the Curated figures. These are formula checks, not a power analysis
or a fresh public-analyzer observation.

Adopt [target-repair method v1](IMPROVER-TARGET-REPAIR.md) over every counted
opportunity, including rejected/unattempted slots. Two separately initialized
outcome-naive review contexts are proposed; their identities, human/model type,
model IDs where applicable, costs and access arrangements must be fixed before
outputs. Stage A fixes target/parent judgments before Stage B reveals complete
child sets. Preserve uncertainty, disagreement and unavailable evidence; no
majority-vote repair or official rescore. Review cost outside the execution
ledger must be reported separately, not hidden in a budget-efficiency claim.

EVAL-02 still requires the independent human sample and matched final/transfer
evidence. No human reviewers have been recruited or contacted; sample/reviewer
arrangements remain to be fixed. This finite comparison and its numerical rule
do not by themselves establish general usefulness, generalization or that the
improver improves indefinitely.

## Readiness and the immediate decision

The completed [v3 connection check](conformance/imp01-v3-sealed-rehearsal-delivery.json)
remains useful engineering evidence. This proposal has not created a task split,
release selection, eligibility attestation, study, authority, owner or launch
command. No paid request or selected-source execution is performed by it.

The user-selected Curated check now supports the actual callback boundary,
but does not establish the missing historical host/source-author separation.
No leak was demonstrated and the original26 remain uncertified. Choose
prospective official WildChat preparation for the strict comparison (recommended),
or explicitly qualified Curated development work; no switch or funding is
adopted here. No further absence search is prescribed to fill the missing history.
After that choice, freeze the actual source/tasks/custody, compatibility/capacity
route, resources/runtime, statistical settings and review arrangements before
requesting a new live allocation. This is experiment preparation under the existing IMP-01 gate;
the DGM/Harness2 cross-check adds no redesign or new gate.
