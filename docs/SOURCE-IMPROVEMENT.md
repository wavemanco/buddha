# Inherited one-file source proposals

[PLAN.md](PLAN.md) remains the sole roadmap. This guide describes the separate
improvement operation; [generation-v1](SOURCE-CANDIDATES.md) retains its existing
contract.

The source route can run a selected parent's improvement procedure and save its
proposed child as a new file. The parent stays unchanged. This is an execution
mechanism, not evidence of better answers or a better improver.

Each selected agent contains one regular UTF-8 `.py` file, at most 1 MiB. The
inherited file contains both functions:

```python
generate(task, config, complete) -> ordered_answers
propose_improvement(parent_bundle, development_feedback, config, complete) -> proposal
```

Generation keeps the existing interface. Improvement receives the literal parent
source, its selected filename and agent fingerprint, plus copies of the selected
development tasks and reviewed notes. It returns an exact literal Python `dict` with only `source` and `hypothesis`,
both exact literal strings: replacement source text and a nonblank explanation.
Subclasses are rejected. Source must be nonempty, differ from the parent bytes
and fit in 1 MiB; the explanation is limited to 4,096 UTF-8 bytes.

`complete(provider, body)` is the existing narrow model callback. `body` is UTF-8
JSON request bytes; the result is decoded raw provider JSON. The host fixes the
provider, model, profile, output allowance, funding and callback ceiling.
Neither function receives a key, SDK client, evaluator, full dataset, spending
database or Docker socket. Parent and child source run only inside the existing
restricted runtime; materialization never imports or executes the returned file
on the host.

## Preparing the separate improvement operation

The existing Python interface is still
`CandidateSession(gateway, descriptor=..., output=...,
expected_runtime_sha256=...)`, followed by `run()`. These names refer to already
prepared Python objects; this is not a standalone operator command. Constructing
the session validates its frozen inputs and creates a new output directory.
Running it starts one confined worker and can spend only its existing approved
Gateway allocation through model callbacks.

An improvement descriptor uses `buddha.candidate-improvement.v1`. It declares the
selected `entrypoint`, expected `parent_agent_sha256`, a pinned `feedback` file,
and the existing `config`, `executor`, `profile`, `runtime` and `max_callbacks`
(an integer from 0 through 1,000).
It uses its own dedicated, serial Gateway owner. The original generation-v1
descriptor and behavior remain separate.

The feedback file has format `buddha.candidate-development-feedback.v1`, pinned
`source` and `split` references containing absolute `path` and raw `sha256`, and
a `records` list. Each record has exactly `task_id` and `note`. It names the
complete sealed source TaskSet, not a selected subset. Notes must be nonblank
UTF-8, at most 4,096 bytes each. There must be 1 through 1,000 unique records;
both the feedback file and its projected worker input must fit in 1 MiB.
The host validates complete source membership, disjoint partitions, family and
normalized-duplicate custody, then requires every feedback ID to belong to
development. It sends only the selected task records and notes to the worker.
The worker receives a list of `{task, note}` records; each task contains only
`id`, `prompt` and `count`. Both the original feedback file and this projection
have explicit, different hash fields.

This checks source and development membership. The separate
[verified screen-feedback bridge](SOURCE-FEEDBACK.md) constructs bounded notes from
a caller-pinned complete native screen, retaining literal excerpts, measurements
and omissions. The generic interface still accepts caller-reviewed notes; it
does not require that bridge or independently authenticate arbitrary note text.
An ID check also cannot prove that a human has never copied held-out text into a
note. Opaque native reports are not passed through as feedback. The complete
dataset and split stay on the host.

The descriptor, feedback, referenced source/split, runtime artifact and existing
eight host-route source files must be original inputs of that owner. Improvement
also requires the installed `policy_study.py` helper as an original input; it does
not change the five-file selected runner. The existing selected agent, release,
runtime and protected host controls remain in force. The improvement-only split helper is checked
and bound before it is imported. Changed files stop the operation; a new hash is
not permission to adopt drift. Source fingerprints identify bytes, not their
author or review time.

## What is saved

The host chooses all output paths. The candidate cannot name another file or
replace host, measurement, profile, runtime or authority controls.

| Saved path | Meaning |
| --- | --- |
| `proposal.json` | The first available bounded terminal JSON frame, including invalid proposal evidence when received. |
| `child/candidate.py` | The exclusively written literal replacement source after successful worker exit, cleanup and host checks. |
| `lineage.json` | Original parent/child source identities, descriptor, feedback file/projection, saved proposal and owner references. |
| `report.json` | This invocation's status, reason, execution evidence, original-owner accounting and actual artifact hashes. |

A received serializable value is retained as canonical JSON, not as original
Python-object bytes. `captured` metadata is checked against that available value.
`oversized` or `omitted` metadata can retain a worker-declared serialization
digest and length while omitting the value. `unavailable` records that no faithful
serialized value was obtained; serialization failure has no invented digest or
length. `not_returned` records that the function did not provide a value. A hard
stop or invalid channel can prevent any bounded proposal frame.
The Gateway's original model replies and accounting remain separate evidence.

Proposal JSON is limited to 8 MiB within the unchanged 32 MiB framed channel and
its structural-depth limit of 64, including the terminal wrapper. Oversized or structurally non-fitting values are not
silently truncated. These are output ceilings, not a guarantee that every hostile
Python value can be serialized before process memory or wall limits stop it.

An already received bounded proposal remains evidence after invalid return
values, failed cleanup, cancellation or a later host refusal. No child is
published as successful through those failures. Partial files from an I/O failure
remain invalid retained state and are never overwritten.

Completion means source materialization, not archive eligibility. A materialized
file can still have invalid syntax, missing entrypoints or failing behavior.
Actual isolated child generation and child improvement, followed by a runnable
grandchild, are required to demonstrate the inherited mechanism. That check must
show a visible generation-procedure change, not merely a changed prompt or name.
It still does not establish useful diversity, held-out gains or improved-improver
effectiveness.

## Recovery and limits

Callbacks retain the existing ordinal, quota, raw receipt, cost and unknown-hold
rules. Improvement uses its own logical identity domain containing the original
descriptor, parent and feedback identities. The output directory is not a new
paid identity. Replaying the same contract against the same original owner can
reuse replies; a changed body at an occupied ordinal conflicts. Create a NEW
`CandidateSession` and a NEW host-chosen output directory for each attempt, while
keeping the same descriptor, selected sources, feedback, runtime pin and original
Gateway owner. Existing output directories are rejected. A session runs once;
`run()` is not a resume call on the same Python object.

A returned proposal cannot bypass an existing stop, skipped completed/unknown
operations or operations added after completion. Changed source needs a newly
frozen operation and the authority that separate work requires. This route does
not release holds, create funding, select parents, promote children, run search,
alter official scores or authorize a real comparison.

Ctrl+C saves a stopped/cancelled report when possible and re-raises the
interruption. Keep original receipts, charges, unknown holds and partial output;
a process or disk failure can leave no terminal report. Such an output is
incomplete. Inspect the original owner before attempting recovery.

## Validation and claim limits

The separate [confined competence probe](conformance/src02-competence-probe.py)
checks a parent, child and grandchild through the actual session/Gateway/runtime
path, including the child calling its inherited improvement procedure and
same-owner replay. It changes generation control flow rather than only renaming
code or changing a prompt. Model replies and proposed programs in that probe are
synthetic. No returned candidate program runs on the host.

Repository validation: 27 new improvement tests and 38 existing candidate tests pass in focused runs.
The full 1,365-test regression passes in 2,393.980 seconds with the same ten local
skips, no failures or errors, and all 182 Python inputs unchanged. Lint, format,
strict typing for Linux and Windows, Bandit, runtime dependency audit and compile
checks pass. Hosted checks for the published head remain a separate gate.

Confined-chain observation: six actual confined workers, including one same-owner replay, were removed
after execution. Five synthetic accounting owners recorded eight new fake HTTPS
replies and nine delivered callbacks; replay supplied the ninth callback without
another request. The synthetic ledger records 88 microdollars spent and no held
amount. Parent generation made two independent draft calls, the child made one
batch call, and the grandchild made one planning call followed by two drafts.
The child executed the same inherited improver body as its parent and produced
the runnable grandchild. This uses supplied programs and fake replies, with zero
real provider calls and no official evaluator execution.

The [delivery record](conformance/src02-inherited-source-delivery.json) binds the
observed results and their source/runtime identities. The probe uses short
synthetic programs and replies; it does not establish maximum-payload,
1,000-callback or arbitrary-recovery capacity. It establishes only its measured
mechanism and payload scope. It does not implement parent search,
archive admission or promotion, authenticate feedback judgments or establish
source-search efficiency. This probe preserves the inherited improver body; it
does not establish edited-improver competence or effectiveness, or demonstrate
useful-diversity gains, held-out improvement or improved-improver effectiveness.

## Assess a materialized child's saved answers

The [source-to-native connection](SOURCE-ASSESSMENT.md) can anchor a selected
child's one-task generation and pass its literal C1 to fresh official native
assessment. It does not rerun the improver, replace this guide's original chain
evidence, authenticate feedback notes or grant archive eligibility. Its confined
proof uses the actual child retained from this guide's original chain, with 23
synthetic replies and two fresh official judging occasions; the second consumes
saved answers after producer retirement. Its hosted Linux and Windows regressions
pass. The separate [common development screen](SOURCE-SCREEN.md)
now verifies matched task coverage and exploratory source-parent eligibility.
Full source-search integration and an actual model-authored experiment remain open.

The [durable proposal stage](SOURCE-PROPOSAL-STAGE.md) connects a selected
parent's verified measured feedback to the existing isolated proposal session.
It records materialized children, clean worker-declared rejections and incomplete
attempts separately, retaining original-owner recovery and passive completion
verification. The generic session still accepts caller-reviewed notes; this
stronger measured-feedback join belongs to the new stage. These lifecycle
outcomes do not establish child competence or scientific improvement.
