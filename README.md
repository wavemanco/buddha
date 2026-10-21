# Buddha

Build agents that improve their own procedures for producing useful, meaningfully different answers on NoveltyBench.

**Start with [the consolidated living plan](docs/PLAN.md)** for the complete original objective, completed work, new findings, dependencies and the next slice. It is the sole current roadmap; design and review documents supply specifications and evidence.

[How Buddha works](docs/HOW-IT-WORKS.md) explains the workflow in plain English:
how answers are generated, grouped and scored; what the 4/5/9 result means; how
parser recovery differs from a judge's decision; and where self-improvement fits.

## Current state

The bounded **MEAS-01/MEAS-02 measurement audit is complete**; next is the
**POL-02 controlled policy comparison**. The project has auditable API
accounting, linked recovery, bounded policy search, replaceable release selection,
and isolated fixed-seed generation. The unchanged official LLM partition, score
and summary commands now compose with generated C1 answers in a complete
[offline-tested native baseline](docs/NATIVE-BASELINE.md).
[Configuration-only upgrades and retirement](docs/RELEASE-UPGRADES.md) now pass
controlled cross-release checks and a separate pinned-official regression.
[Legacy history](docs/RECOVERY-CONTRACT.md#rec-05a-retained-receipts-and-sealed-reads)
now preserves earlier uncertainty and terminal receipts separately, counting a
completed charge once. [Read-only search verification](docs/SEARCH-VERIFICATION.md)
now checks explicitly sealed saved requests, results, lineage and accounting
without keys, model calls or record changes. The [doctor](docs/DOCTOR.md) now
reports locks, unknown writer identity, outstanding diagnostics and native
completion anchors without resuming work. The [blinded measurement audit](docs/MEASUREMENT-AUDIT.md)
now has two frozen model reviews and a separate blinded adjudication. The
[results](docs/MEASUREMENT-AUDIT-RESULTS.md) preserve 17 resolved items and five
uncertain items; human scientific validation remains open. The
[offline judge audit](docs/MEASUREMENT-JUDGE-AUDIT.md) reproduces all six saved
partitions and compares 95 resolved distinct relations. The
[live audit](docs/MEASUREMENT-LIVE-RESULTS.md) now covers all 40 targets: resolved
controls agree, including equivalents, but one historical story set varies
between 4, 5 and 9 groups across repeated/order occasions. Raw official parser
replay confirms this is present in the judge's replies, without repair.
Uncertain cases remain uncertain; this is not population accuracy or a new
ranking. A
[prepared native study](docs/MEASUREMENT-JUDGE-AUDIT.md#prepared-native-study-interface)
now binds those 40 supplied controls to separate accounting occasions; its
offline execution checks do not supply new model judgments. Its
[operator launcher](docs/MEASUREMENT-JUDGE-AUDIT.md#operator-commands) checks
source and shared funding before hidden key entry, then shows progress and
retains the original owners when interrupted. A separate [offline target reader](docs/MEASUREMENT-JUDGE-AUDIT.md#offline-target-reports)
compares complete or explicitly selected partial outputs with frozen development
judgments while keeping uncertain and missing cases visible. Its engineering
fixtures do not supply fresh judge measurements.
The [versioned proposer contract](docs/POLICY-CONTRACT.md) now explains which
sampling mode sees earlier answers and preserves literal task requirements.
Fixed policies reuse the native pipeline; legacy search keeps v1. Controlled
policy comparisons remain open.

A separate [source-agent runtime prerequisite](docs/SOURCE-RUNTIME.md) now passes
actual filesystem, network, resource and cleanup checks on a pinned minimal
Python image. Production candidate execution and its model channel still need
their composed checks; the existing fixed-seed route is unchanged.

These are distinct from scientific success. Meaningful diversity, held-out
improvement, genuine task/improver source evolution and an improved improver have
**not been established**. Earlier pilot reviews flagged recurring premises and
possible plot overlap. Blinded model review resolves some as distinct and leaves
others uncertain; original benchmark scores and raw evidence remain unchanged. See the
[pilot review](docs/PILOT-REVIEW.md), [recovery results](docs/FIRST-LIVE-RESULTS.md)
and [linked continuation results](docs/LINKED-CONTINUATION-RESULTS.md).

At this checkpoint the living plan contains **8 remaining leaf slices**.
The Windows PID-lock observer follow-up is complete at its shared-reader scope;
[the guide](docs/DOCTOR.md#windows-file-sharing) states its boundaries.
The native pipeline is complete at its declared offline scope. Umbrella milestones
are not counted again. They cover
policy/search (2), source evolution (3), held-out evaluation (2) and the
improver comparison (1). This is a checkpoint count, not a promise that research
findings will never require a smaller slice; [PLAN.md](docs/PLAN.md) determines
the current status and order.

The normative benchmark reference is the inspected official **NoveltyBench v1.1**,
commit `64a23be6b18ec1dacc298830aab276061b6e143c`. The paper is historical context.
Existing runs keep their frozen reference. Compatible new releases are intended
to use installation, configuration and checks before running the same frozen
agent; [the modularity contract](docs/BENCHMARK-INTEGRATION.md) states the exact
capability limits and the bounded upgrade/retirement evidence.

The prepared study launcher requires an explicit live flag, a reviewed account
profile and an existing active allocation before unfinished work can run. The
user has now approved a separate **$15 / 120-attempt judge audit**, allowing a
partial result with its reason recorded. At preparation, its allocation had zero
calls and passed local key-binding checks after 1,025 local tests and confined
native proofs. The original audit has since completed with verified saved
accounting and four completion anchors: 40 attempts, $0.032213 recorded cost
and zero held. [The results](docs/MEASUREMENT-LIVE-RESULTS.md) retain judge
variability and broader scientific limits. No further audit command is needed. The
original $50 experiment
remains closed, with its unknown-request hold preserved. See the
[approved audit handoff](docs/MEASUREMENT-JUDGE-AUDIT.md#approved-15-live-audit). [API key guidance](docs/API-KEYS.md) explains process-only
key entry; never paste keys into chat or commit them.

Slice-specific commits and PRs are maintained in
[wavemanco/buddha](https://github.com/wavemanco/buddha). See the
[frozen generation guide](docs/FROZEN-SEED.md),
[confined evaluator guide](docs/CONFINED-NATIVE-EVALUATION.md) and
[conformance audit](docs/NOVELTYBENCH-CONFORMANCE.md) for implemented scope and
limitations. Infrastructure checks do not certify semantic judge accuracy.

## Run the offline example

Python 3.13; no third-party runtime dependencies or credentials required. From this directory:

```powershell
python -m buddha demo --out runs/slice2-demo
python -m buddha demo --out runs/slice2-demo
python -m buddha inspect --run runs/slice2-demo
python -m buddha verify --run runs/slice2-demo
```

All four commands run once in this PowerShell window, require no keys and spend
nothing. `demo` creates the example; repeating it reuses saved replies. `inspect`
prints its progress/accounting, and `verify` checks the stored evidence. They
write only the selected example directory; Ctrl+C stops a foreground command.

The example uses canned responses and judgments. It demonstrates the complete data/accounting path, including cached resume; its scores are synthetic. The second run reuses the same 12 completed operations and makes no new transport calls.

## Policy optimization and the first live run

```powershell
python -m buddha search-demo --out runs/slice3-demo
python -m buddha search-demo --out runs/slice3-demo
python -m buddha search-inspect --run runs/slice3-demo
```

These commands also run once here without keys or API spending. `search-demo`
creates a synthetic policy search; repeating it reconstructs the same search
from saved replies. `search-inspect` reconstructs cached results and prints the search/accounting. Only the
selected example directory changes; Ctrl+C stops a foreground command.

This synthetic example evaluates independent-sampling and in-context seeds, proposes JSON policies, evaluates eligible children on the same development prompts, and reconstructs the archive from cached receipts. Its judgments are constant fixtures, so it demonstrates orchestration rather than improvement.

The first live experiment was authorized for **up to $50 combined**, covering both providers and all search stages. The initial attempt was interrupted while awaiting answer 10. Its nine replies and full uncertain reservation remain intact. The completed recovery restart used a **$49.465918 cap and 118-call allowance**, accounting for the original $0.534082 committed liability and ten attempted calls. It repeated the same one-prompt, two-seed, one-proposal engineering pilot with fresh evidence. Both attempts are now historical inputs. Shared authorization imports their sealed liabilities once and enforces the combined dollar/call cap. The linked continuation reuses nine saved replies as evidence, sends a separately identified replacement for the unknown tenth, then completes the remaining search stages. Its new report separates new cost, inherited evidence cost and shared experiment accounting.

The corrected linked run completed and was verified: nine saved replies reused, 51 new calls for $0.274533, with the original unknown still held. [Linked results and concerns](docs/LINKED-CONTINUATION-RESULTS.md) record the three candidate scores, repeated plots, literal/craft failures and shared accounting. The completed run is closed to new paid calls; its [execution handoff](docs/FIRST-LIVE-CONTINUATION.md) remains historical evidence. Benchmark conformance now passes at its declared offline scope; REC-05's bounded read-only verification and diagnostic gates are complete; the blinded model-development review is complete, and auditing the official judge against those judgments is next.

This command prints the saved completed report once in this window. It needs no
keys, makes no changes and spends nothing:

```powershell
Get-Content runs/first-live-recovery/report.json
```

Historical pilot live commands require an existing `--authorization` database and a matching immutable run/runtime binding before key entry. The new study launcher instead reads the authority bound to its prepared original owners. Historical manifests retain their source guards; use the preserved original runtime for exact reconstruction, rather than attempting to run them with changed source. Read [API key setup](docs/API-KEYS.md) before execution. Prompted keys live only in the runner process and are removed on exit. Do not paste them into chat.

The CLI acknowledges each received key, announces execution, and shows elapsed time, recorded replies, pending/unknown requests, recorded cost, held reservations and published candidate counts. Unchanged state produces a heartbeat every ten seconds. These messages use stderr; stdout remains JSON. Receiving a key confirms local entry, not provider authentication.

To observe an existing process from another terminal without credentials, writes or API calls:

```powershell
python -m buddha watch --run runs/first-live-recovery
```

The watcher keeps running in the second window; Ctrl+C stops watching without
stopping the original run. It works with runs started before progress output was added. It stops when it finds a matching saved completion record or an uncertain operation requiring review. No ledger activity alone cannot establish whether the original process is alive; check its terminal for errors. Do not retry uncertain requests before reconciliation.

## Historical live CLI

The [slice 2 guide](docs/SLICE2.md) and [original continuation handoff](docs/FIRST-LIVE-CONTINUATION.md)
preserve the frozen pilot's preparation, execution, API-key and recovery commands.
They describe the historical v1.1 runner, whose bounded request/parser behavior
is distinct from full native execution. They are not instructions or additional
spending permission for the new native baseline path.

The existing baseline independently samples ten answers with low reasoning
effort. Its historical generation/partition model and quality judge are recorded
in the frozen run manifests. Reverify actual models, provider bounds, rates,
reference version and authorization before a new live experiment; model names
in old examples are not a fresh availability or pricing check.

## Artifacts and guarantees

Each historical CLI run contains a frozen `manifest.json`, byte-verified `dataset.jsonl`, and SQLite ledger. A complete result publishes:

```text
evaluation/
  generations.jsonl
  v1.1/partitions.jsonl
  v1.1/scores.jsonl
  v1.1/summary.json
  provenance.json
```

Imports check complete expected coverage, exact prompt identity, protocol/file hashes, consistency across stages, and metric arithmetic. Provenance establishes local consistency; it is not official certification or a signature. [Benchmark compatibility notes](docs/SLICE2-BENCHMARK-NOTES.md) document deliberate bounded-execution differences from native upstream behavior. Running upstream judging on these files can make new paid calls; use a copy for independent rescoring.

The local cap uses conservative maximum-rate accounting over provider-reported tokens, including reasoning and cache usage. It reserves a whole documented context allowance before each request. This can stop a run earlier than invoice-based accounting would. Guarantees depend on the configured bounds and provider honoring the requested model/tier; unexpected identities or tiers stop spending and retain evidence. Rates must be reverified within seven days before live execution. That historical CLI has no automatic retries or fallback judges. The separately
confined native evaluator preserves prescribed fallback behavior, while uncertain
payment stops new spending. Arbitrary evolved source and publication remain gated.

## Design and verification

- [Consolidated living plan and current next slice](docs/PLAN.md)
- [Architecture and scientific contract](docs/DESIGN.md)
- [Replaceable benchmark integration contract](docs/BENCHMARK-INTEGRATION.md)
- [Frozen seed and isolated generation](docs/FROZEN-SEED.md)
- [Complete selected native baseline](docs/NATIVE-BASELINE.md)
- [Read-only doctor, locks and watch commands](docs/DOCTOR.md)
- [Blinded measurement audit and review pack](docs/MEASUREMENT-AUDIT.md)
- [Complete native commands and environment limits](docs/CONFINED-NATIVE-EVALUATION.md)
- [Pinned benchmark source audit](docs/NOVELTYBENCH.md)
- [Research and successors](docs/RESEARCH.md)
- [Slice 2 handoff, costs, and verification](docs/SLICE2.md)
- [Slice 3 policy-search handoff](docs/SLICE3.md)
- [API keys and the approved budget](docs/API-KEYS.md)
- [Historical slice 1 checks](docs/VERIFICATION.md)

```powershell
python -m unittest discover -s tests -v
python -m ruff check buddha tests agents
python -m ruff format --check buddha tests agents
python -m mypy --strict buddha agents
python -m bandit -r buddha agents
python -m pip_audit --no-deps -r requirements.txt
python -m compileall -q buddha tests agents
```

These checks run once in the current window and make no model calls. `unittest`
runs portable tests with temporary fixtures; Ruff checks style and formatting;
Mypy checks types; Bandit checks common source-security mistakes; `pip_audit`
checks the core dependency list for known advisories and may access its advisory
service; `compileall` checks Python compilation and writes local bytecode caches.
Ctrl+C stops a foreground check. Real-container proofs are separate optional
checks documented in their guides; the core audit does not clear the larger
native evaluator environment.

CI is configured on Windows/Linux, Python 3.13, using the pinned tools in `requirements-dev.txt`; application runtime dependencies remain empty. Development auditing includes certifi (MPL-2.0), recorded in the recovery contract, without adding it to the application runtime. Local verification is reported separately from hosted CI. The user authorizes continued implementation with a summary and PR per slice, pausing for live execution or a required decision. Genuine source self-modification requires the separately gated source-evolution work. HyperAgents contributes conceptual inspiration only; its source is excluded. Earlier dated handoffs describing absent Git/CI are historical.
