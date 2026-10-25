# Check a proposed matched study without starting it

This is the configuration check for a fresh matched-improver handoff. It uses
the existing study v4 and assessment v4 validators. [PLAN.md](PLAN.md) owns the
remaining work; this interface neither funds nor launches an experiment.

`buddha.improver_handoff.check_improver_handoff` takes a proposal file and the
independently reviewed SHA-256 fingerprint of that file. It reads the declared
inputs, checks their bindings and returns a detached configuration summary.
It writes no files, asks for no keys, opens no SQL database, starts no container
and makes no provider request. There is no new command to run yet.

## Proposal fields

The proposal has exactly these five fields:

| Field | Meaning |
| --- | --- |
| `format` | `buddha.improver-handoff.v1`. |
| `assessment` | Absolute `path` and `sha256` of the assessment v4 declaration. That declaration binds the development study, complete task source, custody, numerical plan and rule. |
| `expected_runtime_sha256` | Independently reviewed runtime fingerprint used by both controllers. |
| `directory` | Canonical absolute path for a new trial, with an existing parent. Existing destinations and overlaps with declared controls or selected components are refused. |
| `source_sha256` | Canonical absolute file paths and hashes for every required installed helper, plus any additional reviewed controls. Aliases, a reference to the proposal itself and more than 1,023 entries are refused. |

## What is checked

The check preserves the complete proposed grid, exact starting agents and fixed
improvers, official evaluator, model/profile settings, source inventories and
separate phase limits. It verifies selected files as bytes without decoding,
parsing, importing, compiling or executing selected Python. Trusted validators
execute normally; JSON configuration is parsed normally.

The existing development and final file-input capacity checks project known
future paths without opening nonexistent files. Component inventories, original
controls, the proposal and destination safety are checked again before success.
Distinct final-generation and evaluator folders are protected alongside the
development components. A changed or malformed input
raises `ImproverHandoffError`; it does not produce a partially approved handoff.
These are read-only consistency checks, not an atomic snapshot or a promise that
files cannot change later. Funded preparation must check the original inputs again.

The result says `configuration_checked` and funding `unallocated`. The limits
come from the declared assessment, and totals are their sum; neither grants
spending permission. The existing v4 contract requires two spending phases and
a separate unused-validation authority with zero dollars and zero attempts.
This check creates none of those authorities.

## What the result does not establish

It does not inspect a retained trial, authorize recovery, prove that Docker or
accounts are available, verify current prices, predict the bill or establish
full-grid runtime. The original-call capacity policy still measures actual
future proposals before child work; configuration checks do not guarantee that
those requests will be accepted or produce usable changes.

A funded launcher still needs its approved outer controls connected to original
trial owners, checks of retained partial state before key entry, phase-aware
progress and receipts, and three grants issued for this new study's approved
scope: search, zero validation and final. Those are separate from
this fresh, read-only configuration check. Scientific review, effectiveness and
generalization remain separate claims. Earlier studies and handoff formats stay
unchanged.
