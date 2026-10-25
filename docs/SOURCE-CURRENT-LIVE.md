# Current-source live experiment

This is the approved code-evolution observation for SRC-02/03. The protocol and
review criteria are adopted, current Windows/Linux CI passes, and the funded
handoff is ready for the user to start locally. No model calls were made during
preparation.
[PLAN.md](PLAN.md) remains the current roadmap.

The earlier $7 observation checked whether one exact full-output request could
return a complete source proposal with enough space left. This experiment
measures the current parent itself and runs its model-written descendants.
The [corrected preparation record](conformance/src02-corrected-live-preparation.json)
retains an earlier unfunded checkpoint. Current readiness is described below.

The [earlier preparation](conformance/src02-actual-live-preparation.json) used a
producer that later failed three legacy progress-report compatibility checks in
Ubuntu CI. The [shared correction](SOURCE-PROPOSAL-CAPACITY.md#record-compatibility)
was delivered with a separate bundle pinned to corrected executing code. The original
bundle and failed-head evidence remain unchanged and unfunded. The adopted
protocol, criteria and intent retain their original bytes; this preparation
changes no scientific acceptance or benchmark rule.

## Run the approved experiment

Open a fresh PowerShell window and run this one command. No `cd` command is
needed because every path is absolute. Keep Docker Desktop running.

```powershell
python C:\Users\arvik\code\buddha\runs\reviews\ci-test-progress\docs\conformance\src02-run.py --handoff C:\Users\arvik\code\buddha\runs\src02-current-live-20261024-handoff-v1\launch.json --sha256 3a4186127d30ccf8a69cea65cfcc2ed5651661f14e3892f5ab5646c625a2c65d --receipt C:\Users\arvik\code\buddha\runs\src02-current-live-20261024-receipts-v1\launch-001.json --live --prompt-keys --confirm-project-keys
```

This runs the original experiment once and may spend up to the approved **$25
combined OpenAI/Anthropic cap**, with at most **512 recorded attempts**. It asks
for both API keys locally if they are not already set. Paste each key and press
Enter; hidden input is normal. Never paste keys into chat or a repository file.

The command checks the approved handoff and its fingerprint, saves this
invocation result at the named receipt path, and enables the paid run. The last
flag confirms that these keys belong to the previously attested Standard/default,
public pay-as-you-go projects. A spending record does not add credit to either
provider account.

Use this same window while it runs; a second window is not required. Progress
messages continue while provider calls or container startup take time. Ctrl+C
stops the run; an unresolved request can retain a budget hold. Partial work
keeps its stage, reason, recorded costs and unresolved holds. Run this first
invocation command once. If it stops, keep the files and share the terminal
output before choosing a continuation receipt.

After it finishes, tell Codex the run is complete and share the final terminal
output. Codex will inspect the saved records, assess actual source changes and
update the plan. Source-change evidence and official development scores remain
separate from later held-out improvement claims.

[Prepared handoff and verification](conformance/src02-current-funded-handoff.json).

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

The user approved a **$25 combined cap and 512-attempt limit**, with explicit
partial results allowed. Its dedicated spending record is prepared and starts
with zero spent, held or attempted. Earlier
allowances cover closed experiments and cannot fund this one. The amount is
a maximum, not a spending target or completion estimate. Conservative
reservations can stop work before the cap is spent; unresolved requests retain
their holds.

OpenAI serves generation, source proposals and official grouping. Anthropic
serves official quality scoring and its fallback. The approved local launch
therefore needs both keys. Keys are entered locally and are never part of
these committed protocol files.

## Current handoff status

The fresh bundle is `runs/src02-current-live-20261024-proposal-v3`, prepared
from the exact CI-tested producer `42e5dd2d3d32c1f085c87aaa2de44cc1391587ce`.
All 44 required live helper files match that commit. Its 43 files and 170 source
hashes pass the saved-data reconstruction; the earlier 169-file map is intact.
Tasks, starting program, proposal instructions, supported policies, official
NoveltyBench 1.1 instrument, comparison key and approved terms are unchanged.

The dedicated handoff lives at `runs/src02-current-live-20261024-handoff-v1`.
At preparation it contains no account-key review or study owners, and records
zero attempts, spend and holds. The 77 fixed bindings become 78 with the future
keyed review; the first invocation projects 85 input paths. The existing 111+K
declared-flow bound has K=0 here and remains conditional, not a measured full
owner census. The user launch creates the original search and its owners.

All eight [hosted jobs](https://github.com/wavemanco/buddha/actions/runs/40123333122)
passed: 1,840 tests per OS, with five explicit Linux skips and one Windows skip,
plus every configured quality check. Both required local images are present
and match their declared configuration.

The final public-rate check retains the same conservative profiles, using
[OpenAI Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[OpenAI Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[Claude Opus 5](https://platform.claude.com/docs/en/models/opus-5/overview) and
[Claude Sonnet 5](https://platform.claude.com/docs/en/models/sonnet-5/overview)
documentation. It does not query project access, balances or invoices.

## Earlier preparation checkpoints (historical)

The fresh bundle is `runs/src02-current-live-20261024-proposal-v2`, prepared
from corrected producer `87c041b207d54305ba30621bbf4b6b935d7d19b2`. It remains
separate from the earlier bundle and supplied-response rehearsal. It retains
the adopted protocol, unchanged starting agent, official evaluator and host
profiles, with freshly selected current runners and source handoff v4.

The saved bundle has forty-three files. Its source map has 169 checked hashes;
all 167 bindings from the previous map remain unchanged. The passive check binds
seventy-one controls plus the proposal itself. Independent saved-data review
confirms the configuration and all six expected preparation guard outcomes,
with no unexpected event. Preparation created no original owners or databases
and made no provider call. These are trusted preparation checks, not a general
security claim or an observation of the planned twenty-nine-owner execution.

The refreshed input review retains the conditional `111+K` bound, including permitted
empty database sidecars; `K` counts additional distinct final bindings beyond
the new minimum seventy-seven. The three price-evidence additions are already
included in that minimum. This is a calculation under the declared flow, not
an observed invocation count. The final funded launch must reconcile its actual
input union against the existing limit before use.

The [refreshed proposed launch bindings](conformance/src02-refreshed-launch-bindings.json)
give this experiment concrete future destinations. They remain inside a separate
unfunded draft; they are not an approval or a runnable handoff.

| Proposed location under `runs/` | Purpose |
| --- | --- |
| `src02-current-live-20261024-run-v1/` | The original experiment's generated answers, child programs, results and accounting owners |
| `src02-current-live-20261024-handoff-v1/` | The future approved launch, dedicated spending record and key-bound account review |
| `src02-current-live-20261024-receipts-v1/launch-001.json` | The first launcher invocation's outcome, including an explicit stop or partial result |

Those destinations have not been created. The draft fixes the proposed authority
identity, account statement, three-hundred-second request timeout and exact
approval/launch bytes. Its minimum fixed input union contains seventy-four
distinct paths in the preserved earlier draft v2. The new draft v3 adds three
price-evidence bindings, giving seventy-seven fixed paths. The later account
review makes seventy-eight and is already included in the conditional maximum
of 111. Adding another distinct pinned support file changes `K` and requires
reconciliation. The [earlier draft record](conformance/src02-unfunded-launch-bindings.json)
and its 74/108 calculation remain unchanged.

The account statement retains the user's existing Standard/default processing
and public pay-as-you-go attestations for both providers. It does not verify
provider access or current prices. Actual key fingerprints and the dated account
review are created locally only after funding and key entry; the draft contains
neither. The draft cannot spend money or start an agent.

The selected executing head's original Ubuntu check has now finished with one
read-count assertion failure among 1,789 tests; its
[terminal checkpoint](conformance/src02-unfunded-launch-bindings.json) retains
the original log. Windows is still running at that checkpoint. The [test-only follow-through](conformance/imp01-shared-replay-expectation-delivery.json)
now reproduces that failure and corrects its expected count and message. Sixteen
related checks and seven quality checks pass locally. The executing code and
frozen experiment inputs are unchanged; fresh hosted verification is pending.

No live command is available at this checkpoint. Remaining checks include the
final launch bindings and actual input union, the exact selected executing
code's hosted CI, applicable account/pricing conditions, and a separately
approved allocation. The dated public-price and supported-request evidence is
retained; this preparation does not recertify prices, authenticate keys or
verify account settings. A later funded handoff will document the exact command,
its function and expected output before asking the user to run anything.

Interrupted work may continue only through supported recovery of the original
owners and frozen requests. Known completed replies are reused without another
provider call. Unknown liabilities stay unresolved. There is no replacement
owner, adaptive source repair or extra iteration to manufacture a positive
outcome.

The adopted protocol files retain their preparation-time statements and hashes.
Later preparation, funding and results require separate records; they do not
rewrite those files or the earlier supplied-response rehearsal.

Exact corrected PR #116 now passes all 1,804 tests and configured quality steps
on Ubuntu, with zero failures, zero errors and five explicit skips. At the
October 24, 2026 13:40:26 UTC checkpoint its Windows job is still running. The
[retained CI evidence](conformance/imp01-larger-reader-cost-observation.json)
does not establish a complete platform matrix or grant spending permission.

### Public price evidence at the earlier checkpoint

The October 24 [price refresh](conformance/imp01-larger-reader-cost-observation.json)
and independent review confirm the stored bounds for all five model roles.
Profiles and model IDs remain unchanged. This checks public documentation and
the accepted request features; account access and actual combined request fit
remain separate checks.

The existing launcher accepts the three additional support pins without a code
or proposal-bundle change. The [saved draft v3](conformance/src02-refreshed-launch-bindings.json)
now binds the refresh record, its independent review and its preparation recipe.
The original data-only preparation completed in 34.670 seconds. Independent
saved-data review checks the exact additions, new launch hash, unchanged approval,
all 181 protected inputs and the original forty-three-file bundle. The proposed
run, handoff and receipt folders remain absent.

The fixed input union is now 77 paths, or 78 with the future key-bound review;
the conditional maximum is 111, including permitted empty sidecars. These are
still calculations, not an observed twenty-nine-owner invocation. The future
account review must bind the new launch hash; the real funded input union must
still be reconciled. No actual launch, approval, funding or user command was
created.

A separate read-only Docker check confirms both pinned images meet the selected
executor's image-identity requirements. An earlier diagnostic formatter failed;
the direct inspection succeeds and reproducing that formatter gives the same
error. Both outcomes are retained in the new record. Image identity alone does
not verify worker execution, account access, request capacity or live readiness.
