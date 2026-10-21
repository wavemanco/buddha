# Reading the policy comparison

This reader checks saved evidence and produces descriptive comparisons. It does
not run an agent or a judge, request keys, spend money, resume work, repair files,
or release money held for an uncertain request. The live launch guide is still
being prepared; there is no new command for you to run in this slice.

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

This slice supplies evidence checks, the assessment grid and primary arithmetic.
It does not yet generate the entire registered report: category descriptions
and ranges, judging-occasion score/group agreement, and token/cost/recovery
breakdowns still need their reporting layer. `analysis.status = complete`
describes numerical coverage in this narrow output, rather than completion of
that report or the supplemental review. Those prerequisites and a tested live
handoff remain open before the comparison is launched.

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
An absent repair or fallback flag means **unknown**, not “did not happen.” Raw
request model IDs and receipt hashes are retained per owner. Call order, request
counts or equal bodies cannot establish which request judged a particular row.
This reader does not perform the separate raw-reply/official-parser audit.

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

## Python interfaces and ceilings

`buddha.policy_analysis.analyze_metrics(study, assessments)` is pure arithmetic
for already verified observations. It does not verify provenance. It rejects
more than 100,000 scheduled assessments rather than sampling or truncating.

`buddha.policy_results.analyze_study(...)` performs the passive evidence checks
before calling that arithmetic. Required arguments are the run directory,
intent/protocol paths and their trusted hashes, and the explicit original
authorization path; an original partial-observation path is optional. It returns
an in-memory report and writes nothing. Existing bounded file/tree/ledger
readers apply, and the current scientific projection requires three native
stages with separate partition and score artifacts.

These are Python library interfaces, not operator commands. A tested operator
handoff and export command remain the next prerequisite for the live comparison.
