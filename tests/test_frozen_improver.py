"""Frozen improvers receive common measured parents and complete feedback.

Six methods reuse one existing measured-packet fixture per method. Trusted worker
dispatch is exercised with only its selected-source loader intercepted; neither
the selected improver bytes nor returned source execute on the host. All HTTPS
replies and executor results are supplied fixtures, not confinement/model evidence.
"""

import base64
import copy
import hashlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, sentinel


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def files(root):
    return {
        path.relative_to(root).as_posix(): sha(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    }


class FrozenImproverTests(unittest.TestCase):
    def fixture(self):
        import test_candidate_improvement_stage
        import test_source_feedback

        from buddha.answers import TaskSet

        fixture = test_candidate_improvement_stage.CandidateImprovementStageTests("runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.api()

        def long_literal_measurements(feedback):
            screen = feedback.h.screen()
            feedback.h.programs[screen.candidate_id]["answers"] = [
                "BEGIN_LITERAL\n" + "雪α full text  \n" * 500,
                "END",
            ]
            directory, authority = feedback.h.prepare(screen)
            self.assertEqual(feedback.h.run_screen(directory)["status"], "complete")
            return directory, authority, feedback.h.reference(directory, authority)

        # Changes supplied generated answer data, not the measured-custody reader.
        with patch.object(
            test_source_feedback.SourceFeedbackTests,
            "completed",
            long_literal_measurements,
        ):
            fixture.fixture()
        self.f = fixture
        self.parent_selection = fixture.selection.to_record()
        self.parent_roots = dict(fixture.roots)
        self.parent_path = fixture.roots["agent"] / fixture.record["entrypoint"]
        self.parent_raw = self.parent_path.read_bytes()
        self.parent_id = fixture.selection.agent_sha256
        self.base_recipe = copy.deepcopy(fixture.record)
        packet = json.loads((fixture.packet / "feedback.json").read_bytes())
        self.assertEqual(packet["format"], "buddha.candidate-development-feedback.v2")
        source = TaskSet.from_bytes((fixture.packet / "source.json").read_bytes())
        tasks = {task.id: task for task in source.tasks}
        self.projected = [
            {"task": tasks[row["task_id"]].to_record(), "note": row["note"]}
            for row in packet["records"]
        ]
        self.assertTrue(any(len(row["note"].encode()) > 4096 for row in self.projected))
        self.common_files = {
            path: path.read_bytes()
            for path in [self.parent_path, *fixture.packet.iterdir()]
            if path.is_file()
        }
        self.observed = []
        self.connections = []
        return fixture

    @staticmethod
    def operator_source(name):
        return (
            "# frozen supplied operator: " + name + "\n"
            "def generate(task, config, complete): return []\n"
            "def propose_improvement(parent, feedback, config, complete):\n"
            "    raise RuntimeError('fixture bytes must never execute on host')\n"
        ).encode()

    def case(self, name, operator, *, version=2, entrypoint="candidate.py", task_parent_path=None):
        from buddha.releases import Release, _json, prepare_selection

        f = self.f
        actor = f.root / "frozen-improvers" / name
        actor.mkdir(parents=True)
        (actor / entrypoint).write_bytes(operator)
        f.roots = self.parent_roots | {"agent": actor}
        release = Release.from_record(self.parent_selection["release"])
        f.selection = prepare_selection(
            release,
            f.roots,
            capabilities=self.parent_selection["capabilities"],
        )
        self.assertNotEqual(f.selection.agent_sha256, self.parent_id)
        self.operator_raw = operator
        self.operator_id = f.selection.agent_sha256
        self.target_path = self.parent_path if task_parent_path is None else task_parent_path
        location = f.root / "detached-cases" / name
        location.mkdir(parents=True)
        f.directory, f.descriptor = location / "stage", location / "descriptor.json"
        f.record = copy.deepcopy(self.base_recipe)
        f.record["format"] = "buddha.candidate-improvement.v" + str(version)
        f.record["entrypoint"] = entrypoint
        f.record["parent_agent_sha256"] = self.parent_id
        f.record["executor"]["mounts"] = [
            ["/agent", str(actor)],
            ["/runner", str(f.roots["runner"])],
        ]
        if version == 2:
            f.record["task_parent"] = {
                "path": str(self.target_path),
                "sha256": sha(self.parent_raw),
            }
        f.descriptor.write_bytes(_json(f.record))
        return f

    def run_stage(self, proposal, *, callbacks=0, timeout=False, after_worker_error=None):
        import test_gateway

        from buddha import candidate_worker
        from buddha.channel import read_frame, write_frame
        from buddha.executor import ExecutionResult
        from buddha.gateway import RawHTTPTransport
        from buddha.releases import _json

        test, f = self, self.f

        class Frames:
            def __init__(self, handle):
                self.handle, self.pending, self.replies, self.sent = handle, b"", [], []

            def write(self, raw):
                self.pending += raw
                while b"\n" in self.pending:
                    frame, self.pending = self.pending.split(b"\n", 1)
                    value = read_frame(io.BytesIO(frame + b"\n"))
                    self.sent.append(value)
                    reply = self.handle(value)
                    if reply is not None:
                        framed = io.BytesIO()
                        write_frame(framed, reply)
                        self.replies.append(framed.getvalue())
                return len(raw)

            def flush(self):
                return None

            def readline(self, maximum):
                test.assertTrue(self.replies, "host must supply the pending callback reply")
                raw = self.replies.pop(0)
                test.assertLessEqual(len(raw), maximum)
                return raw

        def execute(spec, *, initial, handle, **kwargs):
            self.assertEqual(initial["format"], "buddha.candidate-improvement-worker.v3")
            self.assertEqual(initial["agent_sha256"], self.operator_id)
            expected_parent = {
                "entrypoint": "candidate.py",
                "source": self.parent_raw.decode(),
                "agent_sha256": self.parent_id,
            }
            self.assertEqual(initial["parent_bundle"], expected_parent)
            self.assertEqual(initial["feedback"], self.projected)
            self.assertEqual(set(dict(spec.mounts)), {"/agent", "/runner"})
            self.assertEqual(dict(spec.mounts)["/agent"], f.roots["agent"])
            self.assertNotIn(self.parent_roots["agent"], dict(spec.mounts).values())
            framed = io.BytesIO()
            write_frame(framed, initial)
            framed.seek(0)
            bridge = Frames(handle)
            worker = candidate_worker.CandidateWorker(read_frame(framed), bridge, bridge)

            def improve(parent, feedback, config, complete):
                self.assertEqual(parent, expected_parent)
                self.assertEqual(feedback, self.projected)
                self.assertEqual(config, f.record["config"])
                self.observed.append(
                    (self.operator_id, copy.deepcopy(parent), copy.deepcopy(feedback))
                )
                for sequence in range(callbacks):
                    request = f.h.request(sequence)
                    complete(request["provider"], base64.b64decode(request["body_base64"]))
                return proposal

            def load_selected(code, namespace):
                self.assertIs(code, sentinel.selected_improver)
                namespace["generate"] = lambda *args: []
                namespace["propose_improvement"] = improve

            # Only this trusted worker's loader is intercepted; other module imports
            # remain ordinary, and no supplied source text compiles/executes here.
            with (
                patch.object(worker, "_sources"),
                patch.object(worker, "_runtime"),
                patch.object(
                    candidate_worker, "_consume", return_value=self.operator_raw
                ) as consuming,
                patch.object(
                    candidate_worker,
                    "compile",
                    return_value=sentinel.selected_improver,
                    create=True,
                ) as compiling,
                patch.object(candidate_worker, "exec", side_effect=load_selected, create=True),
                patch.dict(sys.modules),
            ):
                worker.run()
            compiling.assert_called_once()
            self.assertEqual(compiling.call_args.args[0], self.operator_raw)
            consuming.assert_called_once_with(
                Path("/agent") / f.record["entrypoint"], sha(self.operator_raw)
            )
            if after_worker_error is not None:
                raise after_worker_error
            return ExecutionResult(
                0,
                "f" * 64,
                spec.image_id,
                0,
                0,
                sha(b""),
                len(bridge.sent),
                0.01,
                _json({"fixture": "trusted dispatch; mocked loader/process/HTTPS"}),
                "removed",
            )

        def connection(*args, **kwargs):
            result = f.h.connection(timeout=timeout)
            self.connections.append(result)
            return result

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": test_gateway.KEY}, clear=True),
            patch("buddha.executor.run_container", side_effect=execute),
            patch("http.client.HTTPSConnection", side_effect=connection),
        ):
            return f.run_api(f.directory, transport=RawHTTPTransport(allow_paid=True))

    def passive(self, report):
        from buddha.gateway import RawHTTPTransport

        f = self.f
        before, funding = files(f.root), f.f.authority.summary()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "buddha.candidate_run.CandidateSession", side_effect=AssertionError("new session")
            ),
            patch("buddha.executor.run_container", side_effect=AssertionError("new worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("new network")),
        ):
            inspected = f.inspect_api(
                f.directory,
                authorization=f.f.authority.path,
                expected_report_sha256=sha((f.directory / "report.json").read_bytes()),
            )
            replay = f.run_api(f.directory, transport=RawHTTPTransport(allow_paid=False))
        self.assertEqual(inspected, report)
        self.assertEqual(replay, report)
        self.assertEqual(files(f.root), before)
        self.assertEqual(f.f.authority.summary(), funding)

    def assert_roles(self, report):
        from buddha.releases import Release, _json, prepare_selection
        from buddha.source_screen import SourceScreen, _lineage

        f = self.f
        self.assertEqual(report["format"], "buddha.candidate-improvement-stage-report.v2")
        self.assertEqual(report["parent_agent_sha256"], self.parent_id)
        self.assertEqual(report["improver_agent_sha256"], self.operator_id)
        raw = report["improvement"]
        self.assertEqual(raw["format"], "buddha.candidate-improvement-report.v2")
        self.assertEqual(raw["parent_agent_sha256"], self.parent_id)
        self.assertEqual(raw["improver_agent_sha256"], self.operator_id)
        lineage = json.loads(Path(report["child"]["lineage"]["path"]).read_bytes())
        self.assertEqual(lineage["format"], "buddha.source-lineage.v2")
        self.assertEqual(lineage["parent"]["agent_sha256"], self.parent_id)
        self.assertEqual(lineage["parent"]["source_sha256"], sha(self.parent_raw))
        self.assertEqual(lineage["parent"]["entrypoint"], "candidate.py")
        self.assertEqual(lineage["improver"]["agent_sha256"], self.operator_id)
        self.assertEqual(lineage["improver"]["source_sha256"], sha(self.operator_raw))
        self.assertEqual(lineage["improver"]["entrypoint"], f.record["entrypoint"])
        # Exercise the shared consumer without another screen/worker fixture.
        child_record = copy.deepcopy(f.feedback.h.record)
        generation = child_record["generation"]
        child_root = Path(report["child"]["directory"])
        child_roots = {name: Path(path) for name, path in generation["roots"].items()} | {
            "agent": child_root
        }
        child_selection = prepare_selection(
            Release.from_record(self.parent_selection["release"]),
            child_roots,
            capabilities=self.parent_selection["capabilities"],
        )
        generation["selection"] = child_selection.to_record()
        generation["roots"] = {name: str(path) for name, path in child_roots.items()}
        generation["entrypoint"] = "candidate.py"
        generation["executor"]["mounts"] = [
            ["/agent", str(child_root)],
            ["/runner", str(child_roots["runner"])],
        ]
        child_record["lineage"] = report["child"]["lineage"]
        child_screen = SourceScreen.from_bytes(_json(child_record))
        self.assertEqual(child_screen.candidate_id, report["child"]["agent_sha256"])

        def checked_read(path, digest):
            raw = path.read_bytes()
            self.assertEqual(sha(raw), digest)
            return raw

        self.assertEqual(_lineage(child_screen, checked_read), self.parent_id)
        owner = json.loads((f.directory / "owners/0/manifest.json").read_bytes())
        self.assertEqual(sha(_json(owner["selection"]["components"]["agent"])), self.operator_id)
        bindings = {row["path"]: row["sha256"] for row in owner["invocation"]["inputs"]}
        self.assertEqual(bindings[str(self.target_path)], sha(self.parent_raw))
        self.assertEqual(bindings[str(f.descriptor)], sha(f.descriptor.read_bytes()))
        self.assertEqual(
            bindings[str(f.packet / "provenance.json")], f.written["provenance"]["sha256"]
        )
        for role, value in self.parent_selection["components"].items():
            if role != "agent":
                self.assertEqual(owner["selection"]["components"][role], value)
        history = f.owner_history()
        for sequence, operation in enumerate(history.operations):
            request = operation.receipt["request"]
            self.assertEqual(
                request["logical_id"],
                sha(
                    _json(
                        [
                            "buddha.candidate-improvement-call.v2",
                            sha(f.descriptor.read_bytes()),
                            self.operator_id,
                            self.parent_id,
                            sha(_json(self.projected)),
                            sequence,
                        ]
                    )
                ),
            )
        return history

    def test_legacy_v1_still_refuses_detached_operator_before_owner_or_charge(self):
        self.fixture()
        f = self.case("legacy-mismatch", self.operator_source("initial"), version=1)
        before, funding = files(f.root), f.f.authority.summary()
        with self.assertRaises(f.Error):
            f.prepare()
        self.assertFalse(f.directory.exists())
        self.assertEqual(files(f.root), before)
        self.assertEqual(f.f.authority.summary(), funding)

    def test_two_frozen_operators_receive_same_measured_parent_and_full_packet(self):
        from buddha.releases import _json

        f = self.fixture()
        alternate_parent = f.root / "same-task-parent.py"
        alternate_parent.write_bytes(self.parent_raw)
        self.assertEqual(self.parent_id, sha(_json({"candidate.py": sha(self.parent_raw)})))
        identities, logical = [], []
        for name in ("initial", "evolved"):
            with self.subTest(operator=name):
                options = (
                    {"entrypoint": "operator.py", "task_parent_path": alternate_parent}
                    if name == "evolved"
                    else {}
                )
                f = self.case(name, self.operator_source(name), **options)
                f.prepare()
                child = f.child()
                report = self.run_stage(child, callbacks=1)
                self.assertEqual(
                    (report["status"], report["disposition"]), ("complete", "materialized")
                )
                history = self.assert_roles(report)
                self.assertEqual(len(history.operations), 1)
                self.assertEqual(history.operations[0].status, "completed")
                identities.append(self.operator_id)
                logical.append(history.operations[0].receipt["request"]["logical_id"])
                self.assertEqual(
                    Path(report["child"]["directory"]).joinpath("candidate.py").read_bytes(),
                    child["source"].encode(),
                )
                self.passive(report)
        self.assertEqual(len(set(identities)), 2)
        self.assertEqual(len(set(logical)), 2)
        self.assertEqual(self.observed[0][1:], self.observed[1][1:])
        self.assertTrue(all(path.read_bytes() == raw for path, raw in self.common_files.items()))

    def test_child_change_is_relative_to_task_parent_not_executing_operator(self):
        self.fixture()
        operator = self.operator_source("fixed")
        f = self.case("unchanged-target", operator)
        f.prepare()
        rejected = self.run_stage(
            {"source": self.parent_raw.decode(), "hypothesis": "unchanged target"}, callbacks=1
        )
        self.assertEqual((rejected["status"], rejected["disposition"]), ("complete", "rejected"))
        self.assertEqual(rejected["reason"], "invalid_proposal")
        self.assertIsNone(rejected["child"])
        self.assertEqual(len(f.owner_history().operations), 1)
        self.assertEqual(f.owner_history().operations[0].status, "completed")
        self.passive(rejected)
        f = self.case("operator-as-changed-target", operator)
        f.prepare()
        changed = self.run_stage(
            {"source": operator.decode(), "hypothesis": "changed relative to target"}
        )
        self.assertEqual((changed["status"], changed["disposition"]), ("complete", "materialized"))
        self.assertEqual(
            Path(changed["child"]["directory"]).joinpath("candidate.py").read_bytes(), operator
        )
        self.assertEqual(len(self.assert_roles(changed).operations), 0)
        self.passive(changed)

    def test_original_known_receipt_recovers_once_and_unknown_cannot_be_replaced(self):
        from buddha.executor import ExecutorError

        self.fixture()
        f = self.case("known-reply", self.operator_source("initial"))
        f.prepare()
        partial = self.run_stage(
            f.child(), callbacks=1, after_worker_error=ExecutorError("synthetic after reply")
        )
        f.partial(partial)
        original = f.owner_history()
        self.assertEqual([row.status for row in original.operations], ["completed"])
        owner = (f.directory / "owners/0/manifest.json").read_bytes()
        attempts = files(f.directory / "attempts")
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared",
            side_effect=AssertionError("duplicate send"),
        ):
            complete = self.run_stage(f.child(), callbacks=1)
        self.assertEqual(
            (complete["status"], complete["disposition"]), ("complete", "materialized")
        )
        self.assertEqual(f.owner_history().totals(), original.totals())
        self.assertEqual((f.directory / "owners/0/manifest.json").read_bytes(), owner)
        self.assertTrue(
            all(
                files(f.directory / "attempts")[name] == digest for name, digest in attempts.items()
            )
        )
        self.assertEqual(len(list((f.directory / "owners").iterdir())), 1)
        self.assert_roles(complete)
        self.passive(complete)
        f = self.case("unknown-reply", self.operator_source("evolved"))
        f.prepare()
        stopped = self.run_stage(f.child(), callbacks=1, timeout=True)
        f.partial(stopped)
        self.assertEqual(stopped["reason"], "unknown")
        unknown = f.owner_history()
        self.assertEqual([row.status for row in unknown.operations], ["unknown"])
        self.assertGreater(unknown.totals()["reserved_microusd"], 0)
        owner = (f.directory / "owners/0/manifest.json").read_bytes()
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared",
            side_effect=AssertionError("replacement send"),
        ):
            again = self.run_stage(f.child(), callbacks=1)
        f.partial(again)
        self.assertEqual(f.owner_history().totals(), unknown.totals())
        self.assertEqual((f.directory / "owners/0/manifest.json").read_bytes(), owner)
        self.assertEqual(len(list((f.directory / "owners").iterdir())), 1)
        self.assertFalse((f.directory / "completed/0.json").exists())

    def test_detached_parent_identity_and_measured_parent_are_independent_guards(self):
        from buddha.releases import _json

        self.fixture()
        operator = self.operator_source("parent-binding-control")
        for coherent_target in (False, True):
            with self.subTest(coherent_target=coherent_target):
                name = "wrong-feedback-parent" if coherent_target else "wrong-derived-parent"
                f = self.case(name, operator)
                # Both references point to real, correctly hashed I bytes. In A
                # the declared target identity remains S and contradicts those
                # bytes; in B identity/bytes agree on I but measured feedback is S.
                f.record["task_parent"] = {
                    "path": str(f.roots["agent"] / "candidate.py"),
                    "sha256": sha(operator),
                }
                f.record["parent_agent_sha256"] = (
                    self.operator_id if coherent_target else self.parent_id
                )
                f.descriptor.write_bytes(_json(f.record))
                before, funding = files(f.root), f.f.authority.summary()
                with self.assertRaises(f.Error):
                    f.prepare()
                self.assertFalse(f.directory.exists())
                self.assertEqual(files(f.root), before)
                self.assertEqual(f.f.authority.summary(), funding)

    def test_real_legacy_prefix_packet_is_refused_at_stage_and_direct_session(self):
        from buddha.candidate_run import CandidateRunError, CandidateSession
        from buddha.releases import _json
        from buddha.source_feedback import _build, inspect_source_feedback

        f = self.fixture()
        reference = json.loads((f.packet / "provenance.json").read_bytes())["reference"]
        legacy_directory = f.root / "legacy-prefix-packet"
        legacy = _build(legacy_directory, reference, full_answers=False)
        legacy_directory.mkdir()
        for name, record in legacy.items():
            (legacy_directory / (name + ".json")).write_bytes(_json(record))
        legacy_provenance_sha256 = sha((legacy_directory / "provenance.json").read_bytes())
        self.assertEqual(legacy["feedback"]["format"], "buddha.candidate-development-feedback.v1")
        self.assertTrue(
            any(
                answer["omitted_utf8_bytes"] > 0
                for task in legacy["provenance"]["tasks"]
                for answer in task["answers"]
            )
        )
        with f.feedback.passive():
            self.assertEqual(
                inspect_source_feedback(
                    legacy_directory,
                    expected_provenance_sha256=legacy_provenance_sha256,
                ),
                legacy,
            )

        f = self.case("legacy-prefix-stage", self.operator_source("prefix-stage"))
        legacy_feedback = {
            "path": str(legacy_directory / "feedback.json"),
            "sha256": sha((legacy_directory / "feedback.json").read_bytes()),
        }
        f.record["feedback"] = legacy_feedback
        f.descriptor.write_bytes(_json(f.record))
        before, funding = files(f.root), f.f.authority.summary()
        with self.assertRaises(f.Error):
            f.prepare(expected_feedback_provenance_sha256=legacy_provenance_sha256)
        self.assertFalse(f.directory.exists())
        self.assertEqual(files(f.root), before)
        self.assertEqual(f.f.authority.summary(), funding)

        def direct_owner(name, packet):
            inputs = [
                f.descriptor,
                f.h.runtime_path,
                self.target_path,
                *[packet / (part + ".json") for part in ("source", "split", "feedback")],
                *[f.h.package / (part + ".py") for part in (*f.h.host_names, "policy_study")],
            ]
            owner = f.f.prepare(name, selection=f.selection, roots=f.roots, input_files=inputs)
            return f.f.gateway(live=False, directory=owner)

        # The generic API accepts reviewed full notes without claiming measured
        # provenance: its positive control freezes no provenance/stage helper.
        f = self.case("generic-full-notes", self.operator_source("generic-full"))
        gateway = direct_owner("generic-full-owner", f.packet)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.executor.run_container", side_effect=AssertionError("new worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("new network")),
        ):
            session = CandidateSession(
                gateway,
                descriptor=f.descriptor,
                output=f.root / "generic-full-session",
                expected_runtime_sha256=f.h.expected_runtime,
            )
        self.assertEqual(session.worker["format"], "buddha.candidate-improvement-worker.v3")
        self.assertEqual(session.worker["feedback"], self.projected)
        self.assertEqual(gateway.ledger.totals()["operation_count"], 0)

        f = self.case("generic-prefix-notes", self.operator_source("generic-prefix"))
        f.record["feedback"] = legacy_feedback
        f.descriptor.write_bytes(_json(f.record))
        gateway = direct_owner("generic-prefix-owner", legacy_directory)
        output = f.root / "generic-prefix-session"
        # Generic construction needs a previously prepared owner; refusal must
        # preserve that owner and stop before any Session output or operation.
        before, funding = files(f.root), f.f.authority.summary()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.executor.run_container", side_effect=AssertionError("new worker")),
            patch("http.client.HTTPSConnection", side_effect=AssertionError("new network")),
            self.assertRaises(CandidateRunError),
        ):
            CandidateSession(
                gateway,
                descriptor=f.descriptor,
                output=output,
                expected_runtime_sha256=f.h.expected_runtime,
            )
        self.assertFalse(output.exists())
        self.assertEqual(gateway.ledger.totals()["operation_count"], 0)
        self.assertEqual(files(f.root), before)
        self.assertEqual(f.f.authority.summary(), funding)
        self.assertTrue(all(path.read_bytes() == raw for path, raw in self.common_files.items()))


if __name__ == "__main__":
    unittest.main()
