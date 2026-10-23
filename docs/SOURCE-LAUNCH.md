# Launching a reviewed source experiment

This launcher connects the approved experiment to the existing source-search
controller. It does not create a budget or change NoveltyBench. The proposed
first source experiment now has its own approved allowance and
[concrete local command](SOURCE-FIRST-LIVE.md). This page explains the interface.

## What happens in the terminal

1. Buddha immediately announces that checks have started. It checks the exact
   launch file, proposal, approval, code, runtime, model settings and existing
   funding. These checks do not read keys or send provider requests.
2. If work already exists, Buddha checks its original owners and saved results.
   It refuses a different destination, altered treatment, inactive unfinished
   owner, retained lock or ambiguous dispatched request.
3. For unfinished execution, both live execution and the manual account
   confirmation must be explicit. Buddha then asks once for each missing
   provider key. Paste at the hidden prompt and press Enter. No characters
   appear. An existing process environment value is used without another prompt.
4. Buddha checks the keyed fingerprints and repeats the configuration/state
   checks. A change during key entry stops preparation. No third secret is
   required; see [keyed reviews](KEYED-REVIEWS.md).
5. A fresh run creates its reviewed record and original search owners. An
   existing run uses the same owners and requests. The existing controller
   generates answers, evaluates them through the official benchmark, proposes
   Python changes, screens children and saves its bounded history.

Progress continues while checks, preparation and execution take time. It pauses
during hidden key entry. Before funding is checked, accounting says unknown;
a temporarily unavailable snapshot is reported as unavailable. Neither means
zero spending. Progress is an observer and cannot dispatch requests.

## Commands and their functions

From the reviewed checkout, this optional command displays the available
options and exits. It spends no money, changes no run files, needs no separate
window and normally finishes immediately:

```powershell
python .\docs\conformance\src02-run.py --help
```

After a separate experiment approval, the handoff will supply actual paths and
the trusted hash for this command shape. The capitalized names below are
placeholders, not a ready-to-run command:

```powershell
python "REVIEWED-LAUNCHER-PATH" --handoff "APPROVED-LAUNCH-JSON" --sha256 "APPROVED-SHA256" --receipt "NEW-RECEIPT-JSON" --live --prompt-keys --confirm-project-keys
```

This runs the original approved search once and may spend money within its
existing shared cap. Run it in one ordinary PowerShell window with usable
hidden input; no second window is needed. It stays active until completion or
a stop. Press Ctrl+C to request cancellation. The supplied receipt path must
be a new file outside the search, selected inputs, review and funding records.

`--handoff` selects the launch file. `--sha256` is the independently reviewed
fingerprint of its exact bytes. `--receipt` saves the outcome of this invocation.
`--live` permits unfinished paid execution. `--prompt-keys` enables temporary
hidden key entry. `--confirm-project-keys` confirms the keys belong to the
manually reviewed accounts; it does not verify that assertion with a provider.

The command never creates or enlarges spending permission. Omitting live or
account confirmation stops an unfinished run before keys. A previously complete,
verified run can return its completed status without those flags or keys.

## Completion, interruption and another attempt

Each invocation requests a new receipt. A receipt describes this launch;
the original search observations, owners and accounting remain the evidence
for actual work. Do not overwrite an earlier receipt to make another attempt.
If the initial trusted hash or descriptor checks cannot establish safe receipt
exclusions, no receipt is written and the terminal says so. This prevents even
a failed check from adding files inside original evidence or selected inputs.

| Result | Meaning |
| --- | --- |
| `complete` | The bounded original search has its verified completed report |
| `incomplete` | The controller saved a partial observation, including its reason, iteration and stage |
| `stopped` | A launch gate refused further execution; the receipt identifies the phase and fixed reason |
| `cancelled` | Cancellation occurred; when the controller saved an observation, the receipt names that exact observation |

The process exits with code 0 for completion, 3 for a returned partial or known
stop, 2 for invalid launch/key input, and 130 for cancellation. These numbers
help scripts recognize the outcome; the printed result and receipt explain it.
If the separate launch receipt cannot be saved, Buddha says so. That failure
does not undo a request or erase the original controller records.

A reserved request has not been marked dispatched. The original request may
continue with its reviewed key after the checks pass. A completed reply can
replay without another charge. A dispatched or unknown request may already be
billed and is not automatically retried. A lock alone does not prove whether a
writer is alive or dead; the launcher never removes it. A changing tree or
database may prevent a stable check and produce a checking stop instead.

After a recoverable interruption, the eventual operator handoff will give the
same launch/hash and a new receipt path. Never create a replacement directory,
grant or review to evade retained work. An unanchored partial preparation stops
for investigation rather than being silently adopted.

## Engineering scope

The source launcher uses explicit account-review v2. Historical policy launches
retain v1 and their frozen executable identities. Shared path, read-only
accounting and progress helpers do not migrate historical owners.

The checker projects the exact initial generation invocation's control paths
against the existing 1,024-input boundary. That is not a full-schedule capacity
or cost guarantee. The first concrete experiment now has its
[full-schedule rehearsal](SOURCE-REHEARSAL.md) and a separately approved
[funded local handoff](SOURCE-FIRST-LIVE.md). Model-authored evolution and mutation-competence gates
also remain open in the [living plan](PLAN.md).

[The delivery record](conformance/src02-source-launch-delivery.json) records
57 scoped test methods and seven quality checks. The launcher rehearsal uses
synthetic provider replies and mocked workers. It verifies the real controller,
accounting and saved-owner path; it is not a new container or paid experiment.
Earlier failures and the separately changed, unexecuted receipt-test file in
one broad inventory remain explicit. Hosted full-suite CI is reported separately.
