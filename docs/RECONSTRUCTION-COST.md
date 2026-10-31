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


## Verified receipt sharing and digest exports

The next October 28 repair removes redundant rereads while keeping fresh final
verification. Eight complete digest-map exports now obtain their fingerprints
from the same pass that checks the bytes. Actual byte consumers, SQL/funding
reads, early individual-file checks and original source-reader identity checks
remain in place. Native readers still finish every retained sibling tree.

Nested adoption now freshly finishes the source, validates the complete
prospective receipt union, and only then changes the receiving capture. It
rejects conflicting originals, byte/path overflow, missing database receipts
and database receipts exceeding their individual field limit. It preserves
legacy sidecar/database insertion order as well as complete absolute-path
fingerprints. No cache or arbitrary external digest-map admission is added.

This changes the observation cut: newly adopted paths were checked at the fresh
source finish. The receiver's later fresh finish remains mandatory and rejects
subsequent drift before active work. Neither version supplies an atomic
filesystem snapshot. Work-count tests reduce adoption from three data reads to
one fresh source pass, and eliminate twelve redundant file reads after the
final candidate-generation verification. A genuine plain-generation case also
preserves Path keys and the exact authority exclusion without a second pass.

Independent review found and reproduced three edge cases before publication:
legacy external-key collision ordering, a database marker without any receipt,
and a previously read database that exceeded the narrower ledger field bound.
The final union preflight rejects invalid sources and preserves the old order.
The final 90-method cohort passes. A separate older 68-method cohort had 65
passes and three obsolete test-double errors; replacing that duplicate fake
reader with actual NativeEvidence and rerunning the affected cases resolves
those fixture errors. The cuts remain separately recorded rather than being
combined into a claimed 149-method final pass.

These are work-count and custody results. Whole-study performance, full-layout
capacity and explicit paid continuation remain separate gates in PLAN.md.

## Fresh copies of validated artifacts

The actual saved-run profile records 13,974 artifact-copy calls, 8,137 task-
population reconstructions and over eight million metadata-row validations.
Its cumulative timings overlap and include profiler overhead; they cannot be
added or treated as a controlled speed comparison.

One shared copy method was repeating strict input validation on immutable bytes
that had already passed that validation at construction. It now uses the standard
JSON decoder to return a fresh editable copy. All nine in-repository artifact
types still validate new bytes strictly; canonical bytes and fingerprints stay
unchanged. Callers can edit their copies without changing the original or a
later copy. This introduces no raw-byte cache or parsed-object cache.

A genuine 1,000-row synthetic workload makes twenty record copies. It reproduces
twenty redundant strict decodes and validation serializations before the change;
the new copy path performs zero of those extra passes. Sixty malformed-constructor
subcases still reject. The original nested-copy, frozen-data, format and identity
assertions remain; their two decoder-count proxies now count the actual decoder.

Ninety-nine methods pass before the capacity merge. On the merged source, another
29-method copy/answer/format cohort and the eight capacity methods pass; these
overlapping cuts are recorded separately. Two hundred deterministic nested JSON
cases also reproduce the old views exactly. Configured source checks pass.
[The delivery](conformance/validated-artifact-views-delivery.json) records these
cuts and the separate actual-run check; full hosted coverage remains separate.

The merged repaired source also reconstructs the actual saved study under the
finite v2 policy: 174 owners, 604 attempts, $4.845090 spent/committed, zero held,
and the same absent witness at 1/1/1/0. That guarded check took 861.192 seconds
locally. It used in-memory SQL snapshots and made no provider calls or writes
to the run. This single observation is not a controlled before/after speed
experiment, a whole-run duration estimate or paid continuation authority.

```powershell
python -B -m unittest discover -s tests -p test_validated_artifact_views.py -v
```

This optional developer command runs the five new synthetic checks once, with
no API keys or paid calls. Use the checkout containing this test; no separate
window is needed. Ctrl+C stops it.


## One passive call's directory metadata

The study reader can now share its initial directory listing within one passive
reconstruction. Each capture receives its own editable listing. Different path
spellings, observation limits, threads or held-writer identities do not reuse that
listing. The metadata registry uses the selected entry and path limits; when full,
it falls back to the ordinary fresh directory walk rather than rejecting valid work.
It retains no file contents and disappears when the call ends.

Every capture finish, fingerprint export and public adoption still checks original
bytes, SQLite sidecars and its full directory tree freshly. A successful passive
call also freshly checks every registered initial tree and its relevant held lease.
Unrelated parent-folder locks are outside this optimization's scope. An existing
failure stays primary and discards the invocation's metadata.

Four actual captures of the same small directory previously made eight walks:
four initial walks and four final checks. Sharing now makes six: one initial walk,
the same four final checks and one fresh check when the passive call exits. This
is a work-count result, not a measured production speedup. The original paid run,
its source pins and its authorization are unchanged.

A separate natural study check uses the existing supplied-worker fixture, first
at its initial state, then after its common screen, mutation witness and first
counted plan. The second state stops before any counted proposal. Both versions
reproduce the same next action, coverage, authorization, owner accounting and
complete fingerprints, without changing files or sending another request.

| Natural reader state | Ordinary walks / returned entries | Shared walks / returned entries |
| --- | ---: | ---: |
| Initial one-shot state | 2 / 54 | 3 / 81 |
| First counted plan | 65 / 2,824 | 51 / 2,102 |

The initial state has an extra final walk; the optimization is not beneficial
for every call. In the repeated state, constructor walks fall from 24 to five;
all 41 strict capture finishes remain, followed by five fresh exit walks. Whole-
study constructor walks fall from three to one. Smaller one-shot witness trees
still incur exit-check overhead. These counts do not establish a runtime speedup
or prove that the larger continuation meets its existing action timeout.

The [delivery](conformance/passive-tree-observation-delivery.json) retains both
genuine failures, final source cuts, natural counts and local checks. Remaining
development/final/plain continuation acceptance and paid handoff stay open.

```powershell
python -B -m unittest discover -s tests -p "test_passive*.py" -v
```

This optional developer command runs the small supplied-study and file-integrity
checks once in temporary test folders. It may take a few minutes, needs no API
keys and makes no paid calls. Use this checkout; no separate window is needed.
Ctrl+C stops it.


## Synthetic reconstruction profile after the 657-attempt stop

The October 30 [profile record](conformance/synthetic-reconstruction-profile-observation.json)
checks a small supplied fixture at the frozen `c54819f` source, with 96 public
source pins. It performs one unprofiled strict reconstruction and exactly one
profiled reconstruction using the existing directory-list sharing mechanism.
No application code was changed by this observation.

Both calls reproduce the same checked signature, next `prepare_proposal` action
and supplied activity. The retained fixture stays at 185 files and 1,506,730
bytes with the same complete inventory fingerprint. Each call makes 1,970
capture reads returning 21,682,686 bytes across 84 distinct paths; each also
records 40 owner parses, 184 owner requests and 347 task-population
constructions. These are repeated-work counts, not counts of unique owners or
physical disk transfers.

| Directory-list work | Strict call | Shared call |
| --- | ---: | ---: |
| Constructor walks | 24 | 5 |
| Strict capture-finish walks | 41 | 41 |
| Fresh passive-scope exit walks | 0 | 5 |
| Total walks | 65 | 51 |

This confirms the earlier optimization's work counts in this supplied case;
it is not a new optimization. The strict call took 6.184625 seconds without a
profiler; the shared call took 8.961907 seconds with a profiler. Different
instrumentation and cache order prevent a speed comparison. The complete
observation took 103.714291 seconds, including preparation and verification.
Public cumulative profile rows overlap and must not be added together.

Before profiling, a separate SQLite-guard probe passed 42 checks, including 14
expected denials. A fixture-link probe passed 19 checks, including ten expected
denials. These guards constrain trusted, pinned fixture code; they are not an
operating-system sandbox. The fixture uses supplied replies and owned synthetic
databases. The observation records zero actual provider calls, container starts,
original-data reads, original-file SQL connections and original writes.

The unexecuted v1 draft and v2–v4 setup failures remain separate evidence.
Each failed setup records zero profiled reconstructions. V5 completed, and its
saved result received independent review. It does not identify hotspots in the
actual 657-attempt history, reconcile uncertain container cleanup, validate a
third control profile or clear another live command. Next, continue the bounded
current-owner metadata and compatibility investigation and collect exact-source
PR #190 CI evidence. The command remains on hold under [PLAN.md](PLAN.md).


## Current 193-owner metadata after the 657-attempt stop

The [metadata delivery](conformance/current-owner-metadata-delivery.json) records
one bounded observation of the original search authority selected by the exact saved
outer observation. SQLite queries ran only on its in-memory deserialized image.
The new JSON retains registration fields and status/cost aggregates; it copies
no response payloads or owner roster into repository documentation.

There are 193 registered owners: 174 from the preserved 604-operation cut and
19 later registrations. Independent saved-metadata review confirms all 174 old
run IDs, registered manifest hashes and directory anchors match that cut and
remain inactive/deactivated. Their aggregate stays at 604 completed operations,
$4.845090 spent and zero held. The later owners add 53 operations/$0.678054.
Current search totals are 657 completed operations/$5.523144/zero held, with no
reserved, dispatched or unknown operations. The sole active owner is the next
screen's task-0 generation owner, with zero operations and zero held.

These are registry comparisons, not fresh reads or validation of owner manifests,
ledgers, requests or receipts. Other grants were not opened: whole-study totals
are explicitly labeled metadata from the saved outer observation. The earlier
604 cut is preserved rather than replaced by the current roster.

The first supplied v2 rehearsal retained six passes and one full-main error whose
exact cause was discarded. Supplied v3 passed seven methods. The first actual v2
census then refused with `input_open_changed`, without identifying its input.
A separate three-input metadata probe reproduced a Windows 3.13.12 stat/fstat
ctime discrepancy on the authority. [CPython issue #157671](https://github.com/python/cpython/issues/157671)
contains 3.14 reproductions; support for this host's 3.13.12 finding comes from
the retained local measurement. [Python's 3.13 documentation](https://docs.python.org/3.13/library/os.html#os.stat_result.st_ctime_ns)
provides Windows birth time and deprecates ctime for creation time. The new
observer missed the existing cross-API/same-API distinction already present in
[releases.file_hash](../buddha/releases.py), lines 362-367.

External census v3 uses Windows birth time across APIs while retaining ctime
within each API and in the final path identity. No application source changed.
Supplied v4 passed all eight methods, including a native modified-file case and
injected identity/ctime refusals. The separate actual v3 observation finished in
0.185521 seconds, retaining the same authority image SHA-256 before and after:
`9bdc6e040b548c1997faec81b796fea1be8b6000678954dc1ed4163a5c972b3a`.
It made no original-file SQLite connection, original mutation, provider call or
container start. This is a metadata observation, not a reconstruction-time bound,
atomic snapshot, receipt audit or diagnosis of the original executor failure.

Next prepare one bounded reconstruction/profile of the actual 657-attempt
history using this 193-owner roster and the existing frozen two-profile controls.
No third helper profile is adopted automatically. Cleanup reconciliation,
retained-history compatibility, exact-source hosted completion and live clearance
remain open; the command stays on hold under [PLAN.md](PLAN.md).


## Bounded profile of the actual 657-attempt history

The [actual-history profile](conformance/current657-reconstruction-profile-delivery.json)
ran the whole passive checker once, with a 300-second observation limit and a
330-second parent process limit. It stopped as **partial_deadline**, saved its
profile and exited normally with the incomplete-result code. The reconstruction
prefix took 300.142179 seconds; the parent took 305.304399 seconds including
startup and final checks. The whole checker and its first study restoration
did not return. This is not completed recovery verification.

The observed prefix completed 1,666 task-population constructions; a 1,667th
was interrupted. It made 1,666,495 metadata checks, 16,729 capture reads returning
9,265,872,222 bytes across 2,462 paths, and 390 owner parses for 1,300 owner
requests. Those are repeated application-work counts, not unique disk data or
physical transfers. They identify population processing as a concrete repair
target; the next source review must establish which work can safely be reused.

All 98 reviewed public source/support pins, seven named inputs and four
authorization-file hashes remained exact on final rechecks. The guard recorded
no denied operation. It made no model call, container start or original write;
SQLite opened only memory databases. The 186 successful inner capture finishes
do not establish the interrupted whole-history finish. Original metadata still
comes from the separate 193-owner census; this profile does not replace it.

The supplied-memory boundary check passed all 44 checks. Its earlier two failed
rehearsals remain recorded: a generic failure, then a typed failure in supplied
image setup after 15 checks. [SQLite's serializer](https://raw.githubusercontent.com/sqlite/sqlite/version-3.50.4/src/memdb.c)
internally asks for a page count, which the actual reader does not need or permit. Building the known
supplied image before guard installation corrected that fixture without
relaxing the reader. The actual application and frozen source were unchanged.

Only pinned public function/caller rows are exported; private code, locals and
filenames are excluded. Cumulative profile rows overlap, and some exceed the
300-second observation time. Do not add them or treat this one instrumented
prefix as a speed comparison. Named hash checks are not an atomic filesystem
snapshot. Cleanup, retained-profile compatibility, CI and live clearance remain
separate gates under [PLAN.md](PLAN.md); the run command remains on hold.


## Local reuse of already validated task data

The [first local reuse repair](conformance/source-screen-local-reuse-delivery.json)
removes two proved sources of duplicate work. Controls, materialization and
preflight routines now bind their immutable selected TaskSet once. The passive
collector passes the SourceScreen it already validated to its private source
helper, instead of reconstructing the same screen for every task. The failed-
source path uses the same local-binding approach. No cache was added.

In the same supplied 1,000-row/two-task fixture, controls/materialization/
preflight population scans fall from16/16/19 to10/10/7:51 to27 in total. A
separate saved-screen inspection constructs its strict SourceScreen once
instead of three times. Literal native bytes, typed-ID order, fresh nested
copies, unchanged saved reports/files/accounting and malformed/tampered input
rejections pass at the declared synthetic scope. Four new and seventeen
existing methods pass, all seven configured local quality checks pass, and an
independent rerun of the four new methods passes. These are work-count results,
not a measured speedup for the actual retained study.

All artifact constructors and file/digest/runtime/owner/publication checks stay
strict. Every evidence finish remains fresh. The two production files are
existing helper roles outside CORE; helper membership, benchmark requests and
model settings do not change. The executing c548 source is untouched.

The current history contains A and B producer profiles and one active B owner.
The new helper source cannot silently replace that owner or become a third
admitted profile. A frozen-B one-action path exists, but needs a new checked
study descriptor and closes the whole prepared screen, not just generation.
Any later new-source adoption still needs a bounded versioned owner/profile
relation preserving earlier A/B feedback. This is a compatibility gate, not
another spending allocation or a cleared command. [PLAN.md](PLAN.md) remains
the scheduling authority.

```powershell
python -B -m unittest discover -s tests -p test_source_screen_local_reuse.py -v
```

This optional developer command runs the five supplied-data checks once in
temporary folders. Run it from the project folder containing this version of
the code. It needs no keys, makes no paid calls and starts no containers. No
separate PowerShell window is needed; Ctrl+C stops it.


## One selected-task view per immutable screen

The [instance-local task-view repair](conformance/source-screen-task-view-delivery.json)
reuses the selected TaskSet derived from one already validated SourceScreen.
Its public `tasks` property, including the existing inspection interface, stays
in place. A private standard-library `cached_property` retains that immutable
artifact for this instance; its calculation is the unchanged old getter body.
There is no shared lookup table, persistent cache or cache of file/owner reads.

In the supplied 1,000-row/two-task fixture, population scans change as follows:
The three routines run in the listed order on the same screen. The first builds
the view; the later routines reuse it. These are not separate cold-entry costs.

| Routine | Previous local-binding repair | Instance-local view |
| --- | --- | --- |
| Controls | 10 | 7 |
| Materialization | 10 | 4 |
| Preflight | 7 | 4 |
| Total | 27 | 15 |

A separate check reads the same screen's task view five times: population scans
fall from 15 to three. A newly constructed screen still performs its own three
view-construction scans. Exact selected bytes, fingerprints, string-versus-integer
ID order and fresh record copies remain unchanged. Malformed new declarations
and changed saved task/recipe data still reject. Constructors, file/digest/owner
checks and every fresh capture finish remain strict.

Both regression cases fail before the repair and pass afterward. Seventeen
selected implementer methods and all seven configured quality checks pass at
the recorded source cut. A separate independent rerun reports all five local-
reuse methods passing; that summary is retained in the parent review message,
not a separately supplied raw log. The delivery keeps these observations separate.
They establish work reduction in supplied fixtures, not a timing ratio, completed
actual-history reconstruction or scientific improvement.

There is a memory tradeoff: each live SourceScreen can retain one additional
TaskSet containing the complete sealed dataset payload. Its canonical bytes can
occupy up to 32 MiB, plus object/dictionary overhead. This is not a total RAM
bound; many screens, temporary record copies and concurrent calculations can
retain more. Python 3.13 can compute the first cached value more than once when
threads arrive together. The calculation is deterministic, but the measured
once-per-instance reuse applies to sequential access, not a concurrency guarantee.
[Standard-library contract](https://docs.python.org/3.13/library/functools.html#functools.cached_property).

The same production/test bytes are now integrated on parent ed387f3. One bounded
composed observation passes seven methods (the five local-reuse methods plus
two targeted screen-recovery methods) in36.215 seconds, with five requested
static checks. The earlier17-method/full-seven-quality cut stays separate.
Source review found no defects. Object memory retained by this task view is
outside the evidence reader's raw-byte retention budget; aggregate and peak
process memory have not been measured. No actual-history timing is inferred.

This is prospective helper source. It does not change the frozen B checkout,
replace existing owner bindings, authorize spending or clear the stopped command.
Source adoption and actual retained-history checks retain their own recorded
scopes under [PLAN.md](PLAN.md).


## Lease-content check before constructor reuse

The [lease repair](conformance/lease-capture-repair-delivery.json) addresses the
Windows failure in PR #201. A run lock can be rewritten without a detectable
change to its size or timestamps. The constructor-sharing context now also
hashes its small contents. Changed bytes require fresh construction; unreadable,
non-regular or oversized lock files disable this optional reuse. The regular file reader
and every capture finish retain their existing checks.

The probe reads at most four known lock files, at most 128 bytes each, per
context check. Only their digests are retained. These optimization probes are
outside the capture's raw-byte accounting; their aggregate overhead is unmeasured.
Separate metadata/read observations are not an atomic snapshot and do not prove
writer identity or detect every transient change that is later undone.

A deterministic test forces identical metadata across three changed lock files:
it fails before the repair and passes afterward. The 19-method scoped cohort
finishes in 117.395 seconds, with 18 passes and one existing Windows symlink-
privilege skip. This includes natural supplied-study restoration parity; it is
not a comparable-size history result. A later loop-binding lint correction is
followed by a passing affected regression, lint, format and compilation check.
Types, security and both dependency audits also pass at their recorded cut.
Hosted verification of the new source remains pending; no full-suite pass or
live clearance is claimed.

```powershell
python -B -m unittest discover -s tests -p test_passive_capture_scope.py -v
```

This optional developer command runs the passive-reader guard checks once in
temporary folders, including supplied-study restoration. Run it from the project
folder containing this code version. It needs no keys, makes no paid calls and
starts no containers. It needs no separate PowerShell window; Ctrl+C stops it.
The whole module includes broader checks than the scoped cohort reported above.


## Comparable supplied workload

The fresh-comparison preparation reuses the existing source-study scheduler,
Gateway, authority records and supplied-worker fixtures. It adds no production
controller or orchestration dependency. Eight test/helper files parameterize
those fixtures while preserving their one-task/two-answer defaults.

The small exact-parent cohort passes four methods in 81.213 seconds: the legacy
default, 1,000-source-row/three-task/ten-answer bootstrap, and two environment
metadata checks. The scaled bootstrap creates thirteen genuine supplied owners,
46 operations and zero held. Its dataset is 645,466 bytes and canonical TaskSet
1,113,890 bytes. This smoke uses only 64 synthetic environment members.

The larger declared workload uses 24,043 actual synthetic installed-file members,
a matching manifest/helper and at least 4,013,984 bytes of supported environment
metadata. A source screen is at least 5,315,388 bytes. Source/dataset/split records
are sized before any owner is created. Normal ledger and receipt writers create
the history; no historical row, operation or manifest is fabricated or rewritten.
After nine admitted descendants, the intended cut has 193 study owners and 660
operations, with the next screen's first generation owner prepared but uncalled.
Earlier fixture-bootstrap owners remain outside that study count.

The producer has a 1,200-second limit. Only if it reaches and checks that cut does
one fresh restoration, current-source check and complete reader finish run under
a separate 900-second limit. A timeout or error remains a partial result with
its stage, reason and retained files. There is no automatic retry or extension.
The driver denies real network/container calls and retains synthetic directories.

These are targeted source/metadata/count dimensions, not an exact copy or a
universal worst case. Answer text, agent programs, model replies and request
bodies are synthetic; costs are fixture accounting, not live-spend estimates.
No Docker confinement, original-history compatibility, model quality or
scientific improvement follows. Remaining phases, exact-source hosted CI,
outgoing request settings and a separately reviewed funded handoff stay open.

The final five scoped methods pass in two separately bounded observations:
162.612 seconds for the complete tiny witness and 78.882 seconds for the four
bootstrap/environment checks. The witness behavior test uses six source rows,
one environment resource and ordinary one-call supplied workers, yielding
14 study owners/11 operations. It retains all three tasks' ten complete answers;
its cheaper call counts are not the full workload's 660-operation proof.

The first large-metadata producer stopped after 290.937 seconds at a witness
proposal assertion. Its retained feedback contains three task records, while the
old fixture expected one. The real controller gives the improver full selected
feedback and restricts only its further-generation check to the first task.
That fixture expectation is corrected. An earlier wrapper failure caused by
stripping Windows architecture variables is retained separately and corrected
without permitting subprocesses through its guard.

Three later 180-second observations remain partial. A diagnostic reached
14 owners/50 operations and began witness publication; frame samples show
filesystem/source/history verification doing work, not a quantified dominant
cost. A later small-check failure caught an unforwarded callback setting, which
is now corrected. These records are not combined into a scale-gate pass. The
newly pinned corrected full producer is unexecuted at this publication cut.

```powershell
python -B -m unittest discover -s tests -p "test_scale_*.py" -v
```

This optional developer command runs the five supplied-fixture checks once in
temporary folders. Run it from the project folder containing this code version.
It may take several minutes. It needs no keys, spends no API money and starts no
containers. It needs no separate PowerShell window; Ctrl+C stops it. This command
runs the small checks, not the large producer or its performance gate.
