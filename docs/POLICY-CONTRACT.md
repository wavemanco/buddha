# Explicit policy and proposer contract

POL-01 clarifies the existing policy baseline. It adds an explicitly selected v2
proposer request, using the same two-field policy and existing native evaluation.
It does not start a search or an experiment. [PLAN.md](PLAN.md) owns the roadmap;
controlled comparisons and funding remain POL-02.

## What the sampling modes mean

| Policy value | What the generation request receives |
| --- | --- |
| `regenerate` | The original task and fixed policy instructions for every answer, without preceding answers. An instruction to avoid repetition cannot inspect answers absent from that request. |
| `in-context` | The same task and instructions, followed by all preceding effective answers in order and the fixed continuation `Can you generate a different answer?`. Empty/refused replies retain the frozen seed's effective placeholders in this history. |

Neither mode guarantees meaningful diversity. History can help expose repetition
and can also anchor later answers. Independent sampling here describes the
request construction; it does not establish statistical independence of model
outputs or independent evaluation.

A policy is still exactly `{"instructions": "...", "sampling": "regenerate"}`.
Instructions are at most 4,000 characters; the other permitted sampling value is
`in-context`. A policy cannot select a model, change a budget or modify the
official evaluator. Its arbitrary instruction text can nevertheless conflict
with a task. Structural validity is not semantic compliance.

The [continuation's E9 finding](LINKED-CONTINUATION-RESULTS.md) showed why this
matters: instructions specialized to one task's subject and sentence count can
conflict with other tasks. The v2 prompt tells the proposer that policies apply
across tasks, the original literal format/count/tone take priority, and one
example's requirements must not become unconditional requirements everywhere.
This wording is an intervention to test, not evidence that a model will obey.
Bad policies and weak answers remain evidence; this slice adds no output filter.

## Explicit v2 request interface

`buddha.proposer.propose_call_v2(spec, parent=..., feedback=..., method=...)`
returns an existing `Call` and sends nothing. It reuses v1's validation and
request construction once, then replaces only the system prompt. The model,
output limit, provider fields, two-field schema, parent, feedback and method are
unchanged. Both supported providers use the same effective v2 contract.

`buddha.proposer.contract_record()` returns fresh JSON-compatible data containing
the v2 identity, effective system text, schema, their SHA256 digests and the two
sampling descriptions. It reads no keys and writes nothing. Mutating a returned
record does not change later calls.

The existing `buddha.policy.propose_call` and legacy search remain **v1**. There is
no automatic upgrade or resume conversion. The new module does not connect v2 to
the search controller or create a paid invocation. The v1 policy/search and
frozen seed sources, requests, manifests and receipts remain unchanged.

A future funded caller must explicitly freeze the contract record and actual
executing proposer sources as ordered Gateway invocation inputs, alongside its
parent/feedback inputs. That includes the new proposer source and the reused
legacy policy/helper sources; the existing Gateway separately binds its installed
financial core. The request fingerprint must reflect the v2 effective body.
The new pure API does not automatically bind these inputs, authorize a call,
validate feedback provenance or attest an externally supplied source declaration.
Do not attach v2 to an old owner or label an old v1 run as v2.

## Evaluate a fixed policy using the existing path

The existing [frozen-generation descriptor](FROZEN-SEED.md) already accepts
`instructions` and `sampling` alongside its fixed `provider`, `model` and
`max_output_tokens`. A caller supplies a validated `Policy`'s two fields there,
then uses the existing [native baseline](NATIVE-BASELINE.md) preparation and run
interfaces. A fixed-policy evaluation needs no proposal call or search loop.

The descriptor and config digest freeze the treatment. Task IDs, literal prompts
and requested answer counts come from the selected C1 TaskSet. Generation uses
its original Gateway owner; the ordered C1 Answers then enter the selected
official partition, score and summary stages. The policy does not edit those
stages. Fresh treatments/occasions need their own declared identities and shared
funding; this document creates none.

POL-02 will specify empty versus child instructions under both existing modes,
varied prompts, repeated complete sets and matched resources. Supporting those
inputs is not evidence that this comparison has run or that any policy improves.

## Offline checks and their limits

```powershell
python -W error::ResourceWarning -m unittest discover -s tests -p test_proposer.py -v
```

This runs once in the current PowerShell window, uses temporary fixtures and
mocked provider responses, needs no keys or Docker and spends nothing. It checks
v2 contract/request construction, preserved v1 request bytes, explicit Gateway
input binding and drift refusal, and fixed-policy composition through real host
sessions and accounting. Ctrl+C stops the check.

The composition check mocks container execution and official computations. It
asserts the actual worker configuration, captured generation request history,
fixed model/limits, unchanged native selection and literal C1 handoff. It is not
a new actual-container or scientific result. Earlier [real-worker mode checks](conformance/nb02c3c2-agent-evidence.json)
and [full native baseline checks](conformance/nb02c3c3-delivery.json) remain
separate evidence for the reused path; they do not prove a new controlled policy
comparison or v2 proposal quality. No model judgments, transfer results, source
evolution or held-out improvement are claimed here.
