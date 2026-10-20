"""Real temporary shared authorization for paid-boundary integration fixtures."""

import hashlib

from buddha.authorization import Authorization, runtime_fingerprint
from buddha.benchmark import _canonical
from buddha.ledger import Ledger


def authorized_run(directory, *, budget_microusd=1000, max_calls=3):
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format": "buddha.policy-search.v1",
        "run_id": directory.name,
        "settings": {"budget_microusd": budget_microusd, "max_calls": max_calls},
    }
    manifest_sha256 = hashlib.sha256(_canonical(manifest)).hexdigest()
    (directory / "manifest.json").write_bytes(
        _canonical(manifest | {"record_sha256": manifest_sha256}) + b"\n"
    )
    Ledger(
        directory / "operations.sqlite3",
        run_id=directory.name,
        manifest_sha256=manifest_sha256,
        budget_microusd=budget_microusd,
        max_calls=max_calls,
    )
    authority = Authorization.create(
        directory.parent / (directory.name + "-authorization.sqlite3"),
        authorization_id=directory.name + "-authorization",
        budget_microusd=budget_microusd,
        max_calls=max_calls,
        scope="mocked paid-boundary integration scope",
    )
    authority.bind_run(directory, runtime_sha256=runtime_fingerprint())
    return authority, authority.for_run(directory)
