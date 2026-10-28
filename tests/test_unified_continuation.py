"""Two actual host packages, supplied workers/HTTPS, real original accounting."""

import base64
import copy
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def old_fixture(destination):
    """Run the original preparation in its own real installed package."""
    import test_baseline as raw_fixtures
    import test_improver_launch as primary_fixtures
    from test_plain_comparison_integration import PlainComparisonIntegrationTests
    from test_unified_launch import grant_record

    from buddha import (
        improver_study,
        launch_common,
        plain_comparison,
        source_search,
        unified_funding,
        unified_launch,
    )
    from buddha.authorization import Authorization
    from buddha.releases import _json

    original_temporary = tempfile.TemporaryDirectory
    # The parent owns cleanup. Retain the honest old-process files after exit.
    with patch(
        "tempfile.TemporaryDirectory",
        side_effect=lambda *a, **k: original_temporary(
            *a, **(k | {"dir": destination, "delete": False})
        ),
    ):
        primary_fixtures.ImproverLaunchTests.setUpClass()
        primary = primary_fixtures.ImproverLaunchTests("runTest")
        primary.setUp()
        development = json.loads(Path(primary.definition["development"]["path"]).read_bytes())
        development["starts"] = copy.deepcopy(primary.f.f.starts)
        primary.f.f.recompute_limits(development)
        primary.definition["development"] = primary.f.write(
            "two-start-development.json", development
        )
        analysis = copy.deepcopy(primary.f.plan)
        analysis["counts"]["starts"] = 2
        primary.definition["analysis_plan"] = primary.f.write("two-start-analysis.json", analysis)
        primary.definition["phase_limits"]["search"] = development["limits"]["study"]
        primary.definition["phase_limits"]["final"] = {
            k: 2 * v for k, v in primary.definition["phase_limits"]["final"].items()
        }
        bundle = primary.bundle()
        compatible = type("Compatible", (), {"definition": primary.definition, "f": primary.f.f})()
        raw = {}
        for mode in ("regenerate", "in-context"):
            case = raw_fixtures.BaselineTests("runTest")
            case.setUp()
            PlainComparisonIntegrationTests.match_baseline(case, compatible, mode)
            raw[mode] = case
        plan_path = bundle["folder"] / "plain-plan.json"
        shared_path = bundle["folder"] / "shared-plain.sqlite3"
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
        shared = Authorization.create(
            shared_path,
            authorization_id="fixture-continuation-plain",
            scope=unified_funding.reference_scope(sha(plan_path.read_bytes())),
            budget_microusd=100_000,
            max_calls=100,
        )
        sources = {str(p): sha(p.read_bytes()) for p in (*unified_launch._sources(), plan_path)}
        package = Path(improver_study.__file__).absolute().parent.parent
        sources.update(
            {
                str(package / role): sha((package / role).read_bytes())
                for role in launch_common._UNIFIED_ROLES_V1
            }
        )
        bundle["proposal"]["source_sha256"].update(sources)
        bundle["proposal_path"].write_bytes(_json(bundle["proposal"]))
        bundle["approval"]["proposal_sha256"] = sha(bundle["proposal_path"].read_bytes())
        bundle["record"]["proposal"] = ref(bundle["proposal_path"])
        bundle["record"]["source_sha256"].update(sources)
        primary.save(bundle)
        grants = {name: grant_record(a) for name, a in bundle["authorities"].items()}
        grants["shared_plain_references"] = grant_record(shared)
        outer = {
            "format": "buddha.unified-launch.v1",
            "primary_launch": ref(bundle["path"]),
            "comparison_plan": ref(plan_path),
            "reference_grant": grants["shared_plain_references"],
            "total_limits": {
                k: sum(row[k] for row in grants.values()) for k in ("budget_microusd", "max_calls")
            },
            "directory": str(bundle["folder"] / "unified-workspace"),
            "source_sha256": sources,
        }
        outer_path = bundle["folder"] / "unified.json"
        outer_path.write_bytes(_json(outer))
        primary.prepare(bundle)
        from test_improver_study import ImproverStudyCapacityTests

        ImproverStudyCapacityTests("runTest").fixture(finite_fixture=primary.f.f)
        study = bundle["directory"] / "search/study"
        target = study / "common/0/0/witness"
        original_advance = source_search._advance_witness

        def stop_before_witness(reader, treatment, **kwargs):
            if treatment.to_record()["directory"] == str(target):
                raise KeyboardInterrupt
            return original_advance(reader, treatment, **kwargs)

        with (
            primary.f.supplied(),
            patch.object(source_search, "_advance_witness", side_effect=stop_before_witness),
        ):
            try:
                improver_study.run_improver_study(study, transport=primary.f.f.transport())
            except KeyboardInterrupt:
                pass
        (study / "opaque-unused.bin").write_bytes(b"unused opaque retained evidence")
        reader, state = improver_study._restore(study, bundle["authorities"]["search"].path)
        assert state["action"]["directory"] == target and not target.exists(), {
            "kind": state["action"]["kind"],
            "position": state["action"]["position"],
            "target_present": target.exists(),
        }
        reader.finish()
        grant_paths = {row["path"] for row in grants.values()}
        files = {
            p: {"bytes": Path(p).stat().st_size, "sha256": d}
            for p, d in reader.fingerprints().items()
            if p not in grant_paths
        }
        for p in {
            *state["controls"],
            *(study / name for name in reader.capture.entries if (study / name).is_file()),
        }:
            files[str(p)] = {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
        cut = {
            "format": "buddha.witness-continuation-cut.v1",
            "trial": str(bundle["directory"]),
            "study": str(study),
            "witness": str(target),
            "position": state["action"]["position"],
            "parent": state["action"]["treatment"].to_record()["parent"],
            "attempted": state["attempted"],
            "decisions": len(state["decisions"]),
            "owners": [
                {
                    "directory": str(p),
                    "run_id": reader.owner(p).run_id,
                    "manifest_sha256": reader.owner(p).manifest_sha256,
                    "manifest_raw_sha256": files[str(p / "manifest.json")]["sha256"],
                    "ledger_sha256": reader.owner(p).ledger_sha256,
                }
                for p in sorted(state["owner_paths"])
            ],
            "files": files,
            "entries": sorted(reader.capture.entries),
            "totals": {
                k: state["authorization"][k]
                for k in ("spent_microusd", "reserved_microusd", "operation_count")
            },
        }
        cut_path = bundle["folder"] / "cut.json"
        cut_path.write_bytes(_json(cut))
        destination.joinpath("old.json").write_bytes(
            _json(
                {
                    "original_launch": ref(outer_path),
                    "cut": ref(cut_path),
                    "grants": grants,
                    "source_manifest": ref(bundle["proposal_path"]),
                    "runtime": state["runtime"],
                    "before_controls": {str(p): d for p, d in state["controls"].items()},
                    "base_screen": state["screens"][0].to_record(),
                }
            )
        )


def descriptor(destination):
    from buddha import launch_common, source_screen, unified_continuation
    from buddha.releases import _json

    old = json.loads(destination.joinpath("old.json").read_bytes())
    source = json.loads(Path(old["source_manifest"]["path"]).read_bytes())
    old_package = next(
        Path(p).parent for p in source["source_sha256"] if Path(p).name == "source_screen.py"
    )
    package = Path(unified_continuation.__file__).absolute().parent.parent
    roles = {
        name: {
            "before": {
                "path": str(old_package.parent / name),
                "sha256": source["source_sha256"][str(old_package.parent / name)],
            },
            "after": ref(package / name),
        }
        for name in launch_common._UNIFIED_ROLES_V1
    }
    relation_path = destination / "relation.json"
    relation_path.write_bytes(
        _json(
            {
                "format": "buddha.helper-role-relation.v1",
                "source_manifest": old["source_manifest"],
                "roles": roles,
            }
        )
    )
    record = {
        "format": "buddha.witness-continuation.v1",
        "original_launch": old["original_launch"],
        "cut": old["cut"],
        "helper_relation": ref(relation_path),
        "driver_source": ref(Path(unified_continuation.__file__).absolute()),
        "grants": old["grants"],
        "observation_policy": {
            "format": "buddha.evidence-observation-policy.v2",
            "max_total_bytes": 32 * 1024**3,
            "max_tree_entries": 100_000,
            "max_consumed_paths": 65_536,
            "max_resident_bytes": 0,
        },
        "remaining_phases": [
            "search",
            "freeze",
            "final",
            "plain-regenerate",
            "plain-in-context",
            "comparison",
        ],
    }
    path = destination / "continuation.json"
    path.write_bytes(_json(record))
    assert source_screen.SourceScreen.from_bytes(_json(old["base_screen"]))
    return path


def child(destination, operation):
    from test_gateway import KEY, GatewayTests

    from buddha import unified_continuation as api
    from buddha.executor import ExecutionResult, ExecutorError
    from buddha.gateway import RawHTTPTransport
    from buddha.releases import _json

    path = destination / "continuation.json"
    try:
        checked = api.check_witness_continuation(path, expected_sha256=ref(path)["sha256"])
    except api.WitnessContinuationError as error:
        import traceback

        chain = []
        current = error
        while current is not None and len(chain) < 8:
            chain.append(
                {
                    "type": type(current).__name__,
                    "frames": [
                        [Path(f.filename).name, f.name, f.lineno]
                        for f in traceback.extract_tb(current.__traceback__)
                    ],
                }
            )
            current = current.__context__
        print(json.dumps({"fixture_error_frames": chain}), file=sys.stderr)
        raise
    if operation == "check":
        return checked.summary()
    sends = []
    helper = GatewayTests("runTest")
    value = {
        "source": "# supplied continuation child\nraise RuntimeError('never execute on host')\n",
        "hypothesis": "supplied fixture",
    }

    def worker(spec, *, initial, handle, **kwargs):
        handle(
            {
                "type": "ready",
                "agent_sha256": initial["agent_sha256"],
                "feedback_sha256": sha(_json(initial["feedback"])),
                "runtime_sha256": checked.runtime_sha256,
            }
        )
        request = {
            "type": "request",
            "sequence": 0,
            "provider": "openai",
            "body_base64": base64.b64encode(
                _json(
                    {
                        "model": "test-model",
                        "max_completion_tokens": 100,
                        "messages": [
                            {"role": "user", "content": "same bounded continuation operation"}
                        ],
                    }
                )
            ).decode(),
        }
        connection = helper.connection(
            helper.response(choices=[{"message": {"content": _json(value).decode()}}])
        )
        with patch("http.client.HTTPSConnection", return_value=connection):
            handle(request)
        sends.append(connection.request.call_count)
        if operation == "interrupt":
            raise ExecutorError(
                "supplied interruption after durable reply",
                cleanup_status="removed",
                container_id="f" * 64,
            )
        handle(
            {
                "type": "done",
                "status": "complete",
                "reason": "complete",
                "proposal": {
                    "status": "captured",
                    "value": value,
                    "sha256": sha(_json(value)),
                    "bytes": len(_json(value)),
                },
            }
        )
        return ExecutionResult(
            0,
            "f" * 64,
            spec.image_id,
            0,
            0,
            sha(b""),
            1,
            0.01,
            _json({"fixture": "supplied worker"}),
            "removed",
        )

    with (
        patch.dict(os.environ, {"OPENAI_API_KEY": KEY}),
        patch("buddha.executor.run_container", side_effect=worker),
        patch("http.client.HTTPSConnection", side_effect=AssertionError("unsupplied HTTPS")),
    ):
        try:
            result = api.advance_witness(checked, transport=RawHTTPTransport(allow_paid=True))
        except Exception as error:
            import traceback

            current, chain = error, []
            while current is not None and len(chain) < 8:
                chain.append(
                    {
                        "type": type(current).__name__,
                        "frames": [
                            [Path(f.filename).name, f.name, f.lineno]
                            for f in traceback.extract_tb(current.__traceback__)
                        ],
                    }
                )
                current = current.__context__
            print(json.dumps({"fixture_advance_error_frames": chain}), file=sys.stderr)
            raise
    from buddha.doctor import _Capture, _owner

    capture = _Capture(checked.study)
    owner = _owner(capture, checked.witness / "proposal/owners/0")
    capture.finish()
    return {
        "result": {k: result[k] for k in ("action", "role")},
        "sends": sends,
        "summary": checked.summary(),
        "owner_id": owner.run_id,
        "operation_ids": [op.operation_id for op in owner.operations],
        "manifest_raw_sha256": sha((owner.directory / "manifest.json").read_bytes()),
        "accounting": owner.accounting(),
    }


class UnifiedContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.project = Path(__file__).absolute().parents[1]
        cls.old = cls.root / "old-host"
        shutil.copytree(
            cls.project / "buddha", cls.old / "buddha", ignore=shutil.ignore_patterns("__pycache__")
        )
        shutil.copytree(
            cls.project / "tests", cls.old / "tests", ignore=shutil.ignore_patterns("__pycache__")
        )
        shutil.copytree(cls.project / "docs/conformance", cls.old / "docs/conformance")
        (cls.old / "agents").mkdir()
        shutil.copyfile(cls.project / "agents/frozen_seed.py", cls.old / "agents/frozen_seed.py")
        with (cls.old / "buddha/doctor.py").open("ab") as stream:
            stream.write(b"\n# Literal old-process fixture source identity.\n")
        cls.payload = cls.root / "payload"
        cls.payload.mkdir()
        cls.run_child("old", old=True)
        cls.path = descriptor(cls.payload)

    @classmethod
    def run_child(cls, operation, *, old=False):
        environment = {
            k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        }
        package = cls.old if old else cls.project
        environment["PYTHONPATH"] = os.pathsep.join((str(package), str(package / "tests")))
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(Path(__file__).absolute()),
                "--fixture",
                str(cls.payload),
                operation,
                str(package),
            ],
            cwd=package,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return json.loads(result.stdout.splitlines()[-1])

    def test_two_actual_packages_replay_old_then_resume_one_new_owner_operation(self):
        importlib.import_module("buddha.unified_continuation")
        descriptor(self.payload)
        checked = self.run_child("check")
        self.assertGreater(checked["old_owner_count"], 0)
        self.assertTrue(checked["all_old_owners_inactive"])
        self.assertEqual(self.run_child("prepare")["result"]["action"], "prepared")
        interrupted = self.run_child("interrupt")
        self.assertEqual(interrupted["sends"], [1])
        resumed = self.run_child("resume")
        self.assertEqual(resumed["sends"], [0])
        self.assertEqual(resumed["result"]["action"], "executed")
        self.assertEqual(resumed["owner_id"], interrupted["owner_id"])
        self.assertEqual(resumed["operation_ids"], interrupted["operation_ids"])
        self.assertEqual(len(resumed["operation_ids"]), 1)
        self.assertEqual(resumed["manifest_raw_sha256"], interrupted["manifest_raw_sha256"])
        self.assertEqual(resumed["accounting"], interrupted["accounting"])
        self.assertEqual(resumed["summary"]["old_owner_count"], checked["old_owner_count"])
        from buddha import improver_study
        from buddha.releases import ReleaseError

        old = json.loads((self.payload / "old.json").read_bytes())
        cut = json.loads(Path(old["cut"]["path"]).read_bytes())
        with self.assertRaises(ReleaseError):
            improver_study._restore(Path(cut["study"]), Path(old["grants"]["search"]["path"]))

    def test_rejections_and_late_drift_leave_originals_and_new_witness_untouched(self):
        from contextlib import contextmanager

        from buddha import native_pipeline
        from buddha import unified_continuation as api
        from buddha.doctor import _Capture
        from buddha.gateway import RawHTTPTransport
        from buddha.releases import _json

        original = self.path.read_bytes()
        record = json.loads(original)
        cut_path = Path(record["cut"]["path"])
        cut_raw = cut_path.read_bytes()
        cut = json.loads(cut_raw)
        trial, witness = Path(cut["trial"]), Path(cut["witness"])

        def files():
            return {
                str(p.relative_to(trial)): sha(p.read_bytes())
                for p in trial.rglob("*")
                if p.is_file()
            }

        initial = files()
        with (
            patch("buddha.executor.run_container", side_effect=AssertionError("worker forbidden")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("network forbidden")),
        ):
            bad_records = []
            for key, value in (
                ("extra", True),
                ("driver_source", record["driver_source"] | {"sha256": "f" * 64}),
                ("observation_policy", record["observation_policy"] | {"max_total_bytes": True}),
            ):
                bad_records.append(record | {key: value})
            wrong_grant = copy.deepcopy(record)
            wrong_grant["grants"]["search"]["budget_microusd"] += 1
            bad_records.append(wrong_grant)
            for changed in bad_records:
                try:
                    self.path.write_bytes(_json(changed))
                    with self.assertRaises(api.WitnessContinuationError):
                        api.check_witness_continuation(
                            self.path, expected_sha256=sha(self.path.read_bytes())
                        )
                finally:
                    self.path.write_bytes(original)
            for key in ("cut", "helper_relation"):
                misplaced = trial / ("misplaced-" + key + ".json")
                try:
                    misplaced.write_bytes(Path(record[key]["path"]).read_bytes())
                    self.path.write_bytes(_json(record | {key: ref(misplaced)}))
                    injected = files()
                    with self.assertRaises(api.WitnessContinuationError):
                        api.check_witness_continuation(
                            self.path, expected_sha256=sha(self.path.read_bytes())
                        )
                    self.assertEqual(files(), injected)
                finally:
                    misplaced.unlink(missing_ok=True)
                    self.path.write_bytes(original)
            changes = [
                cut | {"witness": str(witness.with_name("WITNESS"))},
                cut | {"position": cut["position"] | {"start": 1}},
                cut | {"owners": cut["owners"] + [cut["owners"][0]]},
            ]
            missing = copy.deepcopy(cut)
            opaque = trial / "search/study/opaque-unused.bin"
            del missing["files"][str(opaque)]
            changes.append(missing)
            bad_receipt = copy.deepcopy(cut)
            bad_receipt["owners"][0]["manifest_raw_sha256"] = "f" * 64
            changes.append(bad_receipt)
            oversized = copy.deepcopy(cut)
            oversized["files"][str(opaque)]["bytes"] = 64 * 1024**2 + 1
            changes.append(oversized)
            genuine_read = _Capture.read
            for changed in changes:
                try:
                    cut_path.write_bytes(_json(changed))
                    self.path.write_bytes(_json(record | {"cut": ref(cut_path)}))

                    def no_oversized_read(capture, path, maximum=32 * 1024**2, *, changed=changed):
                        if changed is oversized and path == opaque:
                            raise AssertionError("oversized metadata reached file read")
                        return genuine_read(capture, path, maximum)

                    with (
                        patch.object(_Capture, "read", no_oversized_read),
                        self.assertRaises(api.WitnessContinuationError),
                    ):
                        api.check_witness_continuation(
                            self.path, expected_sha256=sha(self.path.read_bytes())
                        )
                finally:
                    cut_path.write_bytes(cut_raw)
                    self.path.write_bytes(original)
            # Unit-injected observations, distinct from the real ledger proof.
            real_snapshot = api.common._snapshot
            for condition in ("unknown", "active"):

                def observed(path, *, condition=condition):
                    value, raw = real_snapshot(path)
                    value = copy.deepcopy(value)
                    if str(path) == record["grants"]["search"]["path"]:
                        if condition == "unknown":
                            value["auth_operations"].append({"status": "unknown"})
                        else:
                            value["auth_deactivations"] = []
                    return value, raw

                with (
                    patch.object(api.common, "_snapshot", side_effect=observed),
                    self.assertRaises(api.WitnessContinuationError),
                ):
                    api.check_witness_continuation(self.path, expected_sha256=sha(original))
            checked = api.check_witness_continuation(self.path, expected_sha256=sha(original))
            from concurrent.futures import ThreadPoolExecutor
            from contextvars import copy_context

            from buddha import launch_common, source_screen

            old = json.loads((self.payload / "old.json").read_bytes())
            screen = source_screen.SourceScreen.from_bytes(_json(old["base_screen"]))
            before = dict(checked._before)
            self.assertEqual(
                launch_common._continued_witness_controls(
                    checked.study, checked.witness, screen, before
                ),
                before,
            )
            with checked._scope():
                with self.assertRaises(api.WitnessContinuationError):
                    launch_common._continued_witness_controls(
                        trial / "other", checked.witness, screen, before
                    )
                with self.assertRaises(api.WitnessContinuationError):
                    launch_common._continued_witness_parent_controls(
                        checked.study,
                        checked.witness,
                        screen,
                        dict(checked._after),
                        trial / "wrong-parent",
                    )
                inherited = copy_context()
                with (
                    ThreadPoolExecutor(max_workers=1) as pool,
                    self.assertRaises(api.WitnessContinuationError),
                ):
                    pool.submit(
                        inherited.run,
                        launch_common._continued_witness_controls,
                        checked.study,
                        checked.witness,
                        screen,
                        before,
                    ).result()
            owner_manifest = Path(cut["owners"][0]["directory"]) / "manifest.json"
            owner_raw = owner_manifest.read_bytes()
            exclusive = native_pipeline._exclusive

            @contextmanager
            def late(path):
                with exclusive(path):
                    owner_manifest.write_bytes(owner_raw + b" ")
                    try:
                        yield
                    finally:
                        owner_manifest.write_bytes(owner_raw)

            with (
                patch.object(native_pipeline, "_exclusive", side_effect=late),
                self.assertRaises(api.WitnessContinuationError),
            ):
                api.advance_witness(checked, transport=RawHTTPTransport(allow_paid=True))
            in_lease = [False]

            @contextmanager
            def grant_window(path):
                with exclusive(path):
                    in_lease[0] = True
                    try:
                        yield
                    finally:
                        in_lease[0] = False

            def changed_grant(path):
                value, raw = real_snapshot(path)
                if in_lease[0] and str(path) == record["grants"]["shared_plain_references"]["path"]:
                    raw += b"late different snapshot"
                return value, raw

            with (
                patch.object(native_pipeline, "_exclusive", side_effect=grant_window),
                patch.object(api.common, "_snapshot", side_effect=changed_grant),
                self.assertRaises(api.WitnessContinuationError),
            ):
                api.advance_witness(checked, transport=RawHTTPTransport(allow_paid=True))
        self.assertEqual(files(), initial)
        self.assertFalse(witness.exists())

    def test_late_directory_kind_change_is_rejected_before_dispatch(self):
        from buddha import native_pipeline, trial_fence
        from buddha import unified_continuation as api
        from buddha.authorization import Authorization

        prepared = api._checked_state(self.path, sha(self.path.read_bytes()))
        authority = Authorization(prepared.search_grant)
        empty = prepared.trial / "validation"
        with (
            prepared.checked._scope(),
            trial_fence.work(
                prepared.search_grant,
                authority._terms(),
                directory=prepared.checked.study,
                kind="search",
            ),
            native_pipeline._exclusive(prepared.checked.study),
        ):
            empty.rmdir()
            empty.write_bytes(b"same name; wrong filesystem kind")
            try:
                with self.assertRaises(api.WitnessContinuationError):
                    prepared.after_locks()
            finally:
                empty.unlink()
                empty.mkdir()


class WitnessContinuationMetadataTests(unittest.TestCase):
    def test_context_retains_lineage_pin_and_excludes_it_from_external_comparison(self):
        from test_helper_role_relation import HelperRoleRelationTests

        from buddha import source_screen
        from buddha import unified_continuation as api
        from buddha.releases import _json

        fixture = HelperRoleRelationTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        bundle = fixture.bundle()
        record = fixture.screen.to_record()
        lineage = fixture.root / "lineage.json"
        record["lineage"] = {"path": str(lineage), "sha256": "a" * 64}
        screen = source_screen.SourceScreen.from_bytes(_json(record))
        pins = bundle["before_controls"] | {lineage: "a" * 64}
        context = api._context(screen, pins, fixture.before_roles)
        source_screen._comparison_controls(context, pins, screen)
        self.assertEqual(context["controls"][str(lineage)], "a" * 64)
        self.assertNotIn(str(lineage), context["comparison_controls"]["external"])
        from buddha import launch_common

        checked = api.CheckedWitnessContinuation(
            fixture.root / "outer.json",
            "b" * 64,
            fixture.root / "study",
            fixture.root / "study/cells/0/0/0/0/witness",
            fixture.root / "study/cells/0/0/0/0/screen",
            record["generation"]["runtime"]["sha256"],
            tuple(bundle["before_controls"].items()),
            tuple(bundle["after_controls"].items()),
            fixture.screen.fingerprint(),
            _json(
                {
                    "format": "buddha.evidence-observation-policy.v1",
                    "max_total_bytes": 1024**3,
                    "max_resident_bytes": 0,
                }
            ),
            b"{}",
            os.getpid(),
            __import__("threading").get_ident(),
        )
        with checked._scope():
            self.assertEqual(
                launch_common._continued_witness_parent_controls(
                    checked.study,
                    checked.witness,
                    fixture.screen,
                    dict(checked._after),
                    checked._parent,
                ),
                dict(checked._before),
            )
            with self.assertRaises(api.WitnessContinuationError):
                launch_common._continued_witness_parent_controls(
                    checked.study, checked.witness, screen, dict(checked._after), checked._parent
                )

    def test_late_anchor_size_and_public_error_normalization_are_bounded(self):
        from buddha import unified_continuation as api
        from buddha.doctor import _Busy, _Capture, _Unsupported

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "search/study").mkdir(parents=True)
            opaque = root / "opaque.bin"
            opaque.write_bytes(b"small")
            entries = frozenset({"search", "search/study", "opaque.bin"})
            (root / ".trial-running.lock").write_text("owned", encoding="ascii")
            (root / "search/study/running.lock").write_text("owned", encoding="ascii")
            snapshot = api._CheckedState(
                None,
                root,
                root / "grant",
                {},
                ((opaque, 64 * 1024**2 + 1, "a" * 64),),
                frozenset(),
                frozenset(),
                entries,
                frozenset({"search", "search/study"}),
                (),
            )
            with (
                patch.object(_Capture, "read", side_effect=AssertionError("oversized late read")),
                self.assertRaises(ValueError),
            ):
                snapshot.after_locks()
            for error in (
                _Busy("untrusted secret canary"),
                _Unsupported("untrusted secret canary"),
            ):
                with (
                    patch.object(api, "_check", side_effect=error),
                    self.assertRaises(api.WitnessContinuationError) as caught,
                ):
                    api.check_witness_continuation(root / "unused.json", expected_sha256="a" * 64)
                self.assertNotIn("canary", str(caught.exception))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fixture":
        target, action, source = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
        sys.path[:1] = [str(source / "tests"), str(source)]
        if action == "old":
            old_fixture(target)
            print(json.dumps({"status": "old_cut_ready"}))
        else:
            print(json.dumps(child(target, action)))
    else:
        unittest.main()
