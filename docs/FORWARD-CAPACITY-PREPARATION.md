# Preparing the forward-runner capacity check

**November 6 approval:** the user approved one offline attempt at frozen source
`8e2fdc50d3a2761ed329b81d74707817342ded75`: **6 hours for setup/writing/reader
admission, 30 minutes reserved for the reader and 10 minutes for reporting:
6h40 total**, retaining the 4 GiB measured child threshold. Only if capacity
passes with unchanged source, one full Linux/Windows qualification is also
approved. Neither has started at this handoff. There is no retry, resume,
extension, model/API call, key entry, real container, funding change or main merge.
The earlier 4h40 attempt remains its own consumed partial with unknown stop cause.
[PLAN D6/D7](PLAN.md#current-gates-to-the-completed-comparison) owns the route.

This approval applies only to the frozen source and exact command below.
The earlier eight-case regression passed, but it used a much smaller workload.
This case reuses the existing
scale fixture and the corrected ordinary study runner. It adds no production
runner, model call, benchmark change or workflow platform.

[PLAN.md](PLAN.md) is the living roadmap. The exact adopted values are in
[the protocol](conformance/forward-capacity-protocol.json); the executable
recipe is [forward-capacity.py](conformance/forward-capacity.py).

## Approved standalone PowerShell command

Open a **new standalone PowerShell window** and run this once. No `cd`, API keys
or administrator rights are needed. Keep the window open until it returns.

```powershell
& 'C:\Users\arvik\code\buddha\runs\checks\full-workload-preparation-20261105-v1\launch-command.ps1'
```

Starts the approved offline check using the fixed base Python and frozen
checkout. It records when the command starts and ends, its exit code and elapsed
time, and refuses an existing attempt/start marker. It uses simulated replies
and records; it spends no API money. It can occupy this window for up to the
6h40 acceptance allowance; late cleanup/reporting remains visible and cannot
pass. Ctrl+C cancels the attempt; do not rerun it automatically.

The terminal may stay quiet between phase messages. Detailed action entries go
to `attempt-1/build-stdout.log`; a quiet terminal alone does not establish a stall.
After the build phase starts, this optional command in a **second PowerShell
window** shows its last eight entries and follows new ones:

```powershell
Get-Content -LiteralPath 'C:\Users\arvik\code\buddha\runs\checks\full-workload-preparation-20261105-v1\attempt-1\build-stdout.log' -Tail 8 -Wait
```

This only reads the progress log and keeps watching it. It spends nothing and
changes nothing. Ctrl+C stops this log view; it does not stop the main check.

When the main command returns, paste its final terminal output here. Codex will
verify the saved writer/reader results and independent invocation receipt.
Only a complete, timely, source-matching pass can trigger the approved full
qualification. That qualification runs all discovered tests on each OS across
ten GitHub jobs, with the existing 60-minute stop without genuine test progress
and six-hour maximum per job. No extra PowerShell command is needed for it.

Approval and the fresh read-only check are retained in
`runs/checks/full-workload-preparation-20261105-v1/approval.json` and
`approved-preflight.json`. They supersede only the old preparation's unapproved
status; the frozen protocol/source/readiness bytes remain unchanged. The binding
SHA256 is `52c87486c525c7373f4d98839c35cdd1b3ee42e738581a7bb741b975c2ab39da`;
the command-file SHA256 is
`c61aba355f7f56c9730baa28c7d2eedd6c24e166f071bd7e8e0539833f82fc3f`.
No workload has been launched from Codex. The remaining sections explain the
unchanged workload, adopted limits and maintainer syntax; their generic examples
are not replacement launch commands for this handoff.

## What the approved case does

It creates new, retained synthetic records using two starting bundles, two
repetitions, two fixed improver arms and two opportunities per arm. Each
screen covers three tasks and ten answers per task. Supplied workers and
supplied HTTP replies replace real execution and provider calls.

Every synthetic child is deliberately admissible. That makes the case exercise
the full declared work instead of finishing cheaply through early failures.
These scores are fixture values, not evidence of creativity or improvement.

| Required work | Derived total |
| --- | ---: |
| Common starting conditions | 4 |
| Counted opportunities / admitted children | 16 |
| Screens / task assessments | 20 / 60 |
| Scored answers | 600 |
| Mutation witnesses | 20 |
| Passing proposal-capacity checkpoints | 36 |
| Original study owners | 296 |
| Supplied request operations | 1,656 |
| Declared maximum calls | 2,652 |

The source contains 1,000 synthetic rows. Existing sizing targets remain:
645,466 dataset bytes, 1,113,890 task-source bytes, 24,043 native inventory
entries, a 4,013,984-byte environment floor and a 5,315,388-byte screen floor.
No sealed final prompts, private agent bodies or original paid databases are
needed for this case. There is no whole-final-panel rehearsal.

Each answer is fixed at **8,192 UTF-8 bytes**, preserving its original text as
an exact prefix. The 600 scored answers contain 4,915,200 raw text bytes;
witnesses generate another 200 answers / 1,638,400 bytes. Comparison feedback
retains both actual layers where required. This is a declared engineering
payload envelope, not a maximum for all possible real-model responses. A pass
would not establish capacity for arbitrary larger outputs.

The runner must preserve full literal feedback and private-copy lineage, finish
all scheduled work, reconcile original-owner accounting, and leave no active
owner or unresolved hold. Its normal cold checks before freeze and publication
remain enabled. Only after complete writer evidence passes does a new process
inspect the saved complete report. The inspection must reproduce the report
and leave the retained study and authorization bytes unchanged. Consumed
control bindings are also checked; this is not a byte audit of every unused
file in the synthetic image.

## Adopted limits and their meaning

- **One attempt, 6 hours 40 minutes total**: six hours for setup, the writer
  and checks before admitting the reader; a fully reserved 30-minute reader;
  and ten minutes reserved for final checks and reporting. The reader starts
  only while its full allowance and the reporting reserve remain. A late
  writer stops partial rather than shrinking the reader's window. Progress
  clocks are per phase; the total deadline never restarts. There is no
  automatic retry, resume or extension.
  The operator must also measure the complete command, including final log
  hashing and report saving. A pass requires that duration to be at most six
  hours and forty minutes. The driver's own complete status is insufficient:
  its final recording follows its last deadline check. Recording or cleanup may finish late; retain
  that time and record a partial in the separate acceptance receipt. This is
  not a guarantee that all reporting processes are forcibly killed at the limit.
- **4 GiB OS-reported peak working set for each child**, measured on Windows
  through final validation, just before terminal-report writing. Later
  report-writing allocations are outside that sample. This is an acceptance
  threshold, not an OS-enforced allocation ceiling.
  Missing terminal memory evidence cannot pass. A last progress observation
  after interruption is only the available observation, not the final peak.
- Keep the existing bounded evidence policy. Its zero-resident setting forbids
  raw-file caching; it does not impose a process-memory limit.

Generation uses twelve supplied calls per answer set. The bounded actual-P/C
request diagnostic observed ten and eleven calls; the legacy scale fixture
used four. This declared population covers those observed counts with
headroom, not every permitted future call pattern, the full call ceiling or
real provider request-body sizes and latency.

These are adopted operating limits, not a completion forecast. The earlier
attempt's last planning entry was at **10,372.213 seconds**, with ten saved
admitted children and six children still unobserved. Its later two-child interval
was **2,406.181 seconds**. A simple continuation scenario is:

`10,372.2127083 + 6 * (2,406.1809058 / 2) = 17,590.7554257 seconds`

That is about **4h53m11s**.

That scenario excludes terminal writer work and assumes the remaining children
cost the same as that observed pair. It already exceeds the old four-hour writer
limit. A five-hour writer would leave only about seven minutes for final work.
Six hours leaves **66m49s** above the scenario for larger history, final validation
and uncertainty. That is an explicit planning margin, not an empirical upper
bound or a guarantee. A timeout remains possible and must be reported honestly;
there is no automatic extension.

Keep the reader's 30 minutes, reporting's 10 minutes and measured 4 GiB threshold
unchanged. No completed full-study observation supports adjusting those values.
The earlier 19.870-second prefix read, roughly 1.01 GiB prefix peak and separate
27.64-second cold witness do not predict complete-study reader time, memory or
speed. The original attempt did not establish a timeout or a stop cause.

Timeouts, errors, changed source, missing evidence and memory-limit misses
remain explicit incomplete or failed acceptance results. Logs, last stage,
timings, available memory evidence, source pins and the synthetic fixture are
retained. Nothing in this recipe clears paid execution.

## How this relates to the older gate

The old **v4 prefix with 193 owners and 660 operations**, and its fresh
15-minute reader, remain unpassed. Its construction partials are retained.

The adopted readiness case for the **new v5 comparison** is a
complete 296-owner/1,656-operation study and a fresh complete-report inspection.
It covers more declared work but is a different version and terminal state.
The user has adopted this case, but it cannot retrospectively pass the old v4
gate. Capacity readiness remains open until actual passing evidence exists.
Full-suite qualification is separate and conditional on that pass.

## Maintainer syntax for future preparations

For future preparations, the source binding and exact paths/hashes are prepared after the candidate
is frozen. The final handoff requires its short checks and independent review to pass. The examples below are maintainer syntax;
angle-bracket values must be replaced by that reviewed handoff. Use the
reviewed candidate checkout named in the binding; the preserved primary
checkout may contain older code. No command is
needed from the project owner during preparation; the examples are not a live
launch instruction.

```powershell
& <absolute-base-python.exe> docs/conformance/forward-capacity.py --binding <binding.json> --sha256 <binding-sha256> --out <new-output-folder> --check
```

Checks the selected source, protocol and unused output path once. It reads and
hashes files and uses local read-only Git commands. It creates no output,
imports no workload fixtures and starts no workload process. It spends no API
money, needs no keys and requires no separate PowerShell window.

```powershell
& <absolute-base-python.exe> docs/conformance/forward-capacity.py --binding <binding.json> --sha256 <binding-sha256> --out <new-output-folder> --execute
```

Only after explicit adoption and execution approval, runs the one bounded
offline attempt and retains its files and logs in the new folder. It uses no
keys or API money. It occupies that terminal until completion. Use a user-started standalone
PowerShell window with the fixed base interpreter. The current handoff includes
the small invocation receipt that records start/end, raw exit code and
whole-command elapsed time around the unchanged recipe, including its final
log hashing and result saving. No keys are needed. Ctrl+C stops the attempt and retains a partial result.
Rerunning requires a fresh approval and a new output folder; it does not resume
an earlier attempt.

The current approval covers frozen source `8e2fdc50`; it does not transfer to
changed code. The [full qualification](CI-TESTS.md#full-qualification) can start
only after the approved capacity case passes. Neither starts from reading this
document or running a maintainer check.

## Why this uses the existing components

The recipe reuses the fixture, ordinary writer, original inspector and bounded
subprocess/Windows-memory measurement patterns. Python
[`subprocess.run`](https://docs.python.org/3.13/library/subprocess.html#subprocess.run)
already supplies timed child execution. [Pyperf](https://pyperf.readthedocs.io/en/stable/runner.html)
is useful for repeated benchmark measurements, but would still require the
domain accounting/custody checks and conditional reader; its Windows memory
measurement also differs from this working-set criterion.
The [real Inspect/owned-process proof](INSPECT-OBSERVABILITY-PROOF.md) is retained
as component evidence. This capacity recipe does not emit Inspect action traces
or inherit that proof's Job/descendant or observer-exit guarantees. Its existing
parent times and joins each direct phase process; after startup, phase guards
refuse subprocess/network work. Loss of the standalone owner can still leave a
partial without terminal evidence. Restart survival stays deferred. Adding an
SDK/supervisor here would create another path to qualify; it is not a D6 acceptance
requirement. Any later Inspect enrollment belongs inside the process doing the
study, with its own checks; no paid-path enrollment is cleared here. No new
dependency or production scheduling layer is added for this one observation.

## Approved execution sequence and full qualification

Both execution decisions are now approved for source `8e2fdc50`. The order is
the single local capacity attempt first; only if its adopted acceptance passes
with unchanged source, start the conditional exact-source full qualification. A stop
consumes that capacity attempt and does not trigger a retry or the conditional
qualification. No label is applied during preparation.

Current local discovery lists **2,232 methods**. The approved qualification
covers the complete inventory on each OS across five existing jobs (ten total). The explicit
capacity workload is not a discovered unit test, so qualification does not
silently repeat it. Short CI selects 476 contracts per OS, including the small
preparation guards. An inventory is a count, not an executed test result.

The existing full workflow stops its test worker after 60 minutes without
genuine test progress; [GitHub-hosted jobs](https://docs.github.com/en/actions/reference/limits) also
have a six-hour maximum. There
is no automatic retry. The previous complete qualification at source 6e took
about 34 to 53 minutes per Linux job and 2h16m to 2h52m per Windows job. Those are
retained earlier-source job durations, not a forecast for this candidate.
Full qualification uses GitHub Actions and no model API keys or charges; the
repository was public when this preparation was checked. It is still a long
run; this user approval allows one conditional attempt, regardless of billing treatment.

The earlier [preparation receipt](conformance/forward-capacity-preparation-delivery.json)
retains its original source and inventories. The [timing receipt](conformance/forward-timing-observation.json)
records the new observations and revised proposal separately. Neither executes
or passes the full-size case.
