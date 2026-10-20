# BENCH-02C3A boundary review

October 20, 2026. Independent review of the actual `channel.py`, `executor.py`, `native_worker.py` and `native_run.py` execution path, including their Gateway/shared-authority and artifact callers. The reviewer made no application changes. Tests and bounded Docker fixtures used synthetic credentials and inputs; no provider call occurred.

Within this slice's evaluator-only, fixed-worker and frozen raw-input scope, no remaining blocking trust or funding defect was identified after the four repairs below. This is a bounded engineering conclusion. It does not close aggregate BENCH-02C3, benchmark conformance, semantic measurement, seed generation or source self-modification.

## Reproduced defects and repairs

| Finding | Actual failing evidence | Repair and passing evidence |
| --- | --- | --- |
| C3-R1: late diagnostics bypassed the stderr limit | A deterministic stream withheld over-limit stderr until the cleanup process wait, after the main loop's last failure check. The initial 18-test executor run had one failure: the executor returned success. | Drain/join readers before closing pipes and check failures after joining. The regression passes in the 19-test executor suite; real Docker stderr flooding also produces an explicit diagnostics stop with owned cleanup. |
| C3-R2: verified source could execute different adjacent bytecode | Actual Docker under `-I -B` imported `VALUE='poison'` although `/runner/helper.py` contained `VALUE='source'`. A trusted literal was compiled without execution on the host; matching timestamp/size made its stale CPython 3.13 cache valid. `__file__` still named the source. | Exact creation and inspected command arguments now include `-X pycache_prefix=/__absent_bytecode_cache`. The worker checks that prefix is active and absent before selected imports; NativeSession rejects selected `.pyc`, `.pyo` and `__pycache__` file inventories. The real regression leaves the colliding adjacent cache present, yet observes the source value and an absent-prefix cache path. |
| C3-R3: an unused approved worker copy could validate a different executable entrypoint | A selected `alternate.py` entrypoint was accepted while matching copies of the expected worker modules remained unused in the selected tree. The constructor regression failed before repair. | The fixed `native-worker.v1` host route requires `buddha/native_worker.py`. Generic Executor custom entrypoints remain available for separately scoped probes. The constructor regression now rejects the mismatch before output or any paid operation. |
| C3-R4: consumed descriptor bytes were not compared with their frozen digest | The constructor hashed the descriptor, then parsed a separate read. A changed/reverted consumed-read fixture supplied a valid different wall limit while normal hash reads saw the original file. The adversarial test was accepted before repair. | The constructor performs a bounded descriptor read, checks SHA256 of those exact bytes against the owner digest, and parses those bytes. The regression delegates normal hashing/fileno operations and injects the mismatch into the actual consumed read, so passing does not depend on changing from `read_bytes()` to `open()`. |

The first two adversarial host-constructor tests failed together before R3/R4's repairs. Afterward both passed, and a third method verifies selected bytecode/cache inventory rejection across official and runner inputs. The final reviewer-observed focused result is **3 tests passed in 3.819 seconds**, with Ruff passing. The bytecode case also extends the previously passing ten-case Docker probe to eleven cases; the prior ten-case evidence remains separate and unchanged.

## Actual Docker observations

The eleven-case probe used the pinned runtime image `sha256:d9476e5c6baf21ba4e70709b96100bdc7fe30637e59a377432690088c8dc77c1` on Docker Engine 29.5.3, Linux/amd64, kernel `6.18.33.1-microsoft-standard-WSL2`, cgroup v2. It ran through the real Executor without Python network monkeypatches.

| Cases | Observations |
| --- | --- |
| Evaluator and agent role boundaries | UID/GID 65532, effective capabilities zero, NoNewPrivs 1 and seccomp mode 2; root/runner/input/role-mount writes denied. The opposite role's mount, provider-key/sentinel environment, nonempty proxy values, Docker socket and tested host/final-data paths were absent. Only the single fixture task entered the input mount. |
| Actual process limits | `memory.max=134217728`, `memory.swap.max=0`, `pids.max=16`, `cpu.max=50000 100000` inside both role containers. These are measured cgroup values rather than inspect-only declarations. |
| Source/cache collision | Same `cpython-313` cache tag; adjacent poison cache remained present. Import returned `source`, with `__cached__` under the active absent prefix. |
| Outbound network | Only `lo` existed. IPv4/IPv6 TCP and UDP, alternate HTTP and HTTPS failed with errno 101; DNS failed with errno -3. These seven attempted paths were denied. |
| Scratch and CPU | Scratch filled at 8,388,608 bytes and refused further writes; direct scratch execution was denied. A bounded CPU loop recorded 13 throttled periods and 607,505 microseconds of CPU usage. |
| Owned deadline and output stops | A detached fork was created before an infinite CPU loop triggered the worker timeout. Newline-free stdout triggered an output stop; stderr flooding triggered a diagnostics stop. |
| Memory and PID pressure | A child allocating beyond the 128 MiB limit was killed with signal 9; the cgroup recorded one OOM kill and 37 memory-limit events. Forking was refused after 14 children. |

Every completed or stopped case's exact owned ID was absent afterward; verification included a successful daemon listing, so daemon unavailability was not mistaken for removal. A separately owned canary remained alive after every case and was removed after the probe. No executor-labelled container remained. Current probe source hashes matched the recorded evidence at verification.

The first three machine-readable records below are also packaged beside this review in
`docs/conformance/`; their bytes match the local `runs/reviews/` records:

- `nb02c3-executor-evidence.json`: eleven-case pass, SHA256 `e5e4ee0830fb4dc61b1cc3ec0026f6aecadf5e28de2ed071f6b45617b6d965b3`.
- `nb02c3-bytecode-shadow-red.json`: actual stale-bytecode reproduction, SHA256 `9d028858f5174c540a0c8f6cb201fc041440b9cc29cdf924d8bf4f4de4fe376c`.
- `nb02c3-executor-ten-case-before-pycache.json`: preserved original ten-case pass, SHA256 `7ab18d781c6110691e927d84a592bfa2b3c561da8e41fbcddd2e8b567b53518f`.
- `nb02c3-executor-fixture-failure-v1.json`: a preliminary fixture parser failure, retained honestly. It parsed `/proc/self/status` keys without removing their trailing colon; no executor defect was inferred. The fixture was corrected before the passing probe runs.

The preliminary fixture-parser record remains under ignored `runs/reviews/`.
The committed records above identify the actual red/green observations; the full
installed-tree and import evidence has separate seals in the runtime record.

## Failed multi-head timing observation

The full-module differential fixture initially required equal request counts
on malformed multi-head scoring. One actual run produced **three** direct SDK
requests and **four** funded requests, with the same failed status and native
partial artifacts. Native `score_llm` uses `gather`; when parsing fails, pending
peer heads may be cancelled during command teardown. The direct canned transport
and the serialized host channel have different timing. No altered scientific
function or financial-accounting defect was demonstrated by this observation.

[The preserved failed-comparator log](nb02c3-funded-native-fixture-failure-v3.log)
records the counts and assertion. It is a historical observation, not a final
passing conformance record. The final parser-failure fixture explicitly uses one
head per typed row so every row's failed call is awaited deterministically;
successful multi-head/cache/fallback fixtures remain separate. This does not
establish network-timing or arbitrary failed multi-head request-count parity.
Every actual funded send remains accounted for, and a failed command remains
failed regardless of its call count.

## Paths and guards reviewed

The host binds the descriptor, actual controller/worker files, selected official/runner inventories, model profiles, exact raw input files, image identity, local endpoint and resource limits. A canonical configuration snapshot is checked on handling and execution. Readiness requires selected native imports and expected hook aliases. Worker-request sequence, exact endpoint/body/header data and host-owned model/profile mapping precede the real Gateway.

The Gateway retains financial ownership: it verifies source/authority before credentials and reservation, saves received raw evidence before interpreting usage and billing, and preserves unknown liability. The worker receives no real credentials and has no direct funded network route. A native stop escapes ordinary SDK retry handlers; unknown/authority/protocol stops latch before further queued work. A response-delivery failure cannot undo a completed host receipt or justify resending an uncertain operation.

The executor owns a fresh labelled container, uses a frozen explicit local endpoint, disables persistent Docker logs, and verifies the restrictive configuration before start. It bounds framing, aggregate output, diagnostics and queueing; diagnostics are not published as raw child text. Watchdog termination targets the owned container while the main synchronous callback retains dispatched host work. Cleanup failures remain explicit rather than becoming successful execution results.

Native output files remain byte-preserving artifacts, separate from host import evidence and the report. Both worker and host enforce size/count/aggregate bounds; links and special files are denied in collection. The host rejects portable-path/case/ancestor collisions, invalid base64, noncontiguous or short nonterminal chunks, and revalidates artifact parents before publication. Atomic hard-link publication refuses an existing destination. A failed or incomplete command cannot become a complete host report merely because some native files exist.

## Explicit limits and remaining work

- **Worker timeout versus host finalization:** the wall limit terminates worker execution. The synchronous host callback must finish durable accounting before returning. The provider socket timeout is not a whole-operation deadline; no bounded total-return guarantee or orphan sender-thread workaround is claimed.
- **Trusted local Docker:** the CLI, daemon and kernel are trusted. Control-command metadata is size-checked after capture; this does not bound allocation against a malicious daemon. Endpoint hashing pins the local location, not a remote attestation of the daemon. Containers are a practical research boundary, not proof against host/kernel exploits or a privileged hostile host racing local filesystem mutations.
- **Image/runtime provenance:** the reviewed immutable image, installed-file audit and imported-module origin checks establish the declared runtime scope. They do not authenticate upstream science, prove every Python function object's history, or constitute a full base-OS vulnerability audit. The AnyIO override and remaining license/base-image limits belong to the separately recorded runtime decision.
- **Native conformance:** this slice runs the complete selected official score/summary path from fixed canned partition inputs. It does not yet execute native partitioning or the frozen seed agent's generation. The separate direct-versus-funded full-module oracle owns numerical/parser/cache/fallback/summary equivalence evidence. This review does not duplicate or predeclare its outcome.
- **Raw input versus C1 provenance:** `answers_sha256` identifies frozen context bytes and must match a frozen input digest; NativeSession does not establish a parsed C1 Answers/TaskSet population relationship. Raw native input files are sealed, but the complete TaskSet -> generation -> Answers -> partition -> evaluation controller remains a later planned connection.
- **Semantic and scientific limits:** complete execution and official scores do not establish meaningful story variety, judge correctness, held-out improvement, transfer or an improving improver. Preserve poor answers and native refusal/malformed/partial artifacts; keep experiment completeness and promotion separate from native summaries.
- **No new live readiness:** no paid command, live allocation, source-mutation executor route or leaderboard claim follows from these offline checks. Final full-suite and composed native-oracle results are recorded by the delivery owner separately.

## Repeating the bounded checks

This command runs once in the current PowerShell window using temporary fixtures and mocked provider transport. It needs no keys or Docker, spends nothing, and checks the three host-constructor regressions. `Ctrl+C` stops it.

```powershell
python -m unittest discover -s tests -p test_native_run_adversarial.py
```

This command runs once in the same window using the already installed pinned Docker image. It creates and removes private containers, makes no provider calls or image downloads, and writes sanitized ignored evidence. `Ctrl+C` stops it and attempts owned-container cleanup.

```powershell
python docs/conformance/nb02c3-executor-probe.py
```
