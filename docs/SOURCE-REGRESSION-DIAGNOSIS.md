# Why the current child scored worse

The current child made a poor measured trade-off: it weakened the request for
different legal answers and returned the same digit ten times. That accounts
for most of this run's score loss. Its code also changed several things at
once, so this evidence does not identify batching alone as the cause.

This is a diagnosis of the [completed run](SOURCE-CURRENT-LIVE-RESULTS.md), not
a new experiment or a change to NoveltyBench. The [living plan](PLAN.md) owns
implementation order and funding. [Evidence](conformance/current-source-regression-diagnosis.json)
retains exact source/receipt references and the separate read-only reviews.

## Where the measured loss came from

Each task has equal weight in the reported means.

| Task | Parent utility | Child utility | Share of this observed utility loss |
| --- | ---: | ---: | ---: |
| Story | 7.6473 | 6.7420 | 13.67% |
| Binary choice | 3.0472 | 3.0472 | 0% |
| One digit | 7.2868 | 1.5684 | 86.33% |

The parent returned `7,3,8,4,9,1,6,2,5,0`. The child's original model replies
were three arrays of `"7","7","7"`, followed by one `"7"`. Its parser simply
collected them. The official digit group count fell from ten to one; this
accounts for all of the decline in mean distinctiveness. The story group count
stayed ten, but its official quality ratings were lower. Binary results were unchanged.

These percentages describe the arithmetic of this three-task observation.
They are not population estimates or estimates of an intervention's causal effect.

## What the child changed

The parent repeatedly asked, "Can you generate a different answer?" and showed
earlier answers as conversation turns. The child requested three answers in
one JSON array, put earlier answers inside its prompt as JSON data, and added:
"For a finite answer space reuse legal answers; uniqueness is not a requirement."

Its saved proposal explanation explicitly linked uneven digit ratings to
permitting repetition. Preserving correctness was sensible, but broad permission
to repeat weakened the separate diversity objective. Ten different legal digits
were available here. A legal answer can still make a poor ten-answer collection.

The child changed batching, novelty wording, task wrapping, history representation
and the maximum aggregate output allowance at once. The same 4,096-token cap
applied to each reply, which now often contained three answers. This makes a
poor mutation observable, without isolating which change caused which effect.

The model, system instructions, reasoning effort, processing tier and per-reply
cap stayed equal. All forty-two P/C generation replies finished normally; none
was truncated or took the malformed-array fallback. There is no evidence of
parser-created repetition or output truncation causing this collapse.

The exact utility difference also contains judge variability. Byte-identical
quality requests for the first digit `7` received ratings 5 for P and 7 for C.
That difference favored C's first digit; it cannot explain why C returned ten
identical answers. Preserve these official ratings. Future matched repetitions
need to be declared in advance, rather than rerunning until a preferred score appears.

## A concrete feedback gap in Buddha

The full-output requirement is working: the C-to-W1 request includes every C
answer and its absolute measurements. However, that packet contains no P
baseline or P-to-C task deltas. C's new index only summarizes those C notes.
The next improver can see poor diversity, but is not explicitly shown how its
parent's changes affected the previous results.

The existing failed-generation feedback covers checked execution failures.
A complete but lower-scoring child is admitted and does not enter that failure
packet. Its regression is preserved in the archive and reports, rather than
delivered as an explicit comparative diagnosis to the next proposal.

This is a real missing feedback treatment, not evidence that adding it will
improve scores. The smallest extension would reuse anchored compatible parent
and child screens, their lineage, full notes, provenance and capacity checks.
It would expose per-task changes in both official metrics and recorded costs,
with explicit unavailable comparisons where necessary. Full literal answers
would remain intact. No private metric, new evaluator or replacement search
controller is needed.

Checks must first establish correct immediate-parent/baseline joins, exact task
and comparison compatibility, correct delta direction, preserved full answers,
legacy replay and refusal of incompatible or changed evidence. A new treatment
must be versioned and bound before future execution. Historical v3 packets and
any adopted study treatment must not silently change.

## How to pursue improvement

The next performance-focused development should use the existing archive,
rather than copying this demonstration's one-iteration `latest` setting.
The numerical frontier already retains P. Archive membership or exploration
parent selection must remain separate from adopting a better measured agent.
Weaker branches can still be useful stepping stones; DGM explicitly retains
such branches in its [archive-based approach](https://arxiv.org/html/2505.22954v3).

The existing bounded archive needs capacity at least five to reserve any
dominated exploration member, because that reserve is `max_active // 5`.
No new archive implementation is required. The future protocol must declare
its capacity, opportunity count and resources rather than changing the old run.

For diagnosis, compare the child's original repetition wording with wording
that requests different correct answers where the task allows them, holding
its batch structure and history representation fixed. A prospective comparison
can then cross wording with batch size one/three while keeping the wrapper and
history policy fixed. Test history representation separately if needed.
Use varied development tasks, matched declared resources and repeated samples.
This tests specific hypotheses instead of assuming all batching is bad.

Have the improvement loop propose focused changes tied to observed failures.
Its performance objective must remain both official metrics and task compliance;
fewer callbacks or more complicated code are not success criteria. The mechanism
demonstration's requirement to change both generation and improvement code in
every proposal need not be imposed on a future performance treatment. Do not
hardcode benchmark task IDs, insert preferred answers, require impossible
uniqueness, or discard poor final outputs before official scoring.

W1 already proposes finite-space allocation and story directions, but only its
first-task generation ran. Its digit behavior, full official performance and
its own improver remain untested; its observed story-subject failure remains.
It is another candidate, not an established repair.

Before claiming improvement, select and assess frozen finalists using the
existing validation, paired analysis, sealed evaluation and independent-review
machinery. Keep negative offspring and both metrics visible. The IMP-01 analyzer
must still measure its declared descendant outcomes; adding a starter fallback
to hide worse descendants would change that comparison.

No new API run or allocation follows from this diagnosis. SRC-02/03 remain
complete for demonstrated mechanisms; IMP-01 and EVAL-02 remain open for
effectiveness and generalization.
