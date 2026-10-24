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

Each arm's parent pool and duplicate history remain separate. Identical source
from different arms is measured separately. Complete source/feedback custody,
original funded owners and the shared trial safeguard are checked between
preparation, execution and publication.

The two arms receive equal declared ceilings and opportunities. This does not
force their actual spending to match: one may fail early or use fewer calls.
The saved report retains those differences rather than buying extra attempts
for the cheaper arm.

## Failures, selection and costs

An opportunity is attempted when its original checked plan is durably saved.
It is complete when its terminal decision is saved. Rejections, duplicates,
checked generation failures, unusable scores and failed validity checks are
completed negative outcomes. They consume their opportunity and retain their
costs. An interrupted original owner remains in flight; it is not replaced by a
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
