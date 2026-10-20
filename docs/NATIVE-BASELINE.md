# Frozen-agent native baseline

BENCH-02C3C3 composes [isolated fixed-seed generation](FROZEN-SEED.md) and
[confined native evaluation](CONFINED-NATIVE-EVALUATION.md). The host controller
in `buddha.baseline` interprets frozen artifact-flow configuration. It imports
no official evaluator or agent implementation, contains no benchmark formula
and does not select or optimize an agent. [PLAN.md](PLAN.md) remains the roadmap.

## Library interface

| Function | Purpose |
| --- | --- |
| `prepare_baseline(directory, descriptor=..., authorization=..., review=...)` | Validate the configuration and selected files, create a fresh baseline directory and bind its first generation owner to the existing shared authorization. Reads no keys and makes no provider calls. |
| `run_baseline(directory, transport=...)` | Run the configured stages or resume their original owners. Preserve every attempt, raw reply and uncertain hold. Actual spending still requires the caller's paid transport, reviewed profiles, keys and active shared authority. |

These are library interfaces, not a newly enabled paid command. Preparing a
baseline does not create or extend the user's authorization. The historical
$50 experiment and its inactive allocations remain unchanged.

The baseline descriptor has format `buddha.native-baseline.v1` and exactly these
fields:

| Field | Meaning |
| --- | --- |
| `tasks` | Absolute path to the source-bound, explicitly selected C1 TaskSet. |
| `generation` | Frozen generation Selection, component roots, existing agent descriptor path and local monetary/call ceilings. |
| `native` | Separate native Selection and roots, installed environment inventory, configured module/cache/call/SDK hooks, executor settings, host model mappings and local ceilings. The controller supplies the actual input mounts. |
| `stages` | One entry per `Release.commands` item, in order. Each names already available input artifact paths, new required output paths with their population-ID field, and whether model calls are allowed. |

Generation and native runners have different file inventories. Their Selections
must agree on the Release and frozen agent identity, while retaining separate
runner/environment identities. Field names, answer count, module paths, CLI
arguments, artifact paths and hooks are data supplied by the selected driver.
This implementation supports the existing text/Python/JSONL capability envelope
and a separate final native summary command. Unsupported outer capabilities
remain explicit compatibility failures, not silent instrument changes.

## Exact inputs and ordered stages

The first immutable owner binds the descriptor, selected TaskSet, generation
descriptor, actual controller/worker sources and reviewed seed bytes. Later
owners are created only after their literal inputs exist. They bind those
inputs, the original C1 answer file and prior immutable completion records under
the same shared authorization. Existing manifests are never rewritten to add
future output hashes. Output directories and mutable databases stay outside
selected component roots.

The controller checks the actual exported C1 file against its generation report,
parses its source/population/agent links, and materializes exactly
`Answers.native_bytes()`. The exported file digest, canonical Answers fingerprint
and native-byte digest are different identities; generation's trailing newline
does not become part of the logical canonical artifact identity. Original row
metadata and literal weak answers remain intact; emitted new metadata is `{}`.
Generation settings remain in separately bound provenance. Optional native model
labels are not inserted over original row fields.

Each required population result must contain every selected typed ID once,
without omissions, duplicates or foreign rows. Numerical values and official
row projections are not rewritten by this check. Native unscored rows are
retained. The final summary is an opaque byte artifact: even a native `NaN`
is preserved rather than coerced into a host score. Complete native coverage
does not by itself establish promotion eligibility, utility or meaningful
distinctiveness.

The final summary has an empty model mapping and a separate transport with paid
calls disabled. Its ordinary positive minimum Gateway ceiling is not permission
to dispatch a request. An unexpected worker request fails before a Gateway model
execution. On success, every stage including summary seals its output/report
hashes and deactivates its owner with that seal digest, independently anchoring
completion in the shared authorization record.

## Files and recovery

| Location | Meaning |
| --- | --- |
| `context.json` | Immutable pointer to the frozen baseline descriptor, bound by the first owner. |
| `owners/0`, `owners/1`, … | Original generation and native Gateway owners, each with its own raw receipts and ledger, all attached to the same authorization. |
| `attempts/<stage>-<attempt>` | Preserved session reports, partial outputs and literal artifacts. Retrying creates a fresh attempt directory. |
| `completed/<stage>.json` | Immutable completion record binding the owner, report and every file of a validated successful attempt. |
| `native-answers.jsonl` | Exact source-derived native generation rows. |
| `staging/<stage>` | Only the configured input files mounted into that native stage. Opaque host source filenames map to declared native destination paths. |
| `report.json` | Published after the entire selected baseline succeeds. References native summary bytes and distinct stage evidence; makes no optimization or improvement claim. |

Recovery reopens each existing owner and validates completed stages. An
interrupted stage rebuilds its output through a fresh attempt, reusing already
completed raw receipts without new sends or charges. A new owner is not resume.
An interruption after publishing a completion record but before anchoring its
digest through deactivation is a narrower exception: resume refuses to bless
that existing unanchored record. It retains the owner, receipts and files for
the REC-05 recovery/doctor work instead of guessing their authenticity.
Unknown/dispatched operations retain their holds and stop further spending,
including across other owners of the shared authorization. Incomplete command
reports and missing/invalid required artifacts prevent downstream execution.

One baseline can run at a time. A hard process kill may leave `running.lock`;
the controller refuses to guess that a concurrent process is dead. Normal
exceptions and Ctrl+C release the foreground lock, preserving original owners
and attempts. Worker wall limits still do not bound synchronous host accounting
finalization. This is the reviewed local Docker/OS trust model, not a malicious
daemon or virtual-machine security claim.

The portable command below checks the composed controller once in the current
PowerShell window. It creates temporary fixtures, uses mocked containers and
HTTPS, requires no Docker/API keys and spends nothing. It checks artifact
handoffs, selected coverage, unchanged-owner recovery and spending stops.
Ctrl+C stops it.

```powershell
python -m unittest discover -s tests -p test_baseline.py
```

Complete module execution and direct official comparisons are separately
recorded by the offline container probe; they do not establish semantic judge
accuracy or general improvement. Configuration-only cross-release upgrade and
clean retirement remain BENCH-03C; arbitrary source evolution remains SRC-01.


## Recorded offline execution

Review findings are retained here and mapped back into the single living plan:

| ID | Evidence and disposition |
| --- | --- |
| C3C3-I1 | Review reproduced an active owner's existing unanchored seal being accepted and later blessed. Resume now requires the independent existing authority anchor. The narrow interrupted-publication usability case remains REC-05 work. |
| C3C3-I2 | Review reproduced transient configuration/report substitution despite restored files. Consumed configuration, seals and reports now require their expected byte digests; controller regression tests cover both seal and report substitution. |
| C3C3-I3 | A final-output mutation guard is tested after implementation: changing summary bytes after stage deactivation cannot acquire a new successful top-level digest. No pre-fix RED is claimed for this check. |

[The full container proof](conformance/nb02c3c3-baseline-evidence.json) uses two
selected real curated tasks and ten fixed-seed answers each. Generation takes
20 mocked calls, unchanged official partitioning two, scoring four and summary
zero. Native artifacts and six SDK request-body captures match unchanged direct
oracles, allowing only typed-ID JSONL row-order normalization. The native source,
SDKs and declared CPU environment variant are the same sealed references used
by the individual command proofs.

The proof interrupts after the first scoring response, preserves that completed
raw receipt and resumes its original score owner with only three new sends.
Completed keyless reuse adds no containers, sends or charges. Four owners share
one synthetic authorization; all are inactive after completion. Twenty-one
watched source/configuration files and ten Gateway-core seals remain unchanged.
No agent or official scientific implementation executes on the host. All 26
physical requests are mocked; this is no real model-spending or improvement
measurement.

BENCH-03C repeats this unchanged probe after the generic-helper extraction;
[its separate regression evidence](conformance/nb03c-official-regression-evidence.json)
binds the new nine-module core with the same native artifacts and call counts.
The original ten-module record above remains historical. See
[upgrade and retirement](RELEASE-UPGRADES.md) for the composed release checks.

The optional command below repeats that proof once in the current PowerShell
window. It needs the previously prepared C3A and C3B Docker Linux images, the
sealed official source checkout and C3B installed-inventory JSON under
`runs/reviews/`. It installs/downloads nothing, uses fake keys and mocked HTTPS,
and makes no actual API calls. It deliberately interrupts then resumes its own
score stage, performs keyless reuse and compares direct native execution.
It retains a uniquely named ignored fixture directory with receipts and attempts,
and writes `runs/reviews/nb02c3c3-baseline-evidence.json`; committed evidence and
historical runs are unchanged. Allow several minutes. Ctrl+C stops it and
attempts owned-container cleanup, retaining partial evidence.

```powershell
python docs/conformance/nb02c3c3-baseline-probe.py
```

The larger native environment's known advisories, CPU binary variant, license
limits and intentional uncertain-payment retry stops remain documented in the
[confined evaluator guide](CONFINED-NATIVE-EVALUATION.md). This bounded offline
conformance result enables no new paid command or allocation. A native baseline
needs no optimizer projection; semantic calibration and held-out improvement
require their own evidence.
