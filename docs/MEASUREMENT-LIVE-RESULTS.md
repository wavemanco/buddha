# MEAS-02: live judge audit

October 20, 2026. The approved audit completed all **40 targets in four anchored
batches**, using 40 physical API attempts and **$0.032213** in recorded cost, with
no outstanding reservation. The passive target reader verifies the saved source
bindings, completion anchors, native rows and financial snapshot. Its inputs
remain byte-identical after analysis. These are local accounting records, not a
reconciled provider invoice.

The audit exercises the pinned NoveltyBench v1.1 partition command at upstream
revision `64a23be6b18ec1dacc298830aab276061b6e143c`, with the declared
`gpt-5.6-luna` judge. It uses the original texts in the frozen development review
pack. It does not generate new answers, run quality scoring, replace the
benchmark's equivalence rule or revise either pilot's scores.

## What the judge did

The baseline occasion covers all 22 review items: six historical ten-answer sets,
nine focused comparisons and seven authored controls. Three further occasions
each repeat the six historical full sets: the same display order, seed 0 and
seed 20261020. Each occasion has its own physical requests and completion anchor.
Reusing the scientific request text for a repeat does not reuse an old reply.

All 17 resolved baseline items agree with the frozen model adjudication. The
seven authored controls include actual equivalent answers; the judge merges the
exact duplicates and declared paraphrases while keeping the distinct controls
apart. This is a selected development check, not population accuracy or human
validation. Five baseline items remain uncertain under the independent review;
their new official partitions do not turn uncertainty into a settled label.

The focused lost-sounds bridge comparison is distinct, matching its frozen
adjudication. All five shared-subject controls are also distinct. Shared girls,
dogs, bridges or water alone are insufficient evidence of equivalence under the
official rule. The blocked-water comparison remains independently uncertain;
the new judge separates it. The cross-policy fawn card is merged, as expected,
but remains a supplemental comparison outside official within-set scoring.

The baseline contains 115 resolved pair appearances with zero disagreements;
each further occasion contains 90, also with zero disagreements. These counts
describe dependent presentations, including repeated resolved full sets. They
are not 385 independent trials or an accuracy estimate. Authored controls and
focused cards were each judged once; only the six full sets were repeated and
reordered.

## Raw replies and parser recovery

All 40 raw responses are intact HTTP 200 replies with normal completion and no
refusal. Their declared groups contain every response index exactly once.
Source-sealed replay through the official `Partition` schema and
`partition_fold` reproduces all 40 saved native rows. Strict and lenient folds
are identical here: no omitted-index singleton completion, repeated-index repair
or semantic retry was needed. This conclusion comes from the raw replies and
official-function replay, not from the number of requests.

Every request and response names `gpt-5.6-luna`; every response reports tier
`default`. The six same-order repeats have identical scientific request bodies
and fresh logical and physical records. All 40 are first physical attempts.
The review retains raw compressed-response, decoded-body, assistant-content,
request and receipt hashes. It uses the pinned Pydantic 2.11.7 / core 2.33.2
versions and verifies the actual mounted official source hashes. This is an
offline inspection of saved execution, not another provider run.

## The material instability

One historical set, recovery pilot A, changes substantially:

| Occasion | Distinct groups | Pack-order partition |
| --- | ---: | --- |
| Baseline | 4 | `0,1,0,0,2,3,0,2,2,2` |
| Fresh same-order repeat | 5 | `0,1,0,0,2,3,0,4,4,4` |
| Display seed 0 | 9 | `0,1,2,0,3,4,5,6,7,8` |
| Display seed 20261020 | 9 | `0,1,2,0,3,4,5,6,7,8` |

This is item `a6deca95bec239a475b0124ec6348ff6`, independently uncertain as a
complete set. The same-order repeat changes three pair relations relative to the
baseline; each shuffled occasion changes eleven. The other five historical
full sets retain the same pair relations across all four occasions. Their group
counts are reported separately in the bound result record.

| Historical answer set | Original recorded groups | New baseline / repeat / seed 0 / seed 20261020 | Independent full-set expectation |
| --- | ---: | --- | --- |
| Recovery A | 9 | 4 / 5 / 9 / 9 | Uncertain |
| Recovery B | 10 | 10 / 10 / 10 / 10 | Resolved distinct |
| Recovery C | 10 | 10 / 10 / 10 / 10 | Resolved distinct |
| Continuation A | 6 | 5 / 5 / 5 / 5 | Uncertain |
| Continuation B | 10 | 10 / 10 / 10 / 10 | Uncertain |
| Continuation C | 10 | 10 / 10 / 10 / 10 | Uncertain |

The same-order change establishes that display order is not the only possible
source of variation. These few observations cannot isolate a causal order
effect, identify a universally correct partition or estimate population
reliability. Class numbers are arbitrary; the comparisons above use equality
relations in original answer order.

## Implications for the experiment

Distinctiveness is the number of official groups, so a 4/5/9 variation directly
changes that measurement for the same answers. Utility is also affected: later
members of a group contribute zero, and changing the grouping can change which
answers need head-quality scores. This audit collected no quality scores and
therefore supplies no replacement utility value or corrected candidate ranking.

The historical scores remain preserved with their original provenance. The
earlier harness had documented request/parser/recovery differences; these new
native measurements do not retroactively make the old execution native. Even
the same provider model name does not make the two instruments interchangeable.
Generation and partitioning also named that same model in the historical runs;
this audit is not independent-model validation.

The next controlled comparison must retain repeated complete answer sets and
declare its judge occasions/order policy before observing results. It must
preserve uncertain cases and disagreements instead of selecting the most
favorable partition. Human assessment remains part of the later independent
evaluation gate. No private plot score, post-hoc majority partition or rewritten
benchmark rule is introduced.

## Evidence and scope

The frozen targets, resolved expectations and uncertainty come from
[the proposal](conformance/meas02-target-proposal.json) and
[the model review](MEASUREMENT-AUDIT-RESULTS.md). The live input was
`runs/meas02-live-20261020/handoff.json`; the authority-anchored completion is
`study/report.json` under that directory. The passive result is
`runs/meas02-live-20261020/target-report.json`.

[The result record](conformance/meas02-live-results.json) binds the live report, target result, raw-response review,
source identities and unchanged-input checks. It distinguishes successful
execution from scientific conclusions. Pair appearances are dependent; repeated
answers and full-set contexts are not independent accuracy trials. Only the two
resolved historical full sets have settled full-set expectations. The other
four full sets retain their independent uncertainty, including recovery A.

The original launcher and owners remain bound to their original 45 executing
source pins. Later application changes must not reseal or reinterpret them.
Before any such integration, the four owners also passed the existing data-only
sealed-history reader from the newer isolated checkout, with the same recorded
totals and unchanged inputs. That reader supports retained raw history without
requiring retired executing sources; it does not authenticate invoices or grant
permission to resume. The saved target report remains separate from that check.

The $15 allocation was specific to these frozen judge targets. Completion does
not authorize new generation, search, quality scoring or a new experiment with
the unused balance. No further command is needed from the user for this audit.
[PLAN.md](PLAN.md) remains the single roadmap.
