# SRC-01: running one candidate source task

This route lets a selected Python candidate answer one host-selected task inside
the [separate restricted runtime](SOURCE-RUNTIME.md). It reuses the existing
container executor, model gateway, shared accounting and C1 answer format.
The fixed-seed route remains separate and unchanged.

It is a programmatic execution boundary. It does not create an agent, modify
source, choose a benchmark split, judge answers, run evolutionary search or
authorize API spending. SRC-02/03 still supply inherited bundles and improvement
procedures; [PLAN.md](PLAN.md) retains those gates.

## What the candidate receives

The selected component contains exactly one regular UTF-8 `.py` file, at most
1 MiB. Its entry point is:

```python
def generate(task, config, complete):
    ...
    return ordered_answers
```

`task` has only `id`, `prompt` and `count`. It has no other dataset rows,
source metadata, evaluation code, judge instructions or final-set access.
`config` has the existing five fields: `provider`, `model`,
`max_output_tokens`, `instructions` and `sampling`. The candidate receives
copies, so editing them cannot change the host's frozen contract.

`complete(provider, body)` accepts UTF-8 JSON request **bytes** for the selected
provider and returns the decoded raw API JSON object. It does not return an SDK
client or a credential. Candidate code interprets the provider response and
chooses its final answers. No frozen-seed interpretation of refusal, truncation
or empty content is silently applied to arbitrary candidate code.

For example, a candidate can make a planning call, a drafting call and a checking
call, then return two answers. Another candidate can return ten answers without
using a model at all. Call count and answer count are independent; neither
behavior by itself establishes useful diversity.

The host fixes the provider/model and output-token ceiling. Each request must
explicitly request a positive allowance at or below that ceiling:
`max_completion_tokens` for OpenAI or `max_tokens` for Anthropic. A candidate
cannot select an endpoint, header, pricing profile, operation ID, retry number
or higher allowance. The existing gateway also validates supported text-only
request fields, tier, credentials, funding and response usage. All actual paid
attempts remain in its existing accounting records.

The result must be an ordered list of exactly `count` valid UTF-8 strings.
Whitespace, empty strings, duplicates and poor answers remain literal evidence.
Correct shape means successful execution; it does not establish task compliance,
quality or distinctiveness. The selected official evaluator measures those
separately.

## What the host freezes

A descriptor with format `buddha.candidate-generation.v1` contains exactly:

| Field | Meaning |
| --- | --- |
| `format` | `buddha.candidate-generation.v1` |
| `tasks` | Absolute path to a sealed C1 TaskSet selecting exactly one task |
| `config` | The five candidate settings described above |
| `entrypoint` | Relative path to the single selected Python file |
| `executor` | Pinned image, role, two mounts, runner entry point, environment, limits and local Docker endpoint |
| `profile` | Host-selected `capability` and `profile_id` in the existing Gateway owner |
| `runtime` | Absolute selected environment-artifact `path` and its `sha256` |
| `max_callbacks` | Maximum model callbacks, an integer from 0 through 1,000 |

The descriptor, TaskSet, runtime artifact and all eight host-route source files
must be explicit invocation inputs of the original prepared Gateway owner.
Those source files are `__init__.py`, `channel.py`, `releases.py`, `wire.py`,
`candidate_worker.py`, `executor.py`, `answers.py` and `candidate_run.py`.
The runner selection must contain exactly the first five, with the same bytes as
the installed host package. Existing Gateway core-source binding applies too.
Use a dedicated owner for this one candidate contract and run its sessions
serially. The route does not coordinate concurrent host callers sharing an owner
or seal/deactivate that owner as a completed multi-stage experiment.

The caller supplies the independently reviewed runtime artifact's expected hash
to `CandidateSession`; the descriptor cannot approve its own image. This joins
the expected hash, frozen invocation input, selected environment component,
image ID and exact image environment. Before loading candidate code, the worker
checks the sealed image audit helper/manifest and recomputes the physical Python
inventory. The currently reviewed runtime record is
[here](conformance/src01-runtime-environment.json). A future image needs its own
review and frozen approval; reading a hash from an untrusted candidate is not
approval.

The programmatic call, after preparing the existing Gateway and its authorization,
is:

```python
session = CandidateSession(
    gateway,
    descriptor=descriptor_path,
    output=new_output_directory,
    expected_runtime_sha256=independently_reviewed_runtime_hash,
)
report = session.run()
```

This example names already prepared Python objects, not a standalone PowerShell
command. Constructing the session validates frozen inputs and creates a new
output directory. `run()` starts one container and can request model calls only
through that original Gateway's existing authority. There is no new live CLI or
spending allocation in this slice.

## Isolation and the request conversation

Candidate source is read as data on the host; it is compiled/executed only inside
the container. Its two read-only mounts are `/agent` and `/runner`. The worker
gets one sanitized task, not the host-held TaskSet file. No official evaluator,
full dataset, host home, Docker socket, ledger or API key is mounted.

The existing executor uses the approved immutable image, non-root user,
read-only root, bounded scratch, process/CPU/memory/wall limits, no outbound
network, dropped capabilities and owned-container cleanup. Python runs isolated
with bytecode loading/writing guards. Candidate stdout becomes bounded
diagnostics; the framed request/reply channel uses private descriptors.

The worker first sends the selected source/task/runtime identities. For each
callback it sends only an ordinal, provider and encoded body. The host requires
ordinals starting at zero with no repeats or gaps; it supplies the selected
profile, stable logical operation identity and attempt zero itself. The worker
receives a raw reply or an explicit stop.

Worker checks and its “ready” message are consistency checks, not a claim that
candidate Python cannot inspect or interfere with its own process. The host
treats all frames as untrusted. The separate container, source selection and
host-owned validation/accounting establish the access boundary. Container/host
trust limits from [the runtime guide](SOURCE-RUNTIME.md) still apply.

## Stops, replay and saved results

The host alone enforces the callback quota. The first callback beyond it gets a
`quota` stop without creating another provider operation. Lack of authority,
unknown liability or invalid gateway requests also stops the channel. Once a
host stop occurs, later frames cannot reopen model access or claim completion.
The worker also keeps that stop even if candidate code catches its exception.

The stable logical identity includes the descriptor, agent, selected TaskSet and
callback ordinal. It excludes the output directory and request-body hash. A
fresh execution against the **same original owner** can therefore replay saved
replies without keys or another send. A changed body at an already used ordinal
is a conflict; it cannot silently become another billable request. Changed
source/configuration needs a newly frozen execution contract and whatever
authorization that separate work requires. This is not arbitrary checkpointing
of the candidate's Python memory or a guarantee of identical fresh model output.

Recovery must consume the original operation prefix. A new attempt cannot skip
old completed replies or an unknown request by choosing to make fewer callbacks.
The host checks this both when receiving completion and before publishing C1:
each delivered ordinal names one distinct completed operation, and the owner's
operation count must equal the delivered count. Otherwise it records a failed
result with `owner_operation_coverage_complete: false`, keeps all old
records/holds and publishes no complete answers. A genuine zero-call candidate
with a clean owner remains valid. Concurrent trusted callers can invalidate the
count snapshot; this is another reason to keep this dedicated owner serial.

Successful publication requires exact literal answer coverage, a valid terminal
frame, process exit zero, the approved image and confirmed owned-container
removal. Only then is `answers.json` written in the existing C1 format, bound to
the selected source and TaskSet. `report.json` records the status/reason,
identities, delivered-call counters, execution evidence, original-owner totals
and operation coverage, and answer-artifact hash. Files use exclusive creation
and are flushed to disk.

“Completed calls” counts delivered replies, including replay. Gateway totals
cover the entire original owner, including earlier operations and holds. They
must not be added together as if they were two spending ledgers.

Failed or stopped executions publish no complete C1 answers. Already recorded
API replies/charges/unknown holds remain in their original owner. A latched host
stop remains explicit in the report even if a worker subsequently misbehaves.
Ctrl+C during execution saves a cancelled report and re-raises the interruption;
cleanup errors remain executor failures. If the process or disk fails before a
terminal report can be saved, the directory is incomplete, never successful;
inspect retained owner records before deciding on another attempt. A C1 file
alone does not establish completion: require its matching complete report and
artifact hash, including when a disk failure leaves a file behind.

## Reproduce the offline integration proof

From the repository folder in PowerShell, use Python 3.13 and Docker Desktop's
Linux engine with the already reviewed source runtime installed. The following
command runs once in the same window. It starts actual confined candidates, uses
synthetic HTTPS responses and fake credentials in temporary fixtures, and saves
a new proof file. It makes no real API calls, uses no live allocation and does
not read your keys or change existing study records. Use a new output filename
for each attempt. Ctrl+C stops the foreground proof and requests owned-container
cleanup; partial evidence may remain for review.

```powershell
python docs/conformance/src01-candidate-probe.py --out runs/src01-candidate-proof-1.json
```

The proof and repository checks establish the execution boundary at their
declared scope. They do not show a parent authoring a child, an improved
improver, benchmark gains or resistance to every host/kernel exploit. The
benchmark integration remains in the existing replaceable release/C1 boundary;
there are no NoveltyBench-version conditions in the candidate runner.
