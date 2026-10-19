# Buddha

Build agents that improve their own procedures for producing useful, meaningfully different answers on NoveltyBench.

**Start with [the consolidated living plan](docs/PLAN.md)** for the complete original objective, completed work, new findings, dependencies and the next slice. It is the sole current roadmap; design and review documents supply specifications and evidence.

Git history and slice PRs are maintained in [wavemanco/buddha](https://github.com/wavemanco/buddha). The initial commit preserves the existing slices together; subsequent changes use separate slice branches. [REC-01's recovery contract](docs/RECOVERY-CONTRACT.md) and sealed historical reader establish the next recovery boundary; linked continuation is not yet executable.

**Slice 3 is implemented and its live pilot is complete:** bounded policy optimization with a fixed proposer, candidate archive, shared spending ledger and common development screen, alongside the existing v1.1 baseline runner. The recovery pilot completed 63 calls for $0.300153 in recorded conservative cost; its child scored higher on one development prompt. This is exploratory evidence, not a held-out improvement claim. See [the completed results and limitations](docs/FIRST-LIVE-RESULTS.md). Generated-source self-modification remains a later slice.

The [pilot concern review](docs/PILOT-REVIEW.md) records repeated plots, effects on both metrics and operational gaps. Its recommendations are incorporated into the living plan. Matching runtime/test source is now preserved. Meaningful diversity has not been validated; benchmark scores remain unchanged.

The [first-run incident review](docs/FIRST-LIVE-REVIEW.md) preserves the uncertain request's evidence, explains the diagnostic gap and records the recovery constraints. New CLI model calls now save safe HTTP diagnostic metadata without changing the frozen evaluator or retrying existing work.

The normative reference is the latest official NoveltyBench code, checked during this work: **v1.1**, commit `64a23be6b18ec1dacc298830aab276061b6e143c`. The paper is historical context. New CLI experiments check upstream HEAD and refuse to start if the reference changed; existing runs keep their frozen version. There is no v1.0 runtime path.

## Run the offline example

Python 3.13; no third-party runtime dependencies or credentials required. From this directory:

```powershell
python -m buddha demo --out runs/slice2-demo
python -m buddha demo --out runs/slice2-demo
python -m buddha inspect --run runs/slice2-demo
python -m buddha verify --run runs/slice2-demo
```

The example uses canned responses and judgments. It demonstrates the complete data/accounting path, including cached resume; its scores are synthetic. The second run reuses the same 12 completed operations and makes no new transport calls.

## Policy optimization and the first live run

```powershell
python -m buddha search-demo --out runs/slice3-demo
python -m buddha search-demo --out runs/slice3-demo
python -m buddha search-inspect --run runs/slice3-demo
```

This synthetic example evaluates independent-sampling and in-context seeds, proposes JSON policies, evaluates eligible children on the same development prompts, and reconstructs the archive from cached receipts. Its judgments are constant fixtures, so it demonstrates orchestration rather than improvement.

The first live experiment was authorized for **up to $50 combined**, covering both providers and all search stages. The initial attempt was interrupted while awaiting answer 10. Its nine replies and full uncertain reservation remain intact. The completed recovery restart used a **$49.465918 cap and 118-call allowance**, accounting for the original $0.534082 committed liability and ten attempted calls. It repeated the same one-prompt, two-seed, one-proposal engineering pilot with fresh evidence. Leave the original inactive. Recovery preparation and funding across directories remain manual; see [the incident review](docs/FIRST-LIVE-REVIEW.md) and [completion handoff](docs/FIRST-LIVE-RESULTS.md). The commands below describe the completed run; they do not start a new optimization iteration.

Supply keys locally through the new hidden prompts:

```powershell
python -m buddha search-inspect --run runs/first-live-recovery
python -m buddha search-run --run runs/first-live-recovery --live --prompt-keys
```

Read [API key setup](docs/API-KEYS.md) before execution. Missing `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` values are requested without echo; prompted keys live only in the runner process and are removed on exit. Do not paste them into chat. Pre-existing environment values are also supported. A budget or uncertain-provider stop preserves receipts and may leave an incomplete candidate; resume the same directory.

The CLI acknowledges each received key, announces execution, and shows elapsed time, recorded replies, pending/unknown requests, recorded cost, held reservations and published candidate counts. Unchanged state produces a heartbeat every ten seconds. These messages use stderr; stdout remains JSON. Receiving a key confirms local entry, not provider authentication.

To observe an existing process from another terminal without credentials, writes or API calls:

```powershell
python -m buddha watch --run runs/first-live-recovery
```

The watcher works with runs started before progress output was added. It stops when it finds a matching saved completion record or an uncertain operation requiring review. No ledger activity alone cannot establish whether the original process is alive; check its terminal for errors. Do not retry uncertain requests before reconciliation.

## Prepare a live baseline

The current baseline independently samples ten answers with low reasoning effort. It uses `gpt-5.6-luna` for generation and set partitioning, and the v1.1 `claude-opus-5` quality judge for each class's first answer. The generation setting of 2,048 corresponds to upstream's doubled 4,096 combined output/reasoning allowance. Both effective judge prompts are pinned byte-for-byte.

The [example configuration](examples/live-config.json) is a generic template with **no spending cap**. Supply an explicit `--budget-usd` when freezing a run. The approved $50 is for the one first live search above; this baseline workflow is an alternative experiment, not additional spending authorization. [Historical cost scenarios](docs/SLICE2.md#cost-planning) are estimates rather than measured charges.

```powershell
python -m buddha check-upstream
python -m buddha fetch --dataset curated --out runs/datasets/curated.jsonl

# Alternative baseline preparation; this does not authorize an additional paid run:
python -m buddha prepare --dataset curated --data runs/datasets/curated.jsonl --config examples/live-config.json --budget-usd 50 --limit 5 --out runs/pilot
python -m buddha inspect --run runs/pilot
```

These commands fetch public data and freeze configuration; they do not invoke models. The selected IDs/text and full source dataset are preserved and checked against their hashes. `--limit` selects the first N source rows for an engineering pilot; it does not create a representative scientific split. Without `--limit`, all source prompts are selected; raise the call allowance deliberately for larger runs.

Set `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` through the process environment or your secret manager. [.env.example](.env.example) contains placeholders; the CLI does not load it automatically. Keys never enter the run manifest or ledger. Enable model calls explicitly:

```powershell
python -m buddha run --run runs/pilot --live --prompt-keys
python -m buddha inspect --run runs/pilot
python -m buddha verify --run runs/pilot
```

The same `run` command resumes completed work. A timeout or unknown provider outcome stops automatic replay and retains its reservation; do not reissue it under a new operation ID. A malformed completed judgment is retained and charged in accounting, then rejected when parsed again. Reconciliation requires external provider evidence, not a retry assumption. See [operation recovery and limits](docs/SLICE2.md#accounting-and-recovery).

## Artifacts and guarantees

Each run contains a frozen `manifest.json`, byte-verified `dataset.jsonl`, and SQLite ledger. A complete result publishes:

```text
evaluation/
  generations.jsonl
  v1.1/partitions.jsonl
  v1.1/scores.jsonl
  v1.1/summary.json
  provenance.json
```

Imports check complete expected coverage, exact prompt identity, protocol/file hashes, consistency across stages, and metric arithmetic. Provenance establishes local consistency; it is not official certification or a signature. [Benchmark compatibility notes](docs/SLICE2-BENCHMARK-NOTES.md) document deliberate bounded-execution differences from native upstream behavior. Running upstream judging on these files can make new paid calls; use a copy for independent rescoring.

The local cap uses conservative maximum-rate accounting over provider-reported tokens, including reasoning and cache usage. It reserves a whole documented context allowance before each request. This can stop a run earlier than invoice-based accounting would. Guarantees depend on the configured bounds and provider honoring the requested model/tier; unexpected identities or tiers stop spending and retain evidence. Rates must be reverified within seven days before live execution. No automatic retries, fallback judges, generated-code execution, or publication occur.

## Design and verification

- [Consolidated living plan and current next slice](docs/PLAN.md)
- [Architecture and scientific contract](docs/DESIGN.md)
- [Latest benchmark source audit](docs/NOVELTYBENCH.md)
- [Research and successors](docs/RESEARCH.md)
- [Slice 2 handoff, costs, and verification](docs/SLICE2.md)
- [Slice 3 policy-search handoff](docs/SLICE3.md)
- [API keys and the approved budget](docs/API-KEYS.md)
- [Historical slice 1 checks](docs/VERIFICATION.md)

```powershell
python -m unittest discover -s tests -v
python -m ruff check buddha tests
python -m ruff format --check buddha tests
python -m mypy --strict buddha
python -m bandit -r buddha
python -m pip_audit --no-deps -r requirements.txt
python -m compileall -q buddha tests
```

CI is configured on Windows/Linux, Python 3.13, using the pinned tools in `requirements-dev.txt`; application runtime dependencies remain empty. Development auditing includes certifi (MPL-2.0), recorded in the recovery contract, without adding it to the application runtime. Local verification is reported separately from hosted CI. The user authorizes continued implementation with a summary and PR per slice, pausing for live execution or a required decision. Genuine source self-modification requires the separate isolated-executor work. HyperAgents contributes conceptual inspiration only; its source is excluded. Earlier dated handoffs describing absent Git/CI are historical.
