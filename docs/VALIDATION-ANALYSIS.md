# Comparing saved validation measurements

The [validation controller](VALIDATION-STUDY.md) collects measurements for frozen agents. This analysis component uses those saved measurements to ask whether the evidence clears the experiment's declared improvement rule. It leaves the official evaluator, scores and summaries unchanged.

The result concerns the expected native scores on the **exact fixed prompt panel**, under the declared generation and judging procedure. It does not establish improvement on unseen prompts, human creativity or future model versions. Final evaluation, independently authored transfer tasks and human assessment remain separate requirements in [PLAN.md](PLAN.md).

## What the analysis reads

`analyze_validation_occasion(...)` takes the study directory, round number, original authorization path and the exact hash of a saved complete result. It verifies the original controls, generation, native artifacts, owners and coverage before using scores. It accepts no replacement scores, confidence bounds, plan or completeness flag from the caller.

This is a read-only library operation: it needs no API key and creates no financial owner, worker, request or saved result. Repeating it uses the same evidence. An interrupted round with no complete result must be recovered through its original controller; this API does not manufacture a result for it.

The full ordered table contains every candidate and comparison agent, prompt and repetition. If a required score is missing or unusable, the affected comparison remains inconclusive. A high score in the remaining rows cannot hide the missing one. Unsupported metric projections remain unavailable.

## Choices must already be in the original plan

The controller copies and binds an analysis-plan file before generation. To use this method, those original bytes must contain its complete typed contract and implementation hashes. The reader checks what was committed then; it cannot attach a more favorable method afterward. An older opaque plan receives an explicit unsupported-plan result.

`ValidationAnalysisPlan` supplies a pure configuration parser. Its inputs fix the method, exact reference release, metric projection, task weighting, repeated-set aggregation, family blocks, assumptions, maximum rounds/candidates/comparators, repetitions, final count, error allocation, numerical improvement rule and analyzer code identities. No scientific numbers are supplied by default.

The plan allocates its allowed error across both metrics and all maximum comparison slots, including slots later unused or unsuccessful. Final and validation portions are separate. Money left over does not buy another look; unused comparisons do not release error allowance for a later favorable test. A final count in this allocation does not freeze actual finalists or complete the final-evaluation controller.

## What counts as an observation

Ten answers to one prompt are one complete answer set. They are related through the task, generation procedure and official grouping. Repeated sets are first averaged within the prompt. Prompts in the same declared family stay together in a block. The method allows dependence within that block, including between agents, metrics and repetitions.

For example, if two of three equally weighted prompts belong to one family, its weight is two thirds; the other family's weight is one third. Those weights determine the conservative uncertainty calculation. Calling each answer or repetition an independent sample would give unjustified extra confidence.

Different blocks must be independent conditional on the experiment's earlier history and frozen settings. That is an explicit assumption, not something the harness proves from family labels or separate API calls. Correlated provider behavior can violate it. Family metadata also does not certify the absence of semantic overlap. A defensible broader block can be declared prospectively when needed; changing blocks after seeing results changes the experiment.

## The conservative lower bound

The first method uses Hoeffding's bound for independent bounded variables, allowing different block distributions. It does not assume that the fixed prompts were randomly sampled from a larger prompt population. Its application here targets the conditional expected difference in native scores on this panel. [Hoeffding's original theorem](https://doi.org/10.1080/01621459.1963.10500830).

The existing metric adapter supplies the supported score ranges. For the official ten-answer protocol these are utility from 0 to 10 and distinctiveness from 1 to 10. The statistical calculation uses those bounds; it does not redefine the benchmark. Synthetic engineering fixtures with another declared answer count remain synthetic fixtures.

Let `d` be the observed equal-prompt difference, `s` the supported score span, `w_f` each family's prompt weight and `alpha` the prospectively allocated tail probability for this metric and comparison. The lower bound is:

```text
radius = sqrt(2 * log(1/alpha) * s² * sum(w_f²))
lower bound = max(-s, d - radius)
```

All repeated sets remain inside their family block; this first method takes no extra concentration benefit from repeated generations. The bound can therefore be very wide or reach the known lower support. That is a valid but uninformative result. It does not prove that the agent failed to improve, and it is not a reason to switch methods after seeing the scores.

The fixed allocation uses the union bound across planned comparisons; comparisons may share the same comparator measurements. Its validity still depends on the stated boundedness and conditional block assumptions. Observing valid rows does not prove those assumptions or justify an unconditional average of successful runs. [Holm's original discussion of familywise error and Bonferroni protection](https://doi.org/10.2307/4615733).

## Arithmetic and the decision

The implementation aggregates saved finite scores and weights as exact fractions. It uses isolated directed Decimal calculations and exact postchecks to round the uncertainty radius upward and the exported lower bound downward. Ordinary rounding must never move an insufficient bound across the declared gain margin. Unsupported arithmetic yields explicit unavailable uncertainty. The numerical contract relies on the documented Python arithmetic semantics. [Python Decimal documentation](https://docs.python.org/3.13/library/decimal.html).

The unchanged [improvement rule](EVALUATION-RULE.md) checks the prospectively fixed primary metric: its lower bound must strictly exceed the minimum gain, while the other metric's bound must meet the inclusive permitted-loss threshold. The analyzer reports every candidate against every fixed comparator and retains both metrics.

Rule satisfaction is a conditional numerical comparison. It does not promote a champion, authorize more spending, certify independent model behavior or complete scientific validation. A result that does not satisfy the rule does not disprove improvement.

## Offline engineering check

From the checkout containing this slice:

```powershell
python -m unittest discover -s tests -p test_validation_analysis.py -v
```

This runs the focused tests once and exits. It uses synthetic temporary data and simulated worker/API replies, spends no API money and needs no keys, Docker worker or separate window. Press Ctrl+C to stop. Passing it checks the implementation; it does not establish an actual agent improvement.
