# BENCH-02C2 funded/native boundary adversarial review

2026-10-20. Read-only application review of the actual gateway header/profile/account/capture changes and `native_transport.py`. Root authorized four new regression methods in `tests/test_gateway_headers.py` after the previous owner transferred that file; no application edits were made by this reviewer. The existing wire decoding implementation remained frozen. All inspected credentials and HTTP responses are synthetic; no provider request occurred.

## Concrete findings

### C2-R1: opaque compression can evade screening when coding is absent or misleading

Direct `_capture` probes reproduced three cases before the shared final-content guard:

- `Content-Encoding: identity` with gzip-compressed provider JSON containing a known synthetic credential.
- `Content-Encoding: gzip` with that secret JSON compressed twice.
- Complete valid response headers without a content-encoding field, with the same gzip payload.

Every probe returned `withheld=False`, retained the exact encoded body, and left the known credential recoverable by decompressing the saved bytes. These are straightforward coding/opaque-content mismatches, not an assertion that arbitrary semantic encodings can be exhaustively redacted. The original body SHA still matched, so digest consistency did not address the secret-retention failure.

Root added a common final-content guard: screen the raw bytes and bounded declared-decoded content for known credentials/JSON ASCII escapes; withhold opaque non-UTF8/control-bearing final content. The separate unavailable-header gate remains explicit. Preserve readable malformed provider envelopes for forensic unknown receipts instead of imposing semantic judge validation or requiring all readable content to be valid outer JSON.

Three added regression tests require withholding+original digest+unknown hold for those reproduced cases. A fourth requires a readable malformed gzip envelope to remain available unchanged while its missing/invalid billing evidence stays unknown; this prevents the security fix from silently discarding all malformed forensic responses.

### C2-R2: raw SDK header values are decoded before their byte ceilings/types are checked

At review time, `make_transport` bounds the raw header count but immediately calls `pair[0].decode('ascii')` and `pair[1].decode('ascii')`. The name/value size/type checks run later in `NativeRequest._headers` after these allocations/method calls. An oversized bytes value can therefore allocate and scan an oversized string before being rejected; a non-bytes object can also run its own decode method before type rejection.

Minimal repair: before decoding each pair, require exact bytes elements and reject raw name bytes over 128 / raw value bytes over `MAX_HEADER_VALUE_BYTES`. Keep the existing count, ASCII, duplicate, framing and sanitized-stop checks. This does not require a new dependency or copying an SDK implementation. A meaningful regression should prove malformed/oversized raw header objects are rejected before their decode method executes and before Exchange is called. No funding bypass was observed. Parent subsequently reported implementing this predecode check, observing four failing regression cases before the repair and 11 focused adapter tests passing afterward. Those adapter results are parent-reported, rather than independently rerun by this reviewer.

## Account, identity and funding assessment

- Profile v2 fixes exact allowed semantic header values and exact owner account headers. Submitted account mismatches fail before credential access; omitted owner account values are injected. The request identity includes the frozen profile hash, so injected account values are bound even when they are absent from the worker-submitted receipt request. No separate account-mutation defect was found in this path.
- The real gateway still verifies frozen owner/core/profile/input identities before credentials, reservation and dispatch. Terminal receipt writes retain their necessary independence from post-send mutable source checks.
- `NativeStop` inherits directly from `BaseException`; the adapter rethrows it rather than converting it into an SDK-retryable ordinary exception. Endpoint/method/framing/header protocol failures stop before Exchange. Exchange ordinary errors become sanitized unknown stops. Cancellation is not recast as a provider failure. The host Exchange must still write durable accounting before deciding/returning a stop.
- Current funded oracle serializes actual Gateway calls under an asyncio lock and explicitly binds adapter/context source files as execution inputs. These are bounded composition checks, not proof of a production RPC queue, actual installed runner/SDK import closure or cancellation/owned-process cleanup. Those remain C3. Its selected runner/environment metadata is not a claim that a complete official runtime was executed.
- Gateway's direct core inventory does not itself discover optional adapter/SDK modules. C3 must prove actual executing adapter/context/SDK files agree with selected source/environment, rather than verifying only staged copies. Binding actual probe input file hashes is useful bounded evidence, not a replacement for that later composed gate.
- Complete valid gzip/deflate/native bodies can be billed and replayed through the original SDK parsers. Incomplete/trailing/unsupported coding, absent/ambiguous billing and uncertain non-200 receipts retain liability and stop. The stricter coding and unknown-stop differences must remain explicit; no universal recovery-path native-parity claim follows.

## Checks and status

Before R1's repair, the three direct capture probes all reproduced the retention failure without running Gateway/core tests. After the parent's source-freeze signal, the reviewer observed terminal success for all 24 header tests in 19.919 seconds (including the four new regressions) and all 31 wire tests in 0.007 seconds. Ruff lint/format for the modified header tests passed. No reviewer test process remains active. Parent owns the separate full-suite and actual-SDK oracle runs; these focused checks do not establish their results or C3 confinement readiness.

No financial files, frozen historical artifacts, app source, allocation or live readiness setting was changed by this reviewer.
