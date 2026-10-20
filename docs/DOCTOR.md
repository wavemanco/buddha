# Observe a saved or interrupted run

`doctor` reports the accounting, locks and completion evidence it can read now.
It does not resume the run, make model calls, use API keys, change records or
remove locks. It is a one-time observation, separate from sealed scientific
[search verification](SEARCH-VERIFICATION.md).

## The preserved first attempt

From the project folder:

```powershell
python -m buddha doctor --run runs/first-live-search --authorization runs/first-live-authorization-v2.sqlite3
```

This reads the original attempt and the explicitly named shared spending record.
It runs once in this window, costs nothing and needs no separate window. Ctrl+C
stops only the observation. It cannot recover the missing tenth reply or release
its reservation. The expected result needs review because that request remains
unknown; exit code 3 is expected for this case.

To observe the completed linked continuation instead:

```powershell
python -m buddha doctor --run runs/first-live-continuation-v2 --authorization runs/first-live-authorization-v2.sqlite3
```

This also runs once here, without keys, spending or record changes. It reports
the continuation's own physical calls separately from the whole authority's
totals. The original unknown hold remains in those shared totals. Ctrl+C stops
the observation. Neither command starts a provider request.

The authorization option is optional. When omitted, the doctor checks only local
records. It never opens an authority or descriptor simply because a saved file
names its path. For native baseline folders, an explicitly selected authority is
needed to observe completion anchors. No benchmark driver, source archive,
installed evaluator, SDK or container is executed.

## Read the result

The output is JSON:

- `status: observed` means bounded local records were read consistently during
  this observation. It does not mean a writer is running or a run is safe to resume.
- `busy_or_changing` means an active SQLite sidecar or observed input change
  prevented a stable observation. `unavailable` includes missing, unsafe or
  inconsistent inputs. `unsupported` means the stored format needs another reader.
  These outcomes have `accounting: null`; unavailable costs are not reported as zero.
- `needs_review` identifies an unknown operation or invalid/unanchored completion
  or lock. A false value does not settle pending work or authorize another call.
- `accounting` and `operations` describe the selected physical records. Reserved,
  dispatched, unknown and completed counts stay separate. A reservation does not
  establish a send; a dispatched request may already have been charged.
- `lock` reports what is stored. `writer.identity` remains `unknown`: current
  empty/PID-only locks lack a process creation identity. A PID observation reports
  only sampled presence of that number, including permission/API limitations.
  If the input could not be read, lock status is `unavailable`, not `absent`.
  An absent lock or PID does not establish remote cancellation or container cleanup.
- `diagnostics` contains safe, validated failure metadata matched to outstanding
  legacy operations. Newer unrelated records cannot hide older unresolved ones.
  Missing diagnostics do not erase the ledger's liability. Raw Gateway owners
  use a different receipt format and do not acquire invented legacy explanations.
- `shared_accounting` covers the entire explicitly selected authority. Only the
  selected run, or the native folder's stage owners, has its local mirrors matched.
  Other authority owners are not thereby locally inspected.
- `observed_sha256` identifies consumed file bytes. Without an external preserved
  seal, this is not authenticated history or proof of an atomic live snapshot.

Exit code 0 means records were observed without a flagged review condition;
3 means review, unavailable/busy input or an unsupported format; 2 means an invalid
command/input exception. Read the JSON rather than treating exit code 0 as approval
to spend, retry or remove a lock.

For native baselines, `stages` lists the original owners and their separate caps.
The top-level physical totals sum these distinct owners; there is no invented
single local cap. Completion can be absent, stored and anchored, anchor not
observed, unanchored and needing review, mismatched or invalid. An active owner
with a completion file remains an interrupted state needing review. The doctor
never adopts its seal or creates a replacement owner. Existing resume refusals stay.

## Continuous observation

```powershell
python -m buddha watch --run runs/first-live-continuation-v2 --authorization runs/first-live-authorization-v2.sqlite3
```

This watches the same saved accounting in a separate window while another run is
active. It uses no keys, spends nothing and changes nothing. Ctrl+C stops watching
without stopping that other run. It returns when a matching saved completion or
review state is observed; this already completed example normally returns at once.
For a native folder, the optional explicit authority lets it check completion
anchors. Without one, it cannot conclude that native completion is anchored.

Watch messages say writer identity is unknown. A heartbeat means the observer is
still polling; it does not prove that execution or a provider request is advancing.
An execution wrapper returning normally also cannot establish saved completion.

## Boundaries

All consumed files and directory entries are bounded. Links, unsafe aliases,
nonregular/hardlinked inputs and active SQLite sidecars are refused. SQLite is
queried only from captured bytes in memory. Before/after comparisons detect
observed change; they do not prove an atomic view under arbitrary concurrent writes.
Byte ceilings are not universal memory or execution-time guarantees.

The PID query uses read-only operating-system facilities: Python's
[Linux PID descriptor](https://docs.python.org/3/library/os.html#os.pidfd_open), or
Windows [process handles](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess)
and a [zero-time wait](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject).
Unavailable or denied queries remain explicit. No signal is sent.

See the [recovery contract](RECOVERY-CONTRACT.md) and [living plan](PLAN.md).
This observer does not reconcile invoices, authenticate providers, judge story
distinctiveness or establish scientific improvement.
