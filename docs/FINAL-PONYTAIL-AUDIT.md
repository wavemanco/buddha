# Final Ponytail source audit and narrow cleanup

What this repo does: Buddha generates answers, scores them using the pinned
official NoveltyBench evaluator, and gives complete development feedback to
an improver that changes agent Python. It then compares frozen descendants
with their starters and plain models. The assumed load is one operator running
the declared three-development-task, sixteen-opportunity, 26-final-task study
with two plain controls.

The read-only audit used clean source `f8e675224b40772e449cacc4dcc3e37081dcad1f`.
Three independent agents covered science/evolution, financial/runtime integrity,
and code/tests/CI/dependencies. They challenged each other's deletion candidates.
The source author separately reviewed launch/observation boundaries; those reads
are supplementary, not another independent audit. All 861 tracked source hashes
still matched after the audit. Detailed reports and the snapshot are retained in
`runs/checks/final-ponytail-audit-20261105-v1`; their hashes are in the
[delivery record](conformance/final-ponytail-audit-delivery.json).

## Should fix

1. **Retire the checker left behind by the closed policy launcher**
   (`buddha/policy_results.py`, originally lines 596–710).
   - **What this is:** `inspect_prepared_study` checked whether the old POL-02
     execution frontend could continue. It is separate from saved-results analysis.
   - **Problem:** The frontend is explicitly retired in [its guide](POLICY-LAUNCH.md),
     but this 115-line function remained. Searches of current code, tests,
     configuration, documentation and dynamic dispatch found no consumer.
   - **Fix:** Delete that function alone. Keep the module, its passive readers,
     policy controllers and preserved historical checkouts. No replacement or
     dependency is needed. This cleanup removes 117 lines including separators.
   - **If we skip it:** Reviewers must maintain an execution-only branch for a
     frontend the current checkout no longer supplies. No speedup is claimed.

No new demonstrated correctness, financial, source-isolation or numerical-scoring
defect was confirmed in the inspected paths. This does not close the known
workload-capacity gap or prove that a live comparison will finish.

## Candidates rejected by adversarial review

- Keep `unified_continuation.advance_study`. Although current internal callers use
  the descriptor entry, the [recovery guide](UNIFIED-EVIDENCE-RECOVERY.md) still
  promises the checked-token API. Absence of a symbol reference did not retire
  that public contract; the initial eleven-line deletion suggestion was withdrawn.
- Keep historical readers and validation at different custody boundaries. The
  [cold profile](RETAINED-WITNESS-PROFILE.md) collected its parent once. It does not
  justify a cache, removal of fresh checks, or a cross-stage performance patch.
- No whole module, dependency or duplicate-discovered test group was proved safe
  to delete. Similar fixtures can check different financial and scientific rules.
- Full source metadata on the host was not reported as a final-task leak: the
  worker receives the checked development projection. The generator and judges
  receive the task they are answering or assessing, as intended.
- Plain-reference results explicitly describe systems with disclosed resources;
  they do not claim an effect isolated from additional compute. Preserve that
  qualification and the prospective resource review before live calls.

## Coverage and limits

The broad map covers 861 tracked files and all 348 Python files: 83 package
modules, 213 test/helper files, 50 documentation tools, one agent and the CI
runner. All Python files were parsed as data. The import/string/dynamic-entry
map supplements deep reading; it is not a line-by-line audit of all test bodies.

Deep review traced development feedback, source inheritance, admission, freezing,
final assessment, plain comparisons and numerical analysis. A separate reviewer
fully read 24 financial, credential, executor, worker and custody modules. The
lean reviewer read CLI/operator and CI discovery/sharding/stop boundaries, package
manifests and compatibility roles. Detailed reports distinguish full reads from
focused reads and test-source samples. Broader historical controllers, all test
bodies and all review interfaces were not exhaustively read.

Host runtime is standard-library-only; evaluator environments are separate.
Historical dependency alerts and scoped evaluator/license exceptions remain
recorded obligations. Different dated alert counts are not a current advisory
clearance. This audit installs or enables nothing and does not clear unresolved
evaluator advisories. README refresh remains queued for proper stack integration,
as the user requested; PLAN owns the current candidate's status.

Post-edit independent review verifies the exact byte deletion and identical ASTs
for every surviving node. Three existing policy-reader checks pass in 2.021 test
seconds across two short invocations: malformed owner refusal, original recipe
bindings and shared owner/control/ceiling checks. Lint, format, strict types,
Bandit and compilation pass. Hosted short CI is recorded separately in the PR;
it is not full qualification. No new mirror test was added for dead-code removal.

Verdict: Remove the single retired checker; preserve active APIs and controls.
A new full workload attempt still needs prior approval. Exact-source
qualification and a funded live study follow conditionally.
Neither capacity nor a scientific improvement claim is established here.

Lean: -117 production lines, -0 dependencies; no replacement machinery.

Not checked: no model calls, keys, real containers, private/sealed tasks, original
paid history, full test qualification, new capacity attempt or restart-survival
experiment. The historical stop cause remains unknown. No speculative fix, long
run, automatic retry, funding change or main merge is authorised by this audit.
