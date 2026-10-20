# MEAS-01: model review and adjudication results

October 20, 2026. The frozen model review resolves **17 of 22 review items** and
leaves **five uncertain**. Only **two of the six complete historical answer sets**
are resolved. These are development judgments under the official NoveltyBench
v1.1 equivalence rule, not human ground truth or revised benchmark scores.
[PLAN.md](PLAN.md) owns the completion gate and next work; the
[review guide](MEASUREMENT-AUDIT.md) describes preparation and masking.

## Material and procedure

The [frozen pack](conformance/meas01-study/pack.json) contains six complete
ten-answer sets from the recovery and linked-continuation runs, nine focused
comparisons and seven authored controls: 22 items and 96 answer appearances.
The historical material comes from one development prompt: “Tell me a story in
five sentences about a girl and her dog.” Authored controls include additional
literal-output tasks; they are not evidence of candidate behavior on those tasks.
The official rule and exact task/answer strings were preserved. Policies, ancestry,
old classes, scores and selection reasons were hidden behind shuffled opaque IDs.

Two fresh, separately instructed model sessions reviewed only the public material.
A third fresh model session received that material and their frozen responses for
explicit adjudication. Responses were frozen before comparison, and the final
response and adjudication record were frozen before unblinding. Blinding was an
instructional restriction with self-reported access, not OS confinement. The exact
inherited model identifiers are unavailable; separate contexts do not establish
different model families, statistical independence or freedom from shared bias.
There were no benchmark-provider API calls or new benchmark allocation. Native
delegation used platform model computation whose exact cost is unavailable.

The first instructions omitted the uncertain-pair field names. Both original
responses therefore failed structural validation. The versioned clarification
renamed `answer_ids[0]` to `left`, `answer_ids[1]` to `right`, and `reason` to
`rationale`. Independent comparison of all 24 affected objects confirms that every
other judgment and field stayed equal. Both originals remain alongside their
valid copies: [review 1 original](conformance/meas01-study/review-1-original.json),
[review 1 v2](conformance/meas01-study/review-1.json),
[review 2 original](conformance/meas01-study/review-2-original.json) and
[review 2 v2](conformance/meas01-study/review-2.json).

## Adjudicator's conclusions

The [final response](conformance/meas01-study/adjudicator-response.json) retains
the complete groups, literal-compliance observations and uncertainty. The
[adjudication record](conformance/meas01-study/adjudication.json) states a decision
and disagreement rationale for every item. The following reports those decisions;
it adds no new ratings.

| Material | Resolved | Uncertain | Result |
| --- | ---: | ---: | --- |
| Six historical full sets | 2 | 4 | Recovery B and C each have ten distinct groups. Recovery A and continuation A/B/C retain uncertainty. |
| Nine focused comparisons | 8 | 1 | The blocked-water comparison remains uncertain. |
| Seven authored controls | 7 | 0 | Explicit content groups and separate literal-form observations are retained. |
| Total | 17 | 5 | Uncertain items produce no resolved regression expectations. |

- **Lost-sounds bridge**, recovery C3/C10, item
  `1c6b4f8f841d8095f3e49f35ba7f9d9c`: **resolved distinct**. The adjudicator
  distinguishes restoring a soundscape with a music box from freeing a musician's
  song from a frozen river and recovering the girl's laughter. The shared dog,
  bridge and lost-sounds premise do not settle equivalence. This does not confirm
  the earlier strong equivalence concern; that concern was not forced into a fixture.
- **Blocked water, L-M1**, continuation C7/C10, item
  `92bbea60cc82d82c3f0727116decc86b`: **uncertain**, with a tentative equivalent
  grouping. Shared discovery, blockage removal, restored village water and a
  keepers ending support overlap, while the bell/salty-well premise leaves a
  central-content boundary unresolved. This item is excluded from resolved fixtures.
- **All five shared-subject controls are resolved distinct**: recovery C6/C8;
  continuation B2/B8, C1/C7, B3/B10 and C2/C10. Shared required characters,
  lighthouse settings, object discovery or restored water alone did not force merging.
- The **cross-policy fawn** comparison is resolved equivalent; the **oak-door**
  comparison, continuation A2/A3, is resolved distinct. The cross-policy finding
  remains supplemental, outside official within-set scoring.
- The **strict controls separate content from form**. The single-digit control
  groups the explanatory “0” response with “0” for content while marking the
  explanation and blank answer as literal violations. The closed-answer control
  groups the negative responses together but marks mixed case and added explanation
  as form violations. “YES” meets the permitted token format while being factually
  wrong; formal compliance does not establish utility.

There are 296 within-item pair appearances: 270 in the full sets, nine in focused
cards and 17 in authored cards. Repeated presentations, shared source answers and
nine inherited continuation replies make these dependent. They are not 296
independent observations or an accuracy denominator. No accuracy, Kappa or
population reliability claim follows. The adjudication retains 16 explicit
uncertain-pair appearances, representing 15 unique source pairs; provisional
groups in uncertain items must not be treated as settled pair labels.

## What is preserved and reusable

The [study manifest](conformance/meas01-study/manifest.json) binds the public pack,
instructions, original/corrected reviews, final response, adjudication and
[expectations fixture](../tests/fixtures/meas01-expectations.json) by physical hashes.
The selection rule includes all 17 explicitly resolved complete items in pack
order and excludes all five uncertain items. It copies the adjudicator's complete
item groups; it does not infer gold through majority vote, pair expansion or
transitive closure. These are versioned model-development regression expectations.

The [independent audit](conformance/meas01-adjudication-review.json) links every
opaque answer to its original reference or authored-control index and exact source
hash. It verifies the 60 historical UTF-8 answer round trips, unchanged official
rule literal, format-only repairs, raw review/adjudication bindings and the actual
fixture-producing API under read-only guards. All 287 protected historical files,
the archived runtime ZIP, sealed v2 authority and 36 package files match their
prior preservation seals. Original partitions, utility, distinctiveness, costs,
holds and rankings remain unchanged. This evidence neither establishes that the
official judge was wrong nor supplies a corrected ranking.

## Remaining measurement work

**MEAS-02** must test how the unchanged official judge applies its own rule to the
declared controls, preserve raw replies and separate semantic judgments from
source-prescribed lenient partition completion. Check partition/order sensitivity
as resources permit and explain effects on both metrics without replacing the
official instrument. New paid judging requires a concrete allocation. Inspected
examples remain development diagnostics, not held-out evidence.

The broader **EVAL-02** gate remains open: frozen finalists, matched resources and
baselines, complete declared coverage, uncertainty, independent audit and the
human sample required by [DESIGN section 11](DESIGN.md#11-failure-modes-and-acceptance-gates).
Model-only adjudication does not close that human component or establish a fully
identified frozen audit instrument. This study supports bounded regression checks;
it establishes neither generalization nor useful-diversity improvement.
