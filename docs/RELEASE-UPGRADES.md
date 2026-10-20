# Benchmark upgrades and retirement

[PLAN.md](PLAN.md) owns the work order. [The integration contract](BENCHMARK-INTEGRATION.md)
defines compatibility; [the native baseline guide](NATIVE-BASELINE.md) defines execution.
This guide explains what changes when a compatible evaluator release changes.

## First baseline on a new release

1. Install the official source and its reviewed dependency environment in their
   own directories. Pin the source, lock and installed files. Keep the old release
   separate; a shared directory containing every release would bind them all.
2. Supply release data: dataset and field names, ordered answer count, Python
   module commands and literal arguments, expected artifact paths, and required
   provider capabilities. Supply the configured native hooks and artifact flow.
   Configuration names functions in the installed evaluator; it does not replace
   their judgment rules or run shell expressions.
3. Check the selected source, installed/import closure, supported outer interface
   and direct/native fixture agreement. Unsupported capabilities need an explicit
   reviewed extension. Bad stories, repetition, empty answers, refusals and invalid
   task-requested JSON are baseline outcomes, not compatibility failures to hide.
4. Keep the existing agent source, instructions, generation model, sampling and
   limits fixed. The required answer count comes from the task. Before any real
   calls, verify current provider bounds, keys and a concrete shared allocation.
5. Run the native baseline and retain all answers, replies, native results and
   summary. An optimizer mapping is optional: a changed native metric does not
   need to be renamed or understood by search before its first baseline runs.
   Agent changes made after seeing that baseline are separate treatments.

The current envelope supports bounded text/JSONL tasks, ordered text answers,
sealed Python module commands, and the two reviewed provider capabilities.
An unknown interface is rejected; this is not a promise that an arbitrary future
release needs no engineering. No new paid command or allocation is supplied here.

## Retire a release without losing its records

Close its active allocations before removing its executing source/environment
from active selection. Archive its source, locks, configuration, selected files
and scientific artifacts. Preserve the original financial databases and their
locations. Removing a release never releases an unknown request's reservation.

`buddha.gateway_history.read_gateway_history()` reads a Gateway owner's recorded
manifest and SQLite ledger using explicit manifest and database hashes. It
checks the bytes against those hashes and returns recorded operations, replies,
known charges and retained holds. Earlier uncertainty receipts and later terminal
receipts remain separate; the terminal charge is counted once. Returned records
are immutable or independent copies. It opens no provider connection, reads no
key, installs no old evaluator, migrates nothing and grants no permission to spend.

The reader consumes a bounded, sealed in-memory copy of the database. It rejects
unsafe paths, active SQLite sidecars, unsupported schemas, inconsistent request
identities and changed evidence. Its ceilings are 512 MiB per ledger, 64 MiB per
serialized raw receipt and 100,000 operations. These are reader resource limits,
not token limits or financial authorizations. The larger receipt ceiling covers
the base64 representation of a legal 16 MiB request plus 16 MiB response.

Recorded source inventories are historical data. An old manifest with the former
ten-module core remains readable after the active core becomes nine modules.
Running that old owner still requires its original runtime; a read-only view
does not waive execution guards. Local hashes establish consistency with saved
bytes, not provider authenticity or invoice reconciliation. Unsupported future
record formats need a separately tested reader extension.

The older pilot/search receipt format uses `buddha.history` instead.
[REC-05A](RECOVERY-CONTRACT.md#rec-05a-retained-receipts-and-sealed-reads) now
preserves its earlier and terminal replies too. Search verification and writer
diagnostics remain REC-05B/C. The two reader formats remain separate; neither
migrates historical financial records.

The shared paid core now obtains generic JSON and validation helpers from
`buddha.common`. The old scientific modules re-export those same helpers for
their existing callers. New Gateway owners bind the nine-module executing core;
older owners retain their original ten-module identity. The old continuation
compatibility check recognizes only the two exact reviewed extraction revisions
and the exact common-source hash, while retaining its original NB-01 revision
pair and all other scientific-source checks. An archive using the extracted
helpers must also contain their exact sealed source. The original pilot archive
needs no new member. No old run is rebound or migrated.

## Observed scope

[The two-release evidence](conformance/nb03c-compatible-releases-evidence.json)
records the same frozen agent, generation settings, generic controller and runners
across changed counts, fields, module arguments, paths and native summary schemas.
The host copy physically lacks the old scientific modules and cannot import the
judge SDKs. Both native baselines match direct execution, including billed parse
retries, refusal fallback and truncation. Poor/repeated text, invalid task JSON,
the seed's declared `[empty]`/`[refused]` markers and unchanged truncated text
reach native assessment. Original provider replies remain in the receipts.
No optimizer projection is supplied.

This proof records 18 mocked sends, seven direct SDK captures, zero real calls,
unchanged source inventories and no remaining owned containers. Archiving A's
active roots preserves its sealed records and its 100,200-microusd synthetic
unknown hold. New B spending then stops before credentials or an operation,
despite ample available money and calls. These are deliberately different canned
instruments, not claims about an unknown future official release.

[The separate official regression](conformance/nb03c-official-regression-evidence.json)
runs the actual pinned NoveltyBench partition, score and summary commands after
the core extraction. Its generated-data artifacts and request-body multisets
still match unchanged direct oracles: 26 mocked sends, six direct captures and
zero real calls. It also preserves original-owner interruption/resume and keyless
complete reuse. The earlier official evidence remains historical and unchanged.

## Offline checks

These commands run once in the current PowerShell window. They create temporary
fixtures, use fake keys and mocked HTTP, and spend nothing. They need no evaluator
download or real API key. Ctrl+C stops a foreground check.

```powershell
python -m unittest discover -s tests -p test_common.py
python -m unittest discover -s tests -p test_gateway_history.py
python -m unittest discover -s tests -p test_continuation_common.py
```

The first checks the extracted generic helpers against their preserved original
behavior and verifies that the paid core can load without the old benchmark
modules. The second checks sealed historical reads, retained receipts and costs,
malformed evidence, resource limits and an actual former-core record. The third
checks narrowly reviewed legacy source compatibility and rejects changed or
missing helper dependencies without changing historical records.

The optional composed proof requires the already prepared C3A Docker image and
installed inventory described in [the confined evaluator guide](CONFINED-NATIVE-EVALUATION.md).
A clean checkout alone lacks those ignored inputs. It runs once in this window,
creates only fixture directories and containers, uses blocked network and fake
HTTPS, and writes evidence under `runs/reviews/`. It spends nothing and needs no
real keys. Ctrl+C stops it; interrupted fixture evidence may remain for review.

```powershell
python docs/conformance/nb03c-compatible-releases-probe.py
```

It runs the same frozen agent and generic pipeline across two deliberately
different canned releases, compares original evaluator artifacts and SDK request
bodies with direct execution, archives the old fixture release, and checks that
its retained uncertainty still blocks new shared spending. The fixtures test the
compatibility contract; they are not new official NoveltyBench versions or
evidence of creative improvement.
