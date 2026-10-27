# One launcher for the Buddha study and plain references

The new launcher connects the original primary controller, both plain-reference
controllers, the combined funding check, original-owner inspection and saved
partial observations. It allocates no money and changes no benchmark settings.
The [living plan](PLAN.md) remains the scheduling authority.

This implementation is not a funded handoff. A full no-cost execution rehearsal,
hosted checks and the remaining prospective review/account/price/request/funding
gates still precede the exact live command.

## Order and what completion means

The fixed order is the original Buddha development/final assessment, then plain
independent sampling, then plain in-context sampling. The primary must actually
verify as complete before either reference is prepared. The first reference
must verify as complete before the second starts. An incomplete controller stops
the invocation and saves a diagnostic; it does not start the next condition.

Finally the existing comparison reader verifies the complete original reports
and computes the declared descriptive comparison. The result is saved once as
`comparison.json` in a separate operator workspace. Repeating a completed
invocation checks the saved data and publication without entering keys or
calling controllers. It never overwrites a different publication.

The terminal prints a compact status, the saved result's path and its SHA-256
fingerprint. The full comparison stays in the saved file rather than filling
the terminal.

`complete` means computational completion. Native target-repair review and the
required human sample remain separate. The primary compute loop has no native
target-review pause and cannot obtain desktop model judgments from PowerShell.
The result explicitly records `pending_separate_review`; it supplies no
scientific winner, human preference or useful-diversity improvement claim.

## Before any paid request

The launcher checks the exact primary/plan pins, original four grants, common
panel, model profile, native instrument and source bindings. The same shared raw
allowance funds both plain modes. The declared combined limits must equal the
four allocation limits; this command cannot reallocate unused phase capacity.
The current proposed $150/16,384-attempt split remains unapproved and unfunded.

Both references' existing owners are inspected before key entry and checked
again afterward. Existing raw work before primary completion, missing owners,
changed inputs, uncertain requests and retained locks stop the run. A separate
outer lock serializes invocations; the original controllers retain their own
locks and transactional spending guards. A lock is not proof that a process is
still running, and the launcher does not remove another invocation's lock.

Missing keys are requested once in one temporary environment. The inner primary
launcher keeps its original launch-hash credential context. Raw owners use a
separate keyed review tied to the outer descriptor, created only after primary
completion. Retained reviews must match their original owner anchors, account
scope and provider fingerprints; an expired unfinished review stops for review.
Keys are never stored in the workspace or supplied to worker environments.

The pin order stays acyclic: static plan and helper sources, then primary launch,
then outer descriptor, then raw owners. The outer descriptor is bound into raw
owners; it is not pinned back into the primary launch that it already references.

## Stopping and resuming

The operator workspace contains its review, outer lock, observations directory
and eventual comparison publication. Primary and raw run directories remain
separate and keep their original IDs, ledgers, replies and holds.

Ctrl+C attempts a new [incomplete observation](COMPARISON-PARTIAL-OBSERVATIONS.md)
and preserves the original cancellation. Other failures likewise preserve their
original exception even if writing a diagnostic fails. Safe notices identify a
saved diagnostic path or say it was unavailable; raw error text is not copied
into that diagnostic. Initial unverified metadata cannot arm an observation.

Resume with the same reviewed handoff and original directories. Do not delete
locks, reviews or owners to force a restart. An interruption during initial
owner preparation can leave a partial root that requires review; this wrapper
does not repair it or create a replacement. Uncertain billing remains stopped.

## Command options

The final command will name the exact reviewed source and funded handoff.

| Option | Plain-English function |
| --- | --- |
| `--handoff` | Selects the frozen combined launch file; it points to existing approvals and grants. |
| `--sha256` | Pins that exact launch file. A changed file is refused. |
| `--check` | Checks configuration, original funding and saved state once; no keys, owners, run records or provider requests. Cannot be combined with live/key flags. |
| `--live` | Allows unfinished paid work within the existing grants. It creates no new allowance. |
| `--prompt-keys` | Asks only for missing keys, hidden, in this process. Paste once and press Enter. |
| `--confirm-project-keys` | Confirms that the supplied keys belong to the manually reviewed projects and account settings. |
| `--help` | Prints options and exits without checking or starting a run. |

This optional help command runs once in the current PowerShell window. It spends
nothing, changes no run records, needs no separate window and stops by itself:

```powershell
python C:\Users\arvik\code\buddha\runs\reviews\unified-comparison-launch\docs\conformance\unified-run.py --help
```

The live command also runs once in its current window. It can spend money; Ctrl+C
stops it while retaining evidence. Exit code 0 means computational completion
(or a passing check), 3 means incomplete/blocked, 130 means cancellation and 2
means a refused or failed launch. No exit code closes the separate scientific
review gates.
