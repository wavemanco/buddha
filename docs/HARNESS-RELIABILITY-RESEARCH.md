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

## How this should affect our ongoing work

The following is a recommendation for the existing IMP-01 reliability work and
the optional reuse item [ENG-INFRA-01](BACKLOG.md#eng-infra-01-evaluate-existing-reliability-infrastructure).
It does not add scientific completion gates or supersede PLAN.md.

1. **Finish the narrow stopped-run repair under its original contract.** Keep
   saved replies, charges, holds, source identities and official settings.
   Adopting another runner during recovery would introduce another compatibility
   problem before the current one is resolved.
2. **Use established lifecycle patterns in separately versioned repairs.** Retain
   the primary typed failure even when cleanup fails; record intended runtime
   identity before launch; classify agent/provider/executor failures separately;
   expose completed-step progress rather than only a periodically printed clock.
   These are prospective recommendations, not claims that all are implemented.
3. **Run one small offline reuse comparison when PLAN schedules it.** Compare the
   existing stage runner with a DBOS wrapper using supplied replies, and inspect
   one result/export boundary with Inspect. Store only small immutable references
   in workflow state. Measure changed code, recovery work, elapsed time and
   operational burden. Stop if the wrapper merely duplicates our controller.
4. **Choose from evidence.** Adopt a component only if it removes maintenance
   while preserving the contracts below. Consider Temporal later if multiple
   machines or worker-version management become a concrete need. Do not deploy
   all the shortlisted platforms.

The offline comparison should inject failures before sending, after simulated
provider acceptance but before local receipt, after receipt persistence, during
checkpoint writes, at executor startup/cleanup and across software changes.
Require exact replay of completed replies, no second simulated send for a saved
operation, retained uncertainty for ambiguous calls, denial of an incompatible
source, unchanged official evaluator artifacts and explicit partial-result
reasons. Check Windows and Linux separately and confirm original files remain
unchanged. These acceptance checks test compatibility; they do not establish
that Buddha improves creativity or that a provider offers exactly-once billing.

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
