# Assess descendants without feeding the results back

This is the sealed-assessment connection for the [finite improver study](IMPROVER-STUDY.md).
The development study asks the initial and evolved improvers to improve the
same starting agents with the same budgets. This assessment then compares the
chosen descendants on a separate, previously assigned final task set. The
[paired analyzer](IMPROVER-ANALYSIS.md) calculates the resulting differences.
The official evaluator and its metrics remain unchanged.

Assessment declarations now pair explicitly with their development format:
v1 with study v1, v2 with study v2, v3 with study v3, and v4 with study v4.
Every mixed pair is
refused before preparation. V3 adopts the
[study's explicit comparison feedback](IMPROVER-STUDY.md#explicit-comparison-feedback-in-study-v3)
and keeps v2's aggregate funding rules, including an exactly matching declared
development allowance and a separately bounded final allowance. It does not
introduce a new analyzer, finalist rule or final-score feedback path.

V4 additionally requires the [study's existing original-request capacity
policy](IMPROVER-STUDY.md#original-request-capacity-in-study-v4). Complete
development inspection verifies the counted and mutation checkpoints before
finalists can be frozen. A capacity stop remains an incomplete development
result and cannot start final assessment. V4 retains the same aggregate funding,
final-task custody, descendant-selection and analysis rules; it does not add a
second capacity evaluator or silently upgrade an older declaration.

## Bounded v3 connection check

The [recorded offline check](conformance/imp01-v3-sealed-rehearsal-delivery.json)
starts a new v3 trial before development begins. Both improvers receive one
opportunity from the same starting occasion; the controller then freezes the
starter and two selected descendants and assesses all three roles on two final
tasks. All six scheduled assessments, analysis and later read-only inspection
complete. Original task text, full outputs, feedback, source identities, spending
records and final-task boundaries stay connected throughout.

This is a software check with supplied worker and judge responses. The two
descendant roles intentionally contain identical source bytes, yet retain their
separate histories and owners. Supplied role-specific scores exercise the
analysis; they say nothing about which improver is better. No model or selected
source runs in this check, no real API key is inherited and no API money is spent.
The local test took 1,197.903 seconds. Actual frozen-P compatibility, both actors'
model capacity, the future study's full-grid runtime, custody and prospective
funding/statistical/review choices remain open. This check creates no live-run
instruction or approval.

## What is fixed before work starts

The prospective trial binds the complete task source, development declaration,
task-family and exposure record, all final task IDs, generation and judging
settings, repetition counts, numerical method, decision rule and executing
source files. It reserves development and final allowances separately. Its
unused validation phase has a zero allowance; this route does not select
descendants using validation results.

Preparation checks the supported numerical method, versioned funding rules and
input-binding capacity for the maximum declared grid. It does not accept a
method name whose implementation will be supplied later. The original trial
controls reach the first development owner and all subsequent execution owners.

## Bind the reviewed launch and approval files

`prepare_improver_assessment_trial` accepts optional `input_bindings`: a mapping
from existing file paths to their independently reviewed SHA-256 fingerprints.
This lets the trial retain the exact launch and approval files alongside its
original experiment inputs. Static files that do not refer back to the trial
can still use the development declaration's existing `consumer_sources` field.

Supplying the mapping, including an empty one, selects a closed v2 trial context.
Omitting it preserves the existing v1 context. The study and assessment
declaration formats, phase limits and official scoring stay the same. Changed
trusted code still needs a fresh source closure; old saved trials require their
matching pinned code rather than a silent declaration upgrade.

Preparation checks the additional paths and fingerprints, conflicting pins,
output overlap and both development and final input capacities before publishing
the new trial. The original phase databases are refused as file pins because
enrolling owners changes those databases. The reviewed approval file and original
grant terms carry the authorization information instead.

The additional files reach the first development owner and later frozen controls.
Both active work and read-only inspection require their original bytes, even
when a file also serves as a selected program that could otherwise be retired.
These checks are sequential observations, not an atomic snapshot.

This remains a library interface, with no new command or live-run instruction.
Preparation writes trial records and enrolls the first owner against existing
grants; it makes no provider request. The complete funded launcher, recovery
handling and phase-aware progress remain separate work.

The custody record states which tasks belong to development, validation and
final assessment, along with their families and known exposure. The software
checks that record and its evidence. This is not proof that a public task was
absent from a model's training data, or that a custodian's statement is true.

## Check the complete funding requirement

IMP1-FEAS-02: the standalone source demonstration's broad per-owner ceilings
cannot be copied into a matched study and treated as its combined budget.
The original v1 controller adds those ceilings across every planned development
and final owner. Preparation requires the full derived phase allowances before
creating the study; an expectation of cheap replies does not waive that check.

The [source and arithmetic review](conformance/imp01-prospective-feasibility.json)
retains two unadopted count examples using the existing three-task development
screen and its unchanged broad owner ceilings:

| Starts / development repetitions / opportunities per arm | Final tasks / sealed repetitions | Final task sets across three roles | Combined authorization ceiling | Call ceiling |
| --- | --- | --- | --- | --- |
| 2 / 1 / 1 | 2 / 1 | 12 | $2,650.000030 | 15,852 |
| 3 / 2 / 2 | 6 / 2 | 216 | $25,050.000306 | 161,172 |

These are conditional reserve requirements, not expected API bills, price
estimates, recommended budgets or approved studies. They expose the consequence
of reusing broad owner allowances. Neither grid has been adopted, and the
separate $25 source demonstration stays unchanged.

Choose the actual grid and affordable, verified limits before requesting an
IMP-01 allocation. Recheck phase funding, fairness, capacity, evidence bindings
and reader cost at that exact design. The explicit v2 route below supplies a
different funding contract; it does not bypass or reinterpret the v1 guard.

Permission to retain partial results covers incomplete execution. It does not
turn a finished prefix into a complete matched comparison or waive preparation
requirements. Keep its stage, reason, coverage, costs and outstanding holds.

### Explicit aggregate caps in v2

`buddha.improver-assessment-trial.v2` requires a
`buddha.improver-study.v2` development declaration. Both v1/v2 mixtures are
rejected. Search funding must exactly match the development aggregate cap;
validation remains zero. Final funding can be a positive dollar and attempt cap
at most the complete derived final-grid ceiling. Each actual phase authority
must match its declared cap exactly. These remain three phases; ordinary
four-phase transfer-trial v2 is a separate interface.

The grid, source copies, request bounds, native evaluator and analysis method
remain fixed. The existing ledger enforces each combined phase cap. If funding
runs out, the original execution records an incomplete result with its stage,
reason, full expected coverage, costs and holds. Continuing checks and reuses
original owners; it does not grant replacement money or duplicate paid calls.
Full development is still required before freezing descendants. Full scheduled
execution is still required before a complete final report; a finished prefix
does not qualify. A partial panel cannot establish a matched comparison by
dropping unfinished arms or tasks.

The [development guide](IMPROVER-STUDY.md#versioned-funding-limits) explains the
shared-cap fairness limit and its optional no-cost checks. This library route
does not adopt an IMP-01 grid, method, allocation or live command. The separate
approved source demonstration and its frozen inputs remain unchanged.

## What freezes after development

The freeze reader reconstructs the completed development study from its
original execution, funding, feedback and selection records. Caller-written
scores or a list of candidate hashes cannot replace those records.

For each starting condition and development repetition, the final schedule
retains the original starter and both descendant slots: one for the initial
improver and one for the evolved improver. A slot with no valid descendant
stays explicitly absent. It is not replaced by the starter or assigned a zero
score. Identical source code in two roles still gets two separate assessments.

The complete ordered schedule, original source copies and confirmation are
written once. The first freeze entry closes further adaptive work, even if an
interruption prevents confirmation from being written. A failed first freeze
does not silently reopen development. Repeating a successful freeze only
checks and returns its original records.

## What runs and what gets reported

Each executable starter or descendant runs on every frozen final task and
repetition through the existing confined generation and official native
evaluation routes. The starter is measured once per condition and is shared
by the two gain comparisons. Final tasks and results do not become development
feedback. There is no new search, ranking, automatic adoption or source change
during assessment.

The execution journal retains interruptions, completed prefixes, costs and
outstanding holds. Resume checks the original owners and replies before doing
unfinished work. A checked generation failure stops the physical grid with an
explicit incomplete record; the controller does not quietly skip that task.

A completed execution report distinguishes physical coverage from scientific
coverage. All scheduled executable cells can finish while a missing descendant
or undefined official scalar leaves the planned comparison inconclusive. The
analyzer retains the original allocation of uncertainty across both metrics
and the three comparisons; it does not spend unused allocations on a smaller
successful subset.

Passive inspection reconstructs the report from the original native records.
It checks both final evidence and the retained development evidence through
the end of the read, including changed bytes, new entries and database
sidecars. It needs no API keys and makes no provider calls or record changes.


## Rechecking archived assessments

A finished assessment and a confirmed descendant freeze can be checked after
external starting-agent and improver source folders have been retired. The
reader keeps their original paths and hashes in the experiment's bindings,
then reconstructs the original development, funding, selection and final
records. It still requires the retained private source copies and all data
needed to interpret the result, including runtime, profile and native
components. A file that also serves one of those data roles remains required.
The matching approved software and original accounting checks still apply.

This is a read-only check: it needs no keys, starts no worker and spends no
money. Repeating a completed run or a confirmed freeze returns the original
checked result or refuses it; missing evidence cannot turn that request into
fresh execution. Changed retained source copies or inconsistent records still
stop verification.

New preparation, the first freeze and unfinished execution still require the
original current source files before entering a writer or creating further
work. Archival inspection does not grant permission to resume an unfinished
experiment with missing producers. The ordinary live container constructor
also retains its filesystem checks; passive reconstruction validates only the
source-mount metadata that it no longer executes.

## Library interface

This is a Python library. A funded operator handoff and an actual controlled
comparison are separate work; this page supplies no live command or allowance.

| Function | What it does |
| --- | --- |
| `prepare_improver_assessment_trial` | Checks the prospective declaration and existing phase allowances, then creates a new trial and its finite development study. Writes local records; makes no provider calls. |
| `freeze_improver_descendants` | Checks completed original development evidence and writes the irreversible final schedule. Makes no provider calls. Repeating a confirmed freeze is a read-only check. |
| `inspect_improver_assessment_freeze` | Checks the original confirmed schedule and development evidence without changing records or spending money. |
| `run_improver_assessment` | Runs or resumes the original final grid. A live transport can spend its separately approved final allowance. |
| `inspect_improver_assessment` | Checks a completed saved report without keys, new calls or record changes. |

The report supports the declared fixed-panel comparisons under their stated
assumptions. It does not establish better future searches, generalization to
unseen tasks, human quality, targeted repair, promotion or a leaderboard result.
