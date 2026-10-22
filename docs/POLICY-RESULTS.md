# Reading the policy comparison

This reader checks saved evidence and produces descriptive comparisons. It does
not run an agent or a judge, request keys, spend money, resume work, repair files,
or release money held for an uncertain request. The
[first actual comparison](POLICY-COMPARISON-RESULTS.md) has been read and its
registered masked model review completed. No further operator command is needed
to read that result.

## Two different kinds of completeness

**Publication complete** means the controller saved the entire declared run.
**Analysis complete** additionally requires usable distinctiveness and utility
for every planned task, policy, generation repetition and judging occasion.
A finished program can therefore have an incomplete analysis. Missing values,
refusals and invalid numbers remain visible; they never become zero scores.

The registered study has 12 prompts, four policies, two fresh generation
repetitions per policy/prompt and two judging occasions per answer set. That is
96 answer sets and 192 task assessments. Rejudging a saved answer set does not
create another generated set or another independent prompt.

The primary result always uses the first judging occasion, called J0. Within
each prompt and policy, average the two generation repetitions. Then give each
prompt equal weight. Report five separate comparisons for both native metrics:

| Comparison | Subtraction |
| --- | --- |
| Child instructions with independent generation | Child/independent minus empty/independent |
| Child instructions with history | Child/history minus empty/history |
| History with empty instructions | Empty/history minus empty/independent |
| History with child instructions | Child/history minus child/independent |
| Interaction | The child-instruction difference with history minus that difference with independent generation |

Later judging occasions stay in the assessment table. They never replace an
unfavorable or missing first occasion. If any required assessment is missing or
unusable, the overall comparison is absent. Available prompt-level values remain
diagnostics. These descriptive results alone do not declare a winner,
statistical significance, held-out improvement or a successful promotion.

The report also describes the original categories, generation repetitions,
judging disagreement, saved recovery metadata and recorded tokens/costs.
`analysis.status = complete` describes numerical coverage. It does not mean the
supplemental review or the controlled experiment is complete. The
[pre-answer mapping](POLICY-PANEL.md) fixes masked coordinates from pinned study
metadata. Its separate [passive materializer](POLICY-PANEL.md#materialize-original-saved-generation)
assembles complete available answer sets from anchored original generation,
even if later judging is unfinished. Missing coverage and provenance stay in a
private receipt. The actual POL-02 handoff, account checks, allocation, execution,
saved-result analysis and registered model review have now completed at their
stated scope. The result report preserves uncertainty and task failures; it
does not close the later human scientific assessment or held-out gates.

## Categories, repetitions and judging disagreement

`registered.descriptive.tasks` retains each selected task's literal prompt and
original source category. Category labels are not inferred from the answer or
changed to suit a result. The generation-repetition table shows each J0 value
beside its prompt/arm mean, preserving missing values. Category ranges describe
those prompt means and the five prompt-level contrasts; they do not pool answers
or give a category extra weight in the overall comparison.

Each category reports planned, observed and usable coverage. A task counts as
observed when at least one J0 assessment is present. `complete_observed_tasks`
requires every planned J0 assessment; `usable_tasks` requires both metrics in
every one. Range completeness is per metric. The `available_range` describes
the values present, with their count.
`complete_range` stays null until every value required for that range is usable.
Available values never replace the planned denominator or produce a headline
comparison from a favorable completed subset.

`registered.judge_agreement` compares each saved answer set's later occasions
with J0. In this study that means J1 minus J0 for distinctiveness and utility,
with the two-value range and any missing reason. Group comparisons ask whether
each pair of original answer positions is together or apart on both occasions.
They ignore arbitrary group numbers and retain the changed pairs. Equal group
counts can therefore accompany changed membership. Ten answers have 45 such
pairs; these dependent relations are descriptions, not independent samples or
evidence that a judge is right. A missing partition leaves agreement unknown.

## What gets checked

The caller supplies the reviewed intent and protocol hashes. The reader matches
them to the original study, selected prompts, policies, repetitions and execution
order. A matching hash establishes file identity; evidence that the plan was
published before outcomes remains a separate requirement.

Each generated answer set must have its original task, agent, settings, raw
answer file and native answer-file identities. Each judging occasion must use
that same set. Native command settings and staged inputs must match the declared
release. Original stage seals must cover the files actually present, and the
original spending authority must contain the matching completed-owner anchors.
Completed-stage reports must show successful process exit and removal of owned workers.

The reader consumes database bytes into memory; it never opens the original
database for SQL or constructs a spending authority. It checks the consumed
bytes again before returning. If files change, a journal is active, or evidence
contradicts itself, it fails with a fixed error and leaves the evidence intact.
This is a stable observation, not an atomic live snapshot or a provider attestation.

Retired controller, agent and official program paths are treated as stored
hashes. Their original programs are neither required nor executed. Required
study/configuration/answer/result data must still be retained. A stored source
hash does not mean the original source bytes have been archived or reread.

## Native scores and their limits

The separate host-side `buddha.noveltybench_results` adapter reads the saved 1.1 row schema.
It checks ordered, typed task IDs, original prompts/answers, class labels and
head-score coverage. It does not recompute utility, repartition answers or
replace official decisions. A duplicate answer's non-head quality score may
legitimately be null. A native refusal or missing head score leaves utility
unscored. Opaque native summary bytes, including nonfinite values, are retained
by hash rather than rewritten into a favorable summary.

Stored cache keys, configuration and repair/fallback metadata remain visible.
`registered.recovery` retains the literal `repair_attempts`, `lenient`,
`fallback_judge`, `fallback_calls` and `unscored` values for each task and
occasion, with their availability. An absent or null repair/fallback value means
**unknown**, not “did not happen.” A recorded value is evidence of saved metadata;
it does not by itself attest execution of the native parser or recovery path.

Raw request model IDs, response hashes, HTTP status and evidence flags are
retained with the original operation. Each operation's `reply_status` also
preserves OpenAI finish reasons or Anthropic's stop reason. For OpenAI, it
records whether each message has a refusal field, whether that field is null,
whether a refusal string is nonempty, and the string's hash. It exports no
refusal text, answer content or thinking text. Anthropic's refusal indication
is its literal stop reason rather than a separate message field.

Missing or malformed status fields remain null with an unavailable or partial
status and a reason. Other available status fields, usage and recorded money
remain separate. A normal finish or refusal indication does not establish
success of the official parser, explain a fallback or prove that repair ran.
Call order, request counts or equal bodies cannot establish which request
judged a particular row. The reader keeps parser recovery and row attribution
unknown; it does not perform the separate raw-reply/official-parser audit or
replace the official outcomes.

This scientific projection is separate from the generic execution route.
A compatible new benchmark release can still run its first unchanged-agent
baseline through configuration and checks. Its result schema must be reviewed
before using this 1.1 projection; a schema change does not require replacing the
agent, accounting or baseline controller. No unknown future release is certified.

## Partial results and money

Without an observation path, analysis requires the complete root report. A
partial result requires an explicitly selected original `observations/N.json`.
There is no automatic “newest attempt” selection. The saved completed prefix
and earlier judging occasions declared by the serial stop coordinate can be
read; later recovered results and unsealed stopped-child rows are not added.
The full planned assessment grid stays present, with unavailable entries marked
missing and the original reason retained.

Accounting reports current study-owner costs and liabilities separately from
the current shared authority and the old report's authorization observation.
An old observation is retained historical data, not current permission to spend
or authenticated evidence of when capture occurred. Original receipts and
uncertain holds remain unchanged.

A known funded study owner with missing original records makes the evidence
invalid; it does not indicate zero cost or work that has not started.
The results reader and packet reader share this check.

`registered.accounting` describes every operation under the study's present
owners, including stopped owners and operations with no saved response. It
reports totals by arm, generation/grouping/quality/summary stage, arm and stage,
and requested model. Generation is counted once for its original cell; rejudging
the same answers does not add another generation cost. These current amounts
can include recovery after an older selected observation. They do not extend
that observation's scientific coverage or rewrite its historical money snapshot.

Recorded actual charges are `spent_microusd`. Unfinished operations retain their
reservation as `reserved_microusd`; committed money is spent plus held. Each
operation also retains its original reservation, but a completed operation's
reservation is no longer a hold. An unknown request's actual cost remains null;
the reader neither estimates a final charge nor releases its reserve.

An operation count is a count of ledger attempt records. A `reserved` attempt
can be unsent: preparation may fail before dispatch. State counts and saved
response counts stay separate; neither is advertised as a confirmed count of
network calls. When a completed operation also retains an earlier checkpoint,
the terminal receipt supplies the observation once. Otherwise an available
checkpoint supplies raw evidence while the unfinished state and hold remain.

Token summaries give `known_input_tokens` and `known_output_tokens` alongside
known/unknown operation counts. Complete `input_tokens` and `output_tokens` are
null if any operation lacks usable usage evidence. A known subtotal is not a
complete total. OpenAI completion counts already include reasoning tokens;
Anthropic input totals include reported cache creation/read tokens. The existing
billing decoder counts these once. Unavailable or malformed usage does not erase
recorded charges or holds.

The physical-retry view uses the saved request's attempt index: an index above
zero is another physical attempt within that logical call. It does not identify
native parser repair, a new generation set or a new judging occasion. Missing
request evidence leaves this classification unknown. The quality-fallback view
reports whether the requested model equals the explicitly configured fallback
model; absent or ambiguous fallback configuration stays unknown. Observing that
model does not prove why it was called, pair it with a particular refusal or
assign it to a native task row. Retry and fallback views overlap the arm/stage
totals and must not be added as extra expenditure.

## Python interfaces and ceilings

`buddha.policy_analysis.analyze_metrics(study, assessments)` is pure arithmetic
for already verified observations. It does not verify provenance. It rejects
more than 100,000 scheduled assessments rather than sampling or truncating.

`buddha.policy_analysis.describe_observations(study, analysis, occasions)` adds
the category, repetition, judging-agreement and literal recovery views to
already verified observations. It does not establish provenance. It rejects
more than 1,000,000 planned answer-pair comparisons before constructing them.

`buddha.policy_results.analyze_study(...)` performs the passive evidence checks
before calling that arithmetic. Required arguments are the run directory,
intent/protocol paths and their trusted hashes, and the explicit original
authorization path; an original partial-observation path is optional. It returns
an in-memory report and writes nothing. Existing bounded file/tree/ledger
readers apply, and the current scientific projection requires three native
stages with separate partition and score artifacts. Its operation report rejects
more than 100,000 recorded operations across the study, including operations
whose request or response metadata is unavailable.

The provider-status projection uses the existing response decoder's 16 MiB
byte ceiling. It accepts one to 128 OpenAI choices and preserves their status
positions. An empty, malformed or larger choice population produces an explicit
unavailable status; it is never silently truncated. This status limit does not
remove the operation, its usage evidence, its charge or its hold.

These are Python library interfaces, not operator commands. A tested operator
handoff and export command remain the next prerequisite for the live comparison.
