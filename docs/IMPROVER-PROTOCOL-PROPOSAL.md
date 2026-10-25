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

The prepared population below concerns the next bounded Buddha development
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
| Development | Three selected WildChat tasks; two repeated occasions per start; two counted opportunities per arm and occasion |
| Feedback | Unchanged comparison policy through explicit study v4; full literal answers, actual-parent deltas, null common roots and retained failed-child history; witnesses retain absolute notes |
| Selection | Existing archive method, `max_active=8`, selection seed 7, `finalist_iteration=2`; select only admitted descendants, never a replacement starter |
| Final | Prepared 26 WildChat tasks in25families, one answer-set occasion per frozen role/task; fresh starter plus initial/evolved descendants for each condition |
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

## Prepared WildChat population and prospective custody

The user selected and reconfirmed official WildChat for this comparison. The
[completed preparation](IMPROVER-WILDCHAT-PREPARATION.md) now binds the complete
1,000-task source, an opaque family/type map, three selected development tasks
and 26 final tasks in 25 families. Original text/IDs and official evaluator
commands/settings remain unchanged. All assigned final members must be used.

A fresh custody-only role read every primary prompt, with no agent sources,
answers, scores or optimization history. Descriptive notes stay in that role;
only opaque metadata and generic method/coverage return to root. Root/source
authors remain inside the optimization scope. Exact P/C predate this preparation.
The saved declaration marks only those26finalmembers eligible for the exact
documented prospective process; the other974members remain unknown. Its60
pinned evidence files and1000data-role disclosures pass the existing custody
validator and seven denial checks. Logical role separation does not establish
universal historical/training invisibility or independent task families.

The [Curated check](IMPROVER-CURATED-SEPARATION.md) found development-only
recorded callbacks and no demonstrated leak, but could not establish complete
historical source-author separation. Preserve that result and original scores.
Curated remains historical/qualified development evidence; no further Curated
run or population question is scheduled here.

The source/family allocation is data preparation, not an adopted funded study.
[Its recipe](conformance/imp01-wildchat-allocation-recipe.json) was originally recorded before
root received the map; its explicit second version precedes the corrected allocation. Whole-family stratified assignment and deterministic
selection preserve the full source; the three development tasks and26finaltasks
have disclosed type-coverage limits. An independent implementation reproduces
all three saved allocation outputs byte-for-byte. The current one-source
interface uses WildChat for both development and final assessment; no dataset
concatenation, prompt rewriting or change to NoveltyBench scoring is introduced.

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
work. The earlier v3 six-cell software check took 1,197.903 seconds; other recorded local
lifecycle checks took 20–41 minutes. These are measured software-check times, not
an actual-grid runtime estimate or a promise of linear scaling.

## Capacity, uncertainty and review

The [bounded original P/C checks](conformance/imp01-both-consumers-delivery.json)
now verify each frozen actor's complete root/own-edge request forwarding. Actual
future requests still need checks at the chosen configuration, including context
and replacement-output headroom. The supplied fixtures do not establish model
attention or certify a returned future replacement. Preserve full text; stop on capacity failure rather than
truncating answers or feedback.

Explicit study v4 and matching assessment v4 now connect the existing original-call
capacity policy to counted proposals and both mutation-witness paths. Study v3
keeps its original behavior and does not acquire this barrier. The next concrete
comparison must explicitly use v4, bind its exact policies and pass configuration
checks; no older declaration is silently upgraded. Missing or failed replacement
evidence stops development as a recorded partial result before child work.
This includes malformed, rejected and callback-free proposals under the closed
`require_replacement` policy. It can therefore stop the whole comparison before
all opportunities are used; retain that consequence when adopting the live design.
The software checks do not certify actual future model capacity or source quality.

Proposed numerical settings use the existing
`fixed_panel_family_hoeffding_shared_starter.v1` method
([meaning and assumptions](IMPROVER-ANALYSIS.md#what-the-uncertainty-calculation-means)),
alpha 0.05, six equal positive tail allowances 1/120, utility as primary metric,
minimum gain 0 and permitted distinct-count loss 0. Both official metrics and all
three contrasts stay visible. These settings are proposed, not silently adopted.

For the prepared WildChat26, equal task weighting gives squared family weights
7/169 (24singletonfamilies and one pair). The independent formula check yields
conservative radii6.297594utility and5.667835distinct count. Even26equally
weighted independent families would give6.068514and5.461662. Repeating
starts/generations does not shrink this method's family radius. It is poorly
sensitive to modest effects; an inconclusive result would not establish absence
of an effect. Family labels do not prove independent blocks. These are formula
checks, not a power analysis or a fresh public-analyzer observation. The earlier
Curated calculation remains historical in the linked feasibility record.

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

## Readiness and next work

The completed [v3 connection check](conformance/imp01-v3-sealed-rehearsal-delivery.json)
remains useful engineering evidence. WildChat release data, the complete task
source, split and scoped prospective custody are now prepared. A live execution
bundle, funded study, authority, owner and launch command still await the required
checks. No paid request or selected-source execution is performed here.

The selected WildChat data/custody preparation is now complete at its bounded
scope. No population decision remains pending. The explicit v4 capacity connection
is implemented; executing-code verification remains separate from live readiness.
The [concrete configuration draft](IMPROVER-WILDCHAT-CONFIGURATION.md) now
passes existing study/assessment and full-grid data checks. Next resolve its
exact input/request envelope and bind actual runtime/resources, aggregate caps,
statistical adoption and review arrangements. Request a new allocation
only after those checks make a concrete live proposal reviewable. No new funds,
owner or launch command follow from this preparation. This remains the original
IMP-01 comparison; the DGM/Harness2 cross-check adds no redesign or new gate.
