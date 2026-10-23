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

The supported library contract covers one declared source TaskSet and its assigned phases. It does not silently combine datasets or claim full benchmark coverage.

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

`prepare_evaluation_trial` checks and records the declaration and three original
phase grants before preparing the limited validation study.

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
