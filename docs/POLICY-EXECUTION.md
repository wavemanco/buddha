# Run a frozen policy comparison

`buddha.policy_run` connects the [frozen study](POLICY-STUDY.md) to the
existing [native baseline](NATIVE-BASELINE.md) and
[fresh judging route](NATIVE-EVALUATION.md). [PLAN.md](PLAN.md) owns current
status. This is an execution interface, not a completed scientific comparison.

## What happens during a study

The study declares four conditions: empty or child instructions, each with
independent or history-aware sampling. It also declares the selected development
tasks, generation repetitions, judging occasions and execution order.

For each scheduled condition and generation repetition, the controller:

1. Generates one complete ordered answer set for each selected task.
2. Runs the selected official grouping, quality and summary commands.
3. Judges those same saved answers on every remaining declared occasion, using
   new owners and request identities. Each occasion runs its own quality scoring
   after its own grouping.
4. Saves every occasion and proceeds to the next scheduled condition.

For example, two selected tasks, two generation repetitions and two judging
occasions across all four conditions produce 16 ten-answer sets: 160 answers
in total. Each set is assessed twice, giving 32 task assessments. The saved
schedule has eight cells, each covering both tasks, and 16 judging occasions.
Those counts describe different units; 160 answers are not 160 independent
experiments.

Generating again measures variation between answer sets. Judging again measures
variation in assessing the same answers. Neither is interchangeable with
recovering an interrupted request: recovery keeps received replies and original
owners, and does not create a fresh assessment.

The controller preserves native results, including their original ordering and
summary bytes. It does not choose the most favorable grouping, compute a
replacement score, rank conditions or claim an improvement. A fresh occasion
does not change the configured display seed. Its identity establishes a new
operation, not statistical independence or a different underlying model.

## What must be frozen first

The execution descriptor, format `buddha.policy-execution.v1`, contains:

| Field | Purpose |
| --- | --- |
| `study` | Absolute `path` and literal file `sha256` of the PolicyStudy artifact. |
| `baseline` | Absolute `path` and literal file `sha256` of an existing baseline descriptor. Its selected tasks and generation configuration must match the study's first scheduled condition. |
| `authorization` | Existing shared authorization's absolute `path`, `id`, `terms_sha256` and exact `scope`. |

The authorization scope is `policy study: ` followed by the study's fingerprint.
The controller checks that scope and the existing terms; it does not allocate
money. The historical $50 experiment and $15 judge audit are closed and do not
fund this comparison.

The user has confirmed standard/default processing and public pay-as-you-go
pricing for both OpenAI and Anthropic. These are recorded account assertions,
not proof of model access or a credential's reviewed project. The protected local
handoff must still check those joins and current profile bounds. The separate
[cost proposal](POLICY-COMPARISON-COSTS.md) remains unallocated.

The baseline template supplies the selected release, generator, evaluator,
profiles, model access, command sequence, seeds, runtime limits and local
spending ceilings. Only the declared instruction/sampling factors and derived
output paths change between conditions. Raw file hashes and canonical study
identities have separate roles: even a whitespace-only edit to a frozen file
invalidates its original raw binding.

Each owner binds the original study, execution descriptor, template, selected
task artifact, generation recipe and complete controller source set. Later
owners inherit the original hashes. Changes during preparation must be detected
before execution; freshly hashing changed files is not permission to adopt them.

The complete study artifact contains the source population for the trusted
host. The existing isolated generation boundary supplies only the current
authorized task to the agent. It does not pass the full split or held-out tasks
to the generator.

## Library interface

| Function | Purpose |
| --- | --- |
| `prepare_study(directory, descriptor=..., authorization=..., review=...)` | Validate the frozen comparison and existing funding, create a fresh directory and bind its first generation owner. Reads no API keys and makes no provider calls. |
| `run_study(directory, transport=...)` | Run or recover the declared schedule through its original children. Unfinished paid work still needs active authority, reviewed profiles, a paid transport and locally supplied keys. |

`prepare_study` accepts optional `input_bindings`: a bounded mapping from `Path`
objects to previously reviewed SHA256 values for external publication files.
These files must be outside the study output directory. The first generation
owner binds them alongside the study's captured configuration and source hashes.
On recovery, the controller inherits their original paths and values from that
first owner; callers do not resupply them. Every later generation and judging
owner retains them. Changed or missing files stop execution rather than being
accepted with fresh hashes. These host checks do not add publication text or
private panel coordinates to model requests.

The values must come from a trusted earlier check. Matching caller-supplied
hashes alone do not establish that a scientific registration preceded the run.
A change detected before owner publication creates no new owner; a later change
may leave partial files pinned to the original values, which fail the existing
execution-identity check. Retain those files as evidence. This interface is not
the passive configuration/readiness checker or the live operator launcher.

These are library functions. There is no new operator command or live handoff
in this execution slice. The separate [actual protocol](POLICY-COMPARISON.md)
and [intent](conformance/pol02-study-intent.json) now declare membership, the
exact child, instrument, supplemental review and analysis. Their future
launcher must verify the reviewed publication against the controller-bound
inputs; direct controller calls do not automatically bind external analysis
documents. The separate [passive reader](POLICY-RESULTS.md) now checks saved
evidence and primary arithmetic, and adds ranges by original category, generation
repetitions, score/group disagreement between judging occasions, and
token/cost/recovery views.
It keeps missing usage and uncertain liabilities explicit; a saved attempt is
not automatically a confirmed wire call, and observed retries/fallback models
do not prove parser repair or its cause. The
[panel mapping and packet materializer](POLICY-PANEL.md) now pass their offline
checks. Before actual execution, complete account/runtime checks, approved
funding and a tested live handoff. Materialize
the actual answer packet and obtain supplemental reviews only after real
generation saves the original answers. Reporting features do not complete the
experiment or the later human scientific assessment.

## Saved records and recovery

| Location under the study directory | Meaning |
| --- | --- |
| `context.json` | Original pointer to the execution descriptor. |
| `cells/<number>/generation.json` and `baseline.json` | Derived recipe and baseline descriptor for that scheduled condition/repetition. |
| `cells/<number>/baseline` | Original generation and first full native assessment, including its owners, attempts, receipts and completion seals. |
| `cells/<number>/judgments/<occasion>` | Fresh full assessment of that cell's original answers; occasions after zero have new native owners. |
| `observations/<number>.json` | Retained incomplete-result explanation, including the stopped cell, occasion, reason and actual returned child report when available. |
| `report.json` | Complete study publication referencing every cell, original generation, occasion, child report digest and native summary. |

An incomplete result preserves its reason, completed cell prefix and stopped
child directory. The reason distinguishes unknown liability, insufficient
authority, protocol failure, cancellation and worker failure. The child keeps
its detailed stage history and any already completed occasions. If a child did
not return a report, the controller records that absence rather than inventing
one. During child execution, Ctrl+C saves a cancellation observation and
propagates the interruption. Interruption during preparation or final publication
may leave retained state without a new observation. Arbitrary disk failure or a
hard process kill may also prevent that write.

A worker can report an `authority` stop when the shared spending guard blocks
a retry of an old unknown request. When the exact stopped owner's validated
records still contain that unknown operation, the study explains the retained
liability with top-level reason `unknown`. Its literal child report keeps
`authority`: the worker records which guard stopped it, while the study
identifies the unknown request still recorded for that owner.

Recovery uses the same study directory and original owners. Received replies
are reused without another send. Unknown requests keep their holds and stop
further spending; this controller does not release money or create replacements.
Changed completed evidence, missing known owners and foreign/out-of-order paths
are errors, not permission to restart. Prior observations remain saved.

Recovery also rejects retained work in a later condition or occasion while a
scheduled predecessor is unfinished. Merely preparing a future owner without
operations is not fresh work. This check validates the retained completion
prefix; it does not authenticate the historical order of externally completed
children. The controller and local filesystem remain trusted host components.

A completed replay validates the retained children and returns the original
complete report without new workers, requests or accounting writes. Its original
authorization snapshot can remain valid after other owners legitimately append
to the shared grant. A snapshot is a consistency record, not authenticated proof
of its capture time.

Only one process runs a study at a time. Normal exceptions and Ctrl+C release
the foreground lock. A hard kill may leave a lock; elapsed time alone does not
establish that another writer is dead. The [doctor's limits](DOCTOR.md) apply.

## Offline check

The [engineering delivery](conformance/pol02-policy-execution-delivery.json)
records 1,173 passing tests and a complete four-condition, two-generation,
two-judgment fixture with two tasks and ten answers per task. It used 64 actual
containers and 256 synthetic HTTP replies; all 56 study owners finished
inactive with no holds. Completed keyless replay added no workers, sends,
accounting writes or persistent report/control changes. Transient writer locks
are still created and removed. These are execution checks using fixed fake
replies, not new model measurements or an improvement result.

Native execution also depends on Docker being able to read each mounted host
directory. During verification, one fresh judging input mount returned filesystem
I/O errors before readiness or any judge request. The same bytes were readable
through a parent mount, and preparation passed at a separate tested run location.
Those observations do not establish the Docker fault's cause or repair the
original run. The failed attempts and their incomplete observations remain saved.

A completed test suite alone does not establish this runtime capability. Moving
an existing study changes its frozen absolute paths; use a separately declared
run for another location, and retain the original records. Recovery in the
original location needs its original inputs to become readable again.

From the repository folder, in the existing PowerShell window:

```powershell
python -W error::ResourceWarning -m unittest discover -s tests -p test_policy_run.py
```

This runs the controller's checks once with synthetic tasks, accounting,
workers and HTTPS replies. It needs no API keys and spends no money. It writes
temporary test files that are cleaned up afterwards. Wait for `OK` or a failure;
Ctrl+C stops it. These mocked-worker checks do not by themselves prove real
container confinement, fresh model judgments or scientific improvement.
