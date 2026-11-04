# Plain references: prepared configuration and runtime checks

This is preparation for the comparison described in
[PLAIN-MODEL-COMPARISON.md](PLAIN-MODEL-COMPARISON.md), under the existing EVAL-02
gate in [PLAN.md](PLAN.md). It does not replace the bounded improver study,
extend its proposed allowance or publish a live command.

Two ordinary `buddha.native-baseline.v1` descriptors are now checked at
`runs/plain-reference-preparation-20261025-v1`:

| Descriptor | Behavior | Additional final-panel workload |
| --- | --- | --- |
| `regenerate/baseline.json` | Plain model, independent conversations | 26 sets / 260 answers |
| `in-context/baseline.json` | Plain model, previous answers in the same conversation | 26 sets / 260 answers |

They use the existing baseline API, reviewed fixed seed and official native
evaluator. Both have empty Buddha instructions, the same selected generator as
the prepared Buddha study, low effort, a 4,096-token API allowance and the
same 26-task final panel. Their source identity is shared; their configuration
fingerprints differ. Their native judge settings, release, pricing and headers
match the aligned candidate. Preparing both options does not authorize running
both or require rerunning Buddha in every sampling mode.

The fixed-seed worker is separate from the source-candidate worker. The fresh
46-file bundle therefore supplies its own reviewed seed/worker selections and
copies the immutable official/data/runtime/profile inputs. It does not edit
P/C, the original study or any older preparation. Its intent records all
remaining pre-live work; it is unfunded and unadopted.

The descriptors retain nominal per-stage monetary ceilings from the library
template and scale its per-task call ceilings to the whole panel. These are
not an allocation, a combined cap or a completion quote. Actual shared funding,
prices/accounts, reservations and the additional reference scope must be fixed
before execution. The [cost examples](conformance/plain-model-comparison-cost-examples.json)
remain conditional arithmetic, including the differences between public prices
and conservative local accounting.

## What was actually exercised

The reviewed fixed seed ran in the pinned network-isolated source runtime on
two synthetic tasks for each sampling mode. Four actual containers completed
and were removed. All 40 outgoing requests used low effort and a 4,096-token
output limit, with no temperature/top-p override or added system instructions.

Independent generation used one user message for every request. In-context
generation used 1, 3, 5, through 19 messages, including each earlier answer and
the official continuation request. History reset for the next task. Both
synthetic generation sessions completed. Fake HTTP replies, dummy credentials
and a network-denial patch prevented provider access. This proves the checked
generation behavior, not model quality, benchmark performance or paid readiness.
No original P/C program or private final prompt was used in this runtime proof.
The fixture used different resource limits, including 512 MiB memory versus the
draft descriptor's 256 MiB; it is not a certificate of the prepared envelope's
capacity. Recheck the exact funded limits and request sizes before live use.

The [delivery record](conformance/plain-reference-preparation-delivery.json)
separates the data-only preparation, which creates no owner, from the runtime
proof, which uses fresh synthetic accounting only. It retains an initial
preparation refusal: the helper imported an identical finite producer from an
unapproved checkout path. The corrected helper uses the original approved
producer path; no guard changed and no partial destination was overwritten.

## What is still required before these results can be compared

Bind the reference descriptors and analysis specification into both the original
Buddha controls and the reference inputs before outcomes. Do not select favorable
tasks, sources, modes or repetitions after seeing results. Preserve the
original complete panel and missing outcomes.

The result join must consume original baseline and Buddha evidence, check their
owners/seals, generator settings, task/release/judge identities and actual
resource use, and retain incomplete work with its reason. A report hash or
caller-supplied scalar alone is insufficient. Reusing a reference across several
Buddha starts does not create extra independent reference observations.

The [checked consumer](PLAIN-COMPARISON-RESULTS.md) now joins complete original
publications through the existing result readers and scoring projection. Its
shared measurement-row helper requires fresh source pins and prospective
bindings; no old preparation is rewritten. The funded operator handoff and
partial-execution reporting remain pending. The original proposed descriptive
contract is [here](conformance/plain-reference-comparison-proposal.json);
implementation does not adopt or fund it. Existing human review samples cover
Buddha roles; do not present them as human comparisons against new plain arms
without a prospectively declared review extension.

The later [unified preparation](UNIFIED-COMPARISON-PREPARATION.md) supplies fresh
descriptors, prospective plan/input bindings and one combined budget proposal.
It also exercises the actual prepared 256 MiB executor/profile on synthetic
tasks, resolving the older runtime-fixture limit mismatch above within that
bounded scope. Original descriptors and evidence remain unchanged. No API key
or live command is needed at this preparation checkpoint.
