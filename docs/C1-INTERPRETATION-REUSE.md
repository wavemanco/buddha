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
