# First controlled policy comparison: results

Configurations that let the generator see its earlier answers have higher
observed distinctiveness and utility on these twelve development prompts.
Child instructions add smaller positive mean differences, with a negative
interaction. The completed masked panel also finds task violations, recurring
story mechanisms and nine uncertain judgments. Neither the numbers nor this
model review establishes a winner, promotion, statistical significance or
held-out improvement.

This study tests Buddha's instructions and generation-history configuration
using the unchanged official NoveltyBench 1.1 evaluator. The [frozen protocol](POLICY-COMPARISON.md)
and [intent](conformance/pol02-study-intent.json) govern the comparison. The
[exact result record](conformance/pol02-live-results.json) retains full-precision
values, every generation repetition, category/contrast ranges, J1 comparisons,
accounting and provenance. Tables below round metric values for reading.

## Coverage and primary result

All **960 answer positions in 96 ten-answer sets** were retained. All
**192 planned task assessments are observed and numerically usable**: twelve
prompts × four arms × two generation repetitions × two judging occasions.
Publication, numerical analysis and the predeclared model-panel process are
complete with uncertain judgments retained. The broader scientific gates
remain open.

J0, the first judging occasion, is primary. Within each prompt and arm, average
its two generation repetitions at J0, then give all twelve prompts equal weight.
J1 never replaces a J0 result. Neither answers nor repeated judging occasions
are independent prompt observations.

| Arm | Configuration | Distinct mean | Utility mean | Recorded USD, both occasions |
| --- | --- | ---: | ---: | ---: |
| 0 | empty / independent | 3.041667 | 3.655960 | 1.824885 |
| 1 | empty / history | 9.333333 | 7.347929 | 5.043444 |
| 2 | child / independent | 4.208333 | 4.549864 | 2.289974 |
| 3 | child / history | 9.500000 | 7.725700 | 5.301215 |

History includes earlier answers in the next generation request (the frozen
in-context condition). Independent generation omits that history. The child
is the exact generic instruction policy from the first fresh pilot; no new
policy proposal or tuning occurred.

| Registered J0 contrast | Distinct difference | Utility difference |
| --- | ---: | ---: |
| Child instructions, independent (2−0) | +1.166667 | +0.893905 |
| Child instructions, history (3−1) | +0.166667 | +0.377772 |
| History, empty instructions (1−0) | +6.291667 | +3.691969 |
| History, child instructions (3−2) | +5.291667 | +3.175836 |
| Interaction: (3−1)−(2−0) | -1.000000 | -0.516133 |

The history contrasts are larger than the instruction contrasts in these
observations. The negative interaction describes a smaller incremental
instruction difference in the history condition. The fixed order, chosen
development prompts, two repetitions and unequal actual spend limit
interpretation; these numbers are not a causal or population estimate.

Native utility combines the prescribed quality judgments, equivalence/novelty
and answer order under patience 0.8. It is not an independent craft, coherence,
instruction-compliance or factual-accuracy score. No official formula,
partition or score was replaced.

## Every prompt and original category

Each cell below is **distinct / utility**, using that prompt's J0 repetition
mean. Descriptions are explanatory; the frozen literal prompts govern.

| Task | Brief description | Arm 0 | Arm 1 | Arm 2 | Arm 3 |
| --- | --- | ---: | ---: | ---: | ---: |
| curated-0 | Five-sentence girl-and-dog story | 6.500 / 5.424 | 10.000 / 7.639 | 10.000 / 8.645 | 10.000 / 8.088 |
| curated-47 | One of two glass descriptions | 1.000 / 1.904 | 7.000 / 4.193 | 1.000 / 1.904 | 8.000 / 5.526 |
| curated-97 | One password digit | 1.000 / 1.456 | 10.000 / 7.526 | 1.000 / 1.232 | 10.000 / 7.170 |
| curated-15 | An interesting invention | 3.000 / 3.282 | 9.500 / 6.425 | 6.000 / 5.870 | 10.000 / 7.985 |
| curated-20 | A character name fitting a specified role | 4.000 / 4.332 | 10.000 / 7.156 | 6.000 / 5.427 | 10.000 / 7.513 |
| curated-26 | A culturally conditioned baby name | 2.000 / 3.250 | 10.000 / 8.521 | 3.000 / 3.867 | 10.000 / 8.825 |
| curated-33 | One teenager's first phone | 3.500 / 3.154 | 10.000 / 6.809 | 3.000 / 2.839 | 10.000 / 7.125 |
| curated-30 | An apparel-shopping recommendation | 4.500 / 4.992 | 9.500 / 7.868 | 5.000 / 6.315 | 10.000 / 8.013 |
| curated-50 | An occupation opinion | 3.500 / 4.823 | 10.000 / 9.000 | 3.500 / 5.018 | 10.000 / 8.880 |
| curated-71 | A Fields Medal recipient | 1.500 / 2.958 | 6.000 / 5.226 | 1.500 / 2.774 | 6.000 / 5.583 |
| curated-65 | Three television series | 4.000 / 5.221 | 10.000 / 8.977 | 6.500 / 6.322 | 10.000 / 9.000 |
| curated-86 | A fruit/vegetable pair | 2.000 / 3.075 | 10.000 / 8.835 | 4.000 / 4.385 | 10.000 / 9.000 |

Each original category contains two prompts. Ranges below describe those two
prompt means, again **distinct range / utility range**. All required J0 values
are usable. These are descriptive ranges, not confidence intervals or a
new pooled score.

| Original category | Arm 0 | Arm 1 | Arm 2 | Arm 3 |
| --- | ---: | ---: | ---: | ---: |
| Creativity | 3.000–6.500 / 3.282–5.424 | 9.500–10.000 / 6.425–7.639 | 6.000–10.000 / 5.870–8.645 | 10.000–10.000 / 7.985–8.088 |
| Character & Entity Naming | 2.000–4.000 / 3.250–4.332 | 10.000–10.000 / 7.156–8.521 | 3.000–6.000 / 3.867–5.427 | 10.000–10.000 / 7.513–8.825 |
| Product & Purchase Recommendations | 3.500–4.500 / 3.154–4.992 | 9.500–10.000 / 6.809–7.868 | 3.000–5.000 / 2.839–6.315 | 10.000–10.000 / 7.125–8.013 |
| Subjective Rankings & Opinions | 1.000–3.500 / 1.904–4.823 | 7.000–10.000 / 4.193–9.000 | 1.000–3.500 / 1.904–5.018 | 8.000–10.000 / 5.526–8.880 |
| Factual Knowledge | 1.500–4.000 / 2.958–5.221 | 6.000–10.000 / 5.226–8.977 | 1.500–6.500 / 2.774–6.322 | 6.000–10.000 / 5.583–9.000 |
| Random Generation & Selection | 1.000–2.000 / 1.456–3.075 | 10.000–10.000 / 7.526–8.835 | 1.000–4.000 / 1.232–4.385 | 10.000–10.000 / 7.170–9.000 |

The JSON record shows R0 and R1 beside their mean for every prompt/arm, every
prompt-level contrast and all five contrast ranges within each category.
Equal category representation does not reproduce the original 100-prompt
corpus frequencies. Password, closed-answer and factual tasks retain their
literal requirements; a larger distinct count alone does not establish
that a task was answered correctly.

## J1 is a diagnostic on the same answers

Seven of 96 sets change at least one label-invariant same-group relation:
**107 of 4,320 answer-position pairs** differ between J0 and J1. Six sets change
distinct count; 58 change utility. The largest absolute J1−J0 difference
is **9 distinct groups** and **6.440826 utility**. Pair relations and repeated
occasions are dependent descriptions, not independent accuracy samples.

A changed group assignment can alter utility as well as distinctiveness;
equal group counts can hide different membership. Both occasions, their
deltas/ranges and changed pair relations remain in the JSON record. No new
raw-reply/official-parser audit has assigned these differences to judging,
parsing, repair or fallback. J0 remains primary.

## Recorded tokens and money

Saved accounting reconciles **2,414 completed ledger operations with receipts**,
**56 original inactive owners**, and **$14.459518 spent and committed, with
$0 held**. These are local recorded charges, not provider invoice reconciliation.
Completed receipts and retained checkpoint copies are selected once, without
double-counting money.

| Arm | Completed operation records | Input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| 0 | 443 | 139,540 | 56,327 |
| 1 | 734 | 351,037 | 105,496 |
| 2 | 491 | 193,926 | 62,169 |
| 3 | 746 | 389,426 | 113,055 |

| Stage | Completed operation records | Input tokens | Output tokens | Recorded USD |
| --- | ---: | ---: | ---: | ---: |
| generation | 960 | 232,172 | 73,075 | 0.248046 |
| grouping | 193 | 155,633 | 26,200 | 0.125065 |
| quality | 1,261 | 686,124 | 237,772 | 14.086407 |
| summary | 0 | 0 | 0 | 0.000000 |

Total recorded usage is **1,073,929 input / 337,047 output tokens**. Usage is
available for all 2,414 operations, so known subtotals equal complete totals
here. Inclusive provider counters do not supply a separate reasoning or cache
breakdown. All arm/stage cross-totals and requested-model totals are in the
JSON record.

All arms had equal scheduled generation counts, model access and per-request
ceilings. They did not use equal actual tokens or money. Generation is counted
once per original set; the costs above include both judging occasions. Ledger
attempt and response counts do not independently attest a number of network
sends.

All recorded attempt indices are zero; no attempt-above-zero physical retry is
observed. No operation requests the configured claude-sonnet-5 fallback model:
there are 1,153 gpt-5.6-luna and 1,261 claude-opus-5 operation records. These
observations do not prove native parser repair never ran or assign a recovery
cause to a task row. The 193 grouping records for 192 assessments are retained
without inventing an explanation.

All projected HTTP statuses are 200. The 1,153 OpenAI responses have literal
finish reason stop and present-null refusal fields; the 1,261 Anthropic
responses have literal stop reason end_turn. These saved response fields do
not independently establish official-parser success, task compliance or an
absence of recovery.

All 1,920 saved repair/lenient/fallback/unscored availability fields across
192 assessment rows are **unknown**, not false. Parser recovery, causal
fallback and operation-to-task-row attribution remain unknown. Raw status,
usage and money stay available independently of those missing facts.

## Predeclared masked supplemental review

The required panel process is complete, with **nine uncertain judgments
retained**. Two fresh masked sessions each reviewed all **24 sets, 240 answers
and 1,080 within-set pairs**. A third fresh masked session adjudicated **67
listed issues across 15 sets**. Seven pair relations, one compliance judgment
and one craft judgment remain uncertain; they were not forced into agreement.

The panel covers the six preselected tasks and one assigned generation
repetition per task. It is the registered supplemental development review,
not a new benchmark audit. It changes no official partitions, distinct counts,
utility values or primary contrasts.

### Task compliance

Final answer-level labels are **228 yes, 11 no and 1 uncertain**. Every arm
has six reviewed sets and 60 answer positions.

| Arm | Yes | No | Uncertain |
| --- | ---: | ---: | ---: |
| 0 · Empty / independent | 60 | 0 | 0 |
| 1 · Empty / history | 52 | 8 | 0 |
| 2 · Child / independent | 60 | 0 | 0 |
| 3 · Child / history | 56 | 3 | 1 |

Each task below has four sets and 40 answer positions.

| Task | Yes | No | Uncertain |
| --- | ---: | ---: | ---: |
| curated-0 · Girl-and-dog story | 39 | 0 | 1 |
| curated-20 · Character name | 40 | 0 | 0 |
| curated-33 · First phone | 40 | 0 | 0 |
| curated-47 · Glass description | 31 | 9 | 0 |
| curated-71 · Fields Medal name | 38 | 2 | 0 |
| curated-97 · Password digit | 40 | 0 | 0 |

Nine violations concern the glass task's literal instruction to pick one of
two descriptions: seven in empty/history and two in child/history. They
supply a third choice, neither choice or no choice. They were not rejected
for adding an explanation or failing an invented one-word rule.

The other two violations are the Fields Medal names Elon Musk
(empty/history) and Andrew Wiles (child/history). The adjudication supplied
[the IMU Fields Medal list](https://www.mathunion.org/imu-awards/fields-medal)
and [the IMU's 1998 description](https://www.mathunion.org/fileadmin/IMU/ICM2002/offline/Beijing/general/prize/medal/1998.htm);
the recorded host check distinguishes Wiles's silver plaque from a Fields
Medal. These checks resolve the listed compliance issues only. The preserved
factual-support labels still contain **121 unverified** and 119 not-applicable
judgments; unlisted fields were not silently upgraded.

### Story mechanisms and official-rule relations

All four reviewed girl-and-dog sets show broader premise concentration. The
child/independent set repeatedly uses dog-hearing-lost-things and family-letter
mechanisms despite an official distinct count of ten. Its supplemental craft
labels include three inadequate stories. Shared motifs are descriptive
diagnostics and do not automatically establish official-rule equivalence.

For the child/history story set, the final model relations include one
definite equivalent pair, giving nine model groups while the unchanged
official result has ten at both J0 and J1. One gender-related compliance
judgment and one craft judgment remain uncertain.

| Official occasion | Model relations agree | Differ | Uncertain |
| --- | ---: | ---: | ---: |
| J0 | 971 | 102 | 7 |
| J1 | 1,017 | 56 | 7 |

These are comparisons of 1,080 dependent within-set relations, not accuracy
estimates. On the selected Fields Medal sets, both history arms have official
J0 distinct count two while the panel has ten groups; child/history changes
to official ten at J1, whereas empty/history remains at two. Independent
custody checks confirm the literal answers, original positions and native
input joins. They do not assign a cause to the judge, parser, repair or other
upstream processing. No extra raw audit or score correction was performed.

### Actor access, evidence and interpretation

The original actors were /root/pol02_masked_review_a and
/root/pol02_masked_review_b. Their declared inputs were only the fixed
instructions and masked packet; each wrote its own output. The third actor,
/root/pol02_masked_adjudication, declared the masked listed-issues input,
its instructions and cited primary sources. The private coordinate map,
arm metadata, official scores and costs were withheld from those review
contexts. These are recorded procedural access declarations, not a proof of
model diversity, statistical independence or human truth. Exact model
identifiers were unavailable.

All three actors used **unpriced host Codex subscription usage**, separate
from the API ledger and not entered as zero-dollar spending. The original
reviews, adjudication and unresolved judgments remain preserved locally.
This public report includes only aggregates and selected findings; it does
not reproduce the private full map, answer packet or full review bodies.

| Evidence | SHA256 |
| --- | --- |
| Masked packet | d160c0fb115ab93276a7e72638208057a4284574f85e576247ca162204c8d177 |
| Original review A | 9b88c5f2d09a87228b2b666fb92c3d2ffbb53f80d94dedfe421e1c0e6a1e9258 |
| Original review B | 856b82568afa9376a1bbf65989ccc138c95e5c6e96995cda76a75a4597e93401 |
| Fresh adjudication | fbe4af2ca101b7b20f49a5504a9ebb989e349375c563f6eb8a42cbf5f12e2aae |
| Joined result | f10cfe2d2005c0a39c0dfbfde9330cde2e70a72a7307dde25b15c882f0ef96e6 |
| Public summary | 6eea3a96e70a36ec70ae4eb7c1013feef6fd090a1defa9e90009d40840e04d80 |
| Independent custody/arithmetic review | 302f84fd8a5e58931c40b09e0fc033f4b399914a51e3b3b01442475985d50d1a |

The bounded POL-02 execution, reporting and supplemental-panel process is
complete with uncertain results. Human assessment, eligible held-out
evaluation, actual model-authored Python evolution and improved-improver
effectiveness remain open.

A practical proposal is to carry the history condition forward as a promising
seed configuration, preserve the original task requirements while diversifying
causes/actions/consequences, and inspect recurring content mechanisms alongside
the official numbers. This direction is **proposed only**: it is not implemented
or funded by this report and does not alter the fixed official evaluator.

## Provenance and limits

The completed passive projection is SHA256
400ae414ca41ac8cb61c013e5c6dd5e010410cec07d21e87936cb5e22ae05e8c.
Its reader receipt is
3f89933215256a49e05fb3f19785e29bba2b7a8c501c255600b9d23636cb592b:
610 captured files, 180 frozen reader inputs unchanged, no new paid calls,
keys, workers/network or SQL against original databases. The independent
numeric review, SHA256
6ddedbb175ee48cd35830692fbaf252a63c4893c6f8aa84935dded812e207fd8,
checks the saved grid, arithmetic, J1 relations and accounting without opening
original run files or databases.

The study fingerprint is
897db6a13c2a3f35bf5dd11e99e5aac20173c1a556f7e55aea9ccfa63a3c19de;
the original completed-publication hash is
a4bdb1b39974d7420374a4cc51cd2af31b2182de3f30743621716df318563017.
Source, protocol, intent, reader, panel and review-dispatch references are in
the JSON record. Raw corpus/answer data and the private panel mapping stay in
their original local custody.

These checks establish retained-evidence consistency, not authenticated
provider/capture time, universal task correctness or human preference.
Selected development prompts, the exposed public corpus, fixed schedule,
small repetition count, unknown recovery causes and the panel's unresolved
judgments prevent a general improvement claim. Broader source evolution and
improved-improver experiments are not evaluated by this policy comparison.
