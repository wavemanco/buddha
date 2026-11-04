# Retired one-request capacity launcher

The one-request diagnostic completed on October 23, 2026. Its
[actual result](SOURCE-CAPACITY-RESULTS.md) records a passing capacity observation
with settled accounting. The standalone launcher, entry script and their ten
tests have been retired from the active checkout because the current experiment
loop does not call them. There is no replacement frontend or new run to start.

The current pure assessor in [source_capacity.py](../buddha/source_capacity.py)
remains in use. This retirement removes a closed experiment's launcher; it does
not remove the current loop's capacity checks or change their rules.

The original pinned code copy, authorization, replies and results remain
historical evidence. Its closed one-attempt allowance does not authorize another
request. The [original operator handoff](SOURCE-CAPACITY-LIVE.md) retains its
historical command against that separate frozen copy, not this checkout.

Historical references remain available:

- [Frozen protocol](SOURCE-CAPACITY-PROTOCOL.md)
- [Exact-body offline rehearsal](SOURCE-CAPACITY-REHEARSAL.md)
- [Original delivery evidence](conformance/src02-capacity-driver-delivery.json)
- [Launcher source before retirement](https://github.com/wavemanco/buddha/blob/4fd16b9f8feba1e8b195cf276775ea261a02a833/buddha/capacity_launch.py)
- [Entry script before retirement](https://github.com/wavemanco/buddha/blob/4fd16b9f8feba1e8b195cf276775ea261a02a833/docs/conformance/src02-capacity-run.py)
- [Launcher tests before retirement](https://github.com/wavemanco/buddha/blob/4fd16b9f8feba1e8b195cf276775ea261a02a833/tests/test_capacity_launch.py)
- [Original driver guide](https://github.com/wavemanco/buddha/blob/4fd16b9f8feba1e8b195cf276775ea261a02a833/docs/SOURCE-CAPACITY-DRIVER.md)

[PLAN.md](PLAN.md) owns the current work and future execution approvals. This
historical capacity result does not establish improved NoveltyBench scores or
current-run readiness.
