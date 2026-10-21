# Controlled policy comparison: frozen structure

The next comparison asks two separate questions: do the child's instructions
help, and does seeing earlier answers help? `buddha.policy_study.PolicyStudy`
freezes that comparison's tasks, four conditions and repetition schedule before
execution. It constructs data only. It does not generate answers, judge them,
start a run, allocate money or authorize access to a task partition.

[PLAN.md](PLAN.md) remains the roadmap. This is an offline prerequisite within
POL-02; the controlled experiment and its scientific conclusions remain open.
The separate [execution controller](POLICY-EXECUTION.md) connects this artifact
to generation and fresh native judging; the data helper itself does not run it.

## The four conditions

Every condition uses the same explicitly chosen tasks, answer count, provider,
model and maximum output tokens per request.

| Arm index | Instructions | Sampling |
| --- | --- | --- |
| 0 | Empty | `regenerate`: each request starts without earlier answers |
| 1 | Empty | `in-context`: later requests include earlier answers |
| 2 | Exact frozen child text | `regenerate` |
| 3 | Exact frozen child text | `in-context` |

Only the two declared factors change. The child's original two-field policy is
preserved in the record, including its original sampling value. The four arms
deliberately test its instruction text under both sampling methods; the original
sampling value does not remove either condition. Child text must be nonblank so
that the instruction comparison does not collapse into the empty condition.

Instructions retain the existing limit of 4,000 Unicode characters, after valid
UTF-8 text is checked. They are not rewritten or specialized by this helper.
The provider is `openai` or `anthropic`; the model and positive per-request token
limit are explicit. These settings do not establish matched actual spending:
history changes input length, outputs vary, and all actual costs must later be
reported. Structural validity also does not establish task compliance or useful
diversity.

## Which tasks are eligible

The host supplies a complete C1 TaskSet and an explicit split bound to its exact
release and dataset digests. Every source task must occur exactly once in
development, validation or final, and every partition must be nonempty. The
host also supplies one declared family for every task. A family cannot cross
partitions. Prompts that become identical after whitespace normalization and
case folding cannot cross partitions either.

The selected IDs must be a nonempty, unique, explicitly ordered subset of
development. Integer `1` and string `"1"` remain different IDs; booleans cannot
stand in for integers. The helper preserves literal prompts, metadata in the
source artifact and the release's requested answer count. It works with
configured field names and counts, rather than assuming NoveltyBench 1.1's
schema or ten answers.

It rejects a source TaskSet that shows only part of the source population, even
though that view still retains the full dataset bytes. Otherwise a caller could
omit held-out IDs from the split's apparent universe. A reordered view containing
the entire population is allowed.

These are consistency checks. They do not discover semantic near-duplicates,
verify that a declared family is scientifically appropriate, authenticate the
upstream source, establish a representative sample or erase prior exposure to
public tasks. Membership, source/task strata and family decisions still need
review before a real study is frozen. This helper does not invent a split or
silently take the first sorted development IDs.

The full artifact and the selected TaskSet retain source data for the trusted
host. They must not be passed wholesale to a candidate or improver: the existing
generation boundary passes an individual authorized task instead. The schedule
contains identities and configuration, without task text or the dataset.

## Two different kinds of repetition

A **generation repetition** creates a fresh complete answer set for every
selected task in an arm. A **judging occasion** evaluates that same answer set
again, using fresh declared judging identities. It does not create more stories.

The contract requires 2–100 generation repetitions and 2–16 judging occasions.
These are structural bounds, not a recommendation that a particular study is
large enough. The caller supplies the complete execution order: every arm and
generation-repetition pair must appear exactly once. The helper does not choose
an order after seeing outcomes or quietly randomize it.

For example, two generation repetitions create eight scheduled cells across
the four arms. With three judging occasions, each cell identifies three future
evaluations of its same answer sets. Those occasions are not 24 independent
prompt samples, and they are not permission to retain only a favorable score.

This distinction responds to the [live audit](MEASUREMENT-LIVE-RESULTS.md): one
fixed ten-story set received partitions with 4, 5, 9 and 9 groups on separate
occasions. Generating again and judging again measure different sources of
variation. The [execution controller](POLICY-EXECUTION.md) preserves every
official result; an actual study still needs its analysis rule fixed before
observation.

An occasion ID here does not select a new display order or seed, change the
official evaluator, create a funding owner or ensure a fresh provider request.
Those require the composed controller and frozen instrument. Same-owner
recovery must reuse recorded replies; a genuinely fresh judging occasion needs
its own declared execution identity. There is no evaluation execution in this
module.

## Library interface and identities

`PolicyStudy.from_bytes(raw)` validates a bounded JSON record with format
`buddha.policy-study.v1`. Its fields are:

| Field | Purpose |
| --- | --- |
| `source` | Complete existing C1 TaskSet record |
| `split` | Exact release/dataset digests, three partition lists and full `{id, family}` declarations |
| `selected_ids` | Ordered development-only population for this comparison |
| `child_policy` | Exact `{instructions, sampling}` policy being tested |
| `generation` | Fixed `{provider, model, max_output_tokens}` access |
| `generation_repeats` | Number of fresh complete generation repetitions per arm |
| `judge_occasions` | Number of separately identified evaluations per generated set |
| `execution_order` | Explicit complete list of `{arm, repeat}` pairs, indexed from zero |

`to_bytes()` returns canonical JSON; `to_record()` returns a fresh mutable view.
`fingerprint()` hashes the frozen bytes. The `.tasks` property derives the
selected TaskSet; `.arms` returns the four policy/configuration records;
`.schedule()` returns the ordered cells and judging-occasion IDs. Editing a
returned view cannot change the frozen artifact or a later returned view.
Invalid data raises `PolicyStudyError`, a subtype of the existing `ReleaseError`.

An arm ID is the existing policy data's canonical JSON SHA256. A cell ID binds
the study fingerprint, arm ID and generation repetition under
`buddha.policy-study-cell.v1`; an occasion ID binds its cell and occasion index
under `buddha.policy-study-judgment.v1`. Changing the declared order changes the
study identity and its derived cell IDs. A digest provides consistency, not
proof that a caller had authority to run anything.

This module uses the existing release and answer artifacts. It imports no
legacy benchmark algorithms, policy controller, financial owner or provider
SDK. It reads no files, keys or environment variables and sends no requests.

## Offline check and remaining work

```powershell
python -B -W error::ResourceWarning -m unittest discover -s tests -p test_policy_study.py -v
```

Run this from the project folder in the current PowerShell window. It runs once
and prints checks of the frozen comparison structure, malformed data, task
separation and identities. It uses in-memory fixtures and a Python subprocess;
it needs no keys or Docker and spends nothing. Ctrl+C stops it.

The separate [native evaluation route](NATIVE-EVALUATION.md) now reuses anchored
generated answers for fresh full judging occasions and retains interruption and
partial-result evidence. This structure artifact does not execute that route.
The [composed controller](POLICY-EXECUTION.md) now connects those routes under
an existing study-scoped authority. The separate [actual comparison protocol](POLICY-COMPARISON.md) now declares
the twelve-task screen, exact child, official instrument, supplemental review
and analysis; its [intent](conformance/pol02-study-intent.json) reconstructs this
existing artifact without redistributing the raw corpus. Account/runtime and
funding checks, a tested handoff, passive analysis and live results remain open.
The original $50 experiment and $15 judge audit do not authorize this study.
The structure helper itself supplies no allocation or improvement result.
