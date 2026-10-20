# Confined native partition, score and summary execution

BENCH-02C3A/B run the complete, unchanged official LLM partition, scoring and
summary entry points in separate Linux containers. These are engineering
conformance slices. They supply no new paid CLI, model profile, funding
allocation, frozen-agent generation, or improvement claim.

The reference remains NoveltyBench commit
`64a23be6b18ec1dacc298830aab276061b6e143c`. The installed runtime and its
explicit AnyIO security overlay are recorded in
[the original runtime preparation guide](conformance/nb02c3-runtime.md). Full
partition imports use [a separately sealed CPU environment](conformance/nb02c3b-cpu-review.md),
including a confined two-build ROUGE wheel. The original CUDA dependency
closure stays held because of actual license restrictions. The CPU variant
retains known advisories and is neither exact upstream binary-lock equivalence
nor an image for arbitrary evolved agent code. Official evaluator source and
SDK versions remain fixed; no missing-library stubs or extracted substitutes
stand in for complete official modules. The environment JSON retains its
preparation-stage metadata; separate import and delivery records report later
observations without rewriting the configuration used by those checks.

## What executes

`buddha.executor.run_container()` starts a fresh, owned container for one
command. `buddha.native_worker` imports the complete configured official modules
and invokes their actual `main()` function with the recorded arguments. The
host does not copy the partition or utility formulas, construct judge prompts,
replace native scorers, or reinterpret a native parser failure as success.

The release configuration chooses module names, entry points, arguments, cache
parameter mappings, logical call hooks and public SDK constructor slots.
Identity-based alias replacement covers references imported into other selected
modules. Cache context uses the actual instance, typed ID, native evaluation key,
command and output path. Child ordinals are allocated when coroutines are
created, before concurrent scheduling. Equal request bodies therefore do not
collapse different samples. SDK parsing, retries and fallback remain native.

The worker has dummy credentials and an HTTP transport view with no provider
sender. It sends bounded requests over a private, correlated JSON-lines
channel. Only the host's existing `Gateway`, attached to shared authorization,
can send a physical provider request. Raw response bytes return to the original
SDK. Unknown liability or exhausted authority escapes native SDK retries and
stops further dispatch; an unknown call retains its hold. The bridge serializes
physical requests and does not reproduce network timing. On a multi-head parser
failure, native concurrent cancellation can produce different request counts
while leaving the same failed status and partial artifacts. Deterministic
single-head failure fixtures check parser/body parity; successful multi-head
fixtures separately check complete outputs and distinct call identities.

## Frozen ownership and confinement

`buddha.native_run.NativeSession` accepts a separately frozen command descriptor,
a real owning Gateway and a fresh output path. Its constructor verifies the
release selection, exact mounted source inventories, explicit model-to-profile
mapping and every input file. The descriptor and the nine actual host/runner
source files must already be invocation inputs. An innocuous staged copy cannot
stand in for different executing controller code. The context digest must identify a frozen
input; this low-level session does not yet prove its derivation from C1
`TaskSet`/`Answers` or enforce a selected experimental population. That binding
belongs to the frozen-agent controller gate. Configuration mutation after
validation fails closed before worker execution or a later request.

The executor verifies the immutable Linux amd64 image and the actual created
container configuration before starting it. It uses a nonroot user, read-only
root and source mounts, no network, no capabilities, no new privileges, private
process/IPC boundaries, bounded memory/CPU/processes, and bounded non-executable
scratch space. Agent and evaluator mount roles cannot be combined. Provider
keys, host home, proxy credentials, Docker sockets and final-data paths are not
mounted. It drains bounded diagnostics without publishing their text, removes
only the exact container whose ownership it verified, and reports uncertain
cleanup as failure.

The worker verifies the installed RECORD/tree inventory, official and runner
bytes, module origins and configured aliases. These checks run before paid
requests and at completion. Explicit image-specific fileless modules and their
sealed loader owners are recorded; arbitrary unknown origins are rejected.

An actual adversarial probe demonstrated that `python -B` still reads cached
bytecode. The executor now redirects bytecode lookup to the absent, read-only
`/__absent_bytecode_cache` path. The worker checks that condition, and selected
official/runner inventories reject `.pyc`, `.pyo` and `__pycache__` content.
The real regression leaves the conflicting adjacent cache present and confirms
that Python executes the recorded source.

## Configured dependency-generated modules

A dependency can legitimately create modules while importing. The protected
runtime contract may declare `derived_modules` by exact module name, separately
from the existing measured fileless-module list. These are generic declarations;
the worker contains no Torch or benchmark-version branches.

A class declaration has `kind: "class"`, `module`, `qualname` and `owner` (a
relative installed-file path). The worker checks the actual module class and its
constructor's defining namespace, exact class-object identity, code filename and
sealed owner bytes. Dictionary reads avoid invoking dependency-defined dynamic
attribute lookups while auditing. A class reusing another class's constructor
cannot satisfy the identity check.

A generated-source declaration has `kind: "source"`, `root`, `basename`, `sha256`
and `owners` (relative installed-file paths). Only private `/tmp` or `/scratch`
roots are supported. The worker requires a canonical absolute regular file,
matching module origin and basename, exact source bytes, no link aliases and
sealed owner files. Neither an undeclared generated module nor a different file
in temporary storage is accepted. These guards run before requests and at the
final audit; the host independently matches the reported declarations, owner
inventory and source hash. A review regression specifically rejects `..`, `.`
and repeated-separator path aliases at the worker boundary.

The CPU profile measures six module-class declarations and one 2,355-byte
source module generated from two installed template/generator owners. Its
source hash matched across fresh processes and an independent data-only
reconstruction of the sealed template. [The import record](conformance/nb02c3b-import-evidence.json)
preserves the original rejection, repairs and passing 5,181-module observation.
This is consistency evidence within the frozen source/image and trusted-host
boundary, not attestation of every function object's history or permission to
run arbitrary candidate code in the evaluator image.

## Outputs and recovery

Each fresh host output folder contains:

| Path | Meaning |
| --- | --- |
| `artifacts/` | Literal native files, including configuration, scores, summaries and marked partial outputs when produced. |
| `imports-ready.json`, `imports-final.json` | Module-origin evidence checked against the frozen owner. |
| `report.json` | Separate host execution status, artifact hashes, hook bindings, image/cleanup observations and scoped accounting. |
| `.receive/` | Temporary receiving files; interrupted files are not published as finished artifacts. |

File publication checks portable paths, ordering, case/ancestor aliases, byte
bounds and directory links. Files are published atomically without overwriting
existing targets. A native file named `report.json` stays under `artifacts/`;
it cannot replace the host report.

The host's `calls.completed` counts raw responses delivered to the worker,
including replay. It is not a count of new charges. `gateway_totals` covers the
entire owning Gateway ledger, including earlier calls and unknown holds.
The same immutable invocation can run again in fresh scratch space: completed
raw receipts replay through the actual SDK without keys, dispatches or new
charges. A different cache input is a new frozen invocation; it cannot silently
replace the old one. Dynamic adoption of newly produced partial checkpoints
into an existing invocation is not implemented here. A host process interruption
can leave a folder without a final report; that folder is incomplete. Existing
receipts and unknown holds still govern any subsequent recovery.

Native summary and host execution success do not establish complete experiment
coverage, eligibility for promotion, semantic variety or held-out improvement.
Those remain separate gates in [the living plan](PLAN.md).

## Checks and practical limits

The unit commands below run once in the current PowerShell window, create
temporary fixtures, need no Docker or API keys, and spend nothing. Ctrl+C stops
a foreground check.

```powershell
python -m unittest discover -s tests -p test_executor.py
python -m unittest discover -s tests -p test_native_worker.py
python -m unittest discover -s tests -p test_native_run.py
```

The first checks process ownership, configuration and bounded output. The second
checks the worker channel and configured hooks. The third checks frozen inputs,
shared financial authority, response replay and artifact publication.

With Docker Desktop's Linux engine running and the reviewed local runtime image
already prepared, this command performs real confinement attacks. It runs once
in the same window, creates and removes its own temporary containers, writes
ignored evidence under `runs/reviews/`, needs no API keys and makes no paid calls.

```powershell
python docs/conformance/nb02c3-executor-probe.py
```

The worker wall limit terminates the owned container. A host callback that has
already dispatched a request must finish durable accounting before the
controller returns. A socket inactivity timeout is not a guaranteed total
response deadline; this slice makes no bounded host-finalization latency claim.
No background paid sender is abandoned on a worker timeout.

The local Docker daemon, immutable reviewed image and host filesystem owner are
trusted. Docker control metadata is size-checked after capture; this is not a
memory bound against a malicious daemon or a defense against its administrator.
Container isolation is not a virtual-machine security guarantee. The installed
package audit is not a complete operating-system vulnerability assessment.
The frozen seed's generation path and C1 population/answer derivation, composed
release upgrades/retirement and final experiment completeness remain open.

## Complete official partition command

C3B invokes the actual `--alg llm --version 1.1` partition CLI, with its original
parser, shuffled ordering, fold retries, cache keys and partial journals. That
CLI has no fallback option; refusal remains the native failure it produces.
Supported judge/scoring fallback remains covered by its own checks. Native
`SystemExit` is normalized to success or failure only after preserving produced
artifacts; an incomplete native journal is never reported as a complete result.

The direct-versus-funded probe uses the same frozen CPU environment and canned
provider replies. It checks literal native files, status/reason and serialized
request bodies; only JSONL row order is normalized by typed ID. Controls include
poor and empty answers, repair and persistent invalid partitions, refusals,
truncation, multiblock responses, full/partial caches, a changed shuffle seed,
resumed partial failures and unshuffled execution. Additional checks exercise
keyless raw-receipt replay and one-attempt uncertain-payment stops. The latter
intentionally stops native physical HTTP retries to retain budget liability;
it is not unrestricted network-retry parity.

The official final-attempt fold can put omitted answers into separate groups.
That can increase the official distinct count. Preserve that result; inspect
raw judgments and replay the official function separately when auditing whether
classes reflect semantic judgments or native recovery. Call counts alone do
not identify that path, and this observation does not establish the cause of
the earlier repeated-story results. Semantic controls remain in MEAS-01/02.

The optional command below runs this engineering check once in the current
PowerShell window. It needs the pinned official source, both prepared local
runtime images and both installed-audit JSON files described in the runtime
records. The old C3A audit file is a declared prerequisite of the reused research
helper, not a production dependency on the older evaluator. It uses fake keys
and mocked HTTPS, spends no model budget, creates/removes owned containers and
writes ignored evidence under `runs/reviews/`. Temporary synthetic accounting
fixtures are removed at completion; actual experiment records are unchanged.
Ctrl+C interrupts the check and attempts owned cleanup; rerun for a complete
proof after an interruption.

```powershell
python docs/conformance/nb02c3b-funded-native-probe.py
```

The separately recorded [partition proof](conformance/nb02c3b-funded-native-evidence.json),
[score/summary regression](conformance/nb02c3b-score-regression-evidence.json),
[installed-byte evidence](conformance/nb02c3b-installed-runtime-evidence.json),
[import evidence](conformance/nb02c3b-import-evidence.json) and
[independent security review](conformance/nb02c3b-security-review.md) keep their
scopes distinct. Canned judgments establish engineering behavior, not semantic
judgment accuracy, useful diversity, source evolution or held-out improvement.


## Composed selected baseline

[The native baseline guide](NATIVE-BASELINE.md) now connects isolated fixed-seed
generation and exact selected C1 native bytes to these official commands through
one shared authorization and separate immutable stage owners. Its actual
26-mocked-send proof includes mid-score interruption/recovery, completed keyless
reuse and direct command comparisons. The host checks required population
coverage without altering native results or summary bytes. This adds no paid
CLI, new allocation, semantic improvement or arbitrary evolved-source claim;
cross-release compatibility/retirement remains its separate plan gate.
