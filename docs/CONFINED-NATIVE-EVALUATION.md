# Confined native score and summary execution

BENCH-02C3A runs the complete, unchanged official LLM scoring and summary
entry points in separate Linux containers. This is an engineering conformance
slice. It supplies no new paid CLI, model profile, funding allocation, agent
generation, partition evaluation, or improvement claim.

The reference remains NoveltyBench commit
`64a23be6b18ec1dacc298830aab276061b6e143c`. The installed runtime and its
explicit AnyIO security overlay are recorded in
[the runtime preparation guide](conformance/nb02c3-runtime.md). The full partition
module has additional unconditional dependencies; importing only a selected
function or substituting missing libraries would not close that gate.

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
Full partition execution, the frozen seed's generation path, composed upgrades
and final experiment completeness remain open.
