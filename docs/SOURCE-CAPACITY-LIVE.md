# Approved $7 full-output capacity observation

**Ready to run once.** The copied executing code passes its exact Linux and
Windows CI checks. The dedicated $7, one-attempt allocation and the actual
keyless handoff check pass; an independent read-only review confirms zero
owners, attempts, spending and holds before launch. The [handoff record](conformance/src02-capacity-funded-handoff.json)
retains those checks. The earlier unfunded approval checkpoint remains history.

This sends one OpenAI request containing the complete retained feedback. It
saves actual usage and checks whether the reply supplies complete changed Python
text with the declared input and output room. The returned code stays text:
this command does not execute it, generate benchmark answers or judge them.
The historical measurements remain attached to their original parent.

## Run this command

Use one normal PowerShell window. You can use your current window or open a
new one; no second window or project-folder change is needed for this absolute
command. It uses the frozen local code copy, independently of your checkout's
current branch.

```powershell
python -I -B C:\Users\arvik\code\buddha\runs\src02-capacity-20261023-handoff-v1\code\docs\conformance\src02-capacity-run.py --handoff C:\Users\arvik\code\buddha\runs\src02-capacity-20261023-handoff-v1\handoff.json --expected-sha256 e1b0bf24be746447549786eefa1c73a97da3f7f59dbb3f1bbc27541639a3d0ba --live --prompt-keys --confirm-project-key
```

This runs once and can spend within the **$7 total cap and one physical-attempt
limit**. The maximum reservation is $6.315672; a reservation is money held
against the limit, not a bill. Earlier experiment balances do not fund it.

`--prompt-keys` asks for the OpenAI key locally if this window does not already
have one. Paste it at the hidden prompt and press Enter; characters will not
appear. No Anthropic key is needed. Never put a key in this command or chat.
`--confirm-project-key` confirms that the supplied key belongs to the project
whose Standard/default processing and public prices you already verified.
`--live` permits this paid request. The hash checks the exact approved handoff;
`-I -B` isolates Python's import settings and avoids writing bytecode caches.

Allow several minutes. Progress appears about every ten seconds. The network
timeout is 180 seconds; a timeout can leave the external request's billing
unknown. Ctrl+C stops the foreground command and retains already recorded
evidence. Do not delete locks or restart an unknown request automatically.

## After it finishes

Paste the final console summary and any error, without keys. Evidence is saved
under `C:\Users\arvik\code\buddha\runs\src02-capacity-20261023-live-v1`.
I will inspect it before giving a recovery or next-run command.

A complete result may pass or fail the declared capacity checks; either is a
measurement. An incomplete, invalid, refused or uncertain outcome remains an
explicit partial result with its stage, reason, costs and holds. It does not
authorize another attempt. This observation alone does not demonstrate a
working current-parent source chain or an improved agent.
