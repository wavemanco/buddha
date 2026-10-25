# Comparing two improvement procedures

This controller supplies the development part of IMP-01: give two fixed
improvers the same starting agents and measured feedback, then compare what
descendants they produce within equal declared limits. Its current engineering
checks use supplied workers and model replies. No funded comparison or claim
that one improver is better follows from those checks.

`initial` and `evolved` name the two declared treatments. The names alone do not
prove ancestry or improvement; a live protocol must establish that separately.
[PLAN.md](PLAN.md) owns the remaining work and experiment sequence.

The separate [sealed-assessment consumer](IMPROVER-ASSESSMENT.md) connects
completed original development records to a prospectively declared final grid
and paired analysis. That connection passes bounded composed checks and
reader-cost observations; this
development controller keeps its original scope and never consumes final
scores as improvement feedback.

## What stays fixed

The declaration fixes both improvement procedures, starting agents, development
tasks, repeated occasions, opportunity count, resource ceilings and selection
rule before work begins. The official evaluator and protected access/accounting
code remain outside the editable agents.

For each starting agent and occasion, the controller first measures that agent
and checks its ability to propose a usable further child. Both improvers then
receive the **same original measurement and full literal answers**. A later
child in one arm cannot become the other arm's starting condition or feedback.

The controller completes all common starting conditions first. It then visits
each opportunity number across the starts and occasions, alternating which
improver goes first. This is a fixed recorded order. Repeating an occasion does
not itself establish statistical independence.

## Three different kinds of agent

| Agent | Job |
| --- | --- |
| Fixed improver | Authors every counted proposal in its arm. A descendant's improver never replaces this experimental treatment. |
| Task parent and counted child | Supply the current generation procedure and its measured development outcomes. Eligible earlier children can become later task parents within their own arm. |
| Validity-only child | Shows that a parent can author a usable further child. It contributes costs and eligibility evidence, but never enters the counted descendant pool. |

## Explicit comparison feedback in study v3

A prospective `buddha.improver-study.v3` declaration requires the exact
`FEEDBACK_COMPARISON_POLICY` from `buddha.improver_study`. It retains v2's
explicit aggregate funding rules. Existing v1/v2 declarations reject the added
field and keep their original absolute feedback and reconstruction rules.

For each counted proposal, the controller records the exact selected parent's
comparison in counted plan v2:

- A common starting screen uses [fixed-study root provenance v8](SOURCE-FEEDBACK.md#a-declared-study-cell-root-belongs-to-its-fixed-improver).
  It says there is no counted parent in this cell; missing parent differences
  are null, rather than an invented zero score.
- A previously admitted child uses comparison provenance v6. It includes that
  child's full outputs beside the full outputs of its actual measured parent,
  the original change hypothesis and **child minus parent** differences in
  official distinct count, utility and recorded task cost. Negative results
  stay visible. This is a descriptive comparison, not a diagnosis of cause.

The controller derives that edge from one original earlier admitted decision
in the same start, repetition and arm, made by the same fixed improver. An equal
source hash, another arm's result or a different screening occasion cannot
substitute for it. Each arm keeps its complete original failed-generation
history. Mutation witnesses retain their existing complete absolute feedback;
they do not receive the counted comparison treatment or become extra chances
to improve a task score.

This changes what feedback the harness supplies. It does not change either
frozen improver's Python, guarantee that it uses the information well, change
NoveltyBench scoring or establish improved performance. Before a live study,
both actual actors and their prospective requests still need compatibility and
capacity checks at the declared settings.

The [bounded consumer rehearsal](conformance/imp01-comparison-consumer-delivery.json)
executes the unchanged original C improver in isolation with a small root packet
and a later child-versus-parent packet. Both emitted requests preserve the whole
note, full parent source and every literal answer. The second includes supplied
differences of minus three utility and minus one distinct answer. C's convenience
`measurement_index` contains only the task ID: its older field lookup does not
unpack the new notes. The complete notes remain in the emitted model request;
this does not show that the model attends to or uses them well. Keep that limitation
with the frozen treatment rather than silently editing C. An edited C would be
a different treatment.

Only C actually executes in that rehearsal. P's behavior, other workers, judging,
provider replies and usage are supplied. It establishes neither a new actual-P
request check nor model context capacity, realistic output headroom or improved
performance. The dated conformance driver is a pinned engineering check, not a
live-run launcher; it clears inherited credentials, uses a fake key and makes no
paid provider calls. [PLAN.md](PLAN.md) retains the remaining checks.

The [follow-up original P/C check](conformance/imp01-both-consumers-delivery.json)
now executes each frozen improver's two proposal workers in separate supplied
studies. P and C both forward the entire root/own-edge note and literal parent
source. All four stdout callback bodies match the captured HTTP bytes exactly.
P has no derived index; C keeps its task-ID-only index. Omitting the new actor
option still selects C, whose two emitted request bodies are byte-identical to
the earlier C-only captures. Original sources and earlier evidence stay unchanged.
This closes the small actual-P construction check, not future request capacity,
model use or improved performance.

The internal rehearsal driver's optional `--actor initial` chooses original P;
`--actor evolved`, or omitting the option, chooses original C. It runs once in
its invoking terminal, writes new fixture/receipt files and starts local minimal
containers with supplied provider replies. It needs no real API key and spends
no API money. Ctrl+C stops it; retain the incomplete evidence and use new output
paths for a new observation. It is an engineering check, not a live-run command.

New comparison work distinguishes a reconstruction limit
(`feedback_reconstruction_limit`, such as excessive nested edge checks) from
a byte limit (`feedback_capacity`). A stop during started execution retains its
stage, coverage, costs and original owners. An initial passive reconstruction
can instead refuse before any new work or observation is created. Neither case
shortens feedback or silently substitutes another parent.

Only a matching assessment v3 can consume a study v3 declaration. Existing
selection, final-task protection and descendant-only finalist rules remain in
force. This library connection supplies no live command or spending allocation.

Each arm's parent pool and duplicate history remain separate. Identical source
from different arms is measured separately. Complete source/feedback custody,
original funded owners and the shared trial safeguard are checked between
preparation, execution and publication.

The two arms receive equal declared ceilings and opportunities. This does not
force their actual spending to match: one may fail early or use fewer calls.
The saved report retains those differences rather than buying extra attempts
for the cheaper arm.

## Original request capacity in study v4

A prospective `buddha.improver-study.v4` declaration requires both the unchanged
comparison-feedback policy and the exact existing
`source_capacity.proposal_capacity_policy()`. Versions 1–3 reject the added
capacity field and retain their original source inventories and behavior.
Only assessment v4 can consume study v4.

Before creating study owners, preparation checks that the declared proposal
profile supports the existing context and output limits. After each completed
proposal, the controller checks the original request, raw reply, token usage,
finish status, source replacement and recorded charge. It writes a capacity
checkpoint before making a counted child's private execution copy or starting
its screen. The literal returned source is already retained as proposal data.
The same rule applies to the common starting-agent check and each child's mutation check. This reuses
the existing capacity mechanism; it makes no additional model request.

All settled calls from that proposal count, including planning calls. A later
usable reply cannot hide an earlier failed capacity check. A rejected, malformed
or programmatically produced proposal with no observed full-source replacement
does not establish capacity either. Under this declared policy, these cases
stop as a **partial result** with reason `proposal_capacity`, its exact stage,
complete planned denominators, costs and unresolved holds. The saved checkpoint
explains whether room was insufficient or the required evidence was unavailable.
They do not become completed rejected opportunities or trigger a new paid retry.

Interrupted publication reuses the original settled replies. Passive inspection
reconstructs checkpoints from those replies and refuses missing, altered,
cross-cell or premature records and child work without a consistent saved
passing checkpoint.
An unresolved provider liability stays unresolved; it does not become a capacity
measurement. Version 4 adds no request truncation, altered official score,
scientific improvement claim, spending allocation or live launch command.

## Failures, selection and costs

An opportunity is attempted when its original checked plan is durably saved.
It is complete when its terminal decision is saved. Rejections, duplicates,
checked generation failures, unusable scores and failed validity checks are
completed negative outcomes once any required v4 capacity check has passed.
They consume their opportunity and retain their costs. An interrupted original owner remains in flight; it is not replaced by a
fresh owner or extra opportunity. Unknown liability stops later work.

Later proposals receive all supported earlier failed-generation examples from
their own arm and condition, with full outputs. Other negative outcomes remain
in the journal; the controller does not invent failed-generation evidence for
them. Oversized feedback produces an explicit partial result, not truncation.

At the end, the frozen selection rule chooses from **all eligible counted
descendants** in each condition/arm. Starting agents and validity-only children
are excluded before selection. If an arm has no eligible descendant, its result
explicitly says `no_valid_descendant`; it does not substitute the starter or
silently drop that arm.

Costs are reconstructed from every original owner. Common starting work is
charged once; arm costs include failed attempts. The validity-check total is an
included subtotal, not an extra charge. Prospective screen limits include every
selected task, while the validity check uses its first ordered task once.

## Versioned funding limits

The original `buddha.improver-study.v1` declaration retains its rules: common
and arm ceilings, plus the whole-study ceiling, must equal the complete derived
grid. Its existing spending authority must cover that whole ceiling.

An explicitly selected `buddha.improver-study.v2` declaration keeps the same
common and arm ceilings, tasks, opportunities, request limits and scoring. It
allows `limits.study` to specify a smaller positive combined dollar and attempt
cap. Each amount must be at most its full-grid ceiling. The actual spending
authority must match both declared amounts exactly; preparation and passive
reconstruction both check this. A larger authority cannot silently expand the
declared allowance.

The existing shared ledger reserves each request's verified maximum charge
before sending it. If the next reservation would exceed either aggregate cap,
execution stops with an incomplete observation, its position, original coverage,
costs and unresolved holds. A cap does not guarantee that the grid will finish.
These are authorization ceilings, not expected bills or guarantees of valid
model outputs. No provider price or request bound is reduced by this version.

Because traversal is fixed, a shared cap can stop before later arms or starting
conditions run. Equal nominal arm ceilings do not imply equal realized resources
in that prefix. Keep every planned denominator; do not analyze only the finished
arms as a completed matched comparison. Final assessment still requires complete
original development. Choosing this format does not fund or adopt a study.

## Saved results and remaining assessment

The saved declaration and context bind the original inputs and authorization.
The journal retains each proposal, measured parent, failure history and terminal
decision. Partial observations preserve the exact original coverage and lower
stage outcome. Completed-report provenance binds their original bytes.

Recovery keeps the original accounting owner. A saved interruption may show
that owner as active; after the request finishes, the current record correctly
shows it as inactive. Historical verification permits that transition while
still requiring the original owner's identity, recorded costs and evidence.
Changing coverage or removing the referenced owner is rejected.

A complete development report contains all expected conditions, decisions,
selected sources or explicit absent descendants, and costs. Passive inspection
reconstructs it without keys, provider calls or a writer lock, including after
the trial has been frozen. Retired external producer programs are not needed
to reinterpret retained evidence.

The [completed-witness replay fix](conformance/imp01-passive-witness-replay-delivery.json)
corrects an earlier check that reopened those retired source files. A finished
witness still needs its original owners, funding, completion seals and saved
outputs. The reader also retains the task, generation recipe and runtime data
through its final byte check. Fresh or unfinished execution still requires
every current input file before new work can proceed.

The current declaration requires an engineering assessment marked `not_frozen`;
the resulting assessment remains `not_ready`, with target repair unassessed.
The [paired analyzer](IMPROVER-ANALYSIS.md) implements the numerical method,
including explicit empty/missing outcomes. The separate [sealed consumer](IMPROVER-ASSESSMENT.md)
now connects original development records to protected final execution and
analysis. Actual effectiveness and the prospectively defined targeted-repair
assessment remain IMP-01 work. Development completion alone does not enable
a final grant or establish a scientific result.

The original [tests-first checkpoint](conformance/imp01-finite-study-delivery.json)
remains historical evidence. The implementation checks cover the composed
development route with supplied workers and replies; they do not demonstrate
that model-authored improvers produce better descendants.
The [implementation record](conformance/imp01-finite-study-implementation.json)
separates completed focused checks, pending larger checks and exact source
versions. A check still running is not recorded as a pass.

## Library interface and optional local checks

The controller is currently a Python library:

| Function | What it does |
| --- | --- |
| `prepare_improver_study` | Checks the frozen declaration and existing allowance, then creates the new study's records. Makes no provider calls. |
| `run_improver_study` | Runs or continues that original study through its approved transport. A live transport can spend its existing approved allowance. |
| `inspect_improver_study` | Checks a complete saved report without keys, provider calls or record changes. |

This implementation supplies no live comparison command or new allowance.

```powershell
python -m unittest discover -s tests -p test_improver_study.py -v
```

Optional: run once from the matching checkout in your current PowerShell
window. These checks use supplied replies, need no keys and spend no API money.
They create temporary test data and can take tens of minutes or more. No second
window is needed; Ctrl+C stops the checks. They do not run a live comparison or
change historical experiment records.

```powershell
python -m unittest discover -s tests -p test_improver_phase_budget.py -v
```

Optional: run the aggregate-cap checks once from the matching checkout in this
PowerShell window. They create temporary records and use supplied replies, need
no keys and spend no API money. They can take tens of minutes; Ctrl+C stops them.
No separate window is needed, and they do not launch a live study.

## Rechecking finished measurements

Before choosing its next step, the controller rechecks earlier measurements
using their saved records. Previously, it followed the same completed answer
and judging trail twice: once in the controller and again in the full result
inspector. That repeated local work grew as the study accumulated results.
The revised route uses the full inspector once, then checks that every original
run, funding record and task-specific input matches the controller's declared
experiment. It also retains the check that no judging work follows a failed
answer-generation step, including an empty judging directory. Unfinished work
continues through the existing recovery checks.

This is passive verification: it needs no API keys and makes no model calls.
The full original evidence checks, exact owner identities, saved-file hashes
and whole-study safeguards remain required; completed records are not simply
trusted or reused without checking. The change removes one bounded piece of
duplicate verification. Any measured elapsed-time improvement and full-suite
test results must be reported separately once observed. It does not establish
that either improvement procedure produces better descendants.

The [delivery record](conformance/imp01-completed-screen-replay-delivery.json)
retains baseline failures, the capture correction and passing focused checks.
Larger verification runs are reported separately.

The [first reader-cost observation](RECONSTRUCTION-COST.md) now measures complete
development, freeze and final readers on one retained six-cell fixture. All six
plain/profiled reads preserve the evidence and reproduce their saved results.
This supplies an initial cost observation, rather than a measured speedup or
the larger multi-condition cost result.

The [hosted witness-replay verification](conformance/imp01-hosted-witness-replay-verification.json)
also records the full Ubuntu pass at exact PR #102: 1,756 tests and every
configured quality step, including the original full-matrix method and the new
retirement regression. Windows and later source revisions need their own results.
