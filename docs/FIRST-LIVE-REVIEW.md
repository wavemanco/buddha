# First live run: uncertain request review

This document preserves incident evidence and recovery constraints. [PLAN.md](PLAN.md), REC-01–05, owns current implementation order and status, including the requested linked continuation.

Reviewed October 19, 2026. **The original run was locally interrupted while awaiting the tenth provider response.** The user-supplied traceback ends with `KeyboardInterrupt` inside `connection.getresponse()` / SSL read. Nine authentic replies are preserved. The tenth request's processing/billing outcome and answer remain unknown, so the original run cannot automatically resume. The review made no provider requests and did not change the original ledger, manifest, dataset or frozen execution code.

## Observed evidence

The machine-readable [evidence snapshot](first-live-request-10.json) records operation identities, provider request IDs for the nine known replies, response hashes, accounting and event timing. It excludes credentials, prompts and answer text. Run ID: `a1257f96467b490b910b559437a71258`.

| Observation | Evidence |
| --- | --- |
| Failed stage | Independent-sampling seed, `curated-0`, generation index 9 (answer 10) |
| Unknown operation | `231aad4e4c5d27b6fdd9e73da5993aee27f357dfa36b40c3b3463836c89c581b` |
| Request fingerprint | `3e77b9c2ec01c66b1426beeb571778f3eb35f5be45bac776e13f25f0b0d5b89a` |
| Prior requests | All ten operation records bind that same request fingerprint |
| Nine known replies | Expected model and standard tier; normal stop; no refusal; 20 input tokens each, 91–108 total output tokens |
| Dispatch event | `2026-10-19T15:45:08.116Z` |
| Unknown event | `2026-10-19T15:45:10.679Z` |
| Event separation | 2.563 seconds |
| Missing evidence | No normalized tenth reply, provider request ID, HTTP status or failure category |
| Completed evaluations | None; partitioning, quality judging and policy proposal were not reached |
| Existing integrity checks | All nine frozen source hashes match; no search lock or final report remains |

The subsequent [user-supplied traceback excerpt](first-live-interrupt-trace.txt) identifies a `KeyboardInterrupt` during SSL reading of the HTTP status line, before response headers were returned to the transport. This establishes local interruption as the stopping mechanism. No timeout or HTTP rejection is reported in that trace. It does not establish whether the provider processed or billed the dispatched request, or recover the missing answer.

## Accounting

| Item | USD |
| --- | ---: |
| Recorded conservative charges for nine replies | 0.001709 |
| Held maximum reservation for the unknown request | 0.532373 |
| Combined committed liability | **0.534082** |
| Original authorization | 50.000000 |
| Maximum remaining authorization after retaining that liability | **49.465918** |

These amounts use the configured upper token rates, not a reconciled provider invoice. No reservation was released, refunded or moved. An external usage total alone cannot identify which of ten identical requests produced a missing answer.

## Root cause of the diagnostic blind spot

The broker preserved `KeyboardInterrupt` and retained the dispatched request's reservation as designed. The older CLI then displayed an uncaught traceback. The current CLI catches interruption, prints an explicit message and returns exit status 130.

A separate diagnostic defect was found during review: the original `HTTPTransport.send` reads the response body before retaining its request ID, rejects all non-200 responses, then collapses ordinary HTTP, network and parsing failures into one generic `ProviderUncertain`. The broker also replaces ordinary exception reasons with a generic message. That defect would lose useful HTTP evidence on other failures; the supplied trace resolves this incident to local interruption before headers were received.

The normal Chat Completions retrieval API returns only completions explicitly created with `store=true`. This request did not enable that option and has no saved completion ID, so ordinary retrieval is not a supported recovery promise. Provider-side logs/support may still help establish receipt, rejection or billing. [Official retrieval contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/retrieve).

## Diagnostic fix

The CLI now selects `DiagnosticHTTPTransport`, a subclass of the unchanged frozen transport. It retains existing credential preflight and single-attempt behavior, sends the same request body to the same endpoint, and binds each call to exactly one dispatched ledger operation through a read-only lookup. Ambiguous fingerprints fail before HTTP dispatch.

New calls save checksummed immutable `diagnostics/<operation-id>/request.json` and `outcome.json` sidecars containing adapter source hash, request fingerprint, exact operation identity, phase, elapsed time, HTTP status, validated request ID and a fixed failure category/allowlisted error code. They never save API keys, request/response bodies, provider error messages or arbitrary headers. Status and request ID are captured before reading the body. A failure to save an outcome cannot discard a known billable reply or mask an interruption.

OpenAI requests also include a unique `X-Client-Request-Id`. This is a correlation ID for provider investigation; it does not make a retry idempotent. The request body, model controls and evaluation protocol are unchanged. [Official request-debugging guidance](https://developers.openai.com/api/reference/overview#debugging-requests).

CLI error JSON includes validated diagnostic metadata when it corresponds to the saved uncertain operation. This improves future diagnosis; it cannot retrospectively create evidence for the already-unknown call. The original nine core source files remain unchanged, and their manifest hashes still pass.

## Recovery decision

1. If an authentic original answer, model identity, request ID and usage can be recovered, reconcile that exact operation through the existing ledger interface with that evidence. Cached execution can then continue. Financial evidence alone without the answer is insufficient for scientific completion.
2. If the answer is irrecoverable, retain this run as a failed partial attempt. A separately identified recovery experiment can use at most **$49.465918** while the original worst-case liability remains reserved. Its call allowance must also account for the ten already-attempted calls. That is a new attempt, not replay or reconciliation; it needs an explicit recovery decision and traceable accounting.
3. Do not edit the original SQLite state, insert a fabricated reply, label the missing answer as a refusal, or silently reissue its operation under another ID. The current controller has no replacement-attempt protocol and requires full coverage plus reconciled accounting to publish a complete result.

The traceback has been received and reviewed. A separately identified recovery restart is prepared as described below. No replacement or new model request has been sent by this review. The support packet remains local; nothing was sent to another person or service.

## Prepared recovery restart

`runs/first-live-recovery` repeats the same one-prompt, two-seed, one-proposal engineering pilot with fresh evidence. It does not reuse the original nine replies or represent a successful continuation of the interrupted baseline. Source, splits, selected prompt, model access, templates and search specification match the original. The new dollar cap is **$49.465918** and the call allowance is **118**, subtracting the original ten attempted calls from 128. A checksummed `funding.json` links the original liability snapshot and the recovery manifest.

This is a deliberately constrained pair of runs, not a general shared cross-run budget service. **Leave `runs/first-live-search` inactive, with its unknown reservation intact. Use only the recovery directory for further paid execution.** Do not later reconcile and resume the old run while spending the recovery cap; that would exceed the declared combined allocation.

```powershell
cd C:\Users\arvik\code\buddha
python -m buddha search-run --run runs/first-live-recovery --live --prompt-keys
```

To observe that run from another terminal without credentials or extra requests:

```powershell
python -m buddha watch --run runs/first-live-recovery
```

The old unresolved maximum liability plus the full new cap totals exactly $50. This preserves the original worst-case charge even if the interrupted provider request was processed. Unknown reservations remain estimates of maximum exposure, not confirmed invoices. The preparation itself invokes no models.

## Verification and delivered files

The full suite passed **245 tests**, including 20 new diagnostic cases and the CLI HTTP-failure integration case. Ruff lint/format across 25 Python files, strict mypy across 13 runtime modules, Bandit, the runtime dependency audit and compilation passed. All HTTP/credential checks in the suite used mocked connections and canary credentials. No new runtime dependency was added.

The new cases cover HTTP 429 metadata, headers captured before body failure, invalid JSON, exact request preservation, fixed endpoints, single dispatch, preflight inheritance, ambiguous identical-request binding, no database creation, secret/message exclusion, outcome-write failure without lost billable reply, interruption preservation, readonly ledger state, immutable request records and summary-to-ledger correlation. A delegated independent review found no blocking safety/accounting issue. The summary describes the newest valid outcome; a newer success can suppress an older failure, while the ledger watcher remains the source for outstanding unknown counts.

The recovery run ID is `a0946e22ae1e45d6bf8f74cf9f4f30bb`. Its manifest and checksummed funding record are saved under `runs/first-live-recovery`; inspection **at preparation time** confirmed zero operations, zero charges and zero reservations there. The original ledger's complete file hash still equaled the captured evidence snapshot, and all nine frozen source hashes matched. Source/splits/screen/search controls matched across runs; only the remaining dollar and call allowances differed. Combined cap and call arithmetic were checked explicitly.

Delivered implementation files are `buddha/diagnostics.py`, the CLI integration in `buddha/__main__.py`, six-decimal budget display in `buddha/progress.py`, associated tests, this report, the metadata evidence JSON and the supplied trace excerpt. No hosted CI or Git commit is claimed; this workspace has no Git repository. This closes the review/diagnostic follow-up and stops before any new paid execution.

## Subsequent completion, October 19, 2026

The user executed the prepared recovery run. It completed 63 calls, three candidate evaluations and one proposal for $0.300153 in recorded conservative cost, with no pending/unknown recovery operations or held recovery reservations. The original run remains unchanged and unresolved. See [the completion verification and codebase implications](FIRST-LIVE-RESULTS.md). Earlier zero-operation observations above describe preparation, not current recovery state.

## Request to salvage the original attempt

The user subsequently asked whether the original attempt could also be recovered and completed. Read-only reinspection confirms nine completed replies, one unknown operation without a saved receipt, matching original ledger hash and unchanged frozen source contracts. Reconstructing the original generation request confirms that it did not enable `store` or attach retrieval metadata. The official [Chat Completions retrieval contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/retrieve), rechecked during this follow-up, requires a stored completion. There is no supported ordinary API retrieval route for this original answer. This does not establish whether it was processed or billed.

Exact resume remains conditional on authentic evidence for that missing response, its provider identity and usage. A fresh response must not be inserted as though it were the interrupted request's original receipt.

The practical salvage design is a separately identified continuation: import the nine completed responses with their original receipt identities and explicit reuse provenance, generate a replacement tenth answer under a new operation/attempt identity, and finish the remaining frozen pilot stages. The source attempt keeps its unknown state and reservation; the continuation result must disclose the interruption and replacement. Imported responses incur no new API charge, while original charges remain in combined accounting. Neither this continuation command nor its cross-run funding enforcement exists yet; no continuation was prepared or executed here.

After the completed recovery's $0.300153, the original known $0.001709 and the retained unknown allowance of $0.532373, the unallocated remainder of the original $50 is **$49.165765**. The shared 128-call allowance leaves **55 new calls** after the original ten attempts and the recovery's 63 calls. The worst-case remaining original pilot requires 55 new calls if the nine completed responses are reused. These numbers describe a possible future allocation, not a newly created spending cap. A supported continuation must enforce it and prevent the same remainder being allocated more than once; the two original frozen per-run caps alone do not do so.
