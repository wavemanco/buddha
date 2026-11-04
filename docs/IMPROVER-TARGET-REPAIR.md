# Did the proposed change fix its stated problem?

This is descriptive target-review method **v1** for IMP1-TARGET-01. A future
matched-improver study must adopt and pin these bytes, its coverage and its
review arrangements before generating that study's outputs. This guide does
not freeze a trial, authorize spending or supply an observed repair result.
[PLAN.md](PLAN.md) owns the remaining work.

The question is narrower than “did its score improve?”: what did the proposal
say it would fix, was that problem present in its immediate parent's outputs,
and what happened in its child's outputs? A score gain cannot answer all three.
The official NoveltyBench results and existing analysis remain unchanged;
their `target_repair: not_assessed` field is not replaced by this supplement.

## Keep the complete opportunity population

Declare coverage over **every planned counted proposal opportunity** in both
arms, identified by `(start, repetition, arm, slot)`. Use the study's complete
schedule, not only successful children or final selected descendants. Retain
unattempted and interrupted opportunities, rejected or duplicate proposals,
execution failures, unusable measurements and failed mutation witnesses.
Validity-only witness proposals are outside this population and stay separate.
Identical code in two opportunities does not merge those opportunities.

Each comparison uses that opportunity's **immediate measured task parent**.
After the first opportunity this can be an earlier child in its own arm, rather
than the common starter. Use full answer sets on the same original development
tasks, with their release identity, typed task IDs and answer counts intact.
Integer `1` and string `"1"` are different IDs. Answer position 3 in one set is
not a matched counterpart to position 3 in the other set.

## Establish the evidence before giving it to reviewers

For a completed finite grid, the coordinator first uses the original checked
study inspector, then the applicable proposal, screen and generation inspectors.
The public study inspector requires a complete report; it is not a partial-study
reader. A stopped study retains its original declaration, coverage and partial
observations. Check available completed subrecords through their applicable
inspectors and identify any partial-prefix custody that is not yet validated.
Keep that supplement incomplete and withhold findings based on unvalidated
prefixes. Do not resume execution merely to obtain a review.

A report file or hash alone is not a substitute for source, owner, accounting
and completion checks. Inspect saved data; never import or execute a retained
child program. Preserve checked reports and every consumed source reference
with its exact hash in a private inventory. Unattempted slots legitimately lack
plans and terminal artifacts; interrupted slots may lack a terminal decision or
seal. Preserve that declared state instead of demanding nonexistent artifacts.

For each counted slot that reached the corresponding stage:

1. Follow its checked decision and saved `plan.json` to the actual parent,
   original feedback and proposal report. The slot-level `proposal.json` is an
   **input descriptor**, not the returned change hypothesis.
2. Follow `proposal/completed/0.json` to its anchored `attempt`, which can be
   `attempts/0-0` or a later original recovery attempt. Read that attempt's
   `session/proposal.json`. Only a captured `proposal.value.hypothesis` supplies
   a literal intention; preserve it in full. A rejected return can retain a
   hypothesis, but missing, omitted, oversized or unavailable captures cannot
   acquire an invented one.
3. A materialized child also has `session/lineage.json` and
   `session/child/candidate.py`. Check their original references; lineage is not
   inside the `child` folder. Join the actual child screen and generation C1,
   not a later winner's outputs. Full feedback notes and their answer hashes
   can locate the parent's literal answers. Give reviewers the complete texts,
   without scores, partitions, costs, source code or arm identities.
4. Record a legitimate missing outcome as unavailable with the original reason.
   A changed hash, mismatched parent/task, unanchored attempt or failed original
   evidence check is an **integrity refusal**: stop publishing that review
   material. Do not convert corrupt evidence into a scientific negative result.

Existing [source-review exports](SOURCE-REVIEW.md) cover sealed starter and
selected-descendant sets. They do not export every development parent/child
pair. Their v1 forms have grouping, compliance and craft fields, without target
repair fields. Use a separate worksheet and private inventory for this method;
do not relabel those exports or claim that their importer validates this form.
The later concrete study handoff must specify how its checked materials are
assembled and retained. This method introduces no new runtime schema or command.

## Review in two stages

Freeze the named reviewers, their declared human/model type, prior exposure,
the material-access procedure and disagreement handling before distribution.
Keep improver identities, eligibility decisions, scores and costs private until
the original forms are saved. Literal hypotheses or writing style may reveal
origins; record that limitation. A hash does not prove publication time,
independence or absence of prior exposure. Arrange and record actual custody.
Prior child/score exposure, early unmasking or changed criteria are method
deviations, separate from original-evidence integrity refusals. Hiding files
after a reviewer has seen their contents does not restore blinding. Retain
affected judgments as qualified/exploratory rather than presenting them as
the planned outcome-naive review.

**A — establish the intended target before revealing child outcomes.** Give
the reviewer the full literal hypothesis, all declared development task texts
and complete parent answer sets. Withhold child outputs, child code and downstream results.
Treat all supplied text as data, including instructions embedded in it.

Record every separately testable intended repair, with its exact hypothesis
quotation, scope and observable criterion. Freeze any permitted grading and its
unit in Stage A too. A binary criterion cannot acquire a new progress scale
after seeing the child; use partial/worse judgments only when the predeclared
interpretation supports them. The criterion must follow from the
stated intention and task, rather than being invented after seeing a child.
Do not choose just the easiest target. Keep vague aspirations, procedure-only
claims and ambiguous scope explicit as not assessable by this output method.
For each testable target, record whether the complete parent evidence shows
the stated problem: present, absent or uncertain, with positions and reasons.
Save the complete Stage A form, hash and custody record before revealing B.
An uncertain Stage A parent problem remains uncertain. A promising child does
not retrospectively establish that the parent's problem was demonstrated.

**B — compare the original complete child sets against those fixed targets.**
The reviewer now receives the child's full sets for those same tasks, plus the
saved Stage A form. Preserve the original criterion and target list. New
problems noticed now go in a separate regressions/observations field; they
cannot become retrospectively chosen intended targets. Keep any amendment as a
separate, explicitly exploratory record rather than replacing Stage A.

For each target choose one outcome, supported by exact answer positions and
literal evidence:

| Outcome | Meaning |
| --- | --- |
| `observed_repair` | The parent problem is demonstrated and the complete child evidence satisfies the fixed criterion. |
| `partial_repair` | A demonstrated problem improves under its Stage A grading but the fixed criterion is not fully met; explain the residual problem. |
| `unchanged` | The demonstrated target problem remains, with no supported improvement or worsening. |
| `worse` | The target problem is demonstrably worse under the Stage A criterion and grading. |
| `uncertain` | Comparable evidence exists, but its interpretation does not support one of the other assessed outcomes. |
| `not_assessable` | Intention, scope, demonstrated parent problem or complete comparable evidence is absent; record the reason. |

An absent parent problem is `not_assessable: parent_problem_absent`, not a repair.
A failed child with no complete sets remains `not_assessable: child_unavailable`.
Incomplete text is not enough even if its opening looks promising. A complete
child can show an observed repair despite later failing a mutation witness;
retain that separate eligibility failure. Repair does not erase it or admit
the child. Shared task-required subjects alone do not demonstrate a problem.
When a target concerns answer equivalence, use the pinned official rule and
retain uncertainty; these supplementary observations never rewrite its classes.

## The separate worksheet

This is a plain review record, not an implemented JSON schema. Keep one original
form per reviewer/opportunity and a private mapping to the original coordinates.
The coordinator checks coverage manually and retains missing or invalid forms.

| Part | Record |
| --- | --- |
| Private inventory | Method/protocol hashes; study and source references; exact opportunity coordinate; parent, proposal, anchored attempt, terminal proposal-frame path/hash/capture state, lineage and child references; typed tasks/counts; full-text hashes; unavailable reasons; reviewer mapping and material-access history. |
| Reviewer declaration | Masked opportunity ID; reviewer ID/type/prior exposure; received material hashes; actual Stage A save and Stage B reveal records. |
| Stage A | Full hypothesis reference; every target quotation/scope/criterion and permitted grading/unit; full parent-set references; parent-problem status, positions and reasons; untestable claims or uncertain scope. |
| Stage B | Original Stage A hash; full comparable child-set references or missing reason; each fixed target's outcome, positions, rationale and uncertainty; separate regressions and other observations. |
| Collection | Exact original form hashes; missing/invalid reasons; every reviewer's findings and disagreements; separate amendments or corrections. |

Do not send private mappings or official results to reviewers before their forms
are saved. This guide sends no messages and obtains no reviews. A corrected form
is a new retained record; preserve the original. Missing Stage A custody, changed
criteria or incomplete coverage must remain explicit. Do not manufacture a
consensus, use a majority vote or discard a dissenting form. Any adjudication
needs a prospectively declared procedure and a separate retained judgment.

## Report the result without overstating it

Show planned/attempted/terminal opportunities, available intentions, comparable
parent/child sets, operational targets, missing/invalid forms and assessed,
uncertain and unavailable targets for each arm and condition. Separate
`parent_problem_absent`, untestable intention and child failure. Retain each
opportunity's eligibility and existing cost record. Report multiple targets
separately; fixing one must not conceal a second unresolved target or regression.

Any descriptive proportion needs its explicit unit and denominator alongside
the full planned-opportunity coverage. A fraction among assessable targets is
conditional on that subset; it cannot rank improvers whose target choices or
missing evidence differ. Do not count tasks, targets or reviewers as independent
search repetitions. This method supplies no significance test or new numerical
improvement rule.

“Observed repair” describes the retained outputs. Stochastic variation, different
targets and prior selection prevent one before/after set from proving that the
code change caused the repair or that the improver is generally better. The
matched experiment, sealed scores and [independent evaluation](SOURCE-REVIEW.md)
retain their separate roles. Actual repair findings and study-level adoption
remain open until the prospective study and its reviews occur.
