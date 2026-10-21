# The first controlled policy comparison

This is the prospective scientific protocol for PLAN's POL-02 development
comparison. [PLAN.md](PLAN.md) owns scheduling and completion status.
The [intent](conformance/pol02-study-intent.json) fixes the actual source,
membership, policy, models and schedule. This document fixes how we will
interpret the results. Neither creates spending authority or starts a run.

The question is whether the existing child's instructions help, whether seeing
earlier answers helps, and whether those effects differ. This is a small
development study. It cannot establish held-out improvement, human preference,
historical originality or superiority to a leaderboard system.

## What is fixed

The instrument is NoveltyBench 1.1 at official commit
`64a23be6b18ec1dacc298830aab276061b6e143c`, with its literal Curated dataset
SHA256 `ca9b6f470e5d7f7e34a281e2fdaa6f6e51c38bdae075ea580d184139ec391fa7`.
The nine selected source files and exact official command arguments are in the
intent. The paper supplies historical context; the pinned official code governs
this experiment. A later benchmark release requires a separate experiment.

| Setting | Fixed choice |
| --- | --- |
| Generation | Existing `agents/frozen_seed.py`, SHA256 `2b87bfe0d3c97ee45db2d45260985ffe0234eca93967f4689fb7c59f82603921`; OpenAI `gpt-5.6-luna`; 4,096 output-token allowance; existing low reasoning and default service tier |
| Instructions | Empty, or the exact first fresh pilot's child `34cecdbd8a9307796972dcc485641fc7021f97e8b2715a87feeb140ab54f424b` |
| Sampling | Independent (`regenerate`), or earlier answers included (`in-context`) |
| Answers | Ten ordered answers per prompt in every condition |
| Grouping | Official LLM partition, `gpt-5.6-luna`; omitted display seed, output cap, service tier and reasoning effort stay omitted |
| Quality | Official LLM scorer, `claude-opus-5`, prescribed `claude-sonnet-5` fallback, 16,000-token allowance and high/adaptive thinking |
| Utility | Official patience 0.8 and official native summary; no replacement formula |
| Concurrency | Two prompt instances in flight per native command; the outer study cells execute serially |
| Repetition | Two new generation sets per condition; two complete judging occasions per generated set |

The child is the generic policy from run `a0946e22ae1e45d6bf8f74cf9f4f30bb`,
not the different task-specialized child from the linked continuation. Its
literal text and original sampling field are preserved in the intent. The
original saved policy-file SHA256 is
`eb3fdc647d0ca558159cb864d5ec6f15efa2a2f8b02db9f04901b2fad304c50a`.
No new proposal or policy tuning occurs in this comparison.

Arms are 0: empty/independent; 1: empty/in-context;
2: child/independent; 3: child/in-context. Execute generation repetition 0
in arm order 0,1,2,3, then repetition 1 in order 3,2,1,0. Within each cell,
retain the selected prompt order below and judging occasions 0,1. The official
null display seed preserves answer order; a new occasion does not shuffle it.
The reversed second block reduces one obvious scheduling imbalance but does
not establish randomization, independence or immunity to provider drift.

The exact canonical study fingerprint is
`897db6a13c2a3f35bf5dd11e99e5aac20173c1a556f7e55aea9ccfa63a3c19de`.
The [intent](conformance/pol02-study-intent.json) records separate full-source
and selected-task fingerprints, all four arm IDs and all eight cell IDs.

## Which prompts are included, and why

Two fresh model-development source reviews each read all 100 literal primary
prompts before split assignment. They proposed 80 and 89 families, respectively.
The [source review](conformance/pol02-study-source-review.json), SHA256
`6bcf52430668d06456d31e14629dd0ad7093d1656099faba8a8c75cd7a51fcc0`,
preserves both maps, their boundary disagreements and the reconciliation.

We take their transitive union and conservatively hold pet-name, gift, book
and credential variants together, producing 72 custody blocks: 17 multi-prompt
blocks and 55 singletons. These are split boundaries, not judgments that their
answers are equivalent. Five blocks span original categories; each row keeps
its official category. A block's majority category, with source-order ties,
is used only to allocate the split.

The existing deterministic split helper is applied separately in each such
stratum. Starting at seed 0, use the first seed that keeps every known
outcome-exposed block in development and permits two distinct development
blocks per original category. Seed 0 qualifies: 58 development, 16 validation
and 26 final rows, occupying 42/13/17 blocks. These are approximately 60/20/20
group allocations, not exact row quotas. The full membership is in the intent.

Previously inspected outcome IDs 0,47,48,97 bring their whole blocks into
development: 0,1,47,48,94,95,96,97,98,99. All 1,100 supplied primary/paraphrase
strings also received a normalized exact-overlap check. Its only cross-ID
match, 47/48, is together in development. This was not a semantic review of
all paraphrases and does not prove that other near-duplicates are absent.

Start the screen with diagnostic IDs 0,47,97. In original category order,
fill to two per category using SHA256 of canonical `[7,id]`, skipping any
already selected block. The resulting ordered screen is:

| Order | ID | Original category | Brief task description |
| --- | --- | --- | --- |
| 0 | curated-0 | Creativity | Five-sentence girl-and-dog story |
| 1 | curated-47 | Subjective Rankings & Opinions | One of two glass descriptions |
| 2 | curated-97 | Random Generation & Selection | One password digit |
| 3 | curated-15 | Creativity | An interesting invention |
| 4 | curated-20 | Character & Entity Naming | A character name fitting a specified role |
| 5 | curated-26 | Character & Entity Naming | A culturally conditioned baby name |
| 6 | curated-33 | Product & Purchase Recommendations | One teenager's first phone |
| 7 | curated-30 | Product & Purchase Recommendations | An apparel-shopping recommendation |
| 8 | curated-50 | Subjective Rankings & Opinions | An occupation opinion |
| 9 | curated-71 | Factual Knowledge | A Fields Medal recipient |
| 10 | curated-65 | Factual Knowledge | Three television series |
| 11 | curated-86 | Random Generation & Selection | A fruit/vegetable pair |

Descriptions are explanatory; the unchanged literal source prompts govern.
Official categories are retained even where their labels seem debatable.
The twelve tasks occupy twelve distinct custody blocks. Equal category counts
deliberately oversample some categories relative to the 100-row corpus.

This study creates 96 complete ten-answer sets, or 960 answers, and 192
task-level assessments across eight cells and sixteen judging occasions.
Answers, generation repetitions, judging occasions and prompts are different
units. None multiplies the number of independent prompt observations.

The reserved validation/final memberships are prospective custody only.
They are not certified unseen, eligible or independent evaluation populations.
Public benchmark contamination and prior source exposure remain limitations;
EVAL-01 must separately establish eligibility before any held-out use.

## How the official results will be analyzed

Keep distinctiveness and utility separate. Read each task's literal native
`distinct` and `utility`; retain native per-cell summaries and both occasions.
Do not reconstruct metric math or use a supplemental judgment to replace it.

The primary descriptive occasion is always ordinal **0**, even if it fails.
For each prompt and arm, average that occasion's metric over the two generation
repetitions. Then calculate these prompt-level contrasts for each metric:

- Child instructions under independent sampling: arm 2 minus arm 0.
- Child instructions under in-context sampling: arm 3 minus arm 1.
- History with empty instructions: arm 1 minus arm 0.
- History with child instructions: arm 3 minus arm 2.
- Interaction: `(arm 3 - arm 1) - (arm 2 - arm 0)`.

Report the equally weighted mean over all twelve prompts, every prompt's
values, per-category descriptions and ranges. Show each generation repetition
alongside the average. Do not pool all answers or judge occasions as independent
samples. With twelve chosen development prompts and only two repetitions,
no significance, promotion, practical-effect or population-variance claim is
predeclared. A positive descriptive difference is not a confirmed improvement.

For each fixed answer set, compare occasion 1 with occasion 0: distinct count,
utility, group membership after accounting for arbitrary group labels, and
literal raw reply/parser/repair/fallback outcomes. Report disagreement and
ranges, retaining both results. Do not choose the larger score or replace a
failed occasion 0 with occasion 1. No causal display-order estimate is made.

All arms have equal scheduled generation counts, judging occasions, model access
and per-request output ceilings. Physical quality, repair, retry and fallback
request counts can differ and are reported. In-context sampling uses more input
tokens; actual output/reasoning use also varies. Report tokens and costs by arm,
generation, grouping, quality, retries and fallback. This does not satisfy
DESIGN section 7's matched actual-token
budget superiority gate. That remains an EVAL requirement, rather than being
silently replaced by this exploratory comparison of fixed access and ceilings.

## Failures and incomplete results

Keep literal poor, empty, refused, truncated and noncompliant answers, including
the frozen seed's already declared effective placeholders. They are not grounds
for filtering a task or generating a more favorable replacement. Missing output
from failed generation remains missing; no answer set is invented.

An incomplete schedule is reported as **incomplete**, with the exact stopped
cell/occasion, completed and missing denominators, child reason, retained
liability and costs. It yields no winner or headline comparison based on the
easiest completed subset. Native artifacts remain available as partial evidence.
Recovery uses original owners and received replies, not fresh replacements.

A completed native process is not automatically a numerically complete study.
Missing/nonfinite task `distinct` or `utility`, or absent required head scores,
must remain explicit; preserve native bytes without turning these into zeros.
Null `generation_scores` at duplicate, non-head positions are normal official
behavior and are not missing quality judgments. Do not demand ten head scores
when the official partition contains fewer groups.

## Supplemental blinded development review

This diagnostic examines the meaning of any gains; it is not another official
score. Preselect one task per original category: IDs 0,20,33,47,71,97.
Keep required diagnostics 0/47/97; select the other category representatives
by the same `[7,id]` rank among the twelve. In category order, use generation
repetitions 0,1,0,1,0,1 respectively. Include all four arms and all ten answer
positions: **24 complete sets / 240 answers**, not selected successful stories.

Prepare a fixed masked mapping before viewing generated text. Reviewers see
only the literal task and its complete set, with a deterministic answer-order
permutation derived from SHA256 of canonical `["pol02-panel-v1",task_id,
arm_index,repeat,position]`. Set labels/order use the same construction without
position. Hide arm, policy, original positions, official scores, costs and
generation/judging metadata; retain the mapping privately. Use original
generation positions again when joining review labels to official artifacts.

Use two fresh Codex model-review sessions with no prior study-output context,
then a third fresh masked adjudication of disagreements/uncertainties only.
Keep both original reviews and unresolved judgments; do not force agreement.
Record actor IDs, host/model identifiers where exposed, unavailable identifiers,
prompts, exact input/output hashes and declared access scope. This arrangement
does not establish model diversity, statistical independence or human truth.
Host Codex usage is reported separately as unpriced subscription usage; it is
not claimed free or included as zero dollars in the API research ledger.
If the required sessions are unavailable, record the review as incomplete.
Do not silently substitute one reviewer or a different paid instrument.

Apply this fixed rubric to every answer and full set:

- Literal task compliance: yes/no/uncertain, with the exact unmet constraint.
  Respect count, form, perspective and task-specific requirements; do not add
  a stricter one-word rule where the task did not request one.
- Official-rule equivalence: group the full set under the pinned official
  definition, including repeated central plots with minor variants. Record
  uncertain relations and reasons rather than guessing missing groups.
- Coherence and craft: adequate/inadequate/uncertain where applicable,
  otherwise not applicable. Check whether actions, causes and resolutions fit.
- Broader premise concentration: present/absent/uncertain with examples.
  Shared required subjects alone are not equivalence or a failure.
- Factual support: supported/contradicted/unverified where applicable.
  Reviewers may cite primary sources; preserve URLs/access dates and distinguish
  those checks from model recollection. Without evidence, retain unverified.

Phone/product advice is task content, not current purchasing guidance. Password
controls are literal-form diagnostics, not proof of secure randomness or safe
credential advice. Closed answer spaces do not make a higher distinct count
automatically desirable. Report compliance and judge disagreements separately.

This panel covers half the prompts and one generation repetition. It does not
validate the other sets or close EVAL-02's human assessment requirement. If
panel generation is missing, keep that panel slot missing; do not choose a
different repetition, task or condition after seeing results.

## Registration, execution and local checks

Commit and review this protocol and its hashed intent before new study outputs.
The future launch preflight must pin that reviewed publication and join these
claims to the controller's actual source, study, template, model, task and
funding inputs before any send. A later analysis reader must repeat the join.
This is trusted publication/launcher custody, not automatic enforcement of an
external protocol by every direct controller call or authenticated time proof.
Do not hide analysis bytes inside policy instructions or a release inventory.

The [hydration helper](conformance/pol02-study-freeze.py) reconstructs the
existing PolicyStudy from the locally held official dataset and verifies the
declared identities. It changes no benchmark algorithm or controller API.
Full source-bearing TaskSet/study bytes stay under ignored local storage;
this slice redistributes neither the raw corpus nor an encoded copy. Separate
dataset rights still need review before a distribution beyond this scope.

These optional checks are for a checkout containing this slice. They are not
a live-run instruction and are unavailable in the preserved old execution
checkout until a separate reviewed handoff is supplied. From the newer project
folder, in the same PowerShell window:

```powershell
python -B docs/conformance/pol02-study-freeze.py --source C:\Users\arvik\code\buddha\runs\references\noveltybench-conformance\64a23be6b18ec1dacc298830aab276061b6e143c
```

This checks the nine selected source files, protocol and reconstructed study
once, then prints IDs and hashes. It reads no keys, creates no owners, starts
no containers, writes no study file and spends no API money. Wait for `checked`
or a failure; Ctrl+C stops it. The optional `--output <new-file>` argument
writes the complete source-bearing study to a new local file in an existing
folder; it refuses an existing file, hidden Windows streams and nonportable
filenames. It does not authorize execution. A failure names the intent, source,
protocol/study or output step; check that input or output choice before retrying.

```powershell
python -B -W error::ResourceWarning -m unittest discover -s tests -p test_policy_intent.py -v
```

This runs the intent regression checks once with synthetic source data and
temporary files. It needs no keys, network or Docker and spends no API money.
Wait for `OK` or a failure; Ctrl+C stops it.

The [cost proposal](POLICY-COMPARISON-COSTS.md) is separate from this scientific
protocol. Exact runtime/profile bindings, account checks, authorization and a
tested local handoff must precede execution. The historical $50 and $15
allowances fund neither this study nor its preparation's future API calls.
