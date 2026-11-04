# Exact request rehearsal and approved live observation

The [capacity driver](SOURCE-CAPACITY-DRIVER.md) has now transported the exact
retained 25,209-byte request through the real Gateway/accounting path with one
mocked HTTPS response. It then verified the same original result without keys
or another send. **This is offline engineering evidence, not a model token
measurement. The separate [actual observation](SOURCE-CAPACITY-RESULTS.md)
subsequently completed with both margins passing, one request and zero held.**

The request hash is `e258ae8166c518ccd8e8a799139e35c7fa609b74fe10fcba0c8c23d1e401a838`.
The parent is recovered as literal data from the retained request's input JSON:
13,455 UTF-8 bytes, source hash `77cfa68f…`, agent identity `22cd302a…`.
Neither that parent nor the returned synthetic source is executed. Historical
feedback still belongs to the older measured parent; the current starter has
not acquired those measurements.

## What the rehearsal establishes

The real HTTP transport receives the exact body and Chat Completions endpoint.
The new original synthetic capacity owner has one settled operation, no held
funds, a complete seal and its authority deactivation anchor. The saved result
replays identically without key entry or HTTPS. A paid-enabled injected
transport is refused during replay. The original fixture remains at its original
paths for inspection; no paid owner is opened for SQL or changed.

The model reply, token counts and resulting recorded cost are supplied fixture
data. They establish accounting and publication behavior only. The benchmark
components are also synthetic; there is no NoveltyBench execution or rescoring.
An earlier rehearsal failed before capacity owner creation because its synthetic
profile wrapper said v1 while containing v2 profile fields. The successful fresh
fixture corrects that wrapper; application code is unchanged. Both records are
retained in the [delivery](conformance/src02-capacity-rehearsal-delivery.json).

## Approved scope and original prelaunch checks: $7, one attempt

The user has approved the [funding proposal](conformance/src02-capacity-funding-proposal.json)
for one OpenAI request under a **$7 total cap and one-attempt limit**, allowing
an explicitly recorded partial result. The [approval record](conformance/src02-capacity-approval.json)
retains that decision; the frozen proposal keeps its original pre-approval status.
It sends the same full
body under the [frozen protocol](SOURCE-CAPACITY-PROTOCOL.md), saves actual usage
and checks for complete changed-source text plus both declared cushions.
It does not execute or adopt returned code or buy generation, judging or search.

The maximum reservation is **$6.315672**, not a prediction of the bill. The
profile reserves the whole 1,050,000-token input ceiling and selected
32,768-token output allowance at conservative rates. This leaves $0.684328 below
the approved cap. No unused balance from an earlier experiment funds this scope;
[API-KEYS.md](API-KEYS.md) records those closed allowances.

The price review on October 23, 2026 uses the official
[model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and
[pricing page](https://developers.openai.com/api/docs/pricing): Standard text
rates start at $2 input/$10 output per million, with long-context multipliers
of 2 for input/cache and 1.5 for output and a possible 10% regional premium.
The [cache guide](https://developers.openai.com/api/docs/guides/prompt-caching)
sets the default 30-minute write rate at 1.25 times uncached input as a total
rate. The resulting upper rates are $5.50 input and $16.50 output per million.
This unchanged Chat body has no extended-cache, tool or nontext option. The
Responses-only 12-hour write rate is outside this request's scope.

Both exact executing-code hosted checks now pass. The dedicated $7/one-attempt
allocation and actual keyless copied-CLI check pass, with an independent
post-funding review and zero owners, attempts, spending or holds at that
checkpoint. The [funded handoff](conformance/src02-capacity-funded-handoff.json)
retains those checks; the earlier unfunded approval checkpoint remains history.
Only an OpenAI key is needed, entered locally; no Anthropic key is involved.
That paragraph describes the prelaunch checkpoint. The [actual result](SOURCE-CAPACITY-RESULTS.md)
is now complete and the allowance is closed for new work. No command is needed
now; [the live guide](SOURCE-CAPACITY-LIVE.md) retains the original handoff.
[PLAN.md](PLAN.md) keeps the separate current-source and scientific gates open.
