# Launch one approved policy comparison

The launcher checks one declared study destination before asking for a key, then
uses the existing [policy study controller](POLICY-EXECUTION.md). It does not
create an allocation, change the frozen policies or interpret benchmark scores.
The current $50 / 4,096-attempt envelope is still a proposal. This slice does not
create a real funded launch file or confirm access to either provider.

## What must be approved first

The [unallocated proposal](POLICY-HANDOFF.md) stays unchanged. After a separate
funding approval, a new caller-pinned `buddha.policy-launch.v1` record names:

- The original proposal, actual funded execution descriptor and approval record,
  each with its absolute path and original physical SHA256.
- One absolute study destination and one fixed local review-file path. Neither
  can be overridden by a later command.
- The required installed launcher/helper source hashes and a finite HTTP
  `timeout_seconds` greater than zero and at most 600.

The separate `buddha.policy-approval.v1` record binds that same proposal hash,
study fingerprint, destination, review path, authorization path/ID/immutable
terms/scope, budget and attempt ceiling, plus the manually reviewed account
scope. It records approval, not authenticated identity or provider billing.
The execution descriptor must reference the exact original study/template and
an existing authority; an unallocated proposal cannot substitute for it.

The authority must be dedicated to the exact planned owner paths for this
destination. The launcher rejects another directory's owners even if they use
the same study fingerprint. It never replaces an existing grant or owner.
Mutable authority bytes are observed consistently, rather than frozen as a
permanent file hash. Immutable terms and every original owner remain bound.

The caller supplies the launch record's trusted SHA separately. A matching
checksum establishes reviewed-byte identity; it does not prove who approved it
or when. Changed installed sources require a new explicit review, not silent
updates to an old proposal or prepared owner.

## One command for preparation and recovery

From the repository folder, the command shape is:

```powershell
python docs/conformance/pol02-run.py `
  --handoff C:\path\to\funded-launch.json `
  --sha256 ORIGINAL_REVIEWED_LAUNCH_SHA256 `
  --receipt C:\path\to\launch-1.json `
  --live --confirm-project-keys --prompt-keys
```

Replace these placeholders only with the separately approved files and hash.
This command runs once in the current window. For unfinished work it can spend
the existing approved allocation. It creates a fresh study only when the
declared destination and review file are absent and the dedicated grant has no
owners. Otherwise it checks and recovers the original prepared study. Press
Ctrl+C to cancel; saved replies, original owners and outstanding holds remain.
It never starts a replacement experiment automatically.

For recovery, keep the same `--handoff` file, original `--sha256` and declared
study destination. Change only the external receipt filename, for example to
`C:\path\to\launch-2.json`; never reuse `launch-1.json`. The new receipt records
this invocation. Changing the receipt does not replace the original study,
grant, review or retained owners.

`--confirm-project-keys` affirms that the supplied inference keys belong to the
manually reviewed provider accounts and billing scope, with the approved account
headers/tier bounds. It is not a provider authentication check. `--live` and this
confirmation are required before unfinished work can request a key.

`--prompt-keys` requests any missing selected provider key through hidden input,
in one session for both providers. Paste once and press Enter; characters do not
appear. A safe notice confirms receipt immediately. Existing environment keys
are validated against an original saved review on recovery. Newly entered keys
exist only in this process's temporary environment and are removed on every
exit, including failure during the second key. Keys are not written to files,
printed, passed as command arguments or included in worker environments.

For this study, fresh or resumable unfinished execution validates both OpenAI
and Anthropic keys. Hidden input asks only for keys missing from the current
process. A known pre-key refusal does not ask for either key. On a fresh launch,
the review is saved only after the required keys validate and the post-entry
configuration check passes. Recovery keeps that same review and date; it does
not refresh an expired review, change credential fingerprints or silently
reapprove bounds. Invalid or incomplete preparation stops explicitly.

Choose a known-safe `--receipt` location outside the study and selected input
components. It must name a NEW file whose parent already exists; a sibling of
the authorization database is fine, and an existing file is never overwritten.
The launcher checks that parent/new-file boundary immediately and checks overlap
with declared study/components once the handoff validates. An invalid handoff
cannot establish all protected roots: the caller is responsible for choosing
the safe location for an early-failure receipt. The actual launch command must
use a separately reviewed receipt directory. This explicit command path, rather
than a path inside an unvalidated document, can record a safe phase and reason
before the study exists. Invalid command/receipt paths cannot guarantee a durable
receipt. Receipt-write failure produces a safe warning and does not replace an
already-known execution result or cancellation observation.

To check an already completed study, use the same handoff and original hash,
choose another NEW receipt filename, and omit `--live`,
`--confirm-project-keys` and `--prompt-keys`. This reads no key, starts no worker,
spends nothing and validates the full stored, authority-anchored cell/occasion
grid and root publication. Omitting those flags for unfinished work stops
before key entry; it is not a dry run of unfinished execution.

## Progress and stops

The first notice appears before slow source/component checks. A bounded
heartbeat shows phase and elapsed time. Before funding is validated, accounting
is unknown. After validation it passively reports recorded attempts, recorded
upper-rate cost, held liability and the allocation cap. These are saved ledger
values, not a verified provider invoice or a count of network sends. A changing
database can make a heartbeat temporarily unavailable. Progress text pauses
during hidden key entry.

Pre-key checks use bounded captured histories and in-memory authority reads.
They validate current installed source/input/profile identity, original review,
all retained owners and mirrors, completed anchors, and retained execution
prefixes. Busy/changing evidence, unknown dispatch outcomes, overruns, expired
reviews and known capacity refusals stop without creating replacement owners.
An inactive retained owner without its completed seal also stops before key
entry, including a later preallocated owner. Valid zero-operation preallocation
alone is allowed; the check never deactivates or reactivates an owner.
The controller repeats its original guards after key entry and before dispatch.

Capacity checks are conservative and do not predict the next native model/body
or promise that the remaining study will finish within the allocation. Completed
receipt replay and a sufficient reservation belonging to the same owner differ
from new capacity or another owner's hold. A declared stage that forbids model
calls, such as the native summary, does not require another paid reservation.
Uncertainty and custody guards still apply to it.

The HTTP timeout comes from the pinned launch record. A 600-second allowance is
a configured transport ceiling, not a claim about provider latency. It changes
no official request body. An ambiguous timed-out request retains its hold and
requires the existing reconciliation path, rather than an automatic new call.
Executor task/stage limits remain those of the original selected descriptors.

The command emits a small JSON status, without raw exception, prompt, reply or
credential text:

- Exit `0`: original stored study completion validated, or execution completed.
- Exit `3`: a known pre-key refusal or incomplete execution; no complete claim.
- Exit `2`: command, configuration or other checks stopped.
- Exit `130`: cancellation.

When the controller has successfully saved an incomplete observation, the
operator retains its exact relative path and reason. The original child report
remains unchanged inside that observation. It does not choose a newest log or
guess an attempt. Corrupt input or an I/O failure need not yield a study
observation; the external receipt records only the phase and facts actually
known. Cancellation likewise carries an exact study observation only if that
write succeeded.

An `observation` path is relative to the declared study directory. Keep that
original study and all earlier receipts. A pre-key refusal can have an external
receipt and reason without a new study observation, because no child ran.
The receipt is an invocation summary; it does not replace the original child
report or authorize retrying an unknown request.

Readiness validates custody and configuration rather than scientific metric
projection. A different reviewed release is not rejected merely because the
separate 1.1 analysis adapter cannot interpret its scores. No result is ranked,
repaired, regenerated or relabeled by these checks.

## Evidence ceiling

The focused launcher checks use synthetic grants, mocked confined workers and
simulated HTTPS only. They include original-owner unknown recovery, a completed
baseline followed by stopped rejudging, a nonpaying summary at the paid-attempt
cap, and exact cancellation records despite external-receipt failure. They are
not a live provider-access test or a full twelve-task capacity proof.

The intended twelve-task/four-arm/two-generation/two-judging schedule has 56
owners and 3,072 physical attempts when every answer is a separately scored head,
before repair/fallback. Actual grouping can reduce quality calls; this is an
all-heads sizing scenario rather than an expected attempt count.
Its normal worker count is 144: eight cells times twelve generation task workers
plus three baseline-native and three fresh-occasion workers. Quality/repair/
fallback paths can vary the attempt count. The earlier two-task, 64-worker
engineering fixture is separate evidence. The [separate full-size engineering delivery](conformance/pol02-operator-handoff-delivery.json)
records the twelve-task schedule through the actual selected containers and
SDKs with short fixed synthetic HTTPS replies. It retains the original-owner
interruption/replay, keyless completion and passive analysis/panel checks,
together with observed file/count/byte bounds. This is not a worst-case answer
size, 4,096-attempt, provider-access, latency or unlimited-recovery guarantee.
Repair/fallback behavior and real scientific outcomes remain separate evidence.

The HTTP timeout limits socket waits, rather than total request duration.
The worker has its own wall limit. The host waits for an in-flight model
callback before unwinding so its financial outcome can be recorded; cancellation
and cleanup may therefore finish later than the worker limit.

The original-source proof completed 3,072 simulated replies, 56 retained owners,
144 successful workers plus one interrupted worker, 192 task assessments and
a complete 24-set/240-position panel. Its recorded synthetic charge is 274,176
microusd with zero held; this is not an invoice or a new allocation. The local
Windows repository regression passes 1,330 tests in 3,425.973 seconds with ten
existing skips; all seven local quality checks pass. Hosted final-head Linux
and Windows checks remain separate merge gates. The [review](conformance/pol02-operator-handoff-review.json) retains historical cohort/source limits.
