# Proposed cost envelope for the policy comparison

This is a reviewable proposal, not spending permission, an activated profile
or a live-run command. [The study protocol](POLICY-COMPARISON.md) fixes twelve
development prompts, four conditions, two generation repetitions and two full
judging occasions. [PLAN.md](PLAN.md) remains the roadmap.

Propose a **new shared $50 USD cap and 4,096 physical attempt records** for
generation and native grouping/quality only, with a truthful partial result if
either limit or another safety guard stops execution. The old $50 experiment
and $15 judge audit are closed and cannot supply this allocation. No proposal
search, policy mutation, source evolution, held-out assessment or leaderboard
submission is included. Final-evaluation allocation is zero for this
development-only scope; future final evaluation needs its own authorization.

## Why this is a proposal rather than a completion quote

At twelve prompts, the normal single-attempt path has:

| Work | Count |
| --- | --- |
| Generation | 960 calls: 96 ten-answer sets |
| Grouping | 192 calls: every set assessed twice |
| Quality | Up to 1,920 calls if all ten answers form separate groups |
| Normal-path upper total | 3,072, before native repair, retries or fallback |

The 4,096-attempt ceiling leaves some recovery room, not a guarantee of covering
every possible native fallback. Every actual attempt counts through the shared
authority. Local summaries make no provider calls. Supplemental Codex review
uses separately disclosed host subscription usage, not this API allocation.

The major unknown is quality judging: the number of groups and adaptive
thinking/output tokens. For illustration, at 2–10 groups per set, 1,000 input
tokens and 100–500 total output tokens per quality call, ordinary Opus pricing
gives **$2.88–$33.60 for quality alone**. If instead all ten groups require
1,000 output tokens per call, that subtotal is $57.60. These are arithmetic
scenarios, not measurements or a forecast. Generation, grouping, retry/fallback
and any applicable account charges are additional. The earlier $0.30 pilot
and $0.032213 grouping-only audit cannot predict this different workload.

## Price and reservation assumptions

Vendor documentation was checked October 21, 2026. Public ordinary input/output
prices per million tokens are $0.20/$1.20 for the exact pinned
[GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
$5/$25 for [Claude Opus 5](https://platform.claude.com/docs/en/models/opus-5/overview)
and $2/$10 for its prescribed
[Sonnet 5 fallback](https://platform.claude.com/docs/en/models/sonnet-5/overview).
The OpenAI page also documents larger-context and cache-write multipliers;
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
lists cache-write rates separately. Exact profile ceilings must include all
applicable charges. Newer model names are not permission to change the judge.

The current broker reserves against documented model context capacity, not a
host estimate of the actual prompt's tokens. It also preserves the official
grouping request's omitted output cap, reserving the documented maximum rather
than inserting a private cheaper cap. Illustrative conservative profiles would
reserve about $0.532373 per generation call, $0.755400 per grouping call and
$10.400000 per Opus quality call. These are temporarily held maxima, not charges
or measured estimates. They must be reverified and bound into the actual
account-reviewed profiles before live preparation.

Consequently a $50 cap may stop at roughly $39.60 already spent when the next
quality call needs a $10.40 reservation. The current native channel serializes
provider exchanges even while two native prompt instances are active.
Unused capacity is not evidence that the guard should be bypassed. A local
native owner also needs a ceiling large enough for one prescribed request;
small per-owner ceilings cannot be justified by historically cheap replies.
The shared cap covers all owners together; local ceilings are not additive
permission to spend their sum.

OpenAI standard/default processing and public pay-as-you-go pricing were
previously confirmed by the user. The user separately confirmed the same
Anthropic account terms on October 21, 2026. Both models' actual access and the
credential-to-reviewed-project join still need checking through the protected
local handoff. Documentation is not account or invoice evidence. Keys are entered
locally, never in chat, committed files or review artifacts. The cap governs
the declared provider API usage under the reviewed pricing contract; taxes,
foreign-exchange charges and subscription usage are reported separately.

## Stops, records and the eventual handoff

The existing shared authority must stop on insufficient money, attempt count,
unknown liability, overrun, invalid bindings or failed worker/protocol checks.
An uncertain provider completion retains its reservation and original identity;
it does not trigger an automatic fresh replacement. No timeout proves that an
external call was unbilled.

A stopped study must record **incomplete**, its literal reason, completed/missing
coverage, known spending, held uncertainty and original child paths. It cannot
declare a winning condition from a partial schedule. Recovery retains original
owners and already received replies. Funding approval does not authorize a
second experiment, extra judging occasions or automatic cap increases.

Before asking the user to run anything, prepare and test the exact configuration,
runtime/profile/account joins, attempt and wall-clock limits, preflight,
key-entry flow, progress output, partial reporting and later passive analysis
against the committed protocol. Pin the reviewed intent and source digests in
that handoff; do not treat jointly rewritten self-consistent files as the
original registration. Show the concrete approved cap and one clear command.
No such live command or new authority is created by this proposal.
