# Proposed history check after the C1 repair

This prepares the next IMP-01 measurement in [PLAN.md](PLAN.md). The user approved
one new bounded attempt on November 3, 2026, after checks. Execution has not
started: hosted CI and final pin/path checks remain. The earlier one-off
construction attempt was used by v13; its partial result and files remain unchanged.
The [approval record](conformance/c1-history-approval.json) records the later
decision separately from the original unapproved preparation.

The purpose is to check whether Buddha can reconstruct a realistic amount of
saved work within 15 minutes before starting another paid comparison. It tests
the history reader, not creativity, useful diversity or improver effectiveness.

## The approved single attempt

| Step | Work | Limit and outcome |
| --- | --- | --- |
| Construct synthetic history | Use the existing supplied-data fixture with the repaired source at `9ded9b9f3decb6a1d66a6497efa53b3e1ce5dd62`, bound to 365 public Python files | Up to 10,800 seconds. Require the exact 193-owner/660-operation cut, nine admitted decisions and the next screen action, with unchanged workload dimensions. |
| Read in a fresh process | Reconstruct the completed history, check current state and finish the existing reader | Up to 900 seconds; run only if construction verifies the required cut and source checks pass. |
| Retain the observation | Save completion or explicit partial results, phase, logs and source checks | No retry, resume or automatic deadline extension. A partial leaves the acceptance gate open. |

The fixture retains 1,000 source rows, three selected tasks with ten answers each,
and the existing source/environment/feedback size requirements. Its eight fixture
files are unchanged. This uses supplied replies: **no model API spending, API
keys, Docker containers or original paid-run records**. It uses local CPU and disk.

The phase limits allow three hours plus a conditional 15-minute read, with
additional setup, hashing and reporting time. The reused parent enforces phase
timeouts; it does not impose a single 11,700-second total deadline.

## What changed, and what remains uncertain

The [C1 repair](C1-INTERPRETATION-REUSE.md) removes duplicate interpretation inside
one evidence read. Its focused tests preserve all fresh reads, hashes and final
checks. Every scheduler action still restores and checks the growing history.
Completion within either limit remains unmeasured. This attempt would measure
that behavior at the required cut.

The prepared parent and child reuse the v13 logic with a fresh namespace and
source binding. Independent review checks their normalized syntax-tree equality,
all 365 source pins, unchanged fixture hashes, cut, workload and phase limits.
The [preparation record](conformance/c1-history-preparation.json) binds the exact
scripts, manifest, metadata corrections and review limits.

## Before execution

The new single-attempt decision is recorded. Complete all configured exact-source
hosted checks and recheck every source/script/manifest pin. Recheck
all eight runtime destinations immediately before launch: each must be absent,
including aliases. The parent checks the workspace first; the other outputs use
exclusive creation. Do not rely on their absence at preparation time.

No operator command is issued by this proposal. No additional PowerShell window
or keys are needed from the user. Once checks clear, the agent runs it once
under the existing phase timeouts and retains any incomplete observation.
