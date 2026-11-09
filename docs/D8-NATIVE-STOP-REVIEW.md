# D8 recovery: evaluator startup failure

November 9, 2026. The comparison remains incomplete. This review records a
diagnosis, not a production fix or permission to repeat the paid command.
[PLAN D8](PLAN.md) owns the next work.

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
