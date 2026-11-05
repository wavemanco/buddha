# One forward source-improvement edge

This interface joins existing stages in order: run the prepared parent screen,
write its complete development feedback, run one fixed improver, then screen its
materialized child under the same task and comparison settings. It does not
reconstruct the whole search history between these stages. Saved stage reports,
original owners, spending records and source lineage remain authoritative.

**This candidate is not cleared for a live run.** The commands below describe the
interface; they are not a funded handoff. Live use still needs the reviewed exact
source, qualification, approved spending allocation and checked preparation.
There are no newly authorized paid calls or long runs. The original
three-development/26-final-task comparison and both plain-model controls remain
open; one development edge cannot replace that study or establish improvement.
[PLAN.md](PLAN.md) owns current approvals and sequence.

## Prepare through Python

There is no preparation CLI. A reviewed preparation script uses the existing
screen declaration, fixed improver declaration and shared authorization:

```python
from pathlib import Path
from buddha.authorization import Authorization
from buddha.source_forward import prepare_source_edge

prepare_source_edge(
    Path(r"C:\path\fresh-edge"),
    parent=Path(r"C:\path\prepared-parent-screen"),
    improver=improver_section,
    authorization=Authorization(Path(r"C:\path\approved-authorization.sqlite3")),
)
```

This creates a new edge definition and binds its original inputs. It makes no
model requests and does not create or enlarge a spending allowance.
`improver_section` is the already reviewed generation-section dictionary for the
fixed improver, including its selected source, model profile and execution limits;
it is not a model name or arbitrary replacement prompt. Paths must be absolute.
The handoff must supply the exact `edge.json` hash and checked source location.
The placeholder paths above do not name an approved run.

## Run the prepared edge

From the exact source checkout identified by the approved handoff:

```powershell
python -m buddha source-edge-run --run C:\path\prepared-edge --definition-sha256 APPROVED_EDGE_JSON_SHA256 --live --prompt-keys
```

This runs once and can spend from the edge's existing shared allowance. It first
checks the original definition and controls without reading keys. It then asks
for missing OpenAI/Anthropic keys needed by the selected profiles: paste each key
once and press Enter; no characters appear. Keys already set in this PowerShell
process are reused. Keys entered at the prompt are removed from the environment
when the command exits. They are not written to the run or passed to candidate
code.

A new PowerShell window is fine. Keep that window open until the command returns;
no second window is required. Press Ctrl+C to stop. Keep the whole run directory
for inspection; an uncertain request can retain a spending reservation and must
not be retried blindly. Repeating this command uses the same edge and original
stage owners, rather than creating another experiment. An already complete edge
is checked without asking for keys or making model calls.

During execution, a progress line appears about every ten seconds with elapsed
time and the shared allowance's recorded attempts, costs and held money. It is
an observation, not evidence that a new answer or stage has finished.

The final JSON describes either the completed edge report or a saved incomplete
observation. `complete` means this declared edge finished; it does not mean the
child improved. An incomplete result retains its stage and reason. Do not start
a fresh edge to hide or reset that result.

## Inspect a complete saved edge

```powershell
python -m buddha source-edge-inspect --run C:\path\prepared-edge --definition-sha256 APPROVED_EDGE_JSON_SHA256 --report-sha256 SAVED_REPORT_JSON_SHA256
```

This checks the caller-pinned definition and complete report against the original
stage evidence, then prints the verified report. It runs once, reads no keys,
starts no worker, makes no model requests and changes no files. It can run in the
same or a separate PowerShell window. Ctrl+C stops the read. The two hashes come
from the checked handoff and retained report; supplying different hashes does not
make altered evidence valid.

The selected official evaluator, source-screen comparison rules and provider
accounting remain those of the existing stages. The generator model stays
configurable; reasoning models default to low effort under the pinned protocol.
Historical search/study readers remain available for their original records;
this edge does not migrate or rewrite them.
