# Measuring what Buddha adds to the same model

This is a prospective comparison specification under EVAL-02 in [PLAN.md](PLAN.md).
It is not a new roadmap, an adopted experiment or a funded live run. The fixed
NoveltyBench evaluator remains the yardstick; this comparison tests Buddha.

The question is: does a frozen Buddha agent produce more useful, distinct
answers than direct use of the same underlying generator model?

This question can accompany the original-versus-evolved improver study. Reuse
prospectively compatible frozen Buddha results and add the declared plain-model
references; it is not a choice between mutually exclusive research goals. The
user's questions did not request reprioritizing or replacing the prepared
bounded study. Its three development tasks and 26-task final panel remain the
current development scope, not all 1,000 WildChat tasks.

## Start with one matched pair

Both sampling modes are supported options. They do not require an immediate
four-condition run. A first matched harness measurement can be plain versus
frozen Buddha in one prospectively selected, verified sampling mode. Its result
applies to that mode. Add other conditions only for a declared question and a
separately costed scope; do not choose modes after seeing favorable results.

The complete optional design is:

| Condition | What the generator receives |
| --- | --- |
| Plain, independent | The original task in a fresh conversation for each answer |
| Plain, in-context | The original task, then earlier answers and the official continuation request |
| Buddha, independent | The frozen Buddha procedure with independent answer sampling |
| Buddha, in-context | The same frozen Buddha procedure with earlier-answer context |

Use the same selected generator model within the chosen comparison. Repeat the
comparison separately for another backbone; do not pool different model IDs
into one same-model harness effect. Current supported routes are OpenAI and
Anthropic; each selected model still needs compatibility and price checks.

The standard generator supports both sampling modes. Arbitrary evolved Python
can ignore the requested mode, batch answers or introduce another procedure.
Before labeling an arm independent or in-context, check the actual outgoing
history and answer-production trace. A host configuration string is not proof.
If a frozen agent cannot implement a declared arm, record that incompatibility;
do not relabel its batch or mixed procedure as standard in-context generation.
Changing its code would define a different frozen agent and intervention.

## What stays matched

Freeze the common task IDs and prompt families, answer count, repetitions,
requested/resolved model identity, low reasoning effort, output allowance,
processing tier, call/token/resource ceilings, evaluator revision and judge
settings before observing comparison results. Use the official native prompt,
partition, utility, fallback and patience rules unchanged.

The plain controls use empty Buddha instructions and the existing fixed-seed
baseline route. They receive no Buddha planner, improver, critique, selection
or learned memory. Shared logging, accounting, isolation and official scoring
are administrative infrastructure and can be reused.

Use ten answers per task. At the current official CLI allowance of 2,048, the
reasoning-generation helper supplies 4,096 inclusive reasoning/output tokens
per request. Keep the [checked request settings](REQUEST-SETTINGS.md) explicit.

Equal ceilings do not mean equal actual consumption. A direct control normally
uses ten generation calls; a Buddha agent might batch, plan or select. Retain
every call and billed token, including reasoning, and disclose extra resources.
Do not generate extra raw answers merely to discard them and burn a budget.
A comparison with unequal resources can measure the declared systems' outcomes;
it cannot by itself isolate a harness effect independent of additional compute.
Report inference costs and total search/proposal/research costs separately.

## How the results would be interpreted

Pair conditions on the same complete prompt-level answer sets. Report both
official distinctiveness and utility, task compliance, failures, coverage,
uncertainty and the required independent review. Prespecify contrasts and any
multiple-comparison rule; do not choose the favorable mode after seeing results.

Plain-versus-Buddha comparisons within a selected mode address harness added value.
Independent-versus-in-context comparisons within each system address the effect
of earlier-answer context, provided the actual procedures obey the declared
mode. Hold the frozen Buddha agent fixed for that mode comparison. If different
agents are optimized for each mode, report the combined intervention instead.

The separate IMP-01 study compares initial and evolved Buddha improvers, with
Buddha starters as controls. It does not supply these plain-model controls.
Its role schema, original frozen workload and proposed $150 scope stay intact.
The earlier policy study is historical evidence, not a substitute for current
source-harness controls.

## Reuse existing execution

Prepare the needed existing `buddha.native-baseline.v1` descriptor with the reviewed
fixed seed, empty instructions and the selected `regenerate` or `in-context`
mode. Prepare the second baseline only if expanding to the other mode. The seed
source hash can be identical while configuration fingerprints must differ.
Their generation/native selections must share the same frozen seed identity;
the fixed-seed worker is distinct from the source-candidate worker.

One or both plain sampling references can accompany the existing frozen Buddha
procedures without rerunning Buddha under every mode. Those comparisons measure
the declared systems as packages. They do not isolate a sampling-mode effect
unless the compared procedures actually follow the same declared mode. Bind
any added contrasts and uncertainty rules prospectively; the original improver
analyzer does not automatically implement them.

Use the existing baseline preparation, execution, original owners, recovery and
native evaluator. A small checked report join must bind their original evidence
to the declared frozen Buddha arms and reject changed model/settings, tasks,
sampling identities, missing coverage and unsupported results. Preserve partial
work with its reason. Do not extend the closed IMP-01 roles merely to fit controls.

For scale only: a fresh matched plain/Buddha pair on 26 tasks with one repetition
would contain 52 answer sets, or 520 answers. Two plain controls alone would
also contain 52 sets, but would not supply the Buddha arms. A complete
four-condition comparison on that panel would contain 104 sets, or 1,040
answers, unless prospectively eligible Buddha measurements are reused. These
are arithmetic examples, not selected
coverage, approved spending or a power claim. Concrete control/source selection,
analysis, capacity and funding must be fixed before outputs.

The [budget examples](conformance/plain-model-comparison-cost-examples.json)
price these small assessment workloads separately from the proposed $150
improver study. They are token-usage scenarios, not a completion forecast or a
hard cap. More modes, repetitions or backbones require an explicit workload
and resource decision before any live command.

For orientation, at current public Luna/Opus 5 prices:

| Fresh assessment on 26 tasks, one repetition | Answer sets | Answers | Shorter / longer illustrative usage |
| --- | --- | --- | --- |
| Plain versus Buddha in one mode | 52 | 520 | About $6 / $27 |
| Both systems in both modes | 104 | 1,040 | About $13 / $53 |

These examples include generation and official judging, assume ten distinct
groups and no retries/fallbacks, and include reasoning tokens. They exclude
source evolution/development, native Codex reviews and human time. They are
two invented usage cases, not a likely price range. Longer high-effort judging
can cost more. At retained conservative accounting rates the same cases record
about $12/$44 for the pair and $24/$88 for four conditions, before unresolved
holds. The runtime must reserve its conservative maximum, not a typical bill.

Rates were checked against the official [Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
and [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing).
Repeating the assessment or adding another backbone increases the workload.
The four-condition assessment approximately doubles this pair's assessment
work; it does not automatically double the separate $150 improver-study cap.

If eligible Buddha results are reused, only the additional references need
generation and judging. One plain reference adds 26 sets/260 answers; both
plain references add 52 sets/520 answers. The same illustrative public-price
cases are about $3/$13 and $6/$27 respectively, excluding development/review.
No additional reference workload is funded or silently added to the existing
$150 scope. Declare its combined cost and allocation before launch.

## Full benchmark coverage comes later

The current development study is bounded to three development tasks and a
separate 26-task WildChat assessment panel. Running all 1,000 WildChat tasks is
not part of that prepared workload. Report its uncertainty and limited scope.

After freezing a system worth broader evaluation, a full leaderboard-aligned
run needs both 1,000 WildChat and 100 Curated prompts, with the required versioned
artifacts. Curated remains usable as a public benchmark with its development
exposure disclosed; it cannot be certified as unseen evidence here. Broader
public coverage does not replace the separate transfer and human requirements.
More task coverage is useful at that later stage; it is not a prerequisite for
the current bounded harness-development comparison. Quote its separate workload
and costs before proposing execution.

No live command is published by this specification.
