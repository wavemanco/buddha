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

## Current-source checkpoint: November 2, 2026

The [fresh-comparison verification](conformance/fresh-comparison-checkpoint.json)
records 57 passing existing checks at published source `1daf9b6` (the same
application code as PR #213). The four cohorts cover required request settings,
official reference bodies, native SDK transport and HTTP usage/response handling.
They use dummy keys and simulated provider connections. All 358 bound source
and fixture hashes match afterward; no real API request or Docker run occurred.

This confirms the current helper behavior, including configurable low-effort
generation and the distinct judge settings above. It does not certify a future
experiment's prepared profiles, selected source requests, runtime, provider
accounts or model availability. Those exact inputs must be checked before the
fresh live handoff. The existing command above remains an optional local check;
no new user command or API key is needed for this checkpoint.

## Prepared-profile checkpoint: November 2, 2026

The fresh preparation's actual profile file and both plain-model configurations
pass a separate, no-cost compatibility check. Seven synthetic request bodies
are accepted; all 27 deliberately incorrect variants are rejected. Independent
sampling ignores the supplied history; in-context sampling preserves it,
including an empty earlier answer. Both controls bind the expected profile
file and the same public fixed-seed source.

The Luna and Opus judge bodies match the pinned public SDK-capture fixture.
The explicit Sonnet body changes only Opus's model field. These preserve
Luna's omitted overrides and the utility judges' adaptive HIGH effort and
16,000-token allowance. The code-authoring profile is inspected separately: it does not
require generation's LOW effort, and no authoring request is produced here.
[Exact evidence and limits](conformance/fresh-request-profile-delivery.json).

This closes prepared-profile compatibility only. It does not execute P/C,
the installed native SDK or the refusal-only fallback trigger, and it checks
no account, price, capacity or live readiness. Earlier simulated HTTP tests
retain their separate scope. Exact outgoing behavior must still be checked
before a paid handoff.

No action is needed from the operator. For developers, this optional command
replays the diagnostic once against the recorded local preparation:

```powershell
python -I -B C:\Users\arvik\code\buddha\runs\reviews\fresh-request-profile-check\docs\conformance\check-fresh-request-profiles.py
```

It needs the named local files with their recorded fingerprints. It reads five
configuration files and one public fixture, prints a JSON result, and changes
no run files. It needs no keys or Docker and spends no API money. Use the
current PowerShell window; Ctrl+C stops it. The direct command has no enforced
time limit; the saved observation took 0.364 seconds under a 120-second limit.
This is a check of this frozen preparation, not a generic check for other runs.

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
