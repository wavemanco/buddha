# One bounded reconstruction diagnostic

This records the completed bounded diagnostic for IMP-01 after the
[three-hour construction partial](conformance/history-read-3h-observation.json).
It uses the already retained synthetic prefix. It does not construct more history,
resume the study, advance an action or run a worker.

The question is which public functions consume time during one reconstruction.
Reuse the existing guarded prefix-profiler: call `_restore`, `_check_current`
and `reader.finish` once, with the same observation policy. Export only profiling
rows and callers belonging to the pinned public Python source inventory.

## Fixed scope

- One metadata-only binding of the exact retained v13 root, with one directory
  enumeration capped at 32 direct entries. Check only the three literal child
  names established by the fixture; refuse ambiguity or aliases.
- One profile attempt, with a 300-second cooperative timer and a 330-second
  external child deadline. Imports, preflight, final hashing and output all remain
  inside the external limit. No retry, resume or extension.
- Read only the selected new synthetic study/authority and its referenced inputs
  through the existing reader. The original paid run is not an input.
- Reject network/process operations, filesystem mutations and on-disk SQLite
  connections. Permit only literal in-memory SQLite and four fixed new child
  outputs. Retain parent logs and either complete or partial results.
- Compare raw study files and authority bytes before and after, and recheck the
  public source inventory. The old manifest and build evidence remain unchanged.

The metadata binding completed in 0.105 seconds: one direct entry, one candidate,
no retained-body reads and no SQL connections. Its retained record is
`runs/checks/v13-prefix-profile-20261103-v1/v13-prefix-metadata-binding-v1.json`,
SHA256 `0a7afcd63fe13f3df5f67d1666720d766d65a14ada45a1b28ac791c68e361e47`.
This establishes a fixed path for the diagnostic; it is not a ledger census.

## Actual result: November 3, 2026

The single attempt stopped as `partial_deadline` during `_restore` after
300.088 seconds. Its own timer raised `KeyboardInterrupt`; this was not a user
interrupt. The parent finished in 308.127 seconds, with child exit code 3 and no
external timeout. `_restore` did not return, so `_check_current` and `reader.finish`
did not complete. No terminal owner/operation census was obtained.

All 1,200 study files and the raw authority bytes matched before and after, as did
the metadata binding and all 364 public Python source pins. The guard recorded
no denied operation during the workload. The parent verified its driver pins.
These observations cover the selected study/authority, not every fixture input.
No API request, container, worker, construction or resume was performed.

The retained [delivery record](conformance/v13-prefix-profile-delivery.json) binds
the proposal, guards, raw results, public profile and logs. The scripts remain in
the named external check folder. Their `DRAFT` filenames are retained identities;
the original proposal is not rewritten to pretend it predicted the outcome.

## Concrete repair selected from the source trace

The saved profile contains 95 generated-evidence reads, 95 outcome validations
and 95 output validations, but 285 constructions of the corresponding `Answers`
object (`answers.py:288`). The public source explains the three interpretations:
`candidate_generation._outputs` parses and discards the object; `_validate_outcome`
parses the same artifact for its terminal-answer join; `_read_evidence` parses it
again for its return value. Each object already derives bounded native bytes,
but `native_bytes` derives them again: 95 calls and 380 total native derivations.

The next bounded repair carries the immutable parsed object and its **original
raw digest/path** through these helpers. Every existing fresh file read, hash
comparison, owner/task/agent/report/done join and final capture check must remain.
Compare subsequent reads to the original raw digest, rather than canonicalized
output bytes, so valid noncanonical JSON is not newly rejected. Retain the native
bytes already computed during construction; keep returned mutable views isolated.
This is local reuse within one evidence read, without a global or cross-owner cache.

Acceptance checks cover exact output/native bytes, one construction per evidence
read, changed-between-read rejection, valid noncanonical input, defensive copies
and unchanged fresh-read/final-check behavior. The 144 native-evidence calls for
48 native-stage occasions are a separate three-stage verification path; they do
not mean 144 different owners or justify relaxing those checks.

Repeated population validation is also visible: 1,388 validations traverse the
1,000-row synthetic population, with 1,402,373 release-loader calls. These counts
identify duplication; they do not establish its isolated wall-clock cost or a
sufficient improvement for the full history gate.

## Meaning of the result

This is a diagnostic of a retained prefix of unverified terminal size. It is not
the required 193-owner/660-operation case and does not run or replace that case's
900-second acceptance test. Instrumented timings cannot establish a speedup or
predict future study throughput. Cumulative profile times overlap; some retained cumulative rows exceed the
interrupt window. Interrupted/reentrant profiling and aggregation by public
function key prevent treating these rows as additive elapsed-time shares.

Use the result for the one local interpretation-reuse repair specified above. It does not automatically adopt another optimization chain, larger
build, new platform or paid handoff. [PLAN.md](PLAN.md) owns those decisions.

No operator command, API key or additional PowerShell window is needed: the agent
ran this offline diagnostic once. Its external parent enforced the stop limit.
No further profile or long build is scheduled by this record.
The generated profiler scripts and all outputs stay in the named check folder.
