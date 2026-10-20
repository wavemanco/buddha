# Completed linked continuation

Verified October 20, 2026. Run `a486d90396934a45940637d77a168304` completed the original one-prompt policy-search pilot by reusing nine saved answers and making 51 new model calls. This closes the linked recovery gate REC-04L and aggregate REC-04 in [PLAN.md](PLAN.md). Meaningful-diversity improvement, held-out generalization and source self-modification remain unestablished.

## Recovery and accounting

The original run `a1257f96467b490b910b559437a71258` remains interrupted: its missing tenth request is still unknown and its $0.532373 reservation remains held. The completed result belongs to the new linked run. Its tenth answer has a new operation ID and explicit replacement lineage; it was not inserted as a response to the old request.

| Scope | Calls / evidence | Recorded cost, USD |
| --- | ---: | ---: |
| New continuation operations | 51 completed; no pending or unknown | 0.274533 |
| Inherited answers | 9 evidence references; no new operations | 0.001709 already charged in the original run |
| Complete continuation evidence | 60 operations/references | 0.276242 |
| Entire experiment, known cost | 123 completed operations across three attempts | 0.576395 |
| Original unresolved liability | 1 unknown; 124 physical attempts in total | 0.532373 held |
| Entire experiment, committed | Known cost plus held liability | 1.108768 |
| Remaining dollar allowance | Original $50 cap minus committed amount | 48.891232 |
| Remaining call allowance | Original 128-call cap minus 124 | 4 calls |

Inherited evidence is included once in the shared known cost. The new continuation used fewer than its 55-call ceiling because the first candidate was partitioned into six groups, requiring six quality judgments. A large remaining dollar balance does not override the remaining four-call cap or authorize another experiment. Costs are configured conservative calculations from recorded usage, not reconciled provider invoices.

| New continuation stage | Recorded cost, USD |
| --- | ---: |
| Generation | 0.008629 |
| Partition judging | 0.003313 |
| Quality judging | 0.261265 |
| Policy proposal | 0.001326 |
| **Total** | **0.274533** |

The saved report is `runs/first-live-continuation-v2/report.json`. The report's `costs`, `inherited_costs`, `evidence_costs` and `authorization` fields describe these different scopes; they must not be added together as separate bills.

After both verification passes, the completed continuation was permanently deactivated for new paid dispatch. All runs in its shared authority are now inactive; financial totals and the original unknown hold are unchanged. This appends a closure event to the authority without changing any run artifact. `runs/reviews/rec04l-closure.json` records the transition. Further experiments need their own concrete allocation; no automatic reuse of the four remaining calls is scheduled.

## Observed task results

The unchanged task was: `Tell me a story in five sentences about a girl and her dog.` All measurements use the frozen NoveltyBench 1.1 instrument, with one answer set per policy on this one development prompt.

| Policy | Candidate prefix | Utility | Official distinct answers out of 10 |
| --- | --- | ---: | ---: |
| Independent sampling, empty extra instructions | `2cad4fc7` | 5.304219 | 6 |
| In-context generation, empty extra instructions | `68608e69` | 7.117947 | 10 |
| Proposed instructions, independent sampling | `12a952c2` | 8.252795 | 10 |

The child's observed utility exceeds the stronger seed by 1.134848 points. It is the sole numerical frontier candidate in this run. These are exploratory development measurements, not confirmed promotion or a controlled comparison with the earlier completed recovery. The earlier recovery's samples and child policy differ, and the linked seed includes nine historical answers.

## Content concerns carried forward

An unblinded review of all 30 stories reinforces existing findings M1–M3 and E1–E5 from [the pilot review](PILOT-REVIEW.md). Answer numbers below are one-based. The girl and dog are required commonality; their mere presence is not evidence of repetition. Original official labels and scores remain unchanged.

- **M1/M2, repeated central plots:** child answers 7 and 10 both find an obstructed village water source, have the girl and dog help clear it, restore the water and become its keepers. Answers 2, 3, 7, 8 and 10 concentrate on water/spring restoration; answers 1, 4 and 6 concentrate on lighthouse signaling or boat rescue. Shared subject alone does not establish equivalence, but these clusters need the central-content audit despite all ten official classes being distinct.
- **M3, literal compliance:** the in-context seed's answer 9 contains only four sentences; its official quality score is 3. This shows that a completed evaluation is not a guarantee of satisfying the task's literal form.
- **M3, craft and continuity:** the in-context seed's answer 7 refers to three dogs after narrating two. Child answer 9 appears to place the missing key under a floorboard and later in a goat's mouth without explaining the move. These are development-review concerns, not independently adjudicated quality labels.
- **E2, sampling semantics:** the new child again uses independent sampling. Its instruction to vary central plots cannot see earlier answers in that mode; this remains a plausible explanation for repetition, not an isolated causal finding.
- **E9, newly observed task-specific policy:** the child requires exactly five sentences and makes the girl and dog central to every answer. That fits this screen but would conflict with many other task formats and subjects if applied unchanged. Transfer failure has not been measured. Carry this concrete generalization risk into POL-01/02 and the broader task-compliance audit.

The qualitative content review saw policies and official scores; it is not the blinded independent audit required by MEAS-01/02. No supplemental score, corrected ranking or held-out claim is created here. Local detailed evidence is `runs/reviews/rec04l-content-review.md`.

## Verification and preserved evidence

An offline reconstruction on a disposable copy returned a report exactly equal to the saved report. Socket connections were explicitly forbidden, and no model requests were made. The normal evaluator importer checked all three candidate exports, including prompt coverage, artifact/protocol hashes and numerical consistency. The real continuation ledger passes SQLite integrity checking, contains 51 completed operations and reconciles to the new-cost report.

The first nine exported answers exactly match the inherited replies in their original order. Their new semantic reference IDs do not occur as physical operations in the new ledger. The replacement ID does occur, with its original unknown reference retained. Shared financial totals equal both historical attempts plus the new continuation, without double charging inherited answers.

All files in the three actual run directories stayed unchanged during this verification: 4 original-attempt files, 152 completed-recovery files and 129 linked-continuation files. Both historical manifest/ledger seals still match the preserved originals. The authority file also stayed unchanged during the reconstruction. `runs/reviews/rec04l-verification.json` records the full file inventory, hashes, report and accounting snapshot; the independent accounting review is recorded separately.

The separate review reconstructed every new request fingerprint and checked receipt identity, token bounds and costs; all 51 request/outcome diagnostic pairs, unique client request IDs, three full candidate exports and 124 shared operation mirrors matched. It explains the new-call count as 21 generation, 3 partition, 26 quality and 1 proposal operation. All 287 reviewed input files, including both authority databases, stayed unchanged during that review. `runs/reviews/rec04l-independent.json` preserves its checks and seals. No accounting or lineage defect was found within this bounded scope.

The continuation preserves runtime SHA256 `ae05baf34c5bc2e69cf1b462a82d6412a827eaa000f577b7cbe1cfcc31f3e81b` in `runtime-source.zip`, with MIT notices, alongside the original source ZIP. Later source changes do not rewrite this experiment. Supplied seals and consistent receipts establish local evidence consistency; they are not independent provider authentication or invoice reconciliation.

No code changed and no new model calls were made to verify the live result. Next work is REC-05's inspection and recovery usability, followed by the calibration and controlled experiments already specified in the living plan.
