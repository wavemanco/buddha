# Durable proposals from measured feedback

[PLAN.md](PLAN.md) remains the roadmap. This is one engineering connection in
SRC-02: a selected parent receives its own verified development measurements
and proposes a child through the existing isolated improvement procedure.
The complete inherited search controller and model-authored experiment remain
separate work.

## What this adds

The [feedback bridge](SOURCE-FEEDBACK.md) writes four files: the complete host-only
source task collection, development split, bounded feedback and host provenance.
Only selected development tasks and notes enter the worker. The new stage checks
that packet against its original screen and the caller's provenance hash,
then checks that its measured candidate is the selected parent. Edited notes
do not become measured feedback merely by updating their local hashes.

Preparation binds the descriptor, runtime, packet, executing helpers and
selection to one new owner under an existing spending authorization. It creates
no authorization or extra allowance. Execution invokes the original
`CandidateSession` in the pinned isolated executor; candidate Python source
never runs in the host process. Official benchmark algorithms and scores are
unchanged.

## Three outcomes

| Outcome | Meaning | What happens next |
| --- | --- | --- |
| Complete / materialized | The worker returned an accepted changed source proposal, execution and cleanup succeeded, and the host saved its child and lineage. | The original owner is closed with a completion hash. The child still needs generation, assessment and competence checks. |
| Complete / rejected | The worker finished cleanly with an accepted failure, such as an invalid, unavailable or oversized proposal. | Preserve its literal failure and captured evidence, close the original owner and let later search record the rejection. There is no child to assess. |
| Incomplete | Execution, cleanup, a broken or unaccepted protocol exchange, quota, cancellation or request uncertainty prevented a trustworthy terminal outcome. | Save the attempt and observation; retain the original owner, replies and any uncertain spending hold. Recovery uses that owner. |

“Complete” describes this proposal's lifecycle. It does not mean a better agent,
a competent improver, archive admission or scientific promotion. For a rejected
proposal, the record preserves the worker's declared failure; a normalized JSON
capture does not prove what Python value the worker originally returned.

A broken session cannot become a completed rejection merely because it saved
a failure-shaped reply. Both terminal outcomes require an accepted final frame,
successful process exit and removal, exact delivered callback coverage, no host
stop and matching original-owner accounting. The raw session report remains
unchanged inside the separate lifecycle envelope.

## Library interface

These are library functions, not additional PowerShell commands or permission
to start another paid experiment:

| Function | Purpose |
| --- | --- |
| `source_feedback.inspect_source_feedback(directory, expected_provenance_sha256=...)` | Read and verify an existing four-file measured packet without changing it. The public builder and writer still require a new directory. |
| `candidate_improvement.prepare_candidate_improvement(directory, ...)` | Validate the selected parent's packet and runtime, then prepare one owner and its original inputs. No provider request or worker starts. |
| `candidate_improvement.run_candidate_improvement(directory, transport=...)` | Execute a new attempt or resume the same owner. This can spend its existing allowance. Received replies retain stable identities; unknown liability blocks new dispatch. |
| `candidate_improvement.inspect_candidate_improvement(directory, authorization=..., expected_report_sha256=...)` | Passively verify a pinned completed publication against original inputs, receipts, outputs, completion seal and independent authorization anchor. It starts no worker and sends nothing. |

Preparation accepts the existing `buddha.candidate-improvement.v1` descriptor,
selection and component roots, an attached authorization and review, local
money/attempt ceilings, and independent runtime/provenance hashes. The feedback
path must name `feedback.json` in the four-file packet. Caller-reviewed input
hashes are forwarded into the owner; changed bytes do not get silently repinned.

## Keep an improver fixed while changing its starting agent

The separate `buddha.candidate-improvement.v2` descriptor supports the first
connection needed for IMP-01. It separates three things:

| Role | Plain meaning | What is fixed |
| --- | --- | --- |
| Improver | The selected Python program that tries to make a better agent | The original selected source, runtime and model-call limits |
| Task parent | The starting agent it is asked to improve | Literal source and its independently checked identity |
| Development packet | The starting agent's recorded task results and complete answers | The original measured packet, including its provenance |

This lets the initial and evolved improvers each try to improve exactly the
same starting agent from exactly the same feedback. In an ordinary inherited
search, the selected program improves itself. That alone cannot isolate whether
a changed improvement procedure is better: its starting agent has changed too.

V2 keeps the existing preparation, execution and inspection functions. It adds
`task_parent: {path, sha256}` to the descriptor. This reference names a bounded,
regular UTF-8 source file supplied as data. `parent_agent_sha256` identifies that
task parent; the selected executable still identifies the improver. The task
parent's identity always uses the one-file inventory `candidate.py`, regardless
of the physical input filename or the improver's entrypoint. Preparation derives
that identity from the actual bytes and checks it against the original measured
packet before creating an owner. A matching local filename or hash supplied by
the caller cannot replace the measured-parent check.

V2 requires full-output feedback format
`buddha.candidate-development-feedback.v2`. Historical prefix packets remain
readable under their existing contracts; they cannot be used for this new
operation. The worker executes only the selected improver. It receives the
task parent's literal source through its input, without another source mount.
Changing the returned child is judged against the task parent, rather than
against the executing improver. A proposal identical to the task parent is a
rejection. One identical to the improver can be a changed child if the task
parent was different.

Worker format v3, session/stage reports v2 and lineage v2 record both roles.
Readiness and model-call identities bind the two source identities and complete
projected feedback. Passive verification reconstructs these joins from the
original owner's inputs and receipts. Known saved replies can be reused only by
that original operation; an unknown request keeps its hold and cannot be
replaced. The old descriptor, callback, report and lineage versions retain their
original inherited-search meaning.

Use this measured proposal stage for IMP-01 experiments. Direct
`CandidateSession` remains a lower-level interface for caller-reviewed
development notes: its v2 checks the pinned task-parent bytes, full packet
format and development membership, but does not certify that arbitrary notes
were measured from that parent. Source identifiers in a raw session report or
lineage are not a measurement certificate. The protected stage additionally
reconstructs the original screen evidence and authenticates the parent/packet
relationship.

The [fixed-improver failure packet](SOURCE-FEEDBACK.md#a-fixed-improver-learns-from-its-own-failed-children)
adds provenance v5 when checked failed children inform later proposals. It
retains complete measured parent answers and checks that all included failures
belong to the same frozen improver. This protected stage accepts that packet
only through descriptor v2 under that same selected improver. A valid packet
from a different improver cannot be borrowed by changing its local file hashes.
The lower-level reviewed-note Session keeps its existing scope.

This connection does not yet choose initial/evolved improvers, allocate equal
descendant budgets, select descendants, run a repeated comparison, or assess
them on sealed tasks. A frozen comparison must keep invoking its declared
improver even when a returned child contains a different improvement procedure.
Those scheduling and evaluation requirements remain open under IMP-01; ordinary
inherited source search continues to use its existing v1 behavior.

The [delivery record](conformance/imp01-frozen-improver-seam-delivery.json)
retains six passing new methods, 102 successful in-process regression methods
and a separate passing 13-method portable-worker cohort. The original mixed
regression run remains failed: its process-free proof guard blocked the portable
workers. Seven quality checks pass after the Windows fixture base repair. A
separate observation runs two supplied improvers in actual restricted containers
with two simulated API replies, identical starting source and full feedback;
both workers are removed and their proposal owners close without holds. No real
provider request, model-authored mutation, official assessment or improvement
effectiveness result is established. Full hosted CI remains pending.

For developers, the following runs the focused connection checks once in the
current PowerShell window. It uses temporary records, simulated workers and
provider replies, needs no keys or Docker, and spends no API money. Wait for
`OK` or a failure; allow several minutes. Ctrl+C stops it. It neither inspects
nor resumes a live run.

```powershell
python -m unittest discover -s tests -p test_frozen_improver.py -v
```

## Saved records and recovery

`context.json` fixes the descriptor and independent pins. `owners/0` retains
the original request owner. Every attempt gets a separate `attempts/0-N`
directory containing `session/` and the host lifecycle `report.json`.
Incomplete observations are append-only files under `observations/`.

For a complete lifecycle, `completed/0.json` seals the exact attempt files.
Its hash is also recorded in the original authorization's owner closure.
The root `report.json` joins both records, the raw session result and any child
reference. A terminal rejection keeps the raw session's failed status inside
the complete outer lifecycle. Retrying a completed stage reuses its saved result
without another session, worker or provider call.
Executable replay still checks the original installed inputs through `Gateway`;
use the passive inspector after retiring the producer's programs.

An interruption between writing a completion seal and recording its independent
authorization anchor leaves a refused state requiring review. This reuses the
existing stage lifecycle; it does not automatically repair that boundary or
claim recovery from every possible process or host failure.

Passive inspection reads retained data and runtime metadata, not retired
producer programs. It checks the original callback prefix and funding history;
saved files being mutually consistent alone is insufficient. Consistency and
custody checks do not authenticate historical host state against an attacker
who controls the host and every original authority record.

## Local checks

From a checkout containing this slice, this runs the focused checks once using
temporary fixtures, simulated provider replies and the real session/accounting
path. It needs no keys or network and spends no API money. Wait for `OK` or a
failure; Ctrl+C stops the tests. It does not inspect or resume your live study.

```powershell
python -m unittest discover -s tests -p test_candidate_improvement_stage.py -v
```

The separate engineering [confined rehearsal](conformance/src02-source-proposal-stage-probe.py)
uses retained synthetic screen data, a reviewed source map and new output paths.
It starts one actual container and supplies one simulated API reply to the
inherited improver. It checks that the measured notes reach that procedure and
that replay and passive inspection add no work. It does not regenerate answers,
rerun judges or execute the materialized child. The ordinary test command above
uses a simulated executor; these are different verification scopes.

This optional command only prints the rehearsal's required developer arguments
and quits. It starts no container, changes no records, reads no keys and spends
nothing. Reproduction needs the original retained local fixtures; a fresh clone
alone does not contain them. This is not a command for your live POL-02 run.

```powershell
python docs/conformance/src02-source-proposal-stage-probe.py --help
```

The delivery records 13 focused lifecycle methods across disjoint cohorts and
40 original regression methods, plus seven application quality checks at 196
unchanged Python inputs. The later probe is the sole new Python addition: its
separate static checks and confined run cover 197 inputs. The first probe attempt
stopped before any worker or operation because its test guard mishandled a
Windows SQLite URI. Its source, partial fixture and failure records remain
preserved alongside the corrected guard checks and successful new rehearsal.
The successful run recorded one removed worker, one simulated reply and 11
synthetic microdollars with no hold. Neither attempt used real provider APIs.
The final 1,439-test inventory is collection only; full final-head hosted CI
is a separate gate. See the [delivery](conformance/src02-source-proposal-stage-delivery.json)
and [review](conformance/src02-source-proposal-stage-review.json) for exact scopes.
