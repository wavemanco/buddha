"""Real synthetic search fixtures; all preparation precedes read-only checks."""

import builtins
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_continuation as linked_fixtures
import test_history as history_fixtures
import test_search as search_fixtures

from buddha.common import _canonical
from buddha.provider import ProviderUncertain
from buddha.search import SearchSpec, run_search


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def setup_fixture(test, fixture_class):
    # Azure Windows TEMP can use an 8.3 alias. Bind canonical paths at creation.
    constructor = tempfile.TemporaryDirectory

    def canonical(*args, **kwargs):
        temporary = constructor(*args, **kwargs)
        temporary.name = str(Path(temporary.name).resolve())
        return temporary

    fixture = fixture_class("runTest")
    with patch("tempfile.TemporaryDirectory", side_effect=canonical):
        fixture.setUp()
    test.addCleanup(fixture.doCleanups)
    return fixture


class InterruptedTransport(search_fixtures.PolicyTransport):
    def send(self, call):
        if self.calls == 9:
            raise TimeoutError("synthetic tenth reply unavailable")
        return super().send(call)


def ordinary(test, *, interrupted=False, proposals=None):
    fixture = setup_fixture(test, search_fixtures.SearchTests)
    fixture.prepare(spec=SearchSpec(iterations=1, screen_size=1, seed=7))
    if interrupted:
        with test.assertRaises(ProviderUncertain):
            run_search(fixture.directory, transport=InterruptedTransport())
        fixture.report = None
    else:
        fixture.report = run_search(
            fixture.directory, transport=search_fixtures.PolicyTransport(proposals=proposals)
        )
    return fixture


def linked(test):
    fixture = setup_fixture(test, linked_fixtures.ContinuationTests)
    fixture.prepare()
    fixture.directory = fixture.out
    fixture.report = run_search(
        fixture.directory,
        transport=linked_fixtures.SyntheticTransport(),
        authorization=fixture.authority,
    )
    return fixture


def funded(test):
    source = setup_fixture(test, history_fixtures.HistoryTests)
    fixture = setup_fixture(test, search_fixtures.SearchTests)
    totals = source.ledger.totals()
    selected = replace(
        search_fixtures.settings(),
        budget_microusd=10_000_000 - totals["committed_microusd"],
        max_calls=128 - totals["operation_count"],
    )
    fixture.prepare(spec=SearchSpec(iterations=1, screen_size=1, seed=7), selected=selected)
    fixture.report = run_search(fixture.directory, transport=search_fixtures.PolicyTransport())
    manifest = record(fixture.directory / "manifest.json")
    funding = {
        "format": "buddha.recovery-funding.v1",
        "policy": "original stays inactive with reservation retained; fresh recovery evidence only",
        "source_run_id": source.manifest["run_id"],
        "source_manifest_sha256": source.manifest_hash,
        "source_ledger_sha256": sha(source.path.read_bytes()),
        "source_attempted_calls": totals["operation_count"],
        "source_known_microusd": totals["spent_microusd"],
        "source_held_microusd": totals["reserved_microusd"],
        "recovery_run_id": manifest["run_id"],
        "recovery_manifest_sha256": manifest["record_sha256"],
        "recovery_budget_microusd": selected.budget_microusd,
        "recovery_max_calls": selected.max_calls,
        "authorization_total_microusd": 10_000_000,
        "authorization_total_calls": 128,
    }
    (fixture.directory / "funding.json").write_bytes(
        _canonical(funding | {"record_sha256": sha(_canonical(funding))}) + b"\n"
    )
    fixture.extra_runs = [source.directory]
    fixture.funding_source = source
    return fixture


def evidence_for(fixture):
    directories = [fixture.directory]
    authorization = None
    if hasattr(fixture, "authority"):
        directories += [fixture.source, fixture.root / "completed-recovery"]
        authorization = {
            "path": str(fixture.authority_path),
            "sha256": sha(fixture.authority_path.read_bytes()),
        }
    directories += getattr(fixture, "extra_runs", [])
    return {
        "format": "buddha.search-verification-input.v1",
        "runs": [
            {
                "directory": str(directory),
                "files": {
                    path.relative_to(directory).as_posix(): sha(path.read_bytes())
                    for path in sorted(directory.rglob("*"))
                    if path.is_file()
                },
            }
            for directory in directories
        ],
        "authorization": authorization,
    }


def source_snapshot(evidence):
    result = {}
    for run in evidence["runs"]:
        directory = Path(run["directory"])
        result[str(directory)] = tuple(
            sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*"))
        )
        for path in directory.rglob("*"):
            if path.is_file():
                result[str(path)] = (path.read_bytes(), path.stat().st_mtime_ns)
    if evidence["authorization"] is not None:
        path = Path(evidence["authorization"]["path"])
        result[str(path)] = (path.read_bytes(), path.stat().st_mtime_ns)
    return result


def record(path):
    return json.loads(path.read_bytes())


def rewrite_record(path, edit, *, checksum="record_sha256"):
    value = record(path)
    value.pop(checksum, None)
    edit(value)
    path.write_bytes(_canonical(value | {checksum: sha(_canonical(value))}) + b"\n")


def corrupt_database(path, sql, arguments=()):
    # Reuse the central native-DDL-preserving mutation helper for synthetic data.
    history_fixtures.HistoryTests.corrupt(SimpleNamespace(path=path), sql, arguments)


@contextmanager
def readonly_boundary(*, cli=False):
    def forbidden(*args, **kwargs):
        raise AssertionError("verification crossed an execution, write or credential boundary")

    connect = sqlite3.connect
    path_open = Path.open
    builtin_open = builtins.open
    environment_get = os.environ.get

    def cli_environment(name, *args, **kwargs):
        # ArgumentParser asks only for these presentation settings. Credentials
        # and all other environment lookups remain forbidden during this check.
        if name not in {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG", "COLUMNS", "LINES"}:
            forbidden()
        return environment_get(name, *args, **kwargs)

    def read_path(path, mode="r", *args, **kwargs):
        if any(character in mode for character in "wax+"):
            forbidden()
        return path_open(path, mode, *args, **kwargs)

    def read_builtin(file, mode="r", *args, **kwargs):
        if any(character in mode for character in "wax+"):
            forbidden()
        return builtin_open(file, mode, *args, **kwargs)

    def memory_only(database, *args, **kwargs):
        if database != ":memory:":
            raise AssertionError("verification queried a source SQLite file")
        return connect(database, *args, **kwargs)

    with ExitStack() as stack:
        for target in (
            "buddha.search.load_search",
            "buddha.search.inspect_search",
            "buddha.search._walk",
            "buddha.search._ledger",
            "buddha.search._contracts",
            "buddha.continuation.load_continuation",
            "buddha.continuation.read_source",
            "buddha.continuation._current_runtime",
            "buddha.ledger.Ledger.__init__",
            "buddha.authorization.Authorization.__init__",
            "buddha.authorization.Authorization.for_run",
            "buddha.authorization.AuthorizedLedger.__init__",
            "buddha.provider.BudgetBroker.__init__",
            "buddha.provider.BudgetBroker.execute",
            "buddha.provider.HTTPTransport.__init__",
            "buddha.provider.HTTPTransport.send",
            "http.client.HTTPSConnection",
            "socket.create_connection",
            "socket.socket.connect",
            "subprocess.run",
            "subprocess.Popen",
            "zipfile.ZipFile.extract",
            "zipfile.ZipFile.extractall",
            "pathlib.Path.mkdir",
            "pathlib.Path.write_bytes",
            "pathlib.Path.write_text",
            "pathlib.Path.touch",
            "pathlib.Path.unlink",
            "pathlib.Path.rename",
            "pathlib.Path.replace",
            "os.open",
        ):
            stack.enter_context(patch(target, side_effect=forbidden))
        stack.enter_context(
            patch("os.environ.get", side_effect=cli_environment if cli else forbidden)
        )
        if cli:
            stack.enter_context(patch("buddha.__main__._key_environment", side_effect=forbidden))
            stack.enter_context(patch("getpass.getpass", side_effect=forbidden))
        stack.enter_context(patch("sqlite3.connect", side_effect=memory_only))
        stack.enter_context(patch.object(Path, "open", read_path))
        stack.enter_context(patch("builtins.open", side_effect=read_builtin))
        # Existing code is already imported; archived Python must remain inert data.
        stack.enter_context(patch("builtins.exec", side_effect=forbidden))
        yield
