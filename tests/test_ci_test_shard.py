"""Full-census CI partitioning with ordinary unittest fixtures and tiny suites."""

import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


def case(name, events):
    class Probe(unittest.TestCase):
        def id(self):
            return name

        def runTest(self):
            events.append(name)

    return Probe()


class CiTestShardTests(unittest.TestCase):
    IDLE_SECONDS = 5.0
    STARTUP_DELAY = 1.0

    def setUp(self):
        self.api = importlib.import_module("ci_test_shard")

    def test_nested_collection_keeps_order_duplicates_and_refuses_custom_suites(self):
        events = []
        cases = [case("duplicate", events), case("other", events), case("duplicate", events)]
        suite = unittest.TestSuite([cases[0], unittest.TestSuite(cases[1:])])
        self.assertEqual(self.api._collect(suite), cases)
        self.assertEqual(events, [])

        class CustomSuite(unittest.TestSuite):
            pass

        for unsupported in (CustomSuite(cases), object()):
            with self.assertRaises(ValueError):
                self.api._collect(unsupported)

    def test_partition_is_exhaustive_ordered_and_isolates_only_the_named_occurrence(self):
        cases = [case("probe." + str(index), []) for index in range(40)]
        cases.append(case(cases[1].id(), []))
        self.assertEqual(self.api._partition(cases, 1, None), [list(range(41))])
        for count in (4, 5):
            with self.subTest(count=count):
                groups = self.api._partition(cases, count, cases[0].id())
                self.assertEqual(groups[0], [0])
                self.assertEqual(
                    sorted(index for group in groups for index in group), list(range(41))
                )
                self.assertTrue(all(group == sorted(group) and group for group in groups))
                self.assertTrue(any(1 in group and 40 in group for group in groups))
                self.assertEqual(groups, self.api._partition(cases, count, cases[0].id()))
        for isolate in ("missing", cases[1].id()):
            with self.assertRaises(ValueError):
                self.api._partition(cases, 4, isolate)

    def test_invalid_configuration_empty_shards_and_ambiguous_isolation_refuse(self):
        cases = [case("duplicate", []), case("duplicate", [])]
        for count, isolate in (
            (0, None),
            (True, None),
            (1.0, None),
            (2, None),
            (1, "duplicate"),
            (4, "missing"),
            (4, "duplicate"),
        ):
            with self.subTest(count=count, isolate=isolate), self.assertRaises(ValueError):
                self.api._partition(cases, count, isolate)
        with self.assertRaises(ValueError):
            self.api._partition([], 1, None)

    def command(self, root, *args, seed="1", timeout=12):
        allowed = (
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "TEMP",
            "TMP",
            "COMSPEC",
            "PATHEXT",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
            "PROGRAMFILES",
            "PROGRAMDATA",
        )
        env = {name: os.environ[name] for name in allowed if name in os.environ}
        env.update(PYTHONHASHSEED=seed, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, str(Path(self.api.__file__).resolve()), *args],
            cwd=root,
            env=env,
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=timeout,
        )

    def watchdog_command(self, root):
        # Startup/discovery shares the real idle window; leave CI scheduling room.
        return self.command(
            root,
            "--count",
            "1",
            "--index",
            "0",
            "--idle-seconds",
            str(self.IDLE_SECONDS),
            timeout=30,
        )

    def fixture(self, root, *, body="pass", setup="pass"):
        tests = root / "tests"
        tests.mkdir()
        (tests / "test_probe.py").write_text(
            "import unittest\nfrom pathlib import Path\n"
            "def setUpModule(): Path('module-setup').write_text('M')\n"
            "def tearDownModule(): Path('module-cleanup').write_text('Z')\n"
            "def record(name):\n"
            "    Path('body').write_text('executed')\n"
            "    Path('occurrence-' + name).write_text('executed')\n"
            "    order = Path('order')\n"
            "    order.write_text((order.read_text() if order.exists() else '') + name + '\\n')\n"
            "class Probe(unittest.TestCase):\n"
            "    @classmethod\n    def setUpClass(cls):\n"
            "        p = Path('setup')\n"
            "        p.write_text((p.read_text() if p.exists() else '') + 'S')\n"
            "    @classmethod\n    def tearDownClass(cls):\n"
            "        p = Path('cleanup')\n"
            "        p.write_text((p.read_text() if p.exists() else '') + 'C')\n"
            + "".join(
                f"    def test_{index:03}(self):\n"
                f"        record('test_probe.Probe.test_{index:03}')\n"
                "        " + (body if index == 0 else "pass").replace("\n", "\n        ") + "\n"
                for index in range(32)
            )
            + "class SkippedFixture(unittest.TestCase):\n"
            "    @classmethod\n    def setUpClass(cls):\n"
            f"        {setup}\n"
            "    def test_one(self): record('test_probe.SkippedFixture.test_one')\n"
            "    def test_two(self): record('test_probe.SkippedFixture.test_two')\n",
            encoding="utf-8",
        )

    def test_inventory_never_runs_bodies_and_assignment_is_process_seed_independent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            args = [
                "--count",
                "4",
                "--index",
                "0",
                "--isolate",
                "test_probe.Probe.test_000",
                "--list-only",
            ]
            first = self.command(root, *args)
            second = self.command(root, *args, seed="9001")
            self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            rows = [json.loads(line) for line in first.stdout.splitlines()]
            self.assertEqual(rows[0]["total"], 34)
            self.assertEqual(rows[0]["index"], 0)
            self.assertEqual(rows[0]["counts"][0], 1)
            self.assertEqual(len(rows) - 1, 34)
            self.assertFalse((root / "body").exists())
            self.assertFalse((root / "setup").exists())
            self.assertFalse((root / "module-setup").exists())

    def test_each_of_four_shards_executes_exactly_its_manifest_in_original_order(self):
        for count, index in ((size, position) for size in (4, 5) for position in range(size)):
            with self.subTest(count=count, index=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.fixture(root)
                result = self.command(
                    root,
                    "--count",
                    str(count),
                    "--index",
                    str(index),
                    "--isolate",
                    "test_probe.Probe.test_000",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                rows = [json.loads(line) for line in result.stdout.splitlines()]
                self.assertEqual(rows[0]["index"], index)
                expected = [row["id"] for row in rows[1:] if row["shard"] == index]
                self.assertEqual(len(expected), rows[0]["selected"])
                self.assertEqual((root / "order").read_text().splitlines(), expected)
                actual = {p.name.removeprefix("occurrence-") for p in root.glob("occurrence-*")}
                self.assertEqual(actual, set(expected))
                self.assertEqual((root / "setup").read_text(), "S")
                self.assertEqual((root / "cleanup").read_text(), "C")
                self.assertEqual((root / "module-setup").read_text(), "M")
                self.assertEqual((root / "module-cleanup").read_text(), "Z")

    def test_normal_class_setup_cleanup_and_class_skip_remain_successful(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root, setup="raise unittest.SkipTest('ordinary class skip')")
            result = self.command(root, "--count", "1", "--index", "0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ordinary class skip", result.stderr)
            self.assertTrue((root / "setup").exists())
            self.assertTrue((root / "cleanup").exists())
            self.assertTrue((root / "body").exists())
            self.assertEqual((root / "setup").read_text(), "S")
            self.assertEqual((root / "cleanup").read_text(), "C")

    def test_failures_errors_and_early_stop_return_nonzero_without_weakening_unittest(self):
        for body, setup in (
            ("self.fail('synthetic assertion')", "pass"),
            ("pass", "raise RuntimeError('synthetic fixture error')"),
            ("self._outcome.result.stop()", "pass"),
        ):
            with self.subTest(body=body, setup=setup), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.fixture(root, body=body, setup=setup)
                result = self.command(root, "--count", "1", "--index", "0")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertTrue((root / "cleanup").exists())
                if "self.fail" in body:
                    self.assertEqual(len(list(root.glob("occurrence-*"))), 34)

    def test_keyboard_interrupt_returns_130(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root, body="raise KeyboardInterrupt('synthetic interruption')")
            result = self.command(root, "--count", "1", "--index", "0")
            self.assertEqual(result.returncode, 130, result.stderr)
            self.assertEqual(len(list(root.glob("occurrence-*"))), 1)

    def test_discovery_failure_and_invalid_index_refuse_before_any_body(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / "tests/test_broken.py").write_text(
                "raise ImportError('synthetic discovery failure')\n", encoding="utf-8"
            )
            result = self.command(root, "--count", "4", "--index", "0", "--list-only")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("synthetic discovery failure", result.stderr)
            self.assertFalse((root / "body").exists())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            for index in ("-1", "4"):
                result = self.command(root, "--count", "4", "--index", index)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse((root / "body").exists())

    def test_idle_watchdog_does_not_count_arbitrary_output_as_test_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(
                root,
                body=(
                    f"import time\ntime.sleep({self.STARTUP_DELAY})\n"
                    "Path('noise-entered').write_text('entered')\n"
                    f"for _ in range({int(self.IDLE_SECONDS * 20)}):\n"
                    "    print('ordinary noise', flush=True)\n    time.sleep(0.1)"
                ),
            )
            result = self.watchdog_command(root)
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn('"reason": "no_genuine_test_progress"', result.stderr)
            self.assertIn('"status": "incomplete"', result.stderr)
            self.assertTrue((root / "noise-entered").is_file())
            self.assertIn("ordinary noise", result.stdout)

    def test_completed_subtests_keep_the_idle_watchdog_alive_without_fake_heartbeats(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(
                root,
                body=(
                    f"import time\ntime.sleep({self.STARTUP_DELAY})\n"
                    "Path('subtests-entered').write_text('entered')\n"
                    "for index in range(12):\n"
                    "    with self.subTest(index=index):\n        time.sleep(0.5)\n"
                    "Path('subtests-complete').write_text('complete')"
                ),
            )
            started = time.monotonic()
            result = self.watchdog_command(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater(time.monotonic() - started, self.IDLE_SECONDS)
            self.assertTrue((root / "subtests-entered").is_file())
            self.assertTrue((root / "subtests-complete").is_file())
            self.assertIn('"kind": "subtest_success"', result.stderr)
            self.assertNotIn('"status": "incomplete"', result.stderr)

    def test_startup_discovery_and_class_setup_have_the_same_idle_bound(self):
        for phase in ("discovery", "class_setup"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.fixture(root)
                path = root / "tests/test_probe.py"
                original = path.read_text(encoding="utf-8")
                entered = f"Path({phase!r}).write_text('entered')"
                pause = f"import time; time.sleep({self.IDLE_SECONDS * 2})"
                if phase == "discovery":
                    path.write_text(
                        f"from pathlib import Path\n{entered}\n{pause}\n" + original,
                        encoding="utf-8",
                    )
                else:
                    path.write_text(
                        original.replace(
                            "p = Path('setup')",
                            f"{entered}\n        {pause}\n        p = Path('setup')",
                            1,
                        ),
                        encoding="utf-8",
                    )
                result = self.watchdog_command(root)
                self.assertEqual(result.returncode, 124, result.stderr)
                self.assertIn('"reason": "no_genuine_test_progress"', result.stderr)
                self.assertIn('"status": "incomplete"', result.stderr)
                self.assertTrue((root / phase).is_file())
                self.assertFalse((root / "body").exists())

    def test_idle_timeout_stops_the_owned_descendant_process_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = (
                "import time\nfrom pathlib import Path\n"
                f"for index in range({int(self.IDLE_SECONDS * 80)}):\n"
                "    Path('descendant').write_text(str(index))\n"
                "    time.sleep(0.05)\n"
            )
            body = (
                "import subprocess, sys, time\n"
                f"subprocess.Popen([sys.executable, '-c', {child!r}], "
                "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                "while not Path('descendant').exists(): time.sleep(0.01)\n"
                "Path('descendant-entered').write_text('entered')\n"
                f"time.sleep({self.IDLE_SECONDS * 2})"
            )
            self.fixture(root, body=body)
            started = time.monotonic()
            result = self.watchdog_command(root)
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn('"reason": "no_genuine_test_progress"', result.stderr)
            self.assertIn('"status": "incomplete"', result.stderr)
            self.assertLess(time.monotonic() - started, self.IDLE_SECONDS * 2)
            self.assertTrue((root / "descendant-entered").is_file())
            self.assertTrue((root / "descendant").is_file())
            before = (root / "descendant").read_bytes()
            time.sleep(0.25)
            self.assertEqual((root / "descendant").read_bytes(), before)

    def test_idle_deadline_cannot_be_nonfinite_nonpositive_or_exceed_sixty_minutes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            for value in ("0", "-1", "nan", "inf", "3601"):
                with self.subTest(value=value):
                    result = self.command(
                        root, "--count", "1", "--index", "0", "--idle-seconds", value
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertFalse((root / "body").exists())

    def test_only_valid_completed_outcomes_advance_the_monotonic_progress_clock(self):
        reader = self.api._ProgressReader(100)
        start = {"sequence": 1, "kind": "start", "test_id": "probe", "time_ns": 101}
        reader.read(io.BytesIO((json.dumps(start) + "\n").encode()))
        self.assertEqual((reader.last_progress, reader.completed), (100, 0))
        success = start | {"sequence": 2, "kind": "subtest_success", "time_ns": 102}
        reader.read(io.BytesIO((json.dumps(success) + "\n").encode()))
        self.assertEqual((reader.last_progress, reader.completed), (102, 1))
        for change in (
            {"sequence": 4},
            {"sequence": True},
            {"kind": "heartbeat"},
            {"time_ns": 99},
            {"time_ns": time.monotonic_ns() + 10**12},
            {"test_id": None},
            {"extra": "unexpected"},
        ):
            invalid = success | {"sequence": 3} | change
            with self.subTest(change=change), self.assertRaises(ValueError):
                reader.read(io.BytesIO((json.dumps(invalid) + "\n").encode()))
            self.assertEqual((reader.last_progress, reader.completed), (102, 1))

    def test_abrupt_clean_exit_during_discovery_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            path = root / "tests/test_probe.py"
            path.write_text("import os; os._exit(0)\n" + path.read_text(), encoding="utf-8")
            result = self.command(root, "--count", "1", "--index", "0")
            self.assertEqual(result.returncode, 125, result.stderr)
            self.assertIn('"reason": "missing_or_invalid_terminal_receipt"', result.stderr)
            self.assertIn('"status": "incomplete"', result.stderr)
            self.assertFalse((root / "body").exists())

    def test_abrupt_clean_exit_during_a_test_body_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root, body="import os; os._exit(0)")
            result = self.command(root, "--count", "1", "--index", "0")
            self.assertEqual(result.returncode, 125, result.stderr)
            self.assertIn('"reason": "missing_or_invalid_terminal_receipt"', result.stderr)
            self.assertIn('"status": "incomplete"', result.stderr)
            self.assertEqual(len(list(root.glob("occurrence-*"))), 1)

    def test_mismatched_terminal_receipt_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(
                root,
                body=(
                    "import atexit, json, sys\n"
                    "def change_receipt():\n"
                    "    directory = Path(sys.argv[sys.argv.index('--_worker') + 1])\n"
                    "    path = directory / 'terminal.json'\n"
                    "    record = json.loads(path.read_bytes())\n"
                    "    record['index'] += 1\n"
                    "    path.write_text(json.dumps(record))\n"
                    "atexit.register(change_receipt)"
                ),
            )
            result = self.command(root, "--count", "1", "--index", "0")
            self.assertEqual(result.returncode, 125, result.stderr)
            self.assertIn('"reason": "missing_or_invalid_terminal_receipt"', result.stderr)
            self.assertEqual(len(list(root.glob("occurrence-*"))), 34)


class FixtureWorkerProgressTests(unittest.TestCase):
    def setUp(self):
        # This module's import defines inert fixtures; no application path is run.
        fixtures = importlib.import_module("test_improver_study")
        self.observe = fixtures.observe_fixture_workers

    def result(self):
        class ObservedResult(unittest.TestResult):
            def __init__(self):
                super().__init__()
                self.subtests = []

            def addSubTest(self, test, subtest, err):
                super().addSubTest(test, subtest, err)
                self.subtests.append((test, subtest, err))

        return ObservedResult()

    def test_worker_arguments_are_forwarded_once_and_result_identity_is_preserved(self):
        calls = []
        spec = SimpleNamespace(role="agent")
        initial, handle, extra = object(), object(), object()
        execution = SimpleNamespace(cleanup_status="removed")

        def execute(received, *, initial, handle, **kwargs):
            calls.append((received, initial, handle, kwargs))
            return execution

        fixture = SimpleNamespace(execute=execute)
        observe = self.observe

        class Observer(unittest.TestCase):
            def runTest(observer):
                observe(fixture, observer)
                actual = fixture.execute(spec, initial=initial, handle=handle, extra=extra)
                observer.assertIs(actual, execution)

        observer, result = Observer(), self.result()
        observer.run(result)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertEqual(calls, [(spec, initial, handle, {"extra": extra})])
        self.assertEqual(len(result.subtests), 1)
        self.assertIs(result.subtests[0][0], observer)
        self.assertIn("role='agent'", str(result.subtests[0][1]))

    def test_original_assertion_and_other_exception_propagate_without_a_checkpoint(self):
        def check(error):
            calls = []

            def execute(spec, *, initial, handle, **kwargs):
                calls.append(spec)
                raise error

            fixture = SimpleNamespace(execute=execute)
            observe = self.observe

            class Observer(unittest.TestCase):
                def runTest(observer):
                    observe(fixture, observer)
                    with observer.assertRaises(type(error)) as caught:
                        fixture.execute(SimpleNamespace(role="native"), initial={}, handle=None)
                    observer.assertIs(caught.exception, error)

            result = self.result()
            Observer().run(result)
            self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result.subtests, [])

        for error in (AssertionError("original checked input"), RuntimeError("original failure")):
            with self.subTest(error=type(error).__name__):
                check(error)

    def test_invalid_completed_worker_cleanup_marks_the_active_case_failed(self):
        execution = SimpleNamespace(cleanup_status="retained")
        fixture = SimpleNamespace(execute=lambda *args, **kwargs: execution)
        observe = self.observe

        class Observer(unittest.TestCase):
            def runTest(observer):
                observe(fixture, observer)
                actual = fixture.execute(SimpleNamespace(role="agent"), initial={}, handle=None)
                observer.assertIs(actual, execution)

        result = self.result()
        Observer().run(result)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(len(result.subtests), 1)
        self.assertIsNotNone(result.subtests[0][2])
        self.assertEqual(result.errors, [])

    def test_manual_fixture_reports_real_worker_check_to_the_active_outer_case(self):
        fixture = unittest.TestCase("runTest")
        spec = SimpleNamespace(role="proposal")
        execution = SimpleNamespace(cleanup_status="removed")
        calls = []

        def execute(received, *, initial, handle, **kwargs):
            fixture.assertIs(received, spec)
            calls.append(received)
            return execution

        fixture.execute = execute
        self.assertIsNone(fixture._outcome)
        observe = self.observe

        class Observer(unittest.TestCase):
            def runTest(observer):
                observer.assertIsNotNone(observer._outcome)
                observe(fixture, observer)
                fixture.execute(spec, initial={}, handle=None)

        observer, result = Observer(), self.result()
        observer.run(result)
        self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
        self.assertEqual(calls, [spec])
        self.assertEqual(len(result.subtests), 1)
        self.assertIs(result.subtests[0][0], observer)
        self.assertIsNone(fixture._outcome)


if __name__ == "__main__":
    unittest.main()
