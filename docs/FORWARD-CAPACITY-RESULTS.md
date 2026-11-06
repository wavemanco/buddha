# Forward-capacity attempt: interrupted partial

The one approved attempt at [PR266](https://github.com/wavemanco/buddha/pull/266),
source `815e15c78cea494e74407e75b3c4b3e843becd8a`, has **no terminal result**.
Its running process/session was absent when checked after the tool connection
was interrupted. The actual termination cause, end time, exit code and complete
command duration are unknown. This is not a capacity pass or an established
timeout. Conditional full qualification was not started.

The user adopted one prospective v5 case with four hours for setup/writing/reader
admission, a fully reserved 30-minute fresh reader and ten minutes of reporting:
4h40 total, with a 4 GiB measured peak threshold per child. The allowance is
consumed. There was no retry, resume, extension, paid call, real container,
original paid-history read or main merge. The original source checkout remains
clean and all 297 raw source pins rehash unchanged.

## What the surviving records establish

| Observation | Saved evidence |
| --- | --- |
| Common conditions | Four screen reports say complete; four witness reports say passed |
| Counted opportunities | Ten saved decisions say admitted, out of sixteen required |
| Last logged action entry | 10,372.2127083 seconds: planning feedback for start0 / repetition1 / arm0 / slot1 |
| Pre-action counters at that entry | 206 owners and 1,158 simulated operations; not terminal financial totals |
| Next action's saved plan | Absent; entry does not establish completion |
| Writer / reader / aggregate reports | Absent; no fresh-reader logs were created |
| Independent whole-invocation receipt | Absent |
| Terminal memory, guards, holds and reconciled accounting | Unavailable |

The log has 164 JSON events, of which 162 are action entries. Independent review
checked the sixteen fixed decision locations, the four common reports/witnesses
and raw hashes. It did not open SQLite, rerun a reader or reconstruct the study.
Saved statuses are useful progress evidence, not replacement terminal checks.
The 296-owner/1,656-operation/full-feedback/complete-reader acceptance remains
unmet. The older v4 gate and all earlier partials retain their original status.

## Slow execution and the unexplained stop are separate questions

The first eight counted opportunities occupy about 103.3 minutes between their
first preparation and second-round planning. The next two occupy about 40.1
minutes between second-round planning entries. Those intervals include boundary
checks and use different conditions and host times. They show the short common
prefix did not measure later work; they do not isolate a bottleneck, establish
an upper bound, prove the four-hour limit would be missed or explain termination.

A narrow source review found that the scheduler already holds a checked parent
screen, while witness dispatch reconstructs that screen for progress and then
again for materials. This happens in common and child paths. Freshness and
accounting validation also do work. Reusing an existing checked handoff is a
candidate simplification, but its cost contribution and safety at this boundary
are not established by the timing log. It is not a demonstrated fix for the stop.
The earlier single stack sample belongs to the separate prefix observation,
not a profile of this interrupted attempt.

A single bounded review of existing Windows crash/restart records found no
matching events in the checked window. The OS last boot predates this attempt.
This does not establish what ended these processes. No terminal receipt was
fabricated from the later observation time, and the late process-absence check
is not treated as the execution end time.

## Subsequent bounded diagnosis: November 5

The authorised historical investigation closed in300.778seconds, within its
30-minute limit. It correlated the own-session unanswered poll with a desktop
instance/executor transition less than a minute after the last study output.
No retained event ties that transition directly to the workload's termination.
Cause, exact end and exit remain unestablished. No further historical log
search is scheduled. A sanitized receipt and selected-line hashes are retained
in runs/checks/inspect-stage-integration-20261105-v1/forensics.json; raw host logs
were not copied into the project.

The user excludes Task Scheduler and global Windows logging. Subsequent work
must use only project-owned processes and project-local observations. Real
Inspect integration addresses the demonstrated visibility gap, without being
presented as a proven fix for the historical stop or the slower second round.

## Stopping point

[PLAN.md](PLAN.md) remains the roadmap. First deliver a short, independently
checked diagnosis linked to these records and the actual call path: distinguish
the unknown termination from measured stage durations and static repeated work;
identify what can safely be reused before proposing any execution-code change.
If the available evidence cannot establish a cause, retain that uncertainty.
No further capacity attempt, qualification, paid run or additional framework
is scheduled by this result. Scientific improvement remains unproved.

Raw logs and the retained synthetic workspace stay under
`runs/checks/forward-timing-budget-checks-20261105-v1`. The approval,
post-interruption observation, bounded host-record lookup, surviving reports
and raw hashes are referenced in the [receipt](conformance/forward-capacity-results.json).
The executing recipe/protocol and earlier evidence stay unchanged.
