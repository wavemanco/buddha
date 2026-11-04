# Checking the combined study budget before keys

The combined study needs one clear budget even though its existing controllers
use separate allowances. The new passive check verifies that the three Buddha
allowances and the one shared plain-model allowance add up to the declared
total. Both plain sampling modes use that same fourth allowance.

This is an implemented part of the coordinated launcher described in
[the unified preparation](UNIFIED-COMPARISON-PREPARATION.md), under DESIGN
sections 5, 7, 8 and 9. It does not start the experiment. The proposed $150 split
remains $40 development, $85 Buddha final assessment and $25 shared by both plain
references, with the separate 16,384-attempt limit. Nothing is funded by adding
this code.

## What it checks

`buddha.unified_funding.check_funding` reads the explicitly selected primary
launch, comparison plan and original allowance files. Its caller must supply
the approved file hashes, exact shared-grant identity and combined limits.

- It calls the existing primary-launch checker, preserving that checker's state,
  phase and stop reason.
- The comparison plan must name that same trial and definition. Its current
  analysis code, plan and new funding-check code must already be included in the
  primary launch's frozen inputs.
- Both plain references must name the same original allowance. Their descriptor
  bytes must still match the plan's hashes.
- All four allowances must have distinct paths, IDs and scopes. The shared
  reference scope is tied to the exact comparison-plan hash. Protected inputs
  and output locations cannot contain the reference allowance.
- Dollar and attempt limits must be bounded integers. The four allocations must
  sum exactly to the declared combined limits. Zero is permitted for an unused
  primary phase, such as validation.
- Recorded charges and unresolved reservations are retained and counted once.
  A fresh study cannot replace used funding. Existing dollar- or attempt-cap
  overruns are refused.
- It rechecks captured allowance bytes and selected controls before returning.
  A detected change refuses the observation.

The result contains the combined limits, four individual allocations, each
allowance's recorded spending and holds, their summed totals, and the original
primary-check result. For example, an unresolved primary request remains an
execution stop even when the budget arithmetic is consistent. A hold is retained
liability; passing this check does not release it or resend its request.

## What this slice establishes

The check reads copied SQLite bytes using the existing passive readers. It does
not construct an authorization object, create an owner, enter a key, contact a
provider, run selected agent code or write a result. It supplies no spending
approval or account authentication. Its argument values must come from the
future approved outer handoff.

This is a bounded observation, not an atomic transaction across four files.
The later launcher must repeat its checks after key entry, and the existing
transactional ledgers continue enforcing each allowance during dispatch. The
scope label identifies the reference experiment; it does not itself prove that
existing owners belong to the two intended baseline directories.

The existing 166-file preparation is preserved at its previous source cut.
Before live use, fresh configuration must bind the changed executing code;
this slice does not silently rewrite that preparation or any historical run.

## Verification and next work

The new checks use fresh synthetic authorities only. Thirteen focused methods
exercise shared-budget arithmetic, strict bounds, hashes, trial identity,
changed descriptors, unbound controls, repeated grant identities/scopes,
protected paths, existing charges/holds, reused funding and changes during
observation. A fourteenth method composes the real original primary-launch
checker with four fresh synthetic allowances. Guards reject key access,
provider/network execution, selected-source parsing and direct SQL connections
to original files. Only copied in-memory database reads are allowed while
checking. Files remain unchanged after each check.

The [whole-baseline original-owner preflight](BASELINE-RECOVERY-CHECK.md) is now
implemented at its passive inspection scope. The next slice still needs
append-only partial observations, followed by coordinated execution through the
existing primary and baseline controllers. The outer launcher must validate all
original raw owners before entering keys or making another paid request. It must
save an incomplete result's stage, reason, spending and unresolved holds without
presenting it as a complete comparison publication. Reviewer/adoption decisions,
account/price/request checks, changed-head hosted CI and a funded handoff still
precede the live command. No new user command is introduced here.
