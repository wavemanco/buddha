# Run the approved Buddha and plain-model comparison

The user approved this study on October 26, 2026: **$150 combined OpenAI and
Anthropic API cap, with 16,384 recorded attempts**. Partial work is retained with
its stage, reason, costs and unresolved holds. The executing Python has passed
all eight Linux/Windows CI jobs and matches the checked source inventory.
[PLAN.md](PLAN.md) owns the wider roadmap.

| Allocation | USD cap | Attempt limit |
| --- | ---: | ---: |
| Buddha development | $40 | 4,096 |
| Buddha final assessment | $85 | 10,240 |
| Both plain-model references, shared | $25 | 2,048 |
| Unused validation | $0 | 0 |
| **Total** | **$150** | **16,384** |

The four grants start with zero spending, holds and attempts. The two plain
references share one grant; unused money cannot move between phase grants.
Earlier experiments remain closed. Recorded costs use conservative token-price
bounds and are not reconciled provider invoices.

## Start the run

Open a normal PowerShell window and run these two commands in order. The first
changes this window's working folder; it spends nothing. The second starts the
approved run once, can spend API money within the grants, and stays in this
window until it finishes or stops. No second window is required.

```powershell
cd C:\Users\arvik\code\buddha
python C:\Users\arvik\code\buddha\runs\reviews\unified-live-configuration\docs\conformance\unified-run.py --handoff C:\Users\arvik\code\buddha\runs\imp01-unified-comparison-20261026-v2\NOT-CREATED-unified-launch.json --sha256 2e426de93d64d94e5060ad3b233ca05c98343832c68cd857b4dbf0b6c0efb522 --live --prompt-keys --confirm-project-keys
```

The explicit Python-file path selects the checked implementation even if the
main project folder is on an older branch. The fingerprint selects the exact
funded handoff; changed inputs are refused. Some frozen internal names retain
`NOT-CREATED` from preparation; the launch records now exist and have been
checked.

The launcher checks configuration and funding before asking for keys. It asks
for missing OpenAI and Anthropic keys without showing their characters. Paste
each key once and press Enter; an acknowledgement confirms receipt. Existing
environment values skip the corresponding prompt. Use the reviewed
Standard/default public pay-as-you-go projects. The confirmation flag asserts
that these are those project keys. Do not send keys in chat.

OpenAI supplies generation, source proposals and the official distinctiveness
judge; Anthropic supplies the official utility judge and its fallback. Prompted
keys last only for this process and are not saved to the run or persistent
environment. [API-KEYS.md](API-KEYS.md) explains the boundary.

## What happens and what to send back

The fixed order is Buddha development and final assessment, plain independent
sampling, then plain in-context sampling. A stopped stage does not start its
successor. The study retains three development tasks, twenty-six final WildChat
tasks, sixteen descendant opportunities, at most 312 Buddha final sets and
fifty-two plain-reference sets. It uses unchanged official NoveltyBench 1.1.

Progress messages identify the phase and known accounting. Initial checks can
take time before key entry; model calls and isolated workers can also take
time. There is no measured full-grid completion-time estimate. This terminal
command does not conduct the later Codex or human reviews.

When the command ends, paste its final JSON message and any error text here,
without keys. The full outputs and accounting remain saved locally. A terminal
`complete` means the computational comparison finished; separate AI review and
any later human evidence still need their own reports. Partial or stopped work
does not become an improvement claim.

Press **Ctrl+C** to stop. The launcher retains completed work and attempts a new
partial observation. Resume with the same command and directories after any
reported blocker has been reviewed. Never delete or replace a grant, review,
lock or run directory to force another start. Unknown requests and retained
holds remain explicit and can stop further spending.

The immutable comparison is eventually saved under:

`C:\Users\arvik\code\buddha\runs\imp01-unified-comparison-20261026-v2\NOT-CREATED-unified-workspace\comparison.json`

Saved incomplete observations use that workspace's `observations` folder.

## Optional check without starting

This command checks the same handoff and original state once. It spends no
money, asks for no keys, creates no run owners or run records, needs no separate
window and exits by itself. It does not authenticate provider accounts. It can
also be run before resuming; share a stopped result rather than changing files.

```powershell
python C:\Users\arvik\code\buddha\runs\reviews\unified-live-configuration\docs\conformance\unified-run.py --handoff C:\Users\arvik\code\buddha\runs\imp01-unified-comparison-20261026-v2\NOT-CREATED-unified-launch.json --sha256 2e426de93d64d94e5060ad3b233ca05c98343832c68cd857b4dbf0b6c0efb522 --check
```

## Reviews after computation

The selected native setup is `gpt-6.1-sol` with `ultra` reasoning: at most
forty-four fresh reviewer contexts, comprising thirty-two target-review contexts
with up to sixty-four staged judgments, plus twelve whole-set contexts and
judgments. This uses unpriced Codex-plan capacity outside the API cap, with no
reviewer API fallback. No scientific reviewer has been launched during funding.

The [AI-only track](REVIEW-TRACKS.md) proceeds without waiting for people. The
parallel human extension uses the same frozen outputs; the project owner is
first selected reviewer and discloses relationship and actual prior exposure.
Actual human ratings add a separate report later without changing official
scores or the earlier AI report. No extra generation or official judging run is
needed for that extension.
