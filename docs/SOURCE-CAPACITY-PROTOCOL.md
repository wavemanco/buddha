# One complete proposal request: frozen capacity protocol

This SRC-02 protocol was frozen before implementation or observation. The
[narrow driver](SOURCE-CAPACITY-DRIVER.md) is now implemented and checked offline;
**there is no funded handoff or live observation yet**. The machine-readable
record retains its original freeze-time status. [PLAN.md](PLAN.md) owns the roadmap.

## The question

Can the exact [projected starter request](SOURCE-REQUEST-CAPACITY.md), containing
all 30 historical answers, return a complete replacement-source proposal with
space left in its response allowance? This measures one request. It does not
test NoveltyBench again or establish improved answers.

Reuse one ordinary funded Gateway call. A new tokenizer, API migration,
benchmark evaluator or source-execution mechanism is unnecessary for this
measurement. The [frozen machine-readable protocol](conformance/src02-capacity-protocol.json)
names the exact body, distinct source identities and acceptance examples.

The body is already retained in the projection receipt. It is 25,209 UTF-8 bytes,
SHA256 `e258ae8166c518ccd8e8a799139e35c7fa609b74fe10fcba0c8c23d1e401a838`.
Send those literal bytes to OpenAI Chat Completions, using `gpt-6.1-sol`, low
reasoning effort, the default tier and `max_completion_tokens=32768`.
Do not reconstruct or shorten the prompt at launch.

## Keep the original results honest

The feedback describes the historical starter `b54a8e60…`; the projected
full-output starter is `22cd302a…`. They differ. This is an explicitly prospective
combination for capacity measurement. It is not a newly measured parent or a
proposal publication of the measured-feedback stage.

The existing `candidate_improvement` wrapper correctly rejects that mismatch.
Keep its check. The raw Gateway route can measure this exact body without
executing either agent, inventing measurements or weakening provenance.
The returned source stays data: do not execute, screen, select or adopt it.

## Count the actual request and leave a declared margin

The official [counting guide](https://developers.openai.com/api/docs/guides/token-counting)
documents a Responses input-count endpoint. It does not establish that a
Responses count equals this unchanged Chat request. It also explains that total
completion usage includes non-visible tokens, with no fixed difference from
visible text. This protocol therefore uses the actual Chat reply's aggregate
usage rather than a visible-text estimate.

The [model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol), checked
October 23, 2026, gives a 1,050,000-token context window and a 128,000-token maximum
output. Retain the smaller selected response cap of 32,768. Freeze two engineering
cushions at **8,192 tokens each**:

- Context cushion: `1,050,000 - prompt_tokens - 32,768 >= 8,192`.
- Observed response cushion: `32,768 - completion_tokens >= 8,192`.

The first reserves room for the entire selected response allowance, not just the
response that happened to be short. The second leaves 25% of that allowance
unused on this occasion. These are declared engineering choices, not statistical
thresholds or a guarantee about future requests.

Inclusive completion usage is authoritative for this calculation; optional
reasoning-token details remain available in the raw reply but are not subtracted
again. Do not count code characters or visible tokens as the total allowance.

## A positive result needs all of these

1. One exact-body request with the fixed endpoint, model, tier and cap, attributable
   to its original owner and actual raw receipt. The call-time guard must reject
   changed bytes or request identity **before** `Gateway.execute` can reserve funds.
2. Complete successful HTTP evidence, the expected provider/model/tier, a provider
   request ID and unambiguous inclusive input/output usage within the frozen profile.
3. Exactly one choice, normal `stop`, no refusal, and the complete strict finite
   JSON object containing only `source` and `hypothesis`. The
   [Chat reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
   distinguishes a normal stop from the output-limit finish reason.
4. Reuse the existing bounded source-proposal validator: nonempty UTF-8 replacement
   source of at most 1 MiB, a nonblank hypothesis of at most 4,096 bytes, and source
   different from the pinned parent. No repair, prefix acceptance or code execution.
5. Both declared cushions pass, with the actual counts and arithmetic saved.

Even this result establishes only complete structured replacement text. It does
not prove valid Python, callable entry points, preservation of functionality,
semantic completeness or mutation competence. Those belong to the actual
isolated source loop.

## Save failures without hiding the usable evidence

Record execution and measurement separately:

| Observed outcome | Measurement record |
| --- | --- |
| Complete changed proposal; both cushions pass | Complete measurement, observed-capacity pass. |
| Complete changed proposal; either cushion fails | Complete measurement, observed-capacity fail. Keep the counts and source text. This is a negative result, not missing data. |
| Output-limit finish, refusal, invalid/incomplete JSON, unchanged or out-of-contract source | Partial measurement, unavailable capacity decision and a specific reason/stage. Preserve raw reply, available usage, costs and failed proposal text. |
| Budget stop, unavailable/uncertain provider evidence or interruption | Partial measurement with reason/stage and original accounting/hold state. Do not infer that a request was unsent. |

A valid billed response may therefore have a partial measurement: billing
completion is not proposal acceptance. Completed evidence and negative outcomes
remain immutable. A partial result must say what is missing; a successful model
call alone cannot become a passing capacity result.

Use one fixed logical identity and attempt. No automatic transmission retry,
fallback, replacement owner, prompt repair or cap increase. An unresolved request
keeps its original hold. Any permissible known-unsent continuation uses that same
operation and authorization; completed replay adds no call or key prompt.

## Implementation and approval boundary

The next implementation is a small frozen-request driver using existing Gateway,
hidden-key entry, raw usage parsing and anchored stage publication. Its focused
checks must cover byte/endpoint drift before spending; margin boundaries;
malformed/refused/truncated replies; original-owner interruption and replay;
unknown holds; and preservation of original artifacts. Rehearse it offline before
asking for a new allocation. Do not create a generic counting framework.

The historical profile reserves $6.315672 for its full input ceiling and selected
output cap at its pinned upper rates. That is retained-profile arithmetic, not a
new allowance, current-price certification or expected bill. Bind a freshly
reviewed profile/account scope and a separate approved one-attempt allocation
before any live command. Only an OpenAI inference key is needed for this check;
no generation, quality judging or Anthropic request is included.

Changing parent source, feedback, request construction, model or cap creates a
different capacity case. Recheck it or retain its capacity failure explicitly.
This one observation cannot guarantee that every permitted 1 MiB replacement or
future full-feedback packet fits. Existing byte guards continue to stop instead
of truncating; no old run, seal or financial scope is reopened.
