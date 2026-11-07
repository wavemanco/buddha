# D8: live-comparison preparation

November 7, 2026. Preparation only: **unfunded and not cleared to launch**. [PLAN D8](PLAN.md) owns scheduling; this is its handoff and limits guide. No keys, model calls, new long runs or main merge are authorized here.

## What this comparison will tell us

The main question is whether the evolved Python improver produces better descendants than the original improver when both get the same starts, complete development feedback and opportunities. Two plain-model controls also measure what the harness adds relative to using the same generator directly. A loss or inconclusive result is a valid result.

| Part | Declared workload |
| --- | --- |
| Development | Three official WildChat tasks; two starts, two repeated conditions and two improver arms; two descendant opportunities per arm/condition, sixteen opportunities total. Twenty screens cover at most sixty ten-answer task sets. |
| Primary final assessment | Twenty-six prospectively separated WildChat tasks; at most 312 ten-answer sets, or 3,120 answers. Final feedback does not return to development. |
| Plain controls | The same generator without Buddha instructions: independent sampling and in-context sampling, each on the same twenty-six final tasks; 520 answers together. |
| Review | AI-only results proceed independently of human availability. Proposed native review: at most forty-four fresh `gpt-6.1-sol`/ULTRA contexts, including thirty-two target contexts/up to sixty-four staged judgments and twelve whole-set judgments. Optional human ratings remain a separate, nonblocking extension. |

That is at most 424 scored ten-answer sets/4,240 answers, plus development mutation-witness work. It is a bounded harness experiment, **not** a full leaderboard submission or a claim that all NoveltyBench tasks are unseen. The retained split/custody references must remain intact; metadata hashes alone cannot certify absence of exposure.

The prepared, unfunded packages still select qualified source `0d27ed4dd5aa44ce58618a6af6824141fed43f02`. D7 passed continuation and full qualification there; D6's separately identified `8e2fdc5` capacity run completed its workload in about 5h33m. The subsequent root-cause corrections described below have short-check evidence only. Neither earlier pass transfers full qualification to changed production source or establishes live performance/scientific improvement.

## Model requests, checked against current official code

NoveltyBench source remains pinned to `64a23be6b18ec1dacc298830aab276061b6e143c`. Its current public files match the source seals used by our official-SDK request fixtures.

| Role | Settings that must reach the provider |
| --- | --- |
| Answer generation | Model choice remains configurable for supported compatible routes. Proposed baseline: `gpt-5.6-luna`, LOW reasoning, `max_completion_tokens: 4096`, no temperature/top-p; declared standard/default service tier. Both plain sampling modes use the same settings. |
| Distinctiveness judge | Explicitly select `gpt-5.6-luna`; official full-response partition messages/schema; **omit** explicit reasoning effort, output-token limit, temperature and service tier. The pinned SDK supplies `stream: false`. Omission inherits provider behavior; it does not disable reasoning. |
| Utility judge | `claude-opus-5`; adaptive thinking, HIGH effort, `max_tokens: 16000`, official strict score schema. |
| Official utility refusal fallback | `claude-sonnet-5`, only after the official refusal condition. This changes the utility model explicitly; it is not a generic timeout, billing or generator fallback. |

The [submission instructions](https://novelty-bench.github.io/submit.html) specify CLI allowance 2,048 and LOW generator effort. The official [reasoning helper, lines 46–58](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/inference.py#L46-L58) doubles that allowance on the wire because reasoning and visible output share it: 4,096 is the matching request, not an independently imposed change. It does not guarantee 2,048 visible tokens. Judge settings come from [utility lines 66–77](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/judge.py#L66-L77), [partition lines 95–113](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/judge.py#L95-L113) and [refusal lines 116–128](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/judge.py#L116-L128). The generic partition CLI default is not the leaderboard's Luna selection; our declaration must select it explicitly.

Python proposal authoring and native review are separate roles from answer generation. The proposed authoring model is `gpt-6.1-sol`, with its existing 32,768-output-token allowance. Do not apply the generator's LOW setting indiscriminately to these roles. Official model names above are aliases, not immutable dated model snapshots. Response model/tier mismatches stop for review rather than silently substitute another model.

The actual native path runs the pinned official code through its locked SDKs and forwards captured request bytes unchanged through Buddha's Gateway. Required/forbidden fields are checked before reservation and key access. Earlier isolated P/C observations captured ten/eleven answer-generation calls respectively, all matching LOW/4,096. These are preserved observations of the same selected source hashes, not fresh executions or guarantees about every descendant. New offline request checks and fresh pack bindings are recorded in the [delivery receipt](conformance/d8-live-preparation-delivery.json).

## Proposed API allowance

The earlier $150 allocation is closed. This proposal creates no authority and cannot use its unused balance.

| Phase | Combined OpenAI + Anthropic cap | Recorded-attempt limit |
| --- | ---: | ---: |
| Development | $40 | 4,096 |
| Primary final | $85 | 10,240 |
| Both plain references together | $25 | 2,048 |
| Total | **$150** | **16,384** |

These are phase caps, not provider caps or expected spending. Exhausting one phase can produce a partial even if another phase has unused allowance; no unapproved transfer is implied. A recorded attempt is not necessarily a charged API reply. A call with uncertain billing keeps its reservation held. Partial results must retain phase, reason, counts, recorded cost and unresolved holds.

A conditional planning ballpark is **$8–20 OpenAI and $20–60 Anthropic**, about **$28–80 combined**. This scales the earlier incomplete 657-operation sample across at most 424 scored sets, allowing roughly 3.56–10 utility groups per set. It is not a measured final-workload forecast, confidence interval or extra cap. Longer answers, fuller proposal context, different grouping, retries or model behavior can exceed it. Recorded configured-rate costs are not provider invoices.

Public Standard input/output prices checked November 7, in USD per million tokens: [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) $0.20/$1.20; [Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) $2/$10; [Opus](https://platform.claude.com/docs/en/about-claude/pricing) $5/$25, Sonnet $2/$10. Existing stored reservation ceilings are more conservative, including reviewed long-context/cache cases and a cushion. Account access, quota and any changed account terms still need confirmation at launch. Earlier user assertions were standard/default processing and public pay-as-you-go for both providers; they have not been silently replaced with a contract assumption.

Native Codex review consumes **unpriced Codex-plan capacity outside the API allowance**. It is not free and has no reviewer API fallback. Human review does not hold up AI-only reporting. Fresh funding/scope adoption must explicitly include the native selection.

## What reduces avoidable stops, and what still can stop

The user's screenshot describes another project. It supplies useful failure categories, not evidence that those incidents happened in Buddha.

| Concern | What Buddha already does / evidence | Remaining limit |
| --- | --- | --- |
| Bad proposal stops the entire search | A fully accounted malformed, unavailable, oversized or invalid proposal counts as a failed opportunity after complete census, settled accounting and clean cleanup. It need not become a child to count. Existing boundary tests exercise settled failures versus unresolved evidence. | Unknown billing, missing evidence or unsafe cleanup still stops; calling those a bad proposal would hide a consequential failure. |
| Feedback was cut short | Complete answers and official feedback are preserved. D6 checked forty-eight task-feedback records with full 8,192-byte answers and zero omissions. Historical one-request full-output capacity observation also passed. | D6 does not establish that every permitted 4,096-token answer fits this byte envelope. No silent truncation is allowed. |
| Arbitrary size ceiling | The corrected prospective full-feedback path shares the existing 32 MiB JSON allowance across builder, host, worker and new starter v3. Complete Unicode input above 1 MiB reaches the captured model callback unchanged in short regression checks. Historical 1 MiB policies and starter v1/v2 bytes remain exact. | This closes the reproduced legacy-1-MiB rejection on the corrected path. The whole configuration still must fit 32 MiB framing and each callback 16 MiB; token/context and runtime limits remain. It does not make every 32 MiB feedback document executable. Frozen agents are not automatically updated. |
| Timeout caused by repeated historical reconstruction | The corrected forward runner reuses checked current state and performs fresh inspection after writes. D6 completed the intended synthetic history; D7 passed the full offline continuation regression and both full OS suites. | Fresh whole-history reads remain substantial. No new hours-long capacity rebuild or old/new-run migration is proposed. |
| Provider takes longer than expected | Existing generation/proposal worker limit is 900 seconds; native stage 1,800 seconds. Funded HTTP timeout is chosen explicitly, up to 600 seconds. Limits and stage outcomes are retained. | Several calls at worst-case network latency need not fit a worker's total allowance. Offline checks cannot prove live latency. No new arbitrary remaining-time threshold is introduced. |
| Timeout/disconnect may have been charged | One dispatched unknown operation retains its full hold and stops shared authority; no blind retry, fallback or automatic hold release. The corrected shared transport preserves a fixed safe error family through pre-response, partial-body and header failures into saved candidate/native reports. | The financial stop remains necessary. `provider_error_family` records only `timeout`, `connection`, `tls`, `http`, `os_error` or `other`; no raw exception text. Old causes cannot be reconstructed, and a crash before report publication is outside this report-level proof. |
| Cosmetic metadata/prose differences | Native requests retain immutable SDK-produced bytes. Official schemas/parsing remain unchanged; checked reuse binds actual source/request/content rather than an informal summary. | No evidence found of this screenshot's signed-reasoning/tool-metadata/cache-annotation bugs in Buddha's text interface. Do not add speculative compatibility repairs. |
| Source, cleanup, budget or sealed-data violation | Existing identity, owned-process cleanup, accounting, split and budget checks remain mandatory. | These stops protect the experiment. They must not be bypassed to report completion. |

Both root-cause corrections now have short red/green regressions; the [correction receipt](conformance/d8-stop-root-causes-delivery.json) records exact scope and evidence. No ledger migration, new orchestration framework or official benchmark change was added. Original source0d27, its qualification and its prepared packages remain unchanged.

Other preventable-stop risks to check before spending are larger JSON wrappers/escaping, the selected agents' own input checks and several individually slow calls exceeding one worker's total lifetime. The declared proposal-capacity policy also requires 8,192 unused output tokens and 8,192 context tokens: a normally completed replacement can fail that conservative margin. This is an explicit policy constraint, not a newly demonstrated implementation defect; changing it needs prospective protocol review. No new arbitrary remaining-time cutoff or speculative limit increase was added here.

The original selected P hash `77cfa68f…` is exactly the preserved starter v2 and still rejects feedback above its own 1 MiB guard. A prospective v3 initial source is prepared separately, not adopted, with the plain generation prefix unchanged. The evolved C source was not blindly patched: it contains neither exact inherited guard pattern, which does not prove large-feedback compatibility. Verify the selected pair in confinement and explicitly bind any compatibility/source changes before a fresh live handoff. Preserve original P/C identities and report the comparison's actual source versions.

## Preparation status and next stopping point

All four unfunded preparations completed in **21.723 seconds** within the 120-second short bound. Their directories are `runs/imp01-d8-primary-20261107-v1`, `runs/imp01-d8-plain-20261107-v1`, `runs/imp01-d8-review-20261107-v1` and `runs/imp01-d8-combined-20261107-v1`. Exact manifests, results and all 133 indexed output hashes are bound in the delivery receipt. Fresh profile checks accept seven synthetic requests and reject twenty-seven altered variants; seventy-eight selected test methods have valid passing observations. Separately retained audit-wrapper failures are explained in the receipt; no production invariant was changed. The four existing metadata builders are reused; any preparation-only path/hash rebinding must itself be recorded and bound as provenance. Selected programs are not imported, compiled or executed on the host; existing byte/UTF-8 validation remains. Inherited custody references remain hash-only. No original paid history, owners, grants or unresolved charges are imported into a fresh experiment.

Before a live command is issued: select and verify the corrected source and compatible improver pair; refresh the existing handoff bindings and independent review; adopt truthful custody and the final scope; obtain a fresh allocation; bind and check the funded outer handoff. Any further full qualification or long run requires separate approval. Recheck actual request settings immediately before paid calls. No new capacity rebuild or infrastructure gate is introduced.

There is **no live command to run yet**. The final funded handoff will give one exact standalone PowerShell command, explain what it spends/changes, when keys are entered and how to stop. Read-only optional commands will also have plain-English explanations. No keys belong in chat, a command line, a committed file or a report.
