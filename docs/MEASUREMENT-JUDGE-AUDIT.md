# MEAS-02: offline saved-judgment audit

October 20, 2026. All six saved historical partition replies reproduce their
recorded classes through the pinned official v1.1 selected functions, without
lenient completion. The available resolved comparisons agree on 95 unique
within-candidate pairs, **all expected distinct**. This establishes neither judge
accuracy nor sensitivity to equivalent answers. MEAS-02 remains partially
addressed; [PLAN.md](PLAN.md) owns its status and next gate.

This diagnostic is bound to the historical v1.1 evidence. Its scripts live under
`docs/conformance`; this slice changes no agent, release selector, gateway or
shared runtime module. The [release-upgrade contract](RELEASE-UPGRADES.md) continues
to govern configuration-only baselines on compatible new official releases.

## What was replayed

The [replay script](conformance/meas02-official-replay.py) uses exact selected
functions/classes from `common.py`, `judge.py` and `partition.py` at upstream
commit `64a23be6b18ec1dacc298830aab276061b6e143c`, with Pydantic 2.11.7 and
pydantic-core 2.33.2. Source-file and selected-AST hashes are recorded in the
[actual replay evidence](conformance/meas02-official-replay.json). This executes
the selected official code; it does not execute the complete modules, native CLI,
SDKs or a fresh model judgment. Scripted immediate single-call coroutines do not
measure concurrent scheduling or network behavior.

For each of the three recovery and three linked-continuation candidates, the
replay binds the saved task, ordered answer hashes, partition request fingerprint,
completed operation and retained reply text. Every reply parses and folds strictly,
matches the recorded partition/distinct count, and produces the same result with
leniency enabled. **None of these six replies requires leniency.** Their high
distinct counts therefore cannot be attributed to this repair path on this evidence.

The retained response is legacy parsed `Reply.text`, not complete raw HTTP bytes
or original response-block boundaries. Seals and replay demonstrate local saved
evidence consistency, not provider authenticity. The historical adapter used one
partition attempt with repair disabled; replay does not retroactively turn it into
a native run or establish native retry behavior for that occasion.

The replay also exercises 23 scripted selected-function controls:

| Control family | Cases | Bounded observation |
| --- | ---: | --- |
| Partition folding | 9 | Strict rejection versus lenient handling of omissions, repeated/out-of-range indices and empty groups. |
| Display-order mapping | 4 | Known displayed groups map back to the intended original answer order under the configured seeds. |
| Stage handling | 6 | Strict success, later valid repair, final-fold leniency, refusal and schema failure remain distinct paths. |
| Generic judge refusal/fallback | 4 | Refusal can invoke a configured fallback; an ordinary parse failure is not treated as refusal. |

Lenient folding removes invalid indices, keeps the first occurrence of repeated
indices and adds omitted answers as singleton classes. Controlled examples show
that even an empty grouping can thereby become an all-singleton result. This is
source-prescribed recovery, not independent semantic confirmation. The generic
fallback controls do not imply that the partition CLI supplies a fallback model;
that CLI supplies none. Order controls check mapping code, not a model's stability
when it sees reordered answers.

The evidence preserves all 287 prior historical-file seals, the archived runtime
ZIP, the sealed v2 authority and all 36 package source seals. Financial decoding
uses in-memory SQLite snapshots. No keys, provider calls, source-database opens,
historical writes or archived-runtime reconstruction were used. See the
[delivery record](conformance/meas02-offline-delivery.json) for slice evidence and
validation status; this report does not claim pending tests or CI have completed.

## Comparison with the frozen development judgments

The pure [comparison helper](conformance/meas02-compare.py) binds the
[MEAS-01 expectations](../tests/fixtures/meas01-expectations.json), their
[unblinded source references](conformance/meas01-adjudication-review.json) and the
six replay rows. It compares equivalence relations rather than arbitrary class
numbers. The [comparison evidence](conformance/meas02-relation-comparison.json)
records these explicit populations:

| Population | Result |
| --- | --- |
| 17 resolved review items | Nine compared: two complete sets and seven focused cards. |
| Remaining resolved items | One cross-policy card has no within-candidate comparison; seven authored cards have no saved judge measurement. |
| Five uncertain items | Excluded from resolved comparisons. |
| 115 pair appearances in resolved items | 97 compared appearances; 95 unique within-candidate pairs after two repeated appearances are deduplicated. |
| 95 measured unique pairs | 95 agreements, zero disagreements; every expected relation is distinct. |

**MEAS2-M1 (observed coverage limit).** These are selected, dependent development
comparisons, not an accuracy estimate,
Kappa result or population reliability measurement. In particular, there is no
measured equivalent pair here: the result cannot establish equivalent-answer
detection or rule out a judge that separates everything. Authored duplicate and
paraphrase controls still need official measurements. Unresolved full sets and
the blocked-water boundary remain uncertain, rather than becoming agreement data.
The [MEAS-01 results](MEASUREMENT-AUDIT-RESULTS.md) retain the model-only review,
instructional blinding, unknown exact model identifiers and shared-model dependence
limits. No human validation or unseen evaluation was added.

The [independent engineering review](conformance/meas02-independent-review.json)
reproduces the source-bound comparison and eight additional counterexamples,
including missing measurements, context disagreement and source substitutions.
It checks provenance and program behavior, not new semantic ratings.

## Why partition changes affect both metrics

The pinned [official scoring source](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/score.py)
selects each class's first answer as its head and scores those heads. Distinctiveness
counts classes; utility credits only a class's first occurrence, with the declared
position weights and patience. Later duplicates receive no utility credit even if
their text is better. This is also the contract in
[DESIGN section 5](DESIGN.md#5-measurement-contract).

Merging or splitting classes can therefore change both the distinct count and
which answers receive quality credit. Changing order can change heads and weights.
A newly required head may have no saved quality score, so a changed partition
does not generally support a valid utility recomputation from the existing scores.
This slice performs no quality rescore, new numerical intervention or corrected
ranking. Original recorded partitions, utility, distinctiveness and rankings remain
unchanged.

**MEAS2-F1/F2 (diagnostic guards).** Comparison binds the exact task hash as well
as source answer identities: changing the task while keeping answers must be
rejected. The replay tool also requires assertion checks; optimized Python must
stop before external imports or source consumption. The delivery record retains
the actual negative controls and their final verification. These checks do not
change the official evaluator or agent.

## Reproduce the offline replay, optionally

With the preserved private inputs, pinned reference source and existing locked
reference environment available, run this from the project folder. The output's
parent directory must exist; choose a new filename:

```powershell
.\runs\reference-env\Scripts\python.exe docs/conformance/meas02-official-replay.py --out runs/reviews/meas02-replay-copy.json
```

This runs once in the same window, needs no API keys, spends no provider money and
changes no historical records. It writes a new diagnostic JSON only after checks;
an existing output is preserved and causes refusal. Ctrl+C stops the process. An
interruption may leave no output or a partial JSON file; keep it as incomplete
evidence, never as a pass. A fresh clone does not include the private historical
inputs or prepared reference environment.

## Remaining live audit and scientific limits

The next MEAS-02 measurement needs fresh official partition judgments on the
declared controls, including equivalent examples and the unresolved boundaries,
plus repeated full sets and display-order variants. Preserve raw replies, actual
fold/repair paths and every physical SDK attempt; a request count alone does not
prove leniency. This remains partition assessment, not candidate generation,
quality rescoring, a full benchmark result or held-out evaluation.

The [dated readiness note](conformance/meas02-paid-readiness.json) and
[concrete target proposal](conformance/meas02-target-proposal.json) specify 40
proposed target judgments: the 22 pack items once, six repeated full sets and two additional display
orders for each full set. Its up-to-120 semantic folds at a three-fold limit do
not bound SDK transport attempts or retries. This is a proposal, **not an approved
allocation, live price profile or spending command**. Its October 20 model/pricing
observations cite official OpenAI documentation, but account/project tier,
applicable maximum charges and physical-attempt allowance remain unverified.
Refresh and bind those facts before paid execution; unused historical balance
provides no new authorization or completion guarantee.

The broader EVAL-02 gate still requires frozen finalists, matched baselines and
resources, declared coverage, uncertainty and the human sample retained by
[DESIGN section 11](DESIGN.md#11-failure-modes-and-acceptance-gates).
This offline replay and model-only development comparison do not establish human
agreement, generalization, useful-diversity improvement or scientific validity.

## Prepared native study interface

The [materializer](conformance/meas02-materialize.py) turns the exact frozen pack
and target proposal into four batches: 22 baseline items, six fresh same-order
repeats, six full sets under seed 0 and six under seed 20261020. Native input
contains each literal prompt and its original answer order. The official code
applies the display permutation; the host never pre-shuffles or unshuffles twice.
Each native row uses its unique target ID, avoiding collisions between the many
historical cases with the same original task ID. The bound target table and
development provenance retain original item/answer/source identities separately.
Review labels and expected classes are not sent to the judge.

The [study controller](conformance/meas02-native-audit.py) uses the existing
`Gateway`, `NativeSession` and shared `Authorization`. Its library functions
are deliberately separate from the old pilot command:

| Interface | Function |
| --- | --- |
| `prepare_native_audit(directory, descriptor=..., authorization=..., review=...)` | Validate the frozen controls and source selection, materialize the four native inputs and bind four original request owners to an existing authorization. Reads no keys and makes no provider calls. Partial preparation remains incomplete. |
| `check_native_audit(directory)` | Check source bindings, retained completions, owner state, next account review and immediate funding without keys, workers or provider calls. Completed-only reuse needs no live profile refresh. |
| `run_native_audit(directory, transport=...)` | Run or recover those original owners. Retain raw replies, every physical attempt, partial artifacts and unknown-charge holds. Actual spending requires an explicitly paid transport, reviewed profiles, keys and active shared authorization. |

The descriptor's exact fields are `format` (`buddha.meas02-native-audit.v1`),
absolute `pack`, `proposal` and `provenance` paths, and `native`. The latter
contains the existing Selection, five component roots, installed environment,
native hooks, executor settings without mounts, model/profile mapping and local
monetary/call ceilings. Its Release lists the four official partition commands
in that occasion order, with concurrency one. Inputs, source bytes, descriptor,
profile and runtime inventories are frozen before dispatch. No source change to
the official evaluator or the version-neutral application is required.

The proposed live judge is the explicit Luna partition profile used by the
reference configurations and historical diagnostics. It is not the bare CLI's
Opus default; see the [conformance distinction](NOVELTYBENCH-CONFORMANCE.md#nb-c3-request-and-execution-differences-remain-open).
Freeze the exact model and account profile before paid comparisons. A different
judge is a different instrument. This preparation reports no benchmark score.

These are **supplied audit controls**, not agent-generated C1 Answers. Short
two/four-answer cards exercise a CLI that accepts variable response counts; they
are not ten-answer benchmark scores. The Release's ten-answer TaskSet contract
does not certify these supplied controls as a generated population. This path
performs no generation, quality scoring or benchmark aggregation.

The four owners share one authorization: their local ceilings do not multiply
its dollar or physical-attempt limit. A fresh repeat has an empty native cache
and a distinct owner; its scientific body matches baseline. Recovery preserves
the original owner, rebuilding an interrupted attempt from completed raw
receipts without charging again. Completed batches bind literal artifact/report
inventories and an authority completion anchor. Missing or changed evidence,
unanchored completion, outstanding uncertainty or insufficient verified funding
stops progression. Hard interruption may retain the exclusive running lock;
the controller never assumes that a process is dead or replaces its owner.

The portable checks can run once in this PowerShell window:

```powershell
python -W error::ResourceWarning -m unittest discover -s tests -p 'test_meas02_*.py'
```

This uses temporary fixtures and simulated containers/HTTPS, needs no Docker or
API keys and spends no provider money. It checks materialization, accounting,
source binding, output coverage and recovery. Ctrl+C stops it; temporary test
files may remain after a hard interruption.

The separate full-module proof requires the preserved reference files and the
previously reviewed local CPU Docker image:

```powershell
python docs/conformance/meas02-native-probe.py --out runs/reviews/meas02-native-proof-copy.json
```

This runs once in the same window, uses synthetic credentials and simulated
provider replies, and spends no provider money. It runs the unchanged official
CLI and SDK in network-disabled containers, writes new proof artifacts under
`runs/reviews`, and refuses to replace an existing output file. Choose a new
filename whose parent exists. It can take several minutes. Ctrl+C stops the
foreground process; retain interrupted evidence as incomplete. A fresh clone
lacks the prepared image, private history and reference environment. Simulated
reply groups test mapping and execution, not semantic accuracy or equivalence
detection by a real model.

The original preparation supplied no paid command, new allocation or
account-specific profile. The operator entry below now provides explicit live
execution over supplied authority; it creates no allocation and grants no
spending permission. The original target proposal and readiness note remain
historical proposals rather than being rewritten as approvals.

The [actual native proof](conformance/meas02-native-proof.json) passes all 40
target mappings and request-render hashes, six fresh identical-body repeats,
interruption/resume and keyless completion reuse, plus shared-money and unknown
stops. Its 42 physical sends are simulated; real provider calls are zero. The
first failed proof assumed native requests arrived in input order. It is
retained; the corrected fixture identifies targets by their bound batch and
unique scientific-render hash. Concurrency one does not promise row arrival
order. The official code and controller required no change for this fixture fix.
The [independent boundary review](conformance/meas02-native-independent-review.json)
and [delivery record](conformance/meas02-native-delivery.json) retain source pins,
negative controls, completed checks and their exact limits.


## Operator commands

The [local launcher](conformance/meas02-run.py) uses the existing hidden-key
helper and the same study controller. It does not change official requests,
answer order, evaluator code or the application's version-neutral modules.
A reviewed descriptor, account review and active shared authorization must be
supplied first. The user has now approved the separate $15/120-attempt allocation
below, with Standard/default processing and public pay-as-you-go pricing. The
credential fingerprint is bound locally before the first request; no key is
supplied in chat or saved in a file.

The following are command forms for the reviewed files, **not instructions to
start a paid run now**. `$studyPath`, `$descriptorPath`, `$authorizationPath` and
`$reviewPath` stand for those supplied paths. Run from the project folder in the
same PowerShell window; a new window is unnecessary.

```powershell
python docs/conformance/meas02-run.py prepare --run $studyPath --descriptor $descriptorPath --authorization $authorizationPath --review $reviewPath
```

This runs once, writes the study inputs and four request-owner records, and
attaches them to the existing allocation. It asks for no keys and makes no model
calls. It does not create money or multiply the shared limits. Partial preparation
remains incomplete; keep its records if it stops. Ctrl+C stops the command.

```powershell
python docs/conformance/meas02-run.py check --run $studyPath
```

This runs once without keys or provider spending. It checks the frozen inputs,
source, all original owners, saved completion evidence and the next unfinished
batch's account/funding conditions. It prints `ready` or `complete` and identifies
the next occasion. It opens the existing authority/ledger interfaces; it is not a
historical read-only viewer. A ready result is a current check, not a promise the
whole study can finish. Execution repeats these checks after key entry.

```powershell
python docs/conformance/meas02-run.py run --run $studyPath --live --prompt-keys
```

After the new allocation is approved, this runs or continues the study once and
can spend within its shared limits. It checks first, then requests only the
reviewed OpenAI key if absent from this process's environment. Paste once and
press Enter: characters remain hidden. A received-key message confirms local
entry, not provider authentication. The key's fingerprint must match the reviewed
account before containers start. Prompted keys are removed when execution exits;
pre-existing environment values are left as they were. Never send keys in chat.

After key entry, a starting message and immediate progress line appear. A
heartbeat repeats every ten seconds during native startup and provider waits.
It shows shared attempt records, recorded spending, held money and the cap.
An attempt record may exist before transmission; recorded spending is the
conservative local calculation, not a reconciled invoice. Held money covers an
unfinished request and is not an extra charge. Progress-observer failure does
not change request accounting or grant permission to continue past a stop.

Ctrl+C cancels foreground execution and retains replies, original owners and
outstanding holds. Continue with the same command and study directory only when
the retained state permits it; a lost reply or unknown payment requires review.
Do not create a fresh directory or allocation to escape a hold. A hard kill can
leave the running lock; its presence alone cannot prove whether a writer lives.

```powershell
python docs/conformance/meas02-run.py run --run $studyPath
```

After all four batches complete, this runs once to recheck and reuse their saved
completion evidence, without keys or new provider calls. Unfinished work refuses
without `--live`. Exit 0 means successful preparation/checking or a completed
run; exit 3 means an incomplete run, 130 means Ctrl+C and 2 means a stopped or
invalid command. A cancellation or incomplete
result never prints successful completion.

**MEAS2-O1/O2 (reproduced operator guard failures).** A small unrelated reservation
must not disguise inadequate funding, and an inactive later owner must stop the
study before an earlier owner spends. The shared preflight now enforces both.
A full existing unsent reservation can only be reused under the original request
identity; another owner's hold is no credit. Source changes after checking are
also rechecked before execution. **MEAS2-O3** rejects an oversized credential,
even if its fingerprint matches, before worker startup. The
[independent review](conformance/meas02-operator-independent-review.json) records
the actual failing checks and their fixes. These are engineering findings, not
new evidence about semantic judge accuracy.

The separate [operator native proof](conformance/meas02-operator-native-proof.json)
exercises this actual launch path over all 40 targets: hidden input, immediate
progress, received-reply interruption, original-owner recovery and completed
keyless reuse. It records 42 simulated sends and zero real calls. Simulated
credentials never leave the fixture; temporary environment values are restored.
The earlier native proof remains unchanged as a separate historical record.
The [operator delivery](conformance/meas02-operator-delivery.json) records the
final checks and their limits. No synthetic response establishes the real
judge's semantic accuracy or stability.


## Earlier allocation proposal

The earlier proposal was **a new $5 shared cap
and at most 120 physical API attempt records** for the 40 frozen judge targets,
across all four occasions. Use the explicit `gpt-5.6-luna` partition profile,
unchanged official requests and the user-confirmed Standard/default project
setting. No generation, search, quality rescore or extra targets are included.
The original experiment's unused balance is not transferred or reopened.

Under public Standard pricing, the proposed conservative profile uses maximum
input/output rates of $0.50/$1.80 per million tokens, including the long-context
and default cache-write upper envelope. Reserving the entire 1,050,000-token
context as input plus 128,000 output tokens requires **$0.7554 before each
request**. This deliberately exceeds a jointly feasible input/output usage: the
model's actual maximum input is 922,000. The safety envelope leaves the native
wire unchanged rather than inserting a smaller output cap or tier override.
See the official [pricing](https://developers.openai.com/api/docs/pricing),
[model limits](https://developers.openai.com/api/docs/models/gpt-5.6-luna) and
[cache billing](https://developers.openai.com/api/docs/guides/prompt-caching).

The $5 cap does **not** guarantee completion: it covers only six such worst-case
requests. Ordinary short responses release unused reservations, which can let
many more targets finish. No credible measured forecast exists yet for this
study. A funding stop is accepted as an incomplete result; retain all replies
and holds, with no automatic top-up, replacement owners or extra targets.
The 120 physical-attempt cap is separate from the proposal's 120 possible
semantic folds: native SDK retries may require additional physical attempts,
and the shared cap can stop them. Unknown payment stops further spending.

Before creation or execution, confirm that public prices apply (custom/Scale
terms need their own reviewed envelope), bind any required account headers or
explicitly none, and produce the credential fingerprint locally through hidden
entry. No raw key belongs in chat or a saved review. That $5 suggestion was not
allocated. The approved $15 allowance below supersedes it.


## Approved $15 live audit

The user approved **$15 shared across all four occasions**, asked the controller
to choose the attempt cap, and explicitly accepted partial completion provided it
is recorded as a partial result with the reason. The selected limit is **120
physical attempt records** for the same 40 targets. SDK retries share that limit;
it is separate from the nominal 120 semantic-fold allowance. No automatic top-up,
new targets, generation, search or quality scoring is included. The
[approval record](conformance/meas02-live-approval.json) preserves the exact scope.

Of the 40 targets, 23 have resolved development expectations and 17 retain
uncertainty, including repeated/order variants. The resolved targets contain
377 expected-distinct and eight expected-equivalent pair appearances. These
share answers and contexts; they are not independent observations or human
gold labels. Agreement excludes uncertain expectations. All 40 still matter
for native coverage and the declared repeat/order diagnostics.

Public pay-as-you-go pricing and Standard/default project processing are
user-confirmed. The conservative reservation remains $0.7554 per request: $15
can cover 19 full worst-case reservations, so completion of 40 targets is not
guaranteed. Short responses release unused money for later requests. Local
recorded costs can exceed the invoice; existing reservations and unknown holds
remain separately visible. Each native batch has a configured 15-minute worker
limit; the host transport has a 60-second response timeout. A timeout can leave
an unknown charge and stop the audit with its reservation retained.

A separate existing authorization and immutable configuration are prepared under
`runs/meas02-live-20261020`. Its four owners share one $15/120 allowance; they do
not receive $15 each. Credential review and study preparation occur only through
local hidden entry. The original $50 authorities, costs and unknown hold remain
unchanged. The earlier native/proposal records remain historical evidence.

The [single-session handoff](conformance/meas02-live.py) will check exact approved
source/configuration and allocation before asking for a key. Use a project-scoped
inference key from the Standard/default public-PAYG project you verified, with no
organization/project override. The confirmation flag below records that manual
assertion; a matching fingerprint alone does not authenticate the account or
prove those account settings. If this is a legacy or ambiguously scoped key,
stop and obtain an appropriate project-scoped key or an explicitly reviewed
routing profile first. Never paste a key into a visible confirmation field.

Local handoff verification passed: 1,025 tests, the confined 40-target study and actual-profile partial-stop/keyless-recovery proofs. The [handoff delivery](conformance/meas02-live-handoff-delivery.json) records the exact pins and limits; hosted PR checks are reported separately.
From this project folder, in an ordinary interactive PowerShell window:

```powershell
python docs/conformance/meas02-live.py --handoff runs/meas02-live-20261020/handoff.json --live --prompt-keys --confirm-project-key
```

This runs once and can spend within the approved $15/120 shared allowance.
`--live` enables unfinished work; `--prompt-keys` requests the missing OpenAI key
without displaying it. `--confirm-project-key` confirms the project/key condition
above. Paste once at the hidden key prompt and press Enter. The same process
records only its fingerprint, prepares the original owners and runs the study,
so there is one key entry. It restores/removes the temporary key on exit. A new
PowerShell window is unnecessary. Progress appears immediately and repeats every
ten seconds. Ctrl+C cancels; rerun this same command only when retained state
permits recovery. It never creates another allocation or replaces an owner.

On full completion, `study/report.json` records all four anchored batches.
A clean stop or native interruption records an append-only observation in
`study/observations/`, with `status: incomplete`, `result: partial`, explicit
reason/codes, saved native evidence and accounting. Completed sealed targets are
separate from validated rows in the stopped attempt; earlier unsealed observations
remain separate references. A provider reply count is never target coverage.
Money, attempt limit, unknown payment, protocol and execution failures are
reported from evidence rather than guessed. If multiple blockers apply, retain
all proven codes. Observation writes must succeed before a saved partial result
is claimed. A hard process kill or invalid/corrupted source can prevent a final
observation. A native output that claims completion but fails the host's
coverage/content checks also stops as invalid evidence, retaining its native
files and receipts without claiming a saved aggregate partial result. These
records remain incomplete and are not promoted.

The console prints a short JSON result and, for a partial result, the observation
filename and reason. Send back "complete" or "partial" and that filename; the
saved files here support the review without pasting keys or long terminal logs.
I will check coverage, raw replies, costs/holds, repair paths, equivalent controls,
repeats and order effects, preserving original benchmark scores.

Optional accounting inspection:

```powershell
python -m buddha authorization-inspect --authorization runs/meas02-live-20261020/authorization.sqlite3
```

This runs once in either PowerShell window, prints this audit's cap, recorded
attempts, spending and held money, asks for no key and makes no provider calls.
It does not resume the audit. No command is needed while the foreground runner's
progress output is sufficient.
