# Reviewing current source-agent outputs

This bridge prepares complete answer sets from a saved final evaluation for
independent review. It supports the ordinary final controller and the matched
improver assessment. It does not generate answers, contact a provider, resume a
run or change an official NoveltyBench score.

The reviewer sees the task, every literal answer in each selected set, the
pinned equivalence rule and the pinned task-quality rubric. Source identities,
roles, lineage, original positions, official scores and accounting stay in a
separate private receipt. Blank and refused answers stay visible.

This is the export part of EVAL-02. Importing and reporting completed reviews,
the explicit transfer phase and the actual independent human study remain open.
No human judgments or scientific improvement are established by a working export.

## Select the sample before generating answers

Before preparing trial owners, write a `buddha.source-review-plan.v1` JSON file
with these exact fields:

| Field | Meaning |
| --- | --- |
| `experiment_id`, `kind` | The original experiment ID and either `final` or `improver`. |
| `tasks_sha256` | The complete original TaskSet fingerprint, including typed IDs and counts. |
| `seed` | A nonnegative integer used to mask display order reproducibly. |
| `protocol`, `materials` | Original absolute `path`/`sha256` references to the protocol bytes and reviewed rule/rubric material. |
| `sets` | A nonempty list of whole-set coordinates: `role`, `role_index`, `task_id`, `repetition`. |
| `format` | Exactly `buddha.source-review-plan.v1`. |

Add the plan, protocol, materials, current `buddha/source_review.py` and current
`buddha/policy_panel.py` as original `custody.evidence` references before trial
preparation. Existing trial machinery carries those pins into frozen controls
and original owner inputs. The exporter rejects missing or changed controls.
Existing completed runs cannot acquire a prospective sample afterward.

For ordinary finals, roles are `candidate` and `comparator`; `role_index` is the
zero-based position within that role. For improver assessments, roles are
`starter`, `initial` and `evolved`; the index is
`start * development_repetitions + development_repetition`. `repetition` selects
the sealed generation repetition. Integer task ID `1` and string ID `"1"` remain
different tasks.

These logical coordinates stay stable when an improver fails to produce a valid
descendant. The private receipt maps them to the actual frozen arm numbers.
An unavailable selected descendant remains an explicit `no_valid_descendant`
entry, and the review materialization is `incomplete`. Equal source code or
equal answer text never causes separate roles to be merged.
If every selected set is unavailable, the receipt records
`no_selected_answer_sets_available` and the three reviewer artifacts are `null`.
It does not emit an empty pack that the existing submission validator rejects.

Every selected set contains all original answer positions. Selection is bounded
by the existing 100,000-position panel ceiling and JSON/evidence limits. A pinned
sample alone does not establish representative sampling, publication time or a
reviewer's independence. The actual study must freeze its sampling and review
protocol before execution; this implementation invents no sample-size threshold.

## Developer interface and files

`buddha.source_review.materialize_source_review` takes the original trial root,
trial kind, exact saved final-report hash, original plan path and its exact hash.
It returns four separate values:

- `packet`: the existing `buddha.meas01-pack.v1` reviewer schema, with complete
  literal text and masked item/answer IDs.
- `template`: the existing `buddha.meas01-submission.v1` response schema. Grouping,
  compliance, rationale, craft and uncertainty fields start unfilled.
- `review`: plain-English review instructions and the pinned quality rubric.
- `private`: selection and availability coverage, original-position mapping,
  C1/report/schedule/source/owner/ledger hashes, consumed-file hashes and accounting.

The function returns data; it writes no files. Keep the private receipt away
from reviewers. Serialize reviewer JSON with `encode_review`, which preserves
the historical pack encoding, including its final newline. Hashing compact JSON
instead would produce a different pack identity and fail the existing submission
validator. The template deliberately fails validation until someone fills it in.

The exporter reconstructs the complete original report through its existing
checked reader, then keeps that observation alive while extracting selected C1.
It checks consumed bytes, database sidecars and the original final and sibling
validation/development trees again before returning. A change during observation
is a typed error, never a partially trusted pack. No producer source is executed.

Masking is procedural: styles and prior exposure can reveal origins. Display
order must never replace original generation order when interpreting utility.
Reviews remain separate observations; they do not automatically become consensus,
gold classes, improver feedback or revised official scores.

## Optional offline check

Run from the checkout containing this slice:

```powershell
python -m unittest discover -s tests -p test_source_review.py -v
```

This runs the export's automated checks once, using temporary test runs and
supplied replies. It spends no API money and needs no keys or separate window.
The two composed paths took about 15 minutes on the current Windows checkout,
including test-run preparation and repeated integrity checks. That is a whole-test
duration, not the time for one export; machine load and later changes can affect it.
Press Ctrl+C to stop it; an interrupted check is not a passing result.

There is no live-run or reviewer-distribution command in this slice. The operator
handoff will document exact commands when the review import and study protocol
are ready.
