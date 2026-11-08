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

Python proposal authoring and native review are separate roles from answer generation. The proposed P3/Ccompat2 pair's four captured authoring requests use `gpt-6.1-sol`, `reasoning_effort: low`, `max_completion_tokens: 32768` and `service_tier: default`. LOW is the observed frozen authoring recipe for this pair; native Codex review remains proposed `gpt-6.1-sol`/ULTRA. This records the settings without changing them. Official model names above are aliases, not immutable dated model snapshots. Response model/tier mismatches stop for review rather than silently substitute another model.

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
| Arbitrary size ceiling | The full-feedback path uses the existing 32 MiB JSON allowance and preserves complete outputs. The prospective Ccompat2 also raises the remaining evolved per-note guard from 1 MiB to 32 MiB. Historical policies and source bytes remain exact. | This removes the reproduced smaller guard; it does not promise every 32 MiB feedback document fits the complete 16 MiB callback body or model context. Exact request/frame checks remain, and policy v2 evaluates capacity from actual original proposal calls. |
| Timeout caused by repeated historical reconstruction | The corrected forward runner reuses checked current state and performs fresh inspection after writes. D6 completed the intended synthetic history; D7 passed the full offline continuation regression and both full OS suites. | Fresh whole-history reads remain substantial. No new hours-long capacity rebuild or old/new-run migration is proposed. |
| Provider takes longer than expected | Generation/proposal worker limit remains 900 seconds; native stage 1,800 seconds. A proven, owned proposal-worker timeout before its done frame can now count as a failed opportunity after complete settled callback/capacity checks, source verification and successful cleanup. No child or score is invented. | The HTTP timeout, up to 600 seconds, is a socket inactivity limit, not a whole-call guarantee. Several slow calls can exhaust a worker. The executor waits for in-flight accounting and cleanup, so host elapsed time can exceed worker lifetime. Unknown liability, timeout after done, and missing native judge scores remain partial. |
| Timeout/disconnect may have been charged | One dispatched unknown operation retains its full hold and stops shared authority; no blind retry, fallback or automatic hold release. The corrected shared transport preserves a fixed safe error family through pre-response, partial-body and header failures into saved candidate/native reports. | The financial stop remains necessary. `provider_error_family` records only `timeout`, `connection`, `tls`, `http`, `os_error` or `other`; no raw exception text. Old causes cannot be reconstructed, and a crash before report publication is outside this report-level proof. |
| Cosmetic metadata/prose differences | Native requests retain immutable SDK-produced bytes. Official schemas/parsing remain unchanged; checked reuse binds actual source/request/content rather than an informal summary. | No evidence found of this screenshot's signed-reasoning/tool-metadata/cache-annotation bugs in Buddha's text interface. Do not add speculative compatibility repairs. |
| Source, cleanup, budget or sealed-data violation | Existing identity, owned-process cleanup, accounting, split and budget checks remain mandatory. | These stops protect the experiment. They must not be bypassed to report completion. |

Both root-cause corrections now have short red/green regressions; the [correction receipt](conformance/d8-stop-root-causes-delivery.json) records exact scope and evidence. No ledger migration, new orchestration framework or official benchmark change was added. Original source0d27, its qualification and its prepared packages remain unchanged.

### The four pre-live risks and their actual evidence

| Risk | Correction / observed result | Practical boundary |
| --- | --- | --- |
| Escaping and wrappers enlarge requests | Earlier P3/Ccompat confined checks preserved thirty current and thirty parent answers: largest body 3,726,439 bytes; frame 4,968,657; cumulative stdout 4,969,512. New short executor checks use a supplied Docker fixture at the maximum 16 MiB callback-body size and with four requests whose total output exceeds the old 32 MiB cumulative allowance. | Per-body 16 MiB and per-frame 32 MiB bounds remain. The existing helper now sets cumulative stdout to at least (callback allowance + 3) times 32 MiB, retaining a larger existing value: twelve callbacks give 480 MiB. This is a derived stream allowance, not a promise every feedback document fits every downstream limit. |
| Several slow callbacks exceed worker lifetime | Retain the existing deadlines; classify only a proven, fully settled proposal timeout as a rejected opportunity. Seven focused lifecycle/outcome checks pass, including unknown charges, uncertain cleanup, source drift and after-done counterexamples. | No latency guarantee, new timer framework, blanket timeout increase or paid retry. Genuine incomplete evaluation/accounting remains partial. |
| Completed proposal fails an arbitrary token cushion | Explicit capacity policy v2 removes the extra 8,192 unused-context/output-token requirements. Existing checks preserve the exact v1 policy and hard v2 bounds. DESIGN section 4 already permits prospectively adopting observations from the actual original proposal calls instead of certifying future requests in advance. | Before admitting a returned child, authoritative input usage plus the whole requested output allowance must fit 1,050,000 tokens; normal finish, no refusal, exact complete replacement and full original-call accounting are required. No tokenizer or bytes-as-tokens heuristic is added. Future requests have not passed in advance. |
| Evolved program has its own smaller guard | The earlier confined diagnosis corrected C's aggregate 1 MiB projection guard in Ccompat. The next boundary review found a separate per-note 1 MiB guard that remained. Prospective Ccompat2 changes only that remaining guard to 32 MiB; all other Ccompat source bytes stay exact. | Original C, Ccompat, their failures and the earlier 13.032-second four-session result remain historical evidence. P3/Ccompat2 then pass four short confined sessions in 26.370 seconds; all owned containers are removed. Complete feedback and a maximum-size parent source reach the mocked callback unchanged. These corrections do not certify every branch of future evolved programs. |

The proposed pair is now **P3** `b84ae0e3…` and **Ccompat2**
`f1c832d5168986bf4bf220bb31f31754192cf262d523118b1f47ea0540fb6bc7`.
Historical P `77cfa68f…`, C `4196cd29…` and Ccompat `d7ea5936…` remain
untouched. Ccompat2 follows Ccompat and historical C; it does not descend from
P3. The two guard corrections change input capacity, not the generation or
improvement algorithms. The refreshed comparison must disclose and prospectively
adopt these actual identities and policy, without rewriting the earlier study.

Fresh runtime `c28851f9a9d85b02e86ed14589de4877353561c7` pins all 348 Python
files. All 84 core production files remain unchanged from `3214557`; four
helper/test-support Python files differ from `5ab`, five from `3214557` including
the earlier test-only correction. The existing preparation helper derives the
cumulative stdout allowance from configured callbacks; proposal and plain-reference
preparations inherit it. Memory remains 256 MiB, with the existing 900-second
source worker and 1,800-second native worker limits. Six short checks pass in
1.9885 seconds, using supplied executor/metadata/model-reply fixtures, not real
containers or provider calls. The selected P3/Ccompat2 pair then passes four
actual confined sessions in 26.370 seconds within 120 seconds. They preserve
all thirty current and thirty parent answers and a 1,048,576-byte parent source.
Each comparison note is 2,717,388 bytes, exceeding the old per-note guard.
The largest complete request body is 12,694,920 bytes, below the unchanged
16 MiB bound. Maximum observed initial configuration is 11,362,911 bytes;
callback frame 16,926,629 bytes; cumulative stdout 16,927,484 bytes.
Every owned container exits successfully and is removed.
Provider replies and usage are supplied; no model call or returned-source
execution occurs. This is transport evidence, not a live context-capacity proof.
[Workload-capacity delivery](conformance/d8-workload-capacity-delivery.json).

The local feedback ceiling is a safety bound, not a universal fit guarantee.
The request body, JSON/base64 frame and model context have distinct limits.
For model context, the proposal uses the existing [actual-call capacity route](SOURCE-PROPOSAL-CAPACITY.md)
allowed by DESIGN section 4: inspect authoritative usage from every actual
original proposal call before admitting a child. Do not add a pessimistic
bytes-as-tokens stop, truncate answers or require another advance guarantee
for arbitrary future descendants. Genuine excessive context, incomplete
replies, unknown charges and unsafe cleanup retain their stops.

## Preparation status and next stopping point

The earlier P3/Ccompat unfunded preparations completed in **21.708 seconds** within
the 120-second short bound. Their directories are
`runs/imp01-d8-ready-primary-20261107-v1`,
`runs/imp01-d8-ready-plain-20261107-v1`,
`runs/imp01-d8-ready-review-20261107-v1` and
`runs/imp01-d8-ready-combined-20261107-v1`. Exact manifests, results and all
133 indexed output hashes are bound in the pair-readiness receipt. The earlier
0d27 packages and their 21.723-second result remain historical.

The corrected v3 refresh now completes all four existing metadata builders in
**22.729 seconds** within 120 seconds, at runtime `c28851f`. The new unfunded
directories are `runs/imp01-d8-capacity-primary-20261108-v3`,
`runs/imp01-d8-capacity-plain-20261108-v3`,
`runs/imp01-d8-capacity-review-20261108-v3` and
`runs/imp01-d8-capacity-combined-20261108-v3`. Their independent output review
is still pending. No owners, spending authorities or API allocations are created.

Two earlier short metadata partials remain retained: 2.071671 seconds stopped
on the old study's selected-agent identity; 12.752453 seconds completed primary
and plain preparation before an unnecessary extra evidence reference made the
review input count eleven instead of ten. The fresh v3 input data removes only
that optional reference, retaining it in delivery evidence; the existing
ten-input guard is unchanged. Fresh output folders preserve both partials.

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

The November 8 qualification at `ad8e5c1` remains failed on the same outdated
boundary test per OS, with all other methods passed or declared skipped and
all 70 quality checks successful. PR #282 corrects only that test and its short
selection; both OSes pass 515 methods and all 14 quality checks. It has no fresh
full-suite pass. The user's decision on [narrow evidence reuse](CI-TESTS.md#november-8-result-and-proposed-test-only-acceptance)
remains pending. The original runtime `3214557` and earlier frozen sources remain exact.
The fresh `c28851f` runtime, helper settings and selected pair are prospective
preparation inputs, with no new full-suite pass.

Next finish independent output review and verify the planned 517-check
hosted short CI. Then present **one concrete adoption/funding/handoff request**:
actual pair and capacity policy v2, scientific scope and truthful custody,
reviewed evidence reuse, current account terms, fresh allocation and native-review
setup. Only after approval and final funded checks should a live command be
issued. Recheck actual outgoing model settings immediately before paid calls.
No new full qualification, capacity rebuild or long observation follows
automatically. [Qualification outcome](conformance/d8-qualification-outcome.json),
[workload-capacity delivery](conformance/d8-workload-capacity-delivery.json).

There is **no live command to run yet**. The final funded handoff will give one exact standalone PowerShell command, explain what it spends/changes, when keys are entered and how to stop. Read-only optional commands will also have plain-English explanations. No keys belong in chat, a command line, a committed file or a report.
