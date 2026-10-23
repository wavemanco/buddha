# Full-output starter request: measured bytes and remaining token check

The prospective starter request contains all 30 original seed answers and is
25,209 UTF-8 bytes. Its complete callback frame is 33,681 bytes. Both fit the
existing byte limits. **Model token fit and output headroom remain unverified.**
This check does not authorize another run or require a user command.

## What this check represents

The passive [full-output builder](SOURCE-FEEDBACK.md) verified the completed
historical seed screen and rebuilt its three ordered development notes. It
preserved every answer, with zero omitted answer positions or bytes. The story
note is 4,769 UTF-8 bytes, above the historical 4,096-byte note ceiling; the other
notes are 849 and 672 bytes. The selected tasks remain `curated-0`, `curated-47`
and `curated-97`, with ten answers each.

The driver then manually reconstructed the fixed trusted starter-v2 payload and
prompt and called the existing trusted `agents.frozen_seed.request` constructor.
It did not execute the composed `propose_improvement` function or compile or
execute mutable candidate source. This establishes a request projection, not
end-to-end improver execution.

The parent in this projection is the current trusted starter v2; the measurements
come from the [first experiment's](SOURCE-FIRST-LIVE-RESULTS.md) older starter.
Their source identities differ. Recombining them for a capacity check does not
make the new starter a measured parent, upgrade original-owner custody, or
change the historical run and its limited feedback.

## Exact serialized sizes

These are byte lengths of the identified serializations, not token counts or
additive pieces of one total. JSON escaping and base64 framing affect the sizes.
The [delivery record](conformance/src02-source-request-capacity-delivery.json)
retains every corresponding SHA256.

| Measured value | Bytes |
| --- | ---: |
| Detached host bundle, including host-only source/split/provenance | 153,749 |
| Canonical full-output feedback packet | 7,270 |
| Escaped ordered task-and-note projection | 6,998 |
| Current complete parent source | 13,455 |
| Starter payload containing parent and feedback | 21,434 |
| Prompt including the fixed instructions and payload | 23,068 |
| Complete Chat Completions JSON body | 25,209 |
| Callback JSON frame, including base64 body and final newline | 33,681 |

The body requests OpenAI `gpt-6.1-sol`, `max_completion_tokens=32768`, low
reasoning effort and the default tier. The starter configuration uses regenerate
sampling and empty additional instructions. The request has one user message;
the complete host dataset, split and provenance are excluded from that message.
The original profile's 1,050,000 input ceiling is a financial reservation bound,
not a measurement of this request's tokens.

## Preservation and observation limits

Projection v2 completed at its recorded source cut in an 8.4103-second measured
span after preflight. All 941 pinned inputs stayed unchanged. Before/after file
name, size and content-hash inventories cover 606 original run files, seven
handoff files and 38 proposal-bundle files: 651 files across those roots. The 56
original frozen source pins also stayed unchanged; these sets overlap and are
not additional independent file populations. The projection-phase read audit
recorded 25 distinct original artifact paths. Pin and preservation hashing made
additional reads; 941 is not the number of artifacts consumed by the builder.

The projection made zero model operations, provider calls, worker launches or
file-backed SQL connections and read no API keys. Its passive readers used 70
memory connections and 68 controlled main-memory deserializations. Within the
projection process, the only permitted write was a new result receipt; the
launcher separately wrote fresh process/stdout/stderr/exit evidence. No packet,
owner or grant was created, and no original artifact was written.

V1 stopped at an absent redirected `.pyc` lookup before feedback/request
construction. That refusal remains retained. V2 admits only absent `.pyc`
lookups beneath the caller's fresh redirected cache prefix. It admitted 61 such
lookups and left the prefix absent. Its guard continued to forbid reading existing unpinned cache content.
This was an observer-guard correction, not a change to the agent or benchmark.

## What must still be checked

OpenAI's [model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
checked October 23, 2026, lists a 1,050,000-token context window and 128,000 maximum
output tokens. Those published limits do not count this request. The chosen
32,768 cap remains unchanged.

The [token-counting guide](https://developers.openai.com/api/docs/guides/token-counting)
describes a count endpoint for Responses inputs, including structural formatting
tokens. This request uses Chat Completions. A Responses count must not be treated
as an exact count of this unchanged Chat request without separately established
parity. No tokenizer was used here; `tiktoken` was unavailable in the reviewed
environment. No byte-to-token conversion is asserted.

The [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
defines `max_completion_tokens` to include visible output and reasoning tokens.
Consequently 32,768 is not a promise of 32,768 visible code tokens, or of a
complete replacement file at the permitted 1 MiB source ceiling.

The remaining gate is narrow: establish a supported model-specific count or
clearly bounded measurement for the actual endpoint and complete request, then
check context and a declared output margin for the full replacement-source JSON.
Repeat that assessment when parent source, full feedback or request logic
changes. This one small request cannot certify future requests. Token fit,
output completeness, local model/account access and any future funding stay
separate pending checks; no benchmark re-audit or new allocation follows here.
