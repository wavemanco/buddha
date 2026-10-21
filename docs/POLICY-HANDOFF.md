# Check an unallocated policy proposal

`buddha.policy_handoff` checks that a proposed comparison, its reviewed documents
and its selected files agree. This happens before creating a run or supplying an
API key. [PLAN.md](PLAN.md) owns the current work order; the
[study protocol](POLICY-COMPARISON.md) owns the scientific comparison.

The result says **configuration checked** and **funding unallocated**. It
creates no spending authorization, enters no keys, starts no workers and makes
no provider calls. It writes no files; the caller receives an in-memory result.

## Library interface

`check_handoff(path, expected_sha256=...)` reads one proposal file and returns
its checked identities, planned counts, model profiles and original file
bindings. It raises `PolicyHandoffError` when the proposal fails a check.
This is a library interface; an operator launcher remains future work.

`expected_sha256` is the proposal's previously reviewed fingerprint, supplied
separately by the caller. A SHA256 fingerprint changes when file contents
change, including whitespace. Rewriting a proposal and its referenced documents
together cannot satisfy the old trusted fingerprint. Fingerprints establish
which bytes were checked; they do not authenticate who reviewed them or when.

## What the proposal contains

The format is `buddha.policy-handoff.v1`, with exactly these fields:

| Field | Meaning |
| --- | --- |
| `format` | Identifies this unallocated proposal format. |
| `study` | Absolute path and raw SHA256 of the existing frozen PolicyStudy. |
| `baseline` | Absolute path and raw SHA256 of the existing baseline template. Its tasks and first generation treatment must match the study. |
| `publications` | Path and raw SHA256 for each reviewed intent, protocol, source review, private panel plan and common review materials. |
| `source_sha256` | Absolute paths and expected hashes covering required installed host/helper/core sources, consumed configuration and publication files. Additional supplied controls are checked too. |
| `requested_terms` | Positive bounded `budget_microusd` and `max_calls` values being proposed, without an authorization ID or database. |

The five publication keys are `intent`, `protocol`, `source_review`,
`panel_plan` and `review_materials`. Each reference has exactly `path` and
`sha256`. Control paths must be unambiguous; aliases, traversal and proposal
self-reference in the source map are rejected. Existing regular-file checks
reject links, reparse points and hard-link aliases.

The checker reuses the controller's configuration join. It checks the complete
study, selected tasks, first treatment, source lineage and native stage flow.
It reconstructs the panel from the reviewed intent and source metadata, then
compares the saved plan. Common rule and rubric text must match the pinned
release and exact protocol slice. No answers or score results are needed.

## File inventories and model roles

The checker derives its required installed source set. Supplying hashes for an
arbitrary smaller list cannot replace a missing controller or helper. Raw
configuration hashes also cover files named by the template whose hashes are
not embedded there, such as the TaskSet and generation recipe.

The generation and evaluation selections each use complete
[component file inventories](BENCHMARK-INTEGRATION.md). Those inventories are
already inside the pinned baseline template. The checker verifies their actual
files and returns selection fingerprints and file counts separately.
Thousands of dependency files do not become thousands of invocation inputs.

The generator's provider, model and output cap must match its selected profile.
Native provider/model mappings must match their selected profiles too. These
checks use the configured roles; they introduce no new benchmark model names
or evaluator behavior.

Consumed control files, the proposal and both selections are rechecked before
success. A result remains a record of checked bytes. Later preparation must use
its original hashes and repeat the existing execution checks; elapsed time or
newly matching hashes do not authorize adopting changed inputs.

## What the result means

The detached `buddha.policy-handoff-check.v1` result contains:

- `status: configuration_checked`, with study/task fingerprints and planned
  task IDs, arms, cells, generation sets, answer counts, judging occasions and
  panel counts.
- `funding.status: unallocated`, the requested limits and exact study scope.
- Selected profiles and separate component selection fingerprints/file counts.
- `reviewed_bindings`, including the proposal itself and all checked control
  paths with their original hashes, bounded to 1,024 entries.
- Explicit limitations on access, pricing, funding and execution readiness.

A judging occasion is one evaluation pass over all selected tasks in one
scheduled cell. For the twelve-task protocol, eight cells and two occasions
mean sixteen such passes and 192 task assessments. The generation schedule
contains 96 ten-answer sets: 960 answers. These are different units.

The returned bindings fit the existing preparation input limit. The trusted
launcher will still need to combine them with the preparation owner's own
generated controls and respect the complete invocation limit.

## What remains before execution

Configuration consistency does not establish that every entrypoint or executor
field would pass the generation/native session constructors. Actual container
and mount checks, request compatibility, dispatch capacity, current price
bounds, credential/project review and provider access remain separate gates.
The result never says that a live run is ready or that funds were approved.

After funding approval, the execution route still requires an existing
authorization with the exact path, ID, terms and study scope. The
[study controller](POLICY-EXECUTION.md) retains that mandatory join; this checker
does not substitute a dummy grant or a partially valid execution descriptor.
The historical experiments' closed grants supply no new allocation.

The [cost envelope](POLICY-COMPARISON-COSTS.md) remains a proposal. A protected,
tested operator handoff is required before providing a live command. Actual
comparison outputs, blinded reviews and scientific conclusions remain open.
