# Check a saved matched trial before asking for keys

The state reader checks whether saved trial records still match the reviewed
experiment. It works on an unfinished original trial as well as a completed one.
It makes no provider request, asks for no keys, writes no records and removes no
locks. This is a library interface; there is no new command to run yet.

The reader uses the existing development and final recovery checks. It joins the
outer launch and approval fingerprints to the original first execution record,
checks all three original grants and accounts for every recorded owner. The
unused validation grant must remain unused. A changed input, foreign owner or
broken record raises an error instead of producing a trusted summary.

## What the phases mean

| Phase | What the records establish |
| --- | --- |
| `search` | Development is prepared or partly complete. Original records identify the next unfinished step. |
| `freeze` | The complete development report has been checked. The chosen descendants still need their one-way final freeze. |
| `final` | The original frozen schedule exists. Final assessment has not yet published its complete report. |
| `complete` | The complete final report agrees with the original records. Reading it makes no new calls. |

Final tasks and results remain outside improvement feedback. The reader never
chooses different descendants, changes the schedule or replaces an owner.

## What the spending fields mean

`phases` contains separate search, unused validation and final summaries. Each
shows its original cap, recorded cost, held amount, operation count and owner
count. `totals` adds the three phases without moving money between them.
`committed_microusd` is recorded cost plus held money; one million microusd is
one US dollar. These are recorded local amounts, not reconciled provider bills.

| Operation status | Meaning |
| --- | --- |
| `reserved` | Money and an attempt were reserved. Dispatch has not been recorded. This count does not prove a request was sent. |
| `dispatched` | Dispatch was recorded, but there is no settled reply. The request may already have been billed. |
| `unknown` | The outcome is uncertain. Its money remains held. |
| `completed` | A reply and its recorded charge are retained. |

Unknown and dispatched operations block readiness. A known reservation overrun
also blocks readiness while preserving the actual recorded charge. Unsent
reservations remain held; the existing controller alone decides whether the
same original operation can proceed. This reader performs no retry, reissue,
settlement, refund or release of held money.

## Readiness and locks

`ready` means this original-custody observation found no readiness block. It is
not spending approval or a promise that the next request fits the remaining cap.
The existing controller and broker still enforce every request. Account access,
current prices, model capacity and full-study runtime need their own checks.

`busy` records an execution lock, including `.search.lock`, `running.lock` or
`.trial-running.lock`. A lock is evidence to review; its presence does not prove
that a process is alive or healthy. The reader leaves it in place. An unfinished
inactive owner also prevents a clean readiness result.

`next_position` identifies the original unfinished stage. `blocked_reasons`
explains known readiness blocks. Invalid custody raises an error; the reader does
not invent zero costs or a replacement schedule when it cannot verify records.

## Interface and limits

`buddha.improver_launch_state.inspect_prepared_improver_trial` takes the original
trial directory, reviewed declaration and its raw fingerprint, reviewed runtime
fingerprint, all three grant paths, development account review and exact outer
input bindings. It supports the current assessment/study v4 route with the
[binding-aware trial context](IMPROVER-ASSESSMENT.md#bind-the-reviewed-launch-and-approval-files).
It returns a detached `buddha.improver-launch-state.v1` summary.

The checks read captured database bytes through in-memory SQLite; they do not
connect to the original database files. Trusted validators may decode retained
Python as UTF-8 text to validate its interface. The reader does not parse that
text as Python, import, compile or execute selected code, and it returns no task,
answer or source text.

`state_sha256` identifies the consumed bytes and captured folder entries, with
each external input and grant kept under its own path. This is a sequential
observation, not an atomic snapshot, signed seal or provider attestation. The
launcher must check again before work. Existing saved records and older formats
keep their matching pinned readers; this interface does not upgrade them.

The source-search launcher uses the same complete fingerprint helper. These
stamps compare observations made with the same pinned reader; they are not
portable identities across reader versions. The historical diagnostic output
keeps its original field names and values.

[PLAN.md](PLAN.md) owns the remaining launch and scientific work. A successful
state check does not establish better generation, a better improver or an
independent final result.
