# Bounded Python source evolution

This controller connects Buddha's existing source execution, official evaluation,
parent selection and improvement stages into a repeated development loop. The
selected agent supplies both `generate` and `propose_improvement`. Its child
inherits those entry points, so a later iteration can execute the child's own
improvement procedure.

NoveltyBench remains the fixed evaluator. The controller changes the agent's
Python file, records what happened, and decides which completed agents can
receive further development work. It does not alter the benchmark's judge,
parser, prompts or scores. [PLAN.md](PLAN.md) remains the roadmap; this guide
describes the controller's contract.

## What one run does

1. Check the frozen configuration, original source files and an existing spending
   authorization. Run a fresh development screen of the starting agent.
2. Choose an eligible parent using the existing archive, latest-parent or
   initial-parent rule. Eligibility requires usable results on every selected
   development task under the same evaluator and resource settings.
3. Save the iteration's parent choice, measured feedback and expected file hashes
   before starting its improvement worker.
4. Run that parent's improvement procedure in isolation. Retain either the
   proposed Python file, a clean proposal rejection, or an incomplete execution.
5. Screen a new child on the same development tasks. A materialized source
   matching another earlier candidate is recorded as a duplicate and is not
   rescored. Declaring the current parent's unchanged source as a completed
   mutation still violates the existing mutation guard.
6. Save the outcome. An eligible child can become a later parent. A checked code
   failure becomes feedback for a later proposal. Repeat up to the declared bound.

The allocation parameters are frozen before execution: one to eight iterations,
an archive capacity of two to 64, a selection seed, and the parent-selection
method. These are bounds, not a promise that maximum-size prompts, callbacks,
retained files and failure histories all fit the existing storage and packet
limits. A live handoff must check its actual schedule and resources separately.

## A code failure is different from an interrupted request

The prospective `buddha.source-screen.v2` uses explicit generation descriptor,
context, seal and source-reference version 2. Existing version 1 evidence keeps
its original interpretation. The worker protocol itself stays unchanged.
These numbers identify Buddha's evidence formats; the separately pinned
NoveltyBench release remains 1.1 for the current study.

| Outcome | What Buddha records | What happens next |
| --- | --- | --- |
| Complete, usable screen | Original answers, native results and common-task metrics | The child may enter the exploratory parent pool |
| Complete screen with unusable metrics | Literal native results and the reason eligibility failed | The child stays out of the parent pool |
| Checked candidate execution failure | Original worker declaration, task, source, receipts and cleanup evidence | No answers or numeric score are invented; the failure can inform a later proposal |
| Incomplete or uncertain execution | Original owner, attempt, replies and any financial hold | The iteration stops; later work cannot replace the unfinished owner |
| Rejected proposal or duplicate source | Original proposal outcome and identity | The iteration is recorded without a fresh child screen |

A checked execution failure requires the worker's accepted `agent_error`
declaration, clean owned cleanup, exit code zero, complete original callback
receipts, matching saved reports and an independently anchored completion. A
failure before the worker becomes ready must have no callbacks. This records a
worker-declared failure; it does not identify the Python exception or prove that
the code will always fail.

Timeouts, uncertain charges, quota stops, cancellation, broken protocol, missing
completion frames, incomplete callback replay and cleanup failures remain
incomplete. A partial task prefix never becomes a complete average. A terminal
failed screen explicitly lists the remaining generation and native assessment
tasks that were not attempted.

## How failure feedback reaches the improver

The worker still receives the existing list of development tasks and text notes.
The host's version 4 full-output feedback provenance binds the selected parent's measured
screen and each original parent → proposal → failed-child edge. It retains the
actual task identity, source identity, worker readiness, completed callbacks and
costs of the relevant original owners.

Every retained failure is represented in the notes, including failures descended
from a different earlier parent. The newest failure includes its complete literal source and hypothesis. Every parent answer and all diagnostic positions remain intact; failure metadata never buys room by cutting outputs. Older failed-source text is not repeated, with hashes, lengths and omissions explicit. Legacy provenance v2 keeps its original prefix policy only for original inspection/replay.

This feedback history covers checked execution failures of materialized children.
Rejected proposals and duplicates remain in the decision and cost history; this
packet does not yet describe them to later improvers. Interrupted or uncertain
operations stop the loop and cannot become a failure note.

The 1 MiB packet and full task-projection limits and 32 MiB host-bundle limit still apply. The new v2 improvement channel has no additional 4,096-byte note cap. Source-search manifest v2 fixes this full-output policy; original manifest v1 fixes historical extraction. If the required information
cannot fit, construction refuses before writing the packet or creating its
proposal owner. Search saves a `feedback_capacity` partial at the `feedback` stage when complete information cannot fit. Byte limits do not prove model context fit; the concrete full request still needs that pre-live check. Feedback describes observations; it supplies no invented score,
automatic penalty or independent diagnosis of the code.

## Resume, accounting and inspection

The root manifest fixes the comparison and is bound into the starting owner and
later owners. Each iteration retains its immutable plan, four feedback files,
proposal stage, optional child screen and decision. Resume reconstructs this
history and checks the original references before allowing later work. It does
not rely on a mutable iteration counter.

Known completed replies are replayed through their original owners without a
second charge. Unknown requests keep their holds. Shared authorization totals
and costs scoped to this search's original owners are reported separately.
Interrupted work remains explicitly incomplete, with its reason and saved
observation. Unanchored or damaged preparation may require review; elapsed time
does not authorize replacement or release a hold.

`inspect_source_search` checks a caller-pinned complete report using saved
evidence. It requires no keys, provider access, worker execution or current
producer source directories. Starting or continuing unfinished execution requires
the original executable inputs. Passive inspection does not authorize spending or
resume an incomplete experiment.

Keep the starting agent's source in a versioned archive before a live run. It is
an original selected component; the controller records its identity and location.
Materialized descendant source is retained in sealed proposal evidence. Being
able to inspect a historical result after retiring a producer path does not
replace preservation of the experiment's source and configuration.

## Python interface and present scope

The library exposes `SourceSearchSpec`, `prepare_source_search`,
`run_source_search` and `inspect_source_search` in `buddha.source_search`.
Preparation requires a prospective one-file seed named `candidate.py`, a fixed
development screen, a five-field proposal template, the specification, an existing
authorization, review metadata and an independently expected runtime hash.
The proposal template contains `config`, `profile`, `max_callbacks`,
`budget_microusd` and `max_calls`; the selected parent's protected execution
components supply the remaining improvement descriptor fields.
Caller-supplied common input bindings must not repeat the starting agent's
lineage file. The screen already binds that candidate-specific file; treating it
as a shared comparison input would make later children incomparable. Preparation
refuses this configuration before creating the search.

These are library functions, not additional PowerShell commands:

| Function | Effect |
| --- | --- |
| `prepare_source_search(...)` | Checks the declaration, writes a new search and prepares its first original owner under an existing authorization. It makes no model calls and creates no new spending allowance. |
| `run_source_search(...)` | Starts or resumes that same search. New model requests use the supplied transport and existing spending limits; saved replies are reused. A stop records its reason and retains unfinished work. |
| `inspect_source_search(...)` | Checks a pinned complete result from saved evidence. It makes no calls, starts no workers and changes no records. |

This API does not allocate funds. A separate reviewed live handoff must freeze
the actual experiment, verify its profiles and processing tiers, obtain its
specific spending authorization, and explain the operator commands. The current
POL-02 comparison and its authorization remain separate.

Task-screen eligibility checks generation and assessment. It does not pre-run
every child's improvement function. That function is checked when the child
later proposes a descendant; a missing or broken improver can stop the run with
its original evidence retained. The source-experiment and improver-competence
gates therefore remain separate from task-screen admission.

For the original source-loop delivery, 41 new acceptance methods and 92 original
regressions passed across their recorded source scopes. These were separate
cohorts, not a full local suite or one final-source test run. Its final lint,
format, types for both platforms, security, dependency and compilation checks
passed at the 204-Python source cut. Collection then found 1,480 unique test IDs;
the 99 test files and 1,439 methods from that delivery's parent were preserved.
Hosted results for that loop cut are tracked in [PR #58](https://github.com/wavemanco/buddha/pull/58).

The [confined rehearsal](conformance/src02-source-loop-delivery.json) also passes
with real isolated Python and the pinned official evaluator. Supplied programs
first produce a broken child, then use its checked failure feedback to repair
it. The repaired child's changed improvement function reads the saved task
measurements, targets the weaker task and produces a runnable grandchild.
The model replies and usage are synthetic: 75 replies, 28 original owners
(21 with operations), 28 removed workers and zero real provider calls.

A controlled host interruption after the first saved decision retains 25 replies
and ten workers' records. Continuation adds 50 replies and 18 workers without
changing that prefix. This is a saved-decision recovery check, not an interrupted
container or uncertain-charge experiment. Complete keyless replay and passive
inspection, including after retiring copied producer paths, add no work or
persistent changes. The starting source and retired files remain retained.

The rehearsal took 2,795.86 seconds, about 47 minutes, on this host. That includes
execution and repeated saved-record checks; the cause of its total wall time has
not been isolated. The separate profile below does not establish a speedup for
the full rehearsal. Practical verification latency and visible progress require
review before a live source handoff. This small run does not establish feasibility
at every maximum bound.

## Saved-record verification cost

The screen now retains its validated format suffix as one immutable value.
Reading that value preserves the existing version 1 and version 2 recipe,
context, seal, anchor and report strings. For the same input declaration, saved
JSON, fingerprints, constructor validation and detached data views remain
unchanged. Prospective installed source identities change; existing artifacts
retain their original source pins. Generic Python dataclass reflection now
includes one private field.

Thirty focused methods pass: five new format/immutability checks and 25 original
screen, outcome and replay checks. Seven quality checks pass at 205 unchanged
Python inputs and four configurations. A separate guarded inspection of the
same saved synthetic run reproduces its original report without keys, workers,
provider calls, original-database SQL or persistent changes.

The profile retains 336 format reads and removes their 336 full-document decodes.
Screen inspections (44), history reads (173), buffered reads (31,231) and file-stat
calls (1,067,379) stay equal in the two observed profiles. Total recorded function
calls fall from 204,818,675 to 180,285,607. Profiled target time is 210.543 seconds
before and 204.910 after; full wrapper time is 222.720 before and 225.389 after.
These separate instrumented observations do not establish a stable speedup.
Repeated verification remains expensive; this slice closes only the redundant
format decoding. Practical latency and visible progress remain live-handoff
requirements. [Exact evidence and limits](conformance/src02-screen-format-delivery.json).

This evidence establishes the exercised engineering mechanism. It does not
establish model-authored improvement, better unseen-task performance, or an
improver that has itself become better. Those remain separate roadmap gates.
