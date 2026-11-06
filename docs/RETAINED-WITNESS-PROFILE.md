# Retained witness performance measurement

## Completed observation: November 5, 2026

The single attempt completed in **27.64 seconds**, within its300-second limit.
It reproduced the saved passed witness and finished custody checks. Independent
review verified all297 frozen source hashes, the5 approved inputs,36 primary
capture receipts, the final profile and worker cleanup. These36 receipts are
not a count of all nested readers' inputs. No provider call, real container,
history write, rebuild, resume or retry occurred.

| Non-overlapping measured phase | Seconds |
| --- | ---: |
| Reader construction |4.45 |
| Witness reconstruction |16.79 |
| Final reader custody check |4.22 |

The profile recorded28.62million calls. Directory inventories consumed about
10.07 seconds cumulatively across39 calls:13 capture constructions and26 finish
checks. The cold parent collector ran **once**, taking6.22 seconds cumulatively.
Those function costs overlap the phases above and must not be added together.
The two reference reads were the parent and proposal, not duplicate parent reads.

No production performance change is justified by this cold case alone. Fresh
custody checks cannot simply be removed. The previously identified cross-stage
checked-parent handoff remains a candidate for a focused caller-count and
drift/context regression; this measurement did not exercise that dispatch path.
Path resolution was predominantly driver work, so it is not a production target.
The audit hook has no separate profile row, leaving its full overhead unquantified.

The final profile was saved before the first30-second sampling interval, so no
periodic sample was needed. The
[delivery receipt](conformance/retained-witness-profile-delivery.json) binds the
script, preparation, results, custody map, pstats and independent review. Raw
records stay in `runs/checks/retained-witness-profile-20261105-v1`. Preserve this
completed attempt; it does not authorise another profile or a capacity run.

## Method and limits

This supports PLAN D4: find where one saved mutation check spends its time,
before choosing a performance correction. It does not rebuild or resume the
experiment, generate answers, judge them or change the benchmark.

The selected input is the completed synthetic witness at
`forward-capacity/cells/0/0/0/1/witness` in the retained PR266 workspace. Use its
matching frozen source `815e15c78cea494e74407e75b3c4b3e843becd8a` at the original
path. Relevant reader files and scheduler functions were independently compared
with the current source; changing the old custody closure is unnecessary.

The invocation calls the existing `_witness` scheduler helper with the saved
declaration, parent, first starting screen, review/runtime and augmented control
map. It retains v5's settled-proposal treatment and the original observation
policy. It profiles reader construction, the witness read and `reader.finish()`
once. A returned outcome must match the saved passed report.

One attempt has a 300-second whole-command cap and requests a cooperative stop
around 240 seconds. Standard-library cProfile counters and public function/phase
snapshots are saved while work runs; final profile data is dumped if the worker
can finish its cleanup. A hard stop can leave an explicit partial without a full
profile. Missing data is not a successful measurement. There is no automatic
retry or deadline extension.

The child receives no API keys. Its guard permits the retained synthetic history
and frozen source as read-only inputs, memory-only SQLite interpretation, and
fresh local output/cache files. It refuses network, producer/container work and
retained-program host execution. The existing Windows process group bounds the
owned worker. Original source and approved input hashes are checked, and normal
reader custody checks remain. No user PowerShell command or key entry is needed;
Codex runs the prepared local check.

Report call counts, own time and cumulative time separately. Cumulative times
overlap and cannot be added. Guard/profiler overhead must be distinguished from
application work. One cold witness read does not measure the scheduler's retained
parent reuse, the last interrupted planning action, total study capacity or an
uninstrumented speedup. The historical stop cause remains unestablished.

Do not patch the application until usable measurements support a specific
inefficiency. Any correction needs a focused correctness check. The final full
Ponytail audit, independent agents and adversarial review of removals remain
outstanding in PLAN D5b before the next candidate freeze.
