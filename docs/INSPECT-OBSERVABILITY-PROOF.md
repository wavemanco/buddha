# Inspect observability compatibility proof

This is the bounded ENG-OBS-01 proof in [PLAN.md](PLAN.md), not adoption of a new
runner. It tests one synthetic stage, with no model calls, against pinned Inspect
AI 0.3.287. The existing Gateway, authority ledger, executor and official
NoveltyBench 1.1 evaluation remain authoritative.

The intended replacement is the custom display/polling in `Progress` and the
duplicate launcher heartbeat on an explicitly selected Inspect path. A second
coordinator or another loop reading `progress.snapshot` does not satisfy that
requirement. The existing paths retain their behaviour while this is a candidate.

The cohort must show a successful stage, an actual typed failure and a genuinely
open action observed before it finishes. It must retain the deliberate failure,
compare the underlying request-construction result with a direct call, and
show no extra model, ledger or execution effects. Its parent deadline will include
viewer shutdown. No retry or automatic deadline extension is part of the proof.

## Dependency scope decision: November 2 local / November 3 UTC 2026

The resolved CPython 3.13 Windows closure contains 80 hash-pinned binary packages.
No extra test framework is required. Both resolution passes used binary-only
packages; no source build or downloaded package code ran during preflight.
The exact 80-version advisory check returned zero reported vulnerabilities and
zero skipped packages. This records that dated query, not a general security
certification.

Inspect core is MIT. Its complete dependency closure also includes these notices:

| Distribution | Notice found in the actual wheel | Scope of this decision |
| --- | --- | --- |
| certifi 2026.10.19 | MPL-2.0 | Reuse the existing development-only exception at the same version. |
| botocore 1.43.117 | MPL-2.0 certificate material | Retain its bundled notice in the isolated proof environment. |
| debugpy 1.8.22 | EPL-1.0 PyDev.Debugger component | Retain the incorporated component's notice in the isolated proof environment. |
| NumPy 2.5.4, Windows wheel | GNU runtime component with GCC runtime exception | Retain the actual Windows binary and its component-specific license notices. |

The host engineering policy requires copyleft to be flagged before use. These
flags were raised before installation. The implementation decision is to enable
this exact closure **only in a new isolated development proof environment**,
retaining the supplied notices. This follows the existing isolated-research
[dependency policy](BENCHMARK-REFERENCE-PROFILE.md#reproduction-and-dependency-notices).
It does not add the packages to Buddha's application requirements, vendor or
redistribute their binaries, or clear other platforms, optional extras, provider
execution or a future distributed runtime. Those uses need their own dependency
and license decision. No claim that the entire closure is MIT is made.

The external preflight receipt is
`runs/checks/inspect-ai-dependency-preflight-20261103-v1/dependency-preflight-v1.json`,
SHA256 `05045a63ad9f17d73d6f20dfbba71e84fb00f1b677cadb8fc58b2da7a7ae320e`.
It binds the full license census, wheel hashes, resolution and advisory output.
The two initially incomplete metadata declarations were resolved from actual
wheel license files: agent-client-protocol is Apache-2.0; zipfile-zstd is MIT.

## Isolation required before execution

Use a fresh owned working directory with an empty `.env` and a keyless child
environment. Pin platformdirs 4.14.3 and verify its resolved appdata/cache paths
stay inside that directory before importing Inspect. Its Windows KnownFolder
overrides, explicit log/cache paths and separate per-process trace files keep
Inspect's startup retention and viewer registry away from existing user data.
Changing the trace filename alone is insufficient because rotation happens first.

The viewer must use a fresh owned PID registry and a loopback port. Port zero is
unsupported. A port race must end as a startup failure, without selecting another
port or terminating an unrelated viewer. Stop and join only the owned process.
The proof admits no external network, model requests, real benchmark inputs,
original run records or source-actor execution. Public API compatibility and
actual viewer behaviour remain unmeasured until the cohort runs.
