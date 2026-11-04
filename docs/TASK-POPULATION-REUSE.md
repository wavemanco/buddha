# Reuse a validated task population

Selecting one task previously checked the entire source dataset twice: once to
find the selected row and again when constructing the selection. Constructing
saved answers also rebuilt a population its nested task artifact had just
validated. The [retained source trace](V13-PREFIX-PROFILE.md) identified these
repeated traversals; its counts predate this change.

Each newly loaded `TaskSet` still validates the complete source, including rows
outside its selection. After those checks succeed, it retains an immutable tuple
of frozen tasks and serialized original rows. Selecting from that exact object
checks the requested IDs, order and counts against this validated population.
The new selection shares the tuple and retains the full sealed source.

Native answer conversion decodes only the selected derived rows. Original
metadata, paraphrases, typed IDs, literal answers and native output fields retain
their existing meaning. A selection can still recover another ID from the
original source. Public record views remain independent mutable copies.

The optimization applies to the exact `TaskSet` class. Subclasses keep the
original constructor and native population-validation paths. Shallow copying,
deep copying and ordinary trusted pickle round trips remain supported; pickle
is not an input format for untrusted artifacts.

## Integrity and memory

Every external artifact construction retains the full release/dataset digest,
strict JSON/UTF-8, complete-row, derived-task and selection checks. Internal
selections retain bounded canonical serialization. Existing file reads, content
hashes, provenance, owner/terminal/accounting joins and final capture checks stay
in place. The population helper's dictionary interface remains compatible with
the policy panel and analysis code.

The tuple adds retained memory for all original row strings, tasks and tuple
entries. Derived selections share it; independently loaded task artifacts each
derive their own representation. Its size follows the bounded source and row
population, and can exceed the original JSONL spelling after serialization.
This is an additional per-object representation, with no zero-memory or fixed
whole-process RAM claim. Each derivation still visits the cached entries to
build a temporary lookup dictionary; it avoids parsing and validating every row
again. That lookup's time and memory scale with row count.

This representation belongs to validated task objects. The evidence reader's
resident-byte policy remains zero and its reads still obtain current file bytes.
No global cache or cross-owner evidence token is introduced.

## Evidence and remaining work

The [delivery record](conformance/task-population-reuse-delivery.json) records
the genuine before-change failures, final checks, exact source cuts and review.
It keeps public interfaces and original native/artifact bytes separate from
work-count measurements.

All 78 focused checks pass. Strict population-validation calls fall from two to
zero for an internal selection, and from two to one when loading saved answers.
The composed source-screen checks observe one initial validation for the task
view and controls, then zero additional validations for materialization and
preflight. Their artifact, metadata, mutation and final-check assertions remain.

Reduced population traversals do not establish an elapsed-time gain. V14 remains
a construction partial at its three-hour deadline; its fresh-reader test never
ran. The 193-owner/660-operation, 900-second reconstruction gate remains open.
[PLAN.md](PLAN.md) owns the next timing proposal and final source/handoff checks.
This change does not select another long build or authorize paid execution.

No operator command, API key or separate PowerShell window is needed for this
code change. It does not start an experiment.
