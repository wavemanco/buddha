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

## Specific stop reasons

The repaired source, policy, improver and unified launchers now preserve these
fixed codes in terminal output and new partial records:

| Code | Plain-English meaning |
| --- | --- |
| `evidence_total_bytes_limit` | The combined files exceed the observation's byte allowance. |
| `evidence_field_bytes_limit` | One file or field exceeds its individual allowance. |
| `evidence_path_count_limit` | There are too many folder entries or consumed file paths. |

Recognition follows a bounded chain of actual typed exceptions, including
causes hidden by the redacted traceback. It never prints arbitrary exception
text or accepts an arbitrary error's claimed code. Unknown errors still use
`launch_stopped`; credential and cancellation results keep their existing
meaning. The unified launcher prints its safe code before the potentially long
recording check, then saves the partial observation and re-raises the original
exception. Original saved observations keep their original labels.

These are engineering changes in a separate checkout. They neither patch the
old executing tree nor authorize starting a changed runtime against its owners.

## Complete-grid capacity remains a gate

The byte allowance is not the only limit. The existing checker also allows
10,000 local entries, counting files and folders together. Current trial
metadata has 2,149 files and 1,574 folders: 3,723 entries. An ordinary retained
task unit has 45 files and 32 internal folders. The allowed 312 successful final
cells therefore need at least 24,336 entries, or 28,059 including today's trial,
before remaining development, higher parent folders and freeze records.

Observed ordinary-unit sizes project about 7.34-7.66 GiB for the final cells
alone. This is an extrapolation, not an upper bound. The existing prospective
checks cover per-owner input sets and a rough development-owner count; they do
not establish complete trial folder or byte capacity.

A separate versioned capacity policy and full-layout rehearsal are required.
Neither failed stage attempts nor local stop observations are fully bounded by
the API-attempt cap, so any rehearsal must declare its recovery envelope.
Exceeding a finite allowance must remain an explicit partial result, with the
reason recorded. No larger folder policy is selected by these repairs.

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
