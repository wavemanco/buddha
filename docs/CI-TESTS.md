# CI test progress and the 60-minute stop rule

CI checks the complete discovered unittest suite on Windows and Linux. Each OS
uses five separate test processes. Every discovered test occurrence belongs to
exactly one process on that OS; duplicate test names are retained. Each process
keeps its selected tests in their original order. Class and module fixtures run
separately in each process that needs them.

The largest finite-study test has its own process. The other tests are assigned
by a stable hash of their names. Each process prints the full assignment list,
its selected count and a shared inventory fingerprint, so missing or duplicate
assignments can be checked. Discovery errors, empty groups and an ambiguous
isolated name stop the check instead of silently reducing coverage.

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
