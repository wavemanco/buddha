# Buddha: research evidence and design implications

Research checked on October 18, 2026. This handoff examines the requested Darwin Gödel Machine (DGM), open-endedness resources, and HyperAgents, then bounds follow-on investigation to six applicable methods or comparators. It is not an exhaustive literature survey. Only primary papers, author repositories, and repository license files support the findings. Public claims are distinguished from inspected implementation behavior and proposed design choices. No paid experiment, benchmark run, or leaderboard submission was performed for this research.

## 1. Evidence conventions and scope

**Observed source** means a fact read in the identified repository revision. **Paper report** means an experimental result or interpretation reported by its authors; it has not been independently reproduced here. **Design inference** means a recommendation for Buddha, informed by the evidence but not established by it. A repository license observation records the license text at the pinned revision, without asserting that every dependency or dataset shares that license.

DGM was cloned to a unique temporary directory for read-only inspection. The outer driver, self-improvement procedure, admission helper, diagnosis prompt assembly, container creation, and coding-evaluation path were inspected. This was a targeted execution-path study, not a line-by-line audit of the repository. Other projects received paper/repository/license inspection at the level stated below. HyperAgents received paper, README, and license inspection only: its implementation was not downloaded, copied, translated, vendored, or used as a code template.

## 2. Reproducible source and license register

The hashes below identify live default-branch revisions observed during this research. They are source references, not dependencies approved for installation.

| Project | Pinned repository revision | License observation | Intended use |
| --- | --- | --- | --- |
| [DGM](https://github.com/jennyzzt/dgm/tree/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2) | `a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2` | [Apache-2.0](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/LICENSE) | Algorithm and source-path reference |
| [Awesome Open-Ended](https://github.com/jennyzzt/awesome-open-ended/tree/966c9ec7ed031eebdffe5a466f8cf4a1f198532d) | `966c9ec7ed031eebdffe5a466f8cf4a1f198532d` | Not independently verified | Literature discovery index |
| [HyperAgents](https://github.com/facebookresearch/HyperAgents/tree/59a68f672dfb92c74aeb7e61535d776fb36e172d) | `59a68f672dfb92c74aeb7e61535d776fb36e172d` | [CC BY-NC-SA 4.0](https://github.com/facebookresearch/HyperAgents/blob/59a68f672dfb92c74aeb7e61535d776fb36e172d/LICENSE.md) | Conceptual inspiration only |
| [HGM](https://github.com/metauto-ai/HGM/tree/013872d95da978483f5b540e531db063d23890da) | `013872d95da978483f5b540e531db063d23890da` | [Apache-2.0](https://github.com/metauto-ai/HGM/blob/013872d95da978483f5b540e531db063d23890da/LICENSE) | Search-policy reference |
| [GEPA](https://github.com/gepa-ai/gepa/tree/f1cfdee2856e9dc4b5b4dc5cc2e391d0aa20d819) | `f1cfdee2856e9dc4b5b4dc5cc2e391d0aa20d819` | [MIT](https://github.com/gepa-ai/gepa/blob/f1cfdee2856e9dc4b5b4dc5cc2e391d0aa20d819/LICENSE) | Prompt/text-policy comparator |
| [CORAL](https://github.com/Human-Agent-Society/CORAL/tree/0123dfb939b35228cf2c1fde224cd0561e727408) | `0123dfb939b35228cf2c1fde224cd0561e727408` | [Apache-2.0](https://github.com/Human-Agent-Society/CORAL/blob/0123dfb939b35228cf2c1fde224cd0561e727408/LICENSE) | Operational design reference |
| [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve/tree/a1e9d91eecde612f0efc8e8e31f59b36998248c0) | `a1e9d91eecde612f0efc8e8e31f59b36998248c0` | [Apache-2.0](https://github.com/algorithmicsuperintelligence/openevolve/blob/a1e9d91eecde612f0efc8e8e31f59b36998248c0/LICENSE) | Optional program-search comparator |

No author-linked Red Queen Gödel Machine implementation/license was established in this bounded search. Independent implementations found through search must not be described as the authors' official release. Paper licenses and repository licenses are separate; a permissive repository label does not license unrelated figures, datasets, or proprietary service outputs.

## 3. DGM: what transfers and what does not

### Paper report

The requested [DGM v3 paper](https://arxiv.org/html/2505.22954v3), dated March 12, 2026, evolves Python coding-agent scaffolds around frozen foundation models. It reports SWE-bench improvement from 20% to 50% and Polyglot improvement from 14.2% to 30.7%. Archive maintenance and parent selection remain fixed. The connection between downstream coding performance and future self-modification ability is an assumption, not a general theorem. The paper estimates approximately USD 22,000 for its SWE-bench run. It does not demonstrate weight training, indefinite improvement, or computational creativity. These results support testing an archive-based optimization loop; they do not establish that replacing its benchmark produces a successful creativity agent.

### Observed source: execution path

[`DGM_outer.py`](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/DGM_outer.py) initializes the archive, reads performance, chooses parents and diagnosis targets, launches modifications, filters eligible children, and appends archive state. Default parent weight is proportional to `sigmoid(10 × (accuracy − 0.5)) / (1 + archived_child_count)`. Default retention keeps all eligible variants. Underexplored ancestry is rewarded; explicit semantic novelty is not measured. Static inspection also finds an omitted comma concatenating two CLI choices and an ascending sort in the `best` branch. A timeout applied to futures after `as_completed` yields them does not impose an overall worker deadline. These are source observations, not executed reproductions.

[`self_improve_step.py`](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/self_improve_step.py) reconstructs ancestor patches inside Docker, obtains a diagnosis, and runs the inherited coding agent against its own repository. It retrieves a generated patch, destroys the modification container, and evaluates the resulting agent. Diagnosis uses a separately configured `o1-2024-12-17` model. Thus, the implementation contains a fixed diagnosis mechanism as well as an inherited editing agent; it is not an unconstrained program independently redesigning every component of its improvement process.

[`utils/evo_utils.py`](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/utils/evo_utils.py) implements the admission helper named `is_compiled_self_improve`. The inspected checks require performance fields, at least one nonempty downstream patch, and a minimum submitted-task count. The name should not be mistaken for an independent compiler test or proof that the child preserves effective self-improvement. Buddha needs explicit capability and integrity checks appropriate to its own candidate interface.

[`prompts/self_improvement_prompt.py`](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/prompts/self_improvement_prompt.py#L305) assembles evaluation logs and agent code for diagnosis. Its SWE path includes the dataset reference patch and test patch. Selected orchestration utilities are omitted from the presented code. This is training/optimization feedback, not untouched final-test evidence. Prompt-level omission also does not enforce a filesystem mutation boundary.

[`utils/docker_utils.py`](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/utils/docker_utils.py#L104) creates the modification container without explicit resource limits, network prohibition, or non-root settings in that call. The improvement procedure passes raw provider credentials into the agent process. [`swe_bench/harness.py`](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/swe_bench/harness.py) separately constructs benchmark environments and applies inherited patches. These separations are useful, but Docker alone is not a sufficient permission, spend, or evaluator-integrity contract.

### Design inference

Preserve DGM's cumulative genealogy and viable stepping stones. Replace coding-specific task assumptions, admission, and fitness with an explicit creativity protocol. Reimplement a small driver with validated configuration rather than porting the prototype wholesale. Keep scoring, data splits, resource accounting, and the promotion rule outside the editable surface. A better creative answer does not, by itself, make an agent a better author of future improvements.

## 4. Applicable successors and comparators

### HyperAgents: separate task skill from improvement skill

**Paper report:** [HyperAgents](https://arxiv.org/html/2603.19461) combines task and meta-agent implementations in an editable program. The meta-agent can revise how future variants are produced, allowing self-modification beyond domains where task performance directly implies coding skill. The paper introduces improvement@k: measure the gain produced by an improver over a bounded number of generated variants, selecting the final variant through validation.

**Design inference:** Distinguish Buddha's response generator from its mutation proposer and evaluate both. An improvement@k experiment requires the same starting policy, tasks, evidence, and budget when comparing improvers. Respect the user's restriction: conceptual inspiration is authorized; HyperAgents implementation reuse is excluded.

### HGM: reward productive lineages

**Paper report:** The [Huxley–Gödel Machine](https://arxiv.org/html/2510.21614v3) identifies a mismatch between immediate task performance and future improvement potential. Its clade metaproductivity aggregates descendant outcomes; Thompson sampling guides search, and expansion is decoupled from additional evaluation. Its theoretical correspondence to a Gödel machine relies on assumptions and a true productivity oracle. The practical estimator is not a guarantee of optimal recursive improvement.

**Design inference:** Record descendant productivity before implementing a sophisticated selector. Expensive judging makes adaptive reevaluation attractive, but continuous, correlated creativity scores need an appropriate statistical treatment. Do not directly transplant a binary-success posterior and describe its intervals as calibrated for NoveltyBench.

### GEPA: a lower-complexity optimization baseline

**Paper report:** [GEPA v2](https://arxiv.org/abs/2507.19457v2), accepted as an ICLR 2026 oral, uses execution trajectories, natural-language reflection, and Pareto-based selection to evolve prompts. Its reported efficiency comparisons concern the evaluated tasks and models. They do not establish creativity performance.

**Observed repository:** The current MIT repository describes a more general optimizer for textual parameters, including prompts, code, and configurations.

**Design inference:** Begin with declarative generation policies and compare against reflective prompt evolution. Label gains accurately: a stronger task prompt is prompt optimization; an improved mechanism for producing useful descendants is a separate, stronger claim. Avoid adding a dependency until the required interface and evaluation budget are known.

### CORAL: durable discovery operations

**Paper report:** [CORAL v3](https://arxiv.org/html/2604.01658v3), dated September 2, 2026, studies asynchronous agents, shared persistent memory, isolated workspaces, interventions, and evaluator separation on mathematical, algorithmic, and systems tasks. It reports discovery gains against its baselines. Those gains have not been established for creative text generation.

**Design inference:** Retain negative results and reusable search lessons across lineages. Separate untrusted candidate execution from evaluation. Long-running agent sessions and multi-agent coordination are possible later experiments, not requirements for an initial bounded loop. Their costs must count when comparing search efficiency.

### Red Queen Gödel Machine: adapt internal critics carefully

**Paper report:** The [Red Queen Gödel Machine v3](https://arxiv.org/html/2606.26294v3), dated October 8, 2026, co-evolves evaluators using fixed ground-truth anchors. Evaluators remain frozen within epochs. Replacement at an epoch boundary erases utility records dependent on the displaced evaluator. This addresses changing search criteria; it does not provide global validity under arbitrary judge changes.

**Design inference:** An adaptive internal creativity critic could be studied later. The official NoveltyBench evaluator must remain unchanged for an official-comparable score. If an internal judge changes, version its outputs and recompute or invalidate affected search comparisons. A critic trained on its own preferences supplies no independent evidence of usefulness.

### AlphaEvolve and OpenEvolve: program evolution comparators

**Paper report:** [AlphaEvolve](https://arxiv.org/abs/2506.13131) studies LLM-guided program evolution for externally scored scientific and algorithmic problems.

**Observed repository:** OpenEvolve is a community implementation with an Apache-2.0 license. It is not DeepMind's released implementation. Its internal execution path was not audited in this research.

**Design inference:** Program archives and staged evaluation are relevant comparison ideas. However, execution correctness and numerical performance offer stronger external verification than a subjective creativity judge. Treat that difference as a design constraint, not a reason to assume comparable results.

## 5. Open-endedness resources and counterevidence

The requested [Awesome Open-Ended index](https://github.com/jennyzzt/awesome-open-ended/tree/966c9ec7ed031eebdffe5a466f8cf4a1f198532d) links quality-diversity, intrinsic-motivation, environment-generation, and self-improvement research. It includes Quality-Diversity through AI Feedback, OMNI-EPIC, DGM, HyperAgents, and CORAL. It is useful for discovery, not a substitute for evaluating the linked primary works. This handoff does not claim that every listed resource was studied.

**Relevant foundations:** [MAP-Elites](https://arxiv.org/abs/1504.04909) retains high-performing solutions across user-defined behavioral dimensions. Its relevance is preserving alternative useful behaviors; arbitrary text-style bins are not automatically valid behavioral dimensions. [QDAIF](https://arxiv.org/abs/2310.13032v4), published at ICLR 2024, uses language models for variation and quality/diversity feedback in creative writing. It is a closer task-domain precedent than coding-only evolution. It evolves an archive of texts, rather than demonstrating that an agent improves its own improvement procedure. These support the archive experiment, not an assumption of novelty or success for Buddha.

[Hughes et al.](https://arxiv.org/abs/2406.04268) offer an observer-relative novelty-and-learnability definition of open-endedness in a position paper. Ten distinct outputs under a finite metric do not demonstrate that property over an indefinite sequence. [OMNI-EPIC v3](https://arxiv.org/abs/2405.15568v3) generates coded tasks and rewards guided by interestingness and learnability. That suggests a later, separate development-curriculum experiment; changing official benchmark tasks or judges would change the measurement and cannot be called an official NoveltyBench score.

**Measurement foundations:** [adaptive-data-analysis research](https://arxiv.org/abs/1411.2664) explains why repeated reuse of observed validation data undermines ordinary statistical interpretation. [Reward-model overoptimization experiments](https://proceedings.mlr.press/v202/gao23h.html) demonstrate divergence between a proxy reward and a stronger synthetic reward under optimization. Neither establishes the amount of bias for NoveltyBench, but both motivate sealed evaluation and independent audits rather than trusting only the optimization judge.

**Paper report:** The October 10, 2026 preprint [Does Failure Feedback Direct Agent Self-Modification?](https://arxiv.org/html/2610.14662) finds no detectable target-specific repair advantage across 145 eligible public DGM modifications. Controlled experiments identify benefits in some repairable mechanisms, but repairing a target does not reliably imply held-out improvement. This is fresh, single-study counterevidence, not a definitive refutation of DGM's aggregate search gains.

**Design inference:** Record targeted repair, transfer to related categories, and held-out net change separately. A rising best-of-archive curve can reflect selection among noisy candidates. It does not identify whether feedback directed the improvement or whether the improver itself improved. Include no-feedback or shuffled-feedback comparisons when making causal claims about reflection.

## 6. NoveltyBench evidence

The separate [NoveltyBench evidence and implementation contract](NOVELTYBENCH.md) records pinned official code, website, and dataset revisions; metric definitions; the v1.0/v1.1 distinction; observed CLI/documentation discrepancies; and Novamine's published artifacts and reproduction limits. It also records byte hashes, dataset-license uncertainty, relevant creativity methods, and concrete judgment counterexamples. No fresh model/judge run was performed. The [project design](DESIGN.md) turns those findings into the protected experiment boundary and acceptance gates.

## 7. Proposed research contract and design provenance

The following is **design inference for Buddha**, not a published or experimentally validated method. The project-specific contribution is a proposed composition and engineering contract. No claim of a new scientific algorithm, new benchmark result, or priority over unexamined literature is warranted.

Borrowed method families are explicit: DGM supplies archive/genealogy search; GEPA motivates reflective text-policy evolution; HGM motivates measuring descendant productivity; HyperAgents motivates distinguishing task and improvement capabilities; CORAL motivates durable memory and evaluator separation; RQGM motivates versioned internal critics. Combining these ideas is not evidence that the combination outperforms any source system.

The initial implementation should express an agent as a validated declarative policy: generation instructions, exploration operators, bounded sampling, and selection behavior. A fixed proposer produces child policies, while an immutable evaluator records utility and distinctiveness separately. Preserve viable Pareto candidates and genealogy rather than collapsing all outcomes immediately into an undocumented scalar. Code-authoring evolution should be a later explicit intervention with its own execution boundary and comparison.

Freeze the benchmark manifest, splits, official evaluator revision, models, prompts, decoding settings, budget, promotion decision, and final-test access rules before observation. Development prompts may inform mutations. Final-test prompts and outcomes must not enter mutation feedback. Repeated validation-based selection is adaptive optimization and must be reported as such. Preserve all attempts, including failed generations, invalid judge responses, timeouts, and rejected candidates; otherwise apparent progress can hide survivorship bias.

Separate three acceptance claims. **Engineering validity** establishes that accounting, provenance, isolation, interruption, and resume behavior work. **Task improvement** establishes held-out utility/distinctiveness gains over a fixed baseline under matched total cost. **Improver improvement** establishes that a revised proposer generates better descendants from the same initial policy under matched conditions. Passing one claim does not establish the others.

The first experiment should compare a fixed generator, prompt-policy evolution, and archive search using the same backbone and total budget. Include archive and feedback ablations before attributing gains to open-endedness or reflection. A leaderboard claim additionally requires the official generation/evaluation protocol, compatible access conditions, and a verified contemporary baseline. Local proxy scores are useful diagnostics, but must remain labeled as proxies.

The first slice should leave a reviewable design and runnable acceptance contract. It should stop before autonomous evolution, paid calls, unrestricted code execution, or any claim of competitive performance. Subsequent slices should implement only the approved boundary and collect evidence against the frozen claims.

## 8. Bounded cross-check after the current source regression

October 24, 2026. This user-requested follow-up checks selected primary-source
documentation and loop code, rather than reopening the design. No third-party
code was copied or executed; reported research gains were not independently
reproduced. [PLAN.md](PLAN.md) remains the scheduling authority.

**Observed DGM source:** At revision `a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2`,
the outer loop defaults to keeping evaluated children in its archive. The optional
`keep_better` rule compares against the original baseline minus a tolerance,
rather than the immediate parent. Selected parent patches are inherited before
the patched coding agent authors another change. Post-evaluation diagnosis is
optional. These mechanisms permit exploration without guaranteeing that each
child improves. [Outer loop](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/DGM_outer.py),
[self-improvement step](https://github.com/jennyzzt/dgm/blob/a565fd2d1dca504ef5104a7cc0f3bdc4ab9b4fd2/self_improve_step.py).

**Observed Harness2 source and paper:** The contrastive step executes a reference
and candidates on the same task under matched configurations, then examines
behavior and code differences. The authors explicitly distinguish this evidence
from verified correctness. Sequential recursion carries a composed harness
forward without a guaranteed score gain. Its persistent experience library is
a related mechanism, not evidence that Buddha needs another library now.
[Paper sections 2.2-2.3](https://arxiv.org/html/2610.14224v1#S2.SS2),
[recursion source at revision 1cfe254](https://github.com/google-research/harness2/blob/1cfe254e8d25b15f37048c3730134686abe60335/harness2/core/recursion.py).

**Inference for Buddha:** The cross-check supports the current exact-parent,
complete-output feedback connection, retained negative attempts and separation
between exploratory ancestry and measured best candidates. It supplies no reason
to change NoveltyBench scoring or restart the architecture. A reusable lessons
library or composition of multiple proposals can remain later experiments.
Neither substitutes for the existing matched improver comparison and independent
held-out evaluation. Full code-diff feedback could be assessed later if the
current source, original hypothesis and paired outputs prove insufficient;
it is not a requirement added by this spot-check.
