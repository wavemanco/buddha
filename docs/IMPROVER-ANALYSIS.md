# Comparing improvement procedures

The numerical part of the improver comparison is implemented. It does not yet
read original experiment records or run the sealed assessment. Those connections
remain IMP-01 work in [PLAN.md](PLAN.md). The [delivery record](conformance/imp01-paired-analysis-delivery.json)
retains the exact checks and source versions.

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
