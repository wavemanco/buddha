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

REC-03's hosted Windows and Ubuntu checks subsequently passed at [the exact PR run](https://github.com/wavemanco/buddha/actions/runs/39365951146).

## REC-04A source and receipt foundation

REC-04 is split into read-only source verification (A), executable continuation/accounting (B), and actual user live completion (L). Its original aggregate gate remains open until all three have evidence.

`read_source` accepts explicit manifest/ledger/archive seals and validates the supported one-prompt, one-proposal source. It requires exactly nine completed initial generation slots and a receiptless unknown tenth, reconstructs semantic operation IDs in generation order, and checks every fingerprint, reservation, model/tier/token bound and recorded charge. All ten independent requests can have the same fingerprint; a fingerprint is never used to infer the answer's position.

The returned source, receipt references and replacement reference are immutable. References use a new run's semantic IDs while retaining the exact original run/operation, generation index, reply, usage/identity, cost and seals. The source cannot masquerade as its own new continuation. These objects are evidence only; this slice creates no provider operation, authority binding, budget allocation or run manifest.

The old ZIP is treated as bounded, sealed data: entry inventory, relative regular paths, indexed hashes, size limits and source-contract bindings are checked without extracting or executing it in production. Five unchanged scientific modules require byte equality. Provider/run/search source is compared as normalized whole-module syntax with only enumerated host definitions/methods/import additions excluded; scientific methods, module/class assignments, constants and import bindings remain checked. Review reproduced later module and class rebinding that could evade a definition-only check; failing regressions now close both cases.

Three separate CI checks execute the sealed archived and current constructors in external temporary Python processes. They remove credentials from the child environment and block network/provider entry points. Actual call bodies/fingerprints, generation modes, empty/refused normalization, judge schemas/systems/scoring and deterministic archive/frontier/parent behavior match across the tested matrix. This complements static checks; it is not formal verification of all Python behavior. Future proposal feedback containing new protocol fingerprints is still explicitly different provenance.

The public `continuation-source` command exposes this read-only check. It was observed rejecting the missing command before implementation. The real original returned nine receipts, 1,709 micro-USD known and the same 532,373 micro-USD unknown hold; both historical manifest-file and ledger-file hashes remain unchanged. The source target first failed with a missing module, then passed 19 checks. Full local verification passed 348 tests in 41.088 seconds with one Windows symlink-privilege skip; Ruff across 36 files, strict mypy across 16 runtime modules, Bandit, runtime dependency audit and compilation passed. Hosted REC-04A CI is reported separately. No provider calls, keys or funding writes were used.

Seals establish consistency with supplied evidence, not independent provider authentication. REC-04B must still validate saved references at execution, bind the new runtime and atomically claim its funding before key entry. Passing this foundation does not mean a linked run has been prepared or completed.

REC-04A's hosted Windows and Ubuntu checks subsequently passed at [the exact PR run](https://github.com/wavemanco/buddha/actions/runs/39367369757).

## REC-04B linked execution and accounting

`continuation-prepare` publishes a new `buddha.policy-search-continuation.v1` manifest, source dataset, original source ZIP, exact current package source ZIP with MIT notices, and an empty operation ledger. The manifest retains the frozen scientific settings and explicitly records new runtime/protocol provenance. Its initial shared accounting snapshot determines its remaining local allowance. Existing preparation reuses that identity and allowance, including after paid progress; partial directories are retained for review rather than deleted or silently repaired.

One attached SQLite transaction binds the new run and accepts the original receiptless unknown as a still-held historical liability for that run. Conflicting claims roll back the local binding table, central registration and events together. Generic binding cannot claim a linked continuation. Repeated binding requires the exact existing claim and never repairs a missing acceptance. Neither preparation nor acceptance releases the old reservation or makes any provider call.

Loading checks the source seals, both source archives, current runtime, original settings/population, allowance snapshot and exact ordered receipt/replacement references. Execution reconstructs each inherited semantic request and checks its position, policy, fingerprint and receipt bounds before returning the stored reply. Those nine references create no physical operations, charges or call allocations. The tenth answer uses the new run's operation ID and retains explicit replacement lineage. Its durable receipt is replayed after interruption without another transmission.

The existing evaluator/search consumes the ordered evidence through the same generation, partition, quality, proposal and archive path. Both CLI and library execution require the bound shared authority even for synthetic linked demonstrations. A continuation report uses `buddha.policy-search-report.v2`: `costs` describes new physical operations; `inherited_costs` describes the nine saved answers; `evidence_costs` sums those evidence components; `authorization` reports the combined experiment, counting original costs once and retaining the unresolved original request. Candidate rows distinguish new and inherited evaluation cost. New physical operations reconcile independently with the local ledger and shared mirror. Saved reports are stable under cached replay and later run deactivation.

The supported continuation remains the bounded original pilot: one development prompt, two seed policies and at most one child proposal. It does not generalize recovery to arbitrary incomplete search states, release unknown receipts, change scientific treatments or validate meaningful diversity. Actual live completion remains REC-04L; tests and offline preparation cannot close it. Source self-modification remains a separate unimplemented part of the living plan.

Review produced failing regressions before closing three integration errors: synthetic linked execution could use a plain ledger; the watcher did not recognize the new report version; and a malformed runtime ZIP with consistently changed checksums raised a raw archive exception instead of `ValidationError`. A malformed manifest format also now returns the typed validation error. All fail before new provider execution where applicable. The native CLI was independently exercised with actual historical inputs in temporary copies, fixed-host mocked HTTPS, fake credentials and socket connections blocked; it completed 55 physical requests, reused nine replies, closed all 55 connections and returned identical cached results without credentials or further sends.

An operational preparation (`11e1ceeb4b1c40bf84a2e765c275ba8c`, authority `936dc3f0f5204617b5c7d561a1f836f6`) was published before that last archive-error review finished. It had zero new operations, cost or reservations and was permanently deactivated before any live command was released. Its original files and authority are retained. The corrected preparation uses a separately versioned authority with the same historical liabilities and total $50/128-call ceiling; the retired authority has no active runs. This is explicit replacement of an unspent preparation, not a fresh experiment, liability release or additional spending allowance. [Operational handoff](FIRST-LIVE-CONTINUATION.md) records the usable command and both preparation identities.

Final local verification passed 381 tests in 82.649 seconds with one Windows symlink-privilege skip; Ruff lint/format (39 files), strict mypy (16 runtime modules), Bandit, runtime dependency audit and compilation passed. Independent native CLI testing was repeated against final runtime `ae05baf34c5bc2e69cf1b462a82d6412a827eaa000f577b7cbe1cfcc31f3e81b`; all concrete review findings are closed within this slice's scope. Actual preparation passed source/runtime/budget checks with socket connections forbidden and no model calls. Both historical manifest-file and ledger-file seals still match. Hosted REC-04B CI is reported separately after publishing its PR.

The first hosted Ubuntu run passed; Windows exposed a fixture-only path mismatch in the narrow authority tests: the handcrafted manifest used the input temporary path spelling rather than `Authorization.path`'s canonical spelling. The production preparer already records the canonical value and its full continuation tests passed. A new equivalent-path regression first reproduced the failure locally, then the fixture was corrected to use the API's canonical identity. The strict runtime guard remains unchanged, as do the prepared runtime and funding. The expanded authority target has 13 tests; the next hosted full suite contains 382.

REC-04B's corrected commit passed hosted Windows and Ubuntu checks with 382 tests in [the PR workflow](https://github.com/wavemanco/buddha/actions/runs/39386398496). The subsequent command-documentation PR also passed [both platforms](https://github.com/wavemanco/buddha/actions/runs/39388883429). Earlier failed Windows runs remain historical evidence of the fixed fixture issue.

## REC-04L actual live completion

The user completed linked run `a486d90396934a45940637d77a168304`: 51 new physical calls, nine inherited replies, three candidate evaluations, one proposal and a complete v2 report. New recorded cost is 274,533 micro-USD; inherited evidence is 1,709 already-charged micro-USD; combined continuation evidence is 276,242. Shared accounting is 124 physical attempts, 576,395 known, 532,373 held and 48,891,232 available micro-USD, with four calls remaining under the original envelope.

Disposable-copy reconstruction with socket connections forbidden exactly matched the saved report. A separate review checked every new call fingerprint, usage/cost/receipt, all paired diagnostics, all candidate exports and all shared operation mirrors. The nine inherited slots have no new physical records, the tenth uses its explicit replacement ID, and original seals/unknown liability remain intact. Both reviews made zero model calls and preserved every input file. After verification, a separate append-only authority event deactivated the completed run; no run artifact, charge or hold changed.

[Results and limitations](LINKED-CONTINUATION-RESULTS.md) close REC-04's bounded recovery gate. They also preserve continued central-plot repetition, task/craft failures and task-specific policy instructions as development diagnostics. Official metrics stay unchanged; useful-diversity, transfer and source-evolution claims remain open. REC-05 supplies the remaining read-only verification and truthful process/diagnostic observation work.

REC-04L hosted Windows and Ubuntu checks passed in [the exact PR workflow](https://github.com/wavemanco/buddha/actions/runs/39390407380). NB-01 subsequently adds one exact old/new benchmark source-hash compatibility pair for validation-only provenance tightening, documented in [the benchmark audit](NOVELTYBENCH-CONFORMANCE.md#nb-c2-a-reproduced-provenance-defect-is-fixed). Valid scientific behavior remains covered by the archived/current executable comparisons; other source changes remain rejected. No frozen runtime or result is rewritten.
