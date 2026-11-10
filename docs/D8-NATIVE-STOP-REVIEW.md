# D8 recovery: evaluator startup failure

November 9, 2026. The comparison remains incomplete. This review records a
diagnosis and a bounded verified production correction. It does not authorize
repeating the historical paid command.
[PLAN D8](PLAN.md) owns the next work.

## Bounded resolution follow-up

**The production correction is implemented and its actual deep-path check passes.**
A controlled read in one container held input bytes and path length constant:
both sources were 154 characters, but the shallow ten-component path was
readable while the twenty-component path returned EIO. This establishes an
observed nesting-dependent failure, not a character/byte limit or a proven
Windows/9P implementation defect. No guessed maximum-depth rejection was added.

Both native-evaluation callers now create dedicated input leaves at
`<authorization folder>/native-inputs/<hash of absolute evaluation path and stage>`.
These are persistent, scoped derivative files, outside the frozen component
trees. Only the selected leaf is mounted read-only. Every input path/hash,
source binding, inventory, release setting and container restriction remains
checked. Historical descriptors retain exact legacy validation; they are not
rewritten. No new configuration schema, dependency, service or retry loop exists.

The passive reader also checks the selected external leaf's exact contents.
The existing capture retains its directory census, rechecks it at completion,
and carries it through capture adoption under the existing entry ceiling.
Links, unselected files, late additions, changed bytes and premature future-stage
materialization remain rejected. This watches only selected leaves, never the
whole shared input store.

The corrected-source proof completes in **34.790 seconds**: a twenty-one-component
evaluation directory produces an eleven-component input mount, then real
Gateway/NativeSession, pinned official partition, ready/final audits, published
artifacts and passive custody all pass. The worker configuration matches the
stopped worker exactly. Dummy credentials, supplied HTTPS and blocked network
access prevent provider calls. Its five synthetic microusd and zero holds are
fixture accounting, not actual spending or benchmark results. The six changed
production-file hashes match the code used for this check.

Earlier in this follow-up, the historical runtime completed the real host/native
partition in30.764 seconds and score plus summary in46.318 seconds at shallow
paths. Opus's outgoing adaptive/HIGH/16,000 settings were asserted, and summary
made no requests. Replies/ratings were supplied; these are execution checks,
not independent judgments of the saved stories or a live comparison result.

Operational attempts are retained: same-path rematerialization failed11.219s
and was rolled back to the original physical directory; a parent mount also
failed5.389s. The approved Desktop restart command exited1 after64.260s because
MCP bridges prevented clean shutdown. Service restoration reported Desktop
running; the user then restarted Docker. The original path still failed afterward.
No bridge process was force-killed or global setting changed. The directory
geometry comparison, rather than a restart assumption, supports the correction.

All42 stopped-file hashes, ten answers and eight grant attributes are preserved.
Actual replacement spending remains $0.009553 with no replacement hold; the
original authentication-rejected attempt retains its separate $0.585611 hold.
No stopped-runtime source, descriptor, budget or operation record was edited.
A newly bound checked handoff is required; the old live command is not cleared.
Retain the ten historical answers rather than adding a special migration system.
Any new generation must be explicitly described in that handoff and stay inside
the remaining approved allowance. No paid call or new long run follows automatically.

Evidence under `runs/checks/d8-native-resolution-20261109-v1` includes:

- `geometry-result.json`: equal-length shallow/deep controlled reads.
- `host-native-partition-fresh/result.json` and `host-native-following/result.json`: historical-runtime host/SDK checks.
- `corrected-native-deep/result.json`: new-source producer, actual host/evaluator and passive-custody pass, with its driver and source pins.
- `focused-staging-check.json`:16 tests in61.796s; `closure-focused-check.json`:8 tests in6.797s, one Windows symlink-capability skip.
- `entry-cap-ci-inventory-check.json`:31 entry-ceiling/test-runner checks in50.792s. Across the three bounded groups:54 successful methods and one declared Windows link-capability skip.
- Rematerialization, rollback, restart, service and original-path partial reports retain the unsuccessful observations.

[Docker's restart reference](https://docs.docker.com/reference/cli/docker/desktop/restart/)
describes its command-wait timeout; it does not certify backend recovery.
The older [vendor EIO report](https://github.com/docker/for-win/issues/7552) is
analogous background only, not a diagnosis of this host.

## What happened

The recovery saved ten generation replies, with $0.009553 recorded spending and
no replacement hold. Its first native evaluation made **zero judge requests**.
The original authentication-rejected attempt and its separate $0.585611 hold
remain unchanged. These are recorded amounts, not reconciled provider invoices.

The evaluation report says the host failed while handling a worker frame before
accepting readiness. Our worker replaces preparation exceptions with a generic
error, then replaces that with `native_error`; the host rejects completion before
readiness and records `host` / `exchange`. The original specific exception was
not retained. The historical report alone cannot identify it.

## What the short diagnosis establishes

1. Running the exact saved worker configuration, image, official evaluator,
   runner and input mount reproduces failure before readiness in 9.978 seconds.
2. Instrumenting **only an isolated diagnostic copy's exception reporting**
   recovers the chained failure: `OSError`, error number 5 (`EIO`, input/output
   error), at `lstat("/inputs")`. This is the container inspecting its input
   folder, before importing the official evaluator. Installed-runtime auditing
   had already passed. No input contents, credentials or traceback locals were
   emitted.
3. With the original unmodified worker and identical input bytes, changing only
   the input mount's host source to a fresh copy reaches readiness in 17.517
   seconds. All 5,180 import-audit entries and expected hook bindings pass.

The reproduced failure therefore concerns Docker's access to the original input
mount. It is not a provider response, NoveltyBench score or answer-size rejection.
The evidence does **not** identify why Docker/Windows returned EIO, prove path
length is responsible, or establish that automatic copying/retrying would solve
the underlying problem. The original lost exception cannot be recovered directly;
the diagnostic reproduces a concrete failure at its startup boundary.

All five diagnostic containers were removed. Each had a 120-second worker limit;
their observed worker invocations took 9.978, 5.315, 5.018, 5.093 and 17.517 seconds.
They used no Gateway, provider transport, API keys or paid requests; host sockets
were blocked, and the container executor retains network isolation. The diagnostic
stopped at its first frame, before any provider request. Twenty-two stopped-task
files were checked before/after and remained byte-exact. Production source,
grants, operation ledgers and stopped-run records were not changed. Independent
source review also matched all 215 owner input files and the selected nine
official/seven runner files to their recorded hashes.

## Why the previous checks missed this

Readable files on Windows and a validated Docker mount declaration do not prove
that Linux inside the container can read that mount. Earlier actual native-wire
checks used separate diagnostic input paths and bypassed the full
`NativeSession`/Gateway composition. Their passing results were narrower than
the readiness confidence we placed in them. More unit-test passes would not
resolve this gap.

## Next acceptance, using the existing stages

Establish that the prospective execution's actual mounts are readable, then
exercise the real host/native evaluation boundary with supplied replies and paid
access blocked. Retain input identity, official settings, audit, confinement,
accounting and cleanup checks. Use that evidence to prepare checked continuation
which can reuse eligible saved generation; do not regenerate the ten answers just
to test evaluator startup. The old staging source is not cleared by a different
diagnostic source passing.

Do not add retry loops, relax validation, change the frozen executing source or
rebuild the full capacity history on this evidence. No new paid call, long run or
live command is authorized by this review. A completed scientific comparison
remains the target; startup success alone does not establish one.

## Local evidence

Paths below are relative to `C:\Users\arvik\code\buddha`:

- Stopped native report: `runs/imp01-d8-recovery-review-20261108-v1/NOT-CREATED-trial-runtime/search/study/common/0/0/screen/tasks/0/evaluation/attempts/1-0/report.json`.
- Generation accounting: the same task's `generation/attempts/0-0/session/report.json`.
- Exact-worker reproduction: `runs/checks/d8-native-boundary-20261109-v1/result.json` and `first-worker-frame.json`.
- Diagnostic exception reports: `runs/checks/d8-native-boundary-20261109-v2/result.json`, `runs/checks/d8-native-boundary-20261109-v3/result.json`, `runs/checks/d8-native-boundary-20261109-v4/result.json`.
- Fresh-mount readiness: `runs/checks/d8-native-mount-20261109-v1/result.json` and `first-worker-frame.json`.

The executor reports `host` for these diagnostic invocations because the
diagnostic deliberately raises after capturing its first frame. For the
fresh-mount check, the saved frame is **ready**, its audit passes, and owned
cleanup is **removed**. That deliberate diagnostic stop is not a second study
failure or a claim that the full evaluation completed.
