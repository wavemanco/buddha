# Check a saved policy search

`search-verify` checks saved search evidence without resuming the run. It checks
the supplied file fingerprints, request slots, saved replies, benchmark arithmetic,
candidate and proposal history, and any selected shared accounting. It needs no
API keys, makes no model calls and changes no run or authorization file.

The input file lists the allowed run folders, every saved file and its previously
recorded fingerprint. The verifier will not invent missing fingerprints or open
another folder simply because a manifest names it. A fingerprint establishes
consistency with saved bytes; it does not prove that a provider supplied them.

## The preserved pilot

From the project folder, this command checks the completed linked continuation:

```powershell
python -m buddha search-verify --run runs/first-live-continuation-v2 --evidence docs/conformance/rec05b-pilot-verification-input.json
```

It runs once in this window. It spends nothing and needs no separate window.
Ctrl+C stops it. The input was assembled from the existing preservation record,
including both original attempts and the shared authority; it was not generated
by trusting whatever files happen to be present now. It belongs to the recorded
`C:\Users\arvik\code\buddha` checkout and its historical folder bindings.

The output is JSON:

- `verified`: the checked complete result agrees with the selected saved evidence.
- `incomplete`: no complete report is present, and verification reached missing or
  unfinished work or an unpublished artifact. `missing` identifies where it stopped.
  A claimed complete report missing required evidence is an error.
- `unsupported`: the declared format or scientific controls need a separately
  reviewed reader. The command does not substitute today's defaults.
- An `error` response means the evidence is inconsistent, unsafe to read or cannot
  be checked under the supplied input. Nothing is repaired or retried.

Exit code 0 means verified, 3 means incomplete or unsupported, and 2 means an
invalid input or evidence error. These codes help scripts distinguish the outcomes;
read the JSON for the reason.

`costs` describes this run's physical operations, including held reservations.
`checked` counts completed requests and artifacts actually checked; a pending
request can therefore appear in the financial count without being counted as a
checked completed reply. Inherited replies have a separate count and create no
new physical charge.

`shared_accounting` describes the entire explicitly selected authority snapshot.
`shared_scope` names the runs whose local ledgers were matched and any additional
authority owners. A saved report's accounting is checked against its recorded
initial context plus that run's recorded operations; it is not replaced by the
authority's later totals.
`evidence_sha256` identifies the exact input declaration consumed.

## What the result establishes

The reader understands the declared legacy v1.1 policy-search and bounded linked
continuation formats. It consumes saved seeds and controls, never today's default
seed policies. It checks the known pure request and scoring recipes against saved
receipts, without model calls, a broker, executable-runtime reconstruction or
archived Python execution. Archived source is inspected only as bounded data.
Runtime ZIPs support stored/DEFLATE members only. Reads check bounded returned
bytes and indexed seals; they do not establish complete compressed-stream
validity or Python import closure.

An incomplete result describes the checked prefix. It does not certify unreached
scientific artifacts. An initial continuation context containing mutable runs
requires a separately preserved historical snapshot and is reported unsupported;
the preserved pilot's initial imported histories are immutable and checked directly.

This is not provider authentication, invoice reconciliation or a review of whether
stories are meaningfully different. It cannot recover a missing reply, release a
hold, remove a lock, authorize another request or establish that an agent improved.
The original unknown request stays unknown.

`search-inspect` is different: it reconstructs cached search artifacts and may write
them. Use `search-verify` when you want a read-only check of what was actually saved.
The native release/baseline formats have their own evidence paths; this legacy
reader does not replace the modular benchmark interface.

See the [living plan](PLAN.md), [recovery contract](RECOVERY-CONTRACT.md) and
[delivery evidence](conformance/rec05b-delivery.json) for scope and verification.
