# Slice 2 benchmark fidelity and limits

The October 20 [direct conformance audit](NOVELTYBENCH-CONFORMANCE.md) supersedes broad fidelity interpretations of this historical note. It confirms successful metric/request construction within the declared profile, records additional parser differences, and leaves full native execution alignment open as BENCH-02.

The normative reference is NoveltyBench code commit
[`64a23be6b18ec1dacc298830aab276061b6e143c`](https://github.com/novelty-bench/novelty-bench/tree/64a23be6b18ec1dacc298830aab276061b6e143c),
metric v1.1. The paper describes historical evaluation and is not the current
request contract.

An independent offline comparison extracted upstream functions using Python's
AST, without importing its model-serving dependencies. Both generation request
bodies matched: independent same-prompt sampling, low reasoning effort, and a
4,096-token combined reasoning/output allowance corresponding to upstream's
explicit 2,048-token setting (not the bare inference CLI default). The Partition and Score JSON schemas matched upstream's
Pydantic schemas, and the Anthropic high-effort quality request matched.

Subsequent deliberate controls differ from upstream requests: OpenAI partition
judging has a 16,000-token output cap; requests explicitly select OpenAI's
`default` and Anthropic's `standard_only` service tiers for billing control.
Generation configuration records these controls. Retries, fallback judges, and
lenient partition repairs are disabled. This is a bounded implementation of the
v1.1 instrument; native upstream execution and identical stochastic results are
not claimed. The comparison above preceded the service-tier additions.

Upstream `regenerate` means independent calls without response history.
`in-context` is a separate protocol. Successful quality judgments score the first
response in each equivalence class; duplicate positions retain null scores.

A temporary, synthetic three-answer export was accepted by upstream's
`load_instances()`. Its `utility_fields()` and `summarize()` functions recomputed
distinctness 2 and utility approximately 5.40983606557377, differing only in final
floating-point rounding. This verifies file/arithmetic compatibility, not live
judgments, an official ten-answer result, or benchmark performance.

**Upstream rejudging can spend money.** Exports omit upstream's `generation_key`,
`partition_key`, and `score_key` cache fields. Its partition/score workflow sees
uncached rows and makes new judge calls. Rejudge a copy: upstream rewrites files
and drops extra identity fields during partition loading, invalidating Buddha's
immutable provenance hashes. Explicitly select `gpt-5.6-luna` for partitioning;
upstream's shared CLI default differs from its published v1.1 records. Merely
recomputing a summary from stored scores does not require model calls.

Failure behavior also differs. Upstream maps an Anthropic HTTP 400 containing
content-filtering text to a generation-refusal placeholder. The local transport
retains an uncertain paid operation and leaves evaluation incomplete when it
cannot reconcile usage. Judge refusal or malformed output likewise prevents a
complete local result; it is not silently excluded to improve a mean.

The importer requires origin `buddha-local`, full protocol equality, exact file
hashes, consistent ordered evidence, and complete expected coverage. These checks
establish local integrity and consistency. A self-hashed manifest is not a
signature, independent source authentication, or official benchmark certification.
Replay configurations identify their provider as `replay`; their canned outputs
and scores are synthetic demonstrations.
