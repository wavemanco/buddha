# Recovering the saved-evidence limit

The October 28 unified comparison stopped during development because Buddha's
saved-record checker reached its cumulative 1 GiB allowance. This is a harness
capacity failure. Adding API credit or restarting the unchanged command does
not resolve it. Keep the stopped run and all its files.

The saved observation records 604 attempts, $4.845090 spent and committed, and
zero held. Final assessment and both plain-model references had not started.
These are local accounting figures, not reconciled provider invoices. The
experiment is incomplete; none of its scientific completion gates close.

## What failed

The original checker accumulated 1,070,166,023 bytes of consumed evidence. Its
next file, `screen/tasks/2/evaluation/command-3.json` in the eighth counted
child's screen, contained 4,018,013 bytes. Only 3,575,801 bytes remained under
the 1,073,741,824-byte allowance. The file passed its individual observation;
adding it to the study-wide observation failed.

The exact saved state reproduced this error in a read-only check lasting
786.763 seconds. The check blocked writes, on-disk SQL connections, network
calls, subprocesses and execution of generated source. Only trusted error
locations, file sizes and cumulative counts were emitted. It inspected no
task, answer or generated-program meaning.

Much of the volume comes from repeated configuration and import inventories.
The controller also reconstructs the accumulated history repeatedly and
repeatedly decodes large task descriptors. These are concrete sources of work;
their share of the original twenty-hour runtime has not been measured.

`launch_stopped` hides the underlying exception. During the separate recording
phase the progress display has no selected budget, so it prints `accounting
unknown`. The saved observation nevertheless recovered all four grant totals.
Recording performs checks and saves a diagnostic; it starts no provider calls.

## First repair slice: bounded passive reading

The new reader stores each consumed path's original size and SHA-256 digest
instead of keeping every file's bytes in memory. A later read must match that
original receipt. The final check rereads the files, checks database sidecars
before and after, and checks the original folder inventory. Changed files do
not become a new accepted baseline.

The default cumulative allowance remains 1 GiB. A private, explicitly selected
`buddha.evidence-observation-policy.v1` can declare a larger finite allowance:

| Field | Meaning |
| --- | --- |
| `format` | Exactly `buddha.evidence-observation-policy.v1` |
| `max_total_bytes` | Positive integer cumulative allowance, at most 64 GiB |
| `max_resident_bytes` | Exactly zero: this version keeps no persistent raw-byte cache |

The allowance is fixed when a capture starts; nested captures inherit the
selected policy. Leaving the policy scope restores the default for new
captures in the same execution context. A future launcher must explicitly
apply the policy in its reader thread; it does not automatically spread to
new threads. Individual file limits, local folder-entry limits, link rejection,
original fingerprints and changed-byte checks remain enforced. A new consumed-
path limit also covers external inputs. This bounds retained
raw bytes, not total Python memory or total reread work. Rereading can add I/O;
this slice does not claim a runtime speed improvement or full-grid capacity.

No production launcher selects this new policy yet. The original executing
tree, scientific setup, grant terms, owners, receipts and spending remain
unchanged. Passing a passive check does not authorize paid continuation.

A separate raw-byte rehearsal uses 2,653 actual retained trial, executing-source
and static-preparation paths: 1,123,069,491 bytes. The default allowance refuses
them; an explicitly selected 4 GiB allowance checks every original fingerprint
successfully, with no persistent raw cache. This exercises real record volume,
not complete study reconstruction, SQL interpretation or continuation. Its
8.753-second raw-only timing cannot be compared with the 786.763-second full
reconstruction as a speed improvement.

## What must happen before another paid start

The [owner-census repair](RECONSTRUCTION-COST.md#owner-census-work) now avoids
decoding the same task population for every file belonging to one owner. Its
work-count and adversarial tests preserve the original owner/funding checks;
they do not establish an end-to-end runtime improvement or enable continuation.

[PLAN.md](PLAN.md) owns the sequence: finish bounded-reader verification,
repair repeated reconstruction and safe error reporting, then implement and
rehearse an explicit continuation across the old and new helper versions.
Recheck complete-grid file/byte capacity, original accounting, source identity,
confinement and outgoing provider settings before a new local handoff.

The continuation must preserve original paths, grants, manifests, receipts,
unknown requests and all charges. Editing frozen source hashes, deleting
evidence, replacing owners or importing trial work into an unrelated grant is
not recovery. No continuation or paid restart command is supplied by this
first slice. No additional funding is requested.
