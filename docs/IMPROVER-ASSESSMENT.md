# Assess descendants without feeding the results back

This is the sealed-assessment connection for the [finite improver study](IMPROVER-STUDY.md).
The development study asks the initial and evolved improvers to improve the
same starting agents with the same budgets. This assessment then compares the
chosen descendants on a separate, previously assigned final task set. The
[paired analyzer](IMPROVER-ANALYSIS.md) calculates the resulting differences.
The official evaluator and its metrics remain unchanged.

## What is fixed before work starts

The prospective trial binds the complete task source, development declaration,
task-family and exposure record, all final task IDs, generation and judging
settings, repetition counts, numerical method, decision rule and executing
source files. It reserves development and final allowances separately. Its
unused validation phase has a zero allowance; this route does not select
descendants using validation results.

Preparation checks the supported numerical method and enough money, calls and
input-binding capacity for the maximum declared grid. It does not accept a
method name whose implementation will be supplied later. The original trial
controls reach the first development owner and all subsequent execution owners.

The custody record states which tasks belong to development, validation and
final assessment, along with their families and known exposure. The software
checks that record and its evidence. This is not proof that a public task was
absent from a model's training data, or that a custodian's statement is true.

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
