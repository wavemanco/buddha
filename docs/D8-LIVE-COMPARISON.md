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

The original unfunded packages retain source `0d27ed4dd5aa44ce58618a6af6824141fed43f02`. The refreshed prospective packages bind a separate, clean runtime snapshot at `3214557b5b80bbf06fdac3924953fad5c8e51fb3`. D7 passed continuation and full qualification at 0d27; D6's separately identified `8e2fdc5` capacity run completed its workload in about 5h33m. The subsequent root-cause corrections have short-check and confined-pair evidence only. Neither earlier pass transfers full qualification to changed production source or establishes live performance/scientific improvement.

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

The actual native path runs the pinned official code through its locked SDKs and forwards captured request bytes unchanged through Buddha's Gateway. Required/forbidden fields are checked before reservation and key access. Earlier isolated P/C observations captured ten/eleven answer-generation calls respectively, all matching LOW/4,096. The prospective compatibility forks preserve those generation paths byte-for-byte; this is source continuity, not a new generation execution or a guarantee about every descendant. Fresh profile checks and pack bindings are recorded in the [pair-readiness receipt](conformance/d8-pair-readiness-delivery.json); the [original preparation receipt](conformance/d8-live-preparation-delivery.json) remains historical.

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
| Bad proposal stops the entire search | Study v5 can count a fully accounted malformed, unavailable, oversized or invalid proposal as a failed counted opportunity, including a counted child's witness, after complete census, settled accounting and clean cleanup. It need not become a child to count. | A failed common starting witness still stops with `common_ineligible`. Unknown billing, missing evidence or unsafe cleanup also stops; these cannot be reported as ordinary failed opportunities. |
| Feedback was cut short | Complete answers and official feedback are preserved. D6 checked forty-eight task-feedback records with full 8,192-byte answers and zero omissions. Historical one-request full-output capacity observation also passed. | D6 does not establish that every permitted 4,096-token answer fits this byte envelope. No silent truncation is allowed. |
| Arbitrary size ceiling | The corrected prospective full-feedback path shares the existing 32 MiB JSON allowance across builder, host, worker and new starter v3. Complete Unicode input above 1 MiB reaches the captured model callback unchanged in short regression checks. Historical 1 MiB policies and starter v1/v2 bytes remain exact. | This closes the reproduced legacy-1-MiB rejection on the corrected path. The whole configuration still must fit 32 MiB framing and each callback 16 MiB; token/context and runtime limits remain. It does not make every 32 MiB feedback document executable. Frozen agents are not automatically updated. |
| Timeout caused by repeated historical reconstruction | The corrected forward runner reuses checked current state and performs fresh inspection after writes. D6 completed the intended synthetic history; D7 passed the full offline continuation regression and both full OS suites. | Fresh whole-history reads remain substantial. No new hours-long capacity rebuild or old/new-run migration is proposed. |
| Provider takes longer than expected | Generation/proposal worker limit remains 900 seconds; native stage 1,800 seconds. A proven, owned proposal-worker timeout before its done frame can now count as a failed opportunity after complete settled callback/capacity checks, source verification and successful cleanup. No child or score is invented. | The HTTP timeout, up to 600 seconds, is a socket inactivity limit, not a whole-call guarantee. Several slow calls can exhaust a worker. The executor waits for in-flight accounting and cleanup, so host elapsed time can exceed worker lifetime. Unknown liability, timeout after done, and missing native judge scores remain partial. |
| Timeout/disconnect may have been charged | One dispatched unknown operation retains its full hold and stops shared authority; no blind retry, fallback or automatic hold release. The corrected shared transport preserves a fixed safe error family through pre-response, partial-body and header failures into saved candidate/native reports. | The financial stop remains necessary. `provider_error_family` records only `timeout`, `connection`, `tls`, `http`, `os_error` or `other`; no raw exception text. Old causes cannot be reconstructed, and a crash before report publication is outside this report-level proof. |
| Cosmetic metadata/prose differences | Native requests retain immutable SDK-produced bytes. Official schemas/parsing remain unchanged; checked reuse binds actual source/request/content rather than an informal summary. | No evidence found of this screenshot's signed-reasoning/tool-metadata/cache-annotation bugs in Buddha's text interface. Do not add speculative compatibility repairs. |
| Source, cleanup, budget or sealed-data violation | Existing identity, owned-process cleanup, accounting, split and budget checks remain mandatory. | These stops protect the experiment. They must not be bypassed to report completion. |

Both root-cause corrections now have short red/green regressions; the [correction receipt](conformance/d8-stop-root-causes-delivery.json) records exact scope and evidence. No ledger migration, new orchestration framework or official benchmark change was added. Original source0d27, its qualification and its prepared packages remain unchanged.

### The four pre-live risks and their actual evidence

| Risk | Correction / observed result | Practical boundary |
| --- | --- | --- |
| Escaping and wrappers enlarge requests | Actual confined workers received complete synthetic feedback of 1,572,970 bytes for a root case and 3,145,147 for an immediate-parent comparison. Both compatible actors preserved every full answer in the captured HTTP bodies, including all thirty current and thirty parent answers in the comparison. Largest body was 3,726,439 bytes; frame 4,968,657; cumulative stdout 4,969,512. | Below the unchanged 16 MiB body and 32 MiB frame/cumulative-output limits for these cases. This is representative evidence, not proof that every allowed 32 MiB feedback document or every Unicode/token distribution fits. No answer is shortened to make a limit pass. |
| Several slow callbacks exceed worker lifetime | Retain the existing deadlines; classify only a proven, fully settled proposal timeout as a rejected opportunity. Seven focused lifecycle/outcome checks pass, including unknown charges, uncertain cleanup, source drift and after-done counterexamples. | No latency guarantee, new timer framework, blanket timeout increase or paid retry. Genuine incomplete evaluation/accounting remains partial. |
| Completed proposal fails an arbitrary token cushion | Explicit capacity policy v2 removes the extra 8,192 unused-context/output-token requirements. Sixteen capacity methods plus a strengthened guard check pass. V1 remains exact. | Input plus the entire declared output cap must still fit 1,050,000 tokens; actual usage must be authoritative and within bounds. Normal finish, no refusal, exact full replacement and full accounting remain required. Mock token counts do not establish live fit. |
| Evolved program has its own smaller guard | The first confined check exposed C's own 1 MiB limit before any callback. A separate confined diagnostic located its exact guard. Prospective Ccompat changes only the seven bytes `1024**2` to `32*1024**2`; every other source byte remains exact. P3/Ccompat then passed both feedback shapes in 13.032 seconds. All four owned containers were removed, with no provider calls. | The original failure/diagnostic remain retained. These observations do not exhaust every branch of evolved or future code. Original source and prior experiment claims remain unchanged. |

The proposed pair is **P3** `b84ae0e3…` and **Ccompat** `d7ea5936…`.
Historical P `77cfa68f…` and C `4196cd29…` remain untouched. Both compatibility
forks keep their generation and improvement algorithms; only their input-capacity
compatibility changes. Ccompat descends from historical C, which descended from
historical P; it does **not** descend from P3. The refreshed comparison must report
these actual identities and prospectively adopt the changed pair and policy.
It must not reuse the old study's source identities or rewrite its results.

## Preparation status and next stopping point

All four refreshed unfunded preparations completed in **21.708 seconds** within
the 120-second short bound. Their directories are
`runs/imp01-d8-ready-primary-20261107-v1`,
`runs/imp01-d8-ready-plain-20261107-v1`,
`runs/imp01-d8-ready-review-20261107-v1` and
`runs/imp01-d8-ready-combined-20261107-v1`. Exact manifests, results and all
133 indexed output hashes are bound in the pair-readiness receipt. The earlier
0d27 packages and their 21.723-second result remain historical.

The fresh profile check's saved output accepts seven synthetic requests and
rejects twenty-seven altered variants. Its outer summary used the wrong output
key after the checker returned; this readback error is retained, with no rerun
or inferred child exit-code/duration claim. No production rule changed to make
the diagnostic pass. Independent reviews check the runtime code, exact C patch,
full-answer request evidence, preparation manifests and output joins.

The four existing metadata builders are reused, with preparation-only path/hash
bindings recorded as provenance. Selected programs are copied/hashed, never
imported, compiled or executed on the host. Inherited custody references remain
hash-only. No original paid history, owners, grants or unresolved charges are
imported. The combined declaration is explicitly unadopted and unfunded.
Inherited nominal per-owner envelopes are not allocations: final funding must
bind the actual $25 shared plain-reference cap and $150 combined phase limits
before any owner can spend.

The November 8 qualification completed at `ad8e5c1` with the same obsolete
boundary-test failure on both OSes; all other methods passed or had declared
skips, and all 70 quality checks passed. The original run remains failed.
A separate test-only correction selects the preserved 1 MiB policy for the
legacy rejection check, restores/verifies the 32 MiB default, and adds that case
to short CI. Runtime `3214557` is unchanged. All 348 Python files in frozen
qualification source `ad8e5c1` match that runtime; the corrected test head
intentionally differs in two test-support Python files. Production code and
configuration remain identical. It has no new full-suite pass.

Before a live command is issued: finish the corrected candidate's short checks
on both OSes and independent review, obtain the user's decision on the
[narrow evidence-reuse proposal or a new full qualification](CI-TESTS.md#november-8-result-and-proposed-test-only-acceptance),
then adopt the actual pair/policy and truthful custody/scope, confirm current
accounts, obtain a fresh allocation, and bind/check the funded outer handoff.
Recheck outgoing request settings immediately before paid calls. No new capacity
rebuild or infrastructure gate is introduced. [Outcome](conformance/d8-qualification-outcome.json).

There is **no live command to run yet**. The final funded handoff will give one exact standalone PowerShell command, explain what it spends/changes, when keys are entered and how to stop. Read-only optional commands will also have plain-English explanations. No keys belong in chat, a command line, a committed file or a report.
