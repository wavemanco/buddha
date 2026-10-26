# Checking model requests before spending

The host selects the generator model. Luna is the current proposed choice, not
a restriction on Buddha. Current paid routes support compatible OpenAI and
Anthropic models. Model compatibility and verified prices still need checking
when a model changes. Reasoning support is declared in the host's profile; it is
not guessed from a model name.

For new reasoning-generation preparations, use **low effort by default**. The
trusted starter already requests low. A new `buddha.gateway-profiles.v3` profile
can require that every outgoing request keeps it. An evolved agent that omits
or changes a required setting stops before reservation, key access or sending.
The host checks the request; it does not silently rewrite it. Existing v1/v2
profiles and historical runs keep their original behavior.

For the current OpenAI reasoning generator, the additional profile field is:

```json
"request_settings": {
  "required": {"reasoning_effort": "low", "max_completion_tokens": 4096},
  "forbidden": ["temperature", "top_p", "max_tokens"]
}
```

The model remains in the existing profile's `spec.model`. For a compatible
Anthropic reasoning generator, require `max_tokens: 4096`, adaptive `thinking`
and `output_config: {"effort": "low"}`, and forbid temperature/top-p overrides.
These are settings for generation, not for the improver's code-authoring calls.
Changing a frozen experiment's model or settings needs a new preparation.

The profile checks literal top-level fields and omissions. Required objects
match in full; extra nested fields also fail. Profile settings are bound into
the selected inputs, original owner and request identity. The feature contains
no NoveltyBench model names or judge rules: those remain versioned configuration.

## Official NoveltyBench 1.1 judges

Keep the official native evaluation route and its pinned source:

| Role | Outgoing settings |
| --- | --- |
| Distinctiveness | `gpt-5.6-luna`; official prompt and structured schema; effort, output cap and temperature omitted |
| Utility | `claude-opus-5`; adaptive thinking, high effort, 16,000 tokens and official structured schema |
| Utility refusal fallback | `claude-sonnet-5`; the same utility settings |

The OpenAI SDK serializes `stream: false` as well. An omitted effort uses the
provider's default; it does not mean reasoning is disabled. Do not apply the
generator's low setting to judges. The older `run.py` judge route adds settings
and is not the publication-compatible native route used by this preparation.

The official [generation helper](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/inference.py#L46-L58)
doubles its CLI 2,048 allowance for reasoning generation, producing 4,096 on
the wire. The [judge helper](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/judge.py#L66-L107)
constructs the different judge settings above. Buddha's explicit standard
processing tiers and the starter's Anthropic cache breakpoint are separately
recorded; matching reasoning settings is not a claim that every generation
request byte equals upstream's.

## Run the no-cost checks

From the checkout containing this slice, in your current PowerShell window:

```powershell
python -m unittest discover -s tests -p "test_*request_settings.py" -v
```

This runs once and checks the real session, accounting and HTTP construction
with synthetic data, dummy keys and fake HTTPS connections. It needs no API
key, makes no provider calls and spends no API money. It creates temporary test
files and removes them afterward. Wait for `OK`; Ctrl+C stops it. It checks
the current code, not your account or a newly selected model's compatibility.

The [delivery record](conformance/imp01-request-settings-delivery.json) separately
records the actual selected P/C first-request observations inside the pinned
sandbox. They used synthetic task/reply data and copied source bytes without
editing them. These observations are not complete generation runs, later-call
proofs, quality measurements or scientific results. Before a live handoff,
recheck the exact prepared profiles, selected sources, worker/host code, model
compatibility, official evaluator, accounts, capacity and spending authority.

## What the next comparison measures

Using Luna inside Buddha is different from a plain Luna control. The prepared
IMP-01 study compares the initial and evolved **Buddha improvers** under matched
conditions. Its starter controls still use Buddha, so that study alone cannot
measure the harness's added value over the underlying model.

The EVAL-02 harness comparison also needs plain-model independent sampling and
plain-model in-context sampling, matched to Buddha by generator, tasks,
reasoning settings and declared inference resources. The plain model receives
the task and only the sampling protocol's necessary continuation messages;
it receives no Buddha instructions, planning, improvement loop or answer
selection. Administrative logging and the fixed official evaluator can be
shared. Report generation cost and total search/research cost separately.
Prepare and cost those controls prospectively; do not add them silently to an
existing frozen workload or treat an improver comparison as their substitute.
