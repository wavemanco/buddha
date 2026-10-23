# Give an agent feedback from a verified development screen

The source improver can already receive development tasks and notes. This bridge
builds those notes from a specifically selected, complete [source screen](SOURCE-SCREEN.md).
It verifies the saved answers, official results, completion seals and accounting
before extracting anything. New packets include every selected output in full, in its original order. They do not replace outputs with excerpts or model-written summaries.

This is an offline library operation. It needs no API key, starts no worker and
spends nothing. The approved POL-02 comparison keeps its frozen handoff and
source code. [PLAN.md](PLAN.md) remains the roadmap.

`inspect_source_feedback(directory, expected_provenance_sha256=...)` verifies
an existing packet against its original measured screen and independent
provenance pin, without changing it. The builder and writer still require a new
directory. The [durable proposal stage](SOURCE-PROPOSAL-STAGE.md) uses this check
before preparing or executing the selected parent's inherited improver.

An optional `failure_history` adds version 4 host provenance for checked
materialized-child execution failures. Each entry pins the actual parent screen,
proposal and failed child screen, including the proposal's original measured
parent occasion. A different occasion for the same source cannot replace it.
Empty history uses version 3 full-output derivation. Historical version 1/2 packets keep their original derivation during inspection and replay. The worker still receives
the existing development-task and text-note format. [Source search](SOURCE-SEARCH.md)
explains which failures enter these notes, the full-output resource limits and the separate
incomplete states that stop execution.

## What the agent learns

For each selected development task, the note gives the recorded distinctiveness
and utility, the complete official grouping and available quality arrays, and every literal answer in full. Invalid or unavailable measurements remain
explicit. Empty answers, repetitions and weak answers stay visible. The bridge
does not invent a task-compliance judgment, a plot summary, a replacement grouping
or a new score.

Each note's recorded cost covers that task's original generation and native
assessment owners, including their retained attempts. It is copied from verified
owner totals in the pinned reports. It does not use the whole shared grant's
spending as the task's cost, estimate an invoice, or treat unknown charges as zero.

Grouping means the official evaluator's grouping of these answers. It is evidence
of what that evaluator decided on that occasion. It does not establish that the
answers have meaningful variety according to people. In particular, a shared
subject can be legitimate, while repeated central plots may deserve independent
review. This bridge preserves that distinction instead of silently changing the
benchmark.

Only the screen's selected development tasks enter the worker packet. The
complete source population and development/validation/final split remain on the
host. The improver receives the existing list of `{task, note}` records, where a
task contains its ID, prompt and requested answer count. Host provenance, paths,
the full dataset and evaluator settings are not passed through as notes.

## Saved records and their meaning

The writer creates a NEW directory containing four canonical JSON files:

| File | Purpose |
| --- | --- |
| `source.json` | The complete source TaskSet from the originally bound screen, for the existing host membership checks. |
| `split.json` | That screen's original split, for the existing development-only checks. |
| `feedback.json` | The `buddha.candidate-development-feedback.v2` packet accepted by the versioned improvement channel; legacy v1 remains readable. |
| `provenance.json` | The report reference, source/control identities, extraction policy and explicit omissions, retained on the host. |

The reference has exactly `directory`, `authorization` and `report_sha256`, like
the parent selector. The supplied hash pins the original raw report bytes.
Verification checks that report against its saved evidence; supplying a new hash
for altered scalar values does not turn them into valid measurements. A hash
identifies bytes, rather than proving who authored them or when.

The caller must bind the feedback, source, split and provenance bytes, the
improvement descriptor and required helper sources, including `source_feedback.py`,
into the original improvement owner before it runs. The generic session does not
automatically require this new helper or provenance file. Creating a packet does not allocate money, select a parent,
run an improvement or supply durable proposal recovery. The existing
[improvement guide](SOURCE-IMPROVEMENT.md) describes that separate operation.

The generic improvement interface still permits caller-reviewed notes. It does
not automatically require this bridge or validate an arbitrary note as an
official measurement. The bridge verifies the extraction when it builds the
packet; the caller's original input bindings must then prevent edits before
execution. The existing source controller enforces that connection for each original proposal owner. New source-search manifests v2/v3 select complete-output extraction; manifest v1 fixes historical prefix extraction even when reconstructing an iteration before its packet exists.

The writer validates the complete packet before creating its destination. An
existing directory is refused. A failure during writing retains the partial new
directory as evidence; it is never presented as a complete packet or overwritten
on retry. Choose a new destination after reviewing that failure.

## Current full-output contract

Provenance v3 (measurements) and v4 (measurements plus failed-child history)
retain every selected answer and diagnostic position. Empty answers, whitespace,
Unicode, control characters, repeated answers and late endings are preserved.
Every answer has zero omitted bytes. The inherited Python improvement function
receives the full notes; the default v2 starter includes them unchanged in its
actual provider request. Arbitrary evolved functions can choose their own use
of those inputs; receiving complete data does not prove good diagnosis.

The existing 1 MiB ceiling applies separately to the canonical escaped feedback
file and to the full task-and-note projection. A note may use that allowance;
there is no additional 4 KiB cap on the v2 channel. The detached host bundle
still has its 32 MiB ceiling. Exceeding a limit raises `SourceFeedbackTooLarge`
before writing the packet or preparing its proposal owner. Search records an
incomplete `feedback` stage with reason `feedback_capacity`; it does not shorten
answers or continue with a partial view. Earlier generation/evaluation spending
and original owners remain recorded.

Failure history keeps all measured parent outputs intact. It adds the complete
newest failed source and hypothesis, plus every checked failure's summary and
cost. Older failed-source text is not repeated; its hashes, lengths and omitted
bytes remain explicit. No answers are invented for a failed generation.

These byte ceilings are resource limits, not proof that a model's token context
fits. Verify the concrete parent, full feedback, request framing and output
headroom before any next live handoff. No reviewed model tokenizer/context
proof is supplied by this change. It neither funds a run nor changes the
completed first experiment or its limited historical feedback.

## Historical v1/v2 prefix contracts (replay only)

Feedback is an explicitly versioned optimization capability. The current bridge
supports the selected NoveltyBench 1.1 projection. A compatible new evaluator can
still run the unchanged agent and preserve native results through the existing
screen before a new feedback projection is implemented. Unsupported projections
are refused here, rather than guessed from opaque reports.

Legacy v1/v2 notes fit their original 4,096 UTF-8 byte ceiling. Both the feedback file and
the complete projected worker input, including task prompts, must fit 1 MiB.
The complete detached host bundle, including source, split and provenance, must
fit 32 MiB.
Truncation is deterministic and recorded; a complete saved answer remains in its
original C1 evidence even when only an excerpt fits the note. These are refusal
ceilings, not a maximum-size runtime or scientific feasibility guarantee.

The historical extraction policy shows the first ten answer positions in original
order. Each excerpt preserves whitespace and ends at a whole Unicode character;
it must fit both 64 UTF-8 bytes and 128 bytes as a canonical JSON string. Host
provenance records every original answer's position, full-text hash, byte length
and omitted bytes, including positions outside the displayed ten. The note also
states how many answers or diagnostic entries were omitted. This makes the
limited view explicit; it does not replace the complete source evidence.
The JSON ceiling includes quotes and escaping. Grouping and quality arrays also
show their first ten positions. Unusable quality entries appear as `null`, with
the original quality status in the note and unusable head positions in host
provenance. The original reports retain the complete diagnostic records.

This bridge accepts complete screens, including complete screens with unusable
metrics. Interrupted screens and failed proposals are not converted into measured
complete screens. The durable proposal stage now records clean rejections and
incomplete attempts separately. Using those failures alongside measured feedback,
repeated proposals, child screening and later parent selection is now connected by the inherited source controller. The earlier packet limits remain historical; current source competence gates stay in PLAN.md.
Changed-improver competence and improved-improver effectiveness remain separate
gates. No useful-diversity or held-out improvement claim follows from producing
this packet.

## Library functions and their effects

The public functions are in `buddha.source_feedback`:

```text
build_source_feedback(directory, *, reference, failure_history=()) -> dict
write_source_feedback(directory, *, reference, failure_history=()) -> dict
```

These are Python API signatures, not PowerShell commands. `directory` is an
absolute NEW destination beside the retained evidence, with an existing parent.
It must not be inside the original screen or selected component directories.

| Function | What it does |
| --- | --- |
| `build_source_feedback(...)` | Checks the pinned complete screen and returns the four proposed JSON records in memory. It creates no directory or files and makes no model calls. |
| `write_source_feedback(...)` | Performs those checks, exclusively writes the four records in the new directory, and returns pinned feedback/provenance file references after all writes finish. It makes no model calls and creates no spending owner. |

The builder addresses `feedback.json` to this exact destination. Moving the
files later requires a new, explicitly identified packet; do not edit its pinned
paths in place. Original input bindings fix the bytes used by a later improvement
operation. Running that operation still requires an approved runtime and an
existing approved Gateway spending allocation.

## Check this bridge offline

From the checkout containing this implementation:

```powershell
python -m unittest discover -s tests -p test_source_feedback.py -v
```

This runs the bridge's checks once in the current PowerShell window, using
temporary synthetic records and simulated workers/network responses. It needs
no key or paid call. Ctrl+C stops the foreground checks. These checks test the
engineering contract; they do not measure an agent's creative performance.

## Complete-output validation

Seventeen focused methods pass together in 419.6 seconds at 229 unchanged Python
inputs. They check full text and late endings, all answer positions, exact
empty/repeated/Unicode values, failed-child feedback, the framed host/worker
channel and the default starter's serialized requests for both providers. They
also check historical packet reconstruction and refusal before oversized
feedback is written or a proposal owner is created. The saved partial reason
reaches the launcher unchanged.

The [delivery record](conformance/src02-full-output-feedback-delivery.json)
binds the source hashes, final cohort, separate quality observations and earlier
unsuccessful checks. The initial full-text and answer-count checks genuinely
failed before the fix. Later adversarial checks exposed whole-input allocation
before refusal and a missing launcher stop reason; both are fixed. An earlier
39-method cohort was interrupted and is not reported as a complete pass.

These checks use fresh synthetic records and mocked workers/network responses;
they make no paid calls or changes to original run records. Local lint, format,
types, security, dependency and compilation checks pass at their recorded cuts.
This is focused engineering evidence, not a full repository regression,
hosted-CI result, vendor-context proof or improved creative performance.

## Historical bridge-delivery validation

This section retains the original feedback-bridge delivery's validation. The
later failure-aware feedback and composed loop have separate
[validation and limits](SOURCE-SEARCH.md#python-interface-and-present-scope).

Thirteen new methods pass across their recorded focused runs. The first cohort
also retained a large-artifact simulator failure; correcting the shared simulator
to emit the protocol's existing chunks lets the genuine oversized-worker-input
check reach the bridge and pass. A separate injected unsupported observation
first escaped the public source reader as an untyped exception. The shared reader
now returns its existing typed error, and both public-reader and bridge boundaries
pass. All 41 original generation/screening methods retain their assertions and
pass at the final sources. Seven quality checks pass at 193 unchanged Python
inputs. The [delivery record](conformance/src02-source-feedback-delivery.json)
keeps the individual pins and unsuccessful attempts; these were not one combined
final 13-method run or a full local repository regression.

A separate passive check builds four notes from two previously saved synthetic
screens, containing 40 literal answers, after their producer programs were
retired. All 221 original files remain unchanged; only eight new packet files are
written. No worker, network call or accounting write occurs. That proof ran at
its recorded sources before the later typed-error change.

At that original delivery, the unchanged improvement session accepted the generated packet and projected only
its selected tasks and notes in the host check. This slice does not run a fresh
improver worker with that packet or demonstrate a repeated search loop. Collection
finds 1,426 unique repository tests without executing their bodies; full hosted
Linux and Windows checks for this slice remain separate pending gates.

## Shared tests for both feedback versions

Full-output packets use worker protocol v2; retained prefix packets use worker
protocol v1. The common simulated-worker fixture now checks the exact version
from the session's validated feedback packet. A bound-packet regression exercises
both versions through real session custody with a simulated response. This keeps
legacy checks useful without requiring a new packet to impersonate the old
protocol. Production source and historical packets are unchanged by this
test-only repair. See the [compatibility delivery](conformance/src02-full-feedback-ci-compat-delivery.json)
for the original hosted failures, local reproduction and verification limits.

One older failure-feedback test also pins the historical v2/v1 extraction and
its 4 KiB note/excerpt limits. It now explicitly reconstructs that synthetic
historical packet and checks it through the real inspector. Every original
assertion stays intact; the public builders remain full-output only. The
prospective full-output failure-history path is checked separately.
