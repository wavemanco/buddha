# Preparing the forward-runner capacity check

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

- **One attempt, three hours total**, including setup, the complete writer,
  inspection and reporting. The fresh inspection also has a **15-minute limit
  within that total**. Progress clocks are per phase; the total deadline never
  restarts. It receives no extra time if the writer uses most of the
  allowance. There is no automatic retry, resume or extension.
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

These are proposed operational limits, not a forecast that the case will
finish. The total reuses the former three-hour time ceiling but asks for a
complete larger study and its reader inside it; the old attempts allowed three
hours for the producer alone. Earlier two-screen observations peaked around
0.89 GB; they justify reporting a concrete memory ceiling, not predicting this
larger case. The eight-case run's 15-minute duration is not extrapolated.

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

The final binding and exact paths/hashes will be prepared after the candidate
is frozen and its short checks pass. The examples below are maintainer syntax;
angle-bracket values must be replaced by that reviewed handoff. Use the
reviewed candidate checkout named in the binding; the preserved primary
checkout may contain older code. No command is
needed from the project owner during preparation.

```powershell
python docs/conformance/forward-capacity.py --binding <binding.json> --sha256 <binding-sha256> --out <new-output-folder> --check
```

Checks the selected source, protocol and unused output path once. It reads and
hashes files and uses local read-only Git commands. It creates no output,
imports no workload fixtures and starts no workload process. It spends no API
money, needs no keys and requires no separate PowerShell window.

```powershell
python docs/conformance/forward-capacity.py --binding <binding.json> --sha256 <binding-sha256> --out <new-output-folder> --execute
```

Only after explicit adoption and execution approval, runs the one bounded
offline attempt and retains its files and logs in the new folder. It uses no
keys or API money. It occupies that terminal until completion; a separate
window is optional. Ctrl+C stops the attempt and retains a partial result.
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
[Inspect logs](https://inspect.aisi.org.uk/eval-logs.html) remain a possible
inspection aid, without replacing these workload acceptance checks. No new
dependency or production scheduling layer is added for this one observation.

## Proposed execution sequence and full qualification

Freeze this candidate after the fixture/recipe checks and independent review.
Seek both execution decisions together. The proposed order is the single local
capacity attempt first; only if its adopted acceptance passes with unchanged
source, start the separately approved exact-source full qualification. A stop
consumes that capacity attempt and does not trigger a retry or the conditional
qualification. No label is applied during preparation.

The current discovered qualification inventory is **2,214 methods per OS**,
partitioned into five existing jobs per OS (ten jobs total). The explicit
capacity workload is not a discovered unit test, so qualification does not
silently repeat it. Short CI selects 458 contracts per OS, including the small
preparation guards. An inventory is a count, not an executed test result.

The existing full workflow stops its test worker after 60 minutes without
genuine test progress; [GitHub-hosted jobs](https://docs.github.com/en/actions/reference/limits) also
have a six-hour maximum. There
is no automatic retry. The previous complete qualification at source 6e took
about 34–53 minutes per Linux job and 2h16m–2h52m per Windows job. Those are
retained earlier-source job durations, not a forecast for this candidate.
Full qualification uses GitHub Actions and no model API keys or charges; the
repository was public when this preparation was checked. It is still a long
run requiring explicit approval, regardless of billing treatment.

The source-bound [preparation evidence](conformance/forward-capacity-preparation-delivery.json)
records the short checks and discovered inventories. Those checks do not
execute or pass the full-size case.
