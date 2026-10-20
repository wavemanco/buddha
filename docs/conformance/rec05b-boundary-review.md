# REC-05B independent verifier review

This read-only review covers the final legacy semantic verifier and explicit evidence reader, its pure evaluation/archive inputs, and accounting/lineage composition. It does not authenticate providers or audit judge semantics. No real calls or live run writes occurred.

Final reviewed source SHA256 values:

- `buddha/search_verify.py`: `b0fcff4db2b8d029198457dde1eadaa58f1a083d3d394b4b3efa87d181b7a735`
- `buddha/search_evidence.py`: `160dac986d16979d25f67ec05ca47d332839b3b3017c368b2883e6b938ccc29c`
- `buddha/continuation.py`: `b0136052472868aee379d7ac78dfd11bcfa40e91aedcd6916d30f9a334003414`
- `buddha/benchmark.py`: `7ef7e26b2ef3cbf4119118a985334048fd30b68a5629f3e3196fa77e8200c49f`

## Findings and final disposition

1. **Archived-contract mutation (source trace):** `_archive_contract` augmented the caller's nested source map in place. Root changed it to a copied map. The new review tests assert the original and extracted contract dictionaries remain unchanged. This finding was traced in source; no independent pre-fix public failing run is claimed for it.
2. **Missing extracted helper dependency (actual pure-boundary RED):** a matching known extracted benchmark source was accepted without its imported `common.py`. Known dependent profiles now require the exact common seal. The original pre-extraction archive without that dependency remains valid.
3. **Unexpected candidate member (actual public RED):** adding a sealed `policy.backup.json` under an otherwise fully checked candidate still returned `verified`. Exact six-file candidate inventories now reject it. The RED used temporary copies of real preserved inputs, not live mutation.
4. **Local/shared binding mismatch (actual composed pure RED):** a structurally valid but foreign local binding passed `_financial -> _shared` with the genuine authority mirror. Nonhistorical bound owners now require matching authorization ID/path and the actual binding checksum. Positive control caught and corrected an initial comparison against the wrong checksum: binding terms hash is the canonical hash of the full validated authorization config, as stored by `_binding_values`, not the config's budget/scope-only terms field. Historical imported ledgers can legitimately be unbound or carry an earlier authority binding.
5. **Initial context versus immutable imported sources (actual pure-helper RED):** reducing the recovery row's recorded cost and coherent aggregate sums increased the accepted initial allowance. `_initial_context` now checks each historical row against its explicitly sealed history/current immutable owner identity. It preserves the distinction between initial aggregate costs and later current shared costs; mutable initial populations without the needed historical snapshot are unsupported.
6. **Archive decompression/typed errors (native RED plus independent runnable RED):** `ZipFile.read()` decompressed an underdeclared 32,768-byte body before returning its declared one-byte prefix, exceeding a patched 8,192-byte member ceiling; malformed DEFLATE escaped as `zlib.error`. Shared archive reads now use explicit `read(min(declared_size, member_ceiling)+1)`, check returned lengths, accept stored/deflated members only, and type ZIP/zlib/EOF/runtime failures as `ValidationError`.

Ignored RED evidence: `rec05b-verifier-counterexamples.json`, `rec05b-binding-counterexample.json`, `rec05b-context-counterexample.json`, `rec05b-archive-red.json`, `rec05b-bounded-archive-red.log`, and `rec05b-independent-focused-pre-binding-correction.log`, all in this directory. These preserve their original failure scope rather than becoming after-the-fix records.

## Verification actually completed

- `tests/test_search_verify_review.py` four groups plus `tests/test_evaluation_bytes.py` seventeen groups: **21 passed in 22.221 seconds, zero skips**. Log: `rec05b-independent-focused-green.log`.
- Earlier pure importer, benchmark and common compatibility subset: **49 passed**. A separate earlier 60-group continuation run had one exact-runtime refusal while another agent edited a source module. That orchestration failure was retained; no source guard was loosened. Root owns the final globally frozen full suite and CI.
- Ruff checks, formatting, strict mypy for the two owned app modules, and Bandit passed before final root suite.
- Scientific preservation is executable: the original benchmark module AST is reconstructed exactly from base `21660311596edeec3ef729168782c2967416f09b`. The ZIP/index validator matches its original AST after reversing only the sealed ZIP input and two bounded read substitutions. Old NB01/common compatibility maps and other continuation functions remain protected. See `rec05b-bounded-buffered-preservation.json`; the prior before-hardening proof remains separate.

The final actual-history probe used only the preserved 287-file expected map in `docs/conformance/nb01-preservation.json` and the independently fixed pilot archive seal. It did not create replacement seals from live files. Trusted stdlib CP437 decoding was preloaded before the no-exec window so a ZIP filename codec import was not confused with archived Python execution.

| Main run | Final result | Checked physical replies | Inherited replies | Local known cost (micro-USD) | Local hold |
| --- | --- | ---: | ---: | ---: | ---: |
| Original first attempt | Incomplete at exact unknown generation slot 9 | 9 | 0 | 1,709 | 532,373 |
| Fresh recovery | Verified | 63 | 0 | 300,153 | 0 |
| Linked continuation | Verified | 51 | 9 | 274,533 | 0 |

Current shared accounting remains separately reported: 576,395 known, 532,373 held, 1,108,768 committed micro-USD and 124 attempts. The original-only case matches one of three shared owners; the recovery case matches two; the linked case explicitly supplies and matches all three. `shared_scope` exposes unmatched owners instead of implying their local mirrors were checked.

Final actual evidence: `rec05b-real-verifier-final.json`, SHA256 `5e6eabcd3412d7a4aa29f9772e5153abf611d59d12056ae7edf3faa2f8c33bc4`; reproducible ignored script: `rec05b-real-verifier-final-probe.py`. All 287 protected inputs, the pilot ZIP, and all 34 package source hashes remained unchanged. The observation window forbids the listed writer APIs, network, authority/ledger/broker constructors, archived execution and source SQLite connections; only exact memory snapshots are queried.

## Remaining limits

- No material blocker remains from this bounded review. Full-suite/hosted CI completion remains root-owned and is not claimed here.
- A verified result establishes recorded-byte, slot, arithmetic, lineage and selected-mirror consistency. It does not establish provider origin, invoice reconciliation, meaningful diversity, correctness of semantic judgment, historical program execution or permission to spend.
- Incomplete results certify only the counted checked prefix and report its missing slot; they do not certify an unvisited tail or release liability.
- The archive reader bounds consumed/returned data. CPython's deflate decoder has a 4,096-byte floor; the production member ceiling is 16 MiB. It does not establish full compressed-stream validity: a forged underdeclared stream can still produce its indexed prefix under stdlib CRC semantics. BZIP2/LZMA are unsupported for this known runtime format. Nothing is extracted or imported.
- Byte ceilings are not a universal resident-memory or execution-time guarantee. Unknown scientific profiles and unsupported mutable historical context remain explicit rather than falling back to current defaults.
- This adds no retry, reconciliation, hold release, writer-liveness conclusion or lock deletion. REC-05C remains separate.
