# Comparing improvement procedures

The numerical comparison is implemented. The [sealed assessment](IMPROVER-ASSESSMENT.md)
now connects it to original development and final records through the protected
executor. Bounded composed checks and [reader-cost observations](RECONSTRUCTION-COST.md)
pass; the actual controlled study remains IMP-01 work in [PLAN.md](PLAN.md).
The [original delivery](conformance/imp01-paired-analysis-delivery.json) retains
its historical checks and source version.

## What is being compared?

Both improvement procedures receive the same starting agent and development
feedback. Each gets the same declared opportunity budget. Development results
select a descendant separately for each procedure. A later sealed assessment
must measure those descendants and a fresh shared starter on the same tasks.

The analysis keeps three results separate, for both official metrics:

| Result | Calculation | Meaning |
| --- | --- | --- |
| Initial improver's gain | Initial descendant minus starter | Did its selected descendant outperform the starting agent? |
| Evolved improver's gain | Evolved descendant minus the same starter | Did its selected descendant outperform the starting agent? |
| Improver effect | Evolved descendant minus initial descendant | Which procedure produced the better selected descendant in this fixed comparison? |

For example, starter 5, initial descendant 4 and evolved descendant 4.5 give
gains of -1 and -0.5, and an improver effect of +0.5. The evolved procedure does
better than the initial one here, while both descendants do worse than the
starter. These are illustrative numbers, not observed results. The analysis
retains both gains so that distinction stays visible.

## Keeping the comparison fair

The plan fixes all starting conditions, repetitions, descendant opportunities,
tasks, weights, error allowances and the numerical improvement rule before
observation. The explicit ordered task list binds each typed ID, family and
answer count to the original task/custody identities. A task missing from every
arm therefore cannot quietly disappear from the analysis.

Each task receives equal weight. Within each task, the calculation averages
sealed repetitions and the planned starting conditions equally. It uses the
same saved starter measurement for both descendant gains. That starter cancels
from the direct evolved-minus-initial comparison.

Equal source code in two roles remains two roles with separate measurements.
The code can generate different answers on different occasions; the analysis
uses the actual supplied measurements rather than assuming zero difference.
Agent identity hashes and raw Python-file hashes are different fields and must
not be interchanged by the later experiment-record reader.

## Missing and failed outcomes

A procedure with no valid descendant retains an explicit empty selection slot.
It receives neither a zero score nor a replacement starter. Every executable
measurement needs an explicit observed or failed row. An absent row, duplicate,
foreign source or changed task identity is an input error.

An explicit failed row or undefined metric keeps the planned denominator and
makes the affected comparison unavailable. An unaffected comparison can still
be shown: missing starter measurements, for example, do not erase the directly
measured difference between two descendants. The overall improvement rule
nevertheless remains inconclusive unless the entire planned panel is complete,
with both metrics usable and no empty descendant slots. It never selects only
successful cases to obtain a favorable result.

## What the uncertainty calculation means

The supported method supplies six conservative lower bounds: three comparisons
times two metrics. Six positive error allowances must be explicitly supplied
and fit within the declared total. They are not chosen from the results.

The method treats related tasks as a family. Repeating generations or starting
conditions does not turn that family into additional independent families.
It uses the existing directed arithmetic and the adapter's declared metric
supports, rather than the observed score range. Wide or uninformative bounds
remain valid outcomes. These are lower bounds, not two-sided confidence
intervals or tests proving a regression.

The mathematical bound assumes independent bounded family blocks, conditional
on the fixed panel and selected descendants. Recorded family names do not prove
that assumption. It supports no claim about future searches, new starting
agents, unseen tasks or human judgments. The derivation follows
[Hoeffding's bounded-sum inequality](https://doi.org/10.1080/01621459.1963.10500830);
the [existing analysis guide](VALIDATION-ANALYSIS.md) explains the shared numerical
kernel and its limits.

The unchanged [numerical rule](EVALUATION-RULE.md) checks the declared primary
metric's minimum gain and the permitted loss on the other metric. It applies
to the improver effect. Non-satisfaction or an inconclusive result does not
prove that the improver has no effect. Target repair remains unassessed here.

## Check what the planned comparison can establish

IMP1-FEAS-01: choose the actual study only after checking its uncertainty
calculation. More API calls do not necessarily make its conclusion stronger.
The current method's uncertainty radius depends on task-family weights:
`span * sqrt(2 * sum(family_weight^2) * ln(1 / tail_allowance))`.
Repeating starting conditions or generations can change the average score, but
does not add independent families to this formula.

A [bounded numerical observation](conformance/imp01-prospective-feasibility.json)
calls the public analyzer on five wholly synthetic panels. For illustration
only, it allocates total error allowance 0.05 equally across six lower bounds,
uses ten answers per task and assumes equally weighted independent families.
The example rule requires a positive utility lower bound and no distinctiveness
loss. None of these choices is an adopted study protocol.

| Assumed families | Supplied utility difference | Utility uncertainty radius | Utility lower bound, rounded |
| --- | --- | --- | --- |
| 2 | +10 | 21.880338 | -10, clipped to support |
| 6 | +10 | 12.632619 | -2.632619 |
| 100 | +10 | 3.094347 | +6.905653 |
| 100 | +0.5 | 3.094347 | -2.594347 |

The six-family example cannot satisfy a positive utility bound even at the
largest possible utility difference. Repeating it across three starts, two
development repetitions and two sealed repetitions leaves its radius unchanged.
The idealized 100-family example can satisfy the rule at extreme differences
on both axes, but not at +0.5 on both. These are numerical feasibility findings,
not measured agent effects, a power estimate or proof of no improvement.

The current bundle contains 100 curated tasks, not the whole benchmark. Its
split declares 72 uneven families, whose squared weights sum to `97/5000`.
It is not the idealized 100-family panel above; an actual sealed subset needs
its own weights. Family labels alone do not establish independence.

Before funding IMP-01, freeze an adequate actual population, justified
assumptions, practical margins, error allowances and complete grid, then check
what that exact design could establish. If another uncertainty method is
needed, review and adopt it prospectively as a separate harness change. Do not
relax the rule after seeing results. Official NoveltyBench scoring is unchanged.

## Library and verification scope

`ImproverAnalysisPlan.from_bytes` checks and freezes the supported prospective
method. `analyze_improver_panel` takes that plan, an explicit population,
selected/empty slots, projected scalar rows and the frozen rule. It performs no
file, database, network or worker operations and does not change its inputs.
It consumes official projected scores; it does not rescore NoveltyBench.

Source, release and custody digests are supplied commitments at this numerical
boundary. The later protected reader must verify their original provenance and
the actual executing source closure before these numbers become experiment
evidence. The separate internal `_source_hashes` helper reads source files only
when explicitly called during preparation; the numerical path does not call it.

Ten new tests, three existing numerical tests and twelve existing rule tests
pass at the recorded cut. They include an independent rational log/square-root
oracle, unequal family sizes, six unequal allowances, empty/failed outcomes,
typed identities and no-I/O controls. Seven repository quality checks pass.
These checks do not establish a complete sealed experiment, hosted-CI success
or improved effectiveness.

```powershell
python -m unittest discover -s tests -p test_improver_analysis.py -v
```

Optional: runs the ten numerical tests once in your current PowerShell window
from the matching checkout. It needs no keys, spends no API money and does not
change experiment records. No second window is needed. Ctrl+C stops the tests;
they normally finish in seconds. No live run is requested by this slice.

## Targeted repair

IMP1-TARGET-01: the analyzer still reports `target_repair: not_assessed`.
A proposal hypothesis records what a change intends to fix; it does not show
that the change fixed it. Overall utility or distinctiveness gains cannot
supply that separate outcome.

Before the actual study, its protocol must define the target-review method,
the relevant parent and child task outputs, coverage and missing/uncertain
outcomes. The [descriptive method v1](IMPROVER-TARGET-REPAIR.md) supplies a separate
two-stage worksheet: fix intended targets using the full hypothesis and parent
sets before revealing child outcomes, then review the complete same-task child
sets. It retains every counted opportunity, actual immediate parents, multiple
targets, missing intentions, failed outcomes and disagreements. The actual
study must prospectively adopt and pin the method, its coverage and its review
arrangements; the method alone supplies no observed repair result.

Existing review exports cover sealed starter and selected-descendant
sets rather than every development proposal. A frozen supplementary review
can report descriptive repair findings from the retained full outputs and
lineage. A machine-checked extension is needed only if the adopted method
requires one. Keep official scores and the original analysis report unchanged.
The [scope record](conformance/imp01-larger-reader-cost-observation.json)
retains the source trace; [DESIGN section 8](DESIGN.md#8-measuring-improvement-competence)
keeps targeted repair within the original IMP-01 reporting requirement.
