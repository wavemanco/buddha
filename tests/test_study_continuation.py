"""Development-only continuation across real package roots and retained history.

Every subprocess advances one ordinary action under its original search grant.
Workers and HTTPS replies are supplied; no selected Python, real provider or
container runs. The old cut, source identities and all ordinary stage seals are
real. Final assessment and plain references remain untouched.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def workers(metadata, *, interrupt_role=None):
    """Vary supplied source by owner, preserving identical retry replies."""
    import test_cell_witness_continuation as cell
    import test_improver_study as improver

    literal_source = improver.source
    study = Path(metadata["study"])

    def source_for_owner(label):
        owner = Path(trace[-1]["owner"]).relative_to(study).as_posix()
        return literal_source(label + "-" + sha(owner.encode())[:12])

    with (
        patch.object(improver, "source", side_effect=source_for_owner),
        cell.supplied_workers(metadata["runtime"], interrupt_role=interrupt_role) as (
            sends,
            trace,
        ),
    ):
        yield sends, trace


def old_step(destination):
    """Perform one original scheduled action, stopping at the last slot-zero witness."""
    from test_unified_continuation import save_cut

    from buddha import (
        candidate_improvement,
        improver_study,
        source_screen,
        source_search,
        trial_fence,
    )
    from buddha import native_pipeline as pipeline
    from buddha.authorization import Authorization
    from buddha.gateway import RawHTTPTransport
    from buddha.releases import _json

    metadata = json.loads((destination / "old-bootstrap.json").read_bytes())
    study = Path(metadata["study"])
    target = study / "cells/0/0/1/0/witness"
    authority = Authorization(Path(metadata["grants"]["search"]["path"]))
    at_cut = False
    with (
        workers(metadata) as (sends, trace),
        trial_fence.work(authority.path, authority._terms(), directory=study, kind="search"),
        pipeline._exclusive(study),
    ):
        reader, state = improver_study._restore(study, authority.path)
        improver_study._check_current(state)
        reader.finish()
        action = state["action"]
        kind, location = action["kind"], action["directory"]
        result = None
        transport = RawHTTPTransport(allow_paid=True)
        if kind == "witness" and location == target:
            at_cut = True
        elif kind == "screen":
            result = source_screen.run_source_screen(location, transport=transport)
        elif kind == "witness":
            result = source_search._advance_witness(
                reader, action["treatment"], authorization=authority, transport=transport
            )
        elif kind == "plan":
            improver_study._write_plan(study, state, action, authority.path)
        elif kind == "prepare_proposal":
            improver_study._prepare_proposal(state, action, authority)
        elif kind == "proposal":
            result = candidate_improvement.run_candidate_improvement(location, transport=transport)
        elif kind == "proposal_capacity":
            source_search._publish_capacity(
                study,
                authority.path,
                location,
                state["record"]["proposal_capacity"],
                child_directory=location / "screen",
            )
        elif kind == "prepare_child":
            source_search._materialize_child_source_for(
                state["screens"][action["position"]["start"]],
                action["proposal"],
                location,
                owner_directory=location / "screen",
                source_copy=True,
            )
            source_screen.prepare_source_screen(
                location / "screen",
                screen=action["child"],
                authorization=authority,
                review=state["review"],
                expected_runtime_sha256=state["runtime"],
                input_bindings=state["controls"],
            )
        elif kind == "decision":
            pipeline._same_or_write(location / "decision.json", _json(action["decision"]))
        else:
            raise AssertionError("unexpected old action " + kind)
        if result is not None:
            assert result.get("status") != "incomplete" and result.get("action") != "incomplete", (
                result
            )
    if at_cut:
        save_cut(destination, metadata, target)
    return {
        "at_cut": at_cut,
        "action": kind,
        "position": action["position"],
        "sends": sends,
        "roles": [r["role"] for r in trace],
    }


def descriptor(destination):
    from test_unified_continuation import descriptor as witness_descriptor

    from buddha.releases import _json

    path = witness_descriptor(destination)
    record = json.loads(path.read_bytes())
    record["format"] = "buddha.study-continuation.v1"
    record["remaining_phases"] = ["search", "freeze", "publication"]
    path.write_bytes(_json(record))
    return path


def files(root):
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in root.rglob("*") if p.is_file()}


def metadata_negatives(destination, metadata, path):
    """Reject wrong scope and test-owned bad evidence before any worker or send."""
    from buddha import unified_continuation as api
    from buddha.releases import _json

    record_raw = path.read_bytes()
    record = json.loads(record_raw)
    relation_path = Path(record["helper_relation"]["path"])
    relation_raw = relation_path.read_bytes()
    trial = Path(json.loads(Path(metadata["cut"]["path"]).read_bytes())["trial"])
    study = Path(metadata["study"])
    before = files(trial)
    rejected = []

    def reject(name, function):
        try:
            function()
        except api.WitnessContinuationError:
            rejected.append(name)
        else:
            raise AssertionError("continuation accepted " + name)

    with (
        patch(
            "buddha.executor.run_container", side_effect=AssertionError("worker forbidden")
        ) as worker,
        patch(
            "http.client.HTTPSConnection", side_effect=AssertionError("network forbidden")
        ) as network,
    ):
        reject(
            "study descriptor in witness-only API",
            lambda: api.check_witness_continuation(path, expected_sha256=sha(record_raw)),
        )
        changed = json.loads(relation_raw)
        changed["roles"]["buddha/doctor.py"]["after"]["sha256"] = "f" * 64
        try:
            relation_path.write_bytes(_json(changed))
            path.write_bytes(
                _json(
                    record
                    | {
                        "helper_relation": {
                            "path": str(relation_path),
                            "sha256": sha(_json(changed)),
                        }
                    }
                )
            )
            reject(
                "changed actual after-helper pin",
                lambda: api.check_study_continuation(path, expected_sha256=sha(path.read_bytes())),
            )
        finally:
            relation_path.write_bytes(relation_raw)
            path.write_bytes(record_raw)
        premature = study / "cells/0/0/0/2"
        assert not premature.exists() and premature.is_relative_to(destination)
        try:
            injected = premature / "proposal/owners/0/manifest.json"
            injected.parent.mkdir(parents=True)
            injected.write_bytes(b"{}")
            retained = files(trial)
            reject(
                "out-of-grid owner",
                lambda: api.check_study_continuation(path, expected_sha256=sha(record_raw)),
            )
            assert files(trial) == retained
        finally:
            shutil.rmtree(premature)
        assert worker.call_count == 0 and network.call_count == 0
    assert files(trial) == before
    return {"rejected": rejected, "worker_calls": 0, "send_calls": 0}


def selection_audit(checked):
    """Reconstruct the frozen rule over real C references in its checked scope."""
    from buddha import improver_study, source_screen

    with checked._scope():
        reader, state = improver_study._restore(checked.study, checked._authorization)
        settings = state["record"]["selection"]
        selections = []
        for arm in (0, 1):
            decisions = state["cell_decisions"][(0, 0, arm)]
            references = [row["screen"] for row in decisions if row["status"] == "admitted"]
            selected = source_screen.select_source_parent(
                references,
                method=settings["method"],
                max_active=settings["max_active"],
                seed=settings["seed"],
                iteration=settings["finalist_iteration"],
            )
            selections.append({"arm": arm, "selection": selected})
        reader.finish()
    return {"selections": selections}


def new_step(destination, operation):
    from buddha import unified_continuation as api
    from buddha.doctor import _Capture, _owner
    from buddha.gateway import RawHTTPTransport

    metadata = json.loads((destination / "old.json").read_bytes())
    path = destination / "continuation.json"
    checked = api.check_study_continuation(path, expected_sha256=sha(path.read_bytes()))
    if operation == "check":
        return checked.summary()
    if operation == "negatives":
        return metadata_negatives(destination, metadata, path)
    if operation == "audit":
        return selection_audit(checked)
    study = Path(metadata["study"])
    cut = json.loads(Path(metadata["cut"]["path"]).read_bytes())
    interrupt = operation.removeprefix("interrupt-") if operation.startswith("interrupt-") else None
    complete = checked.summary()["study_complete"]
    if operation == "replay":
        assert complete
    if complete and operation in {"step", "replay"}:
        assert not any(os.environ.get(name) for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"))
        with (
            patch(
                "buddha.executor.run_container", side_effect=AssertionError("worker forbidden")
            ) as worker,
            patch(
                "http.client.HTTPSConnection", side_effect=AssertionError("network forbidden")
            ) as network,
        ):
            result = api.advance_study(checked, transport=RawHTTPTransport(allow_paid=True))
            assert worker.call_count == 0 and network.call_count == 0
        sends, trace = [], []
    else:
        with workers(metadata, interrupt_role=interrupt) as (sends, trace):
            result = api.advance_study(checked, transport=RawHTTPTransport(allow_paid=True))
    capture = _Capture(study)
    owners = {}
    for role in ("proposal", "generation"):
        path = Path(cut["witness"]) / role / "owners/0"
        if path.exists():
            owner = _owner(capture, path)
            owners[role] = {
                "run_id": owner.run_id,
                "manifest_raw_sha256": sha((path / "manifest.json").read_bytes()),
                "operation_ids": [op.operation_id for op in owner.operations],
                "accounting": owner.accounting(),
            }
    capture.finish()
    nested = result.get("result")
    return {
        "action": result["action"],
        "role": result.get("role"),
        "sends": sends,
        "roles": [r["role"] for r in trace],
        "owners": owners,
        "result_status": nested.get("status") if isinstance(nested, dict) else None,
        "published": (study / "report.json").exists(),
    }


class StudyContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.project = Path(__file__).absolute().parents[1]
        cls.old = cls.root / "old-host"
        for name in ("buddha", "tests", "docs/conformance"):
            shutil.copytree(
                cls.project / name, cls.old / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        (cls.old / "agents").mkdir()
        shutil.copyfile(cls.project / "agents/frozen_seed.py", cls.old / "agents/frozen_seed.py")
        with (cls.old / "buddha/doctor.py").open("ab") as stream:
            stream.write(b"\n# Literal original development-process source identity.\n")
        cls.payload = cls.root / "payload"
        cls.payload.mkdir()
        cls.run_child("old-setup", old=True)

    @classmethod
    def run_child(cls, operation, *, old=False):
        source = cls.old if old else cls.project
        environment = {
            k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        }
        environment["PYTHONPATH"] = os.pathsep.join((str(source), str(source / "tests")))
        started = time.monotonic()
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(Path(__file__).absolute()),
                "--fixture",
                str(cls.payload),
                operation,
                str(source),
            ],
            cwd=source,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        value = json.loads(result.stdout.splitlines()[-1])
        value["process_seconds"] = time.monotonic() - started
        return value

    def checked_action(self, operation, *, old=False, index):
        step = self.run_child(operation, old=old)
        with self.subTest(source="original" if old else "continued", action=index):
            self.assertIn(
                step["action"],
                {
                    "screen",
                    "witness",
                    "plan",
                    "prepare_proposal",
                    "proposal",
                    "proposal_capacity",
                    "prepare_child",
                    "decision",
                    "freeze",
                    "publish",
                    "complete",
                },
            )
            self.assertTrue(all(type(count) is int and count in (0, 1) for count in step["sends"]))
            self.assertTrue(
                all(
                    role in {"proposal", "generation", "native-0", "native-1", "native-2"}
                    for role in step["roles"]
                )
            )
            self.assertIs(type(step["at_cut"] if old else step["published"]), bool)
        return step

    def test_retained_last_slot_zero_cut_reaches_complete_development_and_replays_keylessly(self):
        for index in range(48):
            step = self.checked_action("old-step", old=True, index=index)
            print(
                f"[study fixture] old action {index + 1}: {step['action']}; "
                f"at cut {step['at_cut']}",
                flush=True,
            )
            if step["at_cut"]:
                break
        else:
            self.fail("bounded old fixture did not reach the last slot-zero cut")
        self.path = descriptor(self.payload)
        old = json.loads((self.payload / "old.json").read_bytes())
        cut = json.loads(Path(old["cut"]["path"]).read_bytes())
        study, trial = Path(cut["study"]), Path(cut["trial"])
        self.assertEqual(
            cut["position"],
            {"start": 0, "repetition": 0, "arm": 1, "slot": 0, "stage": "witness_feedback"},
        )
        self.assertEqual(len(cut["owners"]), 18)
        self.assertEqual(cut["decisions"], 1)
        parent = json.loads((Path(cut["parent"]["directory"]) / "screen.json").read_bytes())
        self.assertIsNotNone(parent["lineage"])
        self.run_child("check")
        negative = self.run_child("negatives")
        self.assertEqual(len(negative["rejected"]), 3)
        self.assertEqual((negative["worker_calls"], negative["send_calls"]), (0, 0))
        first = self.checked_action("step", index="cut preparation")
        self.assertEqual(first["sends"], [])
        interrupted = self.checked_action("interrupt-proposal", index="cut interruption")
        resumed = self.checked_action("step", index="cut replay")
        self.assertEqual(interrupted["sends"], [1])
        self.assertEqual(resumed["sends"], [0])
        self.assertEqual(interrupted["owners"]["proposal"], resumed["owners"]["proposal"])
        steps = [first, interrupted, resumed]
        for index in range(48):
            step = self.checked_action("step", index=index)
            steps.append(step)
            print(
                f"[study fixture] new action {index + 1}: {step['action']}; "
                f"published {step['published']}",
                flush=True,
            )
            if step["published"]:
                break
        else:
            raise AssertionError("bounded continuation did not publish complete development")
        report_path = study / "report.json"
        report = json.loads(report_path.read_bytes())
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["coverage"]["completed_opportunities"], 4)
        self.assertEqual(len(report["decisions"]), 4)
        self.assertEqual(len(report["selections"]), 2)
        audited = self.run_child("audit")["selections"]
        for arm in (0, 1):
            profiles = []
            for slot in (0, 1):
                location = study / "cells/0/0" / str(arm) / str(slot)
                decision = json.loads((location / "decision.json").read_bytes())
                self.assertEqual(decision["status"], "admitted")
                self.assertEqual(
                    json.loads((location / "witness/report.json").read_bytes())["status"], "passed"
                )
                profiles.append(
                    json.loads((location / "screen/report.json").read_bytes())["controls_sha256"]
                )
            self.assertNotEqual(
                profiles[0],
                profiles[1],
                "Actual old/new measurement identities must remain different",
            )
            selected = next(row for row in report["selections"] if row["arm"] == arm)
            self.assertEqual(selected["status"], "selected")
            recomputed = next(row["selection"] for row in audited if row["arm"] == arm)
            self.assertEqual(recomputed["format"], "buddha.source-parent-selection.v2")
            self.assertIn("host_control_relation", recomputed)
            self.assertEqual(len(recomputed["control_profiles"]), 2)
            self.assertEqual(
                [row["controls_sha256"] for row in recomputed["control_profiles"]], profiles
            )
            self.assertEqual(recomputed["selected_id"], selected["candidate_id"])
            self.assertEqual(
                sha(Path(selected["source"]["path"]).read_bytes()), selected["source"]["sha256"]
            )
            origin = Path(selected["origin"]["screen"]["directory"])
            original_source = json.loads((origin / "screen.json").read_bytes())["generation"][
                "roots"
            ]["agent"]
            self.assertEqual(
                sha((Path(original_source) / "candidate.py").read_bytes()),
                selected["source"]["sha256"],
            )
            slot_one = study / "cells/0/0" / str(arm) / "1"
            plan = json.loads((slot_one / "plan.json").read_bytes())
            self.assertEqual(plan["selection"]["format"], "buddha.source-parent-selection.v1")
            self.assertNotIn("host_control_relation", plan["selection"])
            self.assertNotIn("control_profiles", plan["selection"])
            for packet in (slot_one / "feedback").glob("*.json"):
                self.assertNotIn('"host_control_relation"', packet.read_text())
        for name, record in cut["files"].items():
            self.assertEqual(sha(Path(name).read_bytes()), record["sha256"])
        before = {
            str(p.relative_to(trial)): sha(p.read_bytes()) for p in trial.rglob("*") if p.is_file()
        }
        self.run_child("check")
        replay = self.run_child("replay")
        self.assertEqual(replay["action"], "complete")
        self.assertEqual(replay["sends"], [])
        self.assertEqual(replay["roles"], [])
        self.assertEqual(
            {
                str(p.relative_to(trial)): sha(p.read_bytes())
                for p in trial.rglob("*")
                if p.is_file()
            },
            before,
        )
        self.assertFalse((trial / "freeze").exists())
        self.assertEqual(list((trial / "final").iterdir()), [])
        plan = json.loads(
            Path(
                json.loads(Path(old["original_launch"]["path"]).read_bytes())["comparison_plan"][
                    "path"
                ]
            ).read_bytes()
        )
        self.assertTrue(all(not Path(row["directory"]).exists() for row in plan["references"]))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fixture":
        destination, operation, source = Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
        sys.path[:1] = [str(source / "tests"), str(source)]
        if operation == "old-setup":
            from test_unified_continuation import old_fixture

            old_fixture(destination, setup_only=True, starting_count=1, opportunities=2)
            result = {"status": "old_setup_ready"}
        elif operation == "old-step":
            result = old_step(destination)
        else:
            result = new_step(destination, operation)
        print(json.dumps(result), flush=True)
    else:
        unittest.main()
