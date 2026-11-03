# Fresh comparison: installed runtime check

The two pinned local images passed their installed-file audits on November 2,
2026. Docker reported version 29.5.3 with a Linux/amd64 engine. Both image IDs,
configurations and non-root users matched the fresh preparation's runtime
metadata. Nothing was downloaded, installed, pulled or rebuilt.

| Image | What was checked |
| --- | --- |
| Source agent | The existing standard-library audit matched its stored manifest and the preparation's expected manifest hash: 1,120 base-Python entries and 16 virtual-environment entries. |
| Native evaluator | The existing installed helper checked 57 distributions and 24,033 installation-record file entries. All 24,043 virtual-environment inventory entries matched the stored, hash-bound manifest; no unowned site-package files were found. |

These were actual audit-container executions. Both returned one result frame,
exited successfully and reported removal. A separate read-only query confirmed
that both audit container IDs were absent afterward. The source audit's
temporary runner was removed; the native audit's small public runner is retained
with the evidence. The native runner copy matches the recorded worker bytes.

The source audit reused `src01-runtime-probe.fresh_audit` unchanged, including
its 15-second/128-MiB worker limit. The native audit used a 60-second/512-MiB
limit and the inventory comparison already used by `NativeWorker._environment`.
It compared installed files rather than requiring historical kernel metadata
to match. Both used the existing executor: network disabled, read-only root,
non-root user, dropped capabilities, bounded resources and a runner-only mount.
No task data, selected improver programs, model keys or model-access callback was
supplied. No experiment accounting owners or grants were created.

The two audits took 20.222 seconds including controller overhead. The existing
executor owned the worker watchdogs and cleanup; the observer imposed no outer
hard-kill deadline. All 360 tracked public Python files, both runtime records
and the recorded diagnostic source files retained their fingerprints.

The extra cleanup check initially stopped before querying containers because
the ordinary shell and keyless audit selected different endpoint fingerprints.
A read-only engine-ID check confirmed they are aliases of the same daemon.
The successful cleanup query used the original audit endpoint. No Docker
context was changed, and distinct endpoint fingerprints must still remain
distinct in bound configurations. The stopped check remains recorded.

## What this establishes

This is a point-in-time check of the installed images and their audit-container
settings. It does not run a benchmark task, P/C generation, a proposal or the
installed judge SDK. It does not measure the eventual workload's memory,
startup time or full-panel capacity. The earlier adversarial confinement
evidence remains separate; this check does not rerun that entire suite.

Matching installed files is not a new dependency-vulnerability or license
clearance. The existing native-runtime notices and archived dependency findings
remain applicable. No image was published by this check.

No operator command or model API key is needed for this completed check.
Further work remains in [PLAN.md](PLAN.md): performance and platform gates,
prospective adoption/separation, actual request behavior, workload capacity,
accounts/prices and a separately funded handoff. No paid-run command is cleared.
[Exact evidence and limits](conformance/fresh-runtime-readiness-delivery.json).
