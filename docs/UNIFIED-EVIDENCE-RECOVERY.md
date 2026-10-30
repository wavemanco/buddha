# Recovering the saved-evidence limit

The October 28 unified comparison stopped during development because Buddha's
saved-record checker reached its cumulative 1 GiB allowance. This is a harness
capacity failure. Adding API credit or restarting the unchanged command does
not resolve it. Keep the stopped run and all its files.

The saved observation records 604 attempts, $4.845090 spent and committed, and
zero held. Final assessment and both plain-model references had not started.
These are local accounting figures, not reconciled provider invoices. The
experiment is incomplete; none of its scientific completion gates close.

## What failed

The original checker accumulated 1,070,166,023 bytes of consumed evidence. Its
next file, `screen/tasks/2/evaluation/command-3.json` in the eighth counted
child's screen, contained 4,018,013 bytes. Only 3,575,801 bytes remained under
the 1,073,741,824-byte allowance. The file passed its individual observation;
adding it to the study-wide observation failed.

The exact saved state reproduced this error in a read-only check lasting
786.763 seconds. The check blocked writes, on-disk SQL connections, network
calls, subprocesses and execution of generated source. Only trusted error
locations, file sizes and cumulative counts were emitted. It inspected no
task, answer or generated-program meaning.

Much of the volume comes from repeated configuration and import inventories.
The controller also reconstructs the accumulated history repeatedly and
repeatedly decodes large task descriptors. These are concrete sources of work;
their share of the original twenty-hour runtime has not been measured.

`launch_stopped` hides the underlying exception. During the separate recording
phase the progress display has no selected budget, so it prints `accounting
unknown`. The saved observation nevertheless recovered all four grant totals.
Recording performs checks and saves a diagnostic; it starts no provider calls.

## First repair slice: bounded passive reading

The new reader stores each consumed path's original size and SHA-256 digest
instead of keeping every file's bytes in memory. A later read must match that
original receipt. The final check rereads the files, checks database sidecars
before and after, and checks the original folder inventory. Changed files do
not become a new accepted baseline.

The default cumulative allowance remains 1 GiB. A private, explicitly selected
`buddha.evidence-observation-policy.v1` can declare a larger finite allowance:

| Field | Meaning |
| --- | --- |
| `format` | Exactly `buddha.evidence-observation-policy.v1` |
| `max_total_bytes` | Positive integer cumulative allowance, at most 64 GiB |
| `max_resident_bytes` | Exactly zero: this version keeps no persistent raw-byte cache |

The allowance is fixed when a capture starts; nested captures inherit the
selected policy. Leaving the policy scope restores the default for new
captures in the same execution context. A future launcher must explicitly
apply the policy in its reader thread; it does not automatically spread to
new threads. Individual file limits, local folder-entry limits, link rejection,
original fingerprints and changed-byte checks remain enforced. A new consumed-
path limit also covers external inputs. This bounds retained
raw bytes, not total Python memory or total reread work. Rereading can add I/O;
this slice does not claim a runtime speed improvement or full-grid capacity.

No production launcher selects this new policy yet. The original executing
tree, scientific setup, grant terms, owners, receipts and spending remain
unchanged. Passing a passive check does not authorize paid continuation.

A separate raw-byte rehearsal uses 2,653 actual retained trial, executing-source
and static-preparation paths: 1,123,069,491 bytes. The default allowance refuses
them; an explicitly selected 4 GiB allowance checks every original fingerprint
successfully, with no persistent raw cache. This exercises real record volume,
not complete study reconstruction, SQL interpretation or continuation. Its
8.753-second raw-only timing cannot be compared with the 786.763-second full
reconstruction as a speed improvement.

## Specific stop reasons

The repaired source, policy, improver and unified launchers now preserve these
fixed codes in terminal output and new partial records:

| Code | Plain-English meaning |
| --- | --- |
| `evidence_total_bytes_limit` | The combined files exceed the observation's byte allowance. |
| `evidence_field_bytes_limit` | One file or field exceeds its individual allowance. |
| `evidence_path_count_limit` | There are too many folder entries or consumed file paths. |

Recognition follows a bounded chain of actual typed exceptions, including
causes hidden by the redacted traceback. It never prints arbitrary exception
text or accepts an arbitrary error's claimed code. Unknown errors still use
`launch_stopped`; credential and cancellation results keep their existing
meaning. The unified launcher prints its safe code before the potentially long
recording check, then saves the partial observation and re-raises the original
exception. Original saved observations keep their original labels.

These are engineering changes in a separate checkout. They neither patch the
old executing tree nor authorize starting a changed runtime against its owners.

## Complete-grid capacity remains a gate

The byte allowance is not the only limit. The existing checker also allows
10,000 local entries, counting files and folders together. Current trial
metadata has 2,149 files and 1,574 folders: 3,723 entries. An ordinary retained
task unit has 45 files and 32 internal folders. The allowed 312 successful final
cells therefore need at least 24,336 entries, or 28,059 including today's trial,
before remaining development, higher parent folders and freeze records.

Observed ordinary-unit sizes project about 7.34-7.66 GiB for the final cells
alone. This is an extrapolation, not an upper bound. The existing prospective
checks cover per-owner input sets and a rough development-owner count; they do
not establish complete trial folder or byte capacity.

A separate versioned capacity policy and full-layout rehearsal are required.
Neither failed stage attempts nor local stop observations are fully bounded by
the API-attempt cap, so any rehearsal must declare its recovery envelope.
Exceeding a finite allowance must remain an explicit partial result, with the
reason recorded. No production launcher selects a larger folder policy yet.

### Version 2: finite byte and count allowances

The separate `buddha.evidence-observation-policy.v2` keeps the same byte and
zero raw-cache fields, and requires two additional positive integer fields:

| Field | Meaning |
| --- | --- |
| `max_tree_entries` | Files and folders in each observed tree; at most 100,000. |
| `max_consumed_paths` | Distinct consumed files, including external inputs and adopted receipts; at most 65,536. |

These allowances are fixed before the initial folder inventory and remain fixed
for that capture's later checks. Defaults and version 1 keep the original count
limits. Individual field limits, sidecars, changed-byte checks, link rejection,
portable names and complete receipt-union checks still apply. Sixty-six final
integration methods pass, including a real 10,001-file fixture and byte/count
rejection during receipt adoption. This does not select a live policy.

### The actual saved stopping point

A guarded passive reconstruction now reaches the saved action instead of the
old cumulative-byte failure. It reconciles 174 owners, 604 attempts, $4.845090
spent/committed and zero held. Seven counted decisions are saved; the eighth
counted proposal and screen have reached the next witness-feedback action at
start 1, repetition 1, arm 1, slot 0. That witness folder does not exist yet.

This observation used explicitly selected finite limits before the later
receipt-sharing integration. It used in-memory SQL snapshots, with no on-disk
SQL connections, keys, model calls, workers, writes to the run or interpretation
or execution of generated Python. It identifies a prospective boundary; a
continuation must still check that boundary and preserve every old owner.

### Full-layout raw rehearsal

The larger policy passes an actual local raw-reading rehearsal over **24 GiB,
48,000 regular files and 81,920 total file/folder entries**. Every declared byte
is read initially, checked again during adoption, and checked at final finish.
No persistent raw cache is used. The exact layout and executing script/checker
hashes are recorded in the [capacity delivery](conformance/evidence-capacity-policy-delivery.json).

The layout accounts for the maximum 296 development owners, 1,248 final owners
and eight shared plain-reference owners. Its 424 task-storage proxies cover
60 development, 312 final and 52 plain task sets; plain tasks share owners.
Each assessment proxy has a 52 MiB byte quota and a padded 90-file/64-folder
geometry. One additional attempt footprint per actual owner is included inside
the declared quotas. An opaque prior-prefix allowance and shared padding bring
the total to 24 GiB. These are synthetic raw records, not completed benchmark
evaluations or a proof that every possible valid history fits. Larger records
or more failures can exceed the finite policy and must stop explicitly.

These optional developer commands run once, make no model calls and need no
separate PowerShell window. Start in the checkout containing the script:

```powershell
New-Item -ItemType Directory -Force runs\checks | Out-Null
$buddhaWorkspace = (Get-Location).Path
python -B docs/conformance/evidence-capacity-rehearsal.py --workspace $buddhaWorkspace --output "$buddhaWorkspace\runs\checks\evidence-capacity-opaque-local-v1"
```

The first line creates the local checks folder if needed, keeping its contents.
The second remembers this checkout's absolute path. The third only prints the
proposed layout, disk requirement and hash; it creates no rehearsal files and
spends no API money. Ctrl+C stops it.

```powershell
python -B docs/conformance/evidence-capacity-rehearsal.py --workspace $buddhaWorkspace --output "$buddhaWorkspace\runs\checks\evidence-capacity-opaque-local-v1" --materialize
```

This optional second command creates and checks the 24 GiB synthetic fixture,
requiring at least 30 GiB free disk space. It prints progress and saves its
plan/result beneath that fresh output folder. Ctrl+C stops it and retains a
marked partial result. Existing output folders are refused; use a fresh name
for another materialization. The fixture remains on disk for review. This is
not the paid experiment's continuation command.

## Sharing freshly verified evidence

The [verified-read repair](RECONSTRUCTION-COST.md#verified-receipt-sharing-and-digest-exports)
now removes redundant byte passes from nested adoption and eight fingerprint
exports. The source is freshly checked, the entire receipt union is validated
before the receiver changes, and later outer verification remains required.
Database field limits, legacy ordering and retained sibling-tree checks remain
enforced. This is not a filesystem transaction or a live continuation.

The [artifact-copy repair](RECONSTRUCTION-COST.md#fresh-copies-of-validated-artifacts)
also removes repeated validation when a checked, immutable package is copied.
Every new package still passes the strict constructor. Every copy is freshly
decoded and can be edited independently. There is no new cache. This reduces
specified repeated work; it does not remove the source-version and original-
owner checks required for a continuation.

### Counted-child witness rehearsal

The next rehearsal reaches a measured child whose parent record has a real lineage link. Its original eleven owners are inactive. The changed host then completes both normal witness stages: ask that child to produce another child, and check that the returned child can generate answers.

Each stage is interrupted after its supplied reply is saved. Restarting keeps the same owner, operation, raw manifest and recorded cost, and sends no duplicate request. The saved witness passes. A later check now reports completion, and another advance returns the saved result without changing the report or creating the next study decision. The completion result remains behind the ordinary leases and fresh file/grant checks.

The counted-cell check passes in505.555seconds, and five earlier continuation methods pass in113.235seconds. The earlier444.913second failure exposed the missing completion-summary field; it is retained. This uses two actual host roots/processes with supplied workers and HTTPS replies. It does not execute original private programs, real containers or paid calls, and it does not yet resume the whole development study. [Bound delivery](conformance/cell-witness-continuation-delivery.json).

Optional developer check, from a checkout containing this slice:

```powershell
python -B -m unittest discover -s tests -p test_cell_witness_continuation.py -v
```

This runs the one offline counted-child rehearsal and creates disposable test files. It spends no API money and starts no real containers. It runs once in the same PowerShell window and can take about nine minutes on the measured machine; Ctrl+C stops it. No separate window is needed.

### Comparing historical and continued screen records

A screen records a fingerprint of its host files and settings. A repaired host can produce a different fingerprint while preserving the same task and scoring protocol. Parent selection and feedback reconstruction must recognize the exact approved pair without pretending those fingerprints are equal.

The internal comparison component accepts only two explicitly supplied, previously checked profiles within one study and original grant. It rejects a third profile, another study/grant, an unexpected screen location, nested scopes and use from a copied thread. Reading a saved reference never activates it. The component supplies no execution or spending permission by itself; the checked development scope below now verifies and binds the actual old/new helper contexts.

A mixed parent selection lists each actual fingerprint and report reference. Uniform selections keep their original format and bytes. Feedback preserves its complete answers, official scores and existing actor checks. A versioned `policy.host_control_relation` records only comparisons that actually depend on the approved difference. It also follows failed-child history and earlier feedback used to author a proposal. An unrelated old packet rebuilt afterward remains byte-identical.

Five new offline methods pass: four relation/provenance checks in203.360seconds and a genuine failed-child/history/comparison check in112.386seconds. Two existing strict-control methods pass in50.528seconds. The three-generation check first exposed a missing dependency marker and then passed after correction. Source/study-root wrapper propagation has helper checks; new declaration-level acceptance for those wrappers is not claimed. [Bound delivery](conformance/screen-control-relation-delivery.json).

Optional developer check, from a checkout containing this slice:

```powershell
python -B -m unittest discover -s tests -p 'test_screen_control_*.py' -v
```

This runs the five offline comparison checks using disposable files and supplied replies. It spends no API money and starts no real containers. It runs once in the same PowerShell window and can take several minutes; Ctrl+C stops it. No separate window is needed.

## Continuing the remaining development

The witness-only scope keeps its original one-witness limit. A separate
checked `buddha.study-continuation.v1` scope covers the exact cut witness, its
decision and the strictly later declared development cells through the normal
study freeze and publication. It adds no extra proposal opportunity and no
final-assessment, plain-reference or paid-CLI permission. The historical Python
module header still describes the first witness mechanism; its executable bytes
are retained at this tested source cut.

The checker preserves the original state controls and every old owner/file pin.
An old owner's scheduled role gets its original controls; only an allowed new
owner gets the actual new helper/driver bindings. Absence from the old-owner list
alone is not permission. Witnesses use the actual old or new parent profile.
The original scheduler and its partial-result handling are shared rather than
reimplemented. The descriptor-entry API reconstructs the study once per normal
action, then uses the same checked state with fresh under-lock file/grant checks
and a newly constructed reader. The checked-token API still rechecks freshly.

The completed rehearsal uses two real source directories/processes, one task,
two supplied answers, two arms and two opportunities per arm. It stops the first
source at the last slot-zero child witness, with eighteen inactive old owners,
then completes the remaining work under the same original fixture grant. An
interrupted proposal resumes the identical owner, operation, manifest and cost
with no second send. All four decisions are admitted. Mixed C-only freeze keeps
the two actual fingerprints, the explicit relation and the declared selection
rule; the frozen files match the selected source bytes. Slot-one proposal
feedback remains correctly old/old. Every old cut file hash remains unchanged.

After publication, keyless replay passes with no new sends, workers or report,
accounting or file changes. Final/plain work remains unused in this fixture.
The [delivery](conformance/study-continuation-delivery.json) records the exact
cuts, earlier failures, independent review and current limits.

Two earlier full attempts timed out at the unchanged 180-second child limit;
their results remain incomplete. The completed run takes 3,405.218 seconds for
the one full test, with all sixty-nine children exiting successfully and the
longest child taking 115.127 seconds. It uses the separately verified constructor
repair. These are one local execution and work-count observations, not a speed
ratio or a universal runtime bound. A reviewed external observer retained the
original temporary paths on failure and requested frame-only stacks at 150
seconds; it changed no shipped code, test, timeout or model setting. Successful
ownership-checked cleanup removed the fixture.

```powershell
python -B -m unittest discover -s tests -p test_study_continuation.py -v
```

This optional developer command runs the descriptor-entry check and supplied
two-slot rehearsal once in disposable test folders. It needs no API keys,
makes no paid calls and starts no real containers. Allow about an hour on the
observed Windows machine. Use a separate PowerShell window if you want to keep
it visible; Ctrl+C stops it. The ordinary test cleans up its temporary folders;
the retained external diagnostic observer is recorded separately.

## Continuing the full comparison

The full-trial bridge reuses the existing coordinated launcher for remaining development, source freeze, sealed final assessment, both plain sampling references and comparison publication. Historical approval files keep their actual original paths and hashes. New owners receive a separate, complete execution-control map. Numerical/selection modules and the official benchmark remain fixed. The original launch hashes still identify the API-key reviews, and the original plain-plan hash still identifies its grant.

The coordinator freshly rejoins the continuation evidence under its workspace lease before key entry and again before the first phase starts. New trial owners also bind the cut reference. Stopped and cancelled terminal records retain the validated continuation hash. The `--continuation` flag explicitly selects this route; reading a saved reference never activates it automatically.

The complete offline trial rehearsal passed on the earlier repair cut. The optimized source has separate focused checks and a successful check against the actual saved history. Its exact published source now passes all eight Linux/Windows CI jobs: 2,135 test occurrences per OS, with five Linux skips and one Windows skip, no failures/errors, and all 56 quality steps successful. The [trial delivery](conformance/trial-continuation-delivery.json) retains the earlier evidence cuts; the [operator handoff record](conformance/trial-continuation-handoff-delivery.json) records this later hosted completion and final clearance separately.

The actual-history check reconciles 174 inactive work units and 604 recorded calls: $4.845090 spent, zero held and no new work units. All 3,277 protected original file hashes and the trial's 2,149-file list remain unchanged. This was a passive inspection; it made no provider calls and did not resume the experiment.

The historical cleared handoff below has since stopped automatically. **Do not rerun it while the stop is being diagnosed.** The existing allocation is unchanged; unused money from earlier closed experiments is not transferred into it.

Optional developer checks, from a checkout containing this slice:

```powershell
python -B -m unittest discover -s tests -p test_phase_continuation.py -v
python -B -m unittest discover -s tests -p test_trial_freshness.py -v
```

The first command checks historical versus executing file bindings. The second checks late evidence changes and stopped/cancelled operator records. Both run once using disposable files and synthetic observations, spend no API money and start no real containers. Use the same PowerShell window; Ctrl+C stops either command. These focused checks do not prove the whole comparison completes.

```powershell
python -B -m unittest discover -s tests -p test_trial_continuation.py -v
```

This optional developer command rehearses recovery through development, final assessment, both plain-model modes and saved-result replay. It uses temporary records and supplied replies, spends no API money and starts no real containers. It runs once in the same PowerShell window and can take hours; Ctrl+C stops it. It does not resume the original paid run.

## Earlier library acceptance

The first [executed continuation mechanism](conformance/witness-continuation-delivery.json)
now passes an offline test using two real source directories and separate Python
processes. The first process completes one small task and leaves four inactive
owners. The second creates one new witness-proposal owner, records a supplied
reply, stops, and resumes the same owner and operation without sending again.
The raw manifest and recorded cost stay identical across that replay.

The new library checker binds the original launch chain, four grant identities,
old owner/file anchors, scheduled witness, original key-review context and actual
new helper/driver files. Its scope is explicit and limited to the checked root
and thread. Historical parent records keep their old bindings; the new witness
records its actual new bindings. It rechecks bytes, file/folder types, sidecars
and grants after acquiring the normal writer locks. All old file contents stay
anchored; directory timestamps and grant bytes may change through legitimate
later work. New bytes are read with fixed field limits, never an arbitrary
size supplied by metadata.

This fixture uses simulated workers and provider replies, with no real API calls
or containers. That first fixture proves only the common-witness proposal
mechanism. The counted-child and remaining-development fixtures add their
separately recorded scopes. Those library checks alone do not establish final
assessment, plain references or whole-trial publication. The later hosted
completion and operator clearance below remain separate from their original
evidence cuts. The library slices alone add no paid operator command.

```powershell
python -B -m unittest discover -s tests -p test_unified_continuation.py -v
```

This optional developer command runs five synthetic source-transition checks
once, using temporary fixtures. It may take a few minutes. It needs no real API
key, makes no paid calls and needs no separate window. Ctrl+C stops it.

The first [helper-transition component](conformance/helper-role-relation-delivery.json)
now checks a precise list of 65 host helpers and three outer source files.
It anchors the old source list to the already recorded handoff, keeps the
original scientific inputs, selected components, runtime and CORE hashes, and
checks the proposed new file bindings. The three old outer pins remain as
historical provenance; the plain-generator source must keep the same hash.

A check using the actual saved screen metadata succeeds with 185 original
bindings and 189 proposed bindings. This is a counterfactual metadata check:
no stage, owner, grant or original file was changed. It does not prove an
executed transition. The complete continuation must also bind its own record
and any named driver, join all original actors and accounting, and handle
old and new stages throughout development, final assessment and plain use.

The component returns a separate proposed map. Original reports and their
actual fingerprints keep their meaning. It adds no launcher opt-in, discovers
no transition automatically, and does not relax the existing parent-selection
guard. Unknown helper names, changed fixed inputs, aliases and a second
complete producer prefix are rejected. Source freshness, repair semantics and
authority still require the outer checked continuation.

The [owner-census repair](RECONSTRUCTION-COST.md#owner-census-work) now avoids
decoding the same task population for every file belonging to one owner. Its
work-count and adversarial tests preserve the original owner/funding checks;
they do not establish an end-to-end runtime improvement or enable continuation.

[PLAN.md](PLAN.md) owns the current sequence. The operator section below records
the later exact-source CI, retained-record, execution-pin, accounting, runtime
and outgoing-request checks separately from these earlier library mechanisms.

The continuation must preserve original paths, grants, manifests, receipts,
unknown requests and all charges. Editing frozen source hashes, deleting
evidence, replacing owners or importing trial work into an unrelated grant is
not recovery. The earlier library slices alone supplied no cleared paid restart
command. The operator section below separately records the checked handoff;
no additional funding is requested by these recovery slices.

## Operator handoff for the original comparison

**Historical command superseded. Do not rerun this block. Use only the [current checked continuation](#current-checked-continuation) under its recorded operator clearance; the old command below is retained as evidence.**

The executing PR179 source passed its complete Linux/Windows matrix and final
source/input/runtime preflight; the [handoff record](conformance/trial-continuation-handoff-delivery.json)
retains that clearance. The operator then ran this exact handoff and entered
both keys. Its later automatic stop is recorded separately in the
[stop observation](conformance/trial-continuation-stop-observation.json);
passing engineering checks did not establish that the actual continuation would complete.

The terminal reached `rechecking`, then printed `Starting original matched
development` and reported `search` with the same 604 recorded attempts,
$4.845090 recorded cost and zero held. It then stopped automatically with
`launch_stopped`. The saved incomplete observation has outer phase `primary`;
its inspection still finds the prepared study in `search` at the same next
witness-feedback step, start 1 / repetition 1 / arm 1 / slot 0. No additional
attempt or charge is recorded. This is retained accounting, not a provider
invoice reconciliation.

That sequence establishes entry into the development controller after its key
and state rechecks. It does not identify the exact failing operation inside
search. The current inner error wrapper discards the specific exception from
the operator report. Earlier increasing CPU measurements established active
computation, not completed validation or logical progress. Preserve this
incomplete result and the original files; do not infer a key failure, a Docker
failure or a benchmark result from the generic reason.

The immediate target is to retain a fixed, safe failure stage and cause, then
rehearse that path without paid calls against realistically sized retained
history. Any repair needs separate checked source and continuation evidence;
the frozen executing checkout will not be silently patched. See
[ENG-OBS-01](BACKLOG.md#eng-obs-01-make-continuation-checks-and-stops-understandable).

The historical command was intended to resume the original experiment at its
next unfinished step. It keeps all
604 recorded API attempts, their replies and the $4.845090 already spent, then
continues development, final assessment, both plain-model references and saved
comparison publication. It creates no new allowance or replacement experiment.

The same combined cap remains **$150 and 16,384 attempts**: $40/4,096 for
development, $85/10,240 for final assessment and $25/2,048 shared by both plain
references. Validation remains $0/0. Earlier spending counts against these same
four original grants. Separate native AI review uses the already approved
Codex capacity outside this API cap; its monetary cost is unpriced, not zero.

The historical operating instructions required Docker Desktop and only one
running copy. A new PowerShell window was optional, with no package installation
needed. The preserved paths and fingerprint below, including their historical
`PROVISIONAL` filename, identify the command that executed the frozen PR #179
checkout at `e62515c5`. **This block is retained as evidence, not a current
instruction to run it.**

```powershell
cd C:\Users\arvik\code\buddha
Write-Host 'Checking the saved run before key prompts. This can take tens of minutes.'
python -B "C:\Users\arvik\code\buddha\runs\reviews\trial-continuation-capture\docs\conformance\unified-run.py" --handoff "C:\Users\arvik\code\buddha\runs\reviews\eval01-final-design-20261023\PROVISIONAL-imp01-trial-continuation-2349d9a-v1.json" --sha256 fc2e4d8fe4b40b79b09aedc6ac869b5ec063d169912e8be12f61c2e2a0ce1785 --continuation --live --prompt-keys --confirm-project-keys
```

The first command opens the project folder and spends nothing. The second
prints one free notice in the same window; it does not keep running. The third
runs the checked continuation once. It verifies the saved work, asks for missing
OpenAI and Anthropic keys using hidden input, rechecks the records, then may
spend money within the original limits. `--continuation` selects the checked
recovery route; `--sha256` checks the chosen record's fingerprint.
`--confirm-project-keys` confirms that the keys belong to the approved accounts.
The program does not write API keys into project files.

The first full-history check happens before the key prompts and progress
display. It can take tens of minutes with no terminal output; it makes no
provider calls. Checks repeat after key entry. Several checks use the same
`checking` label, and each inspection starts its own elapsed clock. Their
`recorded accounting unknown` text means that the display has no selected
budget to show; it does not establish a missing ledger, failed key or stalled
check. The timer and heartbeat alone establish neither completed work nor
forward progress. Once the development controller selects its budget, progress
lines show that phase's attempts, recorded cost, held amount and cap. A held
amount reserves a possible charge; it is not another completed payment.

Ctrl+C stops the command and attempts to save an incomplete observation. Keep
all files and any held or uncertain requests intact; do not reset a budget or
start a second copy. The automatic stop above is the current checkpoint.
Eventual computational completion is followed by separate AI review; optional
human ratings do not block the AI-only report. A completed run does not by
itself establish scientific improvement.

### Safe stop diagnostics in the repair checkout

The separate repair adds a small diagnostic record before the coordinator's
potentially long incomplete-observation collection. It keeps the existing stop
reason and adds fixed exception categories and bounded source locations from
the installed public Buddha package. A location contains only a permitted file
name and line number. It contains no error message, key, local variable, task
answer, private program text or outside file path. Nested wrappers can still
be followed even when they suppress the normal Python traceback display.

The coordinator prints the safe record and attempts to save the same record
as a separate diagnostic JSON file in its existing observations folder. The
ordinary incomplete-observation format and the accounting remain unchanged.
If diagnostic collection or saving fails, the original failure and ordinary
incomplete-recording attempt still take precedence.

These locations help identify the failed check; they do not prove a diagnosis
on their own. They cannot recover the exception from the already finished
October 29 process. This repair does not establish the cause of that stop,
close the earlier silent-start/repeated-label display issues, change a safety
check or clear the historical command for rerun. Focused engineering evidence
is recorded in [the diagnostic delivery](conformance/launcher-stop-diagnostics-delivery.json).

Optional developer check, from the repair checkout:

```powershell
python -B -m unittest discover -s tests -p test_launch_stop_diagnostics.py -v
```

This runs the focused synthetic diagnostic checks once. It makes no paid calls
and does not use the original experiment or ask for keys. Run it in an idle
PowerShell window; no second window is needed. Ctrl+C stops the local check.

### Passive study-start diagnosis

The first guarded observer restored the saved history, then stopped because
its own check compared a three-field summary with four-field authority totals.
That V2 result is retained. It does not explain the original search failure.
The corrected check verifies the three summary fields and, separately, all
four authority fields. It also rejects wrong types, extra or missing fields
and changed amounts; synthetic regression checks cover those cases.

V4 completed the passive check against diagnostic-only `c54819f` source in
1,753.039 seconds. All eight stages and nine checkpoint checks passed, keeping
174 inactive owners, 604 recorded attempts, $4.845090 spent and zero held.
It created no owners and made no API calls. Independent review also passes;
[the observer record](conformance/passive-study-start-observation.json) binds both results.
This checks source/record compatibility before any writer lease or new model
work. It does not exercise the held lease, witness materials or scheduler,
explain the original stop, or establish that recovery works.
The historical command remains on hold; this passive check alone requested no new command or key entry.

A separate native startup check passed the original import audit for 5,180
modules and eight hook aliases in 44.694 seconds, using the original image,
mounts and limits. Its 2,487 watched files remained unchanged. The one container
was removed, and a separate check confirmed it was absent. No API calls,
keys, original SQL connections or new owners were used. This checks startup;
it does not exercise the real work lease or recover the experiment.

Offline outgoing-request checks passed all ten methods on repeat. The first
cohort retained one fixture-setup error; a focused repeat also passed, but the
initial cause remains unknown. These checks use temporary synthetic ledgers
and mocked HTTPS. They verify recorded generator/judge settings at this source
cut, without establishing provider access or permission to restart the run.


### Current checked continuation

The [saved October 30 stop](conformance/continuation-executor-stop-observation.json)
retains 657 attempts, $5.523144 recorded cost and zero held. Final assessment
and both plain references remain unstarted. The first task of the next cell
failed before its isolated worker became ready; container cleanup was unknown
and this failed attempt made no model callbacks. The outer `protocol` label
does not establish a NoveltyBench-settings error. The exact initial executor
cause was discarded. Keep all original records and grants; another live
command will follow separately checked cleanup and diagnostic work.

**Historical clearance: this command was run and has now stopped. Do not rerun it until the follow-up checks are complete.** The command below
selects diagnostic-only `c54819f`
source and continuation `da37a817`; the historical command above is superseded.
All ten exact-source CI jobs now pass their saved-evidence checks: 2,141
ordered/disjoint test occurrences per OS, all 70 quality steps and nine reader
checks. Fresh read-only source, input, runtime, Docker-image metadata and
original-file checks also pass with independent review. The
[handoff record](conformance/diagnostic-continuation-handoff-delivery.json)
links the exact evidence and recorded final operator clearance.

This continues the same experiment at its next unfinished step.
The combined **$150 / 16,384-attempt** limits remain: $40 / 4,096 development,
$85 / 10,240 final assessment and $25 / 2,048 shared by the two plain-model
references; validation stays $0 / 0. All earlier charges still count. The last
verified saved checkpoint is 604 attempts, $4.845090 spent and zero held. No
new allowance is created and money cannot move between these four grants.

Keep Docker Desktop running and start only one copy. A new PowerShell window
is optional. Use the same approved OpenAI and Anthropic project keys with the
confirmed Standard/default public pricing. Missing keys are requested using
hidden input: paste once and press Enter; no characters appear. An input
acknowledgement does not establish provider authentication. Existing key,
model, account and source checks remain in force.

```powershell
cd C:\Users\arvik\code\buddha
Write-Host 'Checking the saved run before key prompts. This can take tens of minutes.'
python -B "C:\Users\arvik\code\buddha\runs\reviews\launcher-safe-stop-diagnostics\docs\conformance\unified-run.py" --handoff "C:\Users\arvik\code\buddha\runs\checks\diagnostic-continuation-preparation-20261029-v1\PROVISIONAL-imp01-trial-continuation-c54819f-v1.json" --sha256 da37a8178d930d684b38518964e277030aa4567a4b4943d4835a8ad9468adfcc --continuation --live --prompt-keys --confirm-project-keys
```

The first line opens the project folder and spends nothing. The second prints
one free notice and finishes. The third is one PowerShell line: it runs the
checked continuation once, verifies the original records, obtains missing keys
and may then spend money within the original grants. `--continuation` selects
the checked recovery route; `--sha256` binds the exact continuation record;
`--confirm-project-keys` confirms use of the approved project accounts. No API
key is written into project files.

The first full-history check may be quiet for tens of minutes before key entry.
Checks repeat afterward, may reuse the `checking` label and may restart their
elapsed clock. `recorded accounting unknown` means the display has no selected
budget; a timer or heartbeat alone does not prove progress. During development,
the amounts shown belong to the active phase. Keep Docker open through the run.

If it stops, share the final status and any safe diagnostic lines or saved
record path, never a key. The coordinator prints bounded public source
locations and attempts to save the same safe record before the longer
incomplete-observation check. Ctrl+C stops work and attempts to retain a marked
partial result; recording may take time. Keep the files and any held or unknown
requests. Do not reset a grant, delete locks or start another copy to force it.

Earlier offline wire checks at this source passed all ten methods on repeat
after one retained fixture-setup error whose cause remains unknown. They used
synthetic records and mocked HTTPS, made no real API calls and retain their
[initial and repeated evidence](conformance/diagnostic-continuation-handoff-delivery.json).
The generator/judge settings and official NoveltyBench protocol are unchanged.
The original search-stop cause also remains unknown: this is a controlled
continuation with better diagnostics, not a demonstrated cause fix or promise
of completion.

Computational completion is followed by the separately approved native AI
review: `gpt-6.1-sol` / `ultra`, at most 44 fresh contexts, using unpriced Codex
capacity outside the API cap and no reviewer API fallback. Optional human
ratings proceed separately and do not block the AI-only report. Completion
alone establishes neither improved performance nor a completed scientific gate.

### Prospective returned-result reporting

The [separately checked reporting repair](conformance/launch-result-diagnostics-delivery.json)
adds a safe diagnostic for an incomplete result returned by the primary
controller. It runs before the primary result is shortened and before the
coordinator's later partial recording. It can expose inline cleanup, worker
readiness and call-count fields without printing answers, keys or source text.
It does not eliminate history reconstruction already done by the inner controller.

Both development and final-assessment branches have the hook. Final assessment
supplies only header/position details at that boundary; the diagnostic never
opens its referenced child files. Diagnostic errors and interruptions preserve
the original outcome. Existing canonical reports and the broad protocol reason
remain unchanged.

This is prospective code, not another cleared command. The retained experiment
now contains original and c548 control profiles; changing host helpers again
requires a checked compatibility case. No profile policy is widened, no lost
Docker cause is recovered and no reconstruction speedup is established here.
Keep the earlier command on hold until the next explicit handoff.

## Bounded A/B-to-C continuation contract

**Preparation only.** A means the original producer, B the frozen `c54819f`
producer, and C the prospective repaired producer. These identify versions of
Buddha's host software, not AI model choices. The current registry contains
174 inactive A owners and 19 B owners; the sole active B generation owner has
zero operations. The [metadata census](conformance/current-owner-metadata-delivery.json)
does not validate their owner files or authorize adoption. The original
174-owner/604-operation cut remains intact and inactive; the current total is
657 operations/$5.523144/zero held. No new command or source migration is cleared.

### Smallest checked extension

Use one new continuation-descriptor version with a finite literal A/B/C profile
table and an exact retained-owner map, rather than widening v1 or accepting an
arbitrary number of profiles. Each profile binds its actual producer root,
helper/control hashes, CORE and runtime. Original protected selection/seed,
CORE/runtime and full helper-role membership stay fixed; only individually
reviewed helper revisions may differ. Each retained-owner entry binds its
directory, run UUID, grant, semantic and raw manifest hashes, ledger/prefix
anchor and actual profile. Reject missing or extra owners, aliases, duplicate
producer identities under different labels, and relabeling an existing UUID.
Only explicitly scheduled, absent future roles may acquire C owners. The map
is checked host data, not authority supplied by a saved marker.

Keep the original inactive-cut rule. The 19 retained B owners form a separate
checked group, including the active owner's explicit unfinished state; they
must not be inserted into v1's inactive original cut. C cannot resume the
prepared B screen using C's installed helpers. Preserve B's exact owner,
attempt history and receipts. A new companion descriptor would itself change B's recorded control identity.
The smallest later option is therefore a separately reviewed external
one-action wrapper: import literal B, validate the existing `da37a817` trial
descriptor through its trial path, then invoke B's existing prepared-screen
action under that exact scope, leases and fresh checks. No such wrapper or
command is cleared here. That action may create remaining scheduled B owners;
refreeze their exact map afterward rather than treating 193 as permanent.
Compatibility and cleanup clearance remain required.

### Keep host provenance out of model input

The control-relation marker is currently host-only: it is stored in feedback
provenance, while the candidate receives only the admitted task/note projection,
configuration and, where applicable, literal parent bundle. Notes' source IDs
do not hash the full provenance policy; no provenance file is mounted for the
worker. Consequently a host-only extension needs no scientific prompt, feedback
payload, template, model, reasoning, token or benchmark change.

Route every existing A/B packet's derivation through its exact pinned legacy
relation before entering the new derivation scope. Preserve all four original
packet files byte-for-byte; do not substitute an A/B/C marker inside an old
packet. A new host-only relation/provenance version may bind the new descriptor
and the actual A/B/C dependencies, including a pinned legacy A/B dependency.
Do not add ambient profiles that the packet did not use. Existing v1 parsers
and rejection rules remain strict. For unchanged evidence, require identical
admitted task/note bytes, configuration, parent and official request settings.
New execution identities can change a Gateway request hash while its body is
unchanged; compare both separately. Arbitrary private actor-authored messages
are not promised identical, and new measured data may legitimately change notes.

| Public touchpoint | Required treatment |
| --- | --- |
| [Continuation scope and owner routing](../buddha/unified_continuation.py#L174), [original-cut check](../buddha/unified_continuation.py#L926) | Add a separate versioned finite map; preserve process/thread/root/grant binding and all inactive A checks. |
| [Literal screen controls](../buddha/source_screen.py#L888), [generation owner](../buddha/candidate_generation.py#L599) | Check the owner's actual installed producer; keep active B and any prepared B screen under B. |
| [Two-profile scope](../buddha/source_screen.py#L84), [finite scope](../buddha/source_screen.py#L142), [dependency policy](../buddha/source_feedback.py#L425), [packet reconstruction](../buddha/source_feedback.py#L1390) | Route legacy v1 replay exactly; version only new host relations/provenance, not old packet bytes. |
| [Feedback projection](../buddha/candidate_run.py#L214), [worker input](../buddha/candidate_worker.py#L198), [request identity](../buddha/gateway.py#L1106) | Keep model-visible projection/settings and distinguish body identity from owner/request identity. |
| [Fresh post-lock checks](../buddha/unified_continuation.py#L334), [one-action dispatch](../buddha/unified_continuation.py#L1256) | Retain ordinary leases, after-lock freshness, execution identity, budget/attempt/model limits and phase fence. |

### Minimum supplied acceptance cases

| Case | Required result |
| --- | --- |
| Legacy A/B replay, including transitive feedback | All four packet bytes and old receipts remain exact; unchanged task/note projection and request body/settings match. |
| Active B presented to C; unknown owner/profile, producer alias or borrowed scope | Refuse before owner creation, ledger transition or send; include wrong process/thread/root/grant/runtime and unsupported fourth profile. |
| Literal B completion and subsequent C role | Same B UUID/attempt prefix, no duplicate paid receipt; C creates only its explicitly absent future role after a clean prepared-screen boundary. |
| A/B/C dependency and interruption | Preserve legacy marker bytes, record only actual dependencies, retain failures/costs/holds, and resume without rebinding existing owners. |
| Freshness, funding and phase changes | Mutated source/raw cut/owner/grant or post-lock state, exhausted budget/attempts, changed model settings and a closed phase stop before dispatch. |

Implement and rehearse only this bounded contract next. Adoption later requires
a fresh full-current raw cut, exact source/runtime pins and owner/receipt checks;
the 193-row metadata receipt is insufficient. Exact-source hosted verification,
bounded actual reconstruction and uncertain cleanup/endpoint reconciliation
remain separate gates. Original $150/16,384 phase allocations and reviewer scope
stay unchanged; preparation grants no extra API allocation or live clearance.
The [delivery](conformance/three-profile-continuation-contract-delivery.json)
records this design review, not an implemented compatibility result.

## Finite relation primitive: first implementation

The [delivery](conformance/finite-profile-relations-delivery.json) implements
only the internal host-side relation layer. A separate v2 scope admits exactly
three caller-checked control hashes. It cannot nest with v1 or another v2 scope.
It preserves process, thread, study, grant and scheduled-screen checks; unknown
hashes and conflicting hashes for the same exact evidence reference refuse.
Identical references may repeat. No descriptor loader or owner-adoption route
uses this scope yet. Marker pins are canonical byte/lexical checks, not proof
of producer source roots, physical file identity or permission to dispatch.

Old A/B-only derivations return the exact old v1 marker. A genuine supplied
four-file A/B feedback packet replays unchanged, including the task/note bytes
admitted to the worker. New A/C or B/C markers list only those controls; a
three-control marker also retains the exact A/B compatibility proof. That
proof does not claim an old packet was read. Dependency composition validates
actual direct screen references/controls and inherited markers together; it adds
no ambient third control. Their combined count is bounded at 256. No feedback payload, actor
template, model, budget or NoveltyBench setting changes.

Review also checked a supplied case where the current screen uses C and
inherited metadata names A/B. Composition must include the directly used C
controls even when the current screens are all C. This is a supported-input
check, not evidence that the actual stopped run produced incorrect metadata.

Nine final-cut methods and all seven configured local quality checks pass.
The initial seven new methods and five v1 regression methods belong to an
earlier source cut. A later seven-method cut passed before review identified
the supplied direct-C case; its narrow failing check and repaired nine-method
result remain separate. No normal-lineage reachability or actual-run error is
established by that supplied case. Cross-root producer/owner checks, a full
new-C packet pipeline, retained-history compatibility and hosted CI remain
separate evidence. These checks establish engineering behavior with supplied
data, not recovery or scientific improvement.

### Preserve fixed scientific code and literal B

`source_screen_results.py` is in the continuation's fixed-science set even
though it is outside the Gateway CORE. Its original literal bytes must remain
in the current experiment's eventual executing variant. Keep that set and its
equality check intact. The general result-collector optimization in PR194 can
serve future fresh studies; it is not admitted into this frozen run. The
nonprotected screen-side reuse and host-only relation work remain prospective
continuation candidates. A separately pinned execution variant is still needed.

Descriptor paths and hashes are part of the recorded control identity. A new
descriptor beside B would create a different profile, even with identical B
helper files. Do not relabel it B. The external one-action option above must
validate the old descriptor and run literal B; only later absent roles may
use a separately bound C after the prepared B screen is cleanly complete.

Optional local check, from the checkout containing this slice:

```powershell
python -B -m unittest discover -s tests -p test_finite_profile_relations.py -v
```

This runs the nine supplied-data checks once and exits. It spends no API
money and changes no saved run; it creates temporary test files. Use an idle
PowerShell window in that checkout, or a separate window while another command
runs. Ctrl+C stops the checks. It is not a live continuation command.

Next implement and rehearse the exact finite producer/retained-owner routing.
Keep its two jobs separate: account for every registered owner, then route the
smaller set of source-proposal/generation anchors. The 174/19 registration split
does not establish one identical control hash for every owner. Existing native
evaluation checks still validate their own role-specific inputs and settings.
Keep the original live command on hold pending exact-source hosted results,
a fresh full-current cut and owner/receipt reconstruction, and endpoint/cleanup
reconciliation. No new grant, key input or user action is needed for this slice.
