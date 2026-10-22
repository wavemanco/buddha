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

Preparation requires the existing `buddha.candidate-improvement.v1` descriptor,
selection and component roots, an attached authorization and review, local
money/attempt ceilings, and independent runtime/provenance hashes. The feedback
path must name `feedback.json` in the four-file packet. Caller-reviewed input
hashes are forwarded into the owner; changed bytes do not get silently repinned.

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
