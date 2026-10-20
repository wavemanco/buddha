# Frozen seed generation recipe

BENCH-02C3C1 moves the existing seed generation procedure into
`agents/frozen_seed.py`, a standalone standard-library module. It contains no
NoveltyBench version, judge prompt, SDK, credential reader, network sender or
accounting import. This is a pure recipe boundary; isolated execution and the
complete official pipeline remain separate gates in [the plan](PLAN.md).

The first baseline treatment remains empty instructions with independent
`regenerate` sampling. The same implementation also preserves the existing
`in-context` mode, in which previous effective answers accompany the next
request. The requested count is task data; counts two and ten use the same
code. Supporting a mode does not automatically add another experiment arm.

## Interface

| Function | Purpose |
| --- | --- |
| `request(config, task, previous=())` | Return the exact UTF-8 JSON request bytes for one answer. It sends nothing. |
| `normalize(provider, response)` | Extract one effective answer from parsed provider JSON using the frozen legacy recipe. Malformed responses fail explicitly. |
| `generate(task, config, complete)` | Request `task.count` ordered answers through a supplied `complete(provider, body)` callback. The callback returns parsed provider JSON; it must be supplied by the trusted funded controller for actual execution. |

Configuration has exactly `provider`, `model`, `max_output_tokens`,
`instructions` and `sampling`. A sanitized task has exactly `id`, `prompt` and
`count`. The seed receives no dataset, judge configuration or benchmark paths.
The later controller must freeze these inputs and retain raw provider evidence
before normalization; this module supplies no authorization by itself.

Legacy request fields, Unicode serialization, the continuation message and
Anthropic cache marker are preserved. Literal whitespace, duplicate or poor
answers, and accepted truncation remain answers. The recipe deliberately maps
empty text to `[empty]` and refusal to `[refused]`; those effective strings are
not the original response. Raw evidence and the recorded normalization identity
must keep that distinction. Unsupported completion states and malformed outer
provider responses are generation failures, never replacement empty answers.

The command below checks the recipe against the actual legacy generation and
reply parser, including both providers and existing sampling modes. It runs
once in the current PowerShell window, creates only temporary test fixtures,
needs no Docker or API keys and spends nothing. Ctrl+C stops it.

```powershell
python -m unittest discover -s tests -p test_frozen_seed.py
```

These differential checks cover valid request/answer behavior and stricter
malformed-input rejection. They do not establish provider availability,
isolation, complete native evaluation, meaningful diversity or improvement.
Callbacks run sequentially, with no automatic retry; callback or parsing failures
escape to the host. Blank prompts retain the original seed's rejection behavior.
C1 still preserves those task bytes; a failed seed must be recorded as a failure
rather than silently dropping the task or inventing an answer. The original
generation implementation and historical receipts remain frozen.

[Delivery evidence](conformance/nb02c3c1-delivery.json) records the tests,
source seals, quality checks and preserved historical inputs.
