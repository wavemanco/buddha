# Give an agent feedback from a verified development screen

The source improver can already receive development tasks and notes. This bridge
builds those notes from a specifically selected, complete [source screen](SOURCE-SCREEN.md).
It verifies the saved answers, official results, completion seals and accounting
before extracting anything. It does not ask a model to write a critique.

This is an offline library operation. It needs no API key, starts no worker and
spends nothing. The approved POL-02 comparison keeps its frozen handoff and
source code. [PLAN.md](PLAN.md) remains the roadmap.

`inspect_source_feedback(directory, expected_provenance_sha256=...)` verifies
an existing packet against its original measured screen and independent
provenance pin, without changing it. The builder and writer still require a new
directory. The [durable proposal stage](SOURCE-PROPOSAL-STAGE.md) uses this check
before preparing or executing the selected parent's inherited improver.

An optional `failure_history` adds version 2 host provenance for checked
materialized-child execution failures. Each entry pins the actual parent screen,
proposal and failed child screen, including the proposal's original measured
parent occasion. A different occasion for the same source cannot replace it.
Empty history keeps the original version 1 derivation. The worker still receives
the existing development-task and text-note format. [Source search](SOURCE-SEARCH.md)
explains which failures enter these notes, the excerpt limits and the separate
incomplete states that stop execution.

## What the agent learns

For each selected development task, the note gives the recorded distinctiveness
and utility, the official grouping and available quality information, and bounded
excerpts from the literal answers. Invalid or unavailable measurements remain
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
| `feedback.json` | The unchanged `buddha.candidate-development-feedback.v1` packet accepted by `CandidateSession`. |
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
execution. Enforcing that connection throughout repeated search is still the
controller's next integration step.

The writer validates the complete packet before creating its destination. An
existing directory is refused. A failure during writing retains the partial new
directory as evidence; it is never presented as a complete packet or overwritten
on retry. Choose a new destination after reviewing that failure.

## Limits

Feedback is an explicitly versioned optimization capability. The current bridge
supports the selected NoveltyBench 1.1 projection. A compatible new evaluator can
still run the unchanged agent and preserve native results through the existing
screen before a new feedback projection is implemented. Unsupported projections
are refused here, rather than guessed from opaque reports.

Notes must fit the existing 4,096 UTF-8 byte ceiling. Both the feedback file and
the complete projected worker input, including task prompts, must fit 1 MiB.
The complete detached host bundle, including source, split and provenance, must
fit 32 MiB.
Truncation is deterministic and recorded; a complete saved answer remains in its
original C1 evidence even when only an excerpt fits the note. These are refusal
ceilings, not a maximum-size runtime or scientific feasibility guarantee.

The fixed extraction policy shows the first ten answer positions in original
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
repeated proposals, child screening and later parent selection remains part of
the open inherited search loop under SRC-02.
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

## Validation at this slice

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

The unchanged improvement session accepts the generated packet and projects only
its selected tasks and notes in the host check. This slice does not run a fresh
improver worker with that packet or demonstrate a repeated search loop. Collection
finds 1,426 unique repository tests without executing their bodies; full hosted
Linux and Windows checks for this slice remain separate pending gates.
