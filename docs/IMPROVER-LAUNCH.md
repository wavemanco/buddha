# Run or resume the reviewed matched comparison

The launcher connects the existing development and sealed-final controllers.
It checks the reviewed files, spending grants and saved work before asking for
keys. It preserves the original trial when work resumes. It does not allocate
money, choose a different experiment or change NoveltyBench scoring.

This implementation is not a funded handoff. The proposed WildChat resources
and review arrangements still need adoption, followed by a separate allocation
and final handoff checks. Wait for the exact reviewed command before live use.
[The current proposal](IMPROVER-PROTOCOL-PROPOSAL.md) records the recommended
execution caps, statistical limits and unresolved review arrangements;
[PLAN.md](PLAN.md) owns that remaining work.

## Command and options

After checking out code containing this launcher, this command shows its options:

```powershell
python docs/conformance/imp01-run.py --help
```

Run it once from the project folder. It prints help, needs no keys, makes no
provider calls and creates no trial records. It finishes immediately; no separate window
or stop command is needed.

The later funded command will supply these options:

| Option | Plain-English function |
| --- | --- |
| `--handoff` | Names the reviewed funded launch file, which points to the proposal and approval. |
| `--sha256` | Supplies the independently reviewed fingerprint of that launch file. A changed file is refused. |
| `--receipt` | Names a new summary file outside original inputs and output. Existing files are never overwritten. Use a different receipt name for each invocation. |
| `--live` | Allows unfinished work to proceed. Existing controllers still enforce each approved phase cap and every request. |
| `--prompt-keys` | Asks for missing provider keys through hidden local terminal input. Paste once and press Enter; no characters appear. Keys are not saved in the receipt. |
| `--confirm-project-keys` | Records your confirmation that these keys belong to the approved account scope. It does not authenticate prices or create spending authority. |

The funded command runs once in the foreground in one PowerShell window. It can
spend money only within the separately approved grants. Press Ctrl+C to cancel;
original records and uncertain charges remain. Wait for cancellation verification
to finish before attempting a restart. A restart uses the same reviewed launch
and trial, with a new receipt filename. Do not create replacement grants or
delete locks, reviews or trial files to force it through.

Existing keys in that PowerShell environment are used without another prompt.
Newly entered keys are temporary for this process and are removed on exit. Never
paste keys into chat. Providers verify access during their actual requests.

## What happens during a run

1. The launcher verifies the exact launch, proposal, approval, installed helpers
   and assessment definition. The raw assessment-file fingerprint and its
   normalized definition fingerprint have separate roles.
2. It checks three distinct original phase grants. Their scopes bind this trial
   directory, definition and phase. Search funds development; final funds sealed
   assessment. The zero-budget validation grant stays unused. Totals add these
   separate limits; money never moves between them.
3. A fresh trial requires unused grants and no old review or trial to replace.
   Its full future input-file projections include the outer controls and future
   keyed review. A retained trial instead goes through the
   [original state reader](IMPROVER-LAUNCH-STATE.md).
4. For unfinished work, it obtains the required keys once, binds their
   non-reversible fingerprints to this launch and repeats the state and funding
   checks. A retained review cannot be replaced with different keys or a new
   account assertion. An expired unfinished review stops for review.
5. The existing controller develops both fixed improvers under the declared
   rules. Only complete development permits the one-way final freeze. The final
   controller evaluates that original schedule without feeding final results
   back into improvement.
6. The launcher writes the new receipt, including recorded phase costs and
   holds. Original manifests, observations and reports remain authoritative.

The built-in progress messages identify checking, keys, preparation, search,
freeze and final work. Their accounting is for the active phase, not the sum of
all phases. Keys suppress heartbeat output while the hidden prompt is open.
Final receipts contain all three phases and their combined recorded totals.
Heartbeat messages show that the observer is running; they do not prove that a
test or provider request has completed.

## Stops, partial results and completed reuse

`complete` means the controller's original final report has completed and passed
its existing checks. Calling the same reviewed launch again can return that
saved result without keys or another model request. The CLI still writes its
new requested receipt.

`incomplete` carries the original controller's reason, position, coverage and
verified observation path. `cancelled` records Ctrl+C and, when the original
controller saved a verifiable cancellation, carries those same fields. The
launcher verifies saved partial records through existing recovery checks; it
does not guess the newest filename or invent missing coverage.

`stopped` means this launch could not proceed. A retained trial may still be
incomplete: for example, an execution lock or uncertain request prevents key
entry and more spending. Unknown and dispatched charges remain held. A known
reservation overrun stops further work while retaining its actual charge.
Unsent reservations also stay held; only the original controller can determine
whether the original operation can continue.

The receipt uses `buddha.improver-launch-receipt.v1`. It reports recorded local
amounts, not reconciled provider invoices. Unverifiable accounting is explicitly
unavailable. For cancellation during search or final assessment, an unverifiable
saved observation is explicitly unavailable too. Earlier cancellation reports
its phase and any available accounting without inventing an observation. One
million microusd is one US dollar.

The command exits with 0 for complete, 3 for a returned incomplete or blocked
launch, 2 for a check/key error, and 130 for cancellation. Error messages use
fixed reasons rather than echoing keys, task text or raw provider errors.

## Limits

Checks observe files sequentially; they are not atomic snapshots or promises
that the remaining schedule will fit its cap. Existing brokers enforce actual
reservations. A lock does not prove a process is alive, and this launcher never
removes one. Earlier saved formats retain their matching pinned readers.

The bounded supplied-worker checks establish launcher behavior at their recorded
scope. They do not establish full-grid runtime, provider access, model capacity,
scientific improvement or independent human quality. WildChat remains selected
for the sealed comparison; Curated remains qualified historical/development
evidence.
