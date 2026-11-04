# Fresh confinement observations

The existing confinement probe passed against both pinned images used by the fresh comparison: the source-runtime image and the native-runtime image. The combined parent observation took **40.388 seconds**. These were controlled runtime fixtures; no actual agent, evaluator command, benchmark task or model API was exercised.

The [delivery record](conformance/fresh-confinement-observations-delivery.json) binds the saved results, image evidence, unchanged helper and source/environment identities. The [living plan](PLAN.md) retains the remaining pre-live gates.

## What was checked

The same existing eleven-case probe ran once per image. Only its environment-record and evidence-output selections changed; its probe logic and controls were unchanged.

| Existing cases | Purpose |
| --- | --- |
| Evaluator and agent boundaries | Check the declared read-only mount/visibility boundaries with synthetic files. |
| Source bytecode | Verify the literal fixture source is used despite a conflicting adjacent bytecode file. |
| Network and scratch | Exercise network denial, bounded scratch space and its execution restriction. |
| CPU, memory and process pressure | Exercise the declared resource controls. |
| Descendant timeout | Stop the owned container and its child processes at the short test deadline. |
| Unfinished stdout and flooded stderr | Stop the case when its output or diagnostic ceiling is exceeded. |

Each image ran eleven case containers and one separately owned canary: **24 distinct containers in total**. A canary is a harmless container kept running to check that stopping a case does not stop an unrelated container.

For all 22 cases, the saved evidence records owned removal, a subsequent successful lookup confirming that exact case container is absent, and the canary still alive. Each canary survived its image's cases and was removed afterward. The timeout and output-flood cases reached their expected stops; their success means the guard behaved as expected, not that the workload completed normally.

## Limits and preservation

The existing ordinary cases use an **8-second wall limit and 128 MiB** of memory. The descendant case uses **1.5 seconds and 64 MiB**; the canary has a **55-second** limit. These are the unchanged probe controls, not the fresh study's generation/evaluation workload limits. The parent imposed no separate outer hard-kill deadline.

The parent records all **360 pinned public Python files unchanged**. Both bound environment records and the byte-sealed probe helper also remain unchanged. No image was rebuilt or pulled, no dependency or application code changed, and no actual API keys, provider calls, private programs, real task data, experiment owners or grants were used.

## What this establishes

This is fresh, point-in-time evidence that the existing synthetic confinement cases work on the ordinary source and native images at the tested Docker endpoint. The [installed-file audits](FRESH-RUNTIME-READINESS.md) and [request observations](FRESH-REQUEST-OBSERVATIONS.md) retain their separate scopes.

The Docker daemon, CLI and host kernel remain trusted. This is not a security-exploit audit, universal container-escape guarantee, new dependency/license clearance, full native SDK or selected-agent assessment, workload-capacity result, performance improvement, scientific result or paid-launch approval. Comparable-size history and the other [pre-live requirements](PLAN.md#current-checkpoint) remain open.

This document records an operator-only observation and provides no execution command.

