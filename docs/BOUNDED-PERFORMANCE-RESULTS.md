# Bounded performance result — November 3, 2026

Implementation branch: `codex/bounded-performance-code`. A documentation copy
does not install this patch into another working checkout.

The two targeted changes reduce repeated work without changing the checked
outputs. **The predeclared 2× planning-speed target was missed: the measured
median improvement is 1.9819167×.** This is a completed short measurement,
with a failed performance hurdle. It does not pass the realistic-size history
gate or authorize another experiment. [PLAN](PLAN.md) owns the next decision.

## What changed

- PT-01: during one planning call, retain each eligible parent's already checked
  screen and reuse it for selection, source lookup and applicable feedback.
  Keep the existing fresh custody checks. Ordinary callers and unavailable
  reuse contexts retain full inspection; there is no cross-action cache.
- PT-02: retain the immutable selected tasks after validation, rather than
  repeatedly decoding the full artifact. Replace that tuple when selecting
  different tasks. Subclasses retain their existing dynamic behavior.

There are four changed application files: [answers](../buddha/answers.py),
[study planning](../buddha/improver_study.py),
[parent selection](../buddha/source_screen.py) and
[feedback](../buddha/source_feedback.py). Dataset formats, request settings,
official scoring, selection rules and persisted schemas are unchanged.
The approved future rule for fully accounted bad proposals is not implemented
by this patch; historical v4 behavior remains intact.

## What was measured

Three fresh Python processes per source cut ran interleaved on the same Windows
host: A2, B1, A3, B2, A4, B3. A is development commit
`2854cd8f9363a603a07be60b184b78d4ab79d9d3`; B is this patch's application cut.
Each process built equivalent fresh fixtures using existing public test helpers:
1,000 dataset rows, three selected tasks, ten answers per task, two genuinely
completed supplied-worker screens, 24,043 native inventory entries and
4,015,328 native-environment bytes. The two screen declarations are
5,315,388 and 5,315,404 bytes. No saved paid-run history was used.

The measured planning phase constructs its reader, runs the actual v1 planning
function, and finishes the reader checks. Fixture setup is excluded from that
phase and included in the separately reported whole-child time. Every child,
including setup, had a 180-second limit and completed within it. Counters and
profilers were disabled. No model APIs, real containers or long history builders
ran. No OS cache flushing was attempted; unrelated host activity was uncontrolled.

| Run | Planning seconds | Whole-child seconds | Whole-child peak working set, bytes |
| --- | ---: | ---: | ---: |
| A2 | 26.815721 | 131.962031 | 887,996,416 |
| B1 | 13.093382 | 114.467507 | 888,000,512 |
| A3 | 23.458510 | 123.882783 | 888,283,136 |
| B2 | 12.622144 | 112.452827 | 888,942,592 |
| A4 | 25.949993 | 124.854778 | 888,213,504 |
| B3 | 15.077081 | 115.485054 | 888,967,168 |

Median planning time fell from **25.949993 to 13.093382 seconds**; the ratio
is **1.9819167196122067×**, below the fixed 2× target. Median whole-child time
fell from **124.854778 to 114.467507 seconds**, a **1.0907442801819076×** ratio.
Median peak working set rose by approximately **0.0821%**, below the predeclared
1.2 candidate/baseline ratio ceiling. This is the OS-reported cumulative peak
for the whole child, not planning-only memory or a guaranteed memory limit.

An earlier A1 attempt is excluded and retained. Before planning, the two fresh
screens had different padded split metadata; the existing purpose guard
correctly rejected them. The fixture was corrected to share the same split,
then the six-run cohort and its order/limits were declared before the first B
measurement. A1 supplied no planning result. There were no timing extensions,
repeats to improve the median, or waived guards.

## Correctness and independent verification

All six declared semantic projections are byte-identical, SHA256
`c95ced47895e520fca849297ed8f5094b39835ae031c76abe8a239e455b5b339`.
They preserve tasks, selected parent/source, literal feedback, answers, metrics,
selection settings and the fixture's saved outgoing request bodies. Raw records
also retain the declared path, owner and source-pin differences. These request
bodies belong to screen fixture setup; no future improver request was dispatched.

Genuine failing checks preceded the changes: selected-task reads unnecessarily
decoded JSON, and the two-parent planning case collected screens seven times
instead of twice. The repaired checks pass. PT-02 passes all 30 answer methods
and five existing artifact-view methods, including primed selection/copy/pickle
and subclass cases. PT-01 passes 21 unique focused methods covering exact
plan/packet bytes, fallback, selection, control profiles, proposal reuse and
late tampering. Its final fallback check explicitly confirms seven ordinary
collections when reuse is unavailable. Existing tests were not removed.

The final combined cut passes Ruff, formatting, strict mypy, Bandit, development
and runtime dependency audits, and in-memory compilation. Discovery finds
2,289 unique test IDs with no duplicates. This is discovery, not a full-suite
pass. Required exact-source Linux/Windows CI remains a separate gate.

An independent agent reviewed the implementation and challenged the six-run
evidence: it verified arithmetic, artifact hashes, source pins, parity and the
strict target miss. The pin inventories cover 306 baseline / 307 candidate
Python files under `buddha`, `agents` and `tests`, not every public file. All
four application files still match the measured cut; a later assertion and
formatting change affects only the new test file and needs no timing repeat.

## Evidence and limits

Raw local evidence is retained beneath
`C:/Users/arvik/code/buddha/runs/checks/bounded-performance-20261103-v1`.
These large fixture files are not committed. The following SHA256 values bind
the retained records:

| Record | SHA256 |
| --- | --- |
| `measure-plan.py` | `102ae5c4c03880bb46ce4dc060dd06c8bd2e31fb934a7330b8d42d1cfd0b3b25` |
| `cohort/protocol.json` | `9e27ff3fd764c4d19dd4cedb98443c4fcd175276d4d1deff38354751091b6ce2` |
| `cohort/results.json` | `313ab13703751ccbbebc35e8b8168b79a0a53167d915e00540fac60f5bc400d2` |
| `cohort/review.json` | `ce08fbb7ef4763321c60a299739aaf1b8e2f3c5832131168b154e978299f6447` |
| `pt01/correctness-receipt.json` | `de55e282b416f29778c72eabb42388a453f40985c0bcc7077e7f70d9456a3488` |
| `pt02/receipt.json` | `40959d4f7c6e88f3d27158d97fec59638dea37552181f11c7d87188023a508b7` |
| `final-checks/receipt.json` | `b4a536a3b2068b04de325ffaec115a4b0cd3343c1b01f4698cc351e3848da4ea` |

The PT-01 correctness receipt records existing tool-observed checks; their raw
stdout is not retained as standalone files. The timing cohort retains its raw
per-process logs and artifacts separately.

This composition is actual v1 planning over two completed screens. It is not
a valid admitted study history, the full restoration loop, positive full v3/v4
study composition, the 193-owner/660-operation proof, a live run, or evidence
of better creativity. The full-history gate is still open. The strict hurdle
miss stops advancement for a user decision; no extra tuning round, paid call,
or new long run follows automatically.
