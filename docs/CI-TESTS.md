# CI test progress and the 60-minute stop rule

CI checks the complete discovered unittest suite on Windows and Linux. Each OS
uses four separate test processes. Every discovered test occurrence belongs to
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

The workflow supplies four groups, the exact isolated test name and the same
3,600-second limit. All existing lint, formatting, type, security, dependency
and compilation checks remain required by the workflow. Local helper checks
and an inventory are not a passing full hosted matrix. Current delivery and
remaining verification are recorded in [PLAN.md](PLAN.md).
