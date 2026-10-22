# Buddha backlog context

[PLAN.md](PLAN.md) remains the single authority for priority, status, dependencies
and the next slice. This file records the context and acceptance boundaries of
unfinished commitments; it does not create another implementation schedule.

## DGM-01: complete inherited source self-improvement

Recorded October 21, 2026 after the comparison with Darwin Gödel Machine (DGM).
This records existing scope in [DESIGN sections 1–4](DESIGN.md#1-objective-and-claims)
and **SRC-02, SRC-03 and IMP-01** in [PLAN.md](PLAN.md); it is not a new milestone.
Those items remain open. The first SRC-02 mechanism now has bounded synthetic
execution evidence; the full inherited search loop and actual model-authored
source experiment remain unfinished. The current next slice remains POL-02.

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
| [Source candidate runner](../buddha/candidate_run.py) | Runs selected generation and inherited proposal procedures in isolation; materializes a separate child with lineage under host-owned accounting. A synthetic parent/child/grandchild chain passes. The [source-to-native adapter](SOURCE-ASSESSMENT.md) connects one-task C1 to existing native assessment and passes a bounded synthetic confined proof; its hosted Linux and Windows regressions pass. The [common development screen](SOURCE-SCREEN.md) now checks fixed-task native results and guarded exploratory parent eligibility/selection; its two-source/two-task confined proof and both hosted OS checks pass, and PR55 is merged. The [verified feedback bridge](SOURCE-FEEDBACK.md) extracts bounded native measurements and literal answer excerpts into the unchanged improvement packet; the durable proposal stage now preserves original-owner execution and recovery; the full search orchestration remains open. See [generation](SOURCE-CANDIDATES.md) and [improvement](SOURCE-IMPROVEMENT.md). | Connect source proposal, feedback, evaluation and selection into the inherited search loop, promote children scientifically, run a model-authored source experiment, or demonstrate a competent changed improver and its effectiveness. |
| [Native policy study controller](../buddha/policy_run.py) | Runs the frozen policy conditions through the baseline and official native assessment pipeline. | Propose children or invoke the source candidate runner as an evolutionary loop. |

The one-file inherited execution path, single-task native connection and common
development screen with exploratory parent selection are implemented at their
stated scope. The screen's bounded synthetic confined proof and both hosted OS
checks pass; PR55 is merged. The feedback bridge's Windows check remains pending.
The earlier native connection's Linux and Windows regressions pass.
The [durable proposal stage](SOURCE-PROPOSAL-STAGE.md) now checks measured parent
feedback before isolated execution and preserves completed child materialization,
clean rejections and incomplete recovery separately. Connecting those outcomes
to child screening and subsequent inherited mutations, scientific promotion,
source search and a model-authored experiment remains open.
The loop must expose retained failures to later proposals. It must distinguish a
finished worker-declared child-generation failure from an interrupted or uncertain
execution, without inventing answers, metrics or archive eligibility. The current
generation-v1 path deliberately leaves those failures incomplete; a prospective
failure-aware contract is needed before claiming a failure-aware search loop.
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
This entry grants no new funding, enables no paid execution and claims no
completed source-evolution experiment.
