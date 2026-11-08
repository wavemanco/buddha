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

The November 7 D8 pair-readiness correction selects **514 methods**, up from
508 in the preceding correction (476 before D8). The added
coverage checks full feedback above the old 1 MiB limit, historical seed/policy
compatibility, safe network-error persistence and unchanged financial holds,
plus prospective capacity v2, the explicitly selected compatibility pair and
settled-timeout outcomes with their unknown-charge/cleanup/source counterexamples.
It uses the same short workflow; no full qualification is scheduled by this
change. Earlier recorded timings belong to their original selections/source.

Discovery still imports every test module and refuses import failures. Only
selected test bodies run. Missing, duplicate or overlapping selection labels
fail rather than quietly reducing coverage. Inventory and terminal receipts
bind the contract scope and literal selection. Existing process containment
and checked terminal completion remain in use.

## Full qualification

The separate `checks` workflow in
[qualification.yml](../.github/workflows/qualification.yml) starts only when a
maintainer applies a label matching the PR's exact source commit.
It first runs the corrected full continuation case on Windows. Only a successful
continuation job releases the five qualification groups per OS. Those groups
retain the full discovered suite, the original
partition seed, isolated large case, all quality checks and the 60-minute
genuine-progress rule. Opening a PR, pushing a commit or adding an unrelated
label does not start its test jobs. Each full run requires the user's approval
for that exact source and its Actions-minute cost.

After approval, use GitHub's PR page to apply `qualify-` followed by the full
40-character head commit SHA, with no spaces. This is a 48-character label.
It requests one continuation job and, only if that passes, ten qualification
jobs against that exact commit; every checkout explicitly
uses the head SHA rather than GitHub's temporary merge commit. The PR must be
mergeable and its head branch must belong to this repository. Fork PRs are
excluded from this route.

No PowerShell command, API key or model API money is needed. The run uses
GitHub Actions minutes. Follow it in **Actions** and use **Cancel workflow** to
stop it. The continuation and all ten qualification jobs must finish successfully;
a skipped workflow or job is
not a full-suite pass.

A later push does not repeat qualification or transfer approval to the new
source. An old label or another label cannot qualify that new commit. A new
SHA label, removing and reapplying a label, or using **Re-run jobs** requires
approval for another run. Do not apply a qualification label during routine
development.

Full qualification of the integrated source remains required before paid
execution or a claim that the integrated system passed. PR #243 keeps its
original workflow and gate. Retiring the obsolete document-lane controller
also retires its nine tests; the remaining full inventory is reported normally.

The earlier ten-job route completed at source8e, with the same test assertion
failing on both OSes. The corrected continuation-first route passed once at
source `0d27ed4dd5aa44ce58618a6af6824141fed43f02` in
[run42352102463](https://github.com/wavemanco/buddha/actions/runs/42352102463).
The first job completed successfully before all ten matrix jobs started.
That exact-source pass does not transfer approval to a later head.
GitHub documents the [PR label event and explicit head checkout](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
and the [format expression](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#format)
used to bind the label to its source.

### Prepared continuation check and timing basis

**Completed once at frozen source0d27; future attempts need new approval.**
All eleven jobs passed without retries, timeouts or cancellations. The first
case passed1/1 with63 successful subtests; its whole job took41m12s. The matrix
completed2,232 methods per OS: Linux2,227 passed/five declared skips and
Windows2,231 passed/one declared skip, with zero failures/errors and all70
quality checks successful. Its parallel job span was3h17m35s; the whole sequence
spanned3h58m49s from first job start to last completion. These are observations,
not a speedup claim or live benchmark result. Production code remains frozen;
this documentation update is not a new full qualification or paid clearance.

The following retains the preparation's timing basis and limits. It reuses the existing
`ci_test_shard` isolation selector and Windows worker containment. There is no
new local runner, fixture or model call. GitHub's
[job dependency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
holds the ten qualification jobs until the continuation job succeeds; no failure
override is configured. Its
[total job timeout](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes)
also includes checkout, installation and fixture setup/cleanup.

The selected case is
`test_study_continuation.StudyContinuationTests.test_retained_last_slot_zero_cut_reaches_complete_development_and_replays_keylessly`.
It builds its own original/continued fixture, checks the corrected one-cold-read /
one-forward-read / incomplete interruption result, reuses the original receipt
without a duplicate send, completes development and verifies immutable old
evidence, selection and keyless replay. Workers and HTTPS replies are supplied;
no generated Python, real container or model API runs. It is an engineering test,
not the live benchmark comparison.

| Stage | Previous observation at source8e | Limit used in the approved attempt |
| --- | --- | --- |
| Full continuation case | Test body: Linux14m29s, Windows40m32s. Conservative class-inclusive envelopes:14m35s /40m52s. | One Windows job,90minutes total, including installation and cleanup. Existing60minutes without genuine progress and180seconds per fixture subprocess remain. |
| Full qualification, only after continuation success | Ten parallel jobs completed in3h36m46s from first job start to last completion. Slowest Linux job48m20s; Windows3h36m46s. | Ten jobs;60minutes without genuine test progress and6hours total per job. No automatic retry. |

The90-minute first-job limit is a little over twice the observed Windows
class-inclusive40m52s and leaves about49minutes for installation, host variation
and other work. A planning baseline is roughly42minutes after adding the prior
Windows setup overhead; it is not a runtime guarantee. We have one execution per
OS, at the earlier source, and no new calibration run. The test-only correction
and this workflow preparation leave production and fixture code unchanged.
The combined sequence's observed-baseline estimate is about4h20m plus queueing;
the two stages have not yet been measured together. Queue time is separate from
job limits; six hours per qualification job is not a six-hour whole-workflow cap.

The previous matrix consumed14h44m25s of aggregate runner time despite its
3h37m parallel elapsed time. The new first job adds its own Windows runner time,
and the complete suite still includes that case on both OSes. Actual billing
depends on the repository/account; these are durations, not a price estimate.
Model API spending remains zero.

Normal assertion failure is a completed failed check. A timeout, cancellation,
runner failure or missing normal completion evidence is an incomplete/partial
result with its stage, reason, elapsed time, source and raw logs retained.
Neither releases qualification. Qualification failures likewise do not clear
paid execution. There is no retry, resume, extension, capacity rebuild or merge
under this preparation. Existing8e capacity evidence retains its original source
identity. [PLAN D6-D8](PLAN.md#current-gates-to-the-completed-comparison) owns
adoption and the remaining gates.

Timing evidence is retained locally in
`runs/checks/continuation-check-preparation-20261106-v1/TIMING-BASIS.json`,
including original job/log hashes and the difference between test-body time,
class-inclusive bounds and whole-shard time. The source run is
[42312404454](https://github.com/wavemanco/buddha/actions/runs/42312404454).

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
