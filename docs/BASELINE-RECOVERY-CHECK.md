# Checking saved plain-model runs before resuming

Each generation or evaluation step has an **owner**: its permanent run identity,
frozen inputs and spending ledger. Resuming must keep that identity. Creating a
new owner after losing the old record could repeat work or hide an uncertain
charge.

`buddha.baseline_state.inspect_references` now inspects both planned plain-model
references together, before the future combined launcher enters keys or starts
another request. It uses the same shared allowance for independent and
in-context sampling. The [combined funding check](UNIFIED-FUNDING-CHECK.md)
separately checks the four allocations against the overall ceiling.

## What the inspection verifies

The comparison plan fixes the two directories, baseline definitions and analysis
code. Every existing owner must retain that plan, the current inspection code
and any additional approved controls in its original inputs.

Before owners exist, the observation also captures the exact task, recipe and
selected profile bytes it reads. It rechecks them before returning and includes
their hashes in the state seal, so a valid configuration change cannot look
like the same unchanged state during key entry.

The check joins every existing owner to its actual original shared funding.
Owner directories must form the expected consecutive sequence. Empty, foreign,
replaced or missing funded owners are refused, including an entire missing peer
directory. An unrelated owner elsewhere on that shared allowance is also
refused. Moving or deleting records does not make the experiment fresh again.

Completed steps must have their original output files, completion seals and
independent funding anchors. The inspector verifies the generation's tasks and
answers, the handoff into evaluation, and each existing evaluation owner's
command and staged inputs. Instructions must remain empty for these plain
references, and each recipe must use its declared sampling mode and profile.

Later evaluation files cannot precede the required completed steps. In
particular, native answers, an evaluation command or evaluation staging cannot
appear while generation remains unsealed. This prevents an earlier paid step
from running before the controller discovers impossible later data. Preparation
for the next step is allowed after its predecessors are sealed; the existing
controller still validates that preparation before sending a new request.

## Reading the result

For each reference the result says whether it is fresh, prepared or complete,
how many owners and completed steps it has, and which step comes next.
“Prepared” includes a retained interrupted run. Only an existing publication
that passes the original complete-result reader is called complete.

The shared financial summary counts spending, attempts and unresolved holds
once across both modes. A dispatched or unknown request anywhere on that
allowance blocks new work in both references. An observed charge exceeding its
original reservation also blocks work. Unfinished owners that have been
deactivated remain stopped. A retained execution lock is a stop regardless of
whether its recorded process still exists; the inspector does not remove it.
Unsent reservations remain held and stay visible in the result.

`ready` means that this inspection found no custody stop. It supplies no
spending approval, account authentication or permission to resend a request.
It does not certify current producer availability, runtime readiness or future
request capacity. The combined launcher must check funding and accounts,
repeat the observation after key entry, and use the original controllers and
transactional ledgers for execution. Sequential observations are not an atomic
snapshot of a running experiment.

## Evidence and remaining work

The inspector reads bounded copied database bytes in memory. It does not create
or replace owners, read credentials, contact providers, execute selected source,
release holds or change files. Extra frozen controls retain the gateway's
256 MiB input bound. Completed-result readers still support retired producer
code and their existing large-ledger/artifact bounds.

Checks use real fresh synthetic owners with mocked provider/worker execution.
They cover interrupted generation and evaluation, same-owner recovery, shared
uncertain billing, foreign/missing owners, altered controls and outputs,
inactive owners, locks, large controls and changes during inspection. The
impossible-future-files check was reproduced failing before its source fix.
The existing complete-result, baseline and native-evaluation suites remain
separate regression evidence; no new benchmark score or scientific conclusion
is established.

A second failing regression showed that fresh recipe changes could leave the
state hash unchanged, and a late change could go unnoticed. Capturing and
rechecking fresh intrinsic bytes fixes both cases. The final 17 new methods and
44 existing regression methods pass; the delivery record keeps their scopes
and timings separate.

The next slice must save append-only partial observations with their actual
stage, reason, costs and holds, then connect both checks and the original
controllers into the combined launcher. The 166-file unfunded preparation stays
unchanged at its recorded source cut; a fresh handoff must bind the final
executing code before live use. No new user command is introduced here.
