# Frozen seed generation recipe

BENCH-02C3C1 moves the existing seed generation procedure into
`agents/frozen_seed.py`, a standalone standard-library module. It contains no
NoveltyBench version, judge prompt, SDK, credential reader, network sender or
accounting import. This recipe is now used by the isolated fixed-seed route below. The complete
official pipeline remains a separate gate in [the plan](PLAN.md).

The first baseline treatment remains empty instructions with independent
`regenerate` sampling. The same implementation also preserves the existing
`in-context` mode, in which previous effective answers accompany the next
request. The requested count is task data; counts two and ten use the same
code. Supporting a mode does not automatically add another experiment arm.

## Interface

| Function | Purpose |
| --- | --- |
| `request(config, task, previous=())` | Return the exact UTF-8 JSON request bytes for one answer. It sends nothing. |
| `normalize(provider, response)` | Extract one effective answer from parsed provider JSON using the frozen legacy recipe. Malformed responses fail explicitly. |
| `generate(task, config, complete)` | Request `task.count` ordered answers through a supplied `complete(provider, body)` callback. The callback returns parsed provider JSON; it must be supplied by the trusted funded controller for actual execution. |

Configuration has exactly `provider`, `model`, `max_output_tokens`,
`instructions` and `sampling`. A sanitized task has exactly `id`, `prompt` and
`count`. The seed receives no dataset, judge configuration or benchmark paths.
The later controller must freeze these inputs and retain raw provider evidence
before normalization; this module supplies no authorization by itself.

Legacy request fields, Unicode serialization, the continuation message and
Anthropic cache marker are preserved. Literal whitespace, duplicate or poor
answers, and accepted truncation remain answers. The recipe deliberately maps
empty text to `[empty]` and refusal to `[refused]`; those effective strings are
not the original response. Raw evidence and the recorded normalization identity
must keep that distinction. Unsupported completion states and malformed outer
provider responses are generation failures, never replacement empty answers.

The command below checks the recipe against the actual legacy generation and
reply parser, including both providers and existing sampling modes. It runs
once in the current PowerShell window, creates only temporary test fixtures,
needs no Docker or API keys and spends nothing. Ctrl+C stops it.

```powershell
python -m unittest discover -s tests -p test_frozen_seed.py
```

These differential checks cover valid request/answer behavior and stricter
malformed-input rejection. They do not establish provider availability,
isolation, complete native evaluation, meaningful diversity or improvement.
Callbacks run sequentially, with no automatic retry; callback or parsing failures
escape to the host. Blank prompts retain the original seed's rejection behavior.
C1 still preserves those task bytes; a failed seed must be recorded as a failure
rather than silently dropping the task or inventing an answer. The original
generation implementation and historical receipts remain frozen.

[Delivery evidence](conformance/nb02c3c1-delivery.json) records the tests,
source seals, quality checks and preserved historical inputs.


## Isolated fixed-seed generation

C3C2 adds `buddha.agent_run.AgentSession(gateway, descriptor=..., output=...)`.
It uses the original immutable Gateway owner and a fresh output directory;
`run()` returns a separate generation report. It never imports or executes the
agent implementation on the host. The selected agent directory must contain
only the reviewed seed source, with its exact frozen hash. The actual trusted
seed file, executing host/worker sources, task artifact and descriptor must all
be bound invocation inputs. A different script or an extra data file is rejected
before execution or spending. Source-evolved agents need their separate gate.

The descriptor identifies the host-only task artifact, five generation settings,
seed entrypoint, fixed generation capability/profile, immutable image, local
Docker endpoint and resource limits. The existing Gateway verifies the complete
release selection. The generation route additionally checks the selected
population/release, actual mounts and fixed model/output cap. It assigns request
identities from the frozen agent/configuration, typed task position/ID and sample
ordinal, with physical attempt zero. The worker cannot choose a profile, endpoint,
header, ledger path or replacement identity.

Each container receives only `/agent`, the minimal `/runner` and one sanitized
`id`/`prompt`/`count` task over the bounded channel. It receives no input-data
mount, full TaskSet/Answers, original row metadata, evaluator, authorization file
or credentials. The worker verifies consumed source, loaded origins, private
working state and absent bytecode-cache prefix before requests and at completion.
The fixed seed imports only the standard library. The reviewed C3A image is
reused for this known source; this is not permission to run arbitrary evolved
code in that environment.

Raw HTTP replies and billing are durable in the host Gateway before the worker
parses them. Completed receipts replay through the same owner without keys or
new sends. A fresh output attempt rebuilds the same in-context prefix; creating
a new Gateway owner is not resume. Unknown/dispatched operations retain their
holds and stop further spending. Parsing a well-billed malformed response is a
generation failure with a known charge, not an empty answer or unknown bill.
There is no automatic provider retry or unknown-request replacement.

| Output | Meaning |
| --- | --- |
| `partial.jsonl` | Literal task outputs returned before the attempt ended. Diagnostic prefix only: final process/cleanup failure can still make the attempt invalid. Raw replies from an unfinished task remain in the Gateway. |
| `answers.json` | C1 Answers artifact, published only after every selected task has the exact ordered answer count and each container exits successfully with verified cleanup. Original source metadata is preserved; new native generation metadata is left to the benchmark controller. |
| `report.json` | Separate status, source/config/task identities, raw-delivery counters, whole-owner accounting and actual container/cleanup evidence. Native evaluation and promotion are separate. |

A host interruption can leave no final report. Keep that incomplete output and
its original Gateway: completed receipts and unknown holds still govern recovery.
A worker wall timeout ends its owned container; an already admitted host request
must finish durable accounting before the controller returns. It is not a total
host-finalization deadline.

The commands below run the portable worker and host checks once in the current
PowerShell window. They use temporary fixtures and mocked provider responses,
need no Docker/API keys and spend nothing. The first checks source, imports and
channel behavior in isolated Python subprocesses; the second checks actual shared
accounting, task/source bindings, raw replay and answer publication. Ctrl+C stops
a foreground check.

```powershell
python -m unittest discover -s tests -p test_agent_worker.py
python -m unittest discover -s tests -p test_agent_run.py
```

The optional command below repeats the real-container acceptance check once in
this PowerShell window. It requires a running local Docker Linux engine and the
exact prepared C3A image recorded in the probe; it installs or downloads nothing.
It uses fake keys and mocked HTTPS, makes no real API calls and spends nothing.
It creates temporary fixtures and writes its new evidence under `runs/reviews/`;
committed evidence and historical runs are unchanged. Allow about three minutes.
Ctrl+C stops it and attempts cleanup of containers owned by this check.

```powershell
python docs/conformance/nb02c3c2-agent-probe.py
```

[The recorded container evidence](conformance/nb02c3c2-agent-evidence.json) covers
ten cases plus keyless replay, both providers and sampling modes, counts two/ten,
selected typed IDs, received-reply interruption, unknown usage, timeout, malformed
replies, insufficient authority and worker cancellation. It records 56 mocked
physical requests including the interrupted prefix, zero real calls and no newly
retained owned containers. Unknown holds remain held; the admitted wall-timeout
request finishes accounting before host return. This checks execution and
provenance, not meaningful novelty, provider availability or native judging.

[C3C2 delivery evidence](conformance/nb02c3c2-delivery.json) records the 703-test
suite, source seals, independent review, three reproduced source/data-scope
regressions and actual container checks. The composed generation, native
partition, score and summary pipeline remains C3C3 in [the plan](PLAN.md).
