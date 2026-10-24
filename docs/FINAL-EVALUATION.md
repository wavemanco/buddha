# Freezing and evaluating finalists

This controller is the last comparison stage of one prospectively declared
experiment. Development and limited validation help choose agents. Final
evaluation then runs the chosen agents and fixed comparison agents against
every task assigned to the experiment's final set. Its answers do not go back
into the improvement loop.

This is a library interface, not a funded experiment or a command to run now.
NoveltyBench remains the selected official evaluator. This controller controls
which agents and tasks are evaluated, when they may run and how the existing
statistical rule consumes their official measurements.

## What must be fixed before observations

The original `buddha.evaluation-trial.v1` contract covers one declared source
TaskSet and its assigned phases. A new ordinary trial can opt into
`buddha.evaluation-trial.v2`, adding a separately declared transfer source and a
fourth original grant. Existing trials keep their original declarations. Neither
version silently combines datasets or claims full benchmark coverage.

The declaration binds the original validation declaration, complete task
population and exposure history, finalist count, comparison agents,
repetitions, practical-effect rule, uncertainty method and implementing source
files. It also states separate search, validation and final budgets and attempt
limits. Each phase needs its own original approved authorization; preparing a
declaration does not grant spending permission.

The current supported selection policy is explicit ordered finalists. The
caller chooses exactly the declared number from candidates with complete
original validation results. This policy does not automatically rank candidates
or claim that a chosen candidate is the best one. The original complete
validation-result population must be supplied; convenient results cannot be
silently omitted. A larger or different selection policy needs a prospective
declaration of its own.

Every assigned final task must be present and still eligible. The controller
does not take the first few tasks or reduce the finalist count after failures.
A declared subset remains a subset of NoveltyBench; complete coverage of that
subset is not complete coverage of the benchmark.

## The one-way freeze

`prepare_evaluation_trial` checks and records the declaration and original phase
grants before preparing the limited validation study: three grants for v1, or
four for v2.

`freeze_finalists` verifies the original validation evidence, chosen sources,
quiescent earlier phases and unused final allocation. It saves the full final
schedule, source copies and a positive confirmation of that schedule. Creating
the freeze entry permanently closes new adaptive work in that trial. If saving
or confirming the freeze fails, the trial remains closed; it cannot choose new
finalists or reconstruct a convenient confirmation.

`run_final_evaluation` uses that original confirmed schedule. It runs every
agent/task/repetition cell through the existing confined generation and native
evaluation paths. Each candidate receives the current task through the existing
model-channel boundary. The trusted host can read the declared population to
enforce coverage; that does not give the candidate a mount of the final dataset.

## Saved evidence and interruptions

The schedule binds each original owner to the final allocation and frozen
controls. A final grant, a copied confirmation file or matching paths alone do
not authorize new direct Gateway execution: execution also needs the checked current
cell inside the consumer's original trial lease.

Completed cells and raw evidence remain at their original paths. A partial
observation must identify the durable completed prefix, next unfinished stage,
reason, original owners and accounting. Recovery uses those original records.
If every task result is saved but the combined report is not, the unfinished
stage is report publication. Completing that stage reuses the saved results;
it does not generate or judge the answers again.
Unknown provider liability stays held and does not authorize a replacement
request. A settled response may be finished without another paid send. No
elapsed-time rule permits deleting a lock or changing an authority.

`inspect_final_evaluation` checks a completed report from its original saved
evidence without keys, workers or new calls. It must reproduce the complete
declared grid and saved result; it cannot publish a favorable subset.

## What the result means

The report retains both official metrics for every required cell, equally
weighted prompt aggregation and the declared family grouping. The final
one-sided tail allocation remains `alpha_final / (2 × F × M)`, where `F` is the
original finalist count and `M` the original comparator count. Failed or missing
slots do not enlarge another comparison's allowance. A required missing scalar
makes its comparison inconclusive.

The bounds rely on the declared independence between prompt families and valid,
bounded official scores. Saving the declaration does not prove those scientific
assumptions.

The fixed practical-effect rule consumes conservative lower bounds. Completing
the run does not mean that an agent improved, that it should be adopted or that
unseen tasks will improve. Human review, transfer evidence and improved-improver
claims retain their separate gates in PLAN.md.

## A separately declared transfer comparison

Transfer asks whether the same frozen agents also work on independently authored,
sealed prompts beyond the benchmark prompts used for development and selection.
Reworded NoveltyBench prompts do not establish independent transfer. The code
checks declared task contents, families and exposure records; those records do
not prove independent authorship, secrecy or absence from a base model's training.

The current route supports an ordinary trial with two sealed panels: final and
transfer. Both use the same official evaluator, model settings, answer-generation
procedure, execution limits and per-cell resources. Transfer does not introduce
a replacement diversity metric or alter NoveltyBench scoring.

Before preparing any trial owners, the v2 declaration must bind the transfer
TaskSet, its complete custody record, every assigned transfer task ID, repetitions
and execution settings. It must also bind the v2 analysis plan and four distinct
original approved authorizations: search, validation, final and transfer. Each
authorization retains its own budget and attempt limit. A declaration creates no
spending permission and cannot reuse an earlier experiment's allowance.

The present compatibility rule is deliberately narrow. The transfer release must
retain every original official source file unchanged and add exactly one new
JSONL dataset path, with different dataset bytes and a distinct release identity.
Its task-field mappings, answer count, evaluator commands, dependencies and other
release settings stay the same. The added path must end in `.jsonl`; adding an
importable Python dataset is refused. Component locations may differ when their
required contents and settings agree. This is an immediate supported input
contract, not a claim that arbitrary benchmark changes need no adapter work.

The transfer TaskSet has its own source identity. The same raw task ID may occur
in both sources without identifying the same prompt. Every member of both complete
populations participates in the overlap checks, including unselected members.
Declared families and normalized duplicate prompts cannot cross the two sources.
All assigned transfer members must be included, eligible and undisclosed to the
named improvement process. A selected subset is still only that declared subset.

`freeze_finalists` performs one shared freeze after checking the original
validation evidence and unused final and transfer allocations. It saves one set
of copied agent sources and one confirmed schedule containing both panels.
Both panels use those same frozen agents. Their reports and partial observations
bind the hash of the whole shared schedule, alongside their own phase, release
and TaskSet identities. There is no second selection step after seeing final
results, and neither panel supplies adaptive improvement feedback.

`run_final_evaluation` runs the final panel.
`run_transfer_evaluation(directory, *, authorization, review, transport)` runs
the declared transfer panel using its original transfer authorization and review.
These are paid-capable library APIs, not operator commands or permission to start
a run. Lower Gateway work still needs the checked current cell inside the original
trial lease; a matching grant or copied freeze file does not enable direct work.

An interruption keeps the original transfer owners, replies, completed cells,
accounting and reason for incompleteness. Continuing through the same transfer API
uses those original records. Completed generation or judging is not repeated to
fill a missing combined publication. It does not rerun the final panel or release
unknown provider liability.

`inspect_transfer_evaluation(directory, *, expected_report_sha256)` checks a saved
complete transfer report against its original evidence. Like final inspection, it
needs no keys, workers or API calls and writes nothing. It checks captured database
bytes in memory; it does not open the saved databases for active work. Completed
transfer execution can also return the checked saved result without new paid work.

The v2 analysis plan reserves a separate, positive transfer error allowance within
the declared total. Its one-sided tail is
`alpha_transfer / (2 × F × M)`, using the original finalist count `F` and comparator
count `M`. It is separate from the final tail and does not grow after failures.
A missing required native scalar stays explicitly unavailable and makes the
applicable improvement rule inconclusive. Completing all cells is not evidence of
improvement or a guarantee about unseen prompts.

This slice supplies the ordinary-trial transfer route. It does not complete an
actual held-out study, choose or certify a human-review protocol, establish
independent authorship or close EVAL-02. Transfer-specific reviewer export/import
and the improved-improver assessment bridge are not yet supported. The existing
final-only and IMP-01 interfaces do not acquire transfer support automatically.

## Optional offline transfer check

```powershell
python -m unittest discover -s tests -p test_transfer_evaluation.py -v
```

This runs the focused transfer checks once in the current PowerShell window;
no separate window is needed. It creates temporary synthetic tasks, owners and
accounting files and uses simulated workers and API replies. It needs no key or
Docker worker and spends no API money. The composed lifecycle can take several
minutes. Ctrl+C stops the foreground checks. Passing them checks this
implementation scope, not independent transfer or agent improvement.

## Check the controller offline

From a checkout containing this slice:

```powershell
python -m unittest discover -s tests -p test_final_evaluation.py -v
```

This runs the focused controller checks once in the current PowerShell window.
They use temporary synthetic data, accounting records and simulated workers and
API replies. They need no key or Docker worker and spend no API money. These
composed checks can take many minutes, especially on Windows. Ctrl+C stops the
foreground checks. Passing them checks implementation behavior, not agent
improvement. The [delivery](conformance/eval01-final-controller-delivery.json)
records the actual checked source cuts and limitations separately.

## Infrastructure completion

EVAL-01 is complete for the supported prospective one-source library. At PR #89
head `572bf75837841162de32c4941c8c2096dfe45d96`, both hosted jobs pass 1,714
tests and every configured quality check. The [completion record](conformance/eval01-hosted-completion.json)
joins those jobs to the original delivery and checked source bytes. Later
commits need their own applicable checks.

Actual held-out results, independent human review and transfer evidence remain
EVAL-02. This completion creates no allocation or live experiment.
