# Buddha backlog context

[PLAN.md](PLAN.md) remains the single authority for priority, status, dependencies
and the next slice. This file records the context and acceptance boundaries of
unfinished commitments; it does not create another implementation schedule.

## DGM-01: complete inherited source self-improvement

Recorded October 21, 2026 after the comparison with Darwin Gödel Machine (DGM).
This records existing scope in [DESIGN sections 1–4](DESIGN.md#1-objective-and-claims)
and **SRC-02, SRC-03 and IMP-01** in [PLAN.md](PLAN.md); it is not a new milestone.
Those items remain open. The [bounded inherited source-search loop](SOURCE-SEARCH.md)
now has supplied-program confined execution evidence. The actual model-authored
source experiment and mutation competence remain open; the formal SRC-03 checks
and IMP-01 effectiveness experiment are not implemented. The
[POL-02 results and registered model review](POLICY-COMPARISON-RESULTS.md) are
complete; preparing the actual model-authored source experiment is next.

**Intended end state: yes, Buddha evolves the agent's Python code.** A parent
agent should author a child implementation, which can change how answers are
planned, generated, critiqued or selected. The child should inherit an improvement
procedure that can itself be changed by its parent and used to author further
children. This uses fixed model APIs; it does not train the foundation model's
weights. “Future work” here means unfinished original scope, rather than an
optional extension beyond the agreed endpoint.

### Why this is still open

The implemented parts are separate:

| Part | What it does today | What it does not yet do |
| --- | --- | --- |
| [Policy search](../buddha/search.py) and [policy schema](../buddha/policy.py) | A fixed proposer changes `instructions` and `sampling`, evaluates policies and retains lineage. The completed live pilots exercised this restricted path. | Author or inherit changed Python implementations. |
| [Source candidate runner](../buddha/candidate_run.py) | Runs selected generation and inherited proposal procedures in isolation; materializes a separate child with lineage under host-owned accounting. A synthetic parent/child/grandchild chain passes. The [source-to-native adapter](SOURCE-ASSESSMENT.md) connects one-task C1 to existing native assessment and passes a bounded synthetic confined proof; its hosted Linux and Windows regressions pass. The [common development screen](SOURCE-SCREEN.md) now checks fixed-task native results and guarded exploratory parent eligibility/selection; its two-source/two-task confined proof and both hosted OS checks pass, and PR55 is merged. The [verified feedback bridge](SOURCE-FEEDBACK.md) extracts bounded native measurements and literal answer excerpts into the unchanged improvement packet; the durable proposal stage preserves original-owner execution and recovery. The [bounded search controller](SOURCE-SEARCH.md) connects these stages, including failed-child feedback and later inherited mutations. See [generation](SOURCE-CANDIDATES.md) and [improvement](SOURCE-IMPROVEMENT.md). | Promote children scientifically, certify every child's mutation competence, or establish improved-improver effectiveness. The [first actual model-authored run](SOURCE-FIRST-LIVE-RESULTS.md) now demonstrates a three-child chain and a changed, used improver; all child mean scores remain below the starter. |
| [Native policy study controller](../buddha/policy_run.py) | Runs the frozen policy conditions through the baseline and official native assessment pipeline. | Propose children or invoke the source candidate runner as an evolutionary loop. |

The one-file inherited execution path, single-task native connection and common
development screen with exploratory parent selection are implemented at their
stated scope. The screen's bounded synthetic confined proof and both hosted OS
checks pass; PR55 is merged. The feedback bridge and durable proposal stage also
pass Linux and Windows CI; PR56 and PR57 are merged at their reviewed heads.
The earlier native connection's Linux and Windows regressions pass.
The [durable proposal stage](SOURCE-PROPOSAL-STAGE.md) now checks measured parent
feedback before isolated execution and preserves completed child materialization,
clean rejections and incomplete recovery separately. The bounded loop now connects
these outcomes to child screening and subsequent inherited mutations. Its rehearsal
executes supplied Python programs in real isolation with fake model replies;
it does not establish model-authored improvement. Prospective failure-aware
generation/screen v2 distinguishes checked worker-declared child-generation
failure from interrupted or uncertain execution, preserving v1 evidence. Failed
children can inform later proposals without invented answers, metrics or eligibility.
Task-screen eligibility does not certify every child's improvement procedure;
scientific promotion and broader competence gates remain open. The actual source experiment has completed; its negative development-score results and changed-improver evidence are [recorded separately](SOURCE-FIRST-LIVE-RESULTS.md).
Python execution support alone is not source self-improvement; changing prompt
text alone is policy optimization. Neither demonstrates a better improver.

### Relationship to DGM

The [DGM paper, section 3](https://arxiv.org/html/2505.22954v3#S3) describes agents
changing their own code while the foundation model remains fixed. In the
[reviewed implementation](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/self_improve_step.py),
the selected parent's coding agent performs a self-edit after ancestral patches
are applied. The resulting agent can later perform further edits. External
diagnosis and experiment orchestration still have fixed roles; this is not a
claim that every part of DGM rewrites itself.

Buddha shares the intended inherited-code mechanism, but targets useful diversity
on a pinned creativity benchmark. It is not currently an implemented equivalent
of DGM. NoveltyBench performance measures generated answers, so higher scores do
not by themselves show competence at editing code or improving future improvers.
Buddha's existing archive and promotion rules remain its own declared design;
this entry does not replace them with DGM's rules or incorporate HyperAgents code.

### Completion boundaries already required by the plan

| Existing item | Evidence needed to close its stated claim |
| --- | --- |
| **SRC-02: inherited task/improver bundles** | Version and safely materialize a bundle with `generate` and `propose_improvement`. A parent authors a substantive child change to real task Python code; the child executes in isolation and retains the ability to author further valid children. Preserve source, lineage, change hypothesis, failures and all paid operations. |
| **SRC-03: inherited improver changes** | A parent authors a change to the actual inherited improvement procedure. Preserve the initial and changed code, check protected boundaries and mutation competence, and demonstrate that the changed procedure can produce a further valid child. Merely compiling, importing or changing unused code is insufficient. |
| **IMP-01: improved effectiveness** | Compare frozen initial and evolved improvers from the same starting conditions, under equal descendant budgets and selection rules, across declared repetitions. Assess descendants on separate sealed tasks and report failures, regressions and cost as well as gains. A working source loop does not close this claim. |

Useful-diversity and generalization claims still require **EVAL-01/EVAL-02**.
Task-code evolution can succeed operationally while those scientific claims
remain negative, inconclusive or untested.

### Mutable agent, protected measurement and host

Candidate changes are confined to its authorized bundle and scoped development
memory. They may cover the generator, planner, critic, selector and improver.
They cannot change the official evaluator, judge configuration or experiment
population to make a score rise. The pinned measurement instrument, splits and
finalization controls, credentials, provider broker, budget ledger, archive
history, promotion authority, sandbox and host filesystem remain host-owned.
Invalid and failed children remain recorded and their paid attempts still count.

A benchmark upgrade remains a separate configured, checked release selection:
run the unchanged agent first, then use authorized development feedback for later
optimization. It does not grant a candidate permission to rewrite the yardstick.

The implementation sequence and dependencies remain in [PLAN.md](PLAN.md).
This entry grants no new funding and enables no paid execution. The completed first source experiment is evidence of the observed chain, not general competence or a better agent/improver.

## ENG-REF-DEPS-01: reconcile current reference dependency alerts

Recorded October 25, 2026 after GitHub's default-branch dependency notice.
The [dated metadata record](conformance/dependency-alert-scope.json) separates
the published default branch from the unmerged development stack.

At the snapshot, `main` is `1bdad29d6c7fabe3f3671af297cf1d40dd0344d1`.
GitHub reports 150 open alert rows, representing 79 distinct GHSA advisory IDs:
14 critical, 79 high, 45 moderate and 12 low. These counts describe advisory
records, not confirmed reachable exploits. The API does not identify the exact
analyzed commit for each alert.

| Scope | Alert rows | Current context |
| --- | ---: | --- |
| `requirements-dev.txt` on `main` | 16 | All 16 advisory IDs are covered by [ENG-DEV-DEPS-01's documented fixes](conformance/dev-dependency-refresh.json). The development stack has the six replacement pins; those changes are unmerged. |
| Four frozen benchmark/reference manifests | 134 | These represent 67 distinct GHSA IDs. The manifest bytes are the same on `main` and the development stack. |

The [existing native security review](conformance/nb02c3b-security-review.md)
documents a narrow research exception for the official LLM partition/scoring
CPU route and keeps CUDA preparation held. It excludes arbitrary evolved-agent
execution and does not clear every dependency or future advisory. Six current
native advisory IDs are absent from its single October 20 snapshot. That
absence alone does not establish that they are new or reachable, or that no
later review discusses them.

Reconcile the current advisory IDs and affected versions against the exact
installed CPU environment and permitted official call paths before claiming
the old exception covers all current alerts. Record applicability or uncertainty
with source evidence. Preserve frozen manifests and historical evidence; any
necessary environment change needs its own reviewed identity and compatibility
evidence. Do not mass-update dependencies or rewrite the old locks to hide the
notice. No fresh vulnerability scan or exploitability assessment occurred here.

This is a separate engineering maintenance concern. [PLAN.md](PLAN.md) keeps
IMP-01 as the sole Next item and retains the two existing scientific gates,
IMP-01 and EVAL-02. Recording this concern authorizes no merge, installation,
new execution capability or spending.

### Six-advisory applicability supplement

The [bounded follow-up](conformance/reference-six-advisory-applicability.json)
checks the six IDs against the retained installed CPU inventory, fixed official
LLM scoring path and primary maintainer advisories. It does not cover all 67
native advisory identities or clear the 134 frozen-manifest alert rows.

| Package / advisory scope | Finding for this exact route |
| --- | --- |
| AnyIO, two IDs | The installed 4.14.2 version contains both fixes. |
| NLTK, two IDs | Installed 3.9.1 is affected and NLTK is eagerly imported. The fixed LLM path does not pass task/answer text to the affected corpus-reader or resource-loader operations. This is source-level route evidence, not a general exploitability clearance. |
| Setuptools, one ID | Installed 79.0.1 is affected, but the selected Linux scoring route does not perform the advisory's Windows legacy wheel installation. |
| Certifi, one ID | Installed 2025.8.3 is affected. The worker's custom transport does not use that CA bundle for provider TLS; the host makes the HTTPS connection. Host trust-store contents and applicability remain unassessed. |

The [Certifi maintainer page](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2)
lists a 2026.10.18 patch; [GitHub's global advisory metadata](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)
lists 2026.10.19. Both representations and the original report are retained;
the old installed version is affected under either. The supplement corrects the
original external report's source label without rewriting its evidence.

ENG-REF-DEPS-01 remains open. Retain host TLS uncertainty and the other advisory
coverage gaps before any broader exception claim. This source review runs no
exploit, scan, package installation, container or provider request. It changes
no dependency, frozen lock, benchmark setting, prepared study or scientific gate.

## ENG-OBS-01: make continuation checks and stops understandable

Recorded October 29, 2026 as an existing operator-observability follow-up under
[DESIGN section 9](DESIGN.md#9-paid-operation-integrity), not a new scientific
gate or spending approval. In the frozen PR179 runtime,
`launch_trial_continuation` calls `_checked_state` before entering the ordinary
launcher's heartbeat. This full-history check can take tens of minutes with no
terminal output, before any key prompt or provider call.

The [historical handoff](UNIFIED-EVIDENCE-RECOVERY.md#operator-handoff-for-the-original-comparison)
prints one free notice before the unchanged Python command. It does not close
the progress gap. During actual execution on October 29, repeated post-key
checks also used ambiguous `checking` labels and `recorded accounting unknown`.
That text means the display has no selected budget; it does not establish a
missing ledger or failed key. Each inspection starts its own timer, and a
heartbeat or increased CPU use does not prove completed checks or forward
progress.

The terminal later reached `rechecking`, `Starting original matched development`
and `search`, then stopped automatically. The
[stop observation](conformance/trial-continuation-stop-observation.json) retains
outer phase `primary`, reason `launch_stopped`, the same 604 recorded attempts,
$4.845090 spent and zero held, and the same unfinished witness-feedback step.
The inner exception wrapper retains neither its specific failure stage nor
cause in the operator result when the coordinator supplies no receipt path.
The exact cause remains unknown; the generic code cannot diagnose credentials,
Docker, source drift or a benchmark failure. Recorded cost is not an invoice
reconciliation. The historical command is held for rerun pending diagnosis.

A future reviewed runtime should reuse the existing progress callback around
the initial passive check, distinguish repeated checking stages, and preserve
fixed safe failure causes and stages through inner and outer wrappers. Keep
raw exception text and credentials out of reports. Retain source/accounting,
freshness, budget and isolation guards, the no-provider-before-keys boundary
and explicit incomplete records. A delayed-check fixture should demonstrate
periodic liveness without inventing completed work; a no-cost rehearsal against
realistically sized retained history should exercise the actual stopped path
and safe error propagation before any new paid handoff. Keep the frozen
runtime unchanged and require separately checked repair/continuation evidence.
PLAN.md retains IMP-01 as Next and the two existing scientific gates; this
follow-up grants no new funding or execution authority.
