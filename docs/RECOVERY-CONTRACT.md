# REC-01: recovery and shared authorization contract

This is the technical contract for REC-01 in [PLAN.md](PLAN.md), not a second roadmap. It preserves the scientific evidence and defines the boundaries the following recovery slices must implement. No model request is authorized by this document alone.

## Historical evidence

`read_history(directory, manifest_sha256=..., ledger_sha256=...)` produces an immutable snapshot from the existing manifest and SQLite ledger. The manifest seal hashes canonical content excluding its checksum field; the ledger seal hashes complete file bytes. Reading must not create, migrate, lock for writing, reconcile or alter the source run. It checks manifest/config identity, supported schema, valid operation states, completed receipt identity, and consistent before/after source bytes. Pending journals, symlinks/reparse paths and an existing writer lock are refused rather than guessed safe.

Completed and unknown receipts retain their real identity and usage. An unknown receipt may contain the very model/identity mismatch that made it uncertain; importing its liability must preserve that evidence rather than discard it. This snapshot establishes consistency with an operator-supplied seal, not independent provider authentication.

The existing original and completed recovery are read-only historical sources. Their scientific manifests and ledgers remain unchanged. Their $0.301862 known charges, $0.532373 unresolved hold, and 73 attempted/allocated calls enter shared accounting exactly once. A repeated import of identical evidence is idempotent; changed evidence conflicts.

## One shared spending authority

The authority's immutable terms are currency USD, cap 50,000,000 micro-USD and 128 calls for this experiment, plus a hash of the reviewed scope. A source/run binding identifies the exact manifest, ledger and executable runtime, and whether it is historical/inactive or active. Omitting or changing a required authority binding must fail before key prompting or provider dispatch in the current paid CLI/library path.

New per-run ledgers remain durable local records. One authorization SQLite database owns the combined limit. Its operation-level liabilities and the active run's ledger transitions commit together using a single transaction with the run database attached. Independent writes followed by best-effort repair are insufficient. Use on-disk databases, rollback journals and full synchronization; reject unsupported journal modes, foreign schemas and unsafe path bindings.

SQLite documents attached-database atomicity only under the relevant on-disk/non-WAL conditions, and describes its multi-file commit protocol. The implementation must check those conditions and fault-test rollback. This does not promise protection from a filesystem or device that violates SQLite's assumptions. [ATTACH contract](https://www.sqlite.org/lang_attach.html), [atomic commit](https://www.sqlite.org/atomiccommit.html).

Authority records comprise immutable terms and run bindings, operation-level accounting, explicit historical-unknown acceptance and append-only events. Derive available cost/calls from those records; do not independently decrement a mutable remainder. Reserve before dispatch, serialize competing reservations, reject cross-run ownership conflicts, and record a known overrun before halting subsequent spending.

Historical sources are inactive. Their older standalone caps are not fresh authority to spend again. Every newly uncertain active operation halts new paid dispatch across the shared authority until reviewed. The original unknown is an explicitly accepted, still-held historical liability for this declared continuation; accepting it never means it completed or was free.

## Local preparation and transmission

Required local diagnostics/request preparation belongs before the durable dispatch boundary. A provably local pre-HTTP preparation failure must remain a truthful, safely resumable unsent operation rather than becoming an unknown provider outcome. A reserved operation may still hold a future spending allocation; that is different from a possibly billed dispatch.

After possible transmission, timeout, keyboard interruption, non-200 status, failed parsing or process death is not proof of cancellation. Preserve reservation and available evidence. Never make an automatic replacement merely because a response is absent or a lock is old. The controller's unknown-stop policy must be enforced at the authority boundary, not inferred from the next operation ID happening to hit an old failure.

## Inherited responses and replacement

The continuation receives a new run identity. Each inherited semantic slot identifies the original run and operation, exact request fingerprint, immutable normalized reply/hash, original model/request ID/usage, original charge, task/policy/stage/index, and source seals. Before reuse, the reconstructed current request must match the saved request fingerprint and all receipt bounds. A new runtime version is disclosed separately from the inherited scientific evidence.

Inherited replies are evidence references, not new provider operations. Reuse creates no invented dispatch, new charge or extra call allocation. The source's existing charge remains in combined accounting once. The replacement tenth response has a new operation/attempt identity and an explicit link to the original unknown; matching request content does not make it the same provider operation. The original unknown remains untouched.

A source may have at most the declared active continuation allocation. Repeated/concurrent preparation cannot create competing continuations or allocate the same remainder twice. New paid cost, inherited evidence cost and combined experiment accounting are reported separately and reconciled. Crash/restart after a durable replacement receipt must replay it without retransmission.

## Source and scientific versioning

Old v1 manifests keep their original runtime guards. They must not be hash-bypassed or relabeled after core edits. Exact historical reconstruction uses the preserved matching source in an external temporary copy, with network disabled and input/output hashes checked.

The continuation is a new explicitly versioned protocol: same source prompt, policy space, original proposer/judge templates, model access, limits and search rules; declared new accounting/runtime and inheritance metadata. Protocol fingerprints therefore change honestly. Those fingerprints appear in proposer feedback, so byte-identical future proposal payloads are not promised merely by matching settings. Verify scientific request bodies and archive rules against the archived constructors, and disclose any metadata-only difference. Do not claim that new host code is the old implementation.

## Acceptance gates by implementing slice

| Gate | Required evidence |
| --- | --- |
| REC-01 | Tests first fail without the historical reader; sealed valid histories load read-only, and malformed/tampered/foreign histories fail without source mutation; contract and runtime/version boundaries recorded |
| REC-02 | Historical imports reconcile exactly; idempotency and ownership checks; competing runs cannot exceed either combined cap; inactive or omitted-authority denial; injected failure rolls back authority and active-ledger effects together; overruns remain durably recorded |
| REC-03 | Pre-send diagnostic failure makes zero HTTP attempts and never creates provider uncertainty; genuine ambiguous sends remain held; safe resume, stop scope and diagnostic evidence verified through the actual broker path |
| REC-04 | Nine authentic inherited replies require zero new calls/charges; new tenth has replacement lineage; original hashes unchanged; duplicate/concurrent continuation denied; restart does not retransmit; complete report separates inherited/new/shared costs |
| REC-05 | Read-only inspection changes no bytes or locks; dead-writer state is not mislabeled proven alive; outstanding diagnostics are not hidden by a newer unrelated success; no liability release based only on elapsed time |

These are independent gates. A passing REC-01 reader is not a functioning continuation or machine-enforced shared budget.

## Git, checks and cadence

The pre-recovery implementation is preserved in the repository's baseline commit and the matching source ZIP. Every following slice uses its own branch, conventional commits and PR with the implemented plan IDs, validation and remaining limits. PRs may be stacked without merging unreviewed work. The user's latest instruction authorizes continuing after slice summaries until a live run or user decision is required; it supersedes the earlier default of stopping after each slice.

CI runs tests, lint, types, code security, runtime dependency audit and compilation on Windows and Linux/Python 3.13. Tool actions and the development dependency closure are pinned. Development tooling includes certifi under MPL-2.0 through the audit tools; it is not an application runtime dependency or bundled agent library. The application remains standard-library-only. Direct tool license observations: Ruff/mypy MIT, Bandit/pip-audit Apache-2.0. This is a recorded development-tool decision, not approval to introduce copyleft into a distributed application path.

## REC-01 observed verification

The new historical-reader target first failed with `ModuleNotFoundError: buddha.history`. Its implementation then passed 15 target tests with one Windows symlink-creation privilege skip. The complete suite passed 260 tests in 23.874 seconds with that same skip; Ruff lint/format, strict mypy (14 modules), Bandit, runtime dependency audit and compilation passed locally. Hosted CI is reported separately after the PR runs.

The new reader was exercised against both actual historical directories. It returned the original ten operations ($0.001709 known, $0.532373 held) and the completed recovery's 63 operations ($0.300153 known), preserving both full ledger hashes. The nine original core source files remain unchanged. No keys or provider calls were used. The CI source checkout preserves exact bytes rather than normalizing the source hashes' Windows line endings.
