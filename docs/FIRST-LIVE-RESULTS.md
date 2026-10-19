# First completed live policy-search pilot

Verified October 19, 2026. Recovery run `a0946e22ae1e45d6bf8f74cf9f4f30bb` completed the slice 3 live engineering pilot: one development prompt, two seed policies, one proposal and one child evaluation. This is evidence that the composed policy-search path works for this case, not evidence of general improvement or source self-modification.

The subsequent [full pilot concern review](PILOT-REVIEW.md) covers all 30 stories, explains why partition errors can inflate utility too, records operational fault probes and preserves matching source. [PLAN.md](PLAN.md) consolidates those findings with the original roadmap and owns all current sequencing/status.

## Observed results

The frozen prompt was: `Tell me a story in five sentences about a girl and her dog.` Metric version is NoveltyBench 1.1 under the run's existing frozen reference and controls; this review did not check upstream again or change the instrument.

| Policy | Utility | Distinct answers out of 10 |
| --- | ---: | ---: |
| Independent sampling, empty extra instructions | 7.183935 | 9 |
| In-context regeneration, empty extra instructions | 7.480236 | 10 |
| Proposed instructions, independent sampling | 8.567273 | 10 |

The child improves observed utility by 1.087037 points (14.53%) over the stronger seed on this prompt, with equal measured distinctiveness. It is the sole observed Pareto-frontier candidate. Admission means complete evaluation and archive inclusion; it is not statistical confirmation or deployment promotion.

The child instructs the generator to satisfy literal constraints, choose a specific original premise or mechanism, and vary central situations and outcomes rather than surface details. The policy is preserved in [policy.json](../runs/first-live-recovery/candidates/34cecdbd8a9307796972dcc485641fc7021f97e8b2715a87feeb140ab54f424b/policy.json).

| Stage | Recorded conservative cost, USD |
| --- | ---: |
| Generation | 0.009326 |
| Partition judging | 0.003376 |
| Quality judging | 0.285910 |
| Policy proposal | 0.001541 |
| **Recovery total: 63 completed calls** | **0.300153** |

There are no pending or unknown operations and no held reservations in the recovery run. Quality judging represents 95.25% of its recorded cost. These are configured maximum-rate calculations on reported tokens, not reconciled invoices. The $49.465918 cap was an allowance, not a spending target. The final report is [report.json](../runs/first-live-recovery/report.json).

## Verification performed after completion

- Reconstructed the complete search report from saved receipts using `inspect_search` on a disposable copy and its network-rejecting cached transport. The reconstructed report exactly equals the saved report, including decisions and costs.
- The three candidate evaluations pass the existing importer, checking protocol identity, complete prompt coverage, cross-stage consistency, artifact hashes and v1.1 arithmetic.
- SQLite reports `integrity_check = ok`; all 63 operation records are completed and their charges sum to the report total.
- All 63 checksummed diagnostic request/outcome pairs bind to the corresponding ledger operation and request fingerprint. Each records HTTP 200 and a received response.
- Existing source contracts validate. Every file in both original run directories has the same SHA256 before and after verification. Inspection of the original ledgers used read-only SQLite connections.
- The original ledger hash still matches the recovery funding snapshot. Both manifest content hashes and the combined funding arithmetic match. Manifest hashes use the canonical content checksum, not the entire checksummed file's byte hash.

No new provider calls were made by this review. No runtime code, tests, frozen manifests, ledgers or evaluation records were changed. The earlier 245-test result remains historical; the suite was not rerun for this documentation-only handoff. There is no Git repository or hosted CI in this workspace.

## Measurement limitation requiring review

A qualitative review found repeated central material in the child outputs despite all ten being assigned separate classes. The task does not require shared names or a special dog ability. Nevertheless, many stories use Mara, Pippin and finding lost things or sounds. In particular, answers 3 and 10 both involve a dog trained to find lost sounds, a bridge, recovered music and restored sound, with different objects and endings.

The stories visibly satisfy the five-sentence girl-and-dog request. The pinned partition definition permits distinct central content despite shared structure, so this observation is a calibration concern, not a demonstrated implementation defect. It does mean that a score of 10 distinct should not be read as ten wholly different creative approaches. The judge supplied groups and numeric scores without explanations. The user's subsequent review explicitly rejected this plot repetition as insufficient distinctiveness. Record the child as failing that qualitative project criterion despite its measured utility increase; this is an unblinded human assessment, not a completed independent rating study. Preserve the original benchmark scores unchanged.

The child selected independent sampling (`regenerate`). In that existing code path, each generation receives the same task and policy instructions without the other nine answers. Its instruction to choose a different central premise consequently cannot compare against what it already produced. This absence of within-set history is verified in the request-construction path; its contribution to the observed repetition is a hypothesis, not an experimentally isolated cause. The existing `in-context` mode supplies previous answers, so a controlled comparison using that capability should precede any new diversity subsystem. History can also anchor repetition and is not a guarantee of diversity.

Evidence: [generated answers](../runs/first-live-recovery/candidates/34cecdbd8a9307796972dcc485641fc7021f97e8b2715a87feeb140ab54f424b/evaluation/generations.jsonl), [partition labels](../runs/first-live-recovery/candidates/34cecdbd8a9307796972dcc485641fc7021f97e8b2715a87feeb140ab54f424b/evaluation/v1.1/partitions.jsonl), and [quality scores](../runs/first-live-recovery/candidates/34cecdbd8a9307796972dcc485641fc7021f97e8b2715a87feeb140ab54f424b/evaluation/v1.1/scores.jsonl).

Before scaling search, review a blinded sample against the existing equivalence definition and retain disagreements separately. Then freeze a comparison of the same instructions under the two existing sampling modes on multiple development prompts, with all calls charged and no silent replacement of similar answers. This is proposed follow-up, not an authorized or executed paid run. Do not overwrite the official-reference judgments or tune them after observing this candidate. No held-out prompts, multiple independent repetitions, matched search-method ablations, transfer tests or human preference study were run.

## What the interruption means for the codebase

The interrupted attempt is an operational incident and a partial experiment, not a source-code rollback. Its durable receipts and unknown reservation behaved conservatively. Progress acknowledgments, heartbeat output, clean interruption handling and safe HTTP diagnostics were added in the prior follow-up; this successful run exercises the normal progress and diagnostic path, not every failure branch.

Recovery remains manual. The CLI has no general recovery-preparation/replacement command, and the runtime does not read or enforce `funding.json` as shared authority across directories. Each ledger enforces its own frozen cap. The constrained two-run arrangement therefore depends on leaving the original inactive. The completed recovery does not reconcile the old unknown request or prove arbitrary interruption recovery is solved.

The old run retains nine completed replies and one unknown request, with no complete candidate result. Those replies are excluded from the recovery scores. Combined recorded known cost is **$0.301862**, with **$0.532373** still held against the old unknown request: **$0.834235** recorded plus unresolved exposure. The recovery report's cost is recovery-only. [funding.json](../runs/first-live-recovery/funding.json) and the [incident review](FIRST-LIVE-REVIEW.md) preserve the relationship; no liability was silently released.

## Historical checkpoint and current plan

Slice 3 now has its capped live pilot. The original full-agent objective remains incomplete: the proposer changes declarative instructions only; source self-modification and an isolated executor are slice 4.

Matching source was subsequently preserved by the [pilot concern review](PILOT-REVIEW.md). The recovery, calibration, policy-comparison, source-execution and scientific work is consolidated in [PLAN.md](PLAN.md); follow that file rather than this handoff for current scheduling. No new experiment or paid execution starts with this results record.
