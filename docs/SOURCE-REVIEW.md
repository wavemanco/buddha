# Reviewing current source-agent outputs

This bridge prepares complete answer sets from a saved final evaluation for
independent review. It supports the ordinary final controller and the matched
improver assessment. It does not generate answers, contact a provider, resume a
run or change an official NoveltyBench score.

The reviewer sees the task, every literal answer in each selected set, the
pinned equivalence rule and the pinned task-quality rubric. Source identities,
roles, lineage, original positions, official scores and accounting stay in a
separate private receipt. Blank and refused answers stay visible.

This is the source-output review bridge in EVAL-02. Export and passive review
import/reporting are implemented, including the offline export command below.
A collection command, the explicit transfer phase and the actual independent
human study remain open. Working review machinery does not establish human
judgments or scientific improvement.

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

## Export files for reviewers

The operator command checks the original saved evaluation, then writes a separate
review folder. Before trial owners are prepared, also pin the current
`buddha/source_review_handoff.py` and `buddha/source_review_results.py` in the
original `custody.evidence`, alongside the sample controls above. The new command
cannot retrofit these control pins or a prospective sample into an old completed trial.

Run this from the checkout containing the approved trial's pinned helpers:

```powershell
python -m buddha source-review-export --help
```

This prints the available flags once. It writes nothing, spends no API money,
needs no keys or separate window, and can be stopped with Ctrl+C.

The following is a template, not an instruction to start a study. Replace every
path, hash and reviewer ID with the frozen study's actual values. Use `final`
for an ordinary final evaluation or `improver` for a matched improver assessment.
The example roster does not prescribe a sample size or authorize human review.
Each repeated `--reviewer ID TYPE` declares one distinct reviewer; `TYPE` must
be `human` or `model`.

```powershell
python -m buddha source-review-export `
  --run "C:\replace\trial" `
  --kind final `
  --report-sha256 REPLACE_WITH_64_HEX_REPORT_HASH `
  --plan "C:\replace\review-plan.json" `
  --plan-sha256 REPLACE_WITH_64_HEX_PLAN_HASH `
  --out "C:\replace\review-exports\round-01" `
  --reviewer declared-human human `
  --reviewer declared-model model
```

This runs once, reading saved evidence and writing review files. It spends no API
money, needs no keys and runs in the same window. Integrity checks can take time.
Press Ctrl+C to stop; original evidence and any unfinished output are retained.

The output's parent folder must already exist. Use an absolute, plain, resolved
path without `..`, links or aliases, separate from the original trial, retained
validation/development trees, selected components and control files. The command
creates the output folder; it does not create missing parent folders.

| File | Who receives it |
| --- | --- |
| `reviewer/pack.json` | Reviewers: tasks, masked IDs, every complete literal answer and the equivalence rule. |
| `reviewer/response-template.json` | Reviewers: a blank form to fill in and return separately. |
| `reviewer/review.md` | Reviewers: instructions and the task-quality rubric. |
| `private/materialization.json` | Coordinator only: source mappings, availability, provenance and original accounting. |
| `private/round.json` | Coordinator only: exact sample hashes and the declared reviewer roster. |
| `complete.json` | Coordinator only: final publication marker and artifact hashes, written last. |

Distribute only the `reviewer` folder, manually. Keep the private plan, round,
source mappings and official scores away from reviewers. This command sends no
messages and performs no automated distribution or collection. Keep the emitted
round fixed before distribution; hashes and declared reviewer types alone do not
prove publication time, identity or independence.

The terminal prints a compact status and file references, not the private payload
or answer texts. `publication_status: complete` means the declared output files
were saved and checked. The separate `status` can still be `incomplete` when
selected source sets are unavailable. If all sets are unavailable, only the two
private files and `complete.json` are written; there is no reviewer folder.

An unmarked, byte-identical prefix can resume with the same invocation. Conflicting
bytes, unknown files or crash leftovers are refused and retained; nothing is
automatically overwritten or cleaned up. A valid existing marker triggers a
read-only check of the entire expected inventory. A missing published artifact
is refused rather than refilled. JSON uses the existing review encoding,
including UTF-8 text and its final newline; literal answer whitespace is preserved.

Exit codes are `0` for a complete source sample, `3` for a checked incomplete
sample, `2` for refusal and `130` for interruption. A marker alone does not make
a stopped invocation pass. Distribute only after the command reports a checked
publication and reviewer files exist.

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

`buddha.source_review_handoff.export_source_review` is the writing interface.
It takes `directory: Path`, `kind`, `expected_report_sha256`, `plan: Path`,
`expected_plan_sha256`, `output: Path` and an explicit `reviewers` list whose
entries contain exactly `id` and `type`. It returns the compact
`buddha.source-review-export.v1` summary: source `status`, `publication_status`,
output path, `complete` and `round_plan` path/hash references, and
`reviewer_directory` (or `null`). It retains the original checked observation
through serialization and publication, checks inputs again before the final
marker and returns only after checking both source evidence and output inventory.
The filesystem, retry, availability and original-helper requirements are the same
as for the command above. Calling this API makes no provider request.

The exporter reconstructs the complete original report through its existing
checked reader, then keeps that observation alive while extracting selected C1.
It checks consumed bytes, database sidecars and the original final and sibling
validation/development trees again before returning. A change during observation
is a typed error, never a partially trusted pack. No producer source is executed.

Masking is procedural: styles and prior exposure can reveal origins. Display
order must never replace original generation order when interpreting utility.
Reviews remain separate observations; they do not automatically become consensus,
gold classes, improver feedback or revised official scores.

## Collect and compare completed forms

Before preparing trial owners, also bind the current
`buddha/source_review_results.py` as an original custody evidence reference if
the trial will use this importer. Existing completed runs cannot add that pin
afterward. The historical `meas01-pack.py` helper stays byte-for-byte unchanged;
the runtime importer carries its review schema, checked against the old validator.
It does not run that documentation script or selected agent source.

The operator command writes `private/round.json` with the explicit roster supplied
on the command line. Keep it fixed before distributing the packet. If using the
read-only materializer directly, freeze a separate review-round JSON file after
export and before distribution with these exact fields:

| Field | Meaning |
| --- | --- |
| `format` | Exactly `buddha.source-review-round.v1`. |
| `plan_sha256`, `report_sha256`, `packet_sha256` | Exact hashes from the private export receipt. The packet hash is `null` if no selected answer set is available. |
| `reviewers` | A nonempty list of distinct declared reviewer IDs, each with `id` and `type` (`human` or `model`). |

This round belongs to the review collection, separate from the original trial
controls. Its packet hash can only be known after generation. Keep its bytes and
hash fixed before collecting responses; retain the publication record when a
scientific claim depends on that timing. A hash alone proves neither when a
file was published nor that a declared human is an independent person.

Save each returned form separately, with its exact original bytes and hash.
Leave an absent response absent; do not copy another response into its slot.
Retain malformed originals when requesting a corrected form. Never rewrite a
saved review to make it pass the validator.

`buddha.source_review_results.inspect_source_reviews` takes the same original
trial and sample arguments as the exporter, plus `round_plan`, its
`expected_round_plan_sha256`, and `submissions`. Each submission reference has
exactly `reviewer_id`, absolute `path` and `sha256`; omit reviewers whose forms
have not arrived. The function reconstructs the original export, reads each
pinned response and returns a private report without writing anything.

| Outcome | How it appears |
| --- | --- |
| Form not supplied | A `missing` reviewer row with `submission_not_supplied`. |
| Pinned form has invalid JSON, incomplete coverage, wrong pack or wrong declared reviewer | An `invalid` row with `invalid_submission`; the raw file reference remains. No favorable subset is salvaged. |
| No selected source set is available | Original missing-source coverage remains; any supplied form is `invalid` with `no_available_packet`. |
| Duplicate reviewer, file or response hash; changed pinned bytes; changed original evidence | A typed refusal. No checked report is returned. |

The report keeps source availability separate from declared human/model review
coverage. It retains valid responses in full: tentative groups, uncertain pairs,
reasons, task-compliance judgments, craft notes, uncertainty and prior exposure.
Invalid forms remain bound by their original file references and hashes.

For each answer set, `partition_disagreement` compares the complete groupings,
ignoring group and member ordering. It is `null` with fewer than two valid forms.
The compliance-disagreement list identifies answers receiving different compliance
judgments. All individual judgments remain visible; these fields perform no
voting, adjudication or automatic correction. Pair uncertainty stays explicit
even when tentative groupings agree. The implementation does not expand every
possible answer pair.

`complete` means that the declared source sample is available and every declared
reviewer supplied a structurally valid form. Reviewers can still disagree. A
model-only roster can have a complete collection while leaving the human-study
requirement entirely unmet. Counts use declared reviewer types; they do not
verify identity, independence or competence. Legacy forms bind the packet hash,
so importing an old form into another round does not establish a fresh review.

The same original capture remains alive through source extraction, submission
reading, report serialization and the final integrity check. The existing
32 MiB JSON and aggregate evidence ceilings apply. A report that exceeds them
is refused; rationales are not shortened to force it through. Official
NoveltyBench scores remain unchanged.

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

To check the importer instead, run from the checkout containing this slice:

```powershell
python -m unittest discover -s tests -p test_source_review_results.py -v
```

This runs the import checks once with supplied review forms and temporary test
runs. It spends no API money, needs no keys and runs in the same window. The
five checks took about 3.6 minutes on the current Windows checkout, including
preparing and repeatedly checking original evaluation evidence. This is a whole
test-cohort duration, not the time for one import; later runs can differ. Press
Ctrl+C to stop; interruption is not a pass.

There is no automated reviewer distribution or collection command in this slice.
A collection CLI is a later step; the passive developer importer above is
available now. The actual study still needs its own frozen protocol and evidence.
