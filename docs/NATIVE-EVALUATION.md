# Judge saved answers again without generating again

`buddha.native_evaluation` starts a new assessment of an already completed,
anchored generation. It reuses the literal saved answers, then runs the selected
native partition, quality and summary commands. It does not call the generator.
[PLAN.md](PLAN.md) remains the roadmap; this is an engineering prerequisite
within the controlled policy comparison, not a new measured comparison.

## Why this distinction matters

Generating again creates new answers. Judging again asks the evaluator to assess
the same answers on another occasion. Those measure different sources of
variation. In the [live audit](MEASUREMENT-LIVE-RESULTS.md), the same ten stories
received partitions with 4, 5, 9 and 9 groups. A second assessment must therefore
retain its own result, rather than overwrite the first or select the better one.

A new judging occasion has new accounting owners and physical request identities.
Recovering an interrupted occasion instead keeps its existing owners and reuses
their received replies. Reusing those replies avoids paying for the same
operation twice; it does not supply a fresh judge decision.

For a complete new assessment, quality scoring must follow that occasion's own
partition. Repeating only grouping and retaining quality scores based on an older
partition would mix different assessments. The official commands and their
summary remain authoritative; the host supplies no alternative grouping rule,
benchmark formula or corrected ranking.

## What the host verifies

The source must be a completed generation from the existing native baseline
format. Its original generation owner must be inactive and independently
anchored to its stage-completion digest in the same shared authorization used
for the new occasion. All original physical operations must be completed.

The host joins the exact stage seal, attempt inventory, C1 answer file, generation
report, task source, configuration, selection, original invocation inputs and
recorded accounting. The source owner's stored runtime identity must match its
original manifest. It checks literal answer bytes and typed task membership;
integer `1` and string `"1"` remain different IDs. Missing, duplicate or foreign
result rows block later stages.

These checks read original data. They neither import the retired producer's
program nor reconstruct an executing Gateway for it. Its program/component
directories may have been retired, provided the required original data and
accounting records remain. A new evaluator selection may contain a different
neutral agent inventory: it is neither mounted nor executed. The saved C1's
agent identity is still checked against the original producer selection.

The new evaluator must use the C1's release. Changing release/schema requires
the separate [upgrade compatibility work](RELEASE-UPGRADES.md), rather than
silently relabeling old answers. Commands, artifact paths, field names, answer
count, hooks and installed environment come from the selected release and its
configuration. This controller has no NoveltyBench-version branch.

Saved-file consistency is not provider attestation, semantic correctness or
proof of statistical independence. The trusted host, local filesystem,
authorization database and reviewed container/OS boundaries remain assumptions.

## Library interface

| Function | Purpose |
| --- | --- |
| `prepare_evaluation(directory, descriptor=..., authorization=..., review=...)` | Check the original generation and new configuration, create a fresh occasion directory and prepare its first native owner. Reads no keys and makes no provider calls. |
| `run_evaluation(directory, transport=...)` | Run or resume that occasion through its original owners, retaining replies, attempts and incomplete-result explanations. Actual paid work still requires active authority, reviewed profiles, a paid transport and locally supplied keys. |

Preparation also accepts optional `input_files`: a bounded list or tuple of
additional control-file Paths. Their original hashes are bound to the first
owner and inherited by later owners, including on recovery. Callers need not
resupply them when resuming. The [policy controller](POLICY-EXECUTION.md) uses
this existing provenance boundary to bind the whole frozen study.

These are library interfaces. This slice supplies no new paid CLI command,
funding allocation or actual study membership. The historical $50 experiment
and $15 judge audit do not authorize another comparison.

The descriptor has format `buddha.native-evaluation.v1` and these fields:

| Field | Meaning |
| --- | --- |
| `source_generation.baseline_directory` | Absolute path to the original baseline data directory. |
| `source_generation.stage_seal_sha256` | SHA256 of its original `completed/0.json` file. |
| `source_generation.owner_manifest_sha256` | Original generation owner's logical manifest digest, its `record_sha256`. |
| `source_generation.owner_ledger_sha256` | SHA256 of the inactive original generation owner's SQLite ledger file. |
| `native` | Existing native selection, component roots, installed inventory, hooks, executor settings, model profiles and local ceilings, as in the baseline descriptor. |
| `stages` | One configured input/output/model-permission entry per native release command, as in the baseline descriptor. |

The exported C1 file digest, canonical Answers fingerprint and native-byte digest
are different identities. The producer's trailing newline belongs to its file
identity; it does not alter the canonical Answers identity. The new occasion
materializes exactly `Answers.native_bytes()` and preserves literal weak answers,
source metadata and ordering.

The final native command has an empty model mapping and a separate transport
with payment disabled. Both apply even when the release has only one native
command. An attempted model request from that command cannot reach paid HTTPS.
Its summary remains opaque bytes, including any native `NaN`; successful
execution does not establish valid scientific metrics or promotion eligibility.

## Records, recovery and incomplete results

| Location in the occasion directory | Meaning |
| --- | --- |
| `context.json` | Frozen pointer to the evaluation descriptor. |
| `owners/1`, `owners/2`, … | Native-stage owners; there is no new generation owner `0`. |
| `attempts/<stage>-<attempt>` | Actual session attempts, raw evidence and partial/native artifacts. |
| `completed/<stage>.json` | Output/report inventory sealed after validation and anchored by owner deactivation. |
| `native-answers.jsonl` | Exact native input derived from the original C1. |
| `staging/<stage>` | Configured inputs supplied to that native command. |
| `observations/<number>.json` | Preserved incomplete-result explanation from an execution stop. |
| `report.json` | Successful whole-occasion publication, referencing its own native summary and stages. |

An incomplete observation records its reason, stopped stage, real owner, actual
attempt when one exists, prior native reports and an observed authorization
snapshot. Reasons distinguish unknown liability, insufficient authority, protocol
failure, cancellation and native failure. A coverage failure after a received
reply records a protocol stop before raising a typed error. Ctrl+C records the
actual interrupted attempt and then propagates the interruption. If the native
session had not written a report, the host does not invent one.

Invalid source/preparation evidence is a typed `EvaluationError`. A changed
already-completed seal is likewise invalid evidence, rather than a funding stop
or a new assessment result. The original complete report remains retained. These
records do not promise successful journaling through arbitrary disk failure or
an abrupt process kill.

Recovery keeps the original owners and physical operations. Known received
replies can be replayed without another send; unknown/dispatched requests retain
their holds and block further spending across the shared authorization. The
controller does not release money, create replacement owners or infer safety
from elapsed time. Existing unanchored seals remain a refusal to resume, with
their evidence preserved.

Only one process can run an occasion at a time. Normal exceptions and Ctrl+C
release its foreground lock. A hard kill may leave `running.lock`; the host
does not guess that another writer is dead. The
[doctor's observation limits](DOCTOR.md) still apply.

## Shared accounting and completed replay

The new route and the prospective baseline share native-stage validation,
sealing and complete-report publication in `buddha.native_pipeline`. This is an
intentional new baseline source revision. Original executing source pins, owners
and historical delivery records remain unchanged.

The authorization snapshot in a completed report describes what accounting
looked like at completion. Other legitimate owners can later add charges to the
same authorization. That must not make an older completed report fail replay or
rewrite its snapshot with newer totals. The shared publisher verifies the
reconstructed scientific/stage evidence, fixed terms, typed financial arithmetic,
compatible owner population and completed owners, then preserves the original
report bytes. Current authority still controls any new dispatch.

A saved snapshot must also contain at least the events needed to create its
authorization and register its known owners. A claim of zero events with existing
owners is rejected; this still does not authenticate the historical capture time.

This fixes an offline-reproduced baseline replay failure: completing a second
baseline on the same grant made replay of the first reject its changed global
authorization totals, despite no change to its own result or stages. The check
does not authenticate when a top-level snapshot was captured. Reserved money
can decrease when holds settle, so it is not treated as a monotonically rising
counter. No new financial schema or historical record migration is introduced.

## Offline check

```powershell
python -B -W error::ResourceWarning -m unittest discover -s tests -p test_native_evaluation.py -v
```

Run this once from the project folder in the current PowerShell window. It checks
fresh judging versus recovery, literal-source validation, accounting stops,
incomplete records and the unpaid final command using temporary files, fake keys
and mocked containers/HTTPS. It needs no Docker or API keys, makes no real calls
and spends nothing. It writes only its temporary fixtures; Ctrl+C stops it.

The separate engineering proof also runs a producer and consumer in different
Python processes, with the copied producer's program paths retired. That proves
the data-only dependency within its declared synthetic scope. It is not a new
model judgment or scientific replication. Actual study membership, instrument,
funding, a composed comparison controller and predeclared analysis remain open
in the single living plan.

The [actual native composition proof](conformance/pol02-native-evaluation-evidence.json)
runs a genuine fixed-seed baseline and two fresh complete judging occasions in
the reviewed containers. All 38 physical HTTPS requests use synthetic replies.
The native artifacts and scientific request bodies match across occasions; an
interrupted quality stage resumes its original receipts. Completed replay of
all three routes adds no worker executions or sends, preserves original report
snapshots after shared-accounting advances, and leaves no new owned container.
This is engineering evidence, with no real model judgments or paid calls. The
[review evidence](conformance/pol02-native-evaluation-review.json) retains
retirement checks, malformed-publication cases and the reproduced failures.
