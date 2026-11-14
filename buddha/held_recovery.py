"""Replay policy for a reviewed NoveltyBench utility request with a retained hold."""

from buddha import noveltybench_results
from buddha.answers import TaskSet, _id
from buddha.gateway import Gateway, GatewayCall, HeldReplacementReplay
from buddha.ledger import OperationConflict
from buddha.releases import Release, _json, _load, _object
from buddha.wire import RawEnvelope, decoded_body


def fallback_model(
    release: Release, stages: list[dict[str, object]], tasks: TaskSet, partition: bytes
) -> str | None:
    """Require the single partition head that makes replay order unambiguous."""
    rows = noveltybench_results._rows(partition)
    if len(rows) == len(tasks.tasks) == 1:
        (task,) = tasks.tasks
        schema = _object(release.to_record()["task"])
        identifier = _id(rows[0][str(schema["id_field"])])
        heads = noveltybench_results._heads(rows[0]["partition"], task.count)
        if type(identifier) is type(task.id) and identifier == task.id and len(heads) == 1:
            config = noveltybench_results.reporting_configuration(release, stages)
            if config["stage_roles"] == ["grouping", "quality", "summary"]:
                model = config["fallback_model"]
                return model if isinstance(model, str) else None
    raise OperationConflict("held utility replay requires one checked partition head")


class UtilityReplay:
    """Deliver the two reviewed replies in order, then permit the frozen refusal fallback."""

    def __init__(
        self, gateway: Gateway, replay: HeldReplacementReplay, fallback: str | None
    ) -> None:
        self.gateway = gateway
        self.decision = replay.decision
        self.pair = (
            (replay.original, replay.original_envelope),
            (replay.replacement, replay.replacement_envelope),
        )
        self.fallback = fallback
        self.consumed = 0
        self.fallback_delivered = False

    def _requires_fallback(self) -> bool:
        replacement, response = self.pair[1]
        return (
            self.fallback is not None
            and self.fallback != _load(replacement.body)["model"]
            and response.status == 200
            and _load(decoded_body(response)).get("stop_reason") == "refusal"
        )

    @property
    def complete(self) -> bool:
        return self.consumed == len(self.pair) and (
            self.fallback_delivered or not self._requires_fallback()
        )

    def reply(self, call: GatewayCall) -> RawEnvelope:
        if self.consumed < len(self.pair):
            expected, envelope = self.pair[self.consumed]
            if call != expected:
                raise OperationConflict(
                    "worker recovery callback differs from the reviewed attempt"
                )
            self.consumed += 1
            return envelope

        replacement, _ = self.pair[1]
        body = _load(replacement.body)
        if (
            not self._requires_fallback()
            or call.capability != replacement.capability
            or call.logical_id == replacement.logical_id
            or call.attempt != 0
            or dict(call.headers).get("x-stainless-retry-count") != "0"
            or _json(_load(call.body)) != _json(body | {"model": self.fallback})
        ):
            raise OperationConflict("worker recovery callback is not the frozen refusal fallback")

        # The owner lease serializes requests. The original and replacement already own two rows.
        ledger = self.gateway.ledger
        if (
            ledger.get(self.gateway.operation_id(call)) is None
            and ledger.totals()["operation_count"] != 2
        ):
            raise OperationConflict("utility owner already has a refusal fallback")
        envelope = self.gateway.execute(call)
        self.fallback_delivered = True
        return envelope
