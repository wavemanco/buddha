# Assess saved answers from a Python candidate

`buddha.candidate_generation` anchors one completed source-candidate generation
so the existing native evaluator can assess its saved answers. The selected
Python runs in the separate [source runtime](SOURCE-RUNTIME.md); official
partition, quality and summary commands use their selected evaluator runtime.
The host supplies no replacement score or grouping formula.

This is a library route within SRC-02. [PLAN.md](PLAN.md) remains the roadmap.
It does not choose parents, run source search, admit candidates to an archive,
create funding or establish that a source change improves answers.
The separate [common development screen](SOURCE-SCREEN.md) now composes this route
over fixed development tasks and provides guarded exploratory parent eligibility
and selection. It does not complete the inherited source-search loop.

## Prepare and run the original producer

The existing [generation-v1 descriptor](SOURCE-CANDIDATES.md#what-the-host-freezes)
still selects one TaskSet task, one Python file, its configuration, executor,
profile, approved runtime and callback ceiling. The candidate keeps
`generate(task, config, complete)`. Zero, one or many callbacks can yield the
same answer count; ten answers do not imply ten requests. The host permits
`max_callbacks` from zero through 1,000 and preserves literal empty, duplicate,
poor and noncompliant answer strings.

```text
prepare_candidate_generation(
    directory, *, descriptor, selection, roots, authorization, review,
    budget_microusd, max_calls, expected_runtime_sha256,
    input_files=(), expected_input_hashes=None,
) -> Path
run_candidate_generation(directory, *, transport) -> dict
```

These are Python API signatures, not standalone operator commands. Preparation
validates the selected files and caller-supplied runtime hash, then writes a NEW
producer directory and original Gateway owner under an existing authorization.
It makes no model calls, reads no keys and grants no additional allocation.
The budget and call fields are local ceilings within that existing authority.

`run_candidate_generation` starts or recovers that original producer. It can
spend only the existing approved allocation through the explicitly supplied
transport, reviewed profile and local credentials. Candidate code never receives
the credentials. A nonpaying transport cannot dispatch a fresh paid request.

The runtime hash must come from the caller's review, separately from the
candidate descriptor. The host joins it to the original selected environment,
runtime artifact, image ID and image environment. Descriptor, TaskSet, runtime,
selected components and installed session/adapter/evidence helpers are bound to
the original owner before execution. Optional `input_files` bind additional
controls; `expected_input_hashes` preserves independently checked original hashes
through preparation and recovery. Changed bytes are refused, never silently
repinned.

## Producer records and completion

| Saved path | Meaning |
| --- | --- |
| `context.json` | Original descriptor path and externally supplied runtime hash. |
| `owners/0` | Dedicated original generation owner, requests, raw replies and accounting. |
| `attempts/0-N/report.json` | Actual candidate attempt and its status, identities, callback counters and execution evidence. |
| `attempts/0-N/answers.json` | Literal C1 answers when the candidate session completes successfully. |
| `completed/0.json` | Validated report/C1 inventory, sealed and independently anchored by owner deactivation. |
| `observations/N.json` | Retained incomplete explanation, actual owner/attempt and available generation report. |
| `report.json` | Successful anchored producer publication and its original accounting snapshot. |

A complete producer needs matching C1/report/source/configuration/runtime/task
identities, exact completed operation coverage, successful process exit and
confirmed removal of its owned worker. Its completed callback count must match
the original completed operations, independently of the answer count. A C1 file
alone does not prove completion. Stage sealing reuses the native pipeline but
has its own `buddha.candidate-generation-stage.v1` format and
`candidate generation completed: ` anchor domain; it is never labeled as a
frozen-seed generation.

Hashes, report joins and the local authority anchor establish consistency with
reviewed saved bytes. They do not authenticate an author, capture time, provider
statement, invoice or scientific judgment.

## Assess the same C1 on fresh occasions

Use the existing `prepare_evaluation(directory, descriptor=..., authorization=...,
review=..., input_files=(), expected_input_hashes=None)` and
`run_evaluation(directory, transport=...)` interfaces described in
[NATIVE-EVALUATION.md](NATIVE-EVALUATION.md). The evaluation descriptor retains
`buddha.native-evaluation.v1`, `native` and `stages`. Its `source_generation`
object instead has exactly these five fields:

| Field | Value |
| --- | --- |
| `format` | `buddha.candidate-generation-source.v1` |
| `generation_directory` | Absolute path to the original producer directory. |
| `stage_seal_sha256` | Raw SHA256 of original `completed/0.json`. |
| `owner_manifest_sha256` | Original owner's logical manifest digest, its `record_sha256`. |
| `owner_ledger_sha256` | Raw SHA256 of the original inactive owner's SQLite ledger file. |

The explicit format selects the source-candidate reader. The original untyped
frozen-baseline reference and its strict one-operation-per-answer contract remain
unchanged. Do not substitute a candidate report for a frozen-seed report.

Preparation passively checks original source evidence under the same shared
authorization, writes exact `Answers.native_bytes()` and creates the first NEW
native owner. It makes no model calls or generator invocation. Running can spend
only the existing allocation through its explicit transport. Each fresh occasion
gets distinct native owners and physical request identities; it judges the same
answers, not a regenerated set. Quality follows that occasion's own partition.
The final summary command has no model mapping and uses payment-disabled
transport. Official artifacts remain opaque, including any nonfinite summary
values; completed execution is not metric validity or promotion eligibility.

The C1 export file hash, canonical Answers identity and native-byte hash are
separate fields. Literal answer order, typed task ID and original row metadata
remain evidence. A new native selection must use the same release; its neutral
agent component is not mounted or executed and does not replace the original
C1's child identity.

## Recovery, replay and retirement

Recover the SAME producer or native occasion directory with its original owner,
configuration and controls. The controller chooses a new attempt directory;
callers do not replace owners to bypass old work. Received replies can replay
without another send. Unknown requests keep their holds and block shared new
spending; elapsed time does not release them. Original-prefix coverage prevents
an attempt from skipping earlier operations by making fewer callbacks.

Source stops retain the actual report when available and an incomplete
observation; Ctrl+C records cancellation and re-raises. A post-attempt protocol
failure retains available original evidence before a typed error. No terminal
report is invented when none was saved. `CandidateGenerationError` is the source
adapter's typed configuration/evidence error. A hard kill or disk failure can
still leave incomplete files or a retained foreground lock; inspect that state
rather than inferring safe recovery.

Completed producer replay uses the same saved seal/report, needs no keys or new
worker, and preserves its original accounting snapshot after other owners add
charges. It still constructs the original Gateway and therefore requires the
original selected component files and executing helper bytes to remain valid.

Passive native assessment is different. It reads original inactive owner,
manifest/ledger, authority mirror and anchor, context, descriptor, TaskSet,
runtime artifact, C1 and report without importing the retired candidate or
constructing its executing Gateway. Its selected agent and runner directories
may be retired while those required data/accounting records remain. The current
native components and reviewed consumer helpers must still be available for a
new assessment. Retirement is not deletion of the original evidence or permission
to execute drifted source. Existing native completion can replay keylessly
without generating or judging again.

## Validation status and limits

The existing source ceiling remains one UTF-8 Python file of at most 1 MiB.
The model channel remains limited to 32 MiB per frame and structural depth 64;
C1/native answer artifacts retain their 32 MiB JSON ceiling. Passive capture
observes at most 10,000 producer-tree entries and consumes at most 1 GiB total,
with 32 MiB ordinary reads and 512 MiB ledger reads. It refuses unstable or
oversized evidence. These guards are ceilings, not proof that a maximum-size
program, payload or callback schedule will complete within configured runtime
limits.

Current focused evidence comprises 20 new checks in 50.341 seconds and one
additional protocol-observation check in 1.514 seconds. The 37 existing
baseline/native checks pass in 184.784 seconds; their ignored wrapper emitted
ResourceWarnings, so this is not a warning-clean wrapper result. These are
separate focused cohorts, not a full regression.

The actual confined source-to-native [probe](conformance/src02-candidate-native-probe.py)
passes using the original materialized SRC53 child at
`parent-improvement-output/child/candidate.py`, source SHA256
`3f28e7b45ae45a23f5c70989e2e89a79d6bab5d213f9e9d70f00a5213334022f`.
Its original source lineage remains unchanged. The child makes one batch callback
to produce ten literal weak strings. Two fresh occasions run the pinned official
partition, score and summary commands in the native image. The second is prepared
and run after retiring the copied producer agent/runner directories, with original
C1/runtime/configuration/accounting evidence retained.

The observed total is 23 new synthetic HTTPS replies and eight removed owned
workers. Accounting contains seven productive owners and one unused, explicitly
deactivated zero-operation baseline scaffold; that scaffold starts no worker.
One quality attempt stops after the real
Gateway has durably completed a reply, through an injected host `RuntimeError`
and reported `ExecutorError`. Same-owner recovery retains that completed receipt
and adds no duplicate physical charge. This is not Ctrl+C or provider-uncertainty
evidence. The synthetic ledger records 115 microdollars spent and zero held.

Source replay before retirement and both completed native replays require zero
new calls or workers and preserve persistent fixture bytes/accounting and original
report snapshots after shared accounting grows. The two fresh occasions have
distinct owners/physical operations, equal configured scientific request-body
multisets and equal normalized sealed native artifacts. Singleton partitions and
score-seven replies are supplied controls, not semantic judgments or an
independent numerical oracle. Candidate and official source execute only in their
separate pinned images; there are no real provider calls or keys.

All seven final quality checks pass in 26.318 seconds with all 185 Python inputs
unchanged: lint, format, strict Linux and Windows typing, Bandit, runtime dependency
audit and compile. Published native-assessment regressions pass on both Linux
and Windows: 1,386 tests in 418.232 seconds with five existing skips on Linux, and
1,386 tests in 3,687.973 seconds with one existing skip on Windows. All six hosted
quality steps pass on both. No full local regression was claimed or substituted.
These results concern that native-assessment source, separately from the newer
screen's pending 1,413-test hosted regressions. See the
[delivery record](conformance/src02-native-assessment-delivery.json) for the pinned
evidence and its limits. No pending outcome is a pass.

This is observed composition with short control payloads, not maximum-size,
1,000-callback or arbitrary-recovery capacity. It narrows the single-task native
connection gap. Full SRC-02 stays open, POL-02 remains the sole Next, and the seven
major remaining leaves retain their existing gates in the living plan.

This route does not establish real provider access, semantic judge accuracy,
final eligibility, scientific promotion, source-search efficiency, model-authored
improvement, edited-improver competence or effectiveness. Common development
screening and exploratory admission now use the separately checked
[screen interface](SOURCE-SCREEN.md); they are not claims supplied by one native
occasion. Remaining gates stay in the living plan. This route creates no paid CLI,
allocation or actual experiment result.
