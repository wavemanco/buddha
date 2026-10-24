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
Both checks matter. The next bounded optimization should reuse their common
checked evidence within one observation while retaining publication, authority,
accounting, consumed-byte and final integrity checks. It must still reject
changed or missing evidence; a saved summary alone is insufficient.

## Limits and next verification

This is one small condition on a nonexclusive Windows machine running Python
3.13.12. Fixture creation and snapshot hashing warmed operating-system caches.
Reader order was fixed. Audit guards and clocks have uncalibrated overhead.
Profiling adds instrumentation and uses a different cache state; subtracting
plain from profiled times does not isolate a causal profiler overhead.
Audit and path-guard costs are not separately exposed in the profile rows;
the file-read and file-status times describe this guarded execution.

There is no production NoveltyBench timing, scaling law, full multi-condition
cost result or measured optimization speedup here. Supplied programs and replies
also establish no model-authored competence or scientific improvement. The
larger IMP-01 cost and exact-current-head hosted checks remain open.

The retained original cohort allows the next change to be checked against the
same evidence. A correct optimization needs failing checks for duplicate work
and evidence corruption, then passing correctness checks and a separate measured
comparison. The official benchmark and its scores remain fixed.
