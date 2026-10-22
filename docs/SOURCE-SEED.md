# A starting file for inherited source experiments

`buddha.source_seed` composes the exact existing frozen generation recipe with
a small, versioned improvement procedure. The result is one self-contained
`candidate.py` containing both `generate` and `propose_improvement`. This is a
starter mechanism; it creates no experiment, owner, profile, allowance or live
command. [PLAN.md](PLAN.md) remains the roadmap.

## Pure factory

```python
compose_source_seed(frozen_seed_raw: bytes) -> bytes
```

The caller supplies the original file bytes. The factory accepts only literal
bytes matching SHA256
`2b87bfe0d3c97ee45db2d45260985ffe0234eca93967f4689fb7c59f82603921`,
checks UTF-8 and the 1 MiB ceiling, and returns that unchanged byte prefix,
two newlines and the fixed `FRAGMENT` string encoded as UTF-8. The complete
result must also fit in 1 MiB. Invalid input raises `SourceSeedError`.

`FRAGMENT_VERSION` is `buddha.source-seed-improver.v1`. Its prompt and parsing
behavior are part of the returned source. The factory performs no file access,
execution, imports of the old generation module, environment lookup or network
operation. Its supplied bytes are checked, not treated as executable input.

The original `agents/frozen_seed.py` is unchanged. Its generation function,
provider requests, history handling, literal placeholders and partial-response
handling remain unchanged in the composed file. Sampling mode, instructions,
models and allowances still come from the caller's existing configuration.
This factory does not choose history mode or strengthen generation instructions.

The selected file is self-contained in the existing standard-library runtime;
it does not import `agents/frozen_seed.py` at execution time. Archive its exact
composed bytes and configuration before a future experiment. A model-authored
child replaces the entire selected file. The host must never reattach the
original fragment to a child or substitute its own improver after a proposal.

## One proposal callback

The added function has the existing interface:

```python
propose_improvement(parent_bundle, development_feedback, config, complete)
```

It reuses the frozen recipe's JSON, task/configuration validation, request
construction and provider normalization helpers. The request includes the full
literal parent and the ordered development `{task, note}` records. The parent
inventory fingerprint is checked as a 64-character lowercase hash field; the
host remains responsible for joining it to the actual Selection and source.

Each task retains its original typed ID, prompt and count. Duplicate IDs,
invalid task/configuration fields, oversized notes and feedback exceeding the
existing 1 MiB escaped-JSON projection ceiling refuse before a callback. Notes
have the existing 4,096 UTF-8 byte bound. These checks do not authenticate
arbitrary note claims or replace the [measured feedback](SOURCE-FEEDBACK.md)
and [proposal-stage](SOURCE-PROPOSAL-STAGE.md) custody checks.

The improver makes exactly one callback. It requires the provider's normal
terminal status, then parses strict JSON with duplicate-key and nonfinite-value
rejection. Refusals, truncation, malformed replies, fenced text and callback
failures are not repaired or retried. The raw model response remains the
Gateway's evidence; a function failure may leave no returned proposal object.

A successful return contains only literal `source` and `hypothesis` strings:
a nonempty changed full source of at most 1 MiB, and a nonblank hypothesis of
at most 4,096 UTF-8 bytes. The normalized reply has a separate 8 MiB JSON bound.
Returned Python is data. Neither the factory nor the fragment compiles or
executes the proposed child. Invalid Python can therefore be returned and later
recorded as a checked execution failure by the existing confined route.

The fixed prompt asks for substantive procedure changes, preservation of both
entrypoints, literal-task priority, legal repetition in closed answer spaces,
and meaningful differences in causes, actions and consequences where allowed.
It supplies no task-specific answer or new benchmark rule. This wording does
not guarantee model compliance or prove a substantive change. Protected host,
model, evaluator, allocation and confinement guards remain authoritative.

## Verification and remaining gates

Fifteen new focused tests pass, including both providers and sampling modes,
exact legacy generation requests/answers, strict proposal parsing, terminal
status handling, callback failures and input/output boundaries. Fifteen original
frozen-seed regressions also pass. Two behavioral failures preceded the minimal
guards for an entrypoint string subclass and escaped Unicode projection size.
The initial missing-module failure is recorded separately as API/setup evidence.
The final stacked cohort passes 35 methods: those 30 plus five existing
screen-format regressions. Seven workflow quality checks pass at 207 Python
inputs and four configuration files. Strict static typing checks the factory
module; the embedded improver is checked by the runtime fixtures. The actual
trusted composed program also passes Ruff lint and formatting checks. Its
formatting preserves the frozen prefix and the complete program's syntax tree.
[Exact evidence and source cuts](conformance/src02-source-seed-delivery.json)
retain the earlier failures, independent review and final checks separately.

Unit fixtures execute only the trusted composed repository seed. They never
compile or execute model-returned child text. This slice runs no containers or
paid models and makes no full-suite or live-account claim.

The factory does not integrate a mutation-competence admission gate. Actual
confined child generation, the child's own improvement call and a runnable
grandchild remain necessary evidence for an inherited-source experiment.
Model authorship, useful-diversity gains and improved-improver effectiveness
remain separate claims. A future handoff must check the actual full-source
proposal size, output allowance, runtime, account/profile settings and budget;
the 1 MiB source ceiling is not a promise that any selected token cap can
reproduce that file.
