# NoveltyBench evidence and implementation contract

**Normative reference:** the latest official code/protocol, currently v1.1 at the pinned commit below. The paper and v1.0 discussion are historical context, not implementation requirements. [Slice 2 notes](SLICE2-BENCHMARK-NOTES.md) describe the implemented v1.1 adapter and explicit execution controls.

Research checked 2026-10-18. These findings come from official papers, repositories, datasets, and saved evaluation artifacts. **No live model generations or judge scores were reproduced, and no paid calls were made.** Local calculations inspected published records; they do not independently validate the judgments.

## Frozen sources

- NoveltyBench code: [`64a23be6b18ec1dacc298830aab276061b6e143c`](https://github.com/novelty-bench/novelty-bench/tree/64a23be6b18ec1dacc298830aab276061b6e143c), committed 2026-09-10; MIT [license](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/LICENSE).
- Website code: [`e51642df57cdf0a2c0f507f668761d3478c3d404`](https://github.com/novelty-bench/novelty-bench.github.io/tree/e51642df57cdf0a2c0f507f668761d3478c3d404).
- Official dataset/results revision: [`8d78adfc3896716724c6d8a8ad202bc77b8e3dff`](https://huggingface.co/datasets/yimingzhang/novelty-bench/tree/8d78adfc3896716724c6d8a8ad202bc77b8e3dff).
- Requested [paper v4](https://arxiv.org/html/2504.05228v4), dated 2025-08-09, describes the original metric, subsequently called v1.0. Current upstream defaults to v1.1. They are different instruments.

## What the benchmark measures

The paper introduces 100 curated prompts and 1,000 filtered WildChat prompts. It measures functional difference: whether another answer adds value beyond a previous answer. This is within-prompt response diversity, not a test of historical originality or scientific discovery. Original evaluation independently sampled ten answers at temperature 1; in-context regeneration is a separately studied protocol. The original pair classifier was trained on 1,000 annotated pairs and evaluated on 100 pairs, reporting 79% accuracy and F1 0.811. [Paper, sections 3–4](https://arxiv.org/html/2504.05228v4#S3).

For ordered responses with class labels `c_i`, quality scores `u_i`, patience `p`, and `k=10`:

\[
D_k=|\{c_1,\ldots,c_k\}|,\qquad
U_k=\frac{\sum_{i=1}^{k}p^{i-1}\,u_i\,\mathbf1[c_i\notin\{c_1,\ldots,c_{i-1}\}]}{\sum_{i=1}^{k}p^{i-1}}.
\]

Use `p=0.8`. Only the **first** occurrence of a class receives quality credit; a later, better duplicate still receives zero. The denominator includes all positions. Thus ordering changes utility. At `p=0`, only the first answer matters; at `p=1`, use the uniform-weight limit. [Executable metric](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/score.py#L98-L177).

The released `train.jsonl` and `val.jsonl` train/validate the **equivalence classifier**; they are not generator-development and final-test splits. Local inspection found 94/6 curated prompt IDs and 906/94 WildChat prompt IDs in those respective files. Keep agent-search development, promotion, and sealed evaluation populations separately declared. [Data inventory](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/data/readme.txt).

## Current evaluation path and discrepancies

1. **v1.0:** deterministic greedy comparison against each class's first response, not random representatives; each response is truncated to 128 tokens and the classifier ignores the supplied prompt argument. Similarity threshold is `0.102`. Original reward scoring uses Skywork-Reward-Gemma-2-27B-v0.2 and fixed thresholds mapping rewards to integers 1–10. [Partition code](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/partition.py#L75-L182), [reward code](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/score.py#L21-L77).
2. **Published v1.1 records:** one `gpt-5.6-luna` set-level partition call sees all ten responses; `claude-opus-5`, high effort, scores each class head independently. However, the CLI imports `DEFAULT_JUDGE=claude-opus-5` for **both stages**. Pin the partition judge explicitly. Also, `score.py`'s opening docstring claims all generations are scored; executable `score_calls()` scores heads only. [Defaults](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/common.py#L5-L8), [partition CLI](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/partition.py#L287-L304), [head calls](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/score.py#L98-L122).
3. Generation refusals/empty visible answers have distinct placeholders; they remain answers to evaluate. A **judge refusal** is an instrument failure: published records and the shared stage handler use `utility=null`, excluding the entire prompt from both summary means. The live scoring CLI instead calls `score_llm()` directly; an exhausted refusal propagates as a failed instance rather than reaching that handler. Do not silently score either state zero or omit it from research accounting. [Refusal fields/live call](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/score.py#L130-L152), [summary](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/summarize.py#L11-L23).
4. Upstream can repair malformed partitions by making omitted responses singleton classes. This can increase distinctness. Preserve repair status; require valid complete partitions for promotion. [Repair behavior](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/partition.py#L207-L226).
5. Current submission protocol specifies ten answers, 2,048 output tokens, and low reasoning effort. Executable inference still defaults to 512 tokens unless explicitly overridden. [Submission protocol](https://novelty-bench.github.io/submit.html), [CLI](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/src/inference.py#L566-L583).

## Novamine: reported result and evidence limits

The official board records a community inference-time scaffold using `claude-opus-5`, with v1.1 headline **9.30 distinct / 6.65 utility**. Raw-model, inference-time, and training-time categories reflect different computational budgets. [Official board](https://novelty-bench.github.io/), [pinned metadata](https://github.com/novelty-bench/novelty-bench.github.io/blob/e51642df57cdf0a2c0f507f668761d3478c3d404/eval/08-19-2026/curated/novamine/novamine-ai/metadata.json).

Published subsets are:

| Subset | Distinct | Utility | Scored prompts |
|---|---:|---:|---:|
| Curated | 9.9 | 7.791406025135341 | 100/100 |
| WildChat | 9.243243243243244 | 6.537160463257586 | 999/1000 |

[Curated summary](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/evaluation/2026-08-19_novamine-ai/nb-curated/v1.1/summary.json), [WildChat summary](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/evaluation/2026-08-19_novamine-ai/nb-wildchat/v1.1/summary.json).

The website combines each metric as `(100*curated + 1000*wildchat)/1100`, rounded to two decimals, even when `n_scored` differs. Preserve this leaderboard calculation separately from an observation-count-weighted scientific estimate. [Aggregator](https://github.com/novelty-bench/novelty-bench.github.io/blob/e51642df57cdf0a2c0f507f668761d3478c3d404/generate_leaderboard_data.py#L281-L300).

Published partition configs name `gpt-5.6-luna`, seed `null`; score configs name `claude-opus-5`, effort `high`, patience `0.8`. The raw Novamine generations have no generation configuration, and the metadata supplies no paper or executable method. Reproduction of its generator is unresolved.

**Concrete measurement concern:** official full generations for `curated-47` and `curated-48` repeatedly select the same two half-glass alternatives with different essays; published partitions assign ten distinct classes to each. For `curated-97`, the prompt requests exactly one digit, but all ten answers add essays and receive scores between 3 and 8. These observed artifacts show a gap between strict answer/content constraints and the judges' interpretation. This does not establish misconduct; it prevents treating leaderboard leadership as proof of general creativity or strict instruction compliance. [Frozen full generations](https://huggingface.co/datasets/yimingzhang/novelty-bench/blob/8d78adfc3896716724c6d8a8ad202bc77b8e3dff/results/2026-08-19_novamine-ai/nb-curated/generations.jsonl), [scores](https://github.com/novelty-bench/novelty-bench/blob/64a23be6b18ec1dacc298830aab276061b6e143c/evaluation/2026-08-19_novamine-ai/nb-curated/v1.1/scores.jsonl).

## Design implications and successors

Optimize a frozen external evaluator, while independently checking literal constraints, factual validity, judge-order sensitivity, cost, and unseen prompts. Keep mutation proposals away from sealed prompts and evaluator code. Report a Pareto frontier and quality floor; lexical difference alone is insufficient. Compare against direct sampling and in-context regeneration under equal base models and declared call/token budgets. A full v1.1 pass requires 1,100 partition calls plus 1,100–11,000 head-quality calls before retries; Novamine's published partitions imply 11,334 judge calls total. This is a call-count calculation, not a dollar estimate.

Applicable later work includes [DARLING](https://arxiv.org/html/2509.02534v1), which couples semantic diversity with quality during online RL ([MIT implementation](https://github.com/facebookresearch/darling)); [CrPO](https://arxiv.org/abs/2505.14442), which integrates creativity dimensions into preference optimization; [Verbalized Sampling v4](https://arxiv.org/abs/2510.01171v4), a training-free candidate generator ([Apache-2.0 implementation](https://github.com/CHATS-lab/verbalized-sampling)); and [Recoding-Decoding](https://arxiv.org/html/2603.19519v1), a sentence-level exploration method. These are candidate mechanisms/baselines, not evidence this project improves or beats Novamine. Avoid importing a full training framework for an API-only first implementation.

The NoveltyBench repository is MIT; its HF card has no explicit license metadata. The upstream [WildChat card](https://huggingface.co/datasets/allenai/WildChat-1M) labels that database `odc-by`. Record dataset provenance separately from code licensing.

## Byte-level provenance

SHA-256 below hashes canonical Git blob bytes, avoiding Windows CRLF conversion. Prompt hashes use the evaluated Python string encoded as UTF-8.

| Object | SHA-256 |
|---|---|
| `data/curated.jsonl` | `ca9b6f470e5d7f7e34a281e2fdaa6f6e51c38bdae075ea580d184139ec391fa7` |
| `data/wildchat-1k.jsonl` | `8534288089508df3f413c1151a58d5fa5bda9d8f8385ae2815384d4e310a54ca` |
| `JUDGE_SYSTEM`, 505 UTF-8 bytes | `5df0b3a31c86ea37e15b17348a34ad064790b670be345dd93fcd0a4d18385eca` |
| `SCORE_SYSTEM`, 531 UTF-8 bytes | `c733873476ded31b4d24fc60241129ce345544795663d2ed3940f4ca2441a24d` |
