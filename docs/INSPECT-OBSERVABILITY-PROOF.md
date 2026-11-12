# Inspect observability compatibility proof

## Current integration status

The pinned Inspect 0.3.287 integration passed the November 5 offline
tracing, error and viewer endpoint check. The optional launcher entry applies to
fresh read-only checks. It replaces the terminal heartbeat for that check.
The saved comparison and paid runs use Buddha's existing launcher and accounting.

On November 12, the same installed release reused a completed sample in a
two-sample, no-model task. The first evaluation called both solvers and stopped
on the second sample. Inspect's retry called only that unfinished sample and
kept the completed sample's original result. The original log hash stayed the
same and both model-usage totals were empty. The successful process took
4.932 seconds. Three setup attempts stopped before either sample ran. The
successful proof blocked external networking and retained only the private
loopback sockets Python needs for its event loop on Windows. This establishes
sample reuse for a loadable Inspect task. The existing Buddha observer creates
its task in memory and has no sample retry path.
The local receipt is `runs/checks/d8-inspect-sample-reuse-20261112-v1/result.json`
with SHA-256 `dff6cf21620b92405e1dc72b6f06021753d7db5942e1ba197b0e6ec9cd65379f`.

For a fresh study, the next candidate for replacement is the loop that
schedules final assessment cells and the two plain-model controls. Inspect
would own sample scheduling, completed-sample skipping and progress display.
The scorer would still run the pinned official NoveltyBench requests through
Buddha's Gateway. Before adopting it, interrupt a small paid-blocked grid after
a completed sample and verify that resumption preserves exact scores, artifacts
and ledger totals without sending again for the completed sample. An observer
error after canonical completion must also preserve that completion. The
current one-operation observer does not exercise this path. [Inspect sample preservation](https://inspect.aisi.org.uk/eval-logs.html#sample-preservation).

The earlier partials retain their original status. [PLAN.md](PLAN.md) is the
scheduling authority.

### Project-only process ownership

The user has excluded Task Scheduler and global Windows logging. No task was
registered and the denied log-setting attempt changed no Windows configuration.
Buddha must observe only its own process IDs/descendants and project-local files.
No command to change Windows logging is needed.

The selected components have separate jobs:

- Inspect records Buddha's stages and errors in a fresh project folder. Its
  [tracing API](https://inspect.aisi.org.uk/tracing.html) supplies the logging
  mechanism; it does not need Windows task-history access.
- A user-started standalone PowerShell process is the preferred run owner and
  supervises only workers it creates. Survival across a Codex restart is deferred.
  The existing Windows-job helper is the candidate for stopping owned descendants;
  actual interpreter ownership must be checked before releasing work.
- Existing containers still isolate candidate code. Moving the entire host
  controller into a service or another workflow platform is not required here.

This scopes Buddha's observation. It does not revoke the Windows account's
existing permissions or change Windows's own logging protocols.

The selected route is Inspect in a user-started standalone PowerShell process.
Inspect supplies stage/action logs and its subprocess result/timeout interface;
Buddha retains its operation identities and budget authority. Inspect0.3.287's
subprocess cleanup stops only its direct process, so descendant cleanup remains
an explicit short-test requirement. Reuse the existing owned Windows-job helper
if needed; do not build another workflow engine or assume chat-independent
lifetime from Start-Process inside a Codex tool.

Process ownership and restart survival are separate checks. Ownership means
confirming that a worker belongs to this run before monitoring or stopping it;
normal failure/timeout handling and owned-descendant cleanup remain required,
including cleanup if the project observer exits. These can use small owned
workers without restarting Codex. Restart survival means the study continues
if the Codex app closes or restarts. The user has deferred that second check;
it must not block the completed comparison. The historical stop cause is still
unestablished. No restart experiment is scheduled, and this clarification
authorises no new execution. No API keys or administrator rights are needed
for the proposed ownership check. No actual paid run, full capacity attempt or
global event-log read is cleared by this route.

### Current ownership proof

The user said to proceed with the ownership check. One independently reviewed
local proof has now completed in39.940338seconds, within its shared five-minute
limit, with no automatic retry. It reused the existing Windows-job helper;
its direct-PID assignment is not
a claim about an interpreter already started by a virtual-environment launcher.

Before third-party imports or work, the actual interpreter must identify itself
through a fresh role/nonce-bound handshake and wait. Retain its Windows process
handle, assign it to the specific owned Job if needed, verify membership and only
then release it. Compare the viewer registry against this interpreter, not its
launcher. Retained handles also let us verify actual worker/descendant exit
without reopening a possibly reused numeric PID. This follows Microsoft's
[specific-job membership API](https://learn.microsoft.com/en-us/windows/win32/api/jobapi/nf-jobapi-isprocessinjob).

Use tiny owned workers for success, nonzero exit, timeout, abrupt termination and
observer-exit cleanup. In the last case only the observer may retain its Job
handle: Windows's [kill-on-last-close behavior](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
must be observed before outer fallback cleanup. Reuse the real Inspect case once
within the same deadline. Keep fixed failure sites, start/end and raw exits,
membership, cleanup and source identities; preserve an explicit partial if a
check fails or reaches the limit. No Codex restart, global activity query, model
call, new production supervisor or paid-path clearance is part of this proof.

The small existing helper is currently used by CI, not every study operator.
Passing this proof establishes the selected ownership boundary; it does not
silently wire it into old paid commands or prove workload capacity.

### Completed ownership and Inspect observation

At source `629a63feee77c04525b388c1cc65b61424f5cfca`, the single cohort passed all
five cases. Actual worker/descendant exits were success0/0, nonzero17/0,
timeout1/1, abrupt worker19/1 and observer23/0. The observer's descendant had
already exited before outer fallback cleanup. All13retained process handles
were signalled and closed, all launchers joined, and cleanup had no errors.
All8actual interpreter IDs differed from their launcher IDs. Their membership
was verified before work; all already inherited the owned Job, so conditional
reassignment was not exercised. No numeric PID was reopened to perform cleanup.

The same cohort used real Inspect once: the existing full-feedback/proposal/
child-screen test passed, both open operation/proposal traces were observed,
and the viewer returned HTTP200. A deliberate error was correctly recorded as
an error, with its private canaries absent and its original exception/cause
preserved for the caller. Model usage was empty (`none/none`); no provider
request or real container was started. Viewer page rendering was not tested.

Independent review checked all case/ownership/cleanup records and decoded every
evaluation-archive entry using the existing pinned compression reader without
importing Inspect or rerunning the cohort. All858source hashes matched. The
original partial remains unchanged. The
[delivery receipt](conformance/inspect-owned-process-delivery.json) binds the
script, preparation, results and independent review by hash. The local raw pack
is `runs/checks/inspect-owned-process-proof-20261105-v1`; it refuses another run
against the existing output folder. No further attempt is authorised here.

## Selected entry and scope

The new optional `buddha.inspect_study.run` calls one trusted offline operation
through an actual Inspect Task/solver. The ordinary source runner now emits
restore, action, refresh, freeze and publication events when this context is
active. The selected context replaces launcher heartbeat polling; it does not
observe a run by repeatedly reconstructing its history.

The first user-facing selection is read-only configuration checking. Maintainer
syntax, after a fresh checked handoff and the exact entry path are supplied:

```powershell
& <pinned-Inspect-python.exe> <candidate-root>/docs/conformance/unified-run.py --handoff <handoff.json> --sha256 <handoff-sha256> --check --inspect-log-dir <new-observation-folder>
```

Runs once, checks the same handoff and creates Inspect records in a new local
observation folder. It spends no API money, asks for no keys and starts no model
or agent container. The folder must be outside original inputs, source folders
and run state. It need not use a separate window for an ordinary check; Ctrl+C
stops it. Do not type the angle-bracket placeholders literally. A standalone
window remains preferred for the eventual study launch; restart testing is deferred.

`--inspect-log-dir` is refused with live execution or original continuation.
The optional Inspect environment and source closure are not cleared for paid
execution. No stock Inspect scorer or provider replaces NoveltyBench/Gateway.
Stage diagnostics are redacted; original exceptions, causes and canonical
results remain authoritative. An Inspect error log must not become a successful
Buddha result. Calls bypassing Inspect's model API do not acquire automatic
model transcripts or usage totals by virtue of this adapter.

Startup uses a fresh empty-dotenv folder, project-owned cache/data/trace paths
and disabled traceback locals before the first Inspect import. A preloaded
Inspect process is refused so cached global file handlers cannot escape the
project scope. The operation keeps its original working directory. Only
framework logging/cache controls are temporarily overridden; API keys are not
read or copied by the observer setup. The proof treats unsupported Unix
CPU-probe files on Windows as absent; selected candidate confinement is unchanged.

This is direct synchronous execution. Inspect's async cancel button is not a
process-tree terminator; the selected external ownership proof above establishes
cleanup only for its declared process shape. Survival across a Codex restart
remains unverified and deferred. The completed cohort used supplied replies and
workers, not a capacity attempt. No full qualification, paid clearance or
speedup follows from this component proof.

### Earlier observation: November 5 (preserved partial)

One check at source `d27bede20d2969a385555b508965bf47eae171ef` stopped after
41.680427 seconds, within its shared 300-second limit. It made no model calls.
Real Inspect reached the existing full-feedback/proposal/child-screen test,
which passed once, and then wrote an open-proposal marker. The parent stopped
at a startup assertion before checking the viewer, releasing the operation or
validating a terminal error log. The result is **partial**, not a timeout or a
successful integration proof. There was no automatic retry.

Independent review confirmed two problems:

1. The viewer recorded a different process ID from its direct launcher. The
   proof's equality assumption cannot pass. Python documents Windows virtual
   environments' [redirector executables](https://docs.python.org/3.13/library/venv.html).
   That is a plausible explanation, but the retained records do not establish
   the actual ancestry or which of two startup assertions fired. A future check
   must establish ownership of the interpreter before allowing it to work.
2. Our logger inherited WARNING while Inspect enabled TRACE only for its own
   logger namespace. The underlying stage ran, but Buddha's trace entries were
   discarded before reaching Inspect. Using Inspect's namespace fixes that
   boundary without changing global verbosity. A real Python logging-hierarchy
   regression failed before the fix and passed afterward.

At that checkpoint, the corrected local suite had 17 methods: 16 passed and one
Windows symlink test was skipped because the account lacked that privilege.
The corrected source had not yet been observed through real Inspect again;
viewer access, open-action trace, terminal redaction and independent lifetime
were unproved. The later completed case above supplies the bounded evidence;
restart survival remains deferred. Exact queries
of only the two actual interpreter IDs retained by this check found both absent;
no unrelated process was queried or stopped. This later absence does not prove
historical job membership or cleanup timing.

[Delivery receipt](conformance/inspect-stage-integration-delivery.json) binds the
preparation, partial result, stage record, trace and separate known-process
postcheck by hash. Raw records stay in the ignored project check folder. Preserve
this attempt; review any corrected short proof before another execution.

### Independent simplification review

The requested Ponytail audit and separate adversarial review confirmed three
findings. The scoped cleanup removes one unused private CLI settings reader,
reuses an existing credential-test fixture, and preserves an already sanitized
failure location after successful worker cleanup. All 25 focused checks pass,
including an independent rerun. Credential protection, cleanup precedence and
the official scientific controls remain. Net production code falls by four lines.

Repeated parent reads before mutation dispatch are also confirmed, but their
cost is unmeasured. That correction remains behind PLAN's bounded profiling
gate. No whole module or dependency was proved safe to delete. The
[audit delivery](conformance/observability-audit-delivery.json) records the
decisions and hashes of the external audit and adversarial reports.

The later final whole-codebase audit remains outstanding in PLAN D5b. Use
Ponytail, independent agents and adversarial validation of proposed removals
after the current corrections, before freezing the next candidate. The earlier
scoped audit is not a claim that all unnecessary code has been removed. The
objective remains the matched NoveltyBench comparison.

## Current disposition: November 4, 2026

PR258 removes our unused observer callback and its prototype tests. No
application caller enabled it, and it implemented no Inspect trace, evaluation
log or viewer. Existing progress messages, accounting, stop diagnostics and saved
evidence remain. The user's cleanup direction targets unnecessary code we wrote;
this retirement does not reject useful third-party observability.

Inspect remains a deferred reuse candidate. Its official [log viewer](https://inspect.aisi.org.uk/log-viewer.html)
can inspect transcripts, scoring and results; its [action traces](https://inspect.aisi.org.uk/tracing.html)
can expose running, failed or unfinished actions. Our isolated proof below did
not reach those features, so compatibility and benefit remain unproven. Any
future adoption should replace a named custom reporting responsibility rather
than add another coordinator. No new proof attempt or dependency is scheduled.

The original isolated environment, receipts and failed proof remain intact.
The following sections describe that historical candidate and its acceptance
criteria; they do not describe an installed application integration.

## Historical candidate and proof

This records the bounded ENG-OBS-01 candidate in [PLAN.md](PLAN.md). Its first
actual proof attempt stopped during Inspect import, before either synthetic
sample ran. Inspect AI 0.3.287 remains unadopted. The existing Gateway, authority
ledger, executor and official NoveltyBench 1.1 evaluation remain authoritative.

The intended replacement is the custom display/polling in `Progress` and the
duplicate launcher heartbeat on an explicitly selected Inspect path. A second
coordinator or another loop reading `progress.snapshot` does not satisfy that
requirement. The existing paths retain their behaviour while this is a candidate.

The intended cohort must show a successful stage, an actual typed failure and a
genuinely open action observed before it finishes. It must retain the deliberate failure,
compare the underlying request-construction result with a direct call, and
show no extra model, ledger or execution effects. Its parent deadline will include
viewer shutdown. That acceptance remains unmeasured; the stopped attempt was not
retried, and further cohorts are parked.

## Actual partial result: November 3, 2026

The isolated development environment was provisioned with all 80 pinned package
versions verified. Buddha's dependency requirements were unchanged. The small
stdlib observer seam passes 26 focused tests, including existing progress and
heartbeat regressions. Those tests did not import Inspect and do not establish
framework compatibility or whole-CLI adoption.
Final configured quality checks and compilation of all 365 public Python files
also pass; the earlier 26-test result was reused without rerunning it.

The one actual attempt returned after 9.202 seconds within its 180-second total
limit. Both owned children exited and were joined; all 365 bound public Python
files remained unchanged. The parent retained an explicit partial result.

Inspect's import-time CPU detector attempted the literal Linux path
`/proc/self/mountinfo`, which maps to `C:\proc\self\mountinfo` on this Windows
drive. The proof's read guard raised `RuntimeError` before the file could open.
Inspect's helper normally catches `OSError` and `ValueError` for absent or
unreadable CPU probes; our different exception prevented that fallback. This
observed failure identifies an overly restrictive proof admission, not an
established Windows incompatibility in Inspect. The host path was not opened to
check whether it exists.

No sample, observer trace action, running viewer, trace query or evaluation log
was reached. Startup-isolation records and both stderr files are retained in the
[delivery record](conformance/inspect-observer-proof-delivery.json). The candidate
seam and isolated package installation do not adopt Inspect as Buddha's runner,
prove a reduction in reconstruction time, release the history gate, or authorize
paid work. No further cohort or retry is scheduled.

## Dependency scope decision: November 2 local / November 3 UTC 2026

The resolved CPython 3.13 Windows closure contains 80 hash-pinned binary packages.
No extra test framework is required. Both resolution passes used binary-only
packages; no source build or downloaded package code ran during preflight.
The exact 80-version advisory check returned zero reported vulnerabilities and
zero skipped packages. This records that dated query, not a general security
certification.

Inspect core is MIT. Its complete dependency closure also includes these notices:

| Distribution | Notice found in the actual wheel | Scope of this decision |
| --- | --- | --- |
| certifi 2026.10.19 | MPL-2.0 | Reuse the existing development-only exception at the same version. |
| botocore 1.43.117 | MPL-2.0 certificate material | Retain its bundled notice in the isolated proof environment. |
| debugpy 1.8.22 | EPL-1.0 PyDev.Debugger component | Retain the incorporated component's notice in the isolated proof environment. |
| NumPy 2.5.4, Windows wheel | GNU runtime component with GCC runtime exception | Retain the actual Windows binary and its component-specific license notices. |

The host engineering policy requires copyleft to be flagged before use. These
flags were raised before installation. The implementation decision is to enable
this exact closure **only in a new isolated development proof environment**,
retaining the supplied notices. This follows the existing isolated-research
[dependency policy](BENCHMARK-REFERENCE-PROFILE.md#reproduction-and-dependency-notices).
It does not add the packages to Buddha's application requirements, vendor or
redistribute their binaries, or clear other platforms, optional extras, provider
execution or a future distributed runtime. Those uses need their own dependency
and license decision. No claim that the entire closure is MIT is made.

The external preflight receipt is
`runs/checks/inspect-ai-dependency-preflight-20261103-v1/dependency-preflight-v1.json`,
SHA256 `05045a63ad9f17d73d6f20dfbba71e84fb00f1b677cadb8fc58b2da7a7ae320e`.
It binds the full license census, wheel hashes, resolution and advisory output.
The two initially incomplete metadata declarations were resolved from actual
wheel license files: agent-client-protocol is Apache-2.0; zipfile-zstd is MIT.

## Isolation required before execution

Use a fresh owned working directory with an empty `.env` and a keyless child
environment. Pin platformdirs 4.14.3 and verify its resolved appdata/cache paths
stay inside that directory before importing Inspect. Its Windows KnownFolder
overrides, explicit log/cache paths and separate per-process trace files keep
Inspect's startup retention and viewer registry away from existing user data.
Changing the trace filename alone is insufficient because rotation happens first.

The viewer must use a fresh owned PID registry and a loopback port. Port zero is
unsupported. A port race must end as a startup failure, without selecting another
port or terminating an unrelated viewer. Stop and join only the owned process.
The proof admits no external network, model requests, real benchmark inputs,
original run records or source-actor execution. Public API compatibility and
actual viewer behaviour remain unmeasured after the import-time stop.
