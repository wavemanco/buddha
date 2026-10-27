"""Unified operator checks on synthetic inputs; orchestration seams are explicit.

The composed method uses the actual primary checker and compatible raw metadata.
Focused lifecycle methods replace controllers, not evidence of actual execution.
"""

import copy
import importlib.util
import io
import json
import tempfile
import traceback
import unittest
from contextlib import ExitStack, contextmanager, redirect_stdout
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_improver_launch_state import files, passive_only, sha

from buddha import gateway, plain_comparison, unified_funding
from buddha.authorization import Authorization
from buddha.provider import ModelSpec
from buddha.releases import _json


def reference(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def grant_record(authority):
    terms = authority.summary()
    return {
        "path": str(authority.path),
        "id": terms["authorization_id"],
        **{key: terms[key] for key in ("terms_sha256", "scope", "budget_microusd", "max_calls")},
    }


class UnifiedLaunchComposedTests(unittest.TestCase):
    def test_actual_primary_and_matching_raw_inputs_are_keyless_and_frozen(self):
        import test_baseline as raw_fixtures
        import test_improver_launch as primary_fixtures
        from test_plain_comparison_integration import PlainComparisonIntegrationTests

        from buddha import unified_launch

        primary_fixtures.ImproverLaunchTests.setUpClass()
        self.addCleanup(primary_fixtures.ImproverLaunchTests.doClassCleanups)
        primary = primary_fixtures.ImproverLaunchTests("runTest")
        self.addCleanup(primary.doCleanups)
        primary.setUp()
        bundle = primary.bundle()
        compatible = SimpleNamespace(definition=primary.definition, f=primary.f.f)
        raw = {}
        for mode in ("regenerate", "in-context"):
            case = raw_fixtures.BaselineTests("runTest")
            self.addCleanup(case.doCleanups)
            case.setUp()
            PlainComparisonIntegrationTests.match_baseline(case, compatible, mode)
            raw[mode] = case
        plan_path = bundle["folder"] / "comparison-plan.json"
        shared_path = bundle["folder"] / "shared-raw.sqlite3"
        plan = {
            "format": "buddha.plain-comparison-plan.v1",
            "method": "all_conditions_then_equal_prompts_descriptive.v1",
            "trial": str(bundle["directory"]),
            "definition_sha256": sha(bundle["declaration"].read_bytes()),
            "references": [
                {
                    "name": mode,
                    "directory": str(case.directory),
                    "authorization": str(shared_path),
                    "definition": str(case.descriptor),
                    "sha256": sha(case.descriptor.read_bytes()),
                }
                for mode, case in raw.items()
            ],
            "consumer_sources": plain_comparison._source_hashes(),
        }
        plan_path.write_bytes(_json(plan))
        authority = Authorization.create(
            shared_path,
            authorization_id="synthetic-unified-shared-raw",
            scope=unified_funding.reference_scope(sha(plan_path.read_bytes())),
            budget_microusd=100_000,
            max_calls=100,
        )
        extra = bundle["folder"] / "outer-static-control.txt"
        extra.write_bytes(b"Synthetic outer control; no execution or account assertion.\n")
        sources = {
            str(path): sha(path.read_bytes())
            for path in (*unified_launch._sources(), plan_path, extra)
        } | plan["consumer_sources"]
        bundle["proposal"]["source_sha256"].update(sources)
        bundle["proposal_path"].write_bytes(_json(bundle["proposal"]))
        bundle["approval"]["proposal_sha256"] = sha(bundle["proposal_path"].read_bytes())
        bundle["record"]["proposal"] = reference(bundle["proposal_path"])
        bundle["record"]["source_sha256"].update(sources)
        primary.save(bundle)
        phases = primary.definition["phase_limits"]
        outer = {
            "format": "buddha.unified-launch.v1",
            "primary_launch": reference(bundle["path"]),
            "comparison_plan": reference(plan_path),
            "reference_grant": grant_record(authority),
            "total_limits": {
                key: sum(row[key] for row in phases.values()) + value
                for key, value in (("budget_microusd", 100_000), ("max_calls", 100))
            },
            "directory": str(bundle["folder"] / "unified-workspace"),
            "source_sha256": sources,
        }
        path = bundle["folder"] / "unified-launch.json"
        path.write_bytes(_json(outer))
        roots = [primary.root, *(case.root for case in raw.values())]
        before = [files(root) for root in roots]
        original_terms = {
            phase: grant_record(grant) for phase, grant in bundle["authorities"].items()
        } | {"shared_plain_references": grant_record(authority)}
        with (
            passive_only(self),
            patch("os.getenv", side_effect=AssertionError("credential read")),
            patch("os.environ.get", side_effect=AssertionError("credential read")),
        ):
            try:
                checked = unified_launch.check_launch(path, expected_sha256=sha(path.read_bytes()))
            except unified_launch.UnifiedLaunchError as error:
                chain = []
                cause = error
                while cause is not None:
                    chain.append(
                        {
                            "type": type(cause).__name__,
                            "locations": [
                                [Path(frame.filename).name, frame.name, frame.lineno]
                                for frame in traceback.extract_tb(cause.__traceback__)
                            ],
                        }
                    )
                    cause = cause.__context__
                print(json.dumps({"synthetic_check_error_chain": chain}), flush=True)
                raise
        self.assertIsNone(checked["stop_code"])
        self.assertEqual([files(root) for root in roots], before)
        self.assertFalse(Path(outer["directory"]).exists())
        self.assertFalse(bundle["directory"].exists())
        self.assertTrue(all(not case.directory.exists() for case in raw.values()))
        self.assertEqual(
            {phase: grant_record(grant) for phase, grant in bundle["authorities"].items()}
            | {"shared_plain_references": grant_record(authority)},
            original_terms,
        )
        self.assertRegex(checked["primary"]["state_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(checked["references"]["state_sha256"], r"^[0-9a-f]{64}$")
        original = copy.deepcopy(checked)
        checked["controls"].clear()
        with passive_only(self):
            self.assertEqual(
                unified_launch.check_launch(path, expected_sha256=sha(path.read_bytes())), original
            )
        original_outer = path.read_bytes()
        cases = [
            outer | {"extra": True},
            outer | {"primary_launch": outer["primary_launch"] | {"sha256": "f" * 64}},
            outer | {"directory": str(bundle["directory"])},
            outer
            | {
                "source_sha256": {
                    name: pin
                    for name, pin in sources.items()
                    if name != str(Path(unified_launch.__file__).absolute())
                }
            },
            outer | {"total_limits": outer["total_limits"] | {"max_calls": True}},
        ]
        for index, changed in enumerate(cases):
            try:
                path.write_bytes(_json(changed))
                before = [files(root) for root in roots]
                with (
                    self.subTest(refusal=index),
                    passive_only(self),
                    self.assertRaises(unified_launch.UnifiedLaunchError),
                ):
                    unified_launch.check_launch(path, expected_sha256=sha(path.read_bytes()))
                self.assertEqual([files(root) for root in roots], before)
            finally:
                path.write_bytes(original_outer)


class UnifiedLaunchLifecycleTests(unittest.TestCase):
    """Cheap glue tests: context readers/controllers are supplied seams, not executions."""

    def setUp(self):
        from buddha import unified_launch

        self.api = unified_launch
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.workspace = self.root / "operator"
        self.primary_root = self.root / "primary"
        self.events, self.prepared, self.runs = [], [], []
        self.primary_state = "fresh"
        self.states = dict.fromkeys(("regenerate", "in-context"), "fresh")
        self.first_partial = None
        self.primary_result = "complete"
        self.primary_review = None
        self.primary_error = None
        self.observation_error = None
        self.enter_change = None
        self.fingerprints = {"openai": "a" * 64, "anthropic": "b" * 64}
        self.specs = [
            ModelSpec(provider, "synthetic-model", 100, 10, 1, 1, "https://example.invalid/bounds")
            for provider in self.fingerprints
        ]
        self.launch_path = self.root / "primary-launch.json"
        self.launch_path.write_bytes(b"{}")
        self.plan_path = self.root / "plan.json"
        self.shared = Authorization.create(
            self.root / "shared-raw.sqlite3",
            authorization_id="synthetic-lifecycle-only",
            budget_microusd=25,
            max_calls=2,
            scope="synthetic lifecycle seam; never dispatches",
        )
        self.plan = {
            "format": "buddha.plain-comparison-plan.v1",
            "method": "all_conditions_then_equal_prompts_descriptive.v1",
            "trial": str(self.primary_root),
            "definition_sha256": "0" * 64,
            "references": [],
            "consumer_sources": plain_comparison._source_hashes(),
        }
        for name in self.states:
            definition = self.root / (name + "-definition.json")
            definition.write_bytes(b"{}")
            self.plan["references"].append(
                {
                    "name": name,
                    "directory": str(self.root / name),
                    "authorization": str(self.shared.path),
                    "definition": str(definition),
                    "sha256": sha(definition.read_bytes()),
                }
            )
        self.plan_path.write_bytes(_json(self.plan))
        control = self.root / "reviewed-control.txt"
        control.write_bytes(b"Synthetic lifecycle control.\n")
        self.record = {
            "format": "buddha.unified-launch.v1",
            "primary_launch": reference(self.launch_path),
            "comparison_plan": reference(self.plan_path),
            "reference_grant": grant_record(self.shared),
            "total_limits": {"budget_microusd": 150, "max_calls": 16},
            "directory": str(self.workspace),
            "source_sha256": {str(control): sha(control.read_bytes())},
        }
        self.path = self.root / "unified.json"
        self.path.write_bytes(_json(self.record))
        self.digest = sha(self.path.read_bytes())
        self.original_inputs = files(self.root)
        self.initial_terms = grant_record(self.shared)

    def check(self, path, digest, *, owned_lock=False):
        self.assertEqual((path, digest), (self.path, self.digest))
        self.events.append(("check", owned_lock))
        review_path = self.workspace / "review.json"
        review = json.loads(review_path.read_bytes()) if review_path.exists() else None
        controls = self.record["source_sha256"] | {str(self.path): self.digest}
        if review is not None:
            controls[str(review_path)] = sha(review_path.read_bytes())
        phase = (
            "primary"
            if self.primary_state != "complete"
            else "plain-regenerate"
            if self.states["regenerate"] != "complete"
            else "plain-in-context"
            if self.states["in-context"] != "complete"
            else "comparison"
        )
        stop = None
        if (self.workspace / "running.lock").exists() and not owned_lock:
            stop = "execution_lock_present"
        if review is not None and any(state != "complete" for state in self.states.values()):
            try:
                gateway._review(review, fresh=True)
            except ValueError:
                stop = "review_expired"
        return {
            "record": copy.deepcopy(self.record),
            "directory": str(self.workspace),
            "controls": controls,
            "funding": {
                "limits": copy.deepcopy(self.record["total_limits"]),
                "terms": copy.deepcopy(self.initial_terms),
            },
            "primary": {
                "state": self.primary_state,
                "account_scope": "synthetic shared account assertion",
                "timeout_seconds": 30,
                "stop_code": None,
                "review": copy.deepcopy(self.primary_review),
            },
            "references": {
                "state": "complete"
                if all(state == "complete" for state in self.states.values())
                else "fresh"
                if all(state == "fresh" for state in self.states.values())
                else "prepared",
                "references": [
                    {"name": name, "directory": str(self.root / name), "state": state}
                    for name, state in self.states.items()
                ],
            },
            "review": review,
            "profiles": [asdict(spec) for spec in self.specs],
            "phase": phase,
            "stop_code": stop,
        }

    @contextmanager
    def keys(self, settings, *, prompt_keys, notice):
        self.events.append(("keys", prompt_keys))
        self.assertEqual({spec.provider for spec in settings.profiles()}, set(self.fingerprints))
        if self.enter_change is not None:
            self.enter_change()
        yield

    def primary(self, path, **options):
        self.events.append(("primary",))
        self.assertEqual(path, self.launch_path)
        self.assertEqual(options["expected_sha256"], self.record["primary_launch"]["sha256"])
        self.assertTrue(options["live"])
        self.assertTrue(options["confirm_project_keys"])
        self.assertFalse(options["prompt_keys"])
        if self.primary_error is not None:
            raise self.primary_error
        if self.primary_result == "complete":
            self.primary_state = "complete"
            self.primary_review = {
                "format": "buddha.account-review.v2",
                "checked_on": datetime.now(UTC).date().isoformat(),
                "credential_context": self.record["primary_launch"]["sha256"],
                "credential_fingerprints": {"openai": self.fingerprints["openai"]},
                "account_scope": "synthetic shared account assertion",
            }
            self.primary_reports()
        return {"status": self.primary_result}

    def primary_reports(self):
        folder = self.primary_root / "final"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "report.json").write_bytes(b'{"synthetic":"primary complete seam"}')

    def prepare(self, directory, **options):
        name = directory.name
        self.events.append(("prepare", name))
        self.assertEqual(self.primary_state, "complete")
        self.assertEqual(options["authorization"].path, self.shared.path)
        self.assertEqual(options["review"]["credential_context"], self.digest)
        self.assertEqual(options["review"]["credential_fingerprints"], self.fingerprints)
        self.assertEqual(options["expected_input_hashes"][self.path], self.digest)
        self.assertIn(self.workspace / "review.json", options["input_files"])
        owner = directory / "owners/0"
        owner.mkdir(parents=True)
        (owner / "manifest.json").write_bytes(_json({"review": options["review"]}))
        self.prepared.append(name)
        self.states[name] = "prepared"

    def run_reference(self, directory, *, transport):
        name = directory.name
        self.events.append(("run", name))
        self.runs.append(directory)
        self.assertTrue(transport.allow_paid)
        self.assertEqual(transport.timeout_seconds, 30)
        if self.first_partial == name:
            self.first_partial = None
            return {"status": "incomplete"}
        self.states[name] = "complete"
        (directory / "report.json").write_bytes(b'{"synthetic":"raw complete seam"}')
        return {"status": "complete"}

    def observe(self, output, **options):
        self.events.append(("observation", options["phase"], options["reason"]))
        self.assertEqual(options["reference_grant"], self.record["reference_grant"])
        self.assertEqual(options["total_limits"], self.record["total_limits"])
        if self.observation_error is not None:
            raise self.observation_error
        raw = _json({"status": "incomplete", "cancelled": options["cancelled"]})
        output.write_bytes(raw)
        return {"path": str(output), "sha256": sha(raw), "observation": json.loads(raw)}

    def compare(self, path, **options):
        self.events.append(("comparison",))
        self.assertEqual(path, self.plan_path)
        self.assertEqual(self.primary_state, "complete")
        self.assertTrue(all(state == "complete" for state in self.states.values()))
        self.assertEqual(set(options["expected_reference_report_sha256"]), set(self.states))
        return {"format": "synthetic.comparison.seam.v1"}

    def credentials(self, providers, *, context):
        self.assertIn(context, {self.digest, self.record["primary_launch"]["sha256"]})
        self.events.append(("fingerprints", context))
        return {provider: self.fingerprints[provider] for provider in providers}

    @contextmanager
    def seams(self):
        with ExitStack() as stack:
            targets = {
                "buddha.unified_launch._configuration": lambda *a: (
                    copy.deepcopy(self.record),
                    {self.path: self.digest},
                ),
                "buddha.unified_launch._check": self.check,
                "buddha.credentials.key_environment": self.keys,
                "buddha.gateway.credential_fingerprints": self.credentials,
                "buddha.improver_launch.launch": self.primary,
                "buddha.baseline.prepare_baseline": self.prepare,
                "buddha.baseline.run_baseline": self.run_reference,
                "buddha.plain_comparison.compare_plain_references": self.compare,
                "buddha.comparison_observation.save_observation": self.observe,
            }
            for target, function in targets.items():
                stack.enter_context(patch(target, side_effect=function))
            for target in (
                "buddha.authorization.Authorization.create",
                "buddha.gateway.RawHTTPTransport.prepare",
                "buddha.executor.run_container",
                "getpass.getpass",
            ):
                stack.enter_context(
                    patch(target, side_effect=AssertionError("unexpected execution"))
                )
            yield
        for path, digest in self.original_inputs.items():
            self.assertEqual(sha(Path(path).read_bytes()), digest)
        self.assertEqual(grant_record(self.shared), self.initial_terms)

    def launch(self, **changes):
        return self.api.launch(
            self.path,
            **(
                {
                    "expected_sha256": self.digest,
                    "live": True,
                    "prompt_keys": True,
                    "confirm_project_keys": True,
                    "notice": lambda text: None,
                }
                | changes
            ),
        )

    def test_serial_order_one_key_context_recheck_and_pending_reviews(self):
        with self.seams():
            result = self.launch()
        work = [
            event
            for event in self.events
            if event[0] in {"primary", "prepare", "run", "comparison"}
        ]
        self.assertEqual(
            work,
            [
                ("primary",),
                ("prepare", "regenerate"),
                ("run", "regenerate"),
                ("prepare", "in-context"),
                ("run", "in-context"),
                ("comparison",),
            ],
        )
        self.assertEqual([event for event in self.events if event[0] == "keys"], [("keys", True)])
        key_at, primary_at = self.events.index(("keys", True)), self.events.index(("primary",))
        self.assertTrue(any(event[0] == "check" for event in self.events[key_at + 1 : primary_at]))
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["review_status"], "pending_separate_review")
        self.assertEqual(json.loads((self.workspace / "comparison.json").read_bytes()), result)
        review = json.loads((self.workspace / "review.json").read_bytes())
        self.assertEqual(review["credential_context"], self.digest)
        self.assertFalse((self.workspace / "running.lock").exists())

    def test_partial_primary_stops_before_raw_preparation(self):
        self.primary_result = "stopped"
        with self.seams():
            result = self.launch()
        self.assertEqual((result["status"], result["reason"]), ("incomplete", "primary_incomplete"))
        self.assertTrue(result["observation_saved"])
        self.assertFalse(self.prepared)
        self.assertFalse(self.runs)
        self.assertFalse((self.workspace / "review.json").exists())
        self.assertNotIn(("comparison",), self.events)

    def test_controller_stop_reasons_are_retained_before_later_conditions(self):
        from buddha import baseline, improver_launch

        with (
            self.seams(),
            patch.object(
                improver_launch,
                "launch",
                return_value={"status": "incomplete", "reason": "unknown"},
            ),
        ):
            result = self.launch()
        self.assertEqual((result["phase"], result["reason"]), ("primary", "unknown"))
        self.assertFalse(self.prepared)
        with (
            self.seams(),
            patch.object(
                baseline,
                "run_baseline",
                return_value={
                    "status": "incomplete",
                    "stopped_stage": 1,
                    "stages": [{"reason": None, "worker": {"reason": "authority"}}],
                },
            ),
        ):
            result = self.launch()
        self.assertEqual((result["phase"], result["reason"]), ("plain-regenerate", "authority"))
        self.assertEqual(self.prepared, ["regenerate"])
        self.assertIn(("observation", "plain-regenerate", "authority"), self.events)
        self.assertNotIn(("comparison",), self.events)

    def test_partial_raw_resumes_same_root_without_preparing_replacement(self):
        self.first_partial = "regenerate"
        with self.seams():
            first = self.launch()
            old = {
                str(path): path.read_bytes() for path in (self.workspace / "observations").iterdir()
            }
            owner = self.root / "regenerate/owners/0/manifest.json"
            owner_raw = owner.read_bytes()
            second = self.launch()
        self.assertEqual(first["reason"], "reference_incomplete")
        self.assertEqual(second["status"], "complete")
        self.assertEqual(self.prepared, ["regenerate", "in-context"])
        self.assertEqual(
            self.runs,
            [self.root / "regenerate", self.root / "regenerate", self.root / "in-context"],
        )
        self.assertEqual(owner.read_bytes(), owner_raw)
        self.assertTrue(all(Path(path).read_bytes() == raw for path, raw in old.items()))
        self.assertEqual(self.events.count(("primary",)), 1)

    def test_cancellation_and_original_error_survive_observation_failure(self):
        for error in (
            KeyboardInterrupt("synthetic cancellation"),
            RuntimeError("synthetic original"),
        ):
            for observation_error in (
                OSError("synthetic observation failure"),
                KeyboardInterrupt("synthetic observation cancellation"),
            ):
                with self.subTest(
                    error=type(error).__name__, observation=type(observation_error).__name__
                ):
                    self.primary_error = error
                    self.observation_error = observation_error
                    with self.seams(), self.assertRaises(type(error)) as raised:
                        self.launch()
                    self.assertIs(raised.exception, error)
                    self.assertFalse(self.prepared)
                    self.assertFalse((self.workspace / "running.lock").exists())
        self.assertIn(("observation", "primary", "cancelled"), self.events)
        self.assertIn(("observation", "primary", "launch_stopped"), self.events)

    def test_outer_lock_stops_before_keys_and_preserves_foreign_lock(self):
        self.workspace.mkdir()
        lock = self.workspace / "running.lock"
        lock.write_bytes(b"synthetic other operator")
        with self.seams():
            result = self.launch()
        self.assertEqual(result["reason"], "execution_lock_present")
        self.assertFalse(
            any(event[0] in {"keys", "primary", "prepare", "run"} for event in self.events)
        )
        self.assertEqual(lock.read_bytes(), b"synthetic other operator")

    def test_changed_preflight_during_key_entry_prevents_all_controllers(self):
        self.enter_change = lambda: self.record["total_limits"].update(max_calls=17)
        with self.seams(), self.assertRaises(self.api.UnifiedLaunchError):
            self.launch()
        self.assertFalse(any(event[0] in {"primary", "prepare", "run"} for event in self.events))

    def retained_review(self, *, days=0, fingerprints=None):
        self.primary_state = "complete"
        self.primary_reports()
        self.workspace.mkdir(exist_ok=True)
        review = {
            "format": "buddha.account-review.v2",
            "checked_on": (datetime.now(UTC) - timedelta(days=days)).date().isoformat(),
            "credential_context": self.digest,
            "credential_fingerprints": self.fingerprints if fingerprints is None else fingerprints,
            "account_scope": "synthetic shared account assertion",
        }
        (self.workspace / "review.json").write_bytes(_json(review))

    def test_expired_review_or_changed_credentials_stop_before_dispatch(self):
        self.retained_review(days=8)
        with self.seams():
            result = self.launch()
        self.assertEqual(result["reason"], "review_expired")
        self.assertFalse(any(event[0] == "keys" for event in self.events))
        self.retained_review(fingerprints=dict.fromkeys(self.fingerprints, "c" * 64))
        with self.seams(), self.assertRaises(self.api.UnifiedLaunchError):
            self.launch()
        self.assertFalse(self.prepared)
        self.assertFalse(self.runs)

    def test_cached_complete_publication_rechecks_without_keys_or_controllers(self):
        with self.seams():
            first = self.launch()
            before = files(self.root)
            self.events.clear()
            with (
                patch(
                    "buddha.credentials.key_environment", side_effect=AssertionError("key entry")
                ),
                patch(
                    "buddha.gateway.credential_fingerprints",
                    side_effect=AssertionError("credential read"),
                ),
            ):
                second = self.launch(live=False, prompt_keys=False, confirm_project_keys=False)
        self.assertEqual(second, first)
        self.assertEqual(files(self.root), before)
        self.assertEqual([event for event in self.events if event[0] != "check"], [("comparison",)])

    def test_completed_primary_still_requires_its_original_credential_context(self):
        self.primary_state = "complete"
        self.primary_reports()
        self.primary_review = {
            "credential_fingerprints": {"openai": "c" * 64},
            "credential_context": self.record["primary_launch"]["sha256"],
        }
        with self.seams(), self.assertRaises(self.api.UnifiedLaunchError):
            self.launch()
        self.assertIn(("fingerprints", self.record["primary_launch"]["sha256"]), self.events)
        self.assertFalse(self.prepared)
        self.assertFalse(self.runs)
        self.assertNotIn(("primary",), self.events)

    def test_missing_live_confirmation_invalid_options_or_transport_never_enter_keys(self):
        for changes in (
            {"live": False},
            {"confirm_project_keys": False},
            {"prompt_keys": 1},
            {"heartbeat_seconds": 0},
            {"transport": gateway.RawHTTPTransport(allow_paid=False, timeout_seconds=30)},
            {"transport": gateway.RawHTTPTransport(allow_paid=True, timeout_seconds=31)},
        ):
            self.events.clear()
            with (
                self.subTest(options=list(changes)),
                self.seams(),
                self.assertRaises(self.api.UnifiedLaunchError),
            ):
                self.launch(**changes)
            self.assertFalse(
                any(event[0] in {"keys", "primary", "prepare", "run"} for event in self.events)
            )

    @contextmanager
    def passive_check_seams(self, primary_state, reference_states):
        controls = {Path(path): digest for path, digest in self.record["source_sha256"].items()}
        controls[self.path] = self.digest
        primary = {
            "state": primary_state,
            "stop_code": None,
            "account_scope": "synthetic shared account assertion",
            "bindings": {str(path): digest for path, digest in controls.items()},
        }
        raw = {
            "state": "fresh"
            if all(s == "fresh" for s in reference_states.values())
            else "prepared",
            "references": [
                {"name": name, "directory": str(self.root / name), "state": state}
                for name, state in reference_states.items()
            ],
            "blocked_reasons": [],
            "state_sha256": "0" * 64,
        }
        before = files(self.root)
        with (
            passive_only(self),
            patch("os.getenv", side_effect=AssertionError("credential read")),
            patch("os.environ.get", side_effect=AssertionError("credential read")),
            patch("buddha.unified_launch._configuration", return_value=(self.record, controls)),
            patch("buddha.unified_funding.check_funding", return_value={"primary": primary}),
            patch("buddha.baseline_state.inspect_references", return_value=raw),
            patch("buddha.unified_launch._compatible", return_value=self.specs),
        ):
            yield
        self.assertEqual(files(self.root), before)

    def test_passive_check_refuses_early_raw_work_and_out_of_order_reference(self):
        for primary, states in (
            ("fresh", {"regenerate": "prepared", "in-context": "fresh"}),
            ("prepared", {"regenerate": "fresh", "in-context": "prepared"}),
            ("complete", {"regenerate": "fresh", "in-context": "prepared"}),
            ("complete", {"regenerate": "fresh"}),
        ):
            with (
                self.subTest(primary=primary, references=states),
                self.passive_check_seams(primary, states),
                self.assertRaises(self.api.UnifiedLaunchError),
            ):
                self.api.check_launch(self.path, expected_sha256=self.digest)

    def test_real_raw_review_context_freshness_and_anchor_match_are_checked_keylessly(self):
        self.retained_review()
        review_path = self.workspace / "review.json"
        original = review_path.read_bytes()
        states = dict.fromkeys(self.states, "fresh")
        with self.passive_check_seams("complete", states):
            self.assertIsNone(
                self.api.check_launch(self.path, expected_sha256=self.digest)["stop_code"]
            )
        with (
            self.passive_check_seams("fresh", states),
            self.assertRaises(self.api.UnifiedLaunchError),
        ):
            self.api.check_launch(self.path, expected_sha256=self.digest)

        for changes in (
            {"credential_context": "f" * 64},
            {"account_scope": "foreign synthetic account"},
            {"credential_fingerprints": {"openai": "a" * 64}},
        ):
            review_path.write_bytes(_json(json.loads(original) | changes))
            with (
                self.subTest(changes=changes),
                self.passive_check_seams("complete", states),
                self.assertRaises(self.api.UnifiedLaunchError),
            ):
                self.api.check_launch(self.path, expected_sha256=self.digest)
        self.retained_review(days=8)
        with self.passive_check_seams("complete", states):
            self.assertEqual(
                self.api.check_launch(self.path, expected_sha256=self.digest)["stop_code"],
                "review_expired",
            )
        review_path.write_bytes(original)
        owner = self.root / "regenerate/owners/0/manifest.json"
        owner.parent.mkdir(parents=True)
        owner.write_bytes(_json({"review": json.loads(original) | {"account_scope": "foreign"}}))
        with (
            self.passive_check_seams("complete", states | {"regenerate": "prepared"}),
            self.assertRaises(self.api.UnifiedLaunchError),
        ):
            self.api.check_launch(self.path, expected_sha256=self.digest)


class UnifiedLaunchCliTests(unittest.TestCase):
    def setUp(self):
        from buddha.unified_launch import _entrypoint

        spec = importlib.util.spec_from_file_location("unified_cli_fixture", _entrypoint())
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)
        self.args = ["--handoff", "synthetic-handoff.json", "--sha256", "0" * 64]

    def invoke(self, flags):
        output = io.StringIO()
        with redirect_stdout(output):
            code = self.cli.main(self.args + flags)
        return code, json.loads(output.getvalue())

    def test_check_mode_is_passive_and_invalid_options_are_redacted(self):
        with (
            patch.object(
                self.cli, "check_launch", return_value={"phase": "primary", "stop_code": None}
            ) as checked,
            patch.object(self.cli, "launch", side_effect=AssertionError("live controller")),
        ):
            code, record = self.invoke(["--check"])
            self.assertEqual((code, record["status"]), (0, "checked"))
            self.assertEqual(checked.call_count, 1)
            for flags in (
                ["--check", "--live"],
                ["--check", "--prompt-keys"],
                ["--SYNTHETIC-PRIVATE-ARGUMENT"],
            ):
                code, record = self.invoke(flags)
                self.assertEqual((code, record["status"]), (2, "stopped"))
                self.assertNotIn("SYNTHETIC-PRIVATE", json.dumps(record))
            self.assertEqual(checked.call_count, 1)

    def test_live_completion_cancellation_and_errors_keep_safe_status_codes(self):
        with patch.object(
            self.cli,
            "launch",
            return_value={
                "format": "buddha.unified-comparison-report.v1",
                "status": "complete",
                "review_status": "pending_separate_review",
                "comparison": {"large_private_artifact": "not console output"},
            },
        ) as launch:
            code, record = self.invoke(["--live", "--prompt-keys", "--confirm-project-keys"])
            self.assertEqual(
                (code, record["status"], record["review_status"]),
                (0, "complete", "pending_separate_review"),
            )
            self.assertEqual(record["format"], "buddha.unified-operator.v1")
            self.assertNotIn("comparison", record)
            self.assertTrue(launch.call_args.kwargs["live"])
            self.assertTrue(launch.call_args.kwargs["prompt_keys"])
            self.assertTrue(launch.call_args.kwargs["confirm_project_keys"])
        with tempfile.TemporaryDirectory() as directory:
            publication = Path(directory) / "comparison.json"
            report = {
                "status": "complete",
                "publication_path": str(publication),
                "comparison": {"large_private_artifact": "not console output"},
            }
            publication.write_bytes(_json(report))
            with patch.object(
                self.cli,
                "launch",
                return_value=report,
            ):
                code, record = self.invoke(["--live"])
                publication.write_bytes(b'{"changed":true}')
                stopped_code, stopped = self.invoke(["--live"])
            self.assertEqual(code, 0)
            self.assertEqual(record["publication_path"], str(publication))
            self.assertEqual(record["publication_sha256"], sha(_json(report)))
            self.assertNotIn("comparison", record)
            self.assertEqual((stopped_code, stopped["status"]), (2, "stopped"))
        for error, code, reason in (
            (KeyboardInterrupt("SYNTHETIC-PRIVATE-ERROR"), 130, "cancelled"),
            (self.cli.credentials.KeyInputError("key_input_invalid"), 2, "key_input_invalid"),
            (RuntimeError("SYNTHETIC-PRIVATE-ERROR"), 2, "launch_stopped"),
        ):
            with self.subTest(reason=reason), patch.object(self.cli, "launch", side_effect=error):
                actual, record = self.invoke(["--live"])
                self.assertEqual((actual, record["reason"]), (code, reason))
                self.assertNotIn("SYNTHETIC-PRIVATE", json.dumps(record))

    def test_help_lists_flags_without_checking_or_executing(self):
        output = io.StringIO()
        with (
            redirect_stdout(output),
            patch.object(self.cli, "launch", side_effect=AssertionError("controller")),
            patch.object(self.cli, "check_launch", side_effect=AssertionError("preflight")),
            self.assertRaises(SystemExit) as stopped,
        ):
            self.cli.main(["--help"])
        self.assertEqual(stopped.exception.code, 0)
        for flag in (
            "--handoff",
            "--sha256",
            "--check",
            "--live",
            "--prompt-keys",
            "--confirm-project-keys",
        ):
            self.assertIn(flag, output.getvalue())
