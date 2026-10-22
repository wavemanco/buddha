# The numerical improvement rule

This implements the two-metric rule in [DESIGN section 6](DESIGN.md#6-archive-and-promotion).
It is a small part of EVAL-01 in [the living plan](PLAN.md). The validation and
final-evaluation controller remains unfinished.

An experiment must choose its main metric and acceptable tradeoff before
seeing the comparison's results. For utility as the main metric, the rule asks:

- Is the lower confidence bound on the utility difference strictly above the
  required gain?
- Is the lower confidence bound on the distinctiveness difference at least
  the negative of the permitted loss?

Both conditions must pass. Choosing distinctiveness as the main metric swaps
the two roles. The rule always uses the declared main metric.

A lower confidence bound describes the lower end of an uncertainty estimate
for a candidate's difference from its comparator. Its construction, confidence
level and validity require a separate, frozen analysis method. This helper
accepts supplied bounds; it does not estimate them from benchmark scores.

## The frozen rule

`buddha.improvement_rule.ImprovementRule.from_bytes` accepts a JSON record with
exactly these fields:

```json
{
  "format": "buddha.improvement-rule.v1",
  "primary_metric": "utility",
  "minimum_gain": 1,
  "max_other_loss": 0.5
}
```

These numbers are examples for checking the code. Scientific thresholds for a
live held-out experiment have not been selected. The main metric is `utility`
or `distinct`; both margins are mandatory, finite and nonnegative. Zero required
gain still requires a strictly positive bound. Zero permitted loss requires the
other bound to be at least zero.

The artifact stores immutable canonical JSON bytes. Changing the metric or a
margin changes its fingerprint. Returned records are detached copies.

## Applying it

`evaluate_improvement_rule(rule, lower_bounds=..., complete_coverage=...)`
accepts one bound for each metric and a literal `True` or `False` coverage flag.
It runs once in memory, reads no files or keys, starts no worker and spends no
money. It returns:

| Status | Meaning |
| --- | --- |
| `rule_satisfied` | Both supplied numerical bounds meet the declared inequalities. |
| `rule_not_satisfied` | At least one supplied bound fails an inequality. This does not disprove improvement. |
| `inconclusive` | Coverage was declared incomplete, or either bound is unavailable (`null` / `None`). |

For the example rule, bounds of utility **1** and distinctiveness **0** fail:
the utility gain equals the threshold. Bounds of utility **1.25** and
distinctiveness **−0.5** pass: the permitted loss includes equality. A
distinctiveness bound below **−0.5** fails. The code applies no rounding or
extra tolerance.

Malformed inputs raise `ImprovementRuleError`, including when coverage is
incomplete. Missing bounds stay unavailable; they never become zero scores.
Results must fit the project's existing bounded JSON record format. Numbers
retain their integer or floating-point representation through comparison;
an integer that cannot be encoded is rejected rather than rounded.

## What the caller must establish

The coverage flag is a caller assertion. The caller must verify complete
compatible evidence and construct the bounds under the experiment's declared
analysis and error policy. A satisfied numerical rule can allow the declared
loss on the other metric.

The later controller must bind this exact rule before observation, limit
validation occasions, freeze finalists before final-task access and preserve
partial or negative results. This helper supplies no permission to access final
data, spend money or promote a candidate. Official NoveltyBench scores and
formulas retain their original meaning.

## Optional developer check

From the project folder:

```powershell
python -B -m unittest discover -s tests -p test_improvement_rule.py -v
```

This runs the numerical-rule checks once in the current window. It needs no
keys, spends no API money and changes no source files. No separate window is
needed; Ctrl+C stops it.
