# Key checks for new source runs

A saved account review lets Buddha check that a request uses the key intended
for that experiment. The review contains a fingerprint, never the key itself.
This slice adds the keyed review required by [DESIGN section 9](DESIGN.md#9-paid-operation-integrity)
to the existing Gateway and source-search path. The [source launcher](SOURCE-LAUNCH.md)
now binds it to the approved launch. A concrete funded source handoff remains
unprepared and no new spending is allocated.

## What changes for the operator

There is no third secret to create or remember. The new mode uses the API key
already supplied locally. Key entry and cleanup continue to use the existing
hidden-input mechanism. No key file, persistent environment setting or new
dependency is introduced.

The source launcher binds the fingerprint to the exact approved launch bytes.
Changing that configuration or using a different key
must stop execution before a request is sent. A launch-context hash is a
consistency check; it does not grant spending permission.

## What is recorded

The new record explicitly identifies itself as `buddha.account-review.v2` and
contains exactly these five fields:

| Field | Meaning |
| --- | --- |
| `format` | The explicit v2 format above |
| `checked_on` | Date of the manual account and pricing review |
| `account_scope` | The reviewed account settings and applicable bounds |
| `credential_context` | Caller-approved lowercase SHA256 context hash |
| `credential_fingerprints` | Provider names mapped to their keyed fingerprints |

The construction is HMAC-SHA256. The API key is its secret key; the message is
the ASCII bytes of `buddha.account-review.v2`, a NUL byte, the provider name,
another NUL byte, and the context hash. The secret remains outside artifacts.
Provider and context separation make the same key produce different
fingerprints for different providers or approved contexts. These fingerprints
can still link records within one context; they are not anonymization.

The record is not provider authentication, a signature, evidence of model
access or proof of account settings. Account settings remain manual assertions.
The shared authorization and accounting guards remain responsible for limits.

## Recovery and older runs

A wrong key leaves the original request reserved and unsent. Supplying the
reviewed key can continue that same request; no replacement owner is created.
A completed reply can still replay without a key or another charge. An
ambiguous dispatched request retains the existing stop rule.

Historical three-field reviews use `credential_sha256` and keep their original
SHA256 semantics. They are not silently converted to v2. The historical policy
launcher still creates those v1 reviews. Changed Gateway code creates a new
runtime identity; legacy-format support does not permit historical frozen
owners to reopen under changed executable bytes.

## Verification and remaining work

Tests cover both provider routes with synthetic HTTPS, wrong-key recovery,
context and format refusal, keyless replay, and a composed source search whose
generation, proposal and native-assessment owners retain the same v2 review.
The composed test mocks workers and provider replies; it is not a new actual
container test or a live source experiment. Legacy Gateway and key-input
checks remain separate regression evidence.

[The delivery record](conformance/src02-keyed-review-delivery.json) retains the
eleven new checks, 70 legacy methods, seven quality checks, earlier failures
and exact scope. Full hosted Linux/Windows results remain separate.

The launcher now checks the approved context and original owners before key
entry and supplies progress and partial-result receipts. The concrete full
experiment still needs its capacity/recovery rehearsal and funded handoff.
The [living plan](PLAN.md) remains the
scheduling authority. This slice allocates no money and changes no benchmark
rules, official scores or historical run records.
