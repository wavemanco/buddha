# CI repairs and PR readiness — October 23, 2026

The fixes now sit on the PR branches that introduced the failures. Later PRs
inherit them through ordinary base merges. No PR was merged and no published
commit was removed or force-pushed. Fresh Windows and Ubuntu checks are running;
their exact heads and job links are saved in the
[delivery record](conformance/ci-stack-repair-delivery.json).

## What failed and what changed

| PRs / original observation | Finding | Correction |
| --- | --- | --- |
| #73 and #74: repeated worker-version assertions | The test fixture expected the older prefix-feedback worker after receiving a full-output packet. Another fixture implicitly expected a historical prefix packet from a builder that now deliberately supplies complete answers. | Put the two test corrections into #73. Check the exact version selected by the validated packet, with both versions covered; explicitly reconstruct historical packets for historical inspection. Production full-output behavior stays intact. |
| #78–#80 Windows: 41 path errors across seven test modules | The new strict trial probe ran before the existing legacy path validator/canonicalizer. Windows runner temporary paths can use a short spelling such as `RUNNER~1`, while the resolved path uses the long spelling. | In #78, move the existing canonicalization line before the trial probe. Keep the initial trial-history refusal, link/reparse checks and strict trial rules. Actual temporary-history imports and poisoned-marker controls exercise the boundary. |
| #78–#80 Ubuntu: portable-core assertion; Windows also had stale path expectations | Independent test expectations omitted the newly installed `trial_fence` module or compared a stored resolved path with an unresolved input spelling. | Include the missing literal core member and resolved-path expectation in #78. Exact equality and prohibited scientific-import checks remain. |
| #71 Windows linked-CLI failure; a separate #74 Windows unknown-resume error | The original logs hid the underlying exceptions. The affected methods pass locally; the original hosted causes remain unidentified. | In #71, retain the original test exception and suppressed exception context if these synthetic recovery paths fail again. A deliberate nested-error/cycle control checks the diagnostic helper. Public CLI redaction, accounting and no-resend assertions remain. This is diagnostic work, not a claimed production fix. |

The earlier #75 and #81 compatibility fixes were valid but placed too late in
the stack to make the originating PRs green. After backporting, #74, #75 and #81
retain documentation and historical evidence only. Their titles and descriptions
now reflect those actual diffs. Historical delivery records keep their original
source cuts and observations.

## What has been checked

The path regression fails before the production correction and passes after it.
Its passing cohort contains 19 methods: two new path-compatibility methods, all
14 original trial-fence methods and three affected history-import methods.
These use synthetic temporary accounting data, with zero model calls or workers.
The strict trial guard implementation itself is unchanged.

The two affected recovery methods and one unique diagnostic control pass at
separately pinned cuts. The control was subsequently tightened to retain a real
exception-context cycle and checked again; this is three unique methods, not
four. No original Windows failure was reproduced. If fresh CI passes without
reproducing either event, that will establish success at the new head, not an
explanation of the older event.

All seven quality commands pass on the updated final stack tip `ac0f204`:
lint, formatting, strict Windows and Linux type checks, code security,
runtime-dependency audit and compilation. All 245 source/configuration inputs
stay unchanged during that run. These checks do not include the unit suite.
The focused method cohorts above retain their own source cuts; they are not
presented as one local full-suite run at every updated PR head.

The initial static-tool attempt could not import tools because isolated Python
excluded the installed user-site tools. It analyzed no application code. The
retained second attempt uses the installed tools with a sanitized environment
and passes. The receipt distinguishes that setup failure from a code failure.

At the saved **13:54:39 UTC** snapshot, fresh hosted jobs for PRs #71–#82 are
in progress. The delivery records every exact head and live job link. Pending
jobs are not green checks. Several heads have more than one pull-request run
after the head/base updates; all observed job IDs are retained. This repair does
not change the workflow, remove tests or retry a timed-out observation as a new
run.

## Why the PRs were drafts

The earlier blanket draft choice treated unfinished project milestones as if
every completed slice were unfinished. That obscured which work was ready for
review. Fourteen completed PRs—#61–#70, #72 and #75–#77—were marked ready after
checking both hosted jobs on each then-current head. Some of those heads have
since inherited base updates and therefore need fresh checks again.

Use draft status for unfinished implementation. A completed slice can be ready
for review while its parent PR, a live experiment or a broader research claim
remains pending. Green checks are recorded against an exact commit. Ready for
review does not authorize merging; dependent PRs remain stacked for review.
The remaining eight completed PRs—#71, #73, #74 and #78–#82—were marked ready on
October 23 after verifying their unchanged repaired heads. All their Ubuntu
jobs have passed; Windows remains in progress at the latest retained snapshot.
Ready status does not assert those pending jobs have passed. No PR was merged.

## Effect on experiments and the roadmap

No official NoveltyBench evaluator, score, model setting or experiment result
changes. No API key, paid call, original paid owner, financial limit or new
allocation is involved. Earlier failed owners and actual runtime proofs retain
their original identities and source cuts.

The [living plan](PLAN.md) still has the same six open leaf slices, with SRC-02
as the sole next slice. Concrete model-context and replacement-code output
headroom, broader mutation competence, finalization and scientific improvement
remain open. CI repair neither closes those gates nor requires a user run.
