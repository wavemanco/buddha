# REC-01: recovery and shared authorization contract

This is the technical contract for REC-01 in [PLAN.md](PLAN.md), not a second roadmap. It preserves the scientific evidence and defines the boundaries the following recovery slices must implement. No model request is authorized by this document alone.

## Historical evidence

`read_history(directory, manifest_sha256=..., ledger_sha256=...)` produces an immutable snapshot from the existing manifest and SQLite ledger. The manifest seal hashes canonical content excluding its checksum field; the ledger seal hashes complete file bytes. Reading must not create, migrate, lock for writing, reconcile or alter the source run. It checks manifest/config identity, supported schema, valid operation states, completed receipt identity, and consistent before/after source bytes. Pending journals, symlinks/reparse paths and an existing writer lock are refused rather than guessed safe.

Completed and unknown receipts retain their real identity and usage. An unknown receipt may contain the very model/identity mismatch that made it uncertain; importing its liability must preserve that evidence rather than discard it. This snapshot establishes consistency with an operator-supplied seal, not independent provider authentication.

The existing original and completed recovery are read-only historical sources. Their scientific manifests and ledgers remain unchanged. Their $0.301862 known charges, $0.532373 unresolved hold, and 73 attempted/allocated calls enter shared accounting exactly once. A repeated import of identical evidence is idempotent; changed evidence conflicts.

## One shared spending authority

The authority's immutable terms are currency USD, cap 50,000,000 micro-USD and 128 calls for this experiment, plus a hash of the reviewed scope. A source/run binding identifies the exact manifest, ledger and executable runtime, and whether it is historical/inactive or active. Omitting or changing a required authority binding must fail before key prompting or provider dispatch in the current paid CLI/library path.

New per-run ledgers remain durable local records. One authorization SQLite database owns the combined limit. Its operation-level liabilities and the active run's ledger transitions commit together using a single transaction with the run database as `main` and the authority attached as `funding`. Independent writes followed by best-effort repair are insufficient. Use on-disk databases, rollback journals and full synchronization; reject unsupported journal modes, foreign schemas and unsafe path bindings.

SQLite documents attached-database atomicity only under the relevant on-disk/non-WAL conditions, and describes its multi-file commit protocol. The implementation must check those conditions and fault-test rollback. This does not promise protection from a filesystem or device that violates SQLite's assumptions. [ATTACH contract](https://www.sqlite.org/lang_attach.html), [atomic commit](https://www.sqlite.org/atomiccommit.html).

Authority records comprise immutable terms and run bindings, operation-level accounting, explicit historical-unknown acceptance and append-only events. Derive available cost/calls from those records; do not independently decrement a mutable remainder. Reserve before dispatch, serialize competing reservations, reject cross-run ownership conflicts, and record a known overrun before halting subsequent spending.

Historical sources are inactive. Their older standalone caps are not fresh authority to spend again. Outstanding dispatches and newly uncertain active operations halt further paid dispatch across the shared authority until reviewed or completed. The original unknown can be explicitly accepted as a still-held historical liability for one declared continuation; accepting it never means it completed or was free. A historical unknown with a received but uncertain identity/tier receipt cannot use this narrow acceptance route: its configured reserve may not bound that different instrument.

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

REC-01's hosted Windows and Ubuntu checks subsequently passed at [the exact PR run](https://github.com/wavemanco/buddha/actions/runs/39339066430).

## REC-02 implementation and boundaries

`Authorization` owns immutable USD/call caps, the exact readable scope and its internally derived canonical checksum. Historical imports are sealed, inactive and idempotent. An empty new run receives an immutable `authorization_binding` extension (its own schema version 1; underlying ledger schema remains 2) in the same transaction as the authority registers the run. It binds authority identity, canonical path and terms checksum. Binding that same run to a different authority is refused, including before its first call.

`AuthorizedLedger` reuses existing operation transitions. It checks exact SQLite schema definitions, path identity, local configuration and an independent authority mirror before each transaction; it never repairs a lowered local liability from that local record. Both databases must use DELETE journals and FULL synchronization. One `BEGIN IMMEDIATE` serializes shared allocations even when different processes have different run databases as `main`. A failed transaction rolls back both effects. Known overrun usage is committed before stopping subsequent spending.

The live CLI requires `--authorization` before loading scientific source or prompting for keys. The HTTP broker refuses an unbound ledger; a custom transport also cannot dispatch a new non-replay model operation without authority. Completed offline receipts remain replayable without a paid transport. `run_baseline` and `run_search` accept the same explicit authority, so the financial guard is part of the library path too.

The constructor captures the authorized runtime and manifest identity. New reservation/dispatch checks the currently installed source and manifest. Completing or marking an already-dispatched operation uncertain uses the captured identity, so editing source while a call is in flight does not discard its response or usage. The next new paid operation is still refused. This is not a hostile-host sandbox: someone running an archived executable, replacing host files or directly using credentials is outside this guard. Future generated code must run behind SRC-01's separate boundary.

Offline CLI commands are `authorization-create` (explicit caps/scope), `authorization-import` (operator-supplied source seals), `authorization-bind` (empty scientifically validated run), `authorization-inspect` (read-only combined accounting) and `authorization-deactivate` (append-only stop). Creating a database records an authorization; it does not grant additional user permission to spend. There is no general unknown-release/retry command. The continuation-specific acceptance API preserves the old hold and will be used only after REC-04 verifies its provenance.

The binding extension is permanent once published. It is not a legacy-ledger migration and has no supported destructive rollback after a run is bound. A binding-publication failure rolls back the new table and authority registration together; an operator preserves any spent/bound run and uses a forward fix rather than deleting its history.

Independent review reproduced and closed two defects before this slice was committed: source drift could discard returned receipts; an added SQLite trigger could reset dispatch state and enable repeat sends. Runnable broker regressions cover both. A further observed limitation, **REC2-F1**, remains scheduled in REC-05: legacy `Ledger.complete` can retain an earlier immutable unknown-receipt row, while the historical reader currently rejects that legal reconciled state. The actual two imported histories do not contain it. General receipt reconciliation/import is not claimed by REC-02.

Verification imported both actual histories twice into a temporary authority. Combined totals were 301,862 micro-USD known, 532,373 held, 834,235 committed, 73 operations, 49,165,765 available and 55 calls remaining; both runs were inactive, and repeated import created no additional events or allocation. Both original manifest-file and ledger-file hashes stayed unchanged. The temporary authority was an offline check, not another operational spending allocation. The linked continuation remains REC-04 work; local preparation remains REC-03 work.

Local verification passed 307 tests in 32.771 seconds with one Windows symlink-privilege skip, Ruff lint/format across 32 files, strict mypy across 15 runtime modules, Bandit, runtime dependency audit and compilation. New authority/entry-point/schema/receipt targets were observed failing before their implementations or fixes. Hosted REC-02 CI is reported separately after the PR runs. No live model calls or credentials were used.

REC-02's hosted Windows and Ubuntu checks subsequently passed at [the exact PR run](https://github.com/wavemanco/buddha/actions/runs/39340445692).

## REC-03 implementation and unsent boundary

The actual HTTP broker now reserves, prepares, performs an authorization-checked dispatch compare-and-set, then transmits once. `HTTPTransport.prepare` returns an immutable per-operation `PreparedHTTP` with serialized body, fixed destination, immutable headers, a connection constructed without connecting, and safe diagnostic metadata. Headers/body/connection are excluded from its representation. The broker owns connection cleanup on dispatch failure and normal exit; no mutable prepared state is cached on a transport.

Diagnostic preparation checks the explicit operation identity/fingerprint against the run ledger, validates or atomically publishes the required request record, and finishes before connection construction or dispatch. An existing record must match every fixed field, schema, checksum, timestamp shape, adapter hash and canonical UUID. It is preserved on conflict. If publication succeeds and the local caller then fails, a retry reads the same UUID and exact request-file bytes. Concurrent preparations still require the ledger's single dispatch winner.

A preparation error leaves both accounting records `reserved`, with the existing allocation held and no dispatch event. Retrying that same operation after fixing the local error is safe. After dispatch, HTTP failure, timeout or interruption before a valid reply remains ambiguous and held; neither the same operation nor a different operation bypasses shared stopping rules. Optional outcome construction/writes/warnings and ordinary close exceptions cannot discard a received reply. An interruption in optional success logging carries the authentic reply to the broker; identity, cost and bounds are recorded before the original interruption propagates. Connection cleanup runs after terminal recording too. Arbitrary process death between receiving a reply and committing its ledger record still requires conservative recovery; no claim of provider-side transactional delivery is made.

This change does not relabel the original historical unknown as unsent: its saved trace reached SSL header reading. The old evidence and held liability remain unchanged. Direct low-level diagnostic `send` remains defensive against repeated prepared requests; paid execution uses the broker's two-phase interface.

The initial ten-case composed target produced five assertion failures and four missing-interface/receipt-preservation errors before implementation. It now has 18 cases covering local-write failure/resume, publication-then-failure UUID reuse, malformed records, plain HTTP constructor failure, deactivation and dispatch-loss cleanup, concurrent preparation with one sender, sequential per-call isolation, true timeout stopping, optional outcome/close failure, interruption propagation and representation redaction. Review observed three additional failing assertions before the received-reply interruption fix. Existing credential/HTTP/parser/diagnostic coverage remains active. Both historical ledger hashes remain unchanged. Hosted REC-03 CI is reported separately; no live model calls or credentials were used.

Full local verification passed 325 tests in 38.785 seconds with one Windows symlink-privilege skip; Ruff lint/format across 33 files, strict mypy across 15 runtime modules, Bandit, runtime dependency audit and compilation passed.
