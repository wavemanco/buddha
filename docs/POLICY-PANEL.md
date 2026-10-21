# Prepare the policy-review mapping and packet

`buddha.policy_panel` fixes masked set and answer-position labels before any
generated answer is inspected. It uses the frozen study and reviewed metadata;
it does not consume answers, scores or review outcomes. [PLAN.md](PLAN.md) owns
scheduling, and the [comparison protocol](POLICY-COMPARISON.md) owns the scientific
contract.

Two interfaces keep preparation separate from saved answers. The existing
`plan_panel` helper creates the private mapping without reading generated text.
The new `buddha.policy_panel_read.materialize_panel` reader uses that frozen map
to assemble a reviewer packet from original saved generation. Neither conducts
reviews, creates funding, executes an agent or establishes live readiness.
Actual packet contents and supplemental reviews require saved generation; the
tested protected handoff and human scientific assessment remain separate.

## Which coordinates are fixed

The registered panel selects one task per original source category. Category
order assigns the generation repetition; it does not set the reviewer display
order. All four arms and every original answer position are included.

| Original category | Actual task ID | Generation repetition |
| --- | --- | --- |
| Creativity | string `curated-0` | 0 |
| Character & Entity Naming | string `curated-20` | 1 |
| Product & Purchase Recommendations | string `curated-33` | 0 |
| Subjective Rankings & Opinions | string `curated-47` | 1 |
| Factual Knowledge | string `curated-71` | 0 |
| Random Generation & Selection | string `curated-97` | 1 |

These six tasks, four arms and ten positions give **24 planned sets and 240
planned answer appearances**. The protocol's shorthand “IDs 0,20,...” refers to
these literal string IDs. Do not remove their prefix or replace them with numbers.
Judging occasions do not create more panel sets. A planned position says nothing
about whether generation has produced an answer there.

## Pure mapping interface and input checks

```python
plan_panel(
    study,
    *,
    intent_raw,
    expected_intent_sha256,
    source_review_raw,
    expected_source_review_sha256,
    expected_protocol_sha256,
)
```

This is a library interface, not an operator command. One call returns an
independent dictionary and writes nothing. It reads no files, environment
variables or keys, makes no provider calls, and spends no money.

The caller supplies a validated `PolicyStudy`, the original intent and source
review bytes, and trusted publication hashes. The helper checks the two byte
hashes before accepting their records; even a whitespace-only change fails the
original raw binding. It then uses the shared `policy_study.validate_intent`
check to match the complete study, release, selected tasks, policies, schedule
and derived identities. The protocol hash is compared with the intent; this
interface does not receive or read the protocol file itself.

The source review must match the study's dataset hash and cover its selected
tasks in order, with matching typed IDs, original categories and prompt hashes.
Panel entries must choose one selected task per source category, in the category
order of the original dataset, with the reviewed alternating repetitions and
consistent counts. Missing categories, changed identities, duplicate tasks,
invalid repetitions or inconsistent counts raise `PolicyPanelError`, a subtype
of `ReleaseError`. The helper does not rerun the source reviews or choose a
different representative.

Hashes establish identity relative to the caller's trusted inputs. They are not
signatures or proof of authenticity, prior publication time or permission to
spend. Jointly replacing the inputs and the caller's trusted hashes does not
preserve the original registration.

## Mask labels and rank conventions

Hash these exact vector shapes using the existing canonical JSON encoding:

```text
set:    ["pol02-panel-v1", task_id, arm_index, repeat]
answer: ["pol02-panel-v1", task_id, arm_index, repeat, position]
```

IDs retain their original type; arm, repetition and position are integers.
Canonical JSON uses compact separators, ASCII escaping and UTF-8 bytes, without
a trailing newline. Labels are the full 64-character lowercase SHA256 digest.
All sets are ordered by ascending digest; answers are ordered by ascending
digest within each set. Original positions start at zero, so this study uses
positions 0 through 9. Any repeated label, including a set/answer collision,
raises a typed error; labels are never shortened or silently replaced.

The protocol already fixes the hash vectors and requires masking before viewing
generated text. Ascending ranks, full lowercase labels, zero-based positions
and collision errors are **new prospective implementation clarifications** to
freeze with the mapping before outcomes. They do not change the frozen protocol
or intent bytes. No answer text, judge occasion, policy text, secret salt or new
identifier is added to the vectors.

## Output, privacy and limits

The returned format is `buddha.policy-panel-plan.v1`. It includes study/task
fingerprints, the supplied input pins, explicit rules, planned counts and sorted
sets. Each set records its mask, actual task ID, arm, generation repetition and
original scheduled cell. Its answer entries contain only masks and original
positions. The result contains no prompt or answer text, answer hashes,
availability flags, reviewer identities, official scores or costs. Editing the
returned dictionary does not change the input artifacts or a later result.

The full coordinate map is private host data and belongs in ignored local
storage. A tracked delivery can record its hash and conventions without giving
reviewers the map. Deterministic labels provide procedural masking, not secrecy:
someone who knows the public recipe and candidate coordinates can recompute
them. Keep the map and generation metadata out of reviewer and adjudicator
inputs; do not claim cryptographic blinding.

Input records and the returned canonical JSON are bounded at 32 MiB. More than
100,000 planned answer appearances is rejected before labels are expanded; the
helper never samples or truncates the panel. The registered study uses 240.

The pure mapping helper makes no generation-availability decisions. The saved
generation reader below supplies those bindings without changing the mapping.

## Materialize original saved generation

`materialize_panel` returns two separate dictionaries: `packet` for reviewers
and `private` for the host. It writes neither. It does not run producers or
judges, make provider calls, request keys, resume work or release held money.
This is another Python library interface; no operator command is added.

The reader checks the original study, generation settings, owners, seals and
shared accounting. A generation is usable once its complete C1 answer record
has its original completion seal and authority anchor. Later judging can have
failed or left an unknown request without making those original answers
unavailable. Final study/baseline publications and downstream judge caches are
not prerequisites for using that anchored generation.

Generation without a completion seal stays unavailable. The private receipt
distinguishes generation not prepared, not started and unsealed generation.
It retains every planned slot and position, without padding a partial set or
substituting another task, repetition or arm. Actual empty/refused effective
answers remain literal answers. Missing output is not an empty answer.

Contradictory anchored evidence is an error, not another missing slot. Examples
include a changed answer file, an authority completion anchor whose generation
seal has disappeared, or a retained funded owner whose original evidence is
missing. The reader raises `PolicyPanelReadError`, a subtype of `ReleaseError`,
and leaves the original records intact. It also validates retained generation
outside the smaller panel instead of silently discarding contradictory custody.

Old agent, controller and benchmark program identities are retained as hashes;
their original executable bytes are neither loaded nor run. Original data,
configuration, owners, seals and ledgers remain necessary. Validation can read
raw provider receipts while checking scheduled owners and shared accounting,
including later judging owners. It does not choose or omit answers using the
contents of official score artifacts. An unresolved later hold remains recorded
and does not turn the reader into permission to spend.

## Reviewer packet and private receipt

`packet` contains only its format, the fixed equivalence rule and rubric, and
complete available items. Each item has a masked set ID, the unchanged literal
task prompt and masked answer IDs with their literal text in the frozen order.
It contains no source coordinates, availability flags, planned coverage,
missing reasons, provenance, model metadata, scores or costs. Give reviewers
only this dictionary, never the combined return value.

`private` retains all planned sets and positions, including unavailable ones,
with their reasons, original coordinates and answer hashes where available.
It also retains original generation bindings, consumed-file/owner identities,
current shared accounting and the packet hash. Its coverage reports planned,
available and unavailable sets and positions. An empty or partial public packet
therefore does not erase missing work from the private denominator.

Private `status = complete` means that every planned panel set has an available
original generation. It does not mean that judging, reviews, the controlled
study or human assessment is complete. Keep this receipt and the original map
in private ignored storage, outside reviewer and adjudicator inputs.

## Materializer inputs and bounds

```python
materialize_panel(
    directory,
    *,
    intent,
    protocol,
    source_review,
    expected_intent_sha256,
    expected_protocol_sha256,
    expected_source_review_sha256,
    authorization,
    plan_raw,
    expected_plan_sha256,
    review_materials_raw,
    expected_review_materials_sha256,
)
```

The directory, intent, protocol, source-review and original authorization inputs
are explicit `Path` objects. The plan and review materials are original raw
bytes supplied with their trusted hashes. Unlike the pure planner, this reader
loads the protocol file and other retained evidence. It recomputes the plan from
the original study/publication inputs and requires the saved plan to match.

The caller supplies reviewed materials containing the fixed rule text/hash and
upstream revision, plus the fixed rubric text and its exact protocol byte range.
The reader checks their raw pin, release/protocol identities, rule hash and
literal rubric slice. Selecting the reviewed rule and rubric remains the
caller's responsibility; the reader does not extract or execute an official
parser. [The materials record](conformance/pol02-panel-review-materials.json)
contains these data for the registered study.
The official rule is reused under MIT; its full upstream notice is retained in
[the third-party notices](../THIRD_PARTY_NOTICES.md).

This reader supports the registered three-stage grouping, quality and summary
layout. Existing observation bounds apply: 10,000 tree entries, 1 GiB of captured
input bytes, bounded metadata/JSON and ledgers, and 100,000 recorded study
operations. The entire returned `packet` plus `private` record must fit the
32 MiB canonical JSON ceiling. Excess input/output is rejected rather than
silently sampled or truncated.

Consumed bytes and tree metadata are checked again before returning. Changing
evidence or an active SQLite journal prevents a stable observation. This is not
an atomic live snapshot, provider attestation or authentication that publication
preceded generation. Trusted pins establish identity, not timestamps or
authenticity.

The two fresh model reviews, masked adjudication, unresolved judgments, separate
unpriced subscription usage, approved funding and actual comparison remain
outside these interfaces. No review-completion, scientific-gain or human
validation claim follows from preparing a packet.

[Offline delivery](conformance/pol02-panel-materializer-delivery.json) and [retained adversarial findings](conformance/pol02-panel-materializer-review.json) record the implemented gate and its limits.
