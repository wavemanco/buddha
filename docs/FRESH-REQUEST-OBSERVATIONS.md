# Fresh request observations: source agents and installed judges

These checks ran the prepared P and C programs and the installed NoveltyBench worker in real isolated containers, while supplying manufactured model replies. They verify the requests that reached the host request boundary and the declared refusal handling. They produced no actual provider API calls or scientific measurements.

The [delivery record](conformance/fresh-request-observations-delivery.json) binds the saved results, diagnostic sources, stage observations and dated CI metadata. The [living plan](PLAN.md) remains the scheduling authority.

## What the source-agent check did

P is the initial source agent and C is the changed source agent selected for the fresh comparison. Each received one synthetic task requesting ten answers. Their Python ran only inside the pinned source-agent image; model traffic passed through the normal host Gateway into a mocked HTTP connection. The connection returned fixed replies instead of contacting OpenAI.

| Observed result | P | C |
| --- | ---: | ---: |
| Answers returned | 10 | 10 |
| Model callbacks completed | 10 | 11 |
| Mocked HTTP requests checked | 10 | 11 |
| Container exit | 0 | 0 |
| Owned-container cleanup reported | removed | removed |

Every captured generator request used `gpt-5.6-luna`, `reasoning_effort: low`, `max_completion_tokens: 4096` and `service_tier: default`, with no unexpected extra request fields. Both settings checks and HTTP-boundary checks passed. The combined parent observation took **9.351 seconds**.

C's extra callback is retained as an observed resource difference in this supplied case. Ten returned answers do not imply identical work by the two programs. These manufactured replies cannot establish their behavior, quality or costs with a real model.

The ordinary host constructor validates opaque program bytes as UTF-8. Describing this route as copying and hashing only would be inaccurate. Program compilation and execution remain inside the container; this check did not interpret the program's Python on the host.

## What the installed judge check did

Five real containers ran the installed current native worker, SDKs and unchanged pinned NoveltyBench 1.1 evaluator. A host transport supplied synthetic replies. The task text was a diagnostic marker, and the generated-answer file was synthetic. The check used ordinary file-inventory validation; it did not use selected benchmark prompts as task input.

| Case | Observed request and outcome |
| --- | --- |
| Distinctiveness partition | One `gpt-5.6-luna` request; complete partition output. The body contains messages, model, JSON response format and `stream: false`, with no explicit reasoning-effort or output-token override. |
| Valid utility score | One `claude-opus-5` request with adaptive thinking, high effort and `max_tokens: 16000`; complete score output. |
| Summary | Complete native summary output, with no model request. |
| Explicit utility refusal | Opus receives the same scoring settings, then the declared fallback calls `claude-sonnet-5` with the inherited adaptive/high/16000 settings; complete score output. |
| Non-refusal length failure | One Opus request, no Sonnet fallback, a failed native completion (`native_error`) and a retained partial score artifact. |

The last case is an expected negative control: the diagnostic passes because a length failure does not trigger refusal fallback. Its worker process exits zero after reporting the structured failure; this is not a successful utility assessment.

All five containers exited zero and reported owned removal. The combined parent observation took **124.842 seconds**. The stage records retain request-body hashes, selected settings, completion status and artifact hashes. Raw chat bodies are not reproduced here. The evaluator, judge settings and benchmark formulas were unchanged. This is a native-worker-only diagnostic with a synthetic file-hash anchor; it does not establish full C1 derivation, NativeSession or financial composition.

## Resource and evidence limits

The source containers used **256 MiB** of memory; the native containers used **2 GiB**. Both checks shortened the worker wall limit to **180 seconds**, while retaining the other configured limits. The prepared study still specifies 900 seconds for source generation and 1,800 seconds for native evaluation. These observations do not establish that the study fits those longer workload limits. Neither parent imposed a separate outer hard-kill deadline.

Across the two checks, seven containers reported removal and actual provider API use was **zero**. Synthetic accounting figures in the source diagnostic are manufactured test values, not charges or a spending allocation. The native diagnostic created no accounting owners or grants. Both parent records report all 360 pinned public Python files unchanged; their result records also preserve the bound input hashes.

The first source attempt remains a **partial**, stopped during fixture setup before any container execution or HTTP request. A separate retained cause observation identified the fixture's blanket socket guard rejecting `socket.gethostname`. The later v2 attempt allowed that local identity operation and completed. This is a diagnostic-fixture correction, not an observed failure of P, C, Docker or a model provider. The v1 cleanup flag does not prove that every nested temporary directory was removed.

The v1 parent records the diagnostic bytes it executed. Its current same-name file is a later formatted cut, so the present file does not reproduce that executed source hash. The delivery keeps both identities explicit and does not reconstruct or claim availability of the exact historical bytes under that filename. The successful v2 diagnostic remains at its recorded source hash.

## Hosted status and what remains

The following is the saved **01:03 UTC, November 3, 2026** metadata snapshot, not a current or full-coverage assertion:

| PR | Successful jobs | Still running |
| --- | ---: | ---: |
| 216 | 10 | 0 |
| 217 | 8 | 2 |
| 218 | 6 | 4 |
| 219 | 5 | 5 |
| 220 | 4 | 6 |
| 221 | 2 | 8 |

No failures or cancellations were recorded. All six PRs were open, non-draft and unmerged at their expected heads. Job conclusions are separate from a full ordered hosted-coverage review.

The source-agent and installed-SDK request subchecks now have actual container evidence within this synthetic scope. They do not establish real model behavior, full 26-task capacity, meaningful distinctiveness, utility improvement, comparative performance, task-separation adoption, account access, prices, a new spending allocation or live readiness. The [comparable-size gate](RECONSTRUCTION-COST.md) and remaining [pre-live checks](PLAN.md#current-checkpoint) retain their own requirements.

These are operator-only diagnostic observations. This document provides no live-run or replay command.

