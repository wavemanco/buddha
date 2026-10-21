# Prepare the private policy-review mapping

`buddha.policy_panel` fixes masked set and answer-position labels before any
generated answer is inspected. It uses the frozen study and reviewed metadata;
it does not consume answers, scores or review outcomes. [PLAN.md](PLAN.md) owns
scheduling, and the [comparison protocol](POLICY-COMPARISON.md) owns the scientific
contract.

This slice supplies the pre-answer mapping only. It does not materialize a
reviewer packet, conduct reviews, create funding or establish live readiness.
The packet materializer and tested protected handoff remain open. The actual
answer packet and supplemental reviews follow real saved generation; the human
scientific assessment remains separate.

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

## Python interface and input checks

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

The later materializer must bind these fixed positions to the original saved
generation and preserve missing panel slots without substituting another task,
repetition or arm. A partial generation must not be padded into a complete
review set. Actual empty/refused effective answers stay literal answers.
Those bindings and availability decisions are not made by this mapping helper.
The two fresh model reviews, masked adjudication, unresolved judgments, separate
unpriced subscription usage, approved funding and actual comparison remain
outside this slice. No scientific gain or human-validation claim follows from
creating a map.
