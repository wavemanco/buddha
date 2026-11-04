"""Read-only four-grant accounting, with real fresh synthetic authority bytes."""

import copy
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from test_improver_launch_state import files, passive_only, sha

from buddha import plain_comparison, unified_funding
from buddha.authorization import Authorization
from buddha.releases import _json


def plan_files(root, trial, identity):
    references = []
    for name in ("regenerate", "in-context"):
        definition = root / (name + "-definition.json")
        definition.write_bytes(b"{}")
        references.append(
            {
                "name": name,
                "directory": str(root / name),
                "authorization": str(root / "plain.sqlite3"),
                "definition": str(definition),
                "sha256": sha(definition.read_bytes()),
            }
        )
    plan = {
        "format": "buddha.plain-comparison-plan.v1",
        "method": "all_conditions_then_equal_prompts_descriptive.v1",
        "trial": str(trial),
        "definition_sha256": identity,
        "references": references,
        "consumer_sources": plain_comparison._source_hashes(),
    }
    path = root / "plan.json"
    path.write_bytes(_json(plan))
    return path, plan


def grant_record(authority):
    terms = authority.summary()
    return {
        "path": str(authority.path),
        "id": terms["authorization_id"],
        **{key: terms[key] for key in ("terms_sha256", "scope", "budget_microusd", "max_calls")},
    }


class UnifiedFundingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.scope_serial = 0
        self.primary_path = self.root / "launch.json"
        self.primary_path.write_bytes(b"{}")
        self.plan_path, self.plan = plan_files(self.root, self.root / "primary", "0" * 64)
        self.authorities = {}
        for name, budget, attempts in (
            ("search", 40, 4),
            ("validation", 0, 0),
            ("final", 85, 10),
            ("shared_plain_references", 25, 2),
        ):
            path = self.root / (
                "plain.sqlite3" if name == "shared_plain_references" else name + ".db"
            )
            scope = (
                unified_funding.reference_scope(sha(self.plan_path.read_bytes()))
                if name == "shared_plain_references"
                else name
            )
            self.authorities[name] = Authorization.create(
                path,
                authorization_id=name,
                budget_microusd=budget,
                max_calls=attempts,
                scope=scope,
            )
        self.primary = {
            "directory": str(self.root / "primary"),
            "definition_sha256": "0" * 64,
            "bindings": {
                str(self.plan_path): sha(self.plan_path.read_bytes()),
                **self.plan["consumer_sources"],
                str(Path(unified_funding.__file__).absolute()): sha(
                    Path(unified_funding.__file__).read_bytes()
                ),
            },
            "authorizations": {
                name: str(authority.path)
                for name, authority in self.authorities.items()
                if name != "shared_plain_references"
            },
            "funding": {"phases": self.phases()},
            "protected_roots": [
                str(self.root / "primary"),
                str(self.primary_path),
                *(
                    str(a.path)
                    for name, a in self.authorities.items()
                    if name != "shared_plain_references"
                ),
            ],
            "state": "fresh",
            "phase": "search",
            "stop_code": None,
        }
        self.grant = grant_record(self.authorities["shared_plain_references"])
        self.options = {
            "expected_launch_sha256": sha(self.primary_path.read_bytes()),
            "comparison_plan": self.plan_path,
            "expected_plan_sha256": sha(self.plan_path.read_bytes()),
            "reference_grant": self.grant,
            "total_limits": {"budget_microusd": 150, "max_calls": 16},
        }

    def phases(self):
        from buddha.launch_common import _snapshot

        return {
            name: (observed := _snapshot(authority.path)[0])["config"] | observed["totals"]
            for name, authority in self.authorities.items()
            if name != "shared_plain_references"
        }

    def check(self, **options):
        before = files(self.root)
        try:
            with (
                passive_only(self),
                patch("os.getenv", side_effect=AssertionError("credential read")),
                patch("os.environ.get", side_effect=AssertionError("credential read")),
                patch(
                    "buddha.improver_launch.check_launch", return_value=copy.deepcopy(self.primary)
                ),
            ):
                return unified_funding.check_funding(self.primary_path, **(self.options | options))
        finally:
            self.assertEqual(files(self.root), before)

    def save_plan(self):
        self.plan_path.write_bytes(_json(self.plan))
        digest = sha(self.plan_path.read_bytes())
        self.options["expected_plan_sha256"] = digest
        self.primary["bindings"][str(self.plan_path)] = digest
        # Preserve the old synthetic grant and bind a fresh one to the new
        # plan, so a later stale-scope refusal cannot mask the guard under test.
        self.scope_serial += 1
        original = self.authorities["shared_plain_references"].path
        preserved = self.root / ("preserved-plain-" + str(self.scope_serial) + ".db")
        self.assertTrue(original.resolve().is_relative_to(self.root))
        self.assertTrue(preserved.resolve().is_relative_to(self.root))
        self.assertFalse(preserved.exists())
        original.rename(preserved)
        self.authorities["shared_plain_references"] = Authorization.create(
            original,
            authorization_id="shared_plain_references",
            budget_microusd=25,
            max_calls=2,
            scope=unified_funding.reference_scope(digest),
        )
        self.grant.clear()
        self.grant.update(grant_record(self.authorities["shared_plain_references"]))

    def operation(self, phase, *, completed=False, charge=3):
        # Deliberately adversarial synthetic receipt bytes, never a paid ledger.
        authority = self.authorities[phase]
        owner = self.root / "synthetic-owner"
        with closing(sqlite3.connect(authority.path)) as connection:
            connection.execute(
                "INSERT INTO auth_runs VALUES (?,?,?,?,?,?,?)",
                (
                    "owner",
                    "0" * 64,
                    str(owner),
                    str(owner / "operations.sqlite3"),
                    "0" * 64,
                    None,
                    0,
                ),
            )
            connection.execute(
                "INSERT INTO auth_operations VALUES (?,?,?,?,?,?,?,?)",
                (
                    "owner",
                    "operation",
                    "0" * 64,
                    7,
                    "completed" if completed else "unknown",
                    "{}" if completed else None,
                    charge if completed else None,
                    "synthetic-request" if completed else None,
                ),
            )
            connection.commit()
        self.primary["state"] = "prepared"
        self.primary["funding"]["phases"] = self.phases()

    def test_four_caps_count_shared_plain_once_and_result_is_detached(self):
        result = self.check()
        self.assertEqual(result["limits"], {"budget_microusd": 150, "max_calls": 16})
        self.assertEqual(len(result["allocations"]), 4)
        self.assertEqual(result["allocations"]["shared_plain_references"]["budget_microusd"], 25)
        self.assertEqual(
            result["totals"],
            dict.fromkeys(
                ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count"), 0
            ),
        )
        result["phases"].clear()
        self.assertEqual(len(self.check()["phases"]), 4)

    def test_invalid_numeric_limits_and_wrong_sums_refuse(self):
        for value in (True, -1, 0, 1.5, "150", 2**63, None, 175):
            for key in ("budget_microusd", "max_calls"):
                with self.subTest(key=key, value=value):
                    limits = self.options["total_limits"] | {key: value}
                    with self.assertRaises(unified_funding.UnifiedFundingError):
                        self.check(total_limits=limits)
        with self.assertRaises(unified_funding.UnifiedFundingError):
            self.check(total_limits={"budget_microusd": 150, "max_calls": 16, "extra": 1})

    def test_wrong_pins_trial_definition_and_unbound_consumers_refuse(self):
        for key in ("expected_launch_sha256", "expected_plan_sha256"):
            with self.subTest(key=key), self.assertRaises(unified_funding.UnifiedFundingError):
                self.check(**{key: "f" * 64})
        for key, value in (("trial", str(self.root / "other")), ("definition_sha256", "f" * 64)):
            original = copy.deepcopy(self.plan)
            self.plan[key] = value
            self.save_plan()
            with self.subTest(key=key), self.assertRaises(unified_funding.UnifiedFundingError):
                self.check()
            self.plan = original
            self.save_plan()
        for path in tuple(self.primary["bindings"]):
            digest = self.primary["bindings"].pop(path)
            with self.subTest(path=path), self.assertRaises(unified_funding.UnifiedFundingError):
                self.check()
            self.primary["bindings"][path] = digest

    def test_both_modes_need_one_grant_and_current_definition_bytes(self):
        self.plan["references"][1]["authorization"] = str(self.root / "second-plain.db")
        self.save_plan()
        with self.assertRaises(unified_funding.UnifiedFundingError):
            self.check()
        self.plan["references"][1]["authorization"] = self.grant["path"]
        self.save_plan()
        Path(self.plan["references"][0]["definition"]).write_bytes(b'{"changed":true}')
        with self.assertRaises(unified_funding.UnifiedFundingError):
            self.check()

    def test_substituted_grant_identity_terms_scope_and_amounts_refuse(self):
        for key, value in (
            ("id", "foreign"),
            ("terms_sha256", "f" * 64),
            ("scope", "foreign"),
            ("budget_microusd", 50),
            ("max_calls", 4),
            ("path", str(self.root / "missing.db")),
            ("budget_microusd", True),
        ):
            with (
                self.subTest(key=key, value=value),
                self.assertRaises(unified_funding.UnifiedFundingError),
            ):
                self.check(reference_grant=self.grant | {key: value})

    def test_protected_roots_and_noncanonical_paths_refuse(self):
        self.primary["protected_roots"].append(str(self.root))
        with self.assertRaises(unified_funding.UnifiedFundingError):
            self.check()
        self.primary["protected_roots"].pop()
        with self.assertRaises(unified_funding.UnifiedFundingError):
            self.check(
                reference_grant=self.grant
                | {"path": str(self.root / "missing" / ".." / "plain.sqlite3")}
            )

    def test_used_raw_funding_cannot_become_a_new_combined_study(self):
        self.operation("shared_plain_references")
        self.primary["state"] = "fresh"
        with self.assertRaises(unified_funding.UnifiedFundingError):
            self.check()

    def test_distinct_files_with_repeated_identity_or_scope_refuse(self):
        for key in ("authorization_id", "scope"):
            with self.subTest(key=key):
                repeated = Authorization.create(
                    self.root / (key + ".db"),
                    authorization_id="shared_plain_references"
                    if key == "authorization_id"
                    else "new-search",
                    scope=self.grant["scope"] if key == "scope" else "new-search-scope",
                    budget_microusd=40,
                    max_calls=4,
                )
                original = self.authorities["search"]
                self.authorities["search"] = repeated
                self.primary["authorizations"]["search"] = str(repeated.path)
                self.primary["funding"]["phases"] = self.phases()
                with self.assertRaises(unified_funding.UnifiedFundingError):
                    self.check()
                self.authorities["search"] = original
                self.primary["authorizations"]["search"] = str(original.path)
                self.primary["funding"]["phases"] = self.phases()

    def test_authority_and_bound_control_changes_during_checking_refuse(self):
        from buddha import launch_common

        finish = launch_common._finish_snapshot
        raw_path = self.authorities["shared_plain_references"].path
        for changed in (raw_path, self.plan_path):
            before, original = files(self.root), changed.read_bytes()

            def injected(path, raw, *, error, changed=changed, original=original):
                if path == raw_path and changed == raw_path:
                    changed.write_bytes(original + b" ")
                finish(path, raw, error=error)
                if path == raw_path and changed == self.plan_path:
                    changed.write_bytes(original + b" ")

            try:
                with (
                    self.subTest(path=changed),
                    passive_only(self),
                    patch(
                        "buddha.improver_launch.check_launch",
                        return_value=copy.deepcopy(self.primary),
                    ),
                    patch("buddha.launch_common._finish_snapshot", side_effect=injected),
                    self.assertRaises(unified_funding.UnifiedFundingError),
                ):
                    unified_funding.check_funding(self.primary_path, **self.options)
            finally:
                changed.write_bytes(original)
            self.assertEqual(files(self.root), before)

    def test_existing_unknown_holds_and_primary_stop_are_preserved_without_owner_claim(self):
        self.operation("shared_plain_references")
        self.primary["stop_code"] = "unknown_operations"
        result = self.check()
        self.assertEqual(result["primary"]["stop_code"], "unknown_operations")
        self.assertEqual(result["totals"]["reserved_microusd"], 7)
        self.assertEqual(result["totals"]["operation_count"], 1)
        self.assertIn("raw original-owner recovery", result["claim"])

    def test_original_spend_and_unknown_liability_sum_once_across_phases(self):
        self.operation("search", completed=True)
        self.operation("shared_plain_references")
        result = self.check()
        self.assertEqual(
            result["totals"],
            {
                "spent_microusd": 3,
                "reserved_microusd": 7,
                "committed_microusd": 10,
                "operation_count": 2,
            },
        )

    def test_changed_primary_observation_and_overrun_refuse(self):
        self.operation("search", completed=True)
        self.primary["funding"]["phases"]["search"]["spent_microusd"] = 0
        with self.assertRaises(unified_funding.UnifiedFundingError):
            self.check()
        self.operation("shared_plain_references", completed=True, charge=26)
        self.primary["funding"]["phases"] = self.phases()
        with self.assertRaises(unified_funding.UnifiedFundingError):
            self.check()

    def test_shared_attempt_overrun_refuses_even_with_zero_additional_cost(self):
        self.operation("shared_plain_references")
        with closing(
            sqlite3.connect(self.authorities["shared_plain_references"].path)
        ) as connection:
            for index in (2, 3):
                connection.execute(
                    "INSERT INTO auth_operations VALUES (?,?,?,?,?,?,?,?)",
                    ("owner", str(index), "0" * 64, 0, "unknown", None, None, None),
                )
            connection.commit()
        with self.assertRaises(unified_funding.UnifiedFundingError):
            self.check()


class UnifiedFundingComposedTests(unittest.TestCase):
    def test_original_primary_checker_and_four_synthetic_grants_compose_readonly(self):
        import test_improver_launch as fixtures

        fixtures.ImproverLaunchTests.setUpClass()
        self.addCleanup(fixtures.ImproverLaunchTests.doClassCleanups)
        original = fixtures.ImproverLaunchTests("runTest")
        self.addCleanup(original.doCleanups)
        original.setUp()
        bundle = original.bundle()
        root = bundle["folder"]
        plan_path, plan = plan_files(root, bundle["directory"], sha(_json(original.definition)))
        pins = {
            str(plan_path): sha(plan_path.read_bytes()),
            **plan["consumer_sources"],
            str(Path(unified_funding.__file__).absolute()): sha(
                Path(unified_funding.__file__).read_bytes()
            ),
        }
        bundle["record"]["source_sha256"].update(pins)
        launch_digest = original.save(bundle)
        raw = Authorization.create(
            root / "plain.sqlite3",
            authorization_id="shared-plain",
            budget_microusd=25,
            max_calls=2,
            scope=unified_funding.reference_scope(sha(plan_path.read_bytes())),
        )
        phases = original.definition["phase_limits"]
        limits = {
            key: sum(row[key] for row in phases.values()) + value
            for key, value in (("budget_microusd", 25), ("max_calls", 2))
        }
        before = files(original.root)
        with (
            passive_only(self),
            patch("os.getenv", side_effect=AssertionError("credential read")),
            patch("os.environ.get", side_effect=AssertionError("credential read")),
        ):
            result = unified_funding.check_funding(
                bundle["path"],
                expected_launch_sha256=launch_digest,
                comparison_plan=plan_path,
                expected_plan_sha256=sha(plan_path.read_bytes()),
                reference_grant=grant_record_from_bytes(raw.path),
                total_limits=limits,
            )
        self.assertEqual(files(original.root), before)
        self.assertEqual(result["primary"]["state"], "fresh")
        self.assertIsNone(result["primary"]["stop_code"])
        self.assertEqual(result["limits"], limits)
        self.assertEqual(
            result["allocations"]["shared_plain_references"],
            {"budget_microusd": 25, "max_calls": 2},
        )
        self.assertFalse(bundle["directory"].exists())
        self.assertFalse(bundle["review_path"].exists())


def grant_record_from_bytes(path):
    from buddha.launch_common import _snapshot

    terms = _snapshot(path)[0]["config"]
    return {
        "path": str(path),
        "id": terms["authorization_id"],
        **{key: terms[key] for key in ("terms_sha256", "scope", "budget_microusd", "max_calls")},
    }
