# Completed pilot: concerns and next steps

Reviewed October 19, 2026, in `C:\Users\arvik\code\buddha`. This records all concerns identified in this review, including the earlier distinctiveness and interruption concerns. It covers all 30 completed stories, their three policies, partitions and quality scores, both runs' accounting, and selected search/provider/recovery paths. It is not an exhaustive security audit of the repository.

All findings are mapped into [the consolidated living plan](PLAN.md), which owns current order, status and dependencies. This review remains the evidence register.

**Conclusion:** the policy-search pipeline completed its live engineering check. Meaningful diversity and general improvement remain unestablished. Repeated plots occur in both the baseline and child, and partition errors can benefit both reported objectives. The interrupted attempt also needs an explicit continuation workflow before more paid execution.

The [evidence record](pilot-review-evidence.json) contains coverage, candidate identities, ten qualitative cases, original labels/scores, source/input hashes, offline fault-probe results and a clearly marked hypothetical arithmetic example. Qualitative findings are unblinded review judgments, not independently adjudicated labels. Original benchmark artifacts remain unchanged.

## What was reviewed and what passed

| Label | Policy | Responses read | Reported distinct | Reported utility |
| --- | --- | ---: | ---: | ---: |
| A | Independent seed, `2cad4fc7…` | 10 | 9 | 7.183935 |
| B | In-context seed, `68608e69…` | 10 | 10 | 7.480236 |
| C | Independent child, `34cecdbd…` | 10 | 10 | 8.567273 |

Answer references below are **1-based**, for example C3 means the child's third answer. The exact task was `Tell me a story in five sentences about a girl and her dog.` Shared girl/dog subject matter is required and earns no negative finding by itself.

All 30 stories were manually read and have five sentence-lines, with no obvious wholesale girl/dog or sentence-count failure. The completed report reconstructs exactly from cached receipts on a disposable copy using a transport that rejects network calls. Its 63 operations and $0.300153 recorded conservative cost reconcile; there are no outstanding recovery operations. All 63 diagnostic pairs bind to their ledger requests and record HTTP 200. The original ledger still matches its preserved hash, retaining nine completed replies and one unknown request.

These checks establish stored consistency and working execution for this case. They do not establish semantic correctness, external authenticity, invoice reconciliation, or general competence.

## Measurement and output concerns

### M1. Substantial plot repetition is broader than the original example

**Observed text and labels; equivalence remains an interpretive review judgment.**

| Cases | Repetition | What the reference judge recorded |
| --- | --- | --- |
| A1, A2, A5, A7 | Blue butterfly chase, dog disappears, pawprints lead to a lost juvenile animal, rescue/reunion. Animal/name substitutions and endings vary. | Only A2 and A7 share a class. A1 and A5 count separately. |
| A4, A6, A8 | Hidden door beneath an old oak, magical garden, changed reward or resolution. | Three separate classes. Shared premise is clear; complete-plot equivalence is less certain. |
| C3, C10 | Dog trained to find lost sounds, bridge, recovered music/instrument, restored sound. | Separate classes. This is a strong candidate for equivalence adjudication. |
| C1, C3, C4, C5, C7, C9, C10 | Seven of ten use hearing or recovering lost objects/sounds. | All count separately. This demonstrates premise concentration, not that all seven necessarily belong to one class. |
| A1 versus B1 | Butterfly, pawprints, lost fawn and reunion recur across policies. | Cross-policy repetition is outside official within-set distinctiveness. |

C6 and C8 are useful controls: both open with a dog sensing rain, but proceed to materially different fawn-rescue and garden stories. Shared names, subject or opening premise alone must not become an automatic duplicate rule. Likewise, different objects or endings alone should not automatically establish a new central plot.

Evidence: A [answers](../runs/first-live-recovery/candidates/2cad4fc7a6fa24def0c19d64d35eaff985c1770e1434084bfcdd6206077be525/evaluation/generations.jsonl) / [labels](../runs/first-live-recovery/candidates/2cad4fc7a6fa24def0c19d64d35eaff985c1770e1434084bfcdd6206077be525/evaluation/v1.1/partitions.jsonl); B [answers](../runs/first-live-recovery/candidates/68608e691190ffda9ea6c52f78d16fb9c67bca735201c9c91a880bdee48f7e06/evaluation/generations.jsonl); C [answers](../runs/first-live-recovery/candidates/34cecdbd8a9307796972dcc485641fc7021f97e8b2715a87feeb140ab54f424b/evaluation/generations.jsonl) / [labels](../runs/first-live-recovery/candidates/34cecdbd8a9307796972dcc485641fc7021f97e8b2715a87feeb140ab54f424b/evaluation/v1.1/partitions.jsonl).

### M2. Partition errors affect utility as well as distinctiveness

**Verified arithmetic dependency; material to interpreting the result.** Utility credits only the first answer of each judge-defined class. If equivalent answers are split into multiple classes, they receive extra utility credit too. Higher utility is therefore not independent reassurance about a questionable partition.

For illustration only, merging C3 and C10 while keeping every other class and first-answer score unchanged changes C from distinct **10** / utility **8.567273** to distinct **9** / utility **8.296620**. This is a hypothetical sensitivity calculation, not an accepted rescore. It does not reverse the observed ranking by itself, and it does not adjudicate the other questionable classes. A defensible comparison requires reviewing all candidates under the same rule.

Evidence: [evaluation.py](../buddha/evaluation.py), `score_sequence`, lines 109–141; [run.py](../buddha/run.py), lines 528–552; full numeric assumptions in the evidence JSON. Earlier wording that separated the utility increase from the diversity concern should be read with this coupling in mind.

### M3. Individual story quality also deserves review

**Observed passages; subjective craft concerns, not formal task failures.** A9 ends with thanks for finding a silver bell whose discovery was not narrated. C5 moves from a bell silencing birds to a restored forest without developing the reversal. C8's weather-sensing ability is decorative to its garden outcome. C2's flashlight-guided drifting drone lacks a clear navigation mechanism. Fantasy permits unusual mechanisms; these are questions about coherent development rather than demands for literal realism.

C's quality scores are `[9,8,9,8,8,9,9,8,9,9]`, while B receives only 7s and 8s. This pattern alone proves neither bias nor bad judging. There is no independent craft assessment or uncertainty estimate supporting those differences, and the quality judge evaluates each class representative in isolation rather than the set's plot range.

### M4. The metric's meaning and ceiling need to stay explicit

**Protocol limitation, not an arithmetic bug.** B and C both reach the maximum distinctiveness of ten, so their observed ranking is entirely through utility. NoveltyBench assesses functional difference within one answer set; it does not establish originality against other policies, literature, model training material, or all previous human work. The A1/B1 overlap is therefore evidence of generator concentration, not a violation of the within-set metric.

Keep official-reference scores and any stronger project criterion separately named and versioned. The user's assessment that the repetition is unacceptable is recorded as a project-level qualitative failure. Do not silently tighten the official prompt, overwrite the saved labels, or treat a new embedding distance as proof of meaningful novelty.

## Experiment and search concerns

| ID | Finding and evidence | Consequence / proposed response |
| --- | --- | --- |
| E1 | **One prompt, one answer set per policy, one proposal.** The manifest selects only `curated-0`; validation/final splits are unused. | The measured difference has no demonstrated stability, generalization or superiority over an alternative search method. Ten answers to one task are not ten independent evaluation tasks. Freeze varied development prompts and repeated occasions before comparative claims. |
| E2 | **No within-set history for C.** [search.py](../buddha/search.py), lines 396–402, passes prior answers only for `in-context`. The fixed proposer names the two sampling values but does not explain their memory semantics ([policy.py](../buddha/policy.py), lines 16–30). | A repeated instruction to choose an original premise cannot compare against the actual preceding outputs. This is a plausible contributor, not a proven isolated cause. Explain existing semantics and test the existing history mode before building a new diversity service. History can also anchor repetition. |
| E3 | **Limited feedback occasion.** The proposer sees the selected parent's full development rows, not both baselines; the weaker independent seed was selected through deliberate archive exploration ([search.py](../buddha/search.py), lines 435–460; [archive.py](../buddha/archive.py), lines 102–161). There is no second iteration to react to C. | The pilot does not demonstrate learning from C's failures or comparing all strategies. Richer feedback or additional iterations are new declared treatments, not interpretations of this run. |
| E4 | **Archive terminology can overstate progress.** Admission accepts a valid unique completed policy; the archive stores policy identity, ancestry and two scalar means. It has no independent semantic-behaviour test or promotion gate ([search.py](../buddha/search.py), lines 480–493; [archive.py](../buddha/archive.py), lines 16–23, 53–69). Exact policy hashes do not detect semantically equivalent rewrites. | “Admitted” is not “proved better”; the frontier inherits judge errors. Keep evaluation completion, numerical selection and independently supported improvement distinct in reports. |
| E5 | **Sampling and independence limits.** Generation, proposal and partitioning use the same configured model; quality uses a different model. There is one judgment per set/representative, no order-sensitivity audit and no independent rescore. The seed controls host selection/splits, not guaranteed remote generation determinism. | Correlated blind spots and stochastic variation are unmeasured risks, not established bias. Stored-receipt replay is exact; freshly calling the model need not reproduce it. Review blinded examples and later repeat declared generation/judging occasions. |
| E6 | **Coverage and leakage controls are limited.** The screen uses the first sorted development IDs; `families` is null. Splitting groups normalized exact duplicates, with optional supplied families, not semantic near-duplicates or task strata ([search.py](../buddha/search.py), lines 190–199; [splits.py](../buddha/splits.py), lines 1–8, 38–71). | A larger prefix is not automatically representative. Before broader testing, declare task coverage and inspect related prompt families without feeding final examples into optimization. |
| E7 | **Scaling has an already-paid failure point.** Proposer feedback is capped at 200,000 canonical JSON bytes, but larger screens are permitted ([policy.py](../buddha/policy.py), lines 107–120; [search.py](../buddha/search.py), lines 58–65). | Seed evaluation can spend money before the feedback-size failure is discovered. Define a versioned bounded feedback-extraction contract or feasibility gate before increasing screen size. Do not silently truncate. |
| E8 | **Current search space is deliberately narrow.** A policy changes instructions and one of two sampling modes; no generated source, learned weights or evolved improver is executed. | This satisfies the preliminary policy-search stage only. Make the evaluation signal credible before expanding to source self-modification; the original full-agent goal remains open. |

The source and model controls are in the completed [manifest](../runs/first-live-recovery/manifest.json); scores and selection are in [report.json](../runs/first-live-recovery/report.json). None of these limitations alone proves the child is worse. They bound what the pilot supports.

## Operational and provenance concerns

| ID | Finding and status | Required response |
| --- | --- | --- |
| O1 | **Combined funding is documentary.** Runtime code never reads `funding.json`; each ledger enforces only its own cap. The current $50 allocation relies on leaving the original inactive. | Before a third paid attempt, enforce one combined authorization and prevent duplicate allocations or spending through superseded attempts. Do not assume directory-local caps provide this. |
| O2 | **The original missing response is unrecovered.** Nine replies are preserved; the tenth has no receipt/request ID. Its request did not enable stored-completion retrieval. Exact resume requires authentic missing-response evidence. | Implement the requested linked continuation with explicit inherited receipts and a separately identified replacement request. Keep original uncertainty and liability. No continuation command exists yet; see [the incident review](FIRST-LIVE-REVIEW.md). |
| O3 | **Reproduced defect: a provably unsent failure becomes unknown.** Diagnostic request-file publication happens before HTTP construction, after the broker's dispatch event. Its failure is caught as uncertain paid work ([diagnostics.py](../buddha/diagnostics.py), lines 123–128; [provider.py](../buddha/provider.py), lines 395–405). The offline probe constructed zero HTTP connections yet retained an unknown operation and its $0.532373 reservation. | Add a trustworthy typed distinction for definitely-not-sent work or move required local preparation before dispatch. Test this through the broker, not only the transport. Preserve uncertainty whenever transmission is genuinely ambiguous. This defect did not cause the actual keyboard interruption. |
| O4 | **Reproduced guard-scope gap: a receiptless unknown does not block another operation ID.** `_check_halted` joins `unknown_receipts`; the original unknown has none ([ledger.py](../buddha/ledger.py), lines 189–194). A disposable-ledger probe successfully reserved/dispatched a different operation after such an unknown. | The normal search correctly stops when it reaches its original unknown operation, and the reservation still protects the dollar cap. A future continuation must explicitly enforce its stop/attempt policy rather than assume the broker globally halts all unknowns. Never use this gap to bypass review. |
| O5 | **Dead-writer review and summaries are incomplete.** A hard kill can leave `dispatched` plus a stale search lock; the observer reports pending/running without knowing whether a writer exists ([search.py](../buddha/search.py), lines 147–159; [progress.py](../buddha/progress.py), lines 159–168). The offline probe reproduced running/one pending with no writer. Also, the newest successful diagnostic outcome can suppress an older outstanding failure summary ([diagnostics.py](../buddha/diagnostics.py), lines 206–277). | Add an explicit review/doctor path and select diagnostic summaries from outstanding ledger operations. Require evidence before declaring a writer dead. Retain unknown liability; elapsed time is not proof of cancellation. Existing same-ID duplicate prevention and watcher unknown counts remain useful. |
| O6 | **Source hashes were not source preservation.** Frozen checks correctly reject changed core bytes, but the runs did not contain their source and the workspace has no Git history. The manifest also excludes CLI/progress/the actual diagnostic transport, though each request records its adapter hash. | Preservation is completed below. For new runs, bind the actual executable runtime and preserve those bytes. The 63 recorded adapter hashes match the current transport; no actual transport mismatch was observed. |
| O7 | **Inspection is not always read-only.** `search-inspect` acquires a lock, opens the writable ledger and can recreate derived artifacts ([search.py](../buddha/search.py), lines 576 onward). The watcher reads without writing, but is not a full scientific verifier. | Use disposable copies for reconstruction, as this review did. A later explicit read-only verification command would clarify the interface; it need not block the immediate semantic audit. |
| O8 | **Cost and status language need scope.** $0.300153 is recovery-only conservative accounting, not a provider invoice. Quality judging accounts for 95.25%; cost scaling is dominated by judging. Some design introduction text still described the pilot as pending after completion. | Report full experiment cost plus unresolved exposure, estimate judging before a larger run, and update status references to one authoritative checkpoint. The stale design introduction is corrected in this handoff. Historical checkpoint sections remain marked historical. |

Combined recorded known cost is **$0.301862**, with **$0.532373** unresolved allowance. The remaining original authorization is **$49.165765 and 55 new calls**. This is unallocated remainder, not an implemented new cap. Reusing the original nine replies leaves at most 55 calls to finish that pilot. The completed recovery is the same one-prompt pilot specification, not an unfinished full benchmark.

## Evidence preservation completed now

Saved [the matching runtime/test snapshot](snapshots/pilot-runtime-2026-10-19.zip), SHA256 `bd32c4d50339e2f2e1cadf01f5872fa3c1cdf12c196e7676a18d6fe96bd534e0`.

It contains 29 source/test/configuration/notice files plus `source-index.json`. Every bound core hash and controller hash matches both frozen manifests; ZIP integrity and each archived file hash were checked. It excludes environment values, credential files and run outputs. It is a local preservation copy, not Git history, an off-machine backup, or a validated sandbox. Future source changes can be developed separately without losing the bytes required to replay these receipts.

Both run directories, runtime files, manifests, ledgers and benchmark results remain unchanged. This review adds documentation, evidence and the source snapshot only. All diagnostic-failure and dead-writer probes used temporary ledgers with mocked or absent HTTP, never real keys or paid calls.

## Recommendations incorporated into the living plan

The review's recovery, calibration, controlled-comparison and evaluation recommendations now live in [PLAN.md](PLAN.md) as REC-01–05, MEAS-01/02, POL-01–03 and EVAL-01/02. That plan also retains original source self-modification and improver-evaluation work that a short pilot follow-up could omit. The numbered planning content was consolidated there; observed findings and verification above are unchanged. This report no longer maintains a separate work sequence.

No further live run or feature implementation was started by this review. The user's existing up-to-$50 authorization remains the total envelope; proposed experiments are not additional independent $50 allowances.

## Verification record

The evidence JSON records the exact offline fault-probe outcomes and hashes of 24 input artifacts plus all 13 runtime source files. Fresh verification for this checkpoint:

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | 245 tests passed in 18.940 seconds; mocked/canned model calls |
| Ruff lint and format check | Passed; 25 Python files formatted |
| Strict mypy | Passed; 13 runtime source files |
| Bandit | No issues; two existing narrow non-security RNG suppressions |
| `pip_audit --no-deps -r requirements.txt` | No known vulnerabilities; no third-party runtime dependencies |
| Python compilation | Passed |
| Evidence, source snapshot and report links | 24 artifact hashes, 13 runtime hashes, ZIP/index hashes, both frozen contracts and local report links validated |

A green regression suite does not negate the newly reproduced boundary gaps, which need targeted acceptance tests in the next implementation slice. No hosted CI or source-code commit is claimed.
