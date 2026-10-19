# CLI progress follow-up

Implemented October 19, 2026 after the first live pilot exposed silent execution. The change covers `buddha/__main__.py`, new `buddha/progress.py`, CLI/progress tests and documentation. All nine source files bound by the existing search manifest remain byte-identical; no manifest, budget, provider setting, ledger migration or evaluation rule changed.

## User-visible behavior

`run` and `search-run` now acknowledge each hidden key after local validation, print a starting message, then emit flushed progress to stderr. Each update reports observer elapsed time, recorded reply count, pending and unknown operations, conservative recorded cost, held reservations, the frozen cap and published candidate count. Unchanged state produces a waiting heartbeat every ten seconds. Reply counts do not imply that the subsequent semantic judgment parsing succeeded. Cached work starts with an `already recorded` label.

Successful execution prints `Run complete`; exceptions print a stopped message, and Ctrl+C returns an interruption error with exit status 130. Final JSON stays on stdout. Credentials, prompt/response text, policy instructions and provider request IDs are not included in progress output. A received-key acknowledgment does not claim provider authentication. Broken output streams or unavailable progress data cannot alter provider dispatch, release a reservation or trigger a retry.

An existing run can be observed without restarting it:

```powershell
python -m buddha watch --run runs/first-live-search
```

The watcher uses short SQLite connections in explicit read-only mode and selects only accounting metadata. It does not use the ledger writer, acquire the search lock, reserve work, read environment credentials or invoke providers. It can be run alongside a live process and works with older processes that lack progress output. It returns a safe JSON snapshot when it finds a matching saved completion record or an uncertain operation. A terminal success marker is a local consistency check; it is not an independent metric audit.

If no completion record appears, the watcher continues waiting until Ctrl+C. Inactivity is not interpreted as proof that the runner is alive, dead, failed or stalled. The original terminal remains authoritative for errors that leave no final completion record, such as a budget or invalid-judgment stop. Do not launch a second paid runner to get progress.

## Observed first-run state

Read-only inspection found nine completed provider replies and one unknown operation: answer 10 of the independent-sampling seed for `curated-0`. There is no completed candidate evaluation or final report. The ledger records **$0.001709** of conservative usage charges and retains a **$0.532373** reservation for the uncertain operation under the $50 cap. A held reservation is not a confirmed invoice charge.

No normalized provider receipt was available for that operation. The stored metadata does not establish whether the provider processed or billed it, or which transport/API failure occurred. It has not been retried, refunded or manually changed. Recovery needs external provider evidence; preserve the same directory and reservation. This progress follow-up does not resolve the uncertain request.

The subsequent [incident review and diagnostic fix](FIRST-LIVE-REVIEW.md) records the completed investigation and the remaining recovery decision.

## Verification

The full suite passed **224 tests**, including 15 new progress checks and two additional CLI cases. Checks cover a blocked worker heartbeat, flush behavior, cached work, read-only connections and no database creation, temporarily busy data, secret/text canaries, broken streams, interruption/error messages, completion identity and immutable observer behavior. Ruff lint/format, strict mypy across 12 runtime modules, Bandit, runtime dependency audit and compilation passed. Runtime remains standard-library-only.

The new watcher was also exercised against the actual first-run ledger. It reported `needs_review`, nine recorded replies and one held unknown operation without making API calls. The existing source hashes and ledger event history were checked unchanged. No Git commit or hosted CI is claimed; this workspace has no Git repository.
