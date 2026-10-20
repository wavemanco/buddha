# MEAS-01 preparation review

This is an audit-pack preparation slice. MEAS-01 remains open for independent
review and explicit adjudication. The human sample belongs to the broader
scientific-evaluation gate. No new semantic labels,
official scores, rankings or regression gold cases were produced.

## Evidence and reproduced defects

| Boundary | Finding and correction |
| --- | --- |
| Rooted input selection | A real temporary-copy probe accepted `root/child/../../outside-controls.json`. Runnable controls/inventory cases then reached a guarded file open. Top-level inputs now reject parent traversal before I/O, as generation references already did. |
| Public identifiers | The initial validator silently collapsed duplicate item or answer IDs. Runnable failures now require globally unique public IDs before validating a response. |
| Exact provenance | Resealed temporary inventories with foreign answer run/candidate/prompt IDs propagated those values into the key. Tests also reproduced accepted source-row ID/protocol mismatches. Declared identities now agree across the candidate, answer record and consumed JSONL row. |
| Finite JSON | Valid JSON `1e999` became `Infinity` output which the helper itself rejected. Rule identities require text; output encoding refuses nonfinite numbers. |
| Shuffle purpose | Bandit flagged the deterministic presentation RNG. The local annotation explains its nonsecurity use; reproducible shuffle is not an access-control or secrecy mechanism. Existing security checks remain enabled. |
| Reviewer-facing schema | The first two submissions used `answer_ids`/`reason`: the instructions had not shown the validator's required `left`/`right`/`rationale` fields. Both originals were frozen. A versioned formatting clarification changed only those keys; corrected judgments were checked against the originals before acceptance. The shared guide now includes the exact example. |

The initial missing-helper import failed before implementation. The first fourteen
functional groups passed after implementation; this is not a claim that all their
behavioral assertions were observed failing beforehand. The four later groups
above had actual behavioral failures before their fixes. The first full-suite
attempt was stopped to annotate the RNG finding before starting the final run.
Its partial log is retained, not counted as a full pass.

The 913-test full suite passed before that final guide clarification. Afterward,
all eighteen focused groups passed again. The final proof checks that only the
`_GUIDE` literal changed in the helper AST and that only reviewer instructions
changed among its outputs. The pack, answer order, task text, official rule and
judgment form remain byte-identical. This is explicit verification scope, not a
claim that the full suite reran after the instruction-text change.

## What the checks establish

The focused fixtures preserve exact Unicode, whitespace, empty, refused and
duplicate answer strings. They check selected JSONL rows, hashes, pointers,
positions, complete populations, rule linkage, masking, replayable shuffling,
malformed input and typed rejection. Fixture build tests forbid file mutations,
source execution, credential lookup, network connections and subprocesses. The
final actual-data review records its own guard scope; the fixture and actual
guards are not assumed identical.

Submission checks require the selected pack digest, reviewer identity/type and
prior-exposure declaration, complete tentative groups, explicit uncertain pairs,
and separate per-answer compliance observations. Duplicate, unknown, missing or
malformed references fail. These checks neither evaluate reasons nor establish
independence, agreement, adjudication or semantic truth.

The [delivery record](meas01-pack-delivery.json) supplies final source pins,
local-suite and CI status. The [actual preparation review](meas01-pack-review.json)
records literal round trips, masking, output hashes and preservation evidence.
The [guide](../MEASUREMENT-AUDIT.md) explains commands and reviewer separation.

## Scientific limits

There are six complete historical sets, nine selected comparison cards and seven
authored controls: 22 items and 96 answer appearances. These cover one development
prompt plus separately authored controls. Repeated presentations and inherited
answers are not independent samples. Full sets preserve context; focused cards,
including cross-policy similarity, cannot replace an official within-set result.
Authored controls supply no measurement of a candidate policy on another task.

No official algorithms or scores change. Public reviewer order is not historical
first-occurrence order. Author intentions and earlier unblinded concern reports
are not gold labels. Metadata masking cannot prevent inference from writing style
or a reviewer seeking outside information. Only the reviewer folder is supplied;
the private key and prior reports stay separate until responses are frozen.

Input checks have declared per-file/population bounds, not a universal aggregate
memory/time guarantee or an atomic filesystem snapshot. No source program,
evaluator, archived runtime or model API runs to prepare the pack. No new financial
authorization, reconciliation, source evolution or scientific improvement claim
is introduced. Human-review arrangements and paid external judging, if chosen,
remain separate decisions.
