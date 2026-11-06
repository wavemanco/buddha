# Preparing the forward-runner capacity check

**November 5 current preparation:** propose one fresh attempt on the current
post-audit source: **6 hours for setup/writing/reader admission, 30 minutes
reserved for the reader and 10 minutes for reporting: 6h40 total**. The earlier
4h40 attempt remains an interrupted partial with unknown stop cause; its allowance
is consumed. This proposal uses its later-round timings, not the short-prefix
extrapolation that supported the old limit. Neither this run nor full qualification
is authorised. [PLAN D6](PLAN.md#current-gates-to-the-completed-comparison) owns the
next decision; [the old result](FORWARD-CAPACITY-RESULTS.md) remains unchanged.

This is preparation, not permission to run. The earlier eight-case regression
passed, but it used a much smaller workload. This case reuses the existing
scale fixture and the corrected ordinary study runner. It adds no production
runner, model call, benchmark change or workflow platform.

[PLAN.md](PLAN.md) is the living roadmap. The exact proposed values are in
[the protocol](conformance/forward-capacity-protocol.json); the executable
recipe is [forward-capacity.py](conformance/forward-capacity.py).

## What the proposed case does

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

## Proposed limits and their meaning

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

These are proposed operating limits, not a completion forecast. The earlier
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

The proposal is to adopt a readiness case for the **new v5 comparison**: a
complete 296-owner/1,656-operation study and a fresh complete-report inspection.
It covers more declared work but is a different version and terminal state.
Adopting it requires an explicit decision; a new result cannot retrospectively
pass the old v4 gate. Until that decision and actual passing evidence exist,
capacity readiness remains open. Full-suite qualification is separate.

## Commands for the reviewed handoff

The final source binding and exact paths/hashes are prepared after the candidate
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
PowerShell window with the fixed base interpreter. The approved handoff will
include the small invocation receipt that records start/end, raw exit code and
whole-command elapsed time around the unchanged recipe, including its final
log hashing and result saving. No keys are needed. Ctrl+C stops the attempt and retains a partial result.
Rerunning requires a fresh approval and a new output folder; it does not resume
an earlier attempt.

Freeze all necessary fixture changes before requesting the existing
[exact-source full qualification](CI-TESTS.md#full-qualification). Its approval
does not transfer to changed code. Neither the capacity recipe nor full
qualification starts automatically from this preparation.

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

## Proposed execution sequence and full qualification

Freeze this candidate after the fixture/recipe checks and independent review.
Seek both execution decisions together. The proposed order is the single local
capacity attempt first; only if its adopted acceptance passes with unchanged
source, start the separately approved exact-source full qualification. A stop
consumes that capacity attempt and does not trigger a retry or the conditional
qualification. No label is applied during preparation.

Current local discovery lists **2,232 methods**. The proposed qualification
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
run requiring explicit approval, regardless of billing treatment.

The earlier [preparation receipt](conformance/forward-capacity-preparation-delivery.json)
retains its original source and inventories. The [timing receipt](conformance/forward-timing-observation.json)
records the new observations and revised proposal separately. Neither executes
or passes the full-size case.
