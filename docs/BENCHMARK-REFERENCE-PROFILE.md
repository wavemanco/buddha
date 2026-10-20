# Exact reference profile: BENCH-02A

October 20, 2026. This is the request-contract foundation of BENCH-02 in the [living plan](PLAN.md), following [the conformance audit](NOVELTYBENCH-CONFORMANCE.md). BENCH-02 remains incomplete until accounting, parsing, recovery and end-to-end execution gates pass. This slice enables no paid route and changes no historical request, result or authorization.

## Frozen reference

Use NoveltyBench 1.1 at [`64a23be6b18ec1dacc298830aab276061b6e143c`](https://github.com/novelty-bench/novelty-bench/tree/64a23be6b18ec1dacc298830aab276061b6e143c). Select Luna partitioning and Opus quality explicitly, as the README describes; do not inherit the shared bare CLI partition default. Use the live partition/score path, ten ordered answers, null display-order seed and patience 0.8. The quality path's prescribed fallback is `claude-sonnet-5`. A fallback event must be recorded independently even where upstream discards its model identity while returning scores. No private equivalence rule is added.

The pinned [dependency lock](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/uv.lock) hashes to `ff6d5b15b77e4ca46a33604586eb7d99666d2802752ab962af9baa2924a50758`. Its relevant versions are:

| Library | Locked version |
| --- | --- |
| OpenAI | 1.107.0 |
| Anthropic | 1.4.0 |
| Pydantic / core | 2.11.7 / 2.33.2 |
| NumPy / Pandas | 2.2.6 / 2.3.2 |
| HTTPX / HTTPX2 | 0.28.1 / 2.12.0 |

An isolated research environment installed only the required dependency closure, with platform markers applied, binary wheels only and every wheel hash checked against that lock. It leaves the host packages and application's standard-library-only requirements unchanged. It does not install the full upstream training/model-serving stack.

NumPy/Pandas differential checks and all six saved candidate results were repeated successfully under the locked versions. The parser/request probes also pass under the locked SDK/Pydantic versions, confirming the previously reported differences rather than resolving them. [Locked arithmetic evidence](conformance/nb02-locked-scoring.json), [locked parser/request evidence](conformance/nb02-locked-request.json).

## Request bodies and the new constructor

The unchanged selected official `judge()` and `judge_client()` functions ran with real locked SDKs, fake keys and in-memory HTTP transports. Actual provider connections were blocked. Captured JSON and real SDK parsing are preserved in [the fixture](../tests/fixtures/native_judges.json); [the probe](conformance/nb02-wire-probe.py) records no real credentials or headers.

OpenAI's structured parser serializes `stream=false`, an additional detail absent from our earlier constructor-kwargs comparison. It still supplies no explicit output cap, tier or reasoning effort. Anthropic sends its original 16,000-token allowance, high/adaptive effort, fixed system/user text and closed score schema, with no tier. These are JSON-body comparisons, not an assertion that headers or raw serialized byte order are identical.

`buddha.reference.judge_body()` now constructs those captured bodies, reusing the existing pinned prompts/schema. It validates stage/input/fallback arguments, preserves full literal input, returns fresh structures and permits the prescribed quality fallback as an explicit model change. It adds no scoring rule. Five new regression tests first failed on the missing module and now pass, including exact captured-body comparisons and the existing legacy paid guard's continued rejection of these unbound native bodies.

The function returns request data, not an authorized `Call`. BENCH-02B must establish the paid-call contract before dispatch. Constructing a body does not bypass the legacy cap/tier validation or open a live path.

## Remaining BENCH-02 gates

These are contract details for the stable work items in the living plan, not a separate roadmap:

- **B — bounded dispatch and raw evidence:** a new explicit profile, runtime/protocol identity, verified worst-case reservation for omitted caps/tiers, every physical attempt recorded, immutable raw provider evidence and truthful terminal accounting. Keep legacy bodies/fingerprints unchanged. Unknown liability stops dispatch; cached completion never spends again.
- **C — native parsing and evaluation integration:** locked schema semantics, first Anthropic judge text block, original head selection/ordering, native fold retry/repair and score fallback/refusal behavior through the broker. Preserve official result fields and summaries; keep complete-coverage and promotion decisions separate. Reproduce the native functions on normal, malformed, refused, truncated, interrupted and fallback cases before an exact-conformance claim. A later paid semantic control pack still requires its own concrete allocation.

OpenAI currently documents a 128,000-token model maximum, allowing a conservative reservation without inserting a request cap. Omitted service tier means project-selected `auto`, so standard-tier historical rates alone are insufficient evidence for the new profile's maximum price. Verify all applicable limits/rates and the actual account configuration before live work. [Model limits](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [service-tier behavior](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

## Reproduction and dependency notices

The normal regression check runs once in the existing PowerShell window, uses the committed offline fixture, needs no extra packages or keys, and spends nothing:

```powershell
python -m unittest discover -s tests -p test_reference.py
```

It checks request construction only, including rejection by the legacy paid-call interface. It does not judge stories or establish completed native integration.

Optional reference-environment reproduction uses [the hash-pinned research requirements](conformance/nb02-reference-requirements.txt). The first command creates a separate environment under ignored `runs/`; the second downloads/install its locked research packages and needs internet, but no model keys or paid calls. Run them one at a time in the same window and wait for each to finish successfully. Activation is unnecessary.

```powershell
python -m venv runs/reference-env
runs/reference-env/Scripts/python.exe -m pip install --require-hashes --only-binary=:all: -r docs/conformance/nb02-reference-requirements.txt
```

The locked wire probe runs once in that window, uses only in-memory provider responses, reads the hash-verified official source and writes ignored review JSON. It requires the pinned source directory/hash inventory described in the conformance audit; a clean clone alone does not contain those local evidence inputs.

```powershell
runs/reference-env/Scripts/python.exe docs/conformance/nb02-wire-probe.py
```

The existing two historical probes in the conformance audit can also run under this environment's Python, given the original local pilot evidence. Their committed locked-version results are linked above.

[Dependency-license evidence](conformance/nb02-reference-licenses.json) records package versions and primary metadata URLs. Certifi is MPL-2.0, already a development-tool dependency; tqdm offers MIT/MPL licensing. NumPy's license includes GNU runtime notices for relevant bundled distributions (GPL with GCC runtime exception and LGPL libquadmath). These are isolated research dependencies, not added application dependencies or redistributed binaries. Resolve exact platform/distribution obligations before any future distribution. No HyperAgents implementation or prompts are used.

Local delivery verification passed 392 tests in 102.587 seconds (one host symlink-privilege skip), including five request-contract regressions; Ruff, strict mypy across 17 runtime modules, Bandit, runtime dependency audit, compilation and whitespace checks pass. All 287 protected input hashes remain unchanged. [Delivery evidence](conformance/nb02a-delivery.json). Hosted CI is reported separately after publication.
