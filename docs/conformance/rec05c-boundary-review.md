# REC-05C observation review

This slice diagnoses saved work. It does not resume execution, alter writer
formats, reconcile receipts, settle holds or identify a writer from missing data.
The [guide](../DOCTOR.md) documents the commands and their meanings.

## Reproduced findings

| Finding | Evidence and correction |
| --- | --- |
| Newer unrelated diagnostics hid outstanding failures | Initial runnable failures reproduced both newer success and newer unmatched uncertainty suppressing an older unknown. Selection now begins with outstanding ledger IDs; strict request/outcome validation precedes deterministic sorting. |
| Readable accounting was reported as running | An existing progress test first failed after its expectation was changed to observed. Writer identity remains unknown. A normal context return also no longer prints completion without a saved matching marker. |
| Existing locks cannot identify their writer | Search locks are empty; native locks contain only a PID. Read-only numeric PID observations remain separate from ownership, health, cancellation and cleanup. No stronger identity was invented or writer receipt introduced. |
| Genuine Windows native completion was rejected | Final baseline seal keys use the writer platform's relative-path spelling. Known complete Windows and POSIX mappings now both work; mixed or foreign completion populations do not. Writer bytes and stored seals remain unchanged. |
| Wrong final summary and source/task identities passed | Actual temporary-copy probes redirected the final summary to generation answers, or changed release/task hashes, while retaining genuine anchored stage records. The observer now binds the exact last sealed summary artifact, selected release and stage-zero task identity. |
| Duplicate or incomplete owner populations were misleading | A copied owner ID inflated physical counts. Partial owners and foreign completion seals could be ignored. Distinct original owner IDs, exact owner population and canonical owner-bound completion names now fail closed. Missing seals remain valid partial work. |
| Legal nonhex ledger IDs disabled observation | Initial progress integration failures traced to applying diagnostic-directory rules to general ledger IDs. Accounting retains those operations. Inapplicable diagnostic records are skipped. A separate runnable RED reproduced and fixed the same suppression in the CLI's compatibility summary reader. |
| A Windows path-leak assertion was weak | Comparing an unescaped Windows path with JSON output could be vacuous. The final helper compares escaped fragments. Its partial rerun was interrupted; it is not represented as a completed pass. The final full-suite result is recorded separately. |
| Unreadable input falsely implied an absent lock | Two runnable failures reproduced `absent` for missing or unreadable roots. Unobserved lock state is now explicitly `unavailable`. Two boundary checks and the existing CLI-watch check passed after correction. |
| The first full suite found a CLI compatibility regression | The 894-test run had one failure: watch without an authorization option passed an extra keyword to the existing entry point. The original call shape is retained when the option is omitted; the existing test was not weakened. The final full run is recorded separately. |

The first doctor/process checks failed on missing modules before implementation.
The stale-running and diagnostic-precedence checks also failed before their fixes.
Some later controls were added after source review or an independent probe; they
are not all claimed as tests-first unit tests. Earlier failures remain ignored
evidence under `runs/reviews`; delivery records their exact fingerprints.

## Checks actually performed

- The final focused doctor/watch target passed 20 + 18 groups before the last
  helper-only Windows assertion strengthening, with no skips or ResourceWarnings.
  Diagnostics then passed 31 groups, including the separately reproduced CLI
  plain-ID case. Process observation passed 15 groups.
- Twelve final native observation controls passed, including the genuine retained
  Windows baseline, both seal-key spellings, each reproduced substitution/population
  defect, and valid partial-stage controls. All 41 original proof files remained
  unchanged; observation used 78 memory-only SQLite connections under writer,
  execution, source-database, transport-preparation, signal and network guards.
- All three actual legacy histories were observed under equivalent read-only
  boundaries. All 287 previously preserved fingerprints and the pilot ZIP matched
  before and after. The original has nine complete calls and one unknown; recovery
  has 63 complete calls; continuation has 51. Shared costs remain 576,395 known,
  532,373 held and 124 physical attempts; all three actual owners remain inactive.
- The exact documented doctor commands also ran in fresh keyless processes:
  original exit 3, continuation exit 0. Those subprocesses have their own preserved
  input hash brackets; Python monkeypatch guards apply to the separate in-process
  observations rather than being claimed across the subprocess boundary.
- Eighteen source-preservation checks passed: financial and execution source bytes
  and the diagnostic transport writer AST remain unchanged. The generic
  in-memory binding helper was moved with its exact AST so native observation need
  not import legacy scientific verification algorithms.

The [delivery record](rec05c-delivery.json) supplies the final full-suite and hosted
CI status. [Actual legacy observations](rec05c-real-observation.json),
[native controls](rec05c-native-observation-review.json) and
[code preservation](rec05c-code-preservation.json) retain the measured scope.
The twelve native controls and actual legacy observations were refreshed after
the final source corrections. They use the same final package bytes as the final
full suite; earlier failure and intermediate proofs remain separately preserved.

## Limits

Input bytes are bounded and compared before/after observation, but no external
seal or atomic live snapshot is established. Unavailable/busy input has unknown
accounting, not zero cost. Existing locks cannot establish a matching, dead or
reused writer. Actual numeric PID queries ran on Windows locally; Linux syscall
behavior used mocks and awaits the new PR's hosted Linux execution.

Native completion observations check saved host report and anchor bindings; they
do not rerun the evaluator, verify judge semantics or certify safe resumption.
No lock removal, completion adoption, replacement owner, retry, reconciliation,
liability release, paid allocation or scientific improvement is introduced.
