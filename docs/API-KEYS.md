# API keys and experiment budgets

The user authorized **up to US$50 for one first live experiment** on 2026-10-19. That is a combined cap across OpenAI and Anthropic, including seed candidates, proposals, generation and judging. It does not authorize repeated $50 experiments. The original and completed recovery attempts are historical evidence. The [living plan](PLAN.md) governs their linked continuation; do not restart either historical directory under a fresh allowance.

## Completed judge-audit allowance

The separate MEAS-02 audit was approved for **$15 total and 120 physical
attempt records** across 40 frozen judge targets. It completed all 40 targets
with 40 attempts, $0.032213 recorded cost and zero held.
[The results](MEASUREMENT-LIVE-RESULTS.md) retain its evidence and limits.
This allowance and the original $50 experiment are closed for new work; their
unused balances authorize no later experiment. Historical unknown charges and
holds retain their original records; closing a scope does not resolve them.

That audit used the verified Standard/default public OpenAI prices and only
an OpenAI project inference key. Its [historical handoff](MEASUREMENT-JUDGE-AUDIT.md#approved-15-live-audit)
explains one-session hidden entry and saved results. Local account review
stores only a fingerprint; account settings are manual assertions, not
evidence obtained from the provider API. A new live study needs its own
reviewed configuration, allocation and command.

## Completed policy comparison and proposed source experiment

POL-02 had its own approved **$50 shared cap and 4,096-attempt limit**. It
completed 960 answers and 192 task assessments with $14.459518 recorded cost
and zero held. [The results](POLICY-COMPARISON-RESULTS.md) preserve its evidence
and limitations. That scope is also closed for new work.

The [first source experiment](SOURCE-EXPERIMENT.md) currently proposes a new
**$25 / 512-attempt** shared cap. It is unallocated: no approval, grant, key
entry or paid execution has been created for it. The keyless configuration
check does not grant permission to spend. A separately reviewed funded launcher
and a clear local command are still required. Do not reuse a historical command
or an unused balance to start source evolution.

## Historical pilot: two dedicated keys

Create an application API key in a dedicated OpenAI project and an Anthropic key scoped to the intended workspace. Use ordinary inference credentials, not organization administration credentials. This implementation calls OpenAI Chat Completions for generation, partitioning and policy proposals, and Anthropic Messages for quality judging. The accounts need billing enabled and access to the configured reference models. ChatGPT/Codex access does not supply these credentials to Buddha.

Keep the keys in your password manager or secrets manager. Never paste them into a chat, issue, command argument, configuration, or source file. Official guidance: [OpenAI API authentication](https://developers.openai.com/api/reference/overview#authentication) and [Anthropic API key setup](https://platform.claude.com/docs/en/get-api-key). Use the providers' usage dashboards and any available spending controls as additional account-level protection; the local ledger does not control unrelated account traffic.

## Historical JSON-policy commands: hidden entry for one command

From a normal interactive PowerShell terminal in `C:\Users\arvik\code\buddha`, a new, reviewed run uses the following form. Set `$runPath` and `$authorizationPath` to the prepared run and its existing shared authorization database. A linked run must first be frozen and bound by `continuation-prepare`; it cannot use the generic binding command:

```powershell
python -m buddha search-run --run $runPath --live --prompt-keys --authorization $authorizationPath
```

The command prompts for missing `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` values without echoing them. Paste each key at its hidden prompt. The secrets are not part of the PowerShell command, so they do not enter command history. Entry fails if a usable terminal or hidden input is unavailable; it never falls back to echoed input. The host temporarily supplies prompted values through its own process environment, then restores the previous environment on exit, including failures. It creates no credential file and does not modify persistent user/system environment variables. Python strings and environment variables are process memory; this is not a promise of cryptographic memory wiping or isolation from other software running as your user.

No characters or asterisks appear during Python's hidden entry. Paste once, then press Enter. The updated CLI acknowledges the key name with `received`; this confirms local input, not successful provider authentication. After the last key it prints `Starting` and begins periodic progress updates. Observe a run from a separate terminal using `python -m buddha watch --run runs/first-live-recovery`. The watcher never requests keys or invokes models.

Existing nonempty environment values take precedence, so an invalid existing key needs to be removed or replaced in the launching terminal first. A baseline uses `run` with the same `--authorization` and `--prompt-keys` options. Authorization and runtime checks happen before any key prompt.

The completed policy comparison used its [dedicated handoff](POLICY-LAUNCH.md)
for OpenAI generation/grouping and Anthropic quality judging. Its historical
command does not launch the new Python source experiment. Source evolution
will have a separately reviewed handoff and command after its new allocation.

## Alternative: inject environment variables from a secret manager

The runner reads `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` from the environment of the process that launches it. Supply them through your secret manager if you already use one. Setting variables in a different PowerShell window does not update a running Codex process. The supplied `.env.example` has placeholders only; Buddha does not automatically load `.env` files. Avoid `setx` for temporary experiments because it persists credentials for future processes.

The trusted HTTP transport adds each key only to the appropriate authorization header for its fixed provider host. Keys are not inserted into model prompts, run manifests, provenance, or SQLite records. Historical JSON policies have no Python execution or tools. Source candidates execute Python only in the separate restricted runtime, without host files, credentials or direct network access. Arbitrary task/output text is retained as research evidence, so do not submit your own secrets as task content. The feedback guard does not detect arbitrary secrets inside text.

## Accounting and recovery

Preparation freezes the local cap into the run manifest. Live execution also requires one shared authorization database with immutable dollar/call limits, readable scope, sealed historical costs and new-run bindings. Each local operation transition and its shared accounting commit in the same attached SQLite transaction. Conservative context/output reservations occur before dispatch. Completed replies are replayed without a new request. Pending/unknown active requests block further shared dispatch; a narrow explicit continuation acceptance can retain the original historical unknown without releasing its liability. A budget stop may leave a partial candidate, which cannot enter the completed archive.

The shared cap covers its declared imported and bound runs and depends on verified provider model, token and maximum-rate bounds. Recorded charges are conservative calculations from returned usage, not provider invoices. Upstream rescoring, taxes, prepaid-credit purchases, old executable copies and unrelated provider traffic remain outside the current host guard. Creating another database does not grant new user authorization. Do not create new directories or authorities to bypass an interrupted or exhausted experiment. Check provider evidence before reconciling an unknown operation.

A required local request-preparation error now leaves an unsent `reserved` operation. Fix the local cause and resume that same run/operation; its original allocation and saved request UUID are reused. A request that reached transmission can remain `dispatched` or `unknown` and needs review instead. Elapsed time or a local diagnostic failure does not prove the original interrupted request was unsent.

Resume the same directory rather than preparing a new one. Offline inspection requires no credentials:

```powershell
python -m buddha authorization-inspect --authorization $authorizationPath
Get-Content runs/first-live-recovery/report.json
```

Revoke a key in its provider dashboard if it is exposed. For an active authorized policy run, replacing a key retains its completed replies; a new key does not reactivate a closed historical run. The native MEAS-02 audit binds the original key fingerprint: stop and review a credential-change procedure before resuming it. Do not edit or replace its saved account review to bypass that check. Changes to models, prompts, splits or budgets require a new experiment and a separately authorized spending decision.
