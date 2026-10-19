# Slice 2: one auditable NoveltyBench v1.1 baseline

This is the historical slice 2 snapshot. The cap was subsequently approved at up to $50 for one first live experiment; see [slice 3](SLICE3.md) and [API key setup](API-KEYS.md) for current status. The verification counts below describe slice 2.

## Delivered behavior

The latest official NoveltyBench implementation is normative. This build pins metric **1.1** and repository commit `64a23be6b18ec1dacc298830aab276061b6e143c`, rechecked against upstream HEAD during final CLI verification. The original paper remains historical context. New CLI preparation fails when upstream changes; a resumed run retains its frozen reference.

The local implementation now supports a fixed end-to-end baseline: verified source prompts, a frozen run manifest, ten independent generations per prompt, set-level partitioning, quality judgments for class heads, metric computation, artifact publication, and independent local re-import. No policy evolution or generated-source execution is included.

The public commands are `check-upstream`, `fetch`, `prepare`, `run`, `inspect`, `verify`, and `demo`. See the [README](../README.md) for complete commands. All runtime code uses Python 3.13's standard library; no new dependency or model SDK was installed.

| File | Implemented contract |
| --- | --- |
| `buddha/evaluation.py` | v1.1-only protocol identity; upstream null/no-shuffle seed; existing metric and coverage checks |
| `buddha/benchmark.py` | Exact v1.1 prompt strings, strict partitions, verified datasets, consistent cross-stage import/export |
| `buddha/ledger.py` | Transactional reservations, immutable run configuration, operation/event history and durable receipts |
| `buddha/provider.py` | Fixed-host single-attempt HTTPS, explicit service tiers, token accounting and replay broker |
| `buddha/run.py` | Frozen development baseline and current reference request construction |
| `buddha/__main__.py` | Local command interface, live gate, verified public-data fetch and upstream check |
| `examples/live-config.json`, `.env.example` | Reviewable model/rate bounds, unset budget and credential placeholders |
| `THIRD_PARTY_NOTICES.md` | MIT notice for reused official judge prompt text |

## Protocol and provenance

The baseline uses Luna for generation/partitioning and the reference Opus quality judge. It does not inject extra generation instructions. Upstream's `regenerate` means independent same-prompt sampling, not the separate in-context protocol. The 2,048 generation setting and low reasoning effort produce an effective combined output/reasoning limit of 4,096. Quality judging uses adaptive thinking, high effort, and 16,000 total output tokens.

Both effective judge prompt hashes match the source audit. Partition ordering supports `null` for the published unshuffled protocol. Incomplete/malformed partitions are rejected; duplicate positions remain unscored and only class heads earn utility. Missing or refused judgments prevent a complete result.

The controller additionally caps OpenAI partition output at 16,000 and explicitly requests standard service tiers. Retries, fallback judges, and lenient repairs are disabled. These controls are recorded in generation configuration and therefore affect the protocol fingerprint. They are disclosed differences from unrestricted native upstream execution; identical stochastic scores are not promised. [Detailed fidelity checks](SLICE2-BENCHMARK-NOTES.md).

Preparation preserves the entire source dataset byte-for-byte alongside exact selected prompts. Loading checks the source hash and verifies that each selected ID/text actually belongs to that snapshot. A declared official hash alone cannot authorize substituted prompt contents. Changing a frozen manifest after ledger creation conflicts with its stored identity.

Exports use upstream-compatible stage field names plus local provenance. The importer requires the recognized local format/origin, exact artifact hashes, matching ordered evidence across stages, recomputed metrics, and complete expected coverage. Self-checksums provide consistency, not external authentication. Plain upstream score files without this provenance sidecar are not accepted by this local importer; upstream-compatible layout is not a claim of official certification.

## Accounting and recovery

Amounts are integer micro-USD: USD 1 = 1,000,000 micro-USD. Independent call and monetary caps apply. The broker reserves a conservative upper amount in one SQLite transaction before dispatch. Stable operation IDs include run, task, stage, and position; request hashes bind the model, limits, rates, and exact body. Concurrent independent ledger connections cannot reserve the same remaining funds or dispatch one operation twice.

Known results and usage are committed before semantic parsing. Thus a paid but malformed judgment is retained and cannot silently be regenerated on resume. Generation empties/refusals stay in the answer set as explicit placeholders. Completed results replay without a key or provider request. Before new HTTP work, all required role credentials are checked locally; missing credentials do not create fictitious uncertain paid work.

Socket/network failures and interrupted dispatches remain potentially billed. They are not automatically retried or refunded. Unknown work retains its full reservation. An unexpected returned model, service tier, or missing request identity preserves the normalized receipt, leaves cost unresolved, and stops new spending until reconciled. Undocumented alias-to-snapshot mappings are rejected instead of guessed. Known token/cost overruns are preserved before the fixed runner stops.

The provider cost calculation uses the configured **maximum applicable rates** on provider-reported tokens. OpenAI prompt/completion totals already include cache/reasoning subdivisions; those subdivisions are not added again. Anthropic input usage sums the disjoint uncached, cache-creation, and cache-read fields; output includes thinking. `actual_microusd`/`spent_microusd` in this ledger mean the recorded conservative charge, not a reconciled provider invoice.

There is no automatic reconciliation command in this slice. A trusted operator can inspect `Ledger.get(operation_id)` and reconcile through `Ledger.complete` only with external evidence of completion, request identity, and cost. Never release an uncertain reservation by editing SQLite, reissuing under a new ID, or assuming that a client timeout canceled billing. Wrong-model results remain invalid scientific evidence even after financial reconciliation.

Schema 1 is retained unchanged. Schema 2 appends an immutable `unknown_receipts` table; the upgrade is transactional. Its documented rollback is permitted only while the new table is empty. Tests cover schema 1 -> 2 -> safe empty rollback -> 2, preservation of earlier operations, and refusal to remove existing receipt evidence. No migration framework or shared database service was added.

Export uses a cooperating-writer lock, staging directory, durable file writes and directory rename. Conflicting output is never silently replaced. Failure-injection tests verify cleanup and resolved-path containment. Abrupt process termination during publication can leave a stale export lock; after proving no writer is active, an operator must review/remove that specific lock before re-exporting. The completed ledger responses remain available; the tool does not automatically delete a possibly active writer's lock.

## Cost planning

These are scenarios, not measured usage or approved caps. Prices were checked against [OpenAI's Luna documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna) and [Anthropic's Opus 5 documentation](https://platform.claude.com/docs/en/models/opus-5/overview). Standard rates per million tokens are Luna USD 0.20 input / 1.20 output, and Opus USD 5 input / 25 output. Reasoning is billed output. This baseline uses no search tools or fast tiers.

Assume ten Luna generation calls per prompt, 1,000 input tokens each, one partition call, and the following quality-head counts. All output amounts below include hidden reasoning. No retry/fallback/evolution costs are included.

| Scenario | Generation output per answer | Partition input/output | Quality heads; input/output per head | Approx. 5 prompts | Approx. 1,100 prompts |
| --- | ---: | ---: | --- | ---: | ---: |
| Lean | 512 | 8,000 / 1,000 | 3; 1,500 / 1,000 | $0.54 | $119 |
| Middle | 1,024 | 14,000 / 2,000 | 6; 2,500 / 3,000 | $2.72 | $599 |
| Heavy thinking | 2,048 | 25,000 / 6,000 | 10; 5,000 / 8,000 | $11.44 | $2,518 |

The earlier $0.50-$5 pilot / $100-$1,100 full-pass planning range assumes moderate quality-judge reasoning, approximately 500-3,000 output tokens per head. The heavy-thinking row shows why that range is not an upper bound. Near the 16,000-token judge cap can cost more. Measure a small pilot before committing to a full evaluation or search population.

For cap accounting, the example config uses Luna maxima USD 0.50 input / 1.80 output across long-context/cache-write tiers, and Opus maxima USD 10 input / 25 output across cache policies. Requests explicitly exclude fast/priority selection. Conservative recorded charges for the three scenarios are approximately $0.70/$3.17/$12.83 for five prompts and $154/$697/$2,822 for a full pass; invoice charges may be lower.

The current conservative whole-context reservation is approximately $0.5324 per Luna generation, $0.5538 per partition, and $10.40 per Opus judgment. This reservation is released down to the recorded usage charge after a known completion. It is held after uncertainty. Therefore the cap must cover the next reservation even if the eventual request would have cost cents. The suggested first pilot is five prompts with a $25 cap, subject to the user's explicit choice; an expensive tail or unresolved request can stop it early. **No cap has been chosen and no paid call has occurred.**

The supplied example has 128 allowed calls, sufficient for a five-prompt worst-case 105-call pass. Larger runs require a deliberately larger call allowance as well as a chosen dollar cap. Live price/context bounds expire after seven days and must be reverified. Local accounting is conditional on correct configured bounds and the provider honoring the requested model/tier, rather than an independent guarantee of a vendor invoice.

## Verification and remaining work

The final suite has **122 passing tests**, including the slice 1 acceptance checks. New modules and the composed runner were tested first in a failing state before implementation. Additional regression tests reproduce the credential-before-dispatch, prompt-substitution, returned-identity, uncertain-receipt, and cached-replay failures before their fixes where applicable.

| Check | Result |
| --- | --- |
| Unit, concurrency, fault-injection, CLI and complete replay suite | 122 passed |
| Ruff lint and formatting | Passed |
| Strict mypy, entire `buddha` package | Passed |
| Bandit, runtime package | No issues; one documented non-security RNG exception to match upstream shuffling |
| Runtime requirements audit | No third-party runtime packages to audit; command completed without a vulnerability finding |
| Python compilation | Passed |
| Public CLI smoke | Upstream check, verified Curated fetch, demo twice, inspect and verify succeeded |
| Paid HTTP/real judge validation | Not run; budget is unset |

The repeated persisted demo uses one synthetic prompt, 12 completed operations, zero reserved balance after completion, and no additional calls on resume. Its metric values are canned simulation results and make no capability claim. Source/schema compatibility was checked independently as described in the benchmark notes. Some final delegated follow-ups hit the host usage limit; the primary agent completed the remaining fixes and checks. A completed independent final audit is not claimed.

There is no Git repository/remote or hosted CI in this workspace. No commit, deployment, submission, or data publication occurred. The implementation is a single-user local runner, not a tenant-hosting service.

This completes the authorized implementation slice and stops at the supplied per-slice checkpoint. Live validation awaits a numeric API cap and available credentials. Slice 3 adds bounded policy optimization, archive selection, and experimental baselines; source self-modification remains the separate isolated-executor slice. The original full-agent objective is not yet complete.
