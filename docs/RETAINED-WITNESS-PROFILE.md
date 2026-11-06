# Retained witness performance measurement

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
