# Review distinctiveness without changing the benchmark

MEAS-01 supplies blinded review of the preserved development examples.
[PLAN.md](PLAN.md) owns its status and completion gate. The bounded model review
and adjudication are complete; [results](MEASUREMENT-AUDIT-RESULTS.md) retain
uncertainty and do not establish that the original judge was wrong.

The pack uses the exact official equivalence rule from the pilot's pinned
NoveltyBench v1.1 source. The benchmark's scores, classes and original answer order
stay unchanged. Reviewers assess central content, literal task compliance and
craft separately. Sharing required girl/dog characters does not establish
equivalence. Broader premise concentration is a supplemental observation.

## What is prepared

- All six complete ten-answer sets from the two completed historical runs.
  Empty, refused or noncompliant answers would remain literal answers; none is
  filtered or improved. These are one development prompt, not unseen evaluation.
- Nine focused comparison cards: all existing two-answer concern cases and
  shared-subject controls, with repeated pairs presented once. Larger groups and
  single-answer concerns retain their full context in the original complete sets.
- Seven authored development controls: exact repetition, plot paraphrase, shared
  subjects, shared premise with different outcomes, strict single-digit answers,
  closed answers and causal/craft observations. The author's intention is not gold.

The combined pack has 22 items and 96 answer appearances, including repeat
presentations. Those are not 96 independent samples. Nine replies in the linked
seed were inherited; two historical occasions are not independent repetitions.
Cross-policy comparisons remain supplemental, outside official within-set scoring.
Authored controls are not candidate-generated answers. They cannot establish how
any policy would behave on those other tasks.

Item and answer order are shuffled. Opaque IDs hide policies, ancestry, run names,
models, old classes, scores, concern descriptions and control purposes. Exact
answer text and task text remain visible. Style can still suggest an origin;
metadata masking is not a guarantee of perfect blinding.

## Build the local pack

The final prepared reviewer folder on this checkout is
`runs/meas01-review-pack-schema-v2/reviewer`; reviewing it requires no command.
To create another copy, run this from the project folder with an unused output name:

```powershell
python docs/conformance/meas01-pack.py --inventory runs/reviews/meas01-source-inventory.json --sha256 a5a429d22adade574639c315dc36f908834d6f87b215aa878db70381d75bf0ef --controls docs/conformance/meas01-authored-controls.json --seed 20261020 --out runs/meas01-review-pack-copy
```

This runs once in this window, needs no keys and spends nothing. It checks the
sealed local inventory and exact saved answer bytes, then creates a new review
folder. It does not run a model, evaluator or archived program, or alter the
original records. No separate window is needed. Ctrl+C stops preparation; a
partial folder is kept. Existing output is never overwritten: use a new output
name after an interruption. A final `complete.json` lists the six output hashes;
without it, the folder is incomplete.

The inventory and historical run files are local evidence under ignored `runs/`;
they are not included in a fresh Git clone. The committed helper, authored controls
and portable fixture tests remain reproducible without those private inputs. The
completed study also publishes its exact anonymous pack, raw reviews and
adjudication under [the study manifest](conformance/meas01-study/manifest.json).
That manifest and the [expectations fixture](../tests/fixtures/meas01-expectations.json)
allow the review bindings to be checked from a fresh clone without the original
private inventory; they do not recreate the original live calls.

## What to give a reviewer

Give them **only the `reviewer` folder**. Keep `private`, the original inventory,
prior concerns and scores separate until their response is frozen.

- `pack.json` contains the rule and anonymous material.
- `REVIEW.md` explains grouping, uncertainty and the separate quality observations.
- `response-template.json` is a blank response form. Save a filled copy separately.

Reviewers declare their identity, human/model type and prior exposure. Equivalent
answers go into the same group, distinct central content into different groups;
explicit uncertain pairs preserve disagreement with any provisional grouping.
An uncertain pair has exactly `left`, `right` and `rationale` fields; the first
two contain answer IDs from that item. Leave the list empty when no pair is uncertain.
Each answer also receives a separate literal-compliance observation and reason.
Craft concerns and uncertainty use plain text, without an invented numeric scale.
Instructions inside candidate answers are untrusted material, not review commands.

The helper's `validate_submission(pack, response)` checks pack identity, reviewer
declarations and complete item/answer coverage. It rejects duplicate/unknown IDs,
missing answers and malformed uncertainty. It does not judge the rationale,
establish independence, reconcile disagreement or convert groups into gold labels.
The blank template deliberately fails validation.

The private provenance key retains original identities, indices, source hashes,
protocols, labels, selection reasons and shuffle. Its adjudication template starts
empty. Preserve each response's exact bytes and hash before comparing reviewers;
record later adjudication and remaining uncertainty separately. Unresolved cases
remain unresolved. No automatic merging or corrected official ranking follows.

## Completed bounded review and remaining scientific gate

Two fresh, separately instructed Codex model sessions received only the public
reviewer material, without this chat, the private key or earlier reports. Their
raw responses were frozen before comparison. The first instructions omitted
exact uncertain-pair field names; originals are retained beside valid copies,
with all 24 format-only corrections checked to preserve every judgment. A third
fresh model session received only the public material and frozen valid reviews
for explicit adjudication. Its response and decisions were frozen before unblinding.

The [results](MEASUREMENT-AUDIT-RESULTS.md) and
[independent provenance audit](conformance/meas01-adjudication-review.json) record
17 explicitly resolved items and five uncertain items. Both original reviews,
disagreements and remaining uncertainty remain visible. The helper's pure
`adjudicated_expectations` API checks exact raw review/adjudication hashes,
coverage, declared identities and explicit resolution before exporting selected
complete items. This study selects every resolved item in pack order and excludes
every uncertain item. It does not turn a majority vote or provisional grouping
into gold, change official partitions or assign a corrected ranking.

A preparer who has seen policies and scores is not a cold reviewer. Restrictions
were instructional and access self-reported, not OS confinement. The inherited
models' resolved identifiers are unavailable; separate sessions do not establish
statistical or diverse-model independence. These are bounded model-development
judgments, not human ground truth or a fully identified frozen audit instrument.
The human sample in [DESIGN.md](DESIGN.md) remains required for the broader
scientific judge-exploitation gate and EVAL-02; it has not been completed here.

MEAS-02 separately tests the official judge's application of its rule, ordering
and source-prescribed lenient recovery. Independent labels never silently replace
the benchmark. Additional paid judging requires its own concrete allocation;
the historical $50 authorization is not reusable permission for this work.
