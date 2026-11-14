# Reliability infrastructure around Buddha's improvement loop

Research checked October 30, 2026. This note answers whether established projects
already address the execution, interruption and recovery problems surrounding
Buddha's DGM-style improvement loop. **Yes: substantial reusable infrastructure
exists. Inspect AI is the closest evaluation platform; DBOS is a promising small
workflow component; Temporal is the stronger candidate when distributed,
versioned workers justify operating another service.** These are recommendations
for a bounded compatibility experiment, not demonstrated integrations.

[PLAN.md](PLAN.md) remains the scheduling authority. This research installs no
dependency, changes no executing source, migrates no records and authorizes no
API spending. The stopped experiment and its scientific settings remain frozen.

**November 12 follow-up.** Inspect has passed the real offline trace, error and
viewer endpoint check. A separate no-model check confirmed that Inspect's
retry skips a completed sample. The first place to evaluate replacing
scheduling and progress code is a fresh final assessment and its two plain controls.
Adoption requires interruption and resume with matching official scores and
accounting. The DBOS wrapper probe removed no production code. Keep it out of
the current recovery and reconsider only if it can replace existing restart
bookkeeping. [Inspect proof and adoption boundary](INSPECT-OBSERVABILITY-PROOF.md).

## What problem are we solving?

The current phase combines reliability engineering with experimental integrity.
The evolutionary algorithm chooses and changes agent procedures. The surrounding
infrastructure must finish work across process failures, account for requests,
identify the code that produced each result and distinguish an agent failure
from an infrastructure failure.

The retained experiment stopped at 657 completed attempts, $5.523144 recorded
cost and zero held. Its last generation attempt failed before worker readiness;
cleanup remained unconfirmed, the container ID was missing and the original
executor cause was lost. Separate profiling found repeated reconstruction of
accumulated evidence. These are different problems: restarting a workflow does
not recover an error that was never saved, prove container cleanup or make
repeated validation cheap. See the [stop record](conformance/continuation-executor-stop-observation.json),
[partial profile](conformance/current657-reconstruction-profile-delivery.json)
and [current roadmap](PLAN.md#current-checkpoint).

Useful infrastructure separates four responsibilities:

| Responsibility | Plain-English meaning | Buddha must retain |
| --- | --- | --- |
| Durable execution | Save completed steps so a crash need not restart everything | Original operation identities and completed replies |
| Paid-call accounting | Know what may have been charged, even when the reply is missing | Reservations, uncertain-outcome holds and shared authorization |
| Isolated execution | Start, observe and clean up an untrusted agent process | Restricted mounts, networking, credentials and resource limits |
| Scientific provenance | Know exactly which treatment and evaluator produced a result | Source bytes, official NoveltyBench protocol, sealed tasks and immutable history |

An **idempotent** operation can be repeated without producing an additional
effect. An API timeout does not establish that the provider did nothing. For
example, a provider might finish a paid request just before the connection fails.
Saving workflow state and preventing a second charge are therefore separate
contracts. The platforms below explicitly require care around repeated external
effects; their workflow guarantees alone do not establish Buddha's financial
guarantees. This distinction follows directly from the
[Temporal activity contract](https://docs.temporal.io/activity-definition#idempotency)
and [DBOS recovery description](https://docs.dbos.dev/architecture#how-workflow-recovery-works).

## Which existing systems are relevant?

| Project | How it addresses the problem | Potential place in Buddha | Main qualification |
| --- | --- | --- | --- |
| [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) | Evaluation logs, recovery, sample checkpoints, sandboxes and model adapters | First platform to assess for evaluation orchestration and result inspection | Checkpoint, model-routing and budget semantics need explicit adaptation |
| [DBOS](https://github.com/dbos-inc/dbos-transact-py) | A Python library records workflow and step outcomes in a database | Small outer workflow experiment around existing stages | An interrupted external step can execute again |
| [Temporal](https://github.com/temporalio/temporal) | Durable workflow history, activities, retries and versioned worker routing | Later distributed execution, if operational scale warrants it | Another service; activity idempotency and source identity remain our responsibility |
| [Harbor](https://github.com/harbor-framework/harbor) | Agent/task/sandbox interfaces and a centralized failure policy | Alternative evaluation platform; failure classification pattern now | Avoid running two competing evaluation coordinators |
| [SWE-ReX](https://github.com/SWE-agent/SWE-ReX) | Separate deployment and runtime interfaces with startup/health/stop stages | Sandbox lifecycle component or implementation reference | Its HTTP runtime is not a drop-in replacement for Buddha's confinement |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Checkpointed graph/task execution and resumable state | Consider if the agent itself later benefits from graph-based control | Default resume uses the latest graph; code identity needs extra controls |
| [Restate](https://github.com/restatedev/restate) | Journaled steps and deployment-pinned service invocations | Technically relevant comparison | Server licensing needs a separate decision |

The table combines documented capabilities with **our assessment of fit**. No
candidate was installed, benchmarked or tested against Buddha during this study.

## Inspect AI: the closest evaluation-platform match

Inspect saves completed samples and can retry failed evaluations while retaining
the task identity and producing a new log. Its sample buffer also supports
recovery after a hard crash. Importantly, its documentation warns that selective
retries can bias results when failures depend on the input. A recovery policy is
part of the experiment, not just an operational convenience.
[Primary documentation](https://inspect.aisi.org.uk/handling-errors.html).

Its agent checkpoints capture conversation/state and selected sandbox files at
defined boundaries. Custom agents must cooperate with the checkpoint interface;
this does not preserve arbitrary process memory, a running tool or an external
side effect. Checkpoint metadata is committed after capture, and orphaned
captures are discarded. Successful-sample checkpoints are deleted by default;
checkpoint failures can warn and continue unless configured strictly. Those
defaults would need deliberate changes for our retained-evidence requirements.
[Checkpoint contract](https://inspect.aisi.org.uk/checkpointing.html).

There is a concrete compatibility hazard: the sandbox agent bridge can map an
unrecognized requested model name to the evaluation model, with a warning.
Buddha requires a verified model identity and only the declared official refusal
fallback. We should use a strict adapter or keep our gateway, and test the actual
outgoing request rather than infer compatibility from a model label.
[Bridge model routing](https://inspect.aisi.org.uk/agent-bridge.html#models).

Inspect also documents cost limits based on model usage and pricing. That is
useful, but the documented limit interface does not by itself establish our
pre-dispatch worst-case reservation and uncertain-charge hold contract. Keeping
Buddha's broker authoritative is a **design inference**, pending an adapter test.
[Limit semantics](https://inspect.aisi.org.uk/setting-limits.html).

This is an actively maintained engineering solution to closely related problems.
Its changelog records fixes for exception chains and memory spikes while
finalizing long samples. METR also says it is moving from Vivaria to Inspect and
recommends Inspect for new evaluation projects. That supports prioritizing
Inspect over a fresh Vivaria deployment; it is not proof of compatibility or a
performance guarantee for Buddha.
[Inspect changelog](https://inspect.aisi.org.uk/CHANGELOG),
[METR's own transition notice](https://vivaria.metr.org/).

**Recommendation:** assess one small integration boundary first, such as an
export/viewer adapter or one synthetic evaluation stage. Keep the official
NoveltyBench evaluator authoritative. Do not replace its grouping or utility
calculation with a convenient platform scorer.

## Durable workflows: DBOS and Temporal

DBOS stores the outcomes of workflow steps and recovers after interruption.
Completed checkpointed steps are reused; an interrupted step without a saved
outcome can run again. External API effects still need idempotency or explicit
uncertainty handling. For Buddha, an unknown paid-call outcome should be a
retained state requiring the existing accounting decision, rather than a generic
exception that the workflow framework automatically retries.
[Recovery mechanics](https://docs.dbos.dev/architecture#how-workflow-recovery-works),
[step contract](https://docs.dbos.dev/python/tutorials/step-tutorial).

DBOS is attractive because it can be embedded as a Python library without a
separate orchestration server. The inspected configuration supports SQLite;
production guidance recommends PostgreSQL. Its versioned recovery uses
application versions, with a default derived from workflow code. That is not a
hash of Buddha's whole source closure. We would retain our explicit source
inventory and keep old versions available for their original work.
[Tagged configuration](https://github.com/dbos-inc/dbos-transact-py/blob/3.4.0/dbos/_dbos_config.py),
[production checklist](https://docs.dbos.dev/production/checklist),
[workflow upgrades](https://docs.dbos.dev/python/tutorials/upgrading-workflows).

DBOS also recommends avoiding large workflow return values. That maps well to
small references to separately retained artifacts, rather than repeatedly moving
every story and receipt through the workflow journal. Whether this reduces
Buddha's reconstruction cost is an **unmeasured hypothesis**, not a result of
this research.
[Scaling guidance](https://docs.dbos.dev/architecture#how-dbos-scales).

Temporal is appropriate when workflows need to survive worker/process failures
across machines. Activities perform external work; their idempotency remains an
application concern. Worker Versioning can pin a workflow to a deployment
version, a useful model for preserving old software alongside new software.
However, independent activities on other queues/deployments are an explicit
exception to that routing. Deployment pinning also does not prove that the
deployed bytes match our approved source inventory.
[Activity idempotency](https://docs.temporal.io/activity-definition#idempotency),
[Worker Versioning and activity behavior](https://docs.temporal.io/worker-versioning).

Temporal requires a service, persistence and workers, or a managed service.
Its Python workflow sandbox checks some replay/determinism constraints; the SDK
explicitly says it is not a security sandbox. It cannot replace the container
boundary around evolved Python.
[Production deployment](https://docs.temporal.io/production-deployment),
[SDK security limitation](https://github.com/temporalio/sdk-python/blob/1.35.0/README.md#sandbox-is-not-secure).

**Recommendation:** DBOS is the first lightweight workflow candidate to test
offline. Temporal becomes preferable if distributed execution and managed worker
versions outweigh its operational cost. This ranking is our engineering
judgment, not a comparative benchmark or an adoption decision.

## Smaller components and patterns worth reusing

Harbor centralizes trial errors into a policy that decides cause, retry,
verification and whether the result counts. It distinguishes agent exhaustion
or refusal from sandbox, provider and verifier failure. Its source also defaults
unknown errors to a retryable policy, which we should not copy for uncertain
paid calls. The useful idea is one typed policy shared by live errors and saved
results; the exact retry and score rules must follow Buddha and NoveltyBench.
[Policy documentation](https://docs.harborframework.com/jobs/error-classification),
[policy source](https://github.com/harbor-framework/harbor/blob/c23909f47508af47a70321eb22c2b40aa190ca5d/src/harbor/models/trial/error_policy.py).

Harbor is also a possible complete evaluation platform with configurable jobs,
agents and sandboxes. Hosted orchestration features should not be assumed to be
present in the local open-source runner. Assess Harbor as an alternative to
Inspect, rather than adding both as competing controllers around the same work.
[Job documentation](https://docs.harborframework.com/jobs/run-a-job),
[sandbox interfaces](https://docs.harborframework.com/sandboxes/pre-integrated-sandboxes).

SWE-ReX separates environment deployment from the runtime that executes commands.
Its Docker implementation assigns a container name before launch, then checks
runtime health; stop uses bounded cleanup attempts and warnings. Assigning and
retaining an intended identity before creation is directly relevant to our
missing-container-ID failure. It improves reconciliation but cannot guarantee
that cleanup succeeds. Its HTTP runtime and published port differ from Buddha's
current network restrictions, so adopting the runtime requires a separate
security/transport review.
[Architecture](https://swe-rex.com/latest/architecture/),
[Docker implementation](https://swe-rex.com/latest/api/deployments/docker/).

LangGraph checkpoints state and task results, but its documentation says resumed
threads use the latest deployed graph. The inspected version also defaults to
asynchronous checkpoint durability; synchronous durability is available. Its
interrupted tasks still require idempotency. These defaults need explicit
adaptation before it can orchestrate a source-frozen experiment. Editable state
and time travel are useful agent features, not an immutable financial archive.
[Resume compatibility](https://docs.langchain.com/oss/python/langgraph/backward-compatibility),
[durability modes](https://docs.langchain.com/oss/python/langgraph/checkpointers#durability-modes),
[task idempotency](https://docs.langchain.com/oss/python/langgraph/functional-api#idempotency),
[persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

Restate journals steps and routes existing invocations to their deployment.
An external side effect can still repeat if failure happens before the result
is durably journaled. Its Python SDK is MIT, but the inspected server is BSL 1.1,
with an additional-use grant and later Apache conversion. We should not describe
the whole platform as MIT or add it under a blanket permissive-dependency policy.
[Durable steps](https://docs.restate.dev/develop/python/durable-steps),
[external side-effect limitation](https://restate.dev/blog/why-we-built-restate#side-effects),
[service versioning](https://docs.restate.dev/services/versioning),
[server license](https://github.com/restatedev/restate/blob/v1.8.1/LICENSE),
[SDK license](https://github.com/restatedev/sdk-python/blob/v1.1.0/LICENSE).

Google's Harness² remains relevant to the improvement algorithm. Its README
documents Propose–Probe–Compose and resumable result directories, but also
unrestricted executor networking and disabled Codex sandboxing by default.
Its research setup is not a substitute for Buddha's paid-call, provenance and
untrusted-code controls. Retain it as algorithmic inspiration without reopening
the whole design.
[Pinned README](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/README.md#results-and-resume).

## Reuse decision for the stopped experiment

Updated October 30, 2026 after the user's correction: the research must reduce
implementation work now, rather than merely recommend another study after all
custom recovery work is finished. [PLAN.md's current checkpoint](PLAN.md#current-checkpoint)
is the single schedule. The [decision delivery](conformance/reliability-reuse-decision.json)
records the bounded offline probe and source trace; neither clears a paid restart.

### Reuse the complete runner and existing retry machinery first

A public-code trace found an important distinction: the original pinned runner
already contains the full development, freeze, final, both plain-reference and
publication sequence. A third host version is needed to deploy newer helpers,
not inherently to perform the scientific comparison. The original one-action
hook already provides normal work leases and accounting. The native pipeline
already handles same-owner attempt ordinals, saved replies and sealing.

The smallest direct recovery case is therefore: reconcile the failed runtime's
cleanup; retain the failed pre-ready attempt, owner UUID and manifest; exercise
the next ordinary attempt through the existing screen action, including its
declared task rows; stop before the next study action, witness or cell. Reentry must verify completion or refuse target drift. Reuse
those paths and existing fixtures instead of adding another retry scheduler.
This is a selected acceptance case, **not an executed recovery test**.

The original runner may still be too slow in practice. Its retained 604-prefix
check took 1,753.039 seconds; its later 657-prefix profile reached a 300-second
observation deadline before the first restoration returned. These observations
have different scopes and establish no timing ratio or full 657-history bound.
They do identify why an unchanged runner cannot be cleared merely because its
phase sequence exists. See the [profile delivery](conformance/current657-reconstruction-profile-delivery.json).
A narrow host upgrade remains an option if that measured cost or a necessary
repair justifies it; broader mixed-version machinery is parked unless required.

### What the isolated DBOS test can and cannot establish

The follow-up checks pinned DBOS 3.4.0 in a separate local environment, using
SQLite, small artifact references and supplied model replies. It changes no
production dependency or original record. Separate-process crash/restart is the
relevant boundary: repeatedly calling a function in one process is insufficient.
The retained probe distinguishes a saved step from an interrupted step without
a checkpoint, and exercises Buddha's existing Gateway rather than inventing a
replacement accounting ledger. Missing, failed and unmeasured cases remain
explicit in the delivery.

DBOS's documented recovery reexecutes an uncheckpointed step; disabling configured
exception retries does not remove that recovery behavior. Its checkpoint cannot
substitute for the Gateway's reservation/uncertain-outcome policy or the source
and work-lease checks. Nor does wrapping the current study loop remove the
history reconstruction *inside* that loop. A wrapper earns adoption only if it
replaces a concrete owned responsibility with less maintained code and passes
these integration boundaries. A successful generic crash/restart demonstration
alone does not satisfy that condition.
[Recovery contract](https://docs.dbos.dev/architecture#how-workflow-recovery-works),
[configured step retries](https://docs.dbos.dev/python/tutorials/step-tutorial#configurable-retries).

License qualification: DBOS's core is MIT, but the stock pinned installation
requires psycopg with its binary extra. The trial resolves an LGPL-licensed
PostgreSQL driver even though it uses SQLite. This was flagged before local
use; no LGPL component is vendored or added to Buddha's distributed dependency
path. An eventual adoption must consider the complete dependency closure.
[DBOS dependency declaration](https://github.com/dbos-inc/dbos-transact-py/blob/3.4.0/pyproject.toml),
[psycopg license](https://github.com/psycopg/psycopg/blob/3.3.6/LICENSE.txt).

The bounded probe finished in **7m23s** within its 15-minute timebox on native
Windows. The saved step ran once across two processes. An interrupted step was
entered twice, but the existing Gateway blocked a second supplied send with an
unknown-operation hold despite ample remaining funds. The source-drift case
retains a typed rejection; its fixture was cleaned, so zero-operation accounting
was not verified. Observer startup/expected-exit errors and unverified whole-tree
child cleanup remain qualified. No Linux, original-history or full-phase
integration was tested. Root independently rehashed the bound artifacts and
checked process/step/send joins without rerunning a worker or opening a database.

**Decision: do not adopt DBOS for the current recovery.** The prototype removes
zero production code. Reuse the existing full-phase coordinator and retry
pipeline; park broader host-version machinery unless the bounded recovery test
shows it is necessary. DBOS remains an unadopted candidate for replacing generic
journaling in a future clean-run runner. This negative decision does not license
unbounded custom salvage.

### Scope and decisions

| Component | Current decision | Development time it should save |
| --- | --- | --- |
| Existing full-phase runner, one-action hook and native retry pipeline | Reuse first; prove the targeted failed-screen boundary before broader integration | Avoid a new phase coordinator and retry scheduler; keep existing owner/accounting semantics |
| DBOS | Bounded probe complete; do not adopt into current recovery, since this wrapper removes no maintained responsibility | Can replace outer durable-step bookkeeping only if an integration actually removes it; cannot fix internal reconstruction or missing old evidence |
| Inspect AI | Retain as a candidate for a later clean evaluation runner, not a current viewer/exporter side project | Potentially replaces evaluation orchestration; an exporter would not remove the present bottleneck |
| Harbor / SWE-ReX patterns | Adapt typed failure preservation and durable intended runtime identity where a concrete repair needs them | Reuse lifecycle/failure design instead of inventing another policy layer; preserve confinement and accounting |
| Temporal / other full platforms | No deployment for this recovery | Avoid new service and migration work without a distributed requirement |

These are engineering decisions about the current local experiment, not claims
that a platform cannot support Buddha. Before further implementation, name the
selected route, the responsibility it removes and the end-to-end acceptance
case. If a bounded rehearsal shows salvage needs a broader architecture,
explicitly compare its remaining cost with a separately approved clean experiment.
Preserve the old partial and its costs in either case. Do not silently migrate
history, repeat paid operations or relabel a new run as continuation.

## Source register and limits of this research

Only first-party documentation, author repositories, source and license files
support the external claims above. Documentation pages are living references
checked on the stated date. The source cuts below are research references, not
installed or approved dependencies. A top-level license does not clear every
transitive dependency, hosted product, model or dataset.

| Project / inspected source | Core license evidence | Deployment qualification |
| --- | --- | --- |
| Inspect AI `7340817a6fb5eb20c14520d13ce8c146d2d893c8` | [MIT](https://github.com/UKGovernmentBEIS/inspect_ai/blob/7340817a6fb5eb20c14520d13ce8c146d2d893c8/LICENSE) | Python evaluation platform; no local compatibility trial performed |
| Harbor `c23909f47508af47a70321eb22c2b40aa190ca5d` | [Apache-2.0](https://github.com/harbor-framework/harbor/blob/c23909f47508af47a70321eb22c2b40aa190ca5d/LICENSE) | Local framework and hosted features are separate scopes |
| SWE-ReX `5c995c365dfb1fd5bc56fda688be5d8538f9931f` | [MIT](https://github.com/SWE-agent/SWE-ReX/blob/5c995c365dfb1fd5bc56fda688be5d8538f9931f/LICENSE.txt) | Runtime/backend confinement must be assessed separately |
| DBOS Python `3.4.0` | [MIT core](https://github.com/dbos-inc/dbos-transact-py/blob/3.4.0/LICENSE) | Enterprise features are separate; inspected integration CI is [Ubuntu](https://github.com/dbos-inc/dbos-transact-py/blob/3.4.0/.github/workflows/unit-test.yml), not proof of native Windows compatibility |
| Temporal server `v1.32.1`; Python SDK `1.35.0` | [Server MIT](https://github.com/temporalio/temporal/blob/v1.32.1/LICENSE), [SDK MIT](https://github.com/temporalio/sdk-python/blob/1.35.0/LICENSE) | SDK [Windows CI](https://github.com/temporalio/sdk-python/blob/1.35.0/.github/workflows/ci.yml) is useful evidence, not proof of Buddha integration or a native server deployment |
| LangGraph `1.2.18` | [MIT core](https://github.com/langchain-ai/langgraph/blob/1.2.18/LICENSE) | Managed service terms are separate; tagged [default execution settings](https://github.com/langchain-ai/langgraph/blob/1.2.18/libs/langgraph/langgraph/pregel/main.py) were inspected |
| Restate server `v1.8.1`; Python SDK `v1.1.0` | [BSL server](https://github.com/restatedev/restate/blob/v1.8.1/LICENSE), [MIT SDK](https://github.com/restatedev/sdk-python/blob/v1.1.0/LICENSE) | Server terms require an explicit decision; [Docker deployment](https://docs.restate.dev/server/deploy/docker) does not establish native Windows support |
| Harness² `1cfe254e8d25b15f37048c3730134686abe60335` | [Apache-2.0 project](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/LICENSE) | README identifies separately licensed third-party material |

The capability comparison is a targeted engineering review, not an exhaustive
survey, security audit or performance study. No reviewed contract established a
drop-in replacement for the combination of Buddha's financial holds, complete
source-byte binding, official benchmark integration and inherited source
evolution. That is a bounded finding about these interfaces, not a claim that
other platforms cannot be extended to provide it. The practical opportunity is
to replace generic orchestration selectively while keeping the experiment's
specialized contracts small and authoritative.

## November 2 local / November 3 UTC 2026: Inspect observability reconsideration

The user asked us to seriously consider Inspect AI if observability is the
responsibility being solved. The earlier parked decision remains the historical
recovery decision. Reopen this separate reuse question: can Inspect replace
`buddha.progress.Progress`'s custom display/poll loop and the launcher's duplicate
`launch_common._heartbeat` status polling? **Research only; no adoption yet.**

Inspect supplies structured evaluation/sample logs, a live viewer, errors,
metadata and model usage. Its runtime tracer records action entry/exit and can
identify unfinished, cancelled, errored or timed-out actions. These are concrete
replacements to assess before writing another progress display or polling layer.
[Viewer](https://inspect.aisi.org.uk/log-viewer.html),
[log API](https://inspect.aisi.org.uk/eval-logs.html),
[tracing](https://inspect.aisi.org.uk/tracing.html).

A custom `Task`/`Solver` can call an existing scaffold, and a custom scorer can
expose existing results. A later custom `ModelAPI` is available if required;
using it would require verifying literal request conversion and retry behavior.
The first slice should keep Gateway, its ledger/uncertain holds, executor and
frozen official NoveltyBench 1.1 evaluator authoritative and unchanged.
[Solvers](https://inspect.aisi.org.uk/solvers.html),
[scorers](https://inspect.aisi.org.uk/custom-scorers.html),
[model adapters](https://inspect.aisi.org.uk/extensions-model-api.html).

Observability and full-history reconstruction are separate responsibilities.
Wrapping the study in a solver still calls its existing `_restore` and integrity
checks; no measured evidence says a viewer makes those checks cheaper. Inspect
checkpoints could support a later state-management redesign, but that is not
adopted here. The current v13 construction/reader, source and limits remain fixed;
this reconsideration adds no runtime gate or automatic migration.

Inspect Evals already implements NoveltyBench, but its stock task is incompatible
with our frozen comparison without adaptation: defaults include ten independent
generations, shuffled input and a small Skywork reward model; partitioning uses
DeBERTa. Reuse our exact native scorer and grouping/utility/request contracts,
not the stock task's scoring or generation defaults. Its implementation also
uses a separate dependency environment.
[Task source](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/src/inspect_evals/novelty_bench/novelty_bench.py),
[scoring source](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/src/inspect_evals/novelty_bench/score.py),
[partition source](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/src/inspect_evals/novelty_bench/partition.py).

Completed samples can be reused on retry, but stable IDs and explicit partials
are required. Sample retries default off; eval-set adds retry machinery, while
model-request retries are documented as unlimited by default. Disable Inspect-owned automatic
retries in the first slice and preserve Buddha's paid-effect/retry decisions.
Inspect cost limits use usage and model prices; they do not establish our
pre-dispatch reservations, shared grants or uncertain-charge hold contract.
[Recovery/retry](https://inspect.aisi.org.uk/handling-errors.html),
[CLI defaults](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/_cli/eval.py),
[cost limits](https://inspect.aisi.org.uk/setting-limits.html#cost-limit).

Checkpointing needs cooperative `checkpointer`/`track`/`tick` integration. It
captures declared agent state, events/store and selected sandbox files, not
arbitrary memory, running tools or external effects. Long calls delay checkpoints;
checkpoint failures continue by default unless strict mode is selected. No
checkpoint/resume policy or retention default is adopted by this proposal.
[Checkpoint contract](https://inspect.aisi.org.uk/checkpointing.html).

Logs contain prompts/messages/outputs. Disabling general raw model API logging
still retains error requests/responses, so flags alone do not establish privacy.
Use only synthetic inputs initially; require explicit safe-event/redaction and
source/receipt hash bindings before enabling real records. Inspect's security
policy treats task/solver Python as executable code and Docker as limited
isolation; retain our executor, sealed-input boundaries and immutable evidence.
[Logging controls](https://inspect.aisi.org.uk/eval-logs.html#model-api-logging),
[recording filters](https://inspect.aisi.org.uk/extensions-model-api.html#filtering-model-call-data),
[security policy](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/SECURITY.md).

**Recommended next slice, separately source-bound and time-boxed:** one offline synthetic
compatibility cohort under a declared parent timeout, with no automatic retry or
extension. One existing stage should expose success and typed failure through a
no-model Inspect task, safe stage events, stable sample IDs and source/receipt
hashes. Demonstrate live progress, an unfinished-action diagnosis, explicit
partial/error display and unchanged underlying results/accounting/requests.

Adopt only if that bounded result supports deleting the named custom display and
duplicate heartbeat/polling responsibility on the integrated path; do not add a
second coordinator or keep two polling systems. Preserve passive evidence and
financial guards. If it cannot remove that responsibility, park it with the
specific failed boundary recorded. Checkpointing and wider scheduling remain
separate decisions. No live-readiness, performance or scientific claim follows.

Before enabling the trial, pin an Inspect release and resolve/audit its runtime
and test dependencies in isolation, including license compatibility. Core Inspect
is MIT; that does not clear transitive packages, benchmark weights or datasets.
[Core license](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/LICENSE).
Living official sources above were checked November 3 UTC. This reconsideration
installs nothing and executes no evaluation, container, model or original record.

## November 4 follow-up: why normal execution keeps rebuilding history

The current runner calls `_restore`, checks the controls, executes one action,
and then repeats from `_restore` ([actual frozen-source loop](https://github.com/wavemanco/buddha/blob/eacf8b8bf8710134348f9cd5d892dac1ae1e383c/buddha/improver_study.py#L2601-L2606)).
Reconstruction creates a fresh evidence reader and walks the declaration, owners,
funding, screens, witnesses and prior decisions to infer the next action. The
action does not return an updated live scheduler state. We reused recovery-style
reconstruction as the ordinary scheduler. That was our implementation choice,
not a NoveltyBench requirement. With growing history, repeated complete walks
can accumulate approximately quadratic work; this describes the structure, not
a measured speedup or a complete runtime profile.

The motivation was consistency after interruption and detecting changed records.
The cost is that a healthy process repeatedly rediscovers work it just completed.
The read-only capture also records tree and receipt digests: legitimate new output
and ledger writes make that old snapshot stale. Deleting `_restore` or keeping
that reader alive would therefore be incorrect.

The useful boundary is between a forward runner, which performs the current step
and records its outcome, and a historical reader, which reconstructs and validates
saved work for inspection or recovery. Both are code; the saved history is data.
They can share formats and validators without making every live action replay the
whole experiment. Merely moving functions to another file does not change that
execution dependency.

Established systems demonstrate this distinction. Temporal retains workflow state
in a worker and routes later tasks back to it; eviction or failure requires replay.
[Primary sticky-execution documentation](https://docs.temporal.io/sticky-execution).
DBOS checkpoints step outputs and, during recovery, uses saved outputs for completed
steps. Unfinished external effects still require idempotency or uncertainty handling.
[Primary architecture documentation](https://docs.dbos.dev/architecture#how-workflow-recovery-works).
These are design examples, not evidence that either integration fits Buddha. Our
[earlier DBOS wrapper probe](conformance/reliability-reuse-decision.json) removed
zero production code and left the internal reconstruction unchanged. Another
wrapper would leave this root problem in place.

The user's current decision is to continue Buddha and defer exact DGM adoption.
The next design should reuse existing forward generation/evaluation/improvement
steps and separate historical reconstruction, with current-input validation,
transactional spending limits, unknown-charge stops, isolation and official scoring
retained. No new platform, broad state-machine rewrite or performance benefit is
established here. The [living plan](PLAN.md) owns the next bounded slice and the
unchanged scientific comparison; the [history observation](conformance/current-history-observation.json)
records the consumed three-hour construction partial.

## November 14 follow-up: OpenResearch as an experiment host

Source review of alphaXiv OpenResearch [v0.2.27](https://github.com/alphaXiv/OpenResearch/releases/tag/v0.2.27),
commit `9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3`, under the
[MIT license](https://github.com/alphaXiv/OpenResearch/blob/9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3/LICENSE).
The operator reported that the V5 resume reached startup checking. This review
used upstream documentation and source. It made no changes to V5 and exercised
neither the released Windows binary nor subscription authentication.

**Best place to try it.** OpenResearch can give a future Buddha run a named
experiment with a committed source archive, a recorded launch command, a
run status, and retained logs and artifacts. This could replace manual
PowerShell output collection and the separate experiment log view.
Inspect's proven role is narrower, inside an evaluation, where its logs and
retry can identify completed samples. If OpenResearch takes over the host
dashboard, keep one progress display for the operator and use Inspect for
sample evidence where it removes work.
[Experiment workflow](https://openresearch.sh/docs/experiments),
[source archive](https://github.com/alphaXiv/OpenResearch/blob/9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3/src/compute.rs#L33-L120),
[Buddha's Inspect proof](INSPECT-OBSERVABILITY-PROOF.md).

**Recovery on Windows.** The local backend uses Git Bash, captures stdout and
stderr and records the exit code. Its Windows Job Object lets it manage the
launched processes. After the supervisor restarts, it can reconcile a surviving
process or read a saved exit code. If Buddha itself exits after a provider
request, safe continuation still depends on Buddha's saved results, operation
IDs and accounting. OpenResearch displays stages and causes that the process
emits. Buddha still needs to supply the exact stage and reason, and its history
reader still does its own verification. The Git archive covers committed
source. Python, installed dependencies, Docker images, official evaluator
assets, task IDs and saved state still need the existing run bindings.
[Windows launch](https://github.com/alphaXiv/OpenResearch/blob/9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3/src/engine/adapters/local.rs#L294-L341),
[process ownership](https://github.com/alphaXiv/OpenResearch/blob/9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3/src/jobs/localbox/windows.rs#L33-L61),
[restart reconciliation](https://github.com/alphaXiv/OpenResearch/blob/9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3/src/engine/submit.rs#L147-L247).

The Windows experiment runner is beta and its stdin pipe opens the launch gate.
The existing interactive PowerShell key prompt therefore needs a different
launch path. The local backend also rejects the platform's experiment timeout
flag. A paid host change would need a verified credential path and existing
Buddha deadlines. Keep credentials out of run commands, archived files and
logs. A worktree alone gives source isolation. Keep sealed task inputs and
keys outside any delegated agent's accessible data. For a local fixture pilot,
use local compute and turn off optional telemetry.
[Windows requirements](https://openresearch.sh/docs/install),
[local timeout handling](https://github.com/alphaXiv/OpenResearch/blob/9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3/src/compute.rs#L652-L664),
[telemetry settings](https://openresearch.sh/docs/install).

**Bring Your Own Subscription.** OpenResearch starts an installed coding
agent using its configured subscription or API authentication. Its delegation
tool accepts a versioned model, a specific route and an effort value from that
route's catalog. Pin all three for an experiment. Omitting the route allows
OpenResearch to choose its preferred one. Verify the actual login and available
efforts on the target machine before use. For example, Claude Code can use an
API credential from the environment. Record the selected route, requested and reported model IDs, effort, agent
version and observed billing mode. The catalog can group aliases and a native
agent can report an in-session model change. A verified
subscription route can avoid separately billed Buddha API requests for that
role while consuming provider plan capacity or usage credits if enabled.
Managed compute has its own billing. [Agent authentication](https://openresearch.sh/docs/agents),
[delegation tool](https://github.com/alphaXiv/OpenResearch/blob/9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3/src/commands/up/agent_tools.rs#L85-L106),
[route selection](https://github.com/alphaXiv/OpenResearch/blob/9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3/src/local/model_routes.rs#L619-L647),
[reported Codex routes](https://github.com/alphaXiv/OpenResearch/blob/9a2949cfe2b7e9336169fcf6ab0c1ba6d4bc24a3/src/local/harness/codex.rs#L85-L155),
[Codex plan usage](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan),
[Claude plan usage](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan),
[compute billing](https://openresearch.sh/docs/billing).

The first model role to consider is native review. The frozen protocol already
specifies fresh Codex reviewers separately from paid scoring. A later
subscription-backed proposal author or candidate generator would be a new
experimental condition. A coding agent can add instructions, tools and history
to a request. If testing it for answer generation, use a matched control and
verify the output allowance and reproducibility before making a leaderboard
claim. Direct delegation is an agent tool in this release. A supported batch
interface for calls from Buddha's Python runner has not been verified.
Official NoveltyBench 1.1 currently uses the pinned OpenAI Luna
partition request and Anthropic Opus utility request. The coding-agent routes
have no demonstrated equivalence to those requests. Keep the official
evaluator and budget ledger in charge of official scoring. V5 continues under
its existing protocol.
[Buddha's frozen settings](D8-LIVE-COMPARISON.md#model-requests-checked-against-current-official-code),
[official scoring workflow](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/README.md#basic-workflow),
[submission rules](https://novelty-bench.github.io/submit.html).

**Smallest useful check.** Run the existing offline Buddha demo in a disposable
Windows OpenResearch experiment with providers blocked. Check that the run
shows the exact source and command, preserves the saved report and the original
12 simulated operations on reuse, and shows the structured error and failed
exit code from a deliberately invalid inspection. Require that the experiment
view directly replaces manual log collection. This establishes host visibility
on a real Buddha command. Claim reattachment or cancellation only after
observing it with a disposable process, and study resume only after testing
interruption with identical completed work and accounting. No V5 input,
subscription login, real container or paid request is needed for the first
check. Both existing Buddha CLI checks passed locally in 0.291 seconds with
socket connections blocked. This verifies the fixture before any OpenResearch
run. [Existing offline CLI checks](../tests/test_cli.py#L489).
