# Current-source live experiment

This is the next actual code-evolution observation for SRC-02/03. The protocol
and review criteria are adopted. A new unfunded input bundle passes the existing
passive configuration checks; it has no spending permission or user run command.
[PLAN.md](PLAN.md) remains the current roadmap.

The earlier $7 observation checked whether one exact full-output request could
return a complete source proposal with enough space left. This experiment
measures the current parent itself and runs its model-written descendants.
[Preparation evidence](conformance/src02-actual-live-preparation.json) records
the new bundle, checks and remaining requirements.

That prepared producer later failed three legacy progress-report compatibility
checks in Ubuntu CI. The [shared correction](SOURCE-PROPOSAL-CAPACITY.md#record-compatibility)
has its own checks and source cut. The original bundle remains unchanged and
unfunded; a fresh bundle pinned to corrected executing code and its own hosted
checks is required before funding or a user command. The adopted experiment
protocol and criteria remain unchanged.

## What the experiment does

The starting agent P is our fixed Python program. It can generate answers and
ask an API model to write a replacement program. The experiment checks whether
a model-written replacement changes procedures that actually run, including
the procedure for proposing the next replacement.

The order is fixed before execution:

1. P produces ten answers on each of three development tasks. The unchanged
   official NoveltyBench 1.1 evaluator groups and scores those answers.
2. P receives all thirty answers and their measured results. Its improver
   proposes W0, a separate child used to check that mutation still works.
   W0 must generate ten answers on the first task before P can be selected.
3. P makes a separate proposal C. This is the one counted search iteration;
   W0 is not promoted into that role.
4. If eligible, C generates and is assessed on the same three tasks.
5. C's own inherited improver receives all of C's measured feedback and
   proposes W1. W1 generates ten answers on the first task as another bounded
   validity check; it does not start a second search iteration.

A fully successful sequence contains eighty generated answers: thirty each
from P and C, and ten each from W0 and W1. Only P and C receive the full official
three-task assessment. Later stages depend on earlier eligibility. A stopped,
invalid or unavailable stage remains recorded, including downstream work that
could not be attempted. This answer count is not a promise of completion or an
API-call estimate.

These are previously seen development tasks: `curated-0`, `curated-47` and
`curated-97`. This experiment supplies no held-out or human-preference result.

## What the improver can read

It receives the complete selected answers and measured feedback, rather than
the historical sixty-four-byte story prefixes. Every original proposal call
must pass the [capacity rules](SOURCE-PROPOSAL-CAPACITY.md) before the host
prepares or executes its returned child. If the evidence or space is
insufficient, the run stops with a reason; it does not silently shorten stories.
The capacity observation uses the original paid reply, with no duplicate probe.

## How we decide what happened

The [adopted protocol](conformance/src02-actual-live-protocol-v1.md),
[exact intent](conformance/src02-actual-live-intent-v1.json) and
[criteria](conformance/src02-actual-live-criteria-v1.json) distinguish:

- whether the declared stages completed;
- whether actual model replies authored the literal child programs;
- whether substantive generation changes actually ran;
- whether C's substantively changed improver actually authored W1;
- how P and C scored on both official development metrics.

An unchanged prompt wrapper, an unused helper or a better score does not prove
that a changed procedure ran. Root checks original records and source identity;
a separate fresh-context reviewer examines procedure changes and evidence of
their use. Both findings are retained. Missing evidence or unresolved
disagreement stays inconclusive. These are engineering reviews, not independent
human ratings.

Official scores may decline while code evolution works. Better improver
effectiveness remains IMP-01; independent useful-diversity evidence remains
EVAL-02. No private score replaces NoveltyBench.

## Spending and keys

The proposal requests a **new, currently unallocated $25 combined cap and
512 physical-attempt limit**, allowing explicit partial results. Earlier
allowances cover closed experiments and cannot fund this one. The amount is
a maximum, not a spending target or completion estimate. Conservative
reservations can stop work before the cap is spent; unresolved requests retain
their holds.

OpenAI serves generation, source proposals and official grouping. Anthropic
serves official quality scoring and its fallback. A later approved local launch
will therefore need both keys. Keys are entered locally and are never part of
these committed protocol files.

## Current handoff status

The new bundle is separate from the supplied-response rehearsal. It contains
the adopted actual-live protocol, unchanged starting-agent bytes, freshly
selected current runners and the unchanged official evaluator and host profiles.
The source handoff is v4, including original-proposal capacity checks. Its
passive check reports unallocated funding and a maximum of twenty-nine original
owner destinations. Preparation created no owners or database and made no
provider call. All six filesystem, SQL, process and network guard controls pass;
these are checks on this trusted preparation, not a general security claim.

The input review gives a conditional bound for the planned owners, including
permitted empty database sidecars. The final funded launch must confirm its
actual file list fits the existing limit before use.

No live command is available at this checkpoint. Remaining checks include the
final launch bindings, selected executing code and hosted CI, applicable
account/pricing conditions, and a separately approved allocation. Public price
and supported-request reviews do not authenticate keys or verify account
settings. A later funded handoff will document the exact command, its function
and expected output before asking the user to run anything.

Interrupted work may continue only through supported recovery of the original
owners and frozen requests. Known completed replies are reused without another
provider call. Unknown liabilities stay unresolved. There is no replacement
owner, adaptive source repair or extra iteration to manufacture a positive
outcome.

The adopted protocol files retain their preparation-time statements and hashes.
Later preparation, funding and results require separate records; they do not
rewrite those files or the earlier supplied-response rehearsal.
