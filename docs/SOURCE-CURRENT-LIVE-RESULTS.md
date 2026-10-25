# Current-source Python evolution: results

The October 24, 2026 experiment completed. **Buddha changed and used both its
generation procedure and its inherited improvement procedure. Its official
development scores fell.** These are separate findings.

SRC-02 and SRC-03 are complete at their original engineering scope. IMP-01
still needs the controlled comparison of improvers; EVAL-02 still needs unseen
evaluation, independent human review and uncertainty reporting. The
[living plan](PLAN.md) owns that sequence.

No command is needed from you now. Do not repeat the original launch. Keep its
files and pinned runtime intact. The [machine-readable result](conformance/src02-current-live-results.json)
retains the original identities, accounting, individual reviews and reconciled
decisions. The [launch guide](SOURCE-CURRENT-LIVE.md) retains the historical command.

## What actually happened

The frozen order completed without a missing or rejected role:

1. Starting program P generated thirty answers: ten on each of three tasks.
2. P received its thirty complete answers and measurements, then proposed W0.
   W0 generated ten answers on the first task as a validity check.
3. P made a separate proposal C, the one counted search child.
4. C generated thirty answers and received the same official three-task assessment.
5. C's own improver received all thirty C answers and measurements, proposed W1,
   and W1 generated ten first-task answers as the second validity check.

That is eighty saved answers. W0 and W1 were validity-only children; neither
received the full official assessment or became a counted search iteration.
Their own improvers and later tasks were not attempted by design.

All three proposal replies contain the complete replacement Python source.
Their literal source fields match the materialized files and private execution
copies. Every proposal retained all thirty ordered parent answers, with zero
omitted answer, partition or score positions. All three original capacity
checks passed; no extra capacity request was sent.

## What changed in the Python

P asked for one answer per callback. C changed the control flow to request
small JSON arrays and collect their strings. On each actual task, its four
callbacks returned batches of three, three, three and one. Those exact strings
became its ten saved answers. P used ten callbacks per task. The changed path
therefore ran; this finding does not rely on the model's explanation or a file
hash alone. C's malformed-batch fallback was not exercised.

C also added an `_evidence` procedure that reads the measured notes and builds
a task-by-task index of metrics and scored positions. Its `propose_improvement`
included that computed index in the actual C-to-W1 request, alongside the
complete original feedback. P's requests had no such derived index. The
resulting W1 was a changed program and generated its ten answers in one batch.

This establishes a substantively changed, used improver under the adopted
criteria. It does not prove that the model relied on the index, that every new
branch works, or that this improver produces better descendants. W1's own
improver was not executed and supplies no evidence for those claims.

The [root review](conformance/src02-current-live-root-review.json) and
[fresh-context mechanism review](conformance/src02-current-live-mechanism-review.json)
were retained separately before reconciliation. They agree on both mechanism
findings. Both are automated host reviews; exact serving model identifiers and
model overlap are unknown. They are not independent human ratings.

## Official development scores

NoveltyBench 1.1, its pinned official code, judge settings and scoring rules
were unchanged. These previously seen development tasks receive equal weight.
Distinctiveness is the official number of groups among ten answers; utility
is the separate official usefulness-and-diversity measure.

| Task | P utility / distinctiveness | C utility / distinctiveness |
| --- | ---: | ---: |
| Five-sentence girl-and-dog story (`curated-0`) | 7.6473 / 10 | 6.7420 / 10 |
| Choose glass half full or half empty (`curated-47`) | 3.0472 / 2 | 3.0472 / 2 |
| Exactly one password digit (`curated-97`) | 7.2868 / 10 | 1.5684 / 1 |
| **Mean** | **5.9938 / 7.3333** | **3.7859 / 4.3333** |

C returned `7` at every digit position. The benchmark recorded the resulting
collapse to one group. Both story batches received ten groups, despite the
descriptive repetition concerns below. Official results remain unchanged.

The search used the predeclared `latest` rule, so C became its selected eligible
parent even though its scores were worse. P remains the numerical frontier.
Eligibility means that required execution, measurement and validity checks
passed; it does not mean superiority. Selection does not install C as the
project's default agent.

Batching and worse scores occurred together here. This one observation cannot
establish that batching caused the decline. Fewer callbacks alone do not
establish improved cost effectiveness.

## Full-output concerns retained

The [supplemental content review](conformance/src02-current-live-content-review.json)
read all eighty answers in full. Indices here are zero-based:

- W1 story index 8 uses Caleb and male pronouns, with no girl. It fails the
  requested girl subject. The original review has a clerical sentence-reference
  error: Caleb is named in sentence 2; the pronouns occur in sentences 3 and 5.
  The original text and review remain unchanged; reconciliation records this correction.
- W0 story index 0 returns the dog to a separate owner and family. This strongly
  conflicts with the ordinary reading of "a girl and her dog"; the review also
  records the possible looser thematic interpretation.
- Rescue-and-safe-ending structures recur within P and C. Concrete causes,
  obstacles and actions also differ. These are qualified same-core concerns,
  rather than a new partition or a corrected distinctiveness count.
- Kite-retrieval and lost-boy-reunion premises recur across roles. Each role's
  official partition applies to its own answer batch, not to all roles together.
- C's roof-kite access and floating-basket support mechanism leave plausibility
  questions. These are craft concerns, not demonstrated impossibilities.

All forty stories have five ordinary sentence units on this descriptive read.
All twenty binary replies choose a permitted option; all twenty digit replies
are exactly one digit. Those checks do not establish all-answer semantic quality.

The W0/W1 witness passes cover the frozen host-enforced interfaces, source
copies, capacity, resource, accounting and execution boundaries. They do not
certify semantic compliance. Their subject/relationship failures remain visible;
the witnesses have no official quality or distinctiveness scores.

C's new index calls some positions `missing_scores`. The eight null binary
positions and nine null repeated-digit positions are official non-head
positions: the distinct group heads were scored successfully. They are not
eight or nine failed API judgments. No missing judgment was repaired here.

## Costs, verification and preservation

The dedicated $25 / 512-attempt scope records **90 completed attempts,
$0.753206 spent and committed, zero held, and all twenty-nine original owners
inactive**. A study owner is the saved execution/accounting record for one
stage; it is not a human contributor. The unused $24.246794 and 422 attempts
authorize no new experiment. This completed scope is closed for new work;
recorded costs are not provider invoice reconciliation.
This run does not release or reconcile any earlier experiment's hold.

| Role | Attempts | Recorded cost |
| --- | ---: | ---: |
| P generation and official assessment | 55 | $0.273761 |
| P-to-W0 proposal and W0 generation | 4 | $0.094901 |
| P-to-C proposal | 1 | $0.095139 |
| C generation and official assessment | 28 | $0.156953 |
| C-to-W1 proposal and W1 generation | 2 | $0.132452 |
| **Total** | **90** | **$0.753206** |

There were three source-proposal calls, forty-six generation calls, six official
grouping calls and thirty-five official quality calls. The six official summary
stages needed no model call. The eighty answers therefore need not correspond
to eighty API replies.

The original funded launch and complete search pass the pinned passive readers.
Separate literal joins verify every receipt, original proposal source, full
feedback packet, private child copy and saved answer population. All 451 files
in the captured original evidence/source inventory remained unchanged during
that verification; all 170 current and 169 earlier preparation-map targets also
remain unchanged. The actual twenty-nine owner manifests contain at most 105
input paths, below the earlier conditional 111-path bound for this scope.

Two review-driver mistakes are retained with their corrections: an overly broad
audit hook initially blocked a local hostname lookup, and a manual decoder
initially assumed an uncompressed reply where the saved reply used supported
gzip encoding. The successful checks use the real cached local host metadata
and existing pinned bounded decoder. No application, evaluator or original
run record was changed to pass these checks.

No selected program was executed again, patched or instrumented during review.
No additional experiment API requests were made. Automated host-review inference
is separately unpriced subscription usage. The original run was not repeated.

## What follows

Two gates remain. IMP-01 must compare initial and evolved improvers under
matched starting conditions and resource ceilings, with a feasible declared
grid and prospective uncertainty method. EVAL-02 must evaluate frozen agents
on unseen tasks and obtain the required independent human sample. Working
source evolution and this negative development result close neither scientific
claim. The [regression diagnosis](SOURCE-REGRESSION-DIAGNOSIS.md) explains the
observed decline and proposed remedies. The living plan owns the next treatment
and comparison work; this report grants no new paid run.
