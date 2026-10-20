# Linked continuation of the interrupted pilot

REC-04B operational handoff, October 20, 2026. [PLAN.md](PLAN.md) remains the single roadmap. This document preserves execution inputs and evidence for the completed REC-04L continuation.

**Completed and verified October 20, 2026:** the continuation reused nine answers and completed 51 new calls for $0.274533 in new recorded cost. [Results, accounting and remaining concerns](LINKED-CONTINUATION-RESULTS.md) record the outcome. The instructions and preparation figures below are retained as the execution record.

## Execution and expected result

Use a normal interactive PowerShell window from this checkout. The reviewed preparation uses the `-v2` paths below. The earlier path without that suffix is permanently inactive.

The first command moves PowerShell into the project folder. The second starts or resumes the prepared live continuation, asks for missing API keys without displaying them, and can spend money within the shared budget.

```powershell
cd C:\Users\arvik\code\buddha
python -m buddha search-run --run runs/first-live-continuation-v2 --live --prompt-keys --authorization runs/first-live-authorization-v2.sqlite3
```

Paste each missing key at its hidden prompt and press Enter. The program acknowledges key names, explains inherited replies and prints periodic progress. A new PowerShell window is fine; no key values belong in chat or command arguments. The existing [key guide](API-KEYS.md) describes input and cleanup.

The first nine answers come from the interrupted run's stored receipts. The next answer is a new request explicitly replacing the missing tenth. The runner then judges that candidate, evaluates the history-aware seed, proposes a child and evaluates an eligible child on the original single prompt. It makes at most 55 new model requests; fewer may suffice if answers are grouped together or a proposal is rejected. The remaining allowance is a ceiling, not a spending target. Progress counts new physical operations; inherited replies do not inflate its API-reply count.

A complete run publishes `runs/first-live-continuation-v2/report.json` and candidate generation/evaluation files. Its v2 report contains new physical `costs`, nine-answer `inherited_costs`, combined `evidence_costs`, shared `authorization` accounting and explicit `continuation` lineage. Original generation order and receipts remain exact. No result from this one-prompt pilot establishes useful-diversity improvement.

After completion, tell Codex the run finished; the files in this checkout can be reviewed directly. If it stops, retain the error text and directory. Uncertain transmission keeps its reservation and stops shared dispatch; an automatic retry is never inferred from elapsed time. A purely local preparation failure remains unsent and can be reviewed for resuming that same operation. Reusing a complete run replays saved replies without new model calls.

These optional commands only read saved records. They do not start or resume the run, ask for API keys, or spend money.

`watch` continuously shows progress for this continuation's new calls: replies received, pending or uncertain requests, recorded costs and money held. Run it in a separate PowerShell window while the main run executes. It stops when it sees completion or an uncertain request needing review. Press **Ctrl+C** to stop only the watcher; the main run in the other window keeps going. The watcher reads saved records, so its updates do not prove the main run is still running.

```powershell
python -m buddha watch --run runs/first-live-continuation-v2
```

`authorization-inspect` prints a one-time budget summary as JSON (structured text). It covers the original attempt, completed recovery and this continuation, showing money spent, money still held and the remaining allowance.

```powershell
python -m buddha authorization-inspect --authorization runs/first-live-authorization-v2.sqlite3
```

Run these commands separately if you want the budget summary immediately. If you paste both into the same window, the second waits until `watch` exits.

## Funding and provenance

The user authorized one experiment up to **$50 total**, including all attempts. Both historical runs are imported inactive. Before new execution: **$0.301862** known, **$0.532373** still held, **$0.834235** committed, **$49.165765** available; 73 of 128 requests already allocated and at most 55 remaining. These are conservative configured-rate calculations, not reconciled provider invoices. The old unknown is neither released nor replaced in its original ledger.

The original run remains `a1257f96467b490b910b559437a71258`; the already completed recovery remains `a0946e22ae1e45d6bf8f74cf9f4f30bb`. The new preparation records their sealed source, current source ZIP and MIT notices, nine inherited semantic references, the new replacement identity and the combined accounting snapshot. Models, prompts, evaluation, sampling and search controls stay frozen. New runtime/protocol provenance is explicit; future stochastic responses and proposer-feedback fingerprints are not promised identical.

| Verified corrected preparation | Identity |
| --- | --- |
| Run | `a486d90396934a45940637d77a168304` |
| Authority | `511fe97a08e049a48907c00bad7462df` |
| Runtime SHA256 | `ae05baf34c5bc2e69cf1b462a82d6412a827eaa000f577b7cbe1cfcc31f3e81b` |
| Local verification record | `runs/reviews/rec04b-preparation.json` |

Preparation and validation made zero model calls and left the new ledger empty. Local checks passed 381 tests (one Windows symlink-privilege skip), Ruff, strict mypy, Bandit, runtime dependency audit and compilation. Independent native-CLI testing used mocked responses and blocked network, then replayed without credentials or new requests. These checks support infrastructure behavior; live account access and actual completion are still untested for this continuation.

Public preflight checked the [official NoveltyBench revision](https://github.com/novelty-bench/novelty-bench/commit/64a23be6b18ec1dacc298830aab276061b6e143c), [Luna model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna) and [Opus 5 documentation](https://platform.claude.com/docs/en/models/opus-5/overview) on October 19 Pacific / October 20 UTC. HEAD still matched frozen v1.1; current published standard, cache and long-context rates fit the existing upper bounds. The check made no model API calls and cannot establish account entitlement, capacity or an identical hosted backend. Detailed local evidence: `runs/reviews/rec04b-live-preflight.json`.

## Retired preparation retained for review

The first preparation was bound before the final malformed-archive review finished. It was permanently deactivated with **zero new operations, cost or held reservation**, and all its files remain available:

| Item | Retired preparation |
| --- | --- |
| Directory | `runs/first-live-continuation` |
| Run ID | `11e1ceeb4b1c40bf84a2e765c275ba8c` |
| Authority file | `runs/first-live-authorization.sqlite3` |
| Authority ID | `936dc3f0f5204617b5c7d561a1f836f6` |
| State | All runs inactive; historical costs and unknown hold retained |

The `-v2` authority explicitly supersedes this unused allocation with the same $50/128-call envelope and both historical liabilities. Creating it grants no additional funding. No old manifest or ledger was rewritten to accept changed source; the original unknown remains untouched. The archive validation error was reproduced by a failing test and fixed before releasing the live command.
