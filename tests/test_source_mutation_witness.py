"""Bounded witness admission through real stages; candidate workers are simulated."""

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_source_search as fixtures

from buddha.executor import ExecutorError
from buddha.releases import _json

WITNESS_CHILD = """def generate(task, config, complete):
    return ["literal witness answer" for _ in range(task["count"])]
"""
LONG_ANSWER = (
    "  BEGIN literal output\n" + "α雪 repeated full text  \n" * 300 + "END literal output  "
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def agent(source):
    return sha(_json({"candidate.py": sha(source.encode())}))


class _Harness:
    """Reuse real search/custody; only the existing executor boundary is supplied."""

    def __init__(self, test, *, iterations=1):
        self.case = case = fixtures.SourceSearchTests("runTest").fixture(iterations=iterations)
        test.addCleanup(case.doCleanups)
        # The original controller ignored this attribute in the behavioral RED.
        # The fixture adapter selects legacy v2 unless this is True.
        case.mutation_witness = True
        self.modes = {}
        self.normal_sources = [fixtures.REPAIRED] * iterations
        self.normal_callbacks = 1
        self.witness_callbacks = 0
        self.interrupt_once = self.unknown_once = False
        self.improvements, self.generations = [], []
        case.programs[sha(WITNESS_CHILD.encode())] = ("supplied-zero-callback-witness", 0)
        original_execute, original_screen = case.execute, case.h.execute
        case.execute_improvement = self.improve

        def screen_execute(spec, *, initial, handle, **kwargs):
            if spec.role == "agent":
                case.h.programs[initial["agent_sha256"]]["answers"] = [LONG_ANSWER, ""]
            return original_screen(spec, initial=initial, handle=handle, **kwargs)

        def execute(spec, *, initial, handle, **kwargs):
            if spec.role == "agent" and "task" in initial:
                self.generations.append(
                    {
                        "owner": handle.__self__.gateway.directory,
                        "agent_id": initial["agent_sha256"],
                        "task": copy.deepcopy(initial["task"]),
                    }
                )
            return original_execute(spec, initial=initial, handle=handle, **kwargs)

        case.h.execute, case.execute = screen_execute, execute

    @staticmethod
    def witness_root(owner):
        return next(
            (path for path in owner.parents if path.name in {"seed-witness", "witness"}), None
        )

    def improve(self, spec, initial, handle, source):
        case = self.case
        owner = handle.__self__.gateway.directory
        witness = self.witness_root(owner)
        if witness is None:
            ordinal = int(owner.relative_to(case.directory).parts[1])
            child, mode, callbacks = self.normal_sources[ordinal], "valid", self.normal_callbacks
        else:
            mode = self.modes.get(initial["agent_sha256"], "valid")
            child = fixtures.BROKEN if mode == "generation_failed" else WITNESS_CHILD
            callbacks = self.witness_callbacks
        value = {"source": child, "hypothesis": "Supplied bounded witness mutation."}
        event = {
            "owner": owner,
            "witness": witness,
            "parent_id": initial["agent_sha256"],
            "source": source,
            "feedback": copy.deepcopy(initial["feedback"]),
            "physical_sends": 0,
        }
        if witness is not None:
            screen = (
                case.directory / "seed"
                if witness.name == "seed-witness"
                else witness.parent / "screen"
            )
            event["screen"] = screen
            event["screen_bytes"] = (screen / "report.json").read_bytes()
        self.improvements.append(event)
        case.engine.workers += 1
        handle(
            {
                "type": "ready",
                "agent_sha256": initial["agent_sha256"],
                "feedback_sha256": sha(_json(initial["feedback"])),
                "runtime_sha256": case.engine.candidate.expected_runtime,
            }
        )
        for sequence in range(callbacks):
            payload = _json({"source": source.decode(), "feedback": initial["feedback"]}).decode()
            request = case.engine.candidate.request(sequence, text=payload)
            response = case.engine.fixture.response(
                choices=[{"message": {"content": _json(value).decode()}}]
            )
            connection = case.engine.fixture.connection(response)
            if witness is not None and self.unknown_once:
                self.unknown_once = False
                connection.getresponse.side_effect = TimeoutError("synthetic witness unknown")
            with patch("http.client.HTTPSConnection", return_value=connection):
                reply = handle(request)
            event["physical_sends"] += connection.request.call_count
            case.engine.physical_sends += connection.request.call_count
            if reply["type"] == "stop":
                handle(
                    {
                        "type": "done",
                        "status": "stopped",
                        "reason": reply["reason"],
                        "proposal": {
                            "status": "unavailable",
                            "value": None,
                            "sha256": None,
                            "bytes": None,
                        },
                    }
                )
                return case.engine.execution(spec)
            if witness is not None and self.interrupt_once:
                self.interrupt_once = False
                raise ExecutorError(
                    "synthetic received witness reply interruption",
                    cleanup_status="removed",
                    container_id="f" * 64,
                )
        if mode == "agent_error":
            status, reason = "failed", "agent_error"
            capture = {"status": "unavailable", "value": None, "sha256": None, "bytes": None}
        elif mode == "invalid":
            status, reason = "failed", "invalid_proposal"
            capture = {"status": "captured", "value": {}, "sha256": sha(_json({})), "bytes": 2}
        else:
            status, reason = "complete", "complete"
            capture = {
                "status": "captured",
                "value": value,
                "sha256": sha(_json(value)),
                "bytes": len(_json(value)),
            }
        handle({"type": "done", "status": status, "reason": reason, "proposal": capture})
        if mode == "cleanup_unknown":
            with patch.object(case.engine, "cleanup", "unknown"):
                return case.engine.execution(spec)
        return case.engine.execution(spec)

    def prepare(self):
        self.case.prepare()

    def run(self, *, paid=True):
        return self.case.run_search(paid=paid)


class SourceMutationWitnessTests(unittest.TestCase):
    def test_failed_seed_improver_cannot_become_a_parent_from_metrics_alone(self):
        h = _Harness(self)
        h.modes[h.case.seed.candidate_id] = "agent_error"
        h.prepare()
        result = h.run()
        # Assert the missing behavior before requiring any new schema field.
        self.assertEqual((result["status"], result["reason"]), ("complete", "no_parent_eligible"))
        self.assertEqual(result["decisions"], [])
        self.assertFalse((h.case.directory / "iterations/0").exists())
        self.assertIsNone(result["selection"]["selected_id"])
        self.assertEqual([row["status"] for row in result["witnesses"]], ["failed"])
        self.assertEqual(result["witnesses"][0]["reason"], "agent_error")
        seed = json.loads((h.case.directory / "seed/report.json").read_bytes())
        self.assertIs(seed["admission"]["eligible"], True)
        self.assertEqual(h.case.inspect(), result)

    def test_failed_child_witness_keeps_native_measurements_but_excludes_parent(self):
        h = _Harness(self)
        h.modes[agent(fixtures.REPAIRED)] = "agent_error"
        h.prepare()
        result = h.run()
        self.assertEqual(
            [row["status"] for row in result["decisions"]], ["mutation_witness_failed"]
        )
        self.assertEqual(result["selection"]["selected_id"], h.case.seed.candidate_id)
        self.assertEqual(len(result["screens"]), 2)
        screen = json.loads((h.case.directory / "iterations/0/screen/report.json").read_bytes())
        self.assertIs(screen["admission"]["eligible"], True)
        self.assertEqual([row["status"] for row in result["witnesses"]], ["passed", "failed"])
        self.assertIsNone(result["witnesses"][1]["generation"])
        for event in h.improvements:
            if event["witness"] is not None:
                self.assertEqual(
                    (event["screen"] / "report.json").read_bytes(), event["screen_bytes"]
                )

    def test_full_feedback_zero_callback_mutation_and_exact_first_task_are_consumed(self):
        h = _Harness(self)
        h.prepare()
        result = h.run()
        manifest = json.loads((h.case.directory / "manifest.json").read_bytes())
        self.assertEqual(manifest["format"], "buddha.source-search-manifest.v3")
        self.assertEqual(result["format"], "buddha.source-search-report.v2")
        self.assertEqual([row["status"] for row in result["witnesses"]], ["passed", "passed"])
        self.assertEqual(result["decisions"][0]["child_id"], agent(fixtures.REPAIRED))
        self.assertEqual(result["decisions"][0]["status"], "admitted")
        self.assertEqual(result["selection"]["selected_id"], agent(fixtures.REPAIRED))
        witness_events = [event for event in h.improvements if event["witness"] is not None]
        self.assertEqual(
            [event["parent_id"] for event in witness_events],
            [h.case.seed.candidate_id, agent(fixtures.REPAIRED)],
        )
        for event in witness_events:
            self.assertEqual([row["task"]["id"] for row in event["feedback"]], ["1", 1])
            for row in event["feedback"]:
                note = json.loads(row["note"])
                self.assertEqual(
                    note["answers"],
                    [{"position": 0, "text": LONG_ANSWER}, {"position": 1, "text": ""}],
                )
                self.assertEqual(note["omitted_answer_positions"], 0)
                self.assertGreater(len(row["note"].encode()), 4096)
            self.assertEqual(event["physical_sends"], 0)
            self.assertEqual((event["screen"] / "report.json").read_bytes(), event["screen_bytes"])
        witnessed_generations = [
            event for event in h.generations if h.witness_root(event["owner"]) is not None
        ]
        self.assertEqual(len(witnessed_generations), 2)
        for event in witnessed_generations:
            self.assertEqual(event["agent_id"], agent(WITNESS_CHILD))
            self.assertEqual(event["task"], h.case.seed.tasks.tasks[0].to_record())
            self.assertIs(type(event["task"]["id"]), str)
        self.assertNotIn(agent(WITNESS_CHILD), result["selection"]["active_ids"])
        self.assertNotIn(
            agent(WITNESS_CHILD),
            [
                json.loads((Path(row["directory"]) / "report.json").read_bytes())["candidate_id"]
                for row in result["screens"]
            ],
        )
        normal = [event for event in h.improvements if event["witness"] is None]
        self.assertEqual(len(normal), 1)
        self.assertEqual(normal[0]["owner"], h.case.directory / "iterations/0/proposal/owners/0")
        self.assertTrue(all(normal[0]["owner"] != event["owner"] for event in witness_events))
        for row in result["witnesses"]:
            self.assertIsNotNone(row["proposal"])
            self.assertIsNotNone(row["generation"])
        self.assertEqual(
            result["provenance"]["scoped_totals"]["operation_count"],
            h.case.authority.summary()["operation_count"],
        )

    def test_rejected_or_failed_generation_is_terminal_but_unclean_cleanup_is_incomplete(self):
        for mode in ("invalid", "generation_failed", "cleanup_unknown"):
            with self.subTest(mode=mode):
                h = _Harness(self)
                h.modes[h.case.seed.candidate_id] = mode
                h.prepare()
                result = h.run()
                if mode == "cleanup_unknown":
                    h.case.partial(result)
                    self.assertIn("witness", result["stage"])
                    self.assertFalse((h.case.directory / "seed-witness/report.json").exists())
                else:
                    self.assertEqual(
                        (result["status"], result["reason"]), ("complete", "no_parent_eligible")
                    )
                    self.assertEqual(result["witnesses"][0]["status"], "failed")
                    self.assertEqual(
                        result["witnesses"][0]["reason"],
                        "invalid_proposal" if mode == "invalid" else "agent_error",
                    )
                    if mode == "generation_failed":
                        generation = json.loads(
                            (h.case.directory / "seed-witness/generation/report.json").read_bytes()
                        )
                        self.assertEqual(generation["disposition"], "candidate_execution_failed")
                        self.assertFalse(
                            list((h.case.directory / "seed-witness").glob("**/answers.json"))
                        )
                self.assertFalse((h.case.directory / "iterations/0").exists())

    def test_known_witness_reply_resumes_original_owner_then_replays_keylessly(self):
        h = _Harness(self)
        h.witness_callbacks, h.interrupt_once = 1, True
        h.normal_callbacks, h.normal_sources = 0, [fixtures.BROKEN]
        h.prepare()
        first = h.run()
        h.case.partial(first)
        self.assertIn("witness", first["stage"])
        location = h.case.directory / "seed-witness"
        original = {
            "manifest": (location / "proposal/owners/0/manifest.json").read_bytes(),
            "plan": (location / "plan.json").read_bytes(),
            "feedback": h.case.h.files(location / "feedback"),
            "attempts": h.case.h.files(location / "proposal/attempts"),
        }
        sends = h.case.engine.physical_sends
        self.assertFalse((h.case.directory / "iterations/0").exists())
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared",
            side_effect=AssertionError("known witness rebilling"),
        ):
            result = h.run()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(h.case.engine.physical_sends, sends)
        self.assertEqual(
            (location / "proposal/owners/0/manifest.json").read_bytes(), original["manifest"]
        )
        self.assertEqual((location / "plan.json").read_bytes(), original["plan"])
        self.assertEqual(h.case.h.files(location / "feedback"), original["feedback"])
        for path, digest in original["attempts"].items():
            self.assertEqual(sha((location / "proposal/attempts" / path).read_bytes()), digest)
        self.assertEqual(
            sum(
                event["physical_sends"] for event in h.improvements if event["witness"] == location
            ),
            1,
        )
        self.assertEqual(len(list((location / "proposal/owners").iterdir())), 1)
        before = (
            h.case.h.files(h.case.directory),
            h.case.authority.summary(),
            h.case.engine.physical_sends,
        )
        with patch(
            "buddha.candidate_run.CandidateSession",
            side_effect=AssertionError("new witness session"),
        ):
            self.assertEqual(h.run(paid=False), result)
            self.assertEqual(h.case.inspect(), result)
        self.assertEqual(
            (
                h.case.h.files(h.case.directory),
                h.case.authority.summary(),
                h.case.engine.physical_sends,
            ),
            before,
        )

    def test_unknown_witness_keeps_hold_and_forbids_generation_or_later_parent_work(self):
        h = _Harness(self, iterations=2)
        h.witness_callbacks, h.unknown_once = 1, True
        h.prepare()
        first = h.run()
        h.case.partial(first)
        self.assertEqual(first["reason"], "unknown")
        self.assertIn("witness", first["stage"])
        summary = h.case.authority.summary()
        self.assertGreater(summary["reserved_microusd"], 0)
        owners = {row["directory"]: row["run_id"] for row in summary["runs"]}
        sends = h.case.engine.physical_sends
        with patch(
            "buddha.gateway.RawHTTPTransport.send_prepared",
            side_effect=AssertionError("unknown witness resend"),
        ):
            again = h.run()
        h.case.partial(again)
        self.assertEqual(h.case.engine.physical_sends, sends)
        self.assertEqual(
            h.case.authority.summary()["reserved_microusd"], summary["reserved_microusd"]
        )
        self.assertEqual(
            {row["directory"]: row["run_id"] for row in h.case.authority.summary()["runs"]}, owners
        )
        self.assertFalse((h.case.directory / "seed-witness/generation").exists())
        self.assertFalse((h.case.directory / "iterations/0").exists())

    def test_changed_packet_and_rehashed_witness_publication_cannot_assert_competence(self):
        h = _Harness(self)
        h.prepare()
        result = h.run()
        packet = h.case.directory / "seed-witness/feedback/feedback.json"
        generation = h.case.directory / "seed-witness/generation/report.json"
        publication = h.case.directory / "report.json"
        originals = {path: path.read_bytes() for path in (packet, generation, publication)}
        before_sends = h.case.engine.physical_sends
        changed = json.loads(originals[packet])
        changed["records"][0]["note"] += "changed measured note"
        packet.write_bytes(_json(changed))
        try:
            with h.case.h.readonly(), self.assertRaises(h.case.Error):
                h.case.inspect_api(h.case.directory, **h.case.reference())
        finally:
            packet.write_bytes(originals[packet])
        changed = json.loads(originals[generation])
        changed["invented_competence"] = True
        generation.write_bytes(_json(changed))
        forged = copy.deepcopy(result)
        forged["witnesses"][0]["generation"]["report_sha256"] = sha(_json(changed))
        publication.write_bytes(_json(forged))
        try:
            with h.case.h.readonly(), self.assertRaises(h.case.Error):
                h.case.inspect_api(h.case.directory, **h.case.reference())
        finally:
            generation.write_bytes(originals[generation])
            publication.write_bytes(originals[publication])
        self.assertEqual(h.case.engine.physical_sends, before_sends)
        self.assertEqual(h.case.inspect(), result)

    def test_legacy_v2_task_only_schedule_and_completed_replay_are_byte_exact(self):
        from buddha import source_search

        case = fixtures.SourceSearchTests("runTest").fixture(iterations=1)
        self.addCleanup(case.doCleanups)
        case.proposals = [fixtures.REPAIRED]
        with patch.object(source_search, "_MANIFEST", "buddha.source-search-manifest.v2"):
            case.prepare()
        result = case.run_search()
        self.assertEqual(result["format"], "buddha.source-search-report.v1")
        self.assertEqual([row["status"] for row in result["decisions"]], ["admitted"])
        self.assertNotIn("witnesses", result)
        self.assertFalse((case.directory / "seed-witness").exists())
        self.assertEqual(
            (
                case.engine.physical_sends,
                len(case.worker_events),
                len(case.authority.summary()["runs"]),
            ),
            (15, 17, 17),
        )
        before = case.h.files(case.directory), case.authority.summary(), case.engine.physical_sends
        self.assertEqual(case.inspect(), result)
        self.assertEqual(case.run_search(paid=False), result)
        self.assertEqual(
            (case.h.files(case.directory), case.authority.summary(), case.engine.physical_sends),
            before,
        )


if __name__ == "__main__":
    unittest.main()
