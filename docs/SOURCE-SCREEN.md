# Compare source-code candidates on the same development tasks

Buddha can screen a selected Python agent on a fixed, ordered list of development
tasks. Each task gets one saved answer set and one fresh assessment by the selected
official evaluator. A different agent must face the same tasks, instructions,
models, evaluator and resource limits before their results can enter one parent
pool. The agent code itself may differ. Pool checks also compare the originally
recorded host-helper versions, host runtime and external control files. Helper
locations can differ when their logical roles and bytes match; other external
files conservatively require the same original absolute path and bytes.

This is a library interface for the source-evolution controller. It does not add
a command for starting another funded experiment. The separately approved POL-02
handoff keeps using its original frozen checkout.

## What happens in a screen

1. Check the complete dataset, its development/validation/final split, the selected
   development tasks, source code, evaluator, runtime and existing spending grant.
2. Run the selected agent in its confined container for the first task. It receives
   that task and its declared configuration. The host retains the full split;
   validation and final task text do not enter the generation request.
3. Save the literal answers, including duplicates, empty text and poor answers.
   One callback to a model need not correspond to one answer: an agent may batch
   answers or use several calls, within its original callback and spending limits.
4. Give those saved answers to the selected official evaluator stages. For
   NoveltyBench these are partition, quality scoring and summary. The host does
   not regroup answers or recalculate official utility.
5. Repeat for every declared development task, in the original order.
6. Verify all retained evidence and funding records before publishing a complete
   screen. Separately decide whether its metrics are usable for parent selection.

Each generation and evaluator stage has its own original owner and ledger under
one shared grant. An owner records the selected files and settings, requests,
replies and cost. A completed stage has a file seal and a separate completion
record in the grant. Recovery uses those same owners and known replies. An unknown
request keeps its spending reservation and blocks fresh spending; restarting does
not erase it or turn it into a free replacement request.

The host passes the original expected hashes of task and evaluator recipes into
each new owner. It refuses changed controls instead of adopting them on recovery.
Before starting the next stage, it also checks that the child's returned complete
report matches its actual saved canonical report, including literal field types.
Native stages reuse the existing artifact-flow checks and passive custody reader;
this adds no replacement evaluator or metric formula.

## Completion, admission and improvement

These are separate decisions:

| Decision | Meaning |
| --- | --- |
| Complete screen | Every declared task finished generation and all native evaluator stages, with verified saved evidence. |
| Eligible parent | Every task has usable, finite metrics in the parent selector's declared range, from a compatible explicitly selected results projection. |
| Selected parent | The existing archive, latest-only or uninformed rule chooses among eligible sources for exploratory allocation. |
| Confirmed improvement | Requires the later independent evaluation protocol; this screen does not establish it. |

With the optional `noveltybench-1.1` projection, task-level distinctiveness and
utility come from the original saved native rows. Each mean uses the entire fixed
task list. A missing or unusable value prevents admission; the host does not drop
that task to produce a more flattering mean. Counts beyond the current selector's
declared distinctiveness range of 1–10 also remain ineligible, without rescaling.
Utility must lie in 0–10. Invalid values and their diagnostics remain in the task
records, even when they prevent a mean or admission.

A compatible native evaluator can finish without an available optimizer projection.
Its native results remain saved and complete; parent selection records why it
cannot use them. Updating a benchmark does not first require changing the agent
or inventing new metric formulas in the harness.

One assessment per task is a declared exploratory screen. It does not settle judge
variability, meaningful plot variety, literal task compliance, quality of an
improver, or performance on unseen tasks. Repeated evaluation and supplemental
review remain governed by [PLAN.md](PLAN.md) and [DESIGN.md](DESIGN.md).

## Library functions and their effects

| Function | What it does |
| --- | --- |
| `SourceScreen.from_bytes(...)` | Reads and validates an immutable declaration. It does not run code, read source directories or spend money. |
| `prepare_source_screen(...)` | Checks original files, runtime approval and the existing screen-scoped grant; creates a new screen and its first owner. It makes no provider requests. |
| `run_source_screen(...)` | Runs or resumes the original screen once. It can spend from its existing grant when a paid transport is supplied; it never creates a grant. Interrupted work and its reason remain recorded. |
| `inspect_source_screen(...)` | Checks a caller-pinned complete report against retained answers, evaluator outputs, seals and funding records. It makes no calls or workers and can work after the producer programs have been retired. |
| `select_source_parent(...)` | Checks every supplied complete screen and chooses an exploratory parent using the existing selection rule. It records exclusions and makes no model calls. |

The public functions are in `buddha.source_screen`:

```text
prepare_source_screen(directory, *, screen, authorization, review,
                      expected_runtime_sha256, input_bindings=None) -> Path
run_source_screen(directory, *, transport) -> dict
inspect_source_screen(directory, *, authorization, expected_report_sha256) -> dict
select_source_parent(references, *, method, max_active, seed, iteration) -> dict
```

These are Python API signatures. Preparation needs an existing grant with scope
`source screen: <comparison_key>`; local budgets do not create an allocation.
Each parent reference has exactly `directory`, `authorization` and
`report_sha256`. Selection accepts `archive`, `latest` or `uninformed`, inspects
every reference and rejects repeated source IDs or different comparison controls.
When none is eligible, it returns `selected_id: null` and the exclusion reasons.

Run preparation and execution need the original executing files. Passive inspection
needs retained evidence and a caller-supplied raw report hash, rather than the
retired producer programs. A report hash identifies bytes; it does not authenticate
the author or date of a scientific result. A retained source lineage similarly
checks local parent/child consistency without proving model authorship.

The screen directory keeps `screen.json`, `context.json`, one numbered directory
per task, and numbered incomplete observations. `report.json` appears only after
complete verified execution. Old observations and the original completion-time
cost snapshot stay intact when another candidate later uses the shared grant.

A complete report identifies the candidate, comparison and original control
fingerprints, optional recorded parent, every task's native metrics and
diagnostics, admission reasons, original owners/seals and accounting snapshot.
Its claim is limited to exploratory parent eligibility. Passive inspection also
checks both generation and native outer reports against their exact canonical
bytes; supplying a new hash for a forged scalar does not make it valid evidence.

## Limits and current validation

A declaration permits at most 64 selected development tasks, 16 native stages
and 256 planned owners. Each source remains one selected Python file under the
existing 1 MiB source ceiling and 0–1,000 callback ceiling. Parent selection accepts
at most 256 complete references and an active-pool limit of 2–64. Ordinary JSON
reads and complete report output are bounded to 32 MiB. Shared passive capture
retains its 10,000-entry, 1 GiB total and 512 MiB ledger limits. These are refusal
ceilings, not proof that every maximum-size schedule fits runtime or memory.

The 20 source-screen focused checks pass in 209.362 seconds with ResourceWarnings
treated as errors. All 153 consumed package, agent and test files remained unchanged.
The broad 191-Python-file inventory did change: the separate, unused conformance
probe was finalized during that cohort. Its before/after maps and that
qualification remain evidence; the whole inventory is not labeled unchanged.

Separate checks cover six new shared-reader boundaries, 13 existing policy-reader
cases, the original invalid-native-flow method and one launcher source-closure
regression. They ran at their individually recorded pins, not as one combined
suite. All seven final quality checks pass in 25.144 seconds with all 191 Python
files unchanged. Collection finds 1,413 unique test IDs, with no duplicates and
zero test bodies executed. The new slice's full hosted Linux and Windows
regressions remain pending; no full local regression is claimed. Separately, the
earlier native-assessment Linux regression passes 1,386 tests in 418.232 seconds
with five existing skips and all six hosted quality steps passing; its Windows
gate remains pending.

The [two-source confined probe](conformance/src02-source-screen-probe.py) is an
engineering driver that needs separately reviewed script and complete source-map
hashes, sealed runtime assets, retained synthetic child evidence and NEW synthetic
output paths. It creates only fake accounting and intercepts provider traffic;
it does not consume an actual experiment grant. Its actual confined run passes:
two source programs face the same two development tasks, producing 46 synthetic
replies across 16 screen owners and 16 removed workers (four agent, twelve native).
The original saved synthetic child uses one batch callback per task and totals
24 replies including native assessment; the separate zero-callback control totals
22. Their literal answers reach equal configured native request-body multisets.
The shared synthetic ledger records 230 microdollars spent and zero held. A
separate unused scaffold owner is explicitly closed with zero calls and no worker.

Completed screen replay, passive inspection, all three parent-selection methods
and passive inspection after retiring copied producer programs add zero calls,
workers or persistent changes. The saved proof is `source-screen-proof-evidence.json`,
raw SHA256 `6b70cb3ffcbe7a386dcd963dfaf33fbef4ff44cfed194db64a587b2220e2fad5`.
This proof injects no interruption; recovery and unknown-hold claims use their
separate focused evidence. Short weak answers, singleton groups and score-seven
replies are mechanism controls, not an independent metric oracle, real model
authorship, judge-accuracy or scientific improvement result. They do not establish
maximum-output capacity or real provider access.

Common screening does not yet connect proposal, feedback, mutation and parent
selection into the complete inherited source-search loop. That remaining work and
the actual model-authored experiment stay under SRC-02 in the consolidated plan.
Changed-improver competence and effectiveness remain separate open gates. POL-02
remains the sole Next; the seven major remaining leaves keep their existing gates.
