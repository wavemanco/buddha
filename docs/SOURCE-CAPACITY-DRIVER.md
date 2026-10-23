# The one-request capacity driver

This implements the [frozen protocol](SOURCE-CAPACITY-PROTOCOL.md). It has only
been checked offline with synthetic replies and mocked HTTPS. **There is no
funded handoff or live command to run yet.** No actual token count or replacement
output margin has been measured. [PLAN.md](PLAN.md) owns the next step.

The driver sends one already saved request through Buddha's existing Gateway.
That request contains the complete historical answers. It saves the literal
reply and usage, then checks whether a complete changed-source proposal and
both declared token cushions are present. Returned Python remains text; the
driver does not execute or adopt it, generate answers or score NoveltyBench.
The historical measured parent and prospective full-output starter remain
separately identified.

## What is checked before a key is requested

The separately supplied handoff hash binds the output location, exact request,
protocol, installed Python sources, selected components, profile, timeout,
account assertion and one-attempt authorization terms. The launcher checks
these inputs, the Gateway's request/header rules and any existing original
owner. Changed or unsupported inputs stop before key entry, owner creation or
reservation. It checks again after key entry and while holding the writer lock.

The authority must already exist with the approved terms. The driver cannot
create an allowance, use an older experiment's balance or open a replacement
owner. Account settings and prices still require a human-verified profile;
recorded costs are not reconciled invoices. Only a local OpenAI inference key
is needed for this target. No Anthropic call is involved.

## Results and recovery

`report.json` names the measurement status, stage, reason, usage, cushions and
original accounting. The original Gateway owner retains the request, raw
response and physical operation. Attempt files and the completion seal bind the
assessment to that receipt. Saved reports are checked by deriving the assessment
again, rather than trusting their saved status.

| Situation | Behavior |
| --- | --- |
| Complete proposal, both cushions pass | Complete measurement with decision `pass`. |
| Complete proposal, a cushion fails | Complete negative measurement with decision `fail`. |
| Settled reply is truncated, refused, invalid or unchanged | Terminal partial measurement with its reason; seal and deactivate the owner. No second paid opportunity. |
| Timeout or unknown provider liability | Partial observation; retain the original hold and stop before another key prompt or send. |
| Failure while preparing a connection, before dispatch | Partial observation; retain the known-unsent reservation. A deliberate rerun can use that same original operation. |
| Assessment interrupted after a settled reply | Retain the partial observation and raw evidence. Finish from that original reply without keys or another send. |
| Completion seal lacks its original authority anchor, or sealed outputs change | Refuse; do not repair the seal, replace the owner or send again. |

An execution failure before completion is saved under `observations` where the
original output structure is available. An invalid handoff or incomplete owner
preparation is a refusal, not permission to recreate its directory. A hard kill
can leave a writer lock; elapsed time never authorizes deleting it. Further
recovery requires review of the original records.

## Command reference for a future approved handoff

These are templates, **not commands for an existing approved run**. Replace both
placeholders only with the exact path and hash supplied in a funded handoff.
Use one PowerShell window in the matching checkout; no second window is needed.

```powershell
python docs\conformance\src02-capacity-run.py --handoff '<APPROVED_HANDOFF_PATH>' --expected-sha256 '<APPROVED_SHA256>'
```

Runs once without spending money. For an untouched allocation it checks the
inputs and reports `ready`, without asking for a key or creating an owner. If
that original request is already settled, it finishes or verifies the saved
measurement from the recorded reply. That replay can write local reports and a
temporary writer lock; it makes no API request. It never clears an unknown hold.

```powershell
python docs\conformance\src02-capacity-run.py --handoff '<APPROVED_HANDOFF_PATH>' --expected-sha256 '<APPROVED_SHA256>' --live --prompt-keys --confirm-project-key
```

Runs the one approved request, or resumes its eligible original state. This can
spend money only within the separately approved cap and one-attempt limit.
`--prompt-keys` asks locally for a hidden OpenAI key if one is not already in
that PowerShell process. `--confirm-project-key` records your confirmation that
the key belongs to the reviewed account; it does not verify account settings
with the provider. A completed reply is replayed without requesting a key.

Both commands exit when finished. During execution a progress line appears
about every ten seconds, except during hidden key entry. Ctrl+C requests a stop;
usable evidence and uncertain charges remain. Do not start a second copy or
delete a lock. Exit code `0` means a complete measurement, including a negative
decision; `1` means ready or partial; `2` means the checks refused or execution
could not proceed. Read the saved decision as well as the exit code.

## Verification scope

Six pure assessment/guard methods and ten launcher methods pass at their
separately recorded cuts. The launcher checks use real Gateway/shared accounting
with mocked HTTPS, fresh temporary databases and blocked external networking
and processes. Regression checks first reproduced missing preflight validation,
paid-enabled cached transport, unsent-failure reporting and argument redaction
gaps. Static review and seven quality checks are recorded separately in the
[delivery](conformance/src02-capacity-driver-delivery.json).

This is focused engineering evidence. The exact retained-body offline rehearsal,
fresh hosted full-suite results, current-price/account review, new allocation and
actual model observation remain separate prerequisites. None of these checks
establishes useful-diversity improvement, child competence or future request fit.
