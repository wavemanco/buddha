# Close adaptive work before final evaluation

This EVAL-01 foundation connects a trial-wide writer check to the existing source
search, feedback, generation, improvement, native assessment and validation
controllers. It makes closing improvement work enforceable at those entry points.
It does not yet supply the finalization controller, a final task schedule or a
command for starting a scientific trial. [PLAN.md](PLAN.md) owns the remaining
sequence.

## What the check protects

A trial has three separate, original spending grants: search, validation and
final evaluation. Their exact paths, identities, immutable terms, amounts,
attempt limits and purposes are recorded in fixed funding metadata. The phase
allocations must add up to the fixed combined allowance. A grant from another
phase or another trial cannot replace the original one.

Three fixed files identify the trial: `.buddha-evaluation-trial.json`,
`definition.json` and `funding.json`. Every newly prepared owner includes their
hashes among its original inputs. These are structural engineering checks;
opaque definition bytes alone do not establish a complete scientific protocol,
independent task custody or a preregistered population.

The trial has one serial writer lock, acquired before local controller locks or
accounting mutations. Nested operations reuse that same original ownership.
Another process, thread or copied ownership token cannot use it. A retained or
replaced lock is refused; elapsed time does not authorize deleting it.

The direct Gateway call keeps this lock through sending the request and recording
its outcome. The generation, improvement and native Sessions also check it before
creating output, throughout their run, and before handling worker callbacks.
Calling those public interfaces directly cannot bypass the controller's check.

| Situation | Result |
| --- | --- |
| Valid search or validation grant, open trial | Only the operations allowed for that phase can prepare or continue work. |
| A marker is malformed, missing or inconsistent with a trial-scoped grant | New work stops before creating its destination or acquiring its local writer lock. |
| Any entry exists at the trial's `freeze` path | New adaptive work stops. A partial or malformed freeze entry closes it too. |
| Final-phase grant | New execution remains disabled until the actual final-schedule consumer is implemented. A fabricated ready file cannot enable it. |
| A complete result already exists | The supported passive reader can verify and return it without obtaining a key or starting a worker. |
| A dispatched request still needs its known result recorded | Settlement retains its original accounting route; closing work does not erase a reply or release an unknown hold. |

The future finalization controller must consume the full prospectively declared
schedule, populations, finalists, numerical rule and original funding before it
can permit final work. This foundation does not implement that consumer or make
a finalization or improvement claim.

## Feedback and historical runs

Creating a new feedback packet is an improvement operation even though it makes
no model call. Its writer checks every referenced parent, proposal and child
screen, as well as the destination, under the same original grant. Choosing a
destination outside a closed trial cannot bypass the source-side check. The
writer uses already verified report terms; it does not construct a live
authorization object or open a financial database. Pure feedback construction
and inspection remain available as passive data operations.

The [complete-output contract](SOURCE-FEEDBACK.md) is preserved. No answer is
shortened by this change. Full packets still stop explicitly at their existing
resource limits.

The trial mechanism is opt-in. Existing unmarked runs retain their existing
scope rules and identities. Passive source readers use the original owner's
recorded helper profile, so a pre-fence owner is not required to have recorded a
file that did not exist when it ran. New owners must include the new helper.
Unknown helper profiles and missing new-helper bindings are refused. This is
not permission to rewrite an old manifest, reseal a run or execute retired code.

Validation preparation inside an opted-in trial now requires the explicit
original `Authorization` object. Legacy metadata preparation outside a trial
keeps its existing signature behavior. No function chooses a grant from the
environment or creates an allowance automatically.

## Check this foundation offline

```powershell
python -m unittest discover -s tests -p "test_trial_fence*.py" -v
```

This runs the trial-check tests once in the current PowerShell window. They use
temporary synthetic data and simulated workers and provider replies, with real
temporary accounting files. No key, Docker worker or paid call is required.
Ctrl+C stops the foreground checks. Passing them is engineering evidence, not
evidence that an agent improves on unseen tasks.

The [delivery record](conformance/eval01-trial-fence-delivery.json) preserves the
failing checks and their fixes. At the final source cut, nine targeted methods
and 36 composed regression methods pass; these overlap and are not 45 different
tests. Seven quality checks also pass. An earlier 47-method regression passed
before the final direct-call fixes and remains tied to that earlier cut.

A separate final-cut passive proof reads six genuinely older publications while
preserving their 429 retained files. It does not finish the interrupted search.
The proof uses memory-only database reads and does not execute retired source.
The regression cohorts use simulated workers and replies with fresh temporary
accounting files. They do not establish a full-suite or hosted-CI pass, repair
the separate Docker startup fault, or close the finalization/scientific gates.
