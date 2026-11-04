# CI: fast feedback and full qualification

Ordinary pull requests need useful feedback in minutes. Full experiment,
interruption and historical-recovery tests are a separate qualification step.
A fast pass never means the full suite passed. [PLAN](PLAN.md) owns the current
work and approval gates.

## Ordinary pull requests

The `fast checks` workflow runs Linux and Windows jobs, each with a
**15-minute total limit**, including installation, quality checks and tests.
This is a limit, not a measured runtime promise. A timeout fails the check.

The existing dependency audits, lint, formatting, strict types, code security
and compilation run before the selected contract tests. Quality checks run
twice rather than ten times. A newer commit cancels an obsolete fast run for
the same PR; distinct PRs and old-workflow runs are not cancelled.

The explicit selection is `CONTRACT_TESTS` in
[ci_test_shard.py](../ci_test_shard.py). It covers shared accounting,
authorization, providers, credentials, requests, task/answer artifacts, seed
generation, capacity arithmetic, path/executor boundaries and the test runner.
It also selects a pure whole-set review check from a mixed-cost module.

Discovery still imports every test module and refuses import failures. Only
selected test bodies run. Missing, duplicate or overlapping selection labels
fail rather than quietly reducing coverage. Inventory and terminal receipts
bind the contract scope and literal selection. Existing process containment
and checked terminal completion remain in use.

## Full qualification

The separate `checks` workflow in
[qualification.yml](../.github/workflows/qualification.yml) is manual-only.
It retains five groups per OS, the full discovered suite, the original
partition seed, isolated large case, all quality checks and the 60-minute
genuine-progress rule. PRs and main pushes do not launch it. A new full run
requires the user's approval for that source.

Full qualification of the integrated source remains required before paid
execution or a claim that the integrated system passed. PR #243 keeps its
original workflow and gate. Retiring the obsolete document-lane controller
also retires its nine tests; the remaining full inventory is reported normally.

**Installation limitation:** GitHub requires a manually dispatched workflow
file on the default branch. This unmerged file is not yet an available
premerge qualification route. Installation must be resolved at integration
before offering a full-run handoff. No long run was dispatched to test it.
See GitHub's [dispatch prerequisite](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatch).

Repository settings inspected on November 3 had no required status checks or
branch rules. Full qualification is a project policy, not a verified automatic
GitHub merge block. Fast green alone does not clear a merge, live run or
scientific claim.

## Progress and stopping

The full runner stops after 3,600 seconds without a completed test, subtest or
fixture outcome. Starts, printed messages and heartbeats do not reset that
clock. Failed or skipped outcomes count as progress; failures still fail.
The fast hosted job adds its stronger 15-minute total limit.

Windows uses a Job Object; Linux uses a private process group. The runner
contains its trusted worker and inherited children and checks a terminal
receipt. An abrupt zero exit cannot turn incomplete work into a pass.
This runner is not the sandbox for model-authored code.

Exit 124 means inactivity; 125 means runner/containment failure; 130 means
interruption. Original exceptions and failed assertions remain failures.

## Optional local commands

These run once from the checkout containing `ci_test_shard.py`, in the current
PowerShell window. No separate window, API keys or Docker is needed. They make
no model API calls. Ctrl+C stops them. They may create temporary test files and
ordinary Python bytecode caches.

```powershell
python -m ci_test_shard --suite contracts --count 1 --index 0 --list-only
```

This prints the selected inventory without running test bodies. It still
imports modules, so import failures remain visible.

```powershell
python -m ci_test_shard --suite contracts --count 1 --index 0
```

This runs the selected contracts in the contained worker. Locally it uses the
60-minute inactivity rule; it does not inherit GitHub's 15-minute job limit.
The implementation's local verification uses a separate short outer limit.
This command is not full qualification.

```powershell
python -B -m unittest discover -s tests -p test_ci_test_shard.py -v
```

This checks selection, inventory, unittest behavior, real progress, stalled
workers, cleanup and terminal receipts with small supplied test programs.
It does not run the complete Buddha acceptance suite.

## Why the old checks were slow

The old workflow put the full suite on both OSes behind every code PR and
checked fast errors afterward. Some tests reconstruct complete experiments
to check individual behaviors. In a completed historical run, one Windows
recovery method took 5,392 seconds; the three slowest methods consumed half
that job's test time. This is local filesystem/history/accounting work with
supplied replies, not paid-model waiting.

The new lane is intended to shorten development feedback. It does not yet shorten full
qualification or prove production history performance. Further reductions
must preserve cold-recovery, custody and accounting coverage; copying a pinned
fixture to another path is not automatically valid.

Earlier records remain evidence for their original sources and policies:

- [Original progress/containment verification](conformance/ci-idle-hosted-completion.json).
- [Windows investigation](conformance/windows-ci-performance-delivery.json).
- [Partition change](conformance/ci-partition-seed-delivery.json).
- [Retired document-lane verification](conformance/ci-leaf-docs-delivery.json).

They do not certify the new fast workflow or the next integrated candidate.
