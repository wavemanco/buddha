# Read the file again; interpret it once

This is the one local IMP-01 repair selected by the
[retained-prefix diagnostic](V13-PREFIX-PROFILE.md). A C1 artifact is the saved,
ordered set of answers from one agent. Reading its bytes and checking its identity
is necessary whenever the evidence is consumed. Rebuilding the same validated
answer object several times inside that one check is avoidable work.

The generated-evidence path previously interpreted the same artifact in its
output check, terminal-answer check and return-value construction. A small private
carrier now retains the parsed immutable object, its exact path and the digest of
the **original file bytes**. Every subsequent read still happens and must match
that path and digest before the object is reused. All owner, task, agent, report,
terminal, accounting and final capture checks remain in place.

Original bytes matter: valid JSON can have different spacing from Buddha's
canonical serialization. Reusing an interpretation must not start rejecting such
files. A later file with different bytes is still refused, even if it describes
the same answers. Returned dictionaries remain fresh mutable copies.

The immutable `Answers` object also retains the bounded native benchmark bytes
already computed during its constructor's existing validation. Repeated exports
return those bytes. This retains one additional derived representation for each
live object, bounded by the existing artifact limit; it is not zero-memory reuse.
There is no global, persistent or cross-owner cache.

## Verification and limits

All 55 focused tests pass. The old/current generation paths now construct one
answer object per evidence read, compared with two/three before. Their three/five
fresh capture reads are unchanged. Tests cover exact output/native bytes and
publication, noncanonical JSON, wrong paths, changed bytes after the initial
validation and before the final check, and mutation of returned views. Repeated
native export performs one conversion rather than reconstructing the population.

Configured Ruff/format, strict mypy, Bandit and in-memory compilation pass.
Dependency audits are reused from the byte-identical requirements. The
[delivery record](conformance/c1-interpretation-reuse-delivery.json) binds the
source and verification receipts. Test transcripts were saved afterward from
tool output and are explicitly labeled as normalized transcriptions; the original
process streams were not retained. The independent source review found no blocker.

These checks establish reduced duplicate work and preservation of the tested
validation behavior. They do not measure whole-history elapsed-time improvement
or pass the 193-owner/660-operation, 900-second acceptance gate. No retained
history, original paid record, provider, container or long construction was used.
The next preparation is a concrete comparable-size attempt on the repaired
source; no new long attempt or optimization chain is authorized by this repair.
[PLAN.md](PLAN.md) owns that next selection and its limits.

No operator command, API key or separate PowerShell window is needed for this
code change. It does not start an experiment.

## Current-source history-check preparation

The current preparation binds a clean, detached checkout of main's
`eacf8b8b` source. The source checkout is separate from this documentation PR,
so later documentation edits do not change the executing source binding.
The [current preparation record](conformance/current-history-preparation.json)
identifies the exact source, scripts, fixture inputs, hashes and output paths.

The earlier [integrated-v2 preparation](conformance/integrated-history-preparation.json)
remains a dated, unexecuted record for `3f73142a`. That source's full test run
failed; the corrected `6e163032` source later passed full qualification. Current
source includes the separately reviewed unused-hook removal and has short-CI
evidence. The older full result does not qualify this later source. Exact-source
full qualification remains required before paid execution.

The workload stays the same: build a synthetic history with 193 owners, 660
recorded operations, nine admitted decisions and no unresolved spending, then
check it in a fresh process within 15 minutes. The proposed construction limit
is three hours; setup, hashing and reporting add time. A construction timeout
means the read was never tested. There is no automatic retry or continuation.

The original eight public fixture files are kept in a separate, pinned input
directory. Seven match the current checkout; the eighth differs only by an
appended test class. The fixture files and the current 342 Python files have
separate hashes and real file origins. This preserves the old v4 workload while
using the current application. It does not test a full v5 study or establish live
capacity, memory use, improved scores or a better improver.

Preparation checks cover source/fixture hashes, unchanged workload and guard
syntax, actual source identity, file-origin helpers and all eight fresh output
destinations. They do not run fixture imports, history construction or the fresh
reader. No paid calls, real containers or original paid-run records are used.

The approved current-v3 attempt is now a construction-deadline partial: the
producer stopped after 10800.248537899926 seconds; the parent records partial
after 10802.99368519988 seconds. No producer terminal result or reader outputs
exist, so the 900-second reader did not run. The allowance is consumed; no
retry, resume, extension, new long run or paid work is authorized. The
[current observation](conformance/current-history-observation.json) retains
source/hash checks and the limits of sparse progress counters. Continue Buddha
and defer exact DGM adoption. Next reuse the existing forward screen, full
feedback, proposal and child-screen components, separating forward execution
from historical-reader reconstruction at their shared responsibility boundary.
A file move or an incremental-replay framework is not the fix. Scientific
controls and the original full comparison remain required; this smaller
engineering proof cannot replace them. The 193/660 replay gate remains unpassed;
prospective forward-route acceptance must be defined and reviewed before paid
execution. [PLAN.md](PLAN.md) owns the sequence.
[Existing reliability research](HARNESS-RELIABILITY-RESEARCH.md) supplies context.
