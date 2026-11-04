# Fresh plain-model reference preparation

The fresh comparison now has two **unfunded plain-model descriptors**. These
describe direct use of the same generator model as Buddha, on the same 26 final
tasks, with ten answers per task:

| Reference | What happens when it eventually runs |
| --- | --- |
| Independent (`regenerate`) | Each answer starts with the task and a fresh conversation. |
| In-context | Earlier answers are included when asking for the next answer. |

Both use the reviewed fixed seed with empty harness instructions. The selected
provider, model, declared output cap, host profiles, official evaluator and
stage order match the primary configuration. This does not establish how an
arbitrary evolved Buddha program actually samples; its request trace still
needs checking before assigning a sampling label.

The recipe shares the primary bundle's immutable benchmark, profiles,
environments and native worker. It adds only the public fixed seed, its five
worker files, the task file and the two pairs of descriptors. It reads no P/C
programs or old run history, creates no owners or spending authority, and does
not generate answers or judge them.

The [recipe](conformance/prepare-fresh-plain-references.py) uses the existing
baseline, fixed-recipe, profile and executor metadata validators. Its manifest
names every admitted file. A new destination is required; partial output is
retained on failure. Error reports keep the stage, error class and public code
locations, while omitting messages, source lines and local variables that could
contain private content. These are checks around trusted preparation code,
not a sandbox for arbitrary programs.

Both dollar and call envelopes now aggregate the 26 per-task ceilings. The old
preparation recipe aggregated calls alone. The resulting **$650 nominal owner
ceilings are not funding, a bill, a forecast or an approved global cap**. A
future shared spending limit must be approved separately and remains binding.
Generation uses one owner with a separate container per task; copying a
per-task generation timeout does not impose that timeout on all 260 answers.
Actual native whole-panel capacity and runtime behavior remain to be checked.

The recipe accepts `--inputs` for its reviewed manifest and `--sha256` for that
manifest's fingerprint. These options create local configuration files once;
they need no keys and spend no model API money. The recorded preparation has
already been performed. A new observation needs a new destination and bound
inputs. This guide supplies no paid-run command.

## Recorded result: November 2, 2026

The first actual construction completed in 1.739 seconds under a 300-second
limit. Both descriptors pass the existing validators. Twelve indexed files
plus the result are retained at `runs/imp01-fresh-plain-20261102-v1`; the 19
shared component files are reused in place. Source and input fingerprints
match their before/after checks. Five supplied checks and the scoped quality
checks pass. Hosted CI has its own gate. [Exact evidence and limits](conformance/fresh-plain-reference-delivery.json).

The task file retains the complete benchmark source for provenance. The
current controller code sends one current task to a generation worker and
development-only feedback to an improver. Workers mount only their agent and
runner folders. This bounded source-level trace does not attest model prior
knowledge, opaque program contents, literal configuration instructions, image
contents or actual containment.
Retained custody declarations keep their original scope; no new exposure
attestation is created by renaming a process.

For developers, this optional command runs the five supplied checks once from
the checkout containing this slice:

```powershell
python -m unittest discover -s tests -p test_fresh_plain_reference_preparation.py -v
```

It uses temporary data and public executor metadata only. It needs no keys or
Docker, spends no API money and does not read the frozen experiment inputs.
Use the current PowerShell window. Expect `Ran 5 tests` and `OK`; zero tests
means this checkout lacks the slice. Ctrl+C stops it. The direct command has
no enforced time limit; the retained observation used a 120-second bound.

Review setup, prospective separation, full CI/composition, comparable-size
history, actual outgoing requests, accounts, prices, runtime/capacity and the
separately funded handoff remain in [PLAN.md](PLAN.md). Primary preparation and
these references do not transfer the original run's grants or outcomes.
