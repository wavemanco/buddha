# Saving an incomplete comparison clearly

Stopping a live comparison must leave a useful record even when it has no final
score or an interrupted step has no saved report. The new observation writer
records that stop separately from complete benchmark results. It does not start
or resume the experiment.

`buddha.comparison_observation.save_observation` writes one explicitly named new
JSON file. It returns that path, the file's SHA-256 hash and the read-back
observation. Every observation has its own file; an existing file is never
overwritten, repaired or promoted into a complete result.

## What the record says

The overall status is always `incomplete`. The stop section contains the
launcher's reported phase, machine-readable reason and whether it was cancelled.
Those reported facts are labeled `launcher_reported`.

Verified saved-state summaries are recorded separately for the primary Buddha
study and its plain references. They preserve their observed state, next
position or step, blockers and state hashes. If a reader cannot establish a
summary, its value is explicitly unavailable. The writer does not invent an
attempt report or infer a stopped stage from the absence of one. Cancellation
can legitimately happen before the controller saves such a report.

The financial section observes the three primary allowances and the one shared
plain-model allowance. It counts that shared allowance once:

- If all four original allowances can be observed consistently, the record has
  their combined recorded spending, holds and attempt count.
- If only some can be verified, `known_subtotal` sums those identified
  allowances, and the overall `totals` remain unavailable.
- If none can be verified, both figures are unavailable. Unknown amounts are
  never replaced with zeros. A real observed zero remains a valid zero.

Each allowance has its own availability status and fixed diagnostic reason.
Changed identities or bytes are marked unavailable. Duplicate grant identities
or paths cannot produce a supposedly unique subtotal. Holds remain held; an
`authority` stop is not rewritten as proof that the budget ran out.

These are sequential observations of recorded accounting, not an atomic snapshot
of a running experiment or a provider invoice. A state summary and a financial
summary can have different availability. Neither supplies approval to spend.

## Protecting the original evidence

The writer first verifies the pinned primary launch, comparison plan and raw
baseline definitions. It derives protected paths before arming any output.
Those exclusions cover original run directories, attempts, artifacts, ledgers,
grants, definitions, tasks, generation recipes, component roots, source folders
and additional controls. A new observation cannot replace a protected path or
occupy a parent where a future protected directory must be created.

It uses the existing exclusive-create writer, flushes and fsyncs the file, then
reads back the exact bytes. Failure preserves the original execution records.
A failed write can leave its new file for review; it is never silently erased
or overwritten. The future combined launcher must report observation failure
without masking its original error or cancellation.

Only selected summary fields are written. Full controller reports, exception
messages and provider replies are not copied into this diagnostic. The writer
does not read credentials, dispatch requests, create owners, release holds or
change official scores.

## Reading it later and what remains

`read_observation` checks the expected external hash and the observation's schema.
It checks the incomplete status and financial arithmetic without reopening
the old grants, models, component directories or live run. Advancing a run or
retiring its producer does not rewrite the earlier observation. Reading it tells
you what was recorded then, rather than reinterpreting it using today's state.
The hash is a consistency check, not an independent attestation of the stop.

The [funding check](UNIFIED-FUNDING-CHECK.md),
[reference recovery check](BASELINE-RECOVERY-CHECK.md) and this writer are now
separate implemented pieces. The [combined launcher](UNIFIED-LAUNCH.md) now
connects them with the existing controllers and handles observation failure at
that execution boundary. Its full execution rehearsal and exact live handoff
remain required. Exact
review/adoption, account/price/request, hosted-CI and funding gates still precede
a live command. The proposed budget and original study remain unchanged.
No new user command is introduced here.
