# Cost of checking saved experiment results

The first complete reader-cost observation passed. On one small supplied-response
experiment, checking the saved development result took **22.728 seconds**, checking
the frozen assessment schedule took **25.005 seconds**, and checking the final
assessment took **36.481 seconds**. These are local Windows observations, not
estimated API times or a measured speed improvement.

The [measurement record](conformance/imp01-reader-cost-observation.json) binds
the exact source, original reports, profiles, process result and independent review.
The separate [hosted verification](conformance/imp01-hosted-witness-replay-verification.json)
records PR #102's full Ubuntu pass. Those CI durations measure whole tests,
including creation and execution, and are not these reader timings.

## What was measured

A result reader does more than open a summary. It reconstructs the result from
the original generated answers, evaluation records, source identities, paid-operation
records and frozen decisions. It checks that they agree and that consumed files
did not change during the check. This work needs no API key and makes no provider call.

The observation created a fresh experiment using existing acceptance-test helpers
and supplied programs and replies. It retained all original folders and database
files at their original locations. It did not move or replace previous experiments.

The development fixture has one starting condition, two counted proposals and
two selected descendant slots. Its separate sealed assessment has three roles
(the common starter and the initial and evolved improvers' selected descendants),
two tasks and one assessment repetition: six complete cells and twenty-four final
owners. The retained scratch inventory contains 640 files and 5,285,341 bytes.
That inventory size is not a count of bytes read during verification.

Each of the three public readers ran once with wall and process-CPU clocks,
then once more in a separate profiling pass. The clocks covered each complete
public call, including its final integrity checks. Full before/after inventory
hashing occurred outside the timed calls.

| Complete reader | Plain wall seconds | Plain CPU seconds | Separate profiled wall seconds |
| --- | ---: | ---: | ---: |
| Development result: `inspect_improver_study` | 22.728 | 22.391 | 32.294 |
| Frozen schedule: `inspect_improver_assessment_freeze` | 25.005 | 24.531 | 35.925 |
| Final result: `inspect_improver_assessment` | 36.481 | 36.063 | 52.170 |

All six calls reproduced their original saved report or schedule. Every
before/after inventory matched. All 225 captured source/parameter pins and all
56 database files remained unchanged. No guard refused an operation.
The original process completed with exit code zero; its output and empty error
log are retained separately from the prospective invocation.

## What explains the work

Profiling follows the functions called during a reader and records how often
they ran and how much time they occupied. A function's *cumulative* time includes
its children, so the following rows overlap and must not be added together.

| Observed function | Development calls / cumulative seconds | Final calls / cumulative seconds |
| --- | ---: | ---: |
| Complete source-screen inspector | 26 / 23.976 | 26 / 24.166 |
| Candidate-generation evidence reader | 65 / 14.167 | 113 / 24.878 |
| File/tree capture finish | 127 / 7.846 | 203 / 13.681 |

In the final profiled call, the underlying file-read method ran 22,265 times
(18.088 seconds of its own time), and Windows file-status checks ran 1,027,091
times (10.170 seconds of their own time). The small physical inventory is
revisited many times; these call counts do not identify unique files or bytes.

The source also shows a concrete duplicate: for a prospective generation, the
source-screen reader reconstructs the generated answers, then the publication
inspector reconstructs that same generation again to check its saved summary.
Both checks matter. The [shared generation reader](conformance/imp01-generation-pair-delivery.json)
now uses their common checked evidence within one observation while retaining
publication, authority, accounting, consumed-byte and final integrity checks.
It still rejects changed or missing evidence; a saved summary alone is insufficient.

## Sharing one checked generation

The source-screen, validation/final-assessment and prepared-launch readers now
obtain a checked publication and its generated answers from one reconstruction.
The complete captured evidence, including database sidecar checks, joins the
enclosing reader's final integrity check. Checked execution failures still
supply no answers and cannot start native evaluation.

The generated-source file list stays exactly the same. Publication-only summary
files do not become new inputs to downstream native owners. Older source-only
and baseline routes keep their existing behavior. A sealed generation whose
summary was never published still uses its original recovery path.

Genuine composed tests first observed two reconstructions per paired consumption
in each of the three affected paths. The corrected paths use one and reproduce
the same reports. New checks also retain rejection of late changed bytes and
nonempty SQLite sidecars, original module identity, v1 compatibility and a real
interruption between sealing and publication. These are correctness and work-count
results. The timing table above remains the original measured source cut.
The separate bounded observation below now measures one affected screen reader.

## Finite replay expectation follow-through

The finite-study replay test still expected two complete reconstructions after
the shared reader was implemented. PR #111's original Ubuntu job reports that
assertion as its only failure among 1,789 tests. The unchanged test reproduces
the same failure locally. The correction changes only the expected count and
message, requiring one complete checked reconstruction.

All sixteen existing finite replay, paired-reader and composed-reader checks
pass after the correction. They retain canonical reports, exact original owner
coverage, retired-producer replay, rejection of foreign or missing evidence,
and late byte/database-sidecar checks. Two separate observations still require
two reconstructions. All seven quality checks pass; the implementation and
prepared live inputs are unchanged. The [delivery](conformance/imp01-shared-replay-expectation-delivery.json)
preserves the original failure, local RED/GREEN results, source trace and scope.
Exact PR #116's Ubuntu job now passes all 1,804 tests: zero failures, zero
errors and five skips, with every configured check successful. At the October 24,
2026 13:40:26 UTC checkpoint, its Windows job and both jobs for PR #117 and
PR #118 remain pending. These checks add no timing comparison or scientific
improvement result.

## Bounded paired-screen observation

One small matched case now has a measured comparison at the exact PR #105 and
PR #107 source cuts. Each version created its own original one-task test run,
with two supplied answers, one generation callback and three native stages.
The complete public screen reader ran once; a separate untimed pass counted
evidence reconstructions.

| Complete screen check | PR #105 baseline | PR #107 shared evidence |
| --- | ---: | ---: |
| Wall seconds | 0.5694292 | 0.3986887 |
| Process CPU seconds | 0.546875 | 0.390625 |
| Reconstructions in separate counted pass | 2 | 1 |

Both original reports were reproduced. Actual task, generation configuration,
literal answers, runtime, stages and request/reply content matched across versions.
Each retained test tree has 80 files, 49 folders and eight databases; all remained
unchanged. The four screen owners contain three supplied API replies, with no
provider call from the final summary stage. No real API or container was used.

The original six-cell cohort could not provide this cross-worktree comparison:
its declaration approves the old consumer's exact absolute path. Source and
record inspection shows that the new path would be refused by that approval
check. This was a static finding, not an observed application failure. The
unexecuted comparison drafts remain retained. We kept the original declaration
and source identity intact and prepared separate original matched fixtures.
Their paths, run IDs and provenance differ; their full histories are not identical.

The [bounded record](conformance/imp01-paired-screen-cost-observation.json) retains
the prospective invocation, both exact source inventories, completed child exits,
raw logs, receipts and independent data review. It distinguishes **450 file pins**
from the two repository directory roots. Preparation and hashing warm the cache
and sit outside the timed reader calls. The full child processes took about
10.9 and 9.1 seconds, including those other activities.

This is one warm, guarded observation in a fixed order on a nonexclusive machine.
It is evidence of the specific duplicated-work reduction, with a local timing
observation. It does not establish a production speedup, a scaling law, the cost
of the larger improver grid, or performance of the later PR #108 review bridge.
No repeat campaign or larger performance experiment follows from this result.

## Two starting conditions

A separate observation at source head `b551885` now measures the same three
complete public readers on two starting conditions. Four counted opportunities
produce four selected descendant slots; the starter, initial and evolved roles
in each condition give six arms, twelve sealed cells and forty-eight final owners.
The [measurement record](conformance/imp01-larger-reader-cost-observation.json)
binds the original invocation, process result, reports, profiles and independent
saved-data review.

| Complete reader | Plain wall seconds | Plain CPU seconds | Separate profiled wall seconds |
| --- | ---: | ---: | ---: |
| Development result | 29.498 | 29.266 | 46.027 |
| Frozen schedule | 33.019 | 32.813 | 50.596 |
| Final result | 45.470 | 45.219 | 75.008 |

Seconds are rounded here; the record retains the original clock values. All six
calls reproduce the original reports or schedule with unchanged evidence. The
new retained tree has 1,161 files, 861 folders, 100 database files and 10,248,337
bytes; all 236 source/parameter pins match. The earlier six-cell tree, including
its 640 files and 56 databases, also remains unchanged.

The entire outer process took 2,498.521 seconds, about 41 minutes 39 seconds.
That includes fixture construction, hashing, complete reader calls and separate
profiling. It is not an isolated preparation time. No paid API or real container
worker was used.

This is one warm, fixed-order supplied-response observation on a nonexclusive
machine. Both the source and cohort differ from the first measurement, so their
times do not isolate a speedup or establish scaling. Production latency, costs
for the full future grid, improved-improver effectiveness and scientific results
remain unestablished. The full future-grid cost gate stays open.

## Limits and next verification

The first observation used one small condition on a nonexclusive Windows machine
running Python 3.13.12. Fixture creation and snapshot hashing warmed operating-system caches.
Reader order was fixed. Audit guards and clocks have uncalibrated overhead.
Profiling adds instrumentation and uses a different cache state; subtracting
plain from profiled times does not isolate a causal profiler overhead.
Audit and path-guard costs are not separately exposed in the profile rows;
the file-read and file-status times describe this guarded execution.

There is no production NoveltyBench timing, scaling law, cost result for the
full planned grid or general optimization-speed claim here. Supplied programs
and replies also establish no model-authored competence or scientific improvement.
Costs for the full planned IMP-01 grid and exact-current-head hosted checks
remain open.

The original cohort remains readable by its approved consumer. The bounded
comparison completes the small duplicate-read observation; the two-condition
observation records a larger engineering case. Costs for the full planned matched
improver workload remain to be established. This does not require changing the
official benchmark or its scores.


## Owner census work

The October 28 [evidence-limit recovery](UNIFIED-EVIDENCE-RECOVERY.md) exposed
another source of repeated work. The finite-study census decoded the full task
population and screen record for each retained owner file, even when those files
belonged to the same owner.

The census now derives immutable task counts once per starting screen and the
stage count once. It validates each exact owner-prefix spelling once, while
still checking the complete folder inventory and the original owner-to-funding
bijection. Deduplication uses exact text: Windows path equality must not hide a
foreign or noncanonical prefix with different capitalization. The same changed-
byte and database-sidecar checks still run afterward. No global mutable cache,
old observation reuse, source-selection change or new producer input is added.

A genuine supplied-worker fixture has eight owners. Adding twenty harmless
files to each owner previously increased task-population reconstructions from
24 to 184, screen decodes from 43 to 323 and schedule-pattern validations from
96 to 736, without changing the result. The corrected census keeps the work
counts constant; task-population reconstruction occurs once for this one-screen
fixture. Separate adversarial cases retain rejection of foreign, orphaned,
noncanonical and out-of-range owners, changed funding identities, missing or
extra owners, late byte changes and active database journals.

An intermediate Windows optimization compared Path objects and incorrectly
skipped two differently capitalized late directory prefixes. The added failing
cases exposed that error before publication. Exact-text deduplication fixes it;
the failed intermediate check remains in the delivery history.

These are work-count and integrity checks, not a production timing profile or a
measurement of the full twenty-hour run. The original executing code stays
frozen. Restart remains blocked until the remaining error, reconstruction and
explicit-continuation work in [PLAN.md](PLAN.md) passes its gates.
