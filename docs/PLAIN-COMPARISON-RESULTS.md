# Reading the plain-model and Buddha comparison

`buddha.plain_comparison.compare_plain_references` reads complete original
publications from the bounded improver study and one or both plain-model
baselines. It checks the records and produces a descriptive comparison in
memory. It starts no workers, makes no provider calls, reads no keys and writes
no results or accounting records. Original databases are captured as bytes and
queried only through copies in memory.

This implements the result join proposed in
[the reference preparation](PLAIN-REFERENCE-PREPARATION.md). It does not adopt or
fund that experiment. [PLAN.md](PLAN.md) remains the roadmap; both IMP-01 and
EVAL-02 remain open.

## What must be fixed before execution

A `buddha.plain-comparison-plan.v1` file declares the original trial location and
definition hash, the selected reference modes and their original locations,
authorization paths and descriptor hashes. It also pins the comparison method
and its consumer sources. It contains no future result hashes.

The same plan path and hash must be supplied through the existing assessment
`input_bindings` and baseline `input_files`/`expected_input_hashes` interfaces
before their owners are created. Every original owner must retain that binding.
Adding a plan after seeing scores is rejected, even if its files and result
hashes are otherwise valid. No new execution controller or accounting schema is
introduced.

After execution, the caller supplies the expected original assessment report
hash and exactly one report hash for every declared reference. These later
publication pins are separate from the prospective plan. A report hash alone
does not prove that a comparison was declared before outcomes.

The library arguments are:

| Argument | Meaning |
| --- | --- |
| `plan` | Path to the original prospective comparison plan. |
| `expected_plan_sha256` | Its previously frozen byte hash. |
| `expected_assessment_report_sha256` | Expected original complete Buddha assessment publication hash. |
| `expected_reference_report_sha256` | Mapping from each declared `regenerate` or `in-context` mode to its original complete baseline report hash. |

There is no new paid CLI command in this slice. Extracting the shared original
measurement-row helper changes the assessment's source pin. The existing
unfunded preparations stay unchanged; a fresh preparation must use the current
consumer sources and bind the plan before any live execution.

## What the reader checks

Both original result readers validate owners, generation answers, stage reports,
sealed artifacts and independent completion anchors. The join then requires the
same selected final TaskSet, preserving typed IDs, order, answer counts, source
and dataset identity. The full development TaskSet is not substituted for the
final panel.

The reference must use empty Buddha instructions and its declared sampling
mode. Generator provider, model, output allowance and the selected full request
profile must match Buddha's declared access. Evaluator code, environment,
hooks, request profiles, stages and execution limits must match. Source
inventories and locations may differ; whole-panel versus per-task wallet and
call ceilings are disclosed separately. Different candidate source hashes are
expected and are not treated as incompatible evidence.

The consumer uses the existing optional NoveltyBench projection to read saved
official utility and distinctiveness. It does not run the judges, repartition
answers, repair rows, change the utility formula or derive a replacement score
for an invalid scalar. Declared request profiles do not independently establish
the sampling behavior of arbitrary evolved code; that still needs its actual
request/history evidence. A system comparison does not isolate the effect of
sampling mode or extra compute.

## How to read the result

The three Buddha roles remain separate: starter, descendant from the initial
improver and descendant from the evolved improver. All planned starts,
development repetitions and sealed repetitions count. A rejected descendant
does not disappear from the denominator.

For each prompt and role, the consumer averages its original measurements over
all planned conditions. It then subtracts each plain reference's measurement
and averages those differences with equal weight per planned prompt. Family
labels remain in the report. There is no significance test or uncertainty bound
in this descriptive comparison.

Numbers are retained as exact numerator/denominator pairs. A saved floating
point value keeps its literal binary value; it is not rounded into a different
measurement. Original measurement rows, role/source identities and null slots
remain available alongside the prompt means. Returned plain-reference rows
also include projection diagnostics; detailed Buddha diagnostics remain in its
original checked native artifacts.

If a required condition or scalar is missing, the affected mean is unavailable
and `analysis.status` is `incomplete`, with `analysis.reason` explaining why.
This is separate from the original executions' completion status. Valid distinctiveness
can remain visible when utility is unavailable. There is no zero filling,
selection of only completed prompts or winner claim.

One plain answer set reused across several Buddha roles remains one reference
observation. Original owners and operations are counted once. The resource
report shows costs, calls, billed input/output tokens, unknown usage, stage
labels and role breakdowns, plus the original development costs. Development
receipt details include code-author and planning calls, billed tokens and
unknown usage, drawn from its already checked original owner list and captured
databases. Development stage labels remain unattributed rather than guessed;
original owner locations retain the detailed trace. Combined API research
totals cover this declared study and its references. Historical experiments
remain separate records. Shared authorization snapshots are not added together as if they were
independent spending. Declared ceilings and actual consumption are different
quantities. Native review and human work are not priced by these API totals.

## Incomplete execution and remaining gates

This consumer requires complete original publications. An unfinished, altered
or unanchored execution is refused; it is not repaired or rerun. Its original
attempts, stage reports, costs and holds remain with the execution evidence.
The funded outer handoff must separately retain a partial-run report containing
its stage and reason before this is ready for live use. A missing publication
does not become a fabricated all-zero comparison.

The next preparation must bind the plan into both sides, check the exact
resource envelope and original partial-result handoff, and present one
consolidated workload/allocation within the proposed **$150 API cap and
16,384-attempt limit**. Earlier smaller dollar figures are conditional usage
examples, not additional caps or authorizations. Reviewer arrangements,
account checks, hosted CI and final outgoing-request checks still precede any
live command. No scientific or human-review gate closes through this reader.

## Optional offline checks

This command checks the numerical aggregation and plan validation once in the
current PowerShell window. It uses temporary synthetic examples, needs no keys
or Docker and spends nothing. Ctrl+C stops it.

```powershell
python -m unittest discover -s tests -p test_plain_comparison.py
```

This command checks the composed reader once using fresh synthetic original
owners, supplied workers and mocked HTTPS. It needs no Docker or keys, makes no
real API calls and does not read your live runs. The completed check took about
20 minutes on this Windows host. It runs in the current window; Ctrl+C stops it. Temporary examples are
cleaned up after normal completion.

```powershell
python -m unittest discover -s tests -p test_plain_comparison_integration.py
```
