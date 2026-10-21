# MEAS-02: offline saved-judgment audit

October 20, 2026. All six saved historical partition replies reproduce their
recorded classes through the pinned official v1.1 selected functions, without
lenient completion. The available resolved comparisons agree on 95 unique
within-candidate pairs, **all expected distinct**. This establishes neither judge
accuracy nor sensitivity to equivalent answers. MEAS-02 remains partially
addressed; [PLAN.md](PLAN.md) owns its status and next gate.

This diagnostic is bound to the historical v1.1 evidence. Its scripts live under
`docs/conformance`; this slice changes no agent, release selector, gateway or
shared runtime module. The [release-upgrade contract](RELEASE-UPGRADES.md) continues
to govern configuration-only baselines on compatible new official releases.

## What was replayed

The [replay script](conformance/meas02-official-replay.py) uses exact selected
functions/classes from `common.py`, `judge.py` and `partition.py` at upstream
commit `64a23be6b18ec1dacc298830aab276061b6e143c`, with Pydantic 2.11.7 and
pydantic-core 2.33.2. Source-file and selected-AST hashes are recorded in the
[actual replay evidence](conformance/meas02-official-replay.json). This executes
the selected official code; it does not execute the complete modules, native CLI,
SDKs or a fresh model judgment. Scripted immediate single-call coroutines do not
measure concurrent scheduling or network behavior.

For each of the three recovery and three linked-continuation candidates, the
replay binds the saved task, ordered answer hashes, partition request fingerprint,
completed operation and retained reply text. Every reply parses and folds strictly,
matches the recorded partition/distinct count, and produces the same result with
leniency enabled. **None of these six replies requires leniency.** Their high
distinct counts therefore cannot be attributed to this repair path on this evidence.

The retained response is legacy parsed `Reply.text`, not complete raw HTTP bytes
or original response-block boundaries. Seals and replay demonstrate local saved
evidence consistency, not provider authenticity. The historical adapter used one
partition attempt with repair disabled; replay does not retroactively turn it into
a native run or establish native retry behavior for that occasion.

The replay also exercises 23 scripted selected-function controls:

| Control family | Cases | Bounded observation |
| --- | ---: | --- |
| Partition folding | 9 | Strict rejection versus lenient handling of omissions, repeated/out-of-range indices and empty groups. |
| Display-order mapping | 4 | Known displayed groups map back to the intended original answer order under the configured seeds. |
| Stage handling | 6 | Strict success, later valid repair, final-fold leniency, refusal and schema failure remain distinct paths. |
| Generic judge refusal/fallback | 4 | Refusal can invoke a configured fallback; an ordinary parse failure is not treated as refusal. |

Lenient folding removes invalid indices, keeps the first occurrence of repeated
indices and adds omitted answers as singleton classes. Controlled examples show
that even an empty grouping can thereby become an all-singleton result. This is
source-prescribed recovery, not independent semantic confirmation. The generic
fallback controls do not imply that the partition CLI supplies a fallback model;
that CLI supplies none. Order controls check mapping code, not a model's stability
when it sees reordered answers.

The evidence preserves all 287 prior historical-file seals, the archived runtime
ZIP, the sealed v2 authority and all 36 package source seals. Financial decoding
uses in-memory SQLite snapshots. No keys, provider calls, source-database opens,
historical writes or archived-runtime reconstruction were used. See the
[delivery record](conformance/meas02-offline-delivery.json) for slice evidence and
validation status; this report does not claim pending tests or CI have completed.

## Comparison with the frozen development judgments

The pure [comparison helper](conformance/meas02-compare.py) binds the
[MEAS-01 expectations](../tests/fixtures/meas01-expectations.json), their
[unblinded source references](conformance/meas01-adjudication-review.json) and the
six replay rows. It compares equivalence relations rather than arbitrary class
numbers. The [comparison evidence](conformance/meas02-relation-comparison.json)
records these explicit populations:

| Population | Result |
| --- | --- |
| 17 resolved review items | Nine compared: two complete sets and seven focused cards. |
| Remaining resolved items | One cross-policy card has no within-candidate comparison; seven authored cards have no saved judge measurement. |
| Five uncertain items | Excluded from resolved comparisons. |
| 115 pair appearances in resolved items | 97 compared appearances; 95 unique within-candidate pairs after two repeated appearances are deduplicated. |
| 95 measured unique pairs | 95 agreements, zero disagreements; every expected relation is distinct. |

**MEAS2-M1 (observed coverage limit).** These are selected, dependent development
comparisons, not an accuracy estimate,
Kappa result or population reliability measurement. In particular, there is no
measured equivalent pair here: the result cannot establish equivalent-answer
detection or rule out a judge that separates everything. Authored duplicate and
paraphrase controls still need official measurements. Unresolved full sets and
the blocked-water boundary remain uncertain, rather than becoming agreement data.
The [MEAS-01 results](MEASUREMENT-AUDIT-RESULTS.md) retain the model-only review,
instructional blinding, unknown exact model identifiers and shared-model dependence
limits. No human validation or unseen evaluation was added.

The [independent engineering review](conformance/meas02-independent-review.json)
reproduces the source-bound comparison and eight additional counterexamples,
including missing measurements, context disagreement and source substitutions.
It checks provenance and program behavior, not new semantic ratings.

## Why partition changes affect both metrics

The pinned [official scoring source](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/score.py)
selects each class's first answer as its head and scores those heads. Distinctiveness
counts classes; utility credits only a class's first occurrence, with the declared
position weights and patience. Later duplicates receive no utility credit even if
their text is better. This is also the contract in
[DESIGN section 5](DESIGN.md#5-measurement-contract).

Merging or splitting classes can therefore change both the distinct count and
which answers receive quality credit. Changing order can change heads and weights.
A newly required head may have no saved quality score, so a changed partition
does not generally support a valid utility recomputation from the existing scores.
This slice performs no quality rescore, new numerical intervention or corrected
ranking. Original recorded partitions, utility, distinctiveness and rankings remain
unchanged.

**MEAS2-F1/F2 (diagnostic guards).** Comparison binds the exact task hash as well
as source answer identities: changing the task while keeping answers must be
rejected. The replay tool also requires assertion checks; optimized Python must
stop before external imports or source consumption. The delivery record retains
the actual negative controls and their final verification. These checks do not
change the official evaluator or agent.

## Reproduce the offline replay, optionally

With the preserved private inputs, pinned reference source and existing locked
reference environment available, run this from the project folder. The output's
parent directory must exist; choose a new filename:

```powershell
.\runs\reference-env\Scripts\python.exe docs/conformance/meas02-official-replay.py --out runs/reviews/meas02-replay-copy.json
```

This runs once in the same window, needs no API keys, spends no provider money and
changes no historical records. It writes a new diagnostic JSON only after checks;
an existing output is preserved and causes refusal. Ctrl+C stops the process. An
interruption may leave no output or a partial JSON file; keep it as incomplete
evidence, never as a pass. A fresh clone does not include the private historical
inputs or prepared reference environment.

## Remaining live audit and scientific limits

The next MEAS-02 measurement needs fresh official partition judgments on the
declared controls, including equivalent examples and the unresolved boundaries,
plus repeated full sets and display-order variants. Preserve raw replies, actual
fold/repair paths and every physical SDK attempt; a request count alone does not
prove leniency. This remains partition assessment, not candidate generation,
quality rescoring, a full benchmark result or held-out evaluation.

The [dated readiness note](conformance/meas02-paid-readiness.json) and
[concrete target proposal](conformance/meas02-target-proposal.json) specify 40
proposed target judgments: the 22 pack items once, six repeated full sets and two additional display
orders for each full set. Its up-to-120 semantic folds at a three-fold limit do
not bound SDK transport attempts or retries. This is a proposal, **not an approved
allocation, live price profile or spending command**. Its October 20 model/pricing
observations cite official OpenAI documentation, but account/project tier,
applicable maximum charges and physical-attempt allowance remain unverified.
Refresh and bind those facts before paid execution; unused historical balance
provides no new authorization or completion guarantee.

The broader EVAL-02 gate still requires frozen finalists, matched baselines and
resources, declared coverage, uncertainty and the human sample retained by
[DESIGN section 11](DESIGN.md#11-failure-modes-and-acceptance-gates).
This offline replay and model-only development comparison do not establish human
agreement, generalization, useful-diversity improvement or scientific validity.
