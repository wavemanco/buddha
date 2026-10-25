# Proposed matched P/C improver experiment

October 25, 2026. **Unfunded proposal, not a frozen study or a launch guide.**
[PLAN.md](PLAN.md) remains the only roadmap. The [checked arithmetic and source
record](conformance/imp01-protocol-proposal-feasibility.json) supports this proposal;
it does not establish scientific eligibility, live readiness or a spending cap.

The [current configuration refresh](IMPROVER-WILDCHAT-CONFIGURATION.md#current-launcher-configuration-refresh)
retains **WildChat, the exact original P/C and the full two-occasion design**.
Curated stays historical/development evidence. The recommended execution limits
are $50 for development and $100 for final assessment, with separate attempt
limits below. These are unfunded recommendations, not approval or a promise that
the whole study will finish. The [prospective review preparation](IMPROVER-WILDCHAT-CONFIGURATION.md#prospective-review-controls)
now binds the human sample and proposes a native target-review route. Its named
model selection and execution allocation still need the user's decision. Human
availability remains unconfirmed; nobody has been invented or contacted on the
user's behalf.

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

## Model roles and two separately recorded runs

The user is comfortable with the proposed $150 ceiling and wants publication
compatibility, while allowing another scientifically justified configuration.
Model questions remain under discussion. This records scope and preparation,
not a grant, model selection or permission to start.

The exact current official repository head is
`64a23be6b18ec1dacc298830aab276061b6e143c`, checked October 25, 2026. Retain
these model IDs and the actual request construction, not just display names:

| Role | Model ID | Official settings to preserve |
| --- | --- | --- |
| Task generation in the Luna recipe | `gpt-5.6-luna` | CLI generation setting 2,048 with low effort; the official OpenAI builder sends `max_completion_tokens=4096`, `reasoning_effort="low"`, and omits temperature. Ten responses per prompt. |
| Official distinctiveness judge | `gpt-5.6-luna` | Reads the prompt and all ten complete responses. The official OpenAI judging branch supplies neither an explicit reasoning-effort override nor an output-token override; preserve those omissions rather than inventing a low/high value. |
| Official utility judge | `claude-opus-5` | `max_tokens=16000`, adaptive thinking and output effort `high`, with the official structured-output prompt/schema and first-response-per-group scoring. |
| Existing official refusal fallback | `claude-sonnet-5` | Same official Anthropic judging constructor and effort, invoked after an Opus refusal; retain fallback provenance/costs. |

Sources: [generation constructor](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/inference.py#L42-L94),
[judging constructor](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/judge.py#L61-L118)
and [metric description](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/README.md#metric-versions).
If using Opus for **generation** in a later backbone comparison, its generation
constructor doubles the 2,048 setting too and uses adaptive thinking with low
effort, not the utility judge's high-effort settings. Luna remains the chosen
generator here; NoveltyBench does not mandate one generator for every system.

These are the official named model aliases, not invented dated snapshots. Bind
the requested IDs and source revision and retain returned model metadata where
available; a named alias alone does not attest to unchanged backend weights.
The prepared numeric evaluator already selects Luna/Opus/Sonnet explicitly.
That matters because the pinned bare partition CLI inherits an Opus default
from `common.py` despite the documented Luna recipe. Keep the explicit selection,
patience 0.8, declared concurrency and unmodified official prompts/folding rules.

The earlier 4,096-versus-2,048 comparison was misleading: the first number is a
host output allowance, while the second is an official CLI setting that becomes
4,096 inclusive reasoning/output tokens on the wire. A larger token budget has
**not** been established. Do not halve the current wire allowance to 2,048 and
call that official compliance. Current metadata also does not establish that
selected agents emit low effort, use the same token field or omit temperature.
Those actual request semantics still need verification before a compliant run.

Buddha's code-authoring model is separately configured as `gpt-6.1-sol` through
the API; the proposed supplemental native reviewers are Codex
`gpt-6.1-sol` / `ultra`. Neither replaces the official numerical judges, and
NoveltyBench does not prescribe those improvement/review roles.

### Development comparison versus leaderboard submission

The publication-aligned configuration is the primary recommendation. First bind
and verify the official effective generation parameters on Buddha's actual
request path, retaining original agent sources and the fixed numerical judges.
The Gateway can carry low effort, but closed generation/profile schemas expose
no external setting that forces it; an actual-path check or narrow compatibility
change may be necessary. No selected P/C/W source was inspected or executed in
this audit, so whole-run compliance is not asserted from configuration alone.

The prepared legacy P/C comparison remains unchanged evidence of a proposed
reproduction environment: three development tasks, 26 final tasks, two starts,
two occasions and fixed improvers. Preserving that environment was the reason
for the earlier proposal, not evidence that a greater allowance is necessary or
better. The user's requested additional configuration must have a prospectively
stated question and a verified effective difference. If the two request paths
are equivalent, do not spend money treating their different labels as different
budgets. If they differ in effort or procedure, name those factors; a causal
claim about token allowance alone requires a matched comparison holding them
fixed. Full-feedback reading is an input/context requirement, separate from
output limits, and remains required in either configuration.

A [complete leaderboard submission](https://novelty-bench.github.io/submit.html)
also needs both NB-Curated and NB-WildChat, ten responses per prompt, declared
sampling and versioned generation/partition/score/summary artifacts. Before its
execution, freeze the system, baseline, selection rule, model/settings, coverage
and total-resource reporting. The [leaderboard](https://novelty-bench.github.io/)
separates raw models and scaffolds by category/budget. A small protocol-aligned
WildChat comparison is not that full submission. Disclose development exposure;
a public-benchmark submission is not automatically wholly unseen or independent
transfer evidence. Human/transfer requirements remain EVAL-02.

The user is comfortable with the **$150 / 16,384-attempt ceiling** for the
bounded comparison. Its concrete aligned configuration, native-reviewer choice,
funded handoff and checks still need completion; no grant is created here. It
does not fund an additional configuration, the full submission, human time or
native Codex reviews. Preserve the earlier unfunded bundles and costing examples;
prospectively bind any changed effective settings and their source identity,
capacity/accounting consequences and authorization scope. Estimate a separate
full submission once its system/baseline and coverage are concrete.

## Native Codex review and provider cost split

Native review means fresh subagents through this Codex desktop session under the
proposed ChatGPT/Codex-plan route. They receive only their assigned staged review
material, not the full development conversation. They are supplemental model
reviewers, not official numerical judges or independent human reviewers. Native
usage consumes the Codex allowance outside the experiment API ledgers; it is
unpriced here, not zero. [Official Codex pricing](https://learn.chatgpt.com/docs/pricing)
distinguishes plan usage from API-key billing. No reviewer API fallback is adopted.

For orientation within the $150 ceiling, **about $35 OpenAI / $115 Anthropic**
is a rough flexible planning split. It proportionally reflects the existing
short-token examples below; it is not a completion forecast, separate enforced
provider caps or a guarantee that those account balances suffice. The actual
controls remain $50 development and $100 final across both providers.

| Generation calls per ten-answer set | OpenAI, conservative accounting | Anthropic, conservative accounting | Combined |
| --- | ---: | ---: | ---: |
| 1 | $13.400688 | $74.474400 | $87.875088 |
| 10 | $21.550368 | $74.474400 | $96.024768 |
| 12 | $23.361408 | $74.474400 | $97.835808 |

These reproduce the [existing sensitivity worksheet](IMPROVER-WILDCHAT-CONFIGURATION.md#runtime-and-resource-preparation),
using its exact hypothetical token vectors and retained conservative profile
rates. They assume 392 ten-answer sets, 372 partitions, 3,720 Opus calls, 72
planning calls and 36 replacements; all scored sets have ten distinct groups,
one judging pass and no refusal fallback/retry. Planning/replacement inputs are
invented inclusive assumptions, not measured full-feedback/history requests.
Output vectors include reasoning. Longer answers, growing histories, retries,
fallbacks, fewer groups and unavailable descendants change the split and cost.

At the freshly checked ordinary public short-input rates, those **same invented
tokens** instead calculate to roughly $6-12 OpenAI plus $40 Anthropic, $46-52
combined, before account/usage adjustments. That is a separate illustrative
billing basis, not a prediction or guaranteed saving. The conservative profiles
use higher price bounds; recorded costs/reservations are not reconciled invoices.
Sources: [Luna pricing](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[Sol pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing).
The largest native reservation still has to fit before dispatch; uncertain
charges retain holds. A phase may stop with a properly marked partial result.

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
individual ceilings. The refreshed v4 configuration now proposes:

| Phase | Dollar cap | Recorded-attempt limit | Purpose |
| --- | ---: | ---: | --- |
| Development (`search`) | $50 | 4,096 | Common starting screens, fixed-improver proposals, mutation witnesses and child screens |
| Validation | $0 | 0 | Unused in this comparison |
| Final | $100 | 12,288 | Frozen starter/descendant generation and unchanged official scoring on all 26 final tasks |
| Combined execution | **$150** | **16,384** | Sum of the separate phase caps; unused development funds do not increase the final cap |

Each phase shares its cap across its original owners and both experimental
arms; it does not grant that amount to every owner. Keep all existing per-owner,
per-request, input and output ceilings. A recorded attempt can include an
operation that was reserved but never sent; this is not a physical-send tally.
The largest native quality reservation
is $11.44, so a new request can stop before the displayed spending reaches the
cap. Reservations cover outstanding possible charges; they are not extra money
or the expected cost of that request. Unknown charges keep their holds.

This is a bounded experiment with partial results allowed, not a completion-cost
estimate. Earlier short-token examples fit conditionally; longer inputs,
fallbacks and retries can exhaust a phase sooner. Do not lower financial input
ceilings merely to make the total attractive. Equal opportunities and declared
limits do not guarantee equal consumed dollars or completed coverage when P/C
behave differently. Report each arm's actual calls, costs, valid-child rate,
coverage and elapsed time. A cap stop remains partial with its stage, reason,
full planned denominator, costs and holds. Do not rank unequal partial arms as
though they completed a matched comparison.

The $150 recommendation covers execution only. Human time and native Codex
target-review usage are outside these phase ledgers and must be reported
separately. Native usage is not priced here and must not be reported as zero.
There is no separate model-review API allowance or automatic API fallback.

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
checks, not a power analysis. The [later configuration refresh](IMPROVER-WILDCHAT-CONFIGURATION.md#current-launcher-configuration-refresh)
also reproduces the exact directed bounds through the public analyzer with
synthetic metrics only. The earlier Curated calculation remains historical in
the linked feasibility record.

In plain English, the planned rule subtracts a large uncertainty allowance from
the measured difference before permitting a positive conclusion. With this
panel it would need an improver-effect utility difference above about 6.30
points and a distinct-count difference of about 5.67 before both lower bounds
can meet the zero-margin rule. Use the analyzer's exact directed rounding, not
these displayed approximations. These are conditional one-sided lower bounds,
not two-sided confidence intervals. The repeated starts/occasions observe
variation but do not supply more independent families to this calculation.
Small or moderate gains can therefore leave improvement unestablished. A
complete panel can return `rule_not_satisfied`; missing required coverage can
return `inconclusive`. Neither establishes absence of an effect. We keep this limit
visible rather than changing the rule after learning the results. Zero margins
also do not establish that a positive result would be practically important.

Use [target-repair method v1](IMPROVER-TARGET-REPAIR.md) over every counted
opportunity, including rejected/unattempted slots. The current proposal makes
an explicit prospective amendment to the earlier draft's instance-identity
timing: fix two reviewer-stream labels, model/type, workload, method, access and
cost-accounting scope before outputs; bind each actual ephemeral instance and
its exposure declaration before showing it any material. This amendment is
made before any study output, not after learning a result.

The proposed streams are TR-A and TR-B. Each stream/opportunity receives its own
fresh native Codex context: at most 32 contexts and 32 two-stage worksheets.
The funding decision will explicitly include `gpt-6.1-sol` with Codex reasoning
effort `ultra`; only after that selection is authorized may the coordinator use
those exact model/effort arguments with `fork_turns=none`. Enroll each instance
without study material, then save the assignment request and returned
agent/session identity before sending Stage A.

Stage A receives the full captured hypothesis, development prompts and complete
parent sets. Withhold child answers/code/outcomes, official scores, source/arm
identities, final material and the other stream's forms. Save the complete
original Stage A form/hash before revealing Stage B. The same instance then
compares full child sets against those fixed targets. Keep uncertainties,
disagreements, regressions and unavailable evidence; no majority-vote repair or
official rescore. There are at most 64 original stage judgments, not a promise
of only 64 underlying Codex requests. No favorable reviewer reroll is allowed.

Current local root metadata identifies the configured model. A separate generic
canary identified its own real session, but its model/effort were not exposed.
Therefore keep requested assignment separate from observed execution metadata;
unavailable observations stay null. Tool requests do not attest to provider
weights or a backend snapshot. Record known setting mismatches or unintended
exposure as deviations. Fresh contexts and shared-file access provide procedural
blinding, not a security sandbox or proof of independence. Both streams use the
same named model as the proposal backbone, so correlated model preferences
remain possible. The observed root
context window is not a capacity certificate: inability to read complete texts
leaves an incomplete review, without excerpts or automatic model/API switching.

EVAL-02 still requires the independent human sample and matched final/transfer
evidence. No human reviewers have been recruited or contacted; sample/reviewer
arrangements remain to be fixed. This finite comparison and its numerical rule
do not by themselves establish general usefulness, generalization or that the
improver improves indefinitely.

The bounded human recommendation is **one independent person, 12 answer sets,
up to 120 complete answers**, drawn prospectively from four tasks in four
families. The candidate covers the four starting conditions and three source
roles, but tasks and conditions are not fully crossed; report it descriptively.
Freeze the actual sample, rules, materials and helper pins before preparing
owners. Bind the real reviewer roster before distributing any materials. A
missing reviewer is recorded as unavailable, and EVAL-02 stays open. Exporting a
blank template or importing a model-completed form is not human evidence;
incomplete blank submissions are rejected.

The prospective human plan, release-bound materials, protocol and four existing
review helpers are now bound into the candidate's original custody controls.
This prepares the sample; it creates no pack, roster, person or judgment. The
literal official equivalence rule is preserved. The supplemental compliance,
craft and factual-support rubric is Buddha's human-review rubric, not official
numeric utility scoring or a new human quality scale.

Target repair remains a different review of development opportunities. Existing
manual worksheets suffice; no new schema, scoring instrument or runtime driver
is needed merely to collect them. Native Codex usage consumes the user's Codex
plan outside the experiment's API ledgers. Report available context/stage usage
and its unpriced monetary component separately; label productivity calculations
as execution-only, without claiming a priced total-research-cost advantage.
Host limits leave explicit missing/incomplete review coverage. No actual study
reviewer or completed judgment is being claimed by this preparation.

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
passes existing study/assessment and full-grid data checks. The next comparison
will use the unchanged original-call capacity mode expressly allowed by DESIGN §4;
there is no new requirement to guarantee acceptance of every future request
before sending it. The separate documented model input limit and absence of a
pre-send counter remain known limitations, with full-feedback and partial-stop
guards preserved. The [readiness supplement](conformance/imp01-wildchat-readiness.json)
records standard-speed request exclusion, runtime metadata availability and
conditional cost/headroom arithmetic. The [matched launcher](IMPROVER-LAUNCH.md)
and refreshed configuration now have bounded local checks. The prospective
review controls are prepared too. Present the combined decision on the separate
execution allocation and named native-reviewer setup, then adopt the pinned
protocol before any owners or outputs. Actual funding, keyed account review and
current executing-code checks still precede a live command. No new funds,
owner or launch command follow from this preparation. This remains the original
IMP-01 comparison; the DGM/Harness2 cross-check adds no redesign or new gate.
