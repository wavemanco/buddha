# Buddha

Build agents that improve their own procedures for producing useful, meaningfully different answers on [NoveltyBench](https://github.com/novelty-bench/novelty-bench).

The design for evolving agent code draws on [DGM](https://github.com/jennyzzt/dgm).

**Start with [the consolidated living plan](docs/PLAN.md)** for the complete original objective, completed work, new findings, dependencies and the next slice. It is the sole current roadmap; design and review documents supply specifications and evidence.

[How Buddha works](docs/HOW-IT-WORKS.md) explains the workflow in plain English:
how answers are generated, grouped and scored; what the 4/5/9 result means; how
parser recovery differs from a judge's decision; and where self-improvement fits.

## Current state

Buddha has demonstrated inherited Python source changes in a live experiment:
the changed agent ran, received complete development outputs and feedback, and
its changed improver produced a further runnable child. That demonstrates the
mechanism. The changed agent scored worse; improved useful diversity and a
better improver remain unproven. [Source experiment results](docs/SOURCE-CURRENT-LIVE-RESULTS.md).

The later 657-call comparison stopped as an explicit partial. Its records remain
intact. The current work prepares a fresh comparison using three development
and 26 final WildChat tasks, both plain-model sampling controls, and the official
NoveltyBench evaluation. The two remaining core phases are IMP-01's controlled
comparison and EVAL-02's assessment; human review is a parallel extension that
does not block the AI-only results. These are phases, not a promised slice count.

The reviewed implementation is now integrated into main through
[PR257](https://github.com/wavemanco/buddha/pull/257), with original slice commit
history preserved. [PR258](https://github.com/wavemanco/buddha/pull/258) removes our
unused observer callback. Existing progress and accounting remain; Inspect is
still a possible observability tool, with its original proof and deferred role
recorded in the [observability guide](docs/INSPECT-OBSERVABILITY-PROOF.md).

The immediate execution gate is a realistic-size history check that requires
separate approval: construct 193 owners/660 operations, then read the completed history in a
fresh process within 900 seconds. Earlier attempts stopped during construction;
the reader limit remains unmeasured. After that gate, the comparison needs a
checked current-source handoff and new funding. Exact-source full qualification
is still required before paid execution; a full pass at an earlier commit does
not transfer to later changes. [PLAN.md](docs/PLAN.md) records the evidence,
limits and next slice. No new long or paid run is authorized by this README.

Historical run reports, capacity observations and implementation receipts remain
in the linked project guides and living plan.

## Benchmark and experiment scope

The normative benchmark reference is the inspected official **NoveltyBench v1.1**,
commit `64a23be6b18ec1dacc298830aab276061b6e143c`. The paper is historical context.
Existing runs keep their frozen reference. Compatible new releases are intended
to use installation, configuration and checks before running the same frozen
agent; [the modularity contract](docs/BENCHMARK-INTEGRATION.md) states the exact
capability limits and the bounded upgrade/retirement evidence.

The completed judge audit used a separate **$15 / 120-attempt allocation**:
40 attempts, $0.032213 recorded cost and zero held.
[Its results](docs/MEASUREMENT-LIVE-RESULTS.md) retain judge variability and
broader scientific limits. Both historical experiment allowances are closed;
the original unknown-request hold remains preserved. A new comparison needs
its own reviewed allocation and handoff. [API key guidance](docs/API-KEYS.md)
explains hidden local key entry; never paste keys into chat or commit them.

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

The corrected linked run completed and was verified: nine saved replies reused, 51 new calls for $0.274533, with the original unknown still held. [Linked results and concerns](docs/LINKED-CONTINUATION-RESULTS.md) record the three candidate scores, repeated plots, literal/craft failures and shared accounting. The completed run is closed to new paid calls; its [execution handoff](docs/FIRST-LIVE-CONTINUATION.md) remains historical evidence. Benchmark conformance now passes at its declared offline scope; REC-05's bounded read-only verification and diagnostic gates are complete; both the blinded model-development review and bounded official-judge audit are complete; the controlled policy comparison is complete at its registered development scope.

This command prints the saved completed report once in this window. It needs no
keys, makes no changes and spends nothing:

```powershell
Get-Content runs/first-live-recovery/report.json
```

The historical pilot's paid CLI entry points are retired on current main; the
offline examples and inspection commands above remain available. Historical
manifests keep their source guards and need their preserved runtime for exact
reconstruction. A new paid study uses its own checked, funded handoff. Read
[API key setup](docs/API-KEYS.md) before execution. Prompted keys live only in the
runner process and are removed on exit; never paste them into chat.

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
python -m ci_test_shard --suite contracts --count 1 --index 0 --idle-seconds 3600
python -m ruff check buddha tests agents ci_test_shard.py
python -m ruff format --check buddha tests agents ci_test_shard.py
python -m mypy --strict buddha agents ci_test_shard.py
python -m bandit -r buddha agents ci_test_shard.py
python -m pip_audit --no-deps -r requirements.txt
python -m pip_audit --disable-pip --no-deps --strict -r requirements-dev.txt
python -m compileall -q buddha tests agents ci_test_shard.py
```

These checks run once in the current window and make no model calls.
`ci_test_shard` runs the selected fast contracts with progress reporting; it is
not the full suite. [CI-TESTS.md](docs/CI-TESTS.md) describes the pinned tools and
separate full-qualification workflow. Ruff checks style and formatting;
Mypy checks types; Bandit checks common source-security mistakes; `pip_audit`
checks the runtime and development dependency lists for known advisories and may
access its advisory service. The development check covers the pinned tools and
their dependencies, refuses skipped packages and makes no package changes;
`compileall` checks Python compilation and writes local bytecode caches.
The audits check versions named in the files, rather than inventorying or
updating packages already installed on your computer.
Ctrl+C stops a foreground check. Real-container proofs are separate optional
checks documented in their guides; the core audit does not clear the larger
native evaluator environment.

Ordinary pull requests and main pushes run the fast contracts and quality
checks on Linux and Windows, with a 15-minute ceiling per job. Feature-branch
pushes alone do not start these checks; open a pull request. PR jobs check the
merge tree and main-push jobs check main. Full qualification uses the complete
inventory across ten separate jobs and requires approval for an exact source
commit. Its progress and stopping rules are documented in [CI-TESTS.md](docs/CI-TESTS.md).

Both OS jobs use Python 3.13 and pinned tools from `requirements-dev.txt`;
application runtime dependencies remain empty. Development auditing includes
certifi (MPL-2.0), recorded in the recovery contract. Local verification and
hosted CI are reported separately. Inherited source modification is demonstrated;
better benchmark performance and improver effectiveness remain unproven.
HyperAgents contributes conceptual inspiration only; its source is excluded.
Earlier handoffs describing absent Git/CI are historical.

CI checks development dependencies immediately after installing the tools,
before running tests. The [development-tool refresh](docs/conformance/dev-dependency-refresh.json)
records the affected pins, patched versions, licenses and isolated-environment
checks. These checks do not audit the separate official evaluator environment.

## License

Buddha-authored code and documentation are available under the [MIT License](LICENSE).
Reused third-party material retains its own license and attribution; see
[third-party notices](THIRD_PARTY_NOTICES.md). External datasets and separately
installed dependencies retain their applicable terms.

## Contributions during development

This repository is not accepting external contributions during the current
development phase. New pull requests are restricted to collaborators. Public
forks and independent use remain welcome under the license above.

Changes to `main` must go through a pull request and can only be merged by the
maintainer's account. Force pushes and deletion of `main` are blocked, including
for administrators. Repository administrators can change these settings.
