# Current comparison preparation and review tracks

The comparison is prepared at executing source `ebce35e1`, but it is still
**unapproved, unadopted, unfunded and not ready to launch**. There is no command
to run from this document. The final handoff will supply the exact command after
the remaining checks and decisions. [PLAN.md](PLAN.md) owns scheduling.

The user's October 26 decision establishes two evidence tracks over the same
frozen experiment. **AI-only work proceeds without waiting for human reviewers.**
The [human extension](REVIEW-TRACKS.md) adds actual ratings later; the project
owner is the first selected human reviewer. Selection is not a completed rating.

## What the run measures

The primary question remains whether the evolved Buddha improver produces
better descendants than the initial improver under common conditions. Two plain
references measure direct use of the same generator, with independent and
in-context sampling. They reuse compatible Buddha results. This is not another
round of testing or redefining NoveltyBench.

| Component | Frozen scope |
| --- | --- |
| Development | Three WildChat tasks, two starting bundles, two repetitions and two descendant opportunities per improver arm: sixteen opportunities. |
| Buddha final assessment | Twenty-six tasks in twenty-five declared families; at most 312 answer sets / 3,120 answer positions. |
| Plain references | The identical final tasks, twenty-six sets per sampling mode: fifty-two sets / 520 answer positions. |
| Whole-set review sample | Twelve Buddha sets, up to 120 complete answers, with condition labels hidden. |

Development and mutation-check answers are additional to the final-panel counts.
These counts do not predict physical requests. Missing descendant slots remain
in the planned analysis. Family assumptions, full planned denominators, failures,
costs and uncertainty remain explicit. This is a bounded study, not a full
leaderboard submission or a required four-condition Buddha sampling experiment.

## One proposed API cap; separate native review

| Allocation | USD cap | Recorded-attempt limit |
| --- | ---: | ---: |
| Buddha development | $40 | 4,096 |
| Buddha final assessment | $85 | 10,240 |
| Both plain references, shared | $25 | 2,048 |
| Unused validation phase | $0 | 0 |
| **Total proposal** | **$150** | **16,384** |

The two plain modes share one $25 allowance. Smaller historical cost examples
were conditional usage illustrations. Neither these figures nor the user's
acceptance of the review tracks creates a grant or reopens a closed allowance.
Partial results retain their stage, reason, known costs, holds and missing work.

The native review proposal now has two components:

| Review procedure | Fresh contexts, maximum | Judgments, maximum |
| --- | ---: | ---: |
| Two staged target-repair review streams over sixteen opportunities | 32 | 64 Stage A/B judgments |
| One whole-set model-review procedure, one context per sampled set | 12 | 12 whole-set judgments |
| **Combined proposal** | **44** | **64 staged + 12 whole-set judgments** |

This adds twelve contexts to the earlier target-only proposal. It is not forty-
four independent raters or a physical request limit. `gpt-6.1-sol` with `ultra`
reasoning remains proposed, not selected. Native review consumes unpriced
Codex-plan usage outside the $150 API cap, with no reviewer API fallback. No
scientific reviewer has been launched by this preparation.

The whole-set procedure preserves every per-set reply and its provenance when
assembling the existing full-pack submission. Submit a complete valid form only
when its required ratings exist. Otherwise retain the partial raw evidence and
explicit missing coverage; never fill missing judgments to satisfy a schema.
The existing collectors validate supplied forms; they do not obtain reviews.

## Nonblocking human evidence

AI-only and later human review rounds reference the identical frozen plan,
report and answer packet. Freeze each round's roster before distributing it.
Keep any earlier incomplete mixed round and its missing reviewers in the record.
Human reports and later augmented reports are separate publications; preserve
the earlier AI report and official computational results.

The first human must disclose being the project owner and record actual prior
exposure and material access, including any AI findings already seen. Hiding
condition labels does not erase that exposure or establish an unaffiliated
review. AI-only publication need not wait to keep a future reviewer outcome-
naive. Human conclusions must state the resulting limitations. Additional
reviewers can contribute through separately identified records later.

The original twelve-set human sample covers Buddha conditions. It does not
establish human preference against the plain references. Human agreement,
validation and preference require actual human ratings. Neither evidence track
automatically establishes improvement or generalization.

## Official instrument and request checks

NoveltyBench 1.1 remains pinned to
[64a23be6](https://github.com/novelty-bench/novelty-bench/commit/64a23be6b18ec1dacc298830aab276061b6e143c).
The October 26 preparation rechecked upstream `main` and ten existing request-
contract methods, all passing with temporary fixtures and mocked HTTPS.

| Role | Prepared request settings |
| --- | --- |
| Generator backbone | Configurable model; this study selects `gpt-5.6-luna`, low effort, 4,096 wire output tokens corresponding to the official CLI allowance of 2,048; no temperature/top-p override. |
| Distinctiveness partition judge | `gpt-5.6-luna`; official structured partition request, with no explicit reasoning-effort or output-token override. |
| Utility judge | `claude-opus-5`; 16,000 output tokens, adaptive thinking, high effort and the official structured score. |
| Utility fallback | `claude-sonnet-5`; the same settings, changing only the model. |

The source-bound profiles enforce those distinctions. The judge's financial
reservation ceiling is not an output-token field injected into its request.
Generation and proposal profiles are separate from native reviewer selection.
Actual evolved Python retains its actual generation procedure: first-request
observations do not certify a whole transcript's sampling behavior. See
[the request audit](REQUEST-SETTINGS.md) and the exact
[refresh receipts](conformance/unified-live-configuration-delivery.json).

The public-price refresh retains conservative per-million-token reservation
rates: Luna $0.55 input / $1.98 output; Sol $5.50 / $16.50; Opus $11 / $27.50;
Sonnet $4.40 / $11. These include the documented applicable cache, long-context
and regional multipliers, rather than assuming the cheapest base rate. Sources:
[OpenAI pricing](https://developers.openai.com/api/docs/pricing),
[prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching),
[Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), and
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing).

Twelve pure request-scope probes also pass: official Opus/Sonnet bodies are
allowed; fast-mode fields/headers, unsupported tier overrides and unreviewed
models/tools are refused before dispatch. These are public-price and request-
scope checks, not account access, invoice validation, fit certification or a
forecast that the entire study will finish within its cap.

## Current files and verification limits

Four fresh ignored folders preserve all 166 files of the preceding preparation:

| Folder under `runs/` | Files |
| --- | ---: |
| `imp01-unified-primary-20261026-v2` | 111 |
| `imp01-unified-review-20261026-v2` | 15 |
| `imp01-unified-plain-20261026-v2` | 46 |
| `imp01-unified-comparison-20261026-v2` | 10 |
| **Base preparation** | **182** |
| `imp01-unified-review-tracks-20261026-v2` | 4 |
| **Active composite proposal** | **186** |

Use the last folder's primary handoff and reference-input bindings with the
base definitions. Its four-file extension binds DESIGN, the review-track guide
and decision to the original controls. It leaves the earlier base resource
document's target-only review proposal intact as history; the current composite
proposal adds the twelve whole-set contexts described above. The superseded
four-file review-track v1 extension and its exact policy-source copies are also
preserved. An old extension is not revalidated against newer policy bytes.

The existing primary validators pass with 171 reviewed bindings, including
intrinsic inputs, and 174 projected bindings with three future launch paths.
The primary handoff's explicit source/control map has 97 entries; it is only a
subset of that full census. Both original development/final capacity projections
pass. The raw reference inputs have 87 static controls including their binding
file; actual owners must additionally bind the future outer launch and raw key
review. This is not an already created raw-owner contract.

The current-source numerical analysis was run once on the existing 312
explicitly synthetic rows/slot evidence. All result fields match the preceding
proof except the declared plan, population and analyzer-source identities.
This checks numerical compatibility; it is not benchmark judging or performance
evidence. Independent metadata and byte checks also preserve 318 tracked Python
files, 451 historical files by raw hash only, the older preparation and all new
control pins. Reviewers inspected neither selected P/C source semantics nor
private prompt contents, and emitted no private prompt text. Trusted validators
parsed task data for the declared metadata and equality checks.

The earlier four-container/forty-mocked-request proof and the subsequent
[18 minute 28 second controller rehearsal](UNIFIED-LAUNCH-REHEARSAL.md) retain
their distinct scopes. The latter uses supplied workers and mocked HTTPS, not
fresh actual containers or providers. Neither predicts full-grid duration.

Remaining handoff work is exact executing-source hosted verification,
prospective protocol/model/allocation decisions, account confirmation and actual
approval/grant/primary-launch/outer-launch/raw-key-review bindings. Those future
records are absent. Static preparation has read no real keys and created no
actual trial, grant, owner, paid call or scientific review.
