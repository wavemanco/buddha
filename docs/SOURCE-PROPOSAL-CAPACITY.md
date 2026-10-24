# Capacity checks on actual source proposals

The prospective source route can use its actual proposal requests as capacity
observations. It does not need to buy a second copy of the same request. This
feature does not allocate money, prepare a live handoff or enable a user command.
The [living plan](PLAN.md) retains the remaining source and scientific gates.

The new policy applies only when explicitly selected in source handoff v4 and
source-search manifest v5. Older records keep their original interpretation.
The historical [one-request result](SOURCE-CAPACITY-RESULTS.md) remains evidence
about its exact request; it does not certify future requests or evolved code.
This prospective policy supersedes an early design draft that imposed the
replacement-output margin on planning calls too. It does not change an old
experiment's criteria or turn a supplied-response rehearsal into a live run.

## What is checked

After a proposal worker finishes and its original paid records are settled,
Buddha reads every original request and reply from that owner. Before preparing
or running the returned child, it checks the actual input usage and each
request's actual output limit against the selected model's context window.
It also verifies that each completed record's original reservation and charge
agree with the Gateway's request bounds, original rates and inclusive usage.
Inconsistent completed billing evidence is refused as contradictory custody;
it is not reported as an ordinary capacity result. This recheck does not certify
that old prices remain current for a new run.

For every proposal callback, including planning:

- The reply must be complete, unrefused text with a normal finish and valid
  original model, processing tier and inclusive usage.
- The model's context window minus actual input tokens and the request's entire
  output allowance must leave at least **8,192 tokens**.

For the complete replacement source, the actual output allowance minus inclusive
output usage must also leave at least **8,192 tokens**. Reasoning tokens remain
part of output usage. A smaller request cannot borrow the larger profile limit
when calculating its room.

This replacement observation requires at least one original raw reply containing
a valid source proposal whose literal source matches the materialized child's
source. Small, complete planning replies have no replacement-output margin test.
They still undergo the context and complete-reply checks. A patch-based or
programmatic mutation without a matching full replacement reply remains
unavailable/inconclusive under this supported policy; it is not silently called
a successful full-source capacity observation.

These are observations after real replies arrive, before the host schedules the
returned child. Future request bytes have not passed in advance. The existing
byte limits stop oversized feedback without shortening it; byte counts are not
substituted for token counts.

## Where it stops execution

The same rules cover the parent's validity child W0, the counted child C, and
the further child W1 authored by C's own improver. The existing controller keeps
its loop, confined workers, API gateway, official evaluator and accounting.

A negative or unavailable capacity result records a partial search with reason
`proposal_capacity`, the exact stage and the saved measurement. It does not
prepare or execute that returned child's generation owner. Earlier charges,
rejected proposals and unresolved liabilities remain recorded; the controller
does not extend the experiment or repair returned source to make the check pass.

Each measurement is saved as `proposal-capacity.json` beside its proposal
directory. The record identifies the fixed policy, anchored proposal, original
owner and ledger, complete request population, exact raw evidence and measured
margins. Verification reproduces those values from the original receipts.
Changing a saved field and supplying a new hash cannot make it valid.

## Recovery and comparisons

If execution stops after the proposal is saved but before the capacity record,
the original replies can be checked on continuation without another API call.
A completed proposal whose owner was sealed just before its report was saved
can also finish that local publication. Its returned child remains blocked
until the original report and passing capacity record have been verified.
A saved negative result stays negative on continuation. Missing or contradictory
records followed by child work are refused. Complete verification remains
read-only and does not request API keys.

The policy and executing consumer are fixed in the original search controls.
Existing child lineage identifies the original proposal and returned source.
Per-child measurement files do not enter the common comparison controls: adding
different files there would change the comparison itself. The controller
reconstructs each required measurement and enforces it at execution and passive
verification boundaries. A checkpoint alone is not an authenticated timestamp.

The barrier covers host-authorized execution of the returned child. It does not
claim to prohibit computations that the already confined parent performs while
authoring its proposal. Passing capacity establishes neither code quality nor
substantive source changes, improved diversity, or improved ability to improve.

## Record compatibility

The capacity-enabled route uses source handoff v4, search manifest v5,
source-search report v3, witness treatment v2 and witness report v2. The fixed
capacity policy and each capacity checkpoint have their own v1 record formats.
Older supported formats retain their meaning and helper inventories. The
capacity helper is imported and added to controls only when the new policy is
explicitly enabled; a new proposal builder must select that expanded inventory.

Progress reports follow that same opt-in boundary. Older witness readers keep
their original eight-field internal progress record and five-field search
projection. Capacity-enabled search projections also expose the current lower
role and the original capacity checkpoint reference (or `null` before it is
published). This lets the launcher show the capacity stage without treating an
unfinished capacity check as ready child execution. The internal lower-role
field remains available to the shared witness and finite improver controllers.

The first exact producer's Ubuntu suite exposed three places where new fields
leaked into legacy reports. The [compatibility correction](conformance/src02-capacity-progress-compat-delivery.json)
keeps the original tests unchanged and fixes the shared projection. It does not
weaken capacity checks, rewrite old owners or turn that historical failed CI
head into a passing result. The corrected head needs its own hosted checks.

There is no new spending allowance, owner type, provider route, command-line
switch or official NoveltyBench scoring rule. A future actual live handoff still
needs its own reviewed intent, funding and current account/price checks.
