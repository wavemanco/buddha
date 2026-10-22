# Check a source experiment before allocating money

`buddha.source_handoff` checks the files and configuration proposed for an
initial source-search experiment. It reuses the existing source screen and
search validators. [PLAN.md](PLAN.md) remains the roadmap; this check is one
prerequisite for the future run handoff.

```python
check_source_handoff(path: Path, *, expected_sha256: str) -> dict
```

This is a Python library interface, not a PowerShell launch command. The caller
supplies the proposal filename and its separately reviewed raw-file SHA256.
The function reads and validates files, then returns a detached report. It
creates no files, grant, owner or spending record, requests no keys, starts no
container and makes no API calls. Invalid input raises `SourceHandoffError`.

## Proposal fields

A strict JSON object with format `buddha.source-handoff.v1` contains:

| Field | Meaning |
| --- | --- |
| `seed_screen` | Existing prospective `buddha.source-screen.v2`, including the complete source, split, ordered development tasks, generation/native selections, configurations and evaluator stages. |
| `proposal_template` | Existing five-field proposal configuration: `config`, `profile`, `max_callbacks`, `budget_microusd`, `max_calls`. |
| `spec` | Existing `buddha.source-search.v1` iteration, parent-selection, seed and active-pool bounds. |
| `expected_runtime_sha256` | Independently reviewed candidate-runtime record identity. |
| `source_sha256` | Absolute control-file names and their raw SHA256 hashes. It must include the independently derived installed helper closure and selected runtime record. |
| `requested_terms` | Proposed positive integer `budget_microusd` and `max_calls`, each at most the existing signed-64-bit limit. These are requests, not permission to spend. |

This initial-proposal format requires `candidate.py`, screen version 2 and no
starting lineage reference. It does not replace the existing search's recovery
or saved-descendant interfaces. A historical version-1 screen keeps its original
meaning. The selected benchmark release remains a separate configuration; this
checker contains no NoveltyBench judge or scoring algorithm.

Both generation and proposal configurations pass the same real validation used
before `prepare_source_search`. This checks selected component bytes, provider,
model and output-allowance agreement with their chosen host profiles, the
independently pinned candidate runtime, native configuration, artifact flow and
optional results projection. A proposal cannot silently adopt a different
runtime or model. The checker also verifies installed core identity and required
helper pins; unrelated supplied hashes cannot substitute for those inputs.

Control paths must be absolute and free of traversal, spelling aliases and
self-reference. Duplicate path aliases refuse. At most 1,023 control entries
leave one initial input slot for the proposal itself. Nested execution stages
add their own files, so this is not a guarantee that every possible schedule
fits the full preparation or storage envelope. That needs the actual handoff's
separate capacity check. No new arbitrary execution envelope is implied.

Selected components and every supplied control are checked again before return,
with control pins checked after the final component reads. Changes are rejected;
their new hashes are never adopted as reviewed expectations. As with the
existing file checks, this is no atomic filesystem lock or protection against
changes after the function returns. Later preparation and execution retain their
own original-input checks.

## What a passing report means

`status: configuration_checked` means configuration consistency at this check.
The result includes candidate, screen, comparison and search identities,
ordered task IDs, the maximum initial candidate-screen/stage-owner schedule,
the proposed terms and original reviewed bindings. Mutating the returned object
cannot alter the saved proposal or a subsequent check.

For `I` iterations, `T` tasks and `S` evaluator stages, the prospective ceilings
are `I + 1` candidate screens and `(I + 1) × T × (1 + S) + I` stage owners.
Rejected proposals, duplicate sources and stops can reduce actual work.
Recovery can run another worker against an original owner. An owner is neither
an API call nor a worker attempt; these ceilings are not cost or completion-time
estimates. Candidate callbacks and the original native evaluators still have
their separately declared limits.

The result always says `funding.status: unallocated`, with scope
`source screen: <comparison_key>`. No grant is inferred from the requested
numbers, a source hash or a passing report. Real provider access, current prices,
account settings, full-source token capacity, installed/running containers,
funding, practical latency/progress and protected live execution still need
their own checks. The check also supplies no mutation-competence admission gate,
semantic review, held-out result or scientific improvement claim.

## Verification

Twelve new methods and five existing source-screen/search methods pass in one
17-method cohort. They check read-only behavior with database, grant, worker
and provider access blocked; typed task order; detached results; strict JSON;
required original pins; profile/runtime mismatches; selected-source drift;
invalid terms/specifications; control-map bounds and aliases; and changes during
checking. An adversarial regression first reproduced a late control change
escaping the initial implementation. The final recheck order closes it.
The earlier missing-module setup error is separate from that behavioral failure.

Seven local quality checks pass at 210 unchanged Python inputs plus four tool,
workflow and dependency configurations: lint, formatting, strict types for
Windows and Linux, Bandit, dependency audit and compilation. Existing production
modules, tests and historical helpers remain unchanged. There is no new local
full-suite result or live-readiness claim. [The delivery record](conformance/src02-source-handoff-delivery.json)
retains exact sources, test IDs, the behavioral failure and final evidence.
