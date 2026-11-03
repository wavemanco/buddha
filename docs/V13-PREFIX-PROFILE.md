# One bounded reconstruction diagnostic

This is the next diagnostic for IMP-01 after the
[three-hour construction partial](conformance/history-read-3h-observation.json).
It uses the already retained synthetic prefix. It does not construct more history,
resume the study, advance an action or run a worker.

The question is which public functions consume time during one reconstruction.
Reuse the existing guarded prefix-profiler: call `_restore`, `_check_current`
and `reader.finish` once, with the same observation policy. Export only profiling
rows and callers belonging to the pinned public Python source inventory.

## Fixed scope

- One metadata-only binding of the exact retained v13 root, with one directory
  enumeration capped at 32 direct entries. Check only the three literal child
  names established by the fixture; refuse ambiguity or aliases.
- One profile attempt, with a 300-second cooperative timer and a 330-second
  external child deadline. Imports, preflight, final hashing and output all remain
  inside the external limit. No retry, resume or extension.
- Read only the selected new synthetic study/authority and its referenced inputs
  through the existing reader. The original paid run is not an input.
- Reject network/process operations, filesystem mutations and on-disk SQLite
  connections. Permit only literal in-memory SQLite and four fixed new child
  outputs. Retain parent logs and either complete or partial results.
- Compare raw study files and authority bytes before and after, and recheck the
  public source inventory. The old manifest and build evidence remain unchanged.

The metadata binding completed in 0.105 seconds: one direct entry, one candidate,
no retained-body reads and no SQL connections. Its retained record is
`runs/checks/v13-prefix-profile-20261103-v1/v13-prefix-metadata-binding-v1.json`,
SHA256 `0a7afcd63fe13f3df5f67d1666720d766d65a14ada45a1b28ac791c68e361e47`.
This establishes a fixed path for the diagnostic; it is not a ledger census.

The profile is not yet executed. Source and output pins must be reviewed before
launch. The cooperative timer attempts to interrupt and save partial statistics;
a delayed C call or slow finalization can cause the external parent to stop the
child before those statistics are saved. A partial profile is not guaranteed.

## Meaning of the result

This is a diagnostic of a retained prefix of unverified terminal size. It is not
the required 193-owner/660-operation case and does not run or replace that case's
900-second acceptance test. Instrumented timings cannot establish a speedup or
predict future study throughput. Cumulative profile times overlap.

Use the result to prepare one concrete execution strategy at the measured
bottleneck. It does not automatically adopt another optimization chain, larger
build, new platform or paid handoff. [PLAN.md](PLAN.md) owns those decisions.

No operator command, API key or additional PowerShell window is needed: the agent
runs this offline diagnostic once. Its external parent enforces the stop limit.
The generated profiler scripts and all outputs stay in the named check folder.
