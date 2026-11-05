# Short forward-runner timing observations

The separately approved follow-up completed the first common screen and its
mutation witness in **449.5494583 seconds**, including its cold prefix read and
reporting. This passes that prefix observation only. The full capacity case
and full CI remain unapproved; the earlier five-minute partial is preserved.

The one authorised five-minute observation ended as a **partial**. It did not
complete the first common screen and witness. The current request to execute
the full three-hour capacity case is withdrawn pending better timing evidence;
the proposed three-hour total and 15-minute full reader remain unadopted.

This result does not supply an empirically justified upper bound for either.
[PLAN.md](PLAN.md) remains the roadmap. The [capacity preparation guide](FORWARD-CAPACITY-PREPARATION.md)
defines the larger proposed workload; this observation did not execute it fully.

## What ran and what was preserved

The observation reused the existing full-size synthetic fixture and ordinary
v5 runner at source `5c21db2071373f871fdc2584868e33a2a07de41a`.
It selected three tasks, ten answers per task, twelve supplied generation
callbacks, 8,192 UTF-8 bytes per answer, 1,000 source rows and 24,043 native
inventory entries. Real model calls and real containers were replaced by
supplied replies and workers; no keys or original paid history were used.

The intended stopping point was one completed common screen and its mutation
witness, before the next common condition: an expected 14 owners and 82
supplied operations. A 240-second stop applied at action boundaries; the outer
child timeout used the remaining part of the 300-second allowance, including
setup. There was no automatic retry, resume or extension. This allowance is
consumed, and the partial synthetic workspace is retained unchanged.

## First observation: five-minute partial

| Saved observation | Result |
| --- | --- |
| Independently measured whole invocation | 301.6919121 seconds; outside 300 seconds |
| Parent observation clock | 301.4309144 seconds; timeout recorded |
| First screen action entry, on the child clock | 151.2660963 seconds |
| Screen action return | Not recorded before termination |
| Task generation reports | Three saved reports say `complete` |
| Task evaluation reports | Three saved reports say `complete` |
| Aggregate screen report / witness | Absent / absent |
| Child terminal result / terminal memory | Absent / unavailable |
| Cold prefix inspection | Not reached |

The child log contains the declared fixture dimensions and that first screen
entry. It has no action-return or terminal event. The empty stderr log does
not establish success. The outer process returned exit code zero because the
observer saved its partial receipt; the receipt records `partial` and timeout.
The whole invocation exceeded the allowance by about 1.69 seconds, including
termination and reporting overhead. This is not a passing timing result.

The six lower-stage reports are progress evidence. They do not establish the
aggregate screen's completed checks or publication, the intended 14-owner /
82-operation stopping point, zero holds or reconciled study accounting.
The independent review read bounded JSON and hashes only; it did not open
SQLite, reconstruct the study or run a full reader. All 297 bound public
source files rehashed unchanged, and script and log hashes match their receipts.

The screen's duration is **right-censored**: its entry is known, but its finish
was not observed. Roughly 149 seconds between entry and the nominal cutoff
is neither its completed duration nor an upper bound. Setup had already used
roughly half the observation. Multiplying this incomplete action or the earlier
909.678-second eight-case aggregate cannot justify a full-study forecast.

## Approved follow-up: completed prefix

The user approved one separate 900-second observation of the same first common
screen and witness. It completed in its new retained workspace without resuming
or overwriting the first attempt. The application source, full-size payload and
16-opportunity declaration stayed unchanged; the observer stopped before the
next common condition. This separate allowance is consumed.

| Saved observation | Result |
| --- | --- |
| Independently measured whole invocation | 449.5494583 seconds; within 900 seconds |
| Parent / child clocks | 448.6422953 / 439.6932565 seconds |
| Cold inspection of this prefix | 19.8701148 seconds |
| Aggregate screen / mutation witness reports | `complete` / `passed` |
| Original owners / supplied operations | 14 / 82 |
| Saved accounting at this prefix | Zero held; all 14 owners inactive |
| Completed common conditions / counted children | 1 of 4 / 0 of 16 |
| Child peak working set | 1,083,768,832 bytes through final validation |
| Execution timeout / guard denials | False / none recorded |

The cold read reproduced the saved prefix's coverage and accounting according
to the reviewed script's checks. Independent review verified the saved result,
14-row accounting arithmetic, aggregate report statuses and raw file hashes;
it did not reopen SQLite or rerun the reader. All 297 public source pins still
match. The first partial's files and observations remain unchanged.

The 900-second limit was an operational allowance, not a completion forecast.
The 720-second action-boundary stop was not reached, and the optional cold read
started before it. The independent whole-invocation clock includes reporting
and meets the adopted limit for this observation. Memory was measured before
terminal-report writing; it is not a full-study or OS-enforced memory bound.

The single 240-second standard-library stack dump was collected during host
JSON encoding along witness capacity/feedback inspection. Its `Timeout` heading
is the diagnostic timer, not an execution timeout. One stack sample identifies
an active code location; it does not prove the dominant cost or a performance
bound. No repository Python module, dependency or controller was added.

The retained proposal and approval are in
`runs/checks/forward-timing-completion-proposal-20261105-v1/proposal.json`;
its `check.py` has SHA256
`5c9f359eedc0a698a6c08ae1e2ada4efac7b65a89934ec048ca39bc2d1f01fec`.
It binds the unchanged executing source `5c21db2` and the existing source
binding named in the receipt. This approved prefix observation is terminal;
it authorises no repeat or further workload. No keys, paid model calls, real
containers or original paid records were used.

## What this establishes for later decisions

This is one measured starting-condition prefix, not a complete study. Later
common conditions, all 16 counted child opportunities, growing feedback, final
freeze/publication and a full-history reader remain unmeasured. The prefix's
19.87-second read is not the full-reader duration. Differences from the first
attempt's setup timing are uncontrolled variation, not a demonstrated speedup.
No empirically justified full-workload upper bound follows by multiplication.

A future full-workload time allowance still needs review and explicit adoption
and execution approval. The earlier three-hour total and 15-minute full-reader
targets remain unadopted. No renewed full-capacity or full-CI run is approved.

## Revised full-capacity proposal

Propose one full-capacity measurement with **4 hours for the writer**, including
setup and checks before admitting the reader, **30 minutes reserved for the
fresh reader**, and **10 minutes reserved for final checks and reporting**:
**4 hours 40 minutes total**. These are maximum allowances, not expected usage
or an empirical guarantee of completion. No further calibration run is scheduled.

The measured first common condition took 391.823 seconds from the first action
entry to the next checked boundary. Twenty screen/witness units at that same
cost would take **130.6 minutes**. That planning scenario excludes the sixteen
additional counted proposals, child bookkeeping, growing comparative feedback
and terminal checks. A four-hour writer budget leaves **109.4 minutes** beyond
that scenario for those costs and uncertainty. Their actual growth remains
unmeasured; this is a chosen operating budget, not a statistical upper bound.

Scaling the 19.870-second prefix read purely by owner count, 14 to 296, gives
about **7 minutes**. The 30-minute reader allowance is about 4.28 times that
scenario. Neither owner-linear scaling nor that margin is validated by this
one prefix. Its roughly 1.01 GiB memory peak also cannot establish full-study
memory use; the proposed 4 GiB acceptance threshold is unchanged.

The writer must finish its admission checks while the entire reader and
reporting reserves remain. A late writer leaves a partial; it cannot steal
the reader's time. Independent whole-command timing remains required. The
previous three-hour/15-minute values are historical unadopted proposals, not
additional success criteria secretly applied to this prospective case.

The proposed case still requires all 296 owners, 1,656 simulated operations,
sixteen admitted children, full feedback/lineage and reconciled accounting.
It needs explicit adoption and execution approval at its final source. Full
qualification remains conditional and separately authorised; no paid or main
merge clearance follows from either engineering check.

The small reservation correction passes six mocked recipe checks, focused
lint/type/security checks and independent source review. It adds no
application module or dependency. The discovered inventory is 459 short
contracts and 2,215 full methods per OS; an inventory is not execution.

The diagnostic also led to a bounded reuse candidate: proposal-capacity checks
reconstruct the same feedback parent before and after writing a checkpoint.
An existing checked-parent handoff already avoids this elsewhere. Reusing it
here may reduce repeated work while preserving fresh evidence checks; it has
not been implemented or measured and adds no new acceptance gate.

Full CI remains separate: 60 minutes without genuine test progress is a stall
watchdog; six hours is the hosted-job ceiling. Earlier source `6e` took about
34–53 minutes per Linux job and 2h16m–2h52m per Windows job. Those observations
do not forecast this source or establish scaled local capacity.

The [evidence receipt](conformance/forward-timing-observation.json) names the
retained local files and raw hashes. It preserves the original partial and
does not pass or rewrite the older unpassed v4 capacity gate.
