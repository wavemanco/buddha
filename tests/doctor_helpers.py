"""Genuine run fixtures and observer guards, prepared before observation."""

import json
import os
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import test_baseline as native_fixtures
import test_diagnostics as diagnostic_fixtures
import test_gateway as gateway_fixtures
import test_history as history_fixtures
import test_run as baseline_fixtures
from search_verify_helpers import (
    linked,
    ordinary,
    readonly_boundary,
    setup_fixture,
)

from buddha.authorization import Authorization
from buddha.baseline import BaselineError
from buddha.doctor import observe
from buddha.provider import ProviderUncertain
from buddha.run import ReplayTransport, run_baseline


def legacy(test):
    fixture = setup_fixture(test, history_fixtures.HistoryTests)
    return fixture


def baseline(test):
    fixture = setup_fixture(test, baseline_fixtures.BaselineRunTests)
    fixture.prepare()
    run_baseline(fixture.destination, transport=ReplayTransport())
    fixture.directory = fixture.destination
    return fixture


def search(test, *, continuation=False):
    return linked(test) if continuation else ordinary(test)


def gateway(test):
    fixture = setup_fixture(test, gateway_fixtures.GatewayTests)
    fixture.send()
    return fixture


def native(test, *, complete=False, unanchored=False):
    fixture = setup_fixture(test, native_fixtures.BaselineTests)
    fixture.prepare()
    if complete:
        fixture.run_pipeline()
    elif unanchored:
        with (
            patch.object(
                Authorization, "deactivate", side_effect=OSError("synthetic interruption")
            ),
            test.assertRaises(BaselineError),
        ):
            fixture.run_pipeline()
    return fixture


def diagnostic(test):
    fixture = setup_fixture(test, diagnostic_fixtures.DiagnosticsTests)
    connection, _ = fixture.connection(status=500)
    with test.assertRaises(ProviderUncertain):
        fixture.execute(connection)
    return fixture


def files(directory, authorization=None):
    result = {}
    directory = Path(directory)
    if directory.exists():
        for path in [directory, *sorted(directory.rglob("*"))]:
            info = path.lstat()
            name = str(path)
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                result[name] = ("link", os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                result[name] = ("directory",)
            else:
                result[name] = (path.read_bytes(), info.st_mtime_ns)
    if authorization is not None and authorization.is_file():
        result[str(authorization)] = (authorization.read_bytes(), authorization.stat().st_mtime_ns)
    return result


@contextmanager
def protected(directory, authorization=None, *, cli=False):
    def forbidden(*args, **kwargs):
        raise AssertionError("doctor executed code or crossed an unselected input boundary")

    directory = Path(directory).resolve()
    authority = None if authorization is None else Path(authorization).resolve()
    with readonly_boundary(cli=cli), ExitStack() as stack:
        for target in (
            "buddha.gateway.Gateway.__init__",
            "buddha.gateway.execution_identity",
            "buddha.baseline.prepare_baseline",
            "buddha.baseline.run_baseline",
            "buddha.run.load_run",
            "buddha.run.run_baseline",
            "buddha.executor.run_container",
            "buddha.native_run.NativeSession.__init__",
            "buddha.agent_run.AgentSession.__init__",
        ):
            stack.enter_context(patch(target, side_effect=forbidden))
        opened = Path.open

        def selected(path, *args, **kwargs):
            resolved = path.resolve()
            if not resolved.is_relative_to(directory) and resolved != authority:
                forbidden()
            return opened(path, *args, **kwargs)

        stack.enter_context(patch.object(Path, "open", selected))
        yield


def checked(test, directory, *, authorization=None):
    before = files(directory, authorization)
    try:
        with protected(directory, authorization):
            result = observe(Path(directory), authorization=authorization)
        serialized = json.dumps(result)
        test.assertNotIn(json.dumps(str(Path(directory)))[1:-1], serialized)
        if authorization is not None:
            test.assertNotIn(json.dumps(str(authorization))[1:-1], serialized)
        return result
    finally:
        test.assertEqual(before, files(directory, authorization))
