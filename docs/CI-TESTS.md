# CI test progress and the 60-minute stop rule

CI keeps five matrix jobs on each of Windows and Linux. The full-suite lane
checks the complete discovered unittest suite; the narrow leaf-document lane
validates its documents and omits only that long suite. All setup and quality
checks remain. In the full-suite lane, every discovered test occurrence belongs
to exactly one process on each OS; duplicate names and original order are
retained. Class and module fixtures run separately in each process that needs them.

The largest finite-study test has its own process. The other tests are assigned
by a stable hash of their names and the configured CI partition seed. Each
process prints the full assignment list,
its selected count and a shared inventory fingerprint, so missing or duplicate
assignments can be checked. Discovery errors, empty groups and an ambiguous
isolated name stop the check instead of silently reducing coverage.

## Narrow leaf-document lane

Only these five exact paths are eligible; there is no Markdown/JSON wildcard:

- `docs/PLAN.md`
- `docs/FRESH-REQUEST-OBSERVATIONS.md`
- `docs/FRESH-CONFINEMENT-OBSERVATIONS.md`
- `docs/conformance/fresh-request-observations-delivery.json`
- `docs/conformance/fresh-confinement-observations-delivery.json`

The guard verifies the checked-out GitHub merge against its declared base and
head, then examines the complete pull-request change, including earlier commits.
Eligible regular-file additions/modifications must pass UTF-8, strict report-JSON
and Git whitespace checks. Duplicate fields, nonfinite decoded numbers and
wrong report formats fail visibly. An earlier code change cannot hide behind
a documentation-only final commit.

Non-PR runs, empty or unverifiable changes, unknown/mixed paths, renames, deletions
and nonregular files retain the full suite. Code, workflow, dependency, runtime
and protocol changes therefore keep full checks. All ten job names, tool setup,
audits, lint, format, types, security and compilation remain; only the long
unittest step can be omitted. Its 3,600-second progress rule is unchanged.
A successful leaf lane is not a completed full test suite.

The [delivery record](conformance/ci-leaf-docs-delivery.json) separates earlier
checks, the exponent-overflow regression and final checks. Hosted execution of
this new lane has not yet been established; local Git fixtures are not hosted
fork proof. The implementation PR itself changes code/workflow and takes the
full lane.

For developers, this optional command runs the nine focused guard tests once in
the current PowerShell window using temporary local Git repositories. It needs
Python and Git, no API keys or Docker, and spends no model budget. Ctrl+C stops it.
It does not run the full suite or submit GitHub jobs.
Expect `Ran 9 tests` and `OK`; zero tests means this checkout lacks the slice.
This direct command has no enforced overall time limit. The saved local cohort
took 3.168 seconds; that observation is not a deadline.

```powershell
python -B -m unittest discover -s tests -p test_ci_leaf_docs.py -v
```

## What counts as progress

The clock starts before test discovery. A completed test, subtest or fixture
outcome advances it. Successes, failures, errors and skips all count as real
outcomes; a failure still makes the test run fail. Merely starting a test,
printing text or emitting a heartbeat does not advance the clock.

Large finite-study fixtures also report individual worker checks after their
existing input assertions and worker return. They check that cleanup completed,
and shared fixtures report through the test that is actually running. Original
execution exceptions still propagate; failed checks still fail the test run.

After 3,600 seconds without such an outcome, the runner stops its worker and
contained child processes, prints an explicit incomplete result and returns
exit code 124. The record includes the reason, last test name and time without
progress. A runner/containment failure returns 125; Ctrl+C returns 130. A normal
worker completion also needs a checked terminal receipt; an abrupt exit with
code zero cannot make unfinished tests pass.

On Windows, the worker is held behind a startup gate until it belongs to a
native Job Object. On Linux, it uses a private process group. Cleanup stops
inherited descendants, including on ordinary completion. The Linux group does
not contain a process that deliberately creates another session. This helper
runs trusted repository tests; it is not the sandbox for generated agent code.

The limit is **inactivity, not total runtime**. A test run can take longer than
an hour while genuine checks keep completing. A long method with no completed
subtests can hit the limit even while it computes. Such a method needs visible,
meaningful acceptance checks; periodic output cannot substitute for them.

Setup, installation and the other non-test checks each have a separate fixed
60-minute step limit, so a stalled tool outside the test runner is bounded too.
The test step uses the progress clock instead of that fixed limit. An idle
timeout fails the job explicitly; it does not report unfinished tests as passed.

Existing hosted jobs do not gain this guard retroactively. Their elapsed time
or current step's start time does not prove a stall. Cancellation under this
rule needs actual evidence of the last genuine progress.

## Timing checks use a separate short limit

The temporary watchdog tests use a five-second inactivity limit and a
30-second outer timeout. The production limit remains 3,600 seconds.
The older half-second noise test could expire before its first print on
Windows. PR #177 failed that assertion; the same fixture was still present
in PR #179. An external one-second delay reproduces that failure without
changing the production runner. The exact scheduling point in the hosted
failure was not recorded.

The repaired fixtures keep real processes and all timeout/progress assertions.
Markers prove discovery, class setup, noise and descendant bodies were entered.
Noise and hangs last longer than five seconds; real completed subtests span
six seconds, with shorter gaps between outcomes. The descendant check still
proves its output stops after cleanup. Printing text never counts as progress.

The workflow now uses five groups to separate the three large finite-study
fixtures under the existing assignment rule. The named isolated test stays
isolated, and the assignment and 3,600-second rule are unchanged. This changes
the workload per job; it does not predict future job runtime. The existing
partition and actual-process checks cover both four and five groups without
changing discovered test names.

The final local check also exposed a Windows cleanup race: the worker had
exited, but its temporary progress file briefly rejected deletion. A separate
diagnostic observed that sharing violation; it did not identify the holder.
Cleanup now retries only Windows sharing violations for up to ten seconds.
Other errors, or a sharing violation that lasts beyond that limit, still fail.
The original failure and diagnostic remain recorded; a later pass does not
erase them.

The [delivery record](conformance/ci-idle-fixture-timing-delivery.json) keeps the
original failure, deliberate reproduction and focused local checks separate.
All 22 helper tests pass locally in 41.949 seconds. The descendant test checks
the emitted termination time separately from bounded directory cleanup, and
still proves the descendant stops writing. These focused checks do not
establish that the complete hosted matrix passes.

### Observed hosted completion for PR #180

The complete [PR #180 CI run](https://github.com/wavemanco/buddha/actions/runs/40824333819)
has now passed all ten jobs on its exact source head `2d199b4e`. Each OS
completed the full 2,135-test inventory, assigned once across five groups and
completed in the recorded order:

| OS | Passed | Skipped | Failures or errors |
| --- | ---: | ---: | ---: |
| Linux | 2,130 | 5 | 0 |
| Windows | 2,134 | 1 | 0 |

All seven quality checks passed in every job: 70 successful steps in total.
A separate evidence reader also passed nine checks that reject incomplete,
misordered or conflicting records. The [hosted completion record](conformance/ci-idle-hosted-completion.json)
binds the exact checkout, complete assignment coverage, all ten saved job
receipts and log fingerprints. Its evidence comes from the completed job logs
and step records; the worker's internal terminal files were not downloaded
separately.

This closes the full hosted verification of that CI maintenance change. The
earlier PR #177 failure and local diagnostic results remain recorded. It does
not establish that later source heads pass, predict future job duration, or
show that the interrupted paid experiment has recovered. The production stop
rule remains 60 minutes without genuine test progress.

## Optional local commands

Run these from the checkout that contains `ci_test_shard.py`. Each command runs
once in the current PowerShell window; no separate window is needed. Ctrl+C
stops it. None makes model API calls. The runner creates temporary files and
Python may create ordinary bytecode caches.

```powershell
python -m unittest discover -s tests -p test_ci_test_shard.py -v
```

This checks the small runner itself with temporary test programs and short
deadlines. It checks assignment coverage, ordinary unittest behavior, real
progress, stalled workers and process cleanup. It does not run the expensive
Buddha application acceptance suite or establish that the full suite passes.

```powershell
python -m ci_test_shard --count 1 --index 0 --list-only
```

This imports the test modules and prints the complete discovered inventory in
one group, without running test bodies. It helps inspect what would be checked.

```powershell
python -m ci_test_shard --count 1 --index 0
```

This runs the complete suite in one guarded process, with the same 60-minute
inactivity limit. It can take several hours and create temporary test fixtures.
It is an optional full local check, not needed merely to inspect the inventory.

The workflow supplies five groups, the exact isolated test name and the same
3,600-second limit. All existing lint, formatting, type, security, dependency
and compilation checks remain required by the workflow. Local helper checks
and an inventory are not a passing full hosted matrix. Current delivery and
remaining verification are recorded in [PLAN.md](PLAN.md).

## Windows cost investigation — November 3, 2026

The user requested faster Windows checks without compromising quality and asked
that the current run proceed unchanged. ENG-CI-01 in [BACKLOG.md](BACKLOG.md#eng-ci-01-reduce-windows-verification-cost-without-reducing-coverage)
records the boundary; this work is parallel to the approved history observation.

The completed shard 1 jobs in [run 41608659735](https://github.com/wavemanco/buddha/actions/runs/41608659735)
use source `9ded9b9f3decb6a1d66a6497efa53b3e1ce5dd62` and the same 593 selected
test IDs from the 2,264-occurrence inventory. Windows skipped one; Linux skipped
three. These are observed job timings, not a controlled machine comparison.

| Work measured | Windows | Linux |
| --- | ---: | ---: |
| All selected tests in shard 1 | 8,073.995 s (134.6 min) | 1,297.521 s (21.6 min) |
| Original controllers, resume and keyless replay | 1,143.003 s | 197.437 s |
| Proposal-capacity checks across the six-cell grid | 1,002.969 s | 147.091 s |
| Prospective six-cell comparison | 938.088 s | 128.630 s |

The three methods together account for 3,084.060 Windows seconds, about 38% of
that job's test time. The test suite occupies about 99% of its captured log
interval; tool installation and quality checks account for roughly 72 seconds
outside it. Dependency caching could save some setup time, but does not explain
or address the dominant measured cost.

These integration tests construct experiments, preserve accounting and source
records, reconstruct histories, and verify recovery and keyless replay. Several
reach the same fresh-file/history verification path repeatedly. The stable name
hash distributes test counts, not measured durations; 593 short tests and 593
integration tests are not equivalent workloads. Tests in one assignment execute
in one contained worker, rather than starting a process for every test.

All five Linux groups completed in 3,586.268, 1,297.521, 4,197.521, 1,311.636 and
3,041.937 seconds respectively. The isolated group contains just one end-to-end
method; that same method took 9,829.672 seconds on Windows. Redistributing other
methods cannot shorten that observed isolated method itself.

The bounded local profile now completes one unchanged source-search recovery
case with fresh supplied fixtures. It performs 55 source-screen collections,
93,855 calls to the ancestor guard, 2,191,311 filesystem status calls and 116,574
buffered reads. This establishes substantial repeated verification work in that
case. Native API binding setup takes under 1% of its profiled time and is left
unchanged. Neither these results nor the OS ratios identify antivirus, a specific
filesystem mechanism or SQLite latency as the cause of the Windows difference.

Any repair must retain fresh reads and all identity/link/reparse, byte-bound,
hash, final-observation, accounting and cleanup checks. Existing test occurrences,
both OSes, all ten jobs, every quality check, contained workers, terminal receipts
and the 60-minute genuine-progress rule remain required. Local profiles are not
passing hosted CI or a claim that the separate 193-owner history gate fits.

### First bounded repair: reuse the path calculation

The candidate reuses only the calculated ancestor paths for ordinary concrete
paths. It still checks every ancestor against the filesystem on every call.
It caches no file contents, hashes, stat results, open handles or permission to
trust a file. Exact spelling and path type form the key. At most 512 entries are
retained; spellings over 1,024 characters or 32 separators, and custom path types,
keep the original lazy behavior. These are cache eligibility limits, not new
reasons to refuse a path. The lexical objects use process memory outside the
raw-byte reader allowance; this is not a process RAM ceiling.

Both runs of the matched local case passed, with their children joined and their
respective source pins unchanged:

| Observed work | Before | Candidate |
| --- | ---: | ---: |
| Ancestor-path construction steps | 3,117,019 | 956,557 |
| Filesystem status calls | 2,191,311 | 2,191,311 |
| Buffered reads | 116,574 | 116,574 |
| Instrumented elapsed seconds | 151.303 | 147.205 |

The construction reduction is established. This one sequential instrumented pair
does not establish a reliable throughput gain: buffered-read time itself changed
from 40.037 to 49.389 seconds. Function times overlap. Whole hosted CI savings
remain unmeasured, and this small repair does not solve the repeated-I/O cost.

The three earlier profiling attempts stopped on instrumentation admission errors:
a required public fixture, owned temporary descriptors and internal atomic links.
Their partial records remain; they are not production defects or timing baselines.
The final pair uses the same corrected collector, case, assertions and bounds.
The [delivery record](conformance/windows-ci-performance-delivery.json) binds the
actual observations, original regression, 61 focused checks and quality results.
The existing 2,264 test bodies remain, with four additional methods. No workflow,
runner, dependency, containment, durability or watchdog setting changes here.

This optional developer command runs those four new checks once in the current
PowerShell window. It uses temporary local files, needs no keys or Docker and
spends no model budget. Ctrl+C stops it. It does not run the full suite.

```powershell
python -B -m unittest discover -s tests -p test_releases.py -k AncestorGeometryTests -v
```

Next, use the retained duration evidence to assess a single optional seed for
the existing assignment hash, keeping isolated group 0 and every test occurrence
in its original order within its new group. Offline estimates must stay separate
from actual hosted savings. No runtime duration database or new scheduler is
needed. Further reduction of repeated history reads remains separately bounded.

The original CI run passed all ten jobs and the workflow at 12:54:30 UTC. The
already approved v14 observation started after the final pin/path checks, using
protected `9ded9b9` source; this candidate is not used in that frozen attempt.

### Rebalance the existing hash assignment

CI now explicitly supplies `--partition-seed 1688`. This only distributes tests
between CI jobs; model sampling and NoveltyBench judging settings are unchanged.
The assignment hashes the UTF-8 decimal seed, one NUL byte (0x00), then the UTF-8
test ID. The isolated method stays in group 0. Every occurrence, including
duplicate names, remains present, with original order retained within each group.

Omitting the option retains the original unsalted assignment and original
inventory/terminal-record shape. Explicit `0` is a seeded assignment. Values must
be integers from 0 through 4,294,967,295. A supplied value appears in the inventory
header and the checked terminal receipt; a receipt for another seed is rejected.
Worker containment, genuine-progress deadlines and all quality checks remain.

The selection examined 4,096 candidate seeds using the completed original
Windows and Linux logs separately. Each non-isolated group reports its 30 slowest cases;
remaining elapsed time is allocated uniformly to the unmeasured occurrences for
this estimate. The ranking balances each OS's avoidable longest-group cost
relative to its fixed-weight model floor. It does not optimize benchmark scores.

| Historical model | Recorded longest group | Seed 1688 estimate |
| --- | ---: | ---: |
| Windows | 13,425.957 s (3h44) | 11,097.938 s (3h05) |
| Linux | 4,197.521 s (70 min) | 3,586.268 s (60 min) |

The projections cover the original 2,264 occurrences. Eight added tests are
unpriced and excluded from that model. The actual current inventory retains all
2,272 occurrences in groups `[1, 579, 546, 601, 545]`; complete hosted execution
and timing remain pending. Conservative residual-cost model bounds still permit
a slower Windows result. Host variation, source changes, fixture duplication and
cache effects require actual measurement before claiming a saving.

This targets waiting for the longest job. It removes no test work and does not
promise fewer total billed Actions minutes. Under the historical fixed weights,
even perfect distribution has a Windows floor near three hours. Reducing
repeated verification remains separate work.

All 26 runner/watchdog methods pass, including wrong-seed receipt rejection and
actual five-group execution of a tiny supplied suite. Nine leaf-document guard
methods also pass; all existing test bodies remain. The
[delivery record](conformance/ci-partition-seed-delivery.json) retains the complete
timing model, current inventory, checks and limitations.

This optional developer command prints the seeded assignment once in the current
PowerShell window. It imports test modules and creates ordinary temporary runner
files, but runs no test bodies and spends no model budget. No keys, Docker or
separate window are needed. Ctrl+C stops it.

```powershell
python -m ci_test_shard --count 5 --index 0 --partition-seed 1688 --list-only --isolate test_improver_study.FiniteImproverStudyTests.test_finite_fixed_operators_common_conditions_negative_slots_and_original_recovery
```

This change is stacked on the lexical-path candidate. The frozen v14 observation
continues on its separately protected source and does not use this CI change.
