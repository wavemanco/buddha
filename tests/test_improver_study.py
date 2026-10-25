"""Finite controlled-improver acceptance checks.

One costly composed method shares an economical real custody fixture across
all recoverable corruptions. Workers/HTTPS/native outputs are supplied; no
selected program compiles or executes on the host. Bootstrap evidence is
outside both actual study roots and never part of either study's accounting.
"""

import copy
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

LITERAL = "  BEGIN full answer\n" + "snow 雪 alpha α  " * 7 + "\nLATE ENDING  "
TASK_ID = "1"  # Deliberately distinct from integer1 in the complete source.
TOTALS = ("spent_microusd", "reserved_microusd", "committed_microusd", "operation_count")
COORDINATES = ("start", "repetition", "arm", "slot")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source(label):
    return (
        "# supplied source: " + label + "\n"
        "raise RuntimeError('selected-module host-exec canary: " + label + "')\n"
        "def generate(task, config, complete):\n"
        "    raise RuntimeError('fixture: never execute selected source on host')\n"
        "def propose_improvement(parent, feedback, config, complete):\n"
        "    raise RuntimeError('own improver: " + label + "')\n"
    ).encode()


def observe_fixture_workers(fixture, observer):
    original_execute = fixture.execute

    def checked_execute(spec, *, initial, handle, **kwargs):
        # Original input assertions and execution exceptions propagate unchanged.
        execution = original_execute(spec, initial=initial, handle=handle, **kwargs)
        with observer.subTest(contract="completed-fixture-worker", role=spec.role):
            observer.assertEqual(execution.cleanup_status, "removed")
        return execution

    fixture.execute = checked_execute


class FiniteImproverStudyTests(unittest.TestCase):
    def fixture_before_new_api(self, *, proposal_capacity=False, capacity_output_tokens=32_768):
        import test_source_screen_outcome

        from buddha import candidate_improvement, source_feedback, source_search
        from buddha.releases import _json, prepare_selection

        self.lower = candidate_improvement
        self.feedback_api, self.shared = source_feedback, source_search
        self.outcome = test_source_screen_outcome.SourceScreenOutcomeTests("runTest")
        self.addCleanup(self.outcome.doCleanups)
        self.h = h = self.outcome.fixture()
        self.root, self.engine = h.root, h.engine
        if proposal_capacity:
            # Configure the prospective fixture before selections or owners exist.
            profile = self.engine.fixture.profiles["profiles"]["primary"]["spec"]
            profile.update(
                input_token_ceiling=1_050_000,
                max_output_tokens=capacity_output_tokens,
                input_microusd_per_million=1,
                output_microusd_per_million=1,
            )
            self.engine.fixture.write(
                "host", "profiles/openai.json", json.dumps(self.engine.fixture.profiles)
            )
            h.record["generation"]["config"]["max_output_tokens"] = capacity_output_tokens
            for section in (h.record["native"], self.engine.native):
                section["selection"] = prepare_selection(
                    self.engine.candidate.release,
                    {name: Path(value) for name, value in section["roots"].items()},
                    capabilities=section["selection"]["capabilities"],
                ).to_record()
        h.record["format"] = "buddha.source-screen.v2"
        h.record["selected_ids"] = [TASK_ID]
        h.record["generation"]["max_calls"] = 3
        h.record["native"]["max_calls"] = 3
        self.records, self.sources = {}, {}
        self.expected_common = {}
        self.events, self.improvements, self.generated = [], [], []
        self.literal = LITERAL
        self.baseline_utility = 7
        self.outcomes = {
            (0, 0, 0, 0): "failed",
            (0, 0, 1, 0): "rejected",
            (0, 1, 1, 0): "failed_witness",
            (0, 1, 0, 1): "duplicate",
            (1, 0, 0, 0): "ineligible",
        }
        self.fixed, self.starts = [], []
        generation = h.record["generation"]
        base_roots = {name: Path(value) for name, value in generation["roots"].items()}
        self.capabilities = generation["selection"]["capabilities"]
        for kind, count in (("S", 2), ("I", 2)):
            for ordinal in range(count):
                actor = self.root / (kind + str(ordinal))
                actor.mkdir()
                raw = source(kind + str(ordinal))
                (actor / "candidate.py").write_bytes(raw)
                roots = base_roots | {"agent": actor}
                selected = prepare_selection(
                    self.engine.candidate.release, roots, capabilities=self.capabilities
                )
                self.sources[selected.agent_sha256] = raw
                item = {
                    "name": ("initial", "evolved")[ordinal] if kind == "I" else "S" + str(ordinal),
                    "selection": selected.to_record(),
                    "roots": {key: str(value) for key, value in roots.items()},
                    "entrypoint": "candidate.py",
                }
                if kind == "I":
                    self.fixed.append(item)
                else:
                    record = copy.deepcopy(h.record)
                    record["generation"].update(selection=selected.to_record(), roots=item["roots"])
                    record["generation"]["executor"]["mounts"] = [
                        ["/agent", str(actor)],
                        ["/runner", str(roots["runner"])],
                    ]
                    screen = h.screen(record)
                    h.programs[screen.candidate_id].update(answers=[LITERAL, ""], callbacks=1)
                    self.starts.append({"name": item["name"], "screen": screen.to_record()})
                    self.records[screen.candidate_id] = screen.to_record()
        self.base = h.Screen.from_bytes(_json(self.starts[0]["screen"]))
        self.template = {
            name: copy.deepcopy(self.base.to_record()["generation"][name])
            for name in ("config", "profile", "max_callbacks", "budget_microusd", "max_calls")
        }
        self.original_execute = h.execute
        self.known_once = self.unknown_once = False
        self.known_owner = None
        self.unknown_scope = None
        self.known_replay = False
        self.scope = self.root / "study"
        controls = {
            path: sha(path.read_bytes())
            for path in [
                *source_search._sources(),
                Path(generation["runtime"]["path"]),
                *(
                    self.root / (kind + str(index)) / "candidate.py"
                    for kind in ("S", "I")
                    for index in range(2)
                ),
            ]
        }
        # Honest setup on pre-existing APIs before importing the missing consumer.
        bootstrap = self.root / "bootstrap-screen"
        h.prepare(self.base, bootstrap, input_bindings=controls)
        self.assertEqual(h.run_screen(bootstrap)["status"], "complete")
        bootstrap_authority = h.authorities[-1]
        reference = h.reference(bootstrap, bootstrap_authority)
        packet = self.root / "bootstrap-feedback"
        written = source_feedback.write_source_feedback(packet, reference=reference)
        parent_path = self.root / "S0/candidate.py"
        actor = self.fixed[0]
        descriptor = self.root / "bootstrap-proposal.json"
        descriptor.write_bytes(
            _json(
                {
                    "format": "buddha.candidate-improvement.v2",
                    **{name: generation[name] for name in ("runtime",)},
                    "entrypoint": actor["entrypoint"],
                    "executor": self.actor_executor(actor),
                    **{
                        name: self.template[name] for name in ("config", "profile", "max_callbacks")
                    },
                    "parent_agent_sha256": self.base.candidate_id,
                    "task_parent": {
                        "path": str(parent_path),
                        "sha256": sha(parent_path.read_bytes()),
                    },
                    "feedback": written["feedback"],
                }
            )
        )
        from buddha.releases import Selection

        stage = self.root / "bootstrap-proposal"
        candidate_improvement.prepare_candidate_improvement(
            stage,
            descriptor=descriptor,
            selection=Selection.from_bytes(_json(actor["selection"])),
            roots={key: Path(value) for key, value in actor["roots"].items()},
            authorization=bootstrap_authority,
            review=self.engine.fixture.review,
            budget_microusd=self.template["budget_microusd"],
            max_calls=self.template["max_calls"],
            expected_runtime_sha256=self.engine.candidate.expected_runtime,
            expected_feedback_provenance_sha256=written["provenance"]["sha256"],
            input_files=list(controls),
            expected_input_hashes=controls,
        )
        with self.supplied():
            result = candidate_improvement.run_candidate_improvement(
                stage, transport=self.transport()
            )
        self.assertEqual(result["disposition"], "materialized")
        self.assertEqual(result["improver_agent_sha256"], self.actor_id(actor))
        self.assertEqual(result["parent_agent_sha256"], self.base.candidate_id)
        self.bootstrap = h.files(bootstrap), h.files(stage), bootstrap_authority.summary()
        self.bootstrap_directories = bootstrap, stage
        # The first future interface access must happen AFTER these assertions.
        return self

    def actor_executor(self, actor):
        value = copy.deepcopy(self.base.to_record()["generation"]["executor"])
        value["mounts"] = [
            ["/agent", actor["roots"]["agent"]],
            ["/runner", actor["roots"]["runner"]],
        ]
        return value

    @staticmethod
    def actor_id(actor):
        from buddha.releases import Selection, _json

        return Selection.from_bytes(_json(actor["selection"])).agent_sha256

    @staticmethod
    def transport():
        from buddha.gateway import RawHTTPTransport

        return RawHTTPTransport(allow_paid=True)

    def supplied(self):
        from contextlib import ExitStack

        import test_gateway

        stack = ExitStack()
        stack.enter_context(
            patch.dict(os.environ, {"OPENAI_API_KEY": test_gateway.KEY}, clear=True)
        )
        stack.enter_context(patch("buddha.executor.run_container", side_effect=self.execute))
        stack.enter_context(
            patch("http.client.HTTPSConnection", side_effect=AssertionError("real HTTPS"))
        )
        stack.enter_context(
            patch.object(self.shared, "_restore", side_effect=AssertionError("fake search"))
        )
        stack.enter_context(
            patch.object(
                self.shared, "_witness_location", side_effect=AssertionError("fake search layout")
            )
        )
        return stack

    def execute(self, spec, *, initial, handle, **kwargs):
        from buddha.releases import _json

        owner = handle.__self__.gateway.directory
        self.events.append((owner, initial["format"]))
        if "candidate-improvement-worker" in initial["format"]:
            return self.improve(spec, initial, handle)
        if spec.role == "agent":
            self.assertEqual(initial["task"]["id"], TASK_ID)
            self.assertIs(type(initial["task"]["id"]), str)
            self.assertEqual(initial["task"]["count"], 2)
            raw = (dict(spec.mounts)["/agent"] / "candidate.py").read_bytes()
            self.h.unusable_task = TASK_ID if b"metric-ineligible" in raw else None
            self.generated.append(
                {
                    "owner": owner,
                    "agent_id": initial["agent_sha256"],
                    "source": raw,
                    "task": copy.deepcopy(initial["task"]),
                }
            )
            if b"checked-generation-failure" in raw:
                self.engine.workers += 1
                handle({"type": "done", "status": "failed", "reason": "agent_error", "answers": []})
                return self.engine.execution(spec)
            manifest = json.loads((owner / "manifest.json").read_bytes())
            record = self.base.to_record()
            record["generation"]["selection"] = manifest["selection"]
            self.h.programs[initial["agent_sha256"]] = {
                "record": record,
                "callbacks": 1,
                "answers": [self.literal, ""],
                "distinct": 2,
                "utility": self.baseline_utility if raw.startswith(b"# supplied source: S") else 7,
            }
        for sentinel in (b"VALIDATION-ONLY-SENTINEL", b"FINAL-ONLY-SENTINEL", b"dataset_base64"):
            if spec.role == "agent":
                self.assertNotIn(sentinel, _json(initial))
        return self.original_execute(spec, initial=initial, handle=handle, **kwargs)

    def improve(self, spec, initial, handle):
        from buddha.executor import ExecutorError
        from buddha.releases import _json

        owner = handle.__self__.gateway.directory
        raw = (dict(spec.mounts)["/agent"] / "candidate.py").read_bytes()
        detached = initial["format"] == "buddha.candidate-improvement-worker.v3"
        witness = "witness" in owner.parts
        cell = None
        if "cells" in owner.parts:
            suffix = owner.parts[owner.parts.index("cells") + 1 :]
            cell = tuple(int(value) for value in suffix[:4])
        if not detached:
            self.assertTrue(witness)
            self.assertNotIn(initial["agent_sha256"], {self.actor_id(item) for item in self.fixed})
        elif cell is not None:
            start, repetition, arm, slot = cell
            self.assertFalse(witness)
            study = Path(*owner.parts[: owner.parts.index("cells")])
            for common_start, common_repetition in self.expected_common[study]:
                common = study / "common" / str(common_start) / str(common_repetition)
                for role, status in (("screen", "complete"), ("witness", "passed")):
                    publication = common / role / "report.json"
                    self.assertTrue(publication.is_file(), "all common checks precede counted work")
                    self.assertEqual(json.loads(publication.read_bytes())["status"], status)
            self.assertEqual(initial["agent_sha256"], self.actor_id(self.fixed[arm]))
            self.assertEqual(raw, (self.root / ("I" + str(arm)) / "candidate.py").read_bytes())
            self.assertEqual(
                initial["parent_bundle"]["agent_sha256"],
                sha(_json({"candidate.py": sha(initial["parent_bundle"]["source"].encode())})),
            )
        notes = [json.loads(row["note"]) for row in initial["feedback"]]
        self.assertEqual([row["task"]["id"] for row in initial["feedback"]], [TASK_ID])
        for note in notes:
            measured = note.get("measurements", note)
            self.assertEqual(
                measured["answers"],
                [{"position": 0, "text": self.literal}, {"position": 1, "text": ""}],
            )
            self.assertEqual(measured["omitted_answer_positions"], 0)
        mode = "valid"
        if witness:
            mode = "rejected" if b"failed-own-witness" in raw else "valid"
            child = source("W-only-validity-" + initial["agent_sha256"])
        elif cell is None:
            child = source("bootstrap-counted-child")
        else:
            start, repetition, arm, slot = cell
            child = source("OWN-C-" + "-".join(str(value) for value in cell))
            if cell in {(1, 1, 0, 0), (1, 1, 1, 0)}:
                child = source("OWN-C-shared-across-arms")
            outcome = self.outcomes.get(cell, "valid")
            if outcome == "failed":
                child = source("checked-generation-failure-" + "-".join(map(str, cell)))
            elif outcome == "rejected":
                mode = "rejected"
            elif outcome == "failed_witness":
                child = source("failed-own-witness")
            elif outcome == "duplicate":
                child = (self.root / ("S" + str(start)) / "candidate.py").read_bytes()
            elif outcome == "ineligible":
                child = source("metric-ineligible")
        value = (
            {}
            if mode == "rejected"
            else {
                "source": child.decode(),
                "hypothesis": "Supplied finite mutation with complete feedback.",
            }
        )
        event = {
            "owner": owner,
            "cell": cell,
            "witness": witness,
            "agent_id": initial["agent_sha256"],
            "source": raw,
            "parent": copy.deepcopy(initial.get("parent_bundle")),
            "feedback": copy.deepcopy(initial["feedback"]),
            "physical_sends": 0,
        }
        self.improvements.append(event)
        self.engine.workers += 1
        ready = {
            "type": "ready",
            "agent_sha256": initial["agent_sha256"],
            "feedback_sha256": sha(_json(initial["feedback"])),
            "runtime_sha256": self.engine.candidate.expected_runtime,
        }
        if detached:
            ready["parent_agent_sha256"] = initial["parent_bundle"]["agent_sha256"]
        handle(ready)
        request = self.engine.candidate.request(
            text=_json({"operator": raw.decode(), "feedback": initial["feedback"]}).decode()
        )
        connection = self.engine.fixture.connection(
            self.engine.fixture.response(choices=[{"message": {"content": _json(value).decode()}}])
        )
        unknown = self.unknown_once and witness and owner.is_relative_to(self.unknown_scope)
        if unknown:
            self.unknown_once = False
            connection.getresponse.side_effect = TimeoutError("synthetic unknown; do not replace")
        with patch("http.client.HTTPSConnection", return_value=connection):
            reply = handle(request)
        event["physical_sends"] = connection.request.call_count
        self.engine.physical_sends += connection.request.call_count
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
            return self.engine.execution(spec)
        if self.known_once and cell is not None and not witness:
            self.known_once = False
            self.known_owner = owner
            raise ExecutorError(
                "known reply interruption", cleanup_status="removed", container_id="f" * 64
            )
        if self.known_replay and owner == self.known_owner:
            self.assertEqual(
                event["physical_sends"], 0, "original completed operation must reuse its reply"
            )
        handle(
            {
                "type": "done",
                "status": "failed" if mode == "rejected" else "complete",
                "reason": "invalid_proposal" if mode == "rejected" else "complete",
                "proposal": {
                    "status": "captured",
                    "value": value,
                    "sha256": sha(_json(value)),
                    "bytes": len(_json(value)),
                },
            }
        )
        return self.engine.execution(spec)

    def declaration(self, api):
        record = {
            "format": "buddha.improver-study.v1",
            "experiment_id": "offline-controlled-improvers",
            "improvers": copy.deepcopy(self.fixed),
            "starts": copy.deepcopy(self.starts),
            "repetitions": 2,
            "descendant_opportunities": 2,
            "proposal_template": copy.deepcopy(self.template),
            "selection": {"method": "latest", "max_active": 2, "seed": 7, "finalist_iteration": 2},
            "witness_policy": dict(self.shared.MUTATION_WITNESS_POLICY),
            "source_copy": dict(self.shared.SOURCE_COPY_POLICY),
            "consumer_sources": {
                str(Path(api.__file__).resolve()): sha(Path(api.__file__).read_bytes())
            },
            "assessment": {
                "status": "not_frozen",
                "reason": "engineering-only fixture; no sealed or target-repair evidence",
            },
        }
        self.recompute_limits(record)
        return record

    def recompute_limits(self, record):
        screen = record["starts"][0]["screen"]
        generation, native = screen["generation"], screen["native"]
        task_count = len(screen["selected_ids"])
        screen_money = task_count * (
            generation["budget_microusd"] + 2 * native["budget_microusd"] + 1
        )
        screen_calls = task_count * (generation["max_calls"] + 2 * native["max_calls"] + 1)
        witness_money = self.template["budget_microusd"] + generation["budget_microusd"]
        witness_calls = self.template["max_calls"] + generation["max_calls"]
        common = {
            "budget_microusd": screen_money + witness_money,
            "max_calls": screen_calls + witness_calls,
        }
        m = record["descendant_opportunities"]
        arm = {
            "budget_microusd": m
            * (self.template["budget_microusd"] + screen_money + witness_money),
            "max_calls": m * (self.template["max_calls"] + screen_calls + witness_calls),
        }
        conditions = len(record["starts"]) * record["repetitions"]
        record["limits"] = {
            "common_cell": common,
            "arm_cell": arm,
            "study": {key: conditions * common[key] + 2 * conditions * arm[key] for key in common},
        }

    def prepare_study(self, label, record, *, trial=False):
        from buddha.authorization import Authorization
        from buddha.releases import _json

        directory, declaration = self.root / label, self.root / (label + ".json")
        declaration.write_bytes(_json(record))
        limits = record["limits"]["study"]
        if trial:
            directory, authority = self.trial_authority(label, limits)
        else:
            authority = Authorization.create(
                self.root / (label + "-authority.sqlite3"),
                authorization_id="offline-" + label,
                budget_microusd=limits["budget_microusd"],
                max_calls=limits["max_calls"],
                scope="source screen: " + self.base.comparison_key(),
            )
        before = self.engine.physical_sends, len(self.events)
        self.api.prepare_improver_study(
            directory,
            declaration=declaration,
            expected_sha256=sha(declaration.read_bytes()),
            authorization=authority,
            review=self.engine.fixture.review,
            expected_runtime_sha256=self.engine.candidate.expected_runtime,
        )
        self.assertEqual((self.engine.physical_sends, len(self.events)), before)
        self.expected_common[directory] = [
            (start, repetition)
            for start in range(len(record["starts"]))
            for repetition in range(record["repetitions"])
        ]
        return directory, declaration, authority

    def run_study(self, directory):
        with self.supplied():
            return self.api.run_improver_study(directory, transport=self.transport())

    def trial_authority(self, label, limits):
        from buddha import trial_fence
        from buddha.authorization import Authorization
        from buddha.releases import _json

        root = self.root / (label + "-trial")
        root.mkdir()
        definition = root / "definition.json"
        definition.write_bytes(_json({"fixture": "finite-consumer phase fence only"}))
        definition_sha = sha(definition.read_bytes())
        phases, authorities = {}, {}
        for phase in ("search", "validation", "final"):
            (root / phase).mkdir()
            scope = trial_fence._scope_text(trial_fence._TrialScope(root, definition_sha, phase))
            caps = limits if phase == "search" else {"budget_microusd": 1, "max_calls": 1}
            authority = Authorization.create(
                self.root / (label + "-" + phase + ".sqlite3"),
                authorization_id="offline-" + label + "-" + phase,
                scope=scope,
                **caps,
            )
            summary = authority.summary()
            phases[phase] = {
                "authorization_path": str(authority.path),
                **{
                    key: summary[key]
                    for key in (
                        "authorization_id",
                        "terms_sha256",
                        "budget_microusd",
                        "max_calls",
                        "scope",
                    )
                },
                "purpose": "source screen: " + self.base.comparison_key()
                if phase == "search"
                else "synthetic unused " + phase,
            }
            authorities[phase] = authority
        funding = root / "funding.json"
        funding.write_bytes(
            _json(
                {
                    "format": "buddha.evaluation-trial-funding.v1",
                    "root": str(root),
                    "definition_sha256": definition_sha,
                    "total_budget_microusd": sum(row["budget_microusd"] for row in phases.values()),
                    "total_max_calls": sum(row["max_calls"] for row in phases.values()),
                    "phases": phases,
                }
            )
        )
        (root / ".buddha-evaluation-trial.json").write_bytes(
            _json(
                {
                    "format": "buddha.evaluation-trial-root.v1",
                    "root": str(root),
                    "definition_sha256": definition_sha,
                    "funding_sha256": sha(funding.read_bytes()),
                }
            )
        )
        return root / "search/study", authorities["search"]

    def freeze_trial(self, directory, authority):
        from buddha import trial_fence

        with trial_fence.lease(authority.path, authority._terms(), directory=directory):
            (directory.parent.parent / "freeze").mkdir()

    def inspect(self, directory, authority):
        return self.api.inspect_improver_study(
            directory,
            authorization=authority.path,
            expected_report_sha256=sha((directory / "report.json").read_bytes()),
        )

    def refused(self, callable_):
        before = self.engine.physical_sends, len(self.events)
        with self.assertRaises(self.api.ImproverStudyError):
            callable_()
        self.assertEqual((self.engine.physical_sends, len(self.events)), before)

    def owner_paths(self, directory):
        return {path.parent for path in directory.rglob("owners/*/manifest.json")}

    def totals(self, authority, directory):
        runs = [
            row
            for row in authority.summary()["runs"]
            if Path(row["directory"]).is_relative_to(directory)
        ]
        return {key: sum(row[key] for row in runs) for key in TOTALS}

    def assert_accounting(self, directory, authority, report, record):
        runs = [
            row
            for row in authority.summary()["runs"]
            if Path(row["directory"]).is_relative_to(directory)
        ]

        def total(rows):
            return {key: sum(row[key] for row in rows) for key in TOTALS}

        self.assertEqual(report["costs"]["totals"], total(runs))
        self.assertEqual(
            report["costs"]["common"],
            total(
                [row for row in runs if Path(row["directory"]).is_relative_to(directory / "common")]
            ),
        )
        self.assertEqual(
            report["costs"]["witness"],
            total(
                [
                    row
                    for row in runs
                    if "witness" in Path(row["directory"]).relative_to(directory).parts
                ]
            ),
        )
        cells = report["costs"]["cells"]
        keyed = {tuple(row[key] for key in COORDINATES[:3]): row for row in cells}
        expected = {
            (s, r, a)
            for s in range(len(record["starts"]))
            for r in range(record["repetitions"])
            for a in range(2)
        }
        self.assertEqual(len(cells), len(expected))
        self.assertEqual(set(keyed), expected)
        for coordinates, row in keyed.items():
            cell = directory / "cells" / "/".join(map(str, coordinates))
            self.assertEqual(
                {key: row[key] for key in TOTALS},
                total([run for run in runs if Path(run["directory"]).is_relative_to(cell)]),
            )
        for key in TOTALS:
            self.assertEqual(
                report["costs"]["common"][key] + sum(row[key] for row in cells),
                report["costs"]["totals"][key],
            )
        generation, native = (self.base.to_record()[name] for name in ("generation", "native"))
        for owner in self.owner_paths(directory):
            relative = owner.relative_to(directory).parts
            manifest = json.loads((owner / "manifest.json").read_bytes())
            if "proposal" in relative:
                section = self.template
            elif "evaluation" in relative:
                section = {"budget_microusd": 1, "max_calls": 1} if owner.name == "3" else native
            else:
                section = generation
            self.assertEqual(
                manifest["settings"],
                {key: section[key] for key in ("budget_microusd", "max_calls")},
            )

    def test_completed_common_witness_replays_after_external_sources_retire(self):
        self.fixture_before_new_api()
        from buddha import improver_study
        from buddha.gateway import RawHTTPTransport

        self.api = improver_study
        record = self.declaration(improver_study)
        record.update(starts=record["starts"][:1], repetitions=1, descendant_opportunities=1)
        record["selection"]["finalist_iteration"] = 1
        self.recompute_limits(record)
        self.outcomes = {(0, 0, arm, 0): "rejected" for arm in range(2)}
        directory, declaration, authority = self.prepare_study("retirement-study", record)
        report = self.run_study(directory)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["coverage"]["completed_common"], 1)
        self.assertEqual([row["status"] for row in report["decisions"]], ["rejected"] * 2)
        self.assertEqual(
            json.loads((directory / "common/0/0/witness/report.json").read_bytes())["status"],
            "passed",
        )

        def snapshot():
            return (
                self.h.files(self.root),
                authority.summary(),
                self.engine.physical_sends,
                self.engine.workers,
                len(self.events),
                len(self.improvements),
                len(self.generated),
            )

        retired = []
        try:
            for name in ("I0", "I1", "S0", "S1"):
                original, destination = self.root / name, self.root / (name + "-retired")
                original.rename(destination)
                retired.append((original, destination))
            before = snapshot()
            destination = self.root / "fresh-retirement-study"
            with (
                self.h.readonly(),
                patch.dict(os.environ, {}, clear=True),
                patch("buddha.trial_fence.work", side_effect=AssertionError("trial work entered")),
                patch(
                    "buddha.native_pipeline._exclusive",
                    side_effect=AssertionError("local writer lock"),
                ),
            ):
                # Retired controls still prevent any fresh, active preparation.
                with self.assertRaises(self.api.ImproverStudyError):
                    self.api.prepare_improver_study(
                        destination,
                        declaration=declaration,
                        expected_sha256=sha(declaration.read_bytes()),
                        authorization=authority,
                        review=self.engine.fixture.review,
                        expected_runtime_sha256=self.engine.candidate.expected_runtime,
                    )
                self.assertFalse(destination.exists())
                # Original completed custody is sufficient for passive replay.
                self.assertEqual(self.inspect(directory, authority), report)
                self.assertEqual(
                    self.api.run_improver_study(
                        directory, transport=RawHTTPTransport(allow_paid=False)
                    ),
                    report,
                )
            self.assertEqual(snapshot(), before)
        finally:
            for original, destination in reversed(retired):
                destination.rename(original)

    def test_finite_fixed_operators_common_conditions_negative_slots_and_original_recovery(self):
        self.fixture_before_new_api()
        observe_fixture_workers(self, self)
        # Actual initial RED belongs here, after genuine old measured/role APIs.
        from buddha import improver_study
        from buddha.releases import Selection, _json

        self.api = improver_study
        record = self.declaration(improver_study)
        directory, declaration, authority = self.prepare_study("study", record)
        # Pure malformed declarations reuse components, not expensive measurements.
        for label, change in (
            ("boolean-repetition", lambda r: r.update(repetitions=True)),
            ("omitted-future-budget", lambda r: r["limits"]["study"].update(budget_microusd=1)),
            (
                "different-fixed-count",
                lambda r: r["improvers"].append(copy.deepcopy(r["improvers"][0])),
            ),
            ("mixed-typed-task", lambda r: r["starts"][1]["screen"].update(selected_ids=[1])),
            ("unapproved-witness-depth", lambda r: r["witness_policy"].update(depth=2)),
        ):
            malformed = copy.deepcopy(record)
            change(malformed)
            path = self.root / (label + ".json")
            path.write_bytes(_json(malformed))
            destination = self.root / label
            before = authority.summary(), self.engine.physical_sends
            with self.subTest(declaration=label), self.assertRaises(self.api.ImproverStudyError):
                self.api.prepare_improver_study(
                    destination,
                    declaration=path,
                    expected_sha256=sha(path.read_bytes()),
                    authorization=authority,
                    review=self.engine.fixture.review,
                    expected_runtime_sha256=self.engine.candidate.expected_runtime,
                )
            self.assertFalse(destination.exists())
            self.assertEqual((authority.summary(), self.engine.physical_sends), before)
        original_declaration = declaration.read_bytes()
        genuine_prepare = self.lower.prepare_candidate_improvement
        injected = []

        def change_after_preparation(stage, **values):
            result = genuine_prepare(stage, **values)
            if "cells" in stage.parts and "witness" not in stage.parts and not injected:
                injected.append(stage / "owners/0")
                declaration.write_bytes(original_declaration + b" ")
            return result

        with patch.object(
            self.lower, "prepare_candidate_improvement", side_effect=change_after_preparation
        ):
            with self.assertRaises(self.api.ImproverStudyError):
                self.run_study(directory)
        self.assertEqual(len(injected), 1)
        self.assertFalse(any(owner == injected[0] for owner, _ in self.events))
        declaration.write_bytes(original_declaration)
        original_manifest = (injected[0] / "manifest.json").read_bytes()
        self.known_once = True
        partial = self.run_study(directory)
        self.assertEqual(partial["status"], "incomplete")
        # The existing protected stage reports an interrupted worker without
        # DONE as protocol. Keep its raw execution cause and public envelope.
        self.assertEqual(partial["reason"], "protocol")
        self.assertEqual(
            partial["position"],
            {"start": 0, "repetition": 0, "arm": 0, "slot": 0, "stage": "proposal"},
        )
        self.assertEqual(partial["child"]["owner"], str(injected[0]))
        self.assertEqual(partial["child"]["status"], "incomplete")
        self.assertEqual(partial["child"]["reason"], "protocol")
        attempt = Path(partial["child"]["attempt"])
        session_raw = (attempt / "session/report.json").read_bytes()
        self.assertEqual(sha(session_raw), partial["child"]["outcome"]["session_report_sha256"])
        session = json.loads(session_raw)
        self.assertEqual(session["reason"], "execution")
        self.assertEqual(session["execution"]["cleanup_status"], "removed")
        self.assertIsNone(partial["child"]["outcome"]["terminal"]["done_status"])
        self.assertEqual(
            json.loads((injected[0].parents[1] / partial["child"]["observation"]).read_bytes()),
            partial["child"],
        )
        self.assertEqual(
            partial["coverage"],
            {
                "expected_common": 4,
                "completed_common": 4,
                "expected_cells": 8,
                "completed_cells": 0,
                "expected_opportunities": 16,
                "attempted_opportunities": 1,
                "completed_opportunities": 0,
                "in_flight_opportunities": 1,
                "unattempted_opportunities": 15,
            },
        )
        self.assertEqual(self.known_owner, injected[0])
        self.assertFalse((injected[0].parents[2] / "screen").exists())
        self.assertGreater(self.totals(authority, directory)["spent_microusd"], 0)
        self.assertEqual(self.totals(authority, directory)["reserved_microusd"], 0)
        fixed_file = self.root / "I0/candidate.py"
        original_fixed = fixed_file.read_bytes()
        altered_witness = []

        def change_common_control_after_witness_prepare(stage, **values):
            result = genuine_prepare(stage, **values)
            if "cells" in stage.parts and "witness" in stage.parts and not altered_witness:
                altered_witness.append(stage / "owners/0")
                fixed_file.write_bytes(original_fixed + b"# changed after preparation\n")
            return result

        self.known_replay = True
        with patch.object(
            self.lower,
            "prepare_candidate_improvement",
            side_effect=change_common_control_after_witness_prepare,
        ):
            with self.assertRaises(self.api.ImproverStudyError) as stopped:
                self.run_study(directory)
        self.assertEqual(len(altered_witness), 1, str(stopped.exception))
        self.assertFalse(any(owner == altered_witness[0] for owner, _ in self.events))
        fixed_file.write_bytes(original_fixed)
        report = self.run_study(directory)
        self.assertEqual(report["status"], "complete")
        self.assertEqual((injected[0] / "manifest.json").read_bytes(), original_manifest)
        self.assertEqual(
            report["coverage"],
            {
                "expected_common": 4,
                "completed_common": 4,
                "expected_cells": 8,
                "completed_cells": 8,
                "expected_opportunities": 16,
                "attempted_opportunities": 16,
                "completed_opportunities": 16,
                "in_flight_opportunities": 0,
                "unattempted_opportunities": 0,
            },
        )
        self.assertEqual(len(report["decisions"]), 16)
        self.assertEqual(
            {
                tuple(row[key] for key in ("start", "repetition", "arm", "slot"))
                for row in report["decisions"]
            },
            {
                (start, repetition, arm, slot)
                for start in range(2)
                for repetition in range(2)
                for arm in range(2)
                for slot in range(2)
            },
        )
        negative = {
            (0, 0, 0, 0): "candidate_execution_failed",
            (0, 0, 1, 0): "rejected",
            (0, 1, 1, 0): "mutation_witness_failed",
            (0, 1, 0, 1): "duplicate",
            (1, 0, 0, 0): "ineligible",
        }
        self.assertEqual(
            {tuple(row[key] for key in COORDINATES): row["status"] for row in report["decisions"]},
            {
                coordinate: negative.get(coordinate, "admitted")
                for coordinate in {
                    (s, r, a, i)
                    for s in range(2)
                    for r in range(2)
                    for a in range(2)
                    for i in range(2)
                }
            },
        )
        self.assertEqual(report["assessment"]["status"], "not_ready")
        self.assertEqual(report["assessment"]["target_repair"], "not_assessed")
        self.assertFalse(
            (directory / "freeze/ready.json").exists(),
            "no scientific readiness without frozen analysis",
        )
        self.assertEqual(len(report["selections"]), 8)
        cross_arm = [
            json.loads((directory / "cells/1/1" / str(arm) / "0/screen/report.json").read_bytes())
            for arm in range(2)
        ]
        self.assertEqual(cross_arm[0]["candidate_id"], cross_arm[1]["candidate_id"])
        cross_arm_owners = [
            json.loads(
                (
                    directory
                    / "cells/1/1"
                    / str(arm)
                    / "0/screen/tasks/0/generation/owners/0/manifest.json"
                ).read_bytes()
            )
            for arm in range(2)
        ]
        self.assertNotEqual(cross_arm_owners[0]["run_id"], cross_arm_owners[1]["run_id"])
        witness_ids = {
            row["agent_id"]
            for row in self.generated
            if row["owner"].is_relative_to(directory)
            and "witness" in row["owner"].relative_to(directory).parts
        }
        for selected in report["selections"]:
            self.assertNotIn(selected["candidate_id"], witness_ids)
            saved_source = Path(selected["source"]["path"]).read_bytes()
            self.assertEqual(sha(saved_source), selected["source"]["sha256"])
            self.assertIn(b"OWN-C-", saved_source)
            self.assertNotIn(b"W-only-validity", saved_source)
        self.assertTrue((directory / "freeze/selections.json").is_file())
        self.assertEqual(len(list((directory / "common").glob("*/*/screen/report.json"))), 4)
        common_reports = [
            json.loads(path.read_bytes())
            for path in (directory / "common").glob("*/*/screen/report.json")
        ]
        self.assertEqual(len({row["controls_sha256"] for row in common_reports}), 1)
        first_owner = json.loads(
            (directory / "common/0/0/screen/tasks/0/generation/owners/0/manifest.json").read_bytes()
        )
        original_inputs = {
            row["path"]: row["sha256"] for row in first_owner["invocation"]["inputs"]
        }
        for path in [
            Path(self.api.__file__).resolve(),
            declaration,
            *(
                self.root / (kind + str(index)) / "candidate.py"
                for kind in ("S", "I")
                for index in range(2)
            ),
        ]:
            self.assertEqual(original_inputs[str(path)], sha(path.read_bytes()))
        self.assertEqual(
            len(
                [
                    row
                    for row in self.generated
                    if row["owner"].is_relative_to(directory / "common")
                    and "witness" not in row["owner"].relative_to(directory).parts
                ]
            ),
            4,
        )
        self.assertFalse((directory / "cells/0/0/1/0/screen").exists())
        self.assertFalse((directory / "cells/0/1/0/1/screen").exists())
        self.assertFalse((directory / "cells/0/0/0/0/screen/tasks/0/evaluation").exists())
        self.assertTrue(
            all(
                owner.relative_to(directory).parts.count("witness") <= 1
                for owner in self.owner_paths(directory)
            )
        )
        self.assertFalse(
            any(
                "validation" in part or "final" == part
                for owner in self.owner_paths(directory)
                for part in owner.relative_to(directory).parts
            )
        )
        counted = [
            event
            for event in self.improvements
            if event["cell"] is not None
            and not event["witness"]
            and event["owner"].is_relative_to(directory)
        ]
        latest = {event["owner"]: event for event in counted}
        self.assertEqual(len(latest), 16)
        first_invocations = {}
        for event in counted:
            first_invocations.setdefault(event["owner"], event["cell"])
        expected_order = []
        for slot in range(2):
            for start in range(2):
                for repetition in range(2):
                    first_arm = (start + repetition + slot) % 2
                    expected_order.extend(
                        (start, repetition, arm, slot) for arm in (first_arm, 1 - first_arm)
                    )
        self.assertEqual(list(first_invocations.values()), expected_order)
        self.assertEqual(
            [tuple(row[key] for key in COORDINATES) for row in report["decisions"]], expected_order
        )
        decisions = {tuple(row[key] for key in COORDINATES): row for row in report["decisions"]}

        def original_reference(stage):
            return {
                "directory": str(stage),
                "authorization": str(authority.path),
                "report_sha256": sha((stage / "report.json").read_bytes()),
            }

        # Validate EVERY real counted worker invocation, including the same-owner
        # known-reply retry, against its OWN condition/arm's checked prefix.
        self.assertEqual(record["selection"]["method"], "latest")
        for event in counted:
            start, repetition, arm, slot = event["cell"]
            cell = directory / "cells" / str(start) / str(repetition) / str(arm)
            current = cell / str(slot)
            plan = json.loads((current / "plan.json").read_bytes())
            prior = [decisions[(start, repetition, arm, index)] for index in range(slot)]
            eligible = [row for row in prior if row["status"] == "admitted"]
            expected_parent_path = (
                (cell / str(eligible[-1]["slot"]) / "screen")
                if eligible
                else (directory / "common" / str(start) / str(repetition) / "screen")
            )
            expected_parent = original_reference(expected_parent_path)
            self.assertEqual(plan["parent"], expected_parent)
            parent_report = json.loads((expected_parent_path / "report.json").read_bytes())
            parent_screen = json.loads((expected_parent_path / "screen.json").read_bytes())
            generation = parent_screen["generation"]
            expected_source = (
                Path(generation["roots"]["agent"]) / generation["entrypoint"]
            ).read_bytes()
            self.assertEqual(event["agent_id"], self.actor_id(self.fixed[arm]))
            self.assertNotIn(b"OWN-C-", event["source"])
            self.assertNotIn("W-only-validity", event["parent"]["source"])
            self.assertEqual(event["parent"]["agent_sha256"], parent_report["candidate_id"])
            self.assertEqual(event["parent"]["source"].encode(), expected_source)
            context = json.loads((event["owner"].parents[1] / "context.json").read_bytes())
            recipe = json.loads(Path(context["descriptor"]).read_bytes())
            self.assertEqual(recipe["feedback"]["path"], str(current / "feedback/feedback.json"))
            provenance = json.loads((current / "feedback/provenance.json").read_bytes())
            self.assertEqual(provenance["reference"], expected_parent)
            expected_history = []
            for previous in prior:
                if previous["status"] != "candidate_execution_failed":
                    continue
                previous_path = cell / str(previous["slot"])
                previous_plan = json.loads((previous_path / "plan.json").read_bytes())
                failed_report = json.loads((previous_path / "screen/report.json").read_bytes())
                proposal_report = json.loads((previous_path / "proposal/report.json").read_bytes())
                self.assertEqual(failed_report["disposition"], "candidate_execution_failed")
                self.assertEqual(proposal_report["disposition"], "materialized")
                self.assertEqual(
                    proposal_report["improver_agent_sha256"], self.actor_id(self.fixed[arm])
                )
                expected_history.append(
                    {
                        "parent": previous_plan["parent"],
                        "proposal": original_reference(previous_path / "proposal"),
                        "screen": original_reference(previous_path / "screen"),
                    }
                )
            self.assertEqual(provenance.get("failure_history", []), expected_history)
            if expected_history:
                self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v5")
                self.assertEqual(
                    provenance["improver_agent_sha256"], self.actor_id(self.fixed[arm])
                )
            else:
                self.assertNotIn("failure_history", provenance)
            manifest = json.loads((event["owner"] / "manifest.json").read_bytes())
            bindings = {row["path"]: row["sha256"] for row in manifest["invocation"]["inputs"]}
            for name in ("source", "split", "feedback", "provenance"):
                packet_path = current / "feedback" / (name + ".json")
                self.assertEqual(bindings[str(packet_path)], sha(packet_path.read_bytes()))
            parent_data = Path(recipe["task_parent"]["path"])
            self.assertTrue(
                parent_data.is_relative_to(directory),
                "literal measured parent remains retained data after producer retirement",
            )
            self.assertEqual(parent_data.read_bytes(), event["parent"]["source"].encode())
            if slot == 0:
                self.assertEqual(
                    event["parent"]["source"].encode(),
                    (self.root / ("S" + str(start)) / "candidate.py").read_bytes(),
                )
        for start in range(2):
            for repetition in range(2):
                initial = [
                    event
                    for event in latest.values()
                    if event["cell"][:2] == (start, repetition) and event["cell"][3] == 0
                ]
                self.assertEqual(len(initial), 2)
                self.assertEqual(initial[0]["parent"], initial[1]["parent"])
                self.assertEqual(initial[0]["feedback"], initial[1]["feedback"])
                for arm in range(2):
                    plan = json.loads(
                        (
                            directory
                            / "cells"
                            / str(start)
                            / str(repetition)
                            / str(arm)
                            / "0/plan.json"
                        ).read_bytes()
                    )
                    self.assertEqual(
                        plan["parent"]["directory"],
                        str(directory / "common" / str(start) / str(repetition) / "screen"),
                    )
        repaired = latest[directory / "cells/0/0/0/1/proposal/owners/0"]
        note = json.loads(repaired["feedback"][0]["note"])
        self.assertEqual(len(note["failures"]), 1)
        self.assertEqual(note["failures"][0]["improver_id"], self.actor_id(self.fixed[0]))
        self.assertIn("checked-generation-failure", note["newest_failure"]["source"])
        self.assertEqual(note["newest_failure"]["source_omitted_utf8_bytes"], 0)
        for coordinate in ((0, 0, 0, 1), (0, 0, 1, 1), (0, 1, 1, 1)):
            key = (
                directory
                / "cells"
                / "/".join(str(value) for value in coordinate)
                / "proposal/owners/0"
            )
            self.assertEqual(
                latest[key]["parent"]["source"].encode(),
                (self.root / "S0/candidate.py").read_bytes(),
            )
        self.assertTrue(
            any(
                event["parent"]["source"].encode()
                != (self.root / ("S" + str(event["cell"][0])) / "candidate.py").read_bytes()
                for event in latest.values()
                if event["cell"][3] == 1
            )
        )
        totals = self.totals(authority, directory)
        self.assert_accounting(directory, authority, report, record)
        self.assertEqual(report["costs"]["totals"], totals)
        self.assertEqual(
            report["costs"]["common"]["spent_microusd"]
            + sum(row["spent_microusd"] for row in report["costs"]["cells"]),
            totals["spent_microusd"],
        )
        self.assertGreater(report["costs"]["common"]["spent_microusd"], 0)
        self.assertGreater(report["costs"]["witness"]["spent_microusd"], 0)
        for row in report["costs"]["cells"]:
            self.assertLessEqual(
                row["spent_microusd"], record["limits"]["arm_cell"]["budget_microusd"]
            )
        self.assertEqual(totals["reserved_microusd"], 0)
        funded = {
            Path(row["directory"])
            for row in authority.summary()["runs"]
            if Path(row["directory"]).is_relative_to(directory)
        }
        self.assertEqual(funded, self.owner_paths(directory))
        self.assertTrue(all(not row["active"] for row in authority.summary()["runs"]))
        original_row = next(
            row for row in authority.summary()["runs"] if row["directory"] == str(self.known_owner)
        )
        self.assertEqual(original_row["operation_count"], 1)
        self.assertEqual(
            self.bootstrap,
            (
                self.h.files(self.bootstrap_directories[0]),
                self.h.files(self.bootstrap_directories[1]),
                self.h.authorities[0].summary(),
            ),
        )
        self.passive_and_corruptions(directory, declaration, authority, report)
        # One short UNKNOWN prefix reuses source/components, not a second full grid.
        other, _, other_authority = self.prepare_study("unknown-study", record)
        self.unknown_scope, self.unknown_once = other, True
        partial = self.run_study(other)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["reason"], "unknown")
        self.assertEqual(
            partial["position"],
            {
                "start": 0,
                "repetition": 0,
                "arm": None,
                "slot": None,
                "stage": "common_witness_proposal",
            },
        )
        self.assertEqual(
            partial["child"]["owner"], str(other / "common/0/0/witness/proposal/owners/0")
        )
        self.assertEqual(partial["child"]["status"], "incomplete")
        self.assertEqual(partial["child"]["reason"], "unknown")
        self.assertEqual(partial["coverage"]["expected_opportunities"], 16)
        self.assertEqual(partial["coverage"]["completed_opportunities"], 0)
        self.assertEqual(partial["coverage"]["attempted_opportunities"], 0)
        self.assertEqual(partial["coverage"]["in_flight_opportunities"], 0)
        self.assertEqual(partial["coverage"]["unattempted_opportunities"], 16)
        self.assertGreater(other_authority.summary()["reserved_microusd"], 0)
        self.assertFalse(
            (other / "cells").exists() and any((other / "cells").rglob("manifest.json"))
        )
        before = self.engine.physical_sends, self.owner_paths(other), len(self.events)
        resumed = self.run_study(other)
        self.assertEqual(resumed["status"], "incomplete")
        self.assertEqual(resumed["reason"], "unknown")
        self.assertEqual(resumed["child"], partial["child"])
        self.assertEqual(
            (self.engine.physical_sends, self.owner_paths(other), len(self.events)), before
        )
        self.assertFalse((other / "report.json").exists())
        # A real new funded owner is deliberately left as terminal corruption.
        # Do not delete its funding row to make the old study look healthy again.
        plan = directory / "cells/0/0/0/1/proposal.json"
        packet = json.loads(plan.read_bytes())["feedback"]
        provenance = Path(packet["path"]).parent / "provenance.json"
        extra = directory / "cells/0/0/0/99"
        extra.mkdir()
        self.lower.prepare_candidate_improvement(
            extra / "proposal",
            descriptor=plan,
            selection=Selection.from_bytes(_json(self.fixed[0]["selection"])),
            roots={key: Path(value) for key, value in self.fixed[0]["roots"].items()},
            authorization=authority,
            review=self.engine.fixture.review,
            budget_microusd=self.template["budget_microusd"],
            max_calls=self.template["max_calls"],
            expected_runtime_sha256=self.engine.candidate.expected_runtime,
            expected_feedback_provenance_sha256=sha(provenance.read_bytes()),
        )
        self.refused(lambda: self.inspect(directory, authority))
        self.refused(lambda: self.run_study(directory))

    def test_two_prior_failed_edges_no_valid_descendant_and_completed_fenced_replay(self):
        self.fixture_before_new_api()
        from buddha import improver_study
        from buddha.gateway import RawHTTPTransport

        self.api = improver_study
        record = self.declaration(improver_study)
        record.update(starts=record["starts"][:1], repetitions=1, descendant_opportunities=3)
        record["selection"]["finalist_iteration"] = 3
        record["selection"]["method"] = "archive"
        self.baseline_utility = 9
        self.recompute_limits(record)
        self.outcomes = {(0, 0, 0, slot): "failed" for slot in range(3)} | {
            (0, 0, 1, 0): "rejected",
            (0, 0, 1, 1): "rejected",
        }
        directory, _, authority = self.prepare_study("multi-edge", record, trial=True)
        report = self.run_study(directory)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(
            report["coverage"],
            {
                "expected_common": 1,
                "completed_common": 1,
                "expected_cells": 2,
                "completed_cells": 2,
                "expected_opportunities": 6,
                "attempted_opportunities": 6,
                "completed_opportunities": 6,
                "in_flight_opportunities": 0,
                "unattempted_opportunities": 0,
            },
        )
        self.assertEqual(
            {tuple(row[key] for key in COORDINATES): row["status"] for row in report["decisions"]},
            {
                **{(0, 0, 0, i): "candidate_execution_failed" for i in range(3)},
                (0, 0, 1, 0): "rejected",
                (0, 0, 1, 1): "rejected",
                (0, 0, 1, 2): "admitted",
            },
        )
        latest = {
            event["owner"]: event
            for event in self.improvements
            if event["cell"] is not None and not event["witness"]
        }
        last = directory / "cells/0/0/0/2"
        note = json.loads(latest[last / "proposal/owners/0"]["feedback"][0]["note"])
        self.assertEqual(len(note["failures"]), 2)
        self.assertEqual(
            [row["improver_id"] for row in note["failures"]], [self.actor_id(self.fixed[0])] * 2
        )
        provenance = json.loads((last / "feedback/provenance.json").read_bytes())
        self.assertEqual(provenance["format"], "buddha.source-screen-feedback.v5")
        self.assertEqual(
            [row["proposal"]["directory"] for row in provenance["failure_history"]],
            [str(directory / "cells/0/0/0" / str(i) / "proposal") for i in range(2)],
        )
        self.assertEqual(note["newest_failure"]["source_omitted_utf8_bytes"], 0)
        self.assertIn("checked-generation-failure-0-0-0-1", note["newest_failure"]["source"])
        self.assertEqual(len(report["selections"]), 2)
        rows = {row["arm"]: row for row in report["selections"]}
        self.assertEqual(rows[0]["status"], "no_valid_descendant")
        self.assertIsNone(rows[0]["candidate_id"])
        self.assertIsNone(rows[0]["source"])
        self.assertFalse((directory / "freeze/sources/0.py").exists())
        self.assertEqual(rows[1]["status"], "selected")
        self.assertIsNotNone(rows[1]["candidate_id"])
        self.assertNotIn(rows[1]["candidate_id"], {self.base.candidate_id})
        common = json.loads((directory / "common/0/0/screen/report.json").read_bytes())
        counted = json.loads((directory / "cells/0/0/1/2/screen/report.json").read_bytes())
        self.assertGreater(
            common["admission"]["mean_utility"], counted["admission"]["mean_utility"]
        )
        self.assertEqual(
            rows[1]["candidate_id"],
            counted["candidate_id"],
            "S is excluded before descendant ranking even when S dominates C",
        )
        self.assert_accounting(directory, authority, report, record)
        self.freeze_trial(directory, authority)
        before = self.h.files(directory.parent.parent), authority.summary()
        with (
            self.h.readonly(),
            patch.dict(os.environ, {}, clear=True),
            patch(
                "buddha.native_pipeline._exclusive",
                side_effect=AssertionError("passive local lock"),
            ),
        ):
            self.assertEqual(self.inspect(directory, authority), report)
            self.assertEqual(
                self.api.run_improver_study(
                    directory, transport=RawHTTPTransport(allow_paid=False)
                ),
                report,
            )
        self.assertEqual((self.h.files(directory.parent.parent), authority.summary()), before)

    def test_preowner_refusals_use_correct_caps_sufficient_authority_and_full_grid_projection(self):
        self.fixture_before_new_api()
        from buddha import improver_study
        from buddha.authorization import Authorization
        from buddha.releases import _json, prepare_selection
        from buddha.search_evidence import MAX_FILES

        self.api = improver_study
        original = self.declaration(improver_study)
        cases = []
        for m in (True, 9):
            record = copy.deepcopy(original)
            record["descendant_opportunities"] = m
            record["selection"]["finalist_iteration"] = m
            self.recompute_limits(record)
            cases.append(("invalid-m-" + str(m), record))
        for location, field in (
            ("common_cell", "budget_microusd"),
            ("arm_cell", "max_calls"),
            ("study", "max_calls"),
        ):
            record = copy.deepcopy(original)
            record["limits"][location][field] += 1
            cases.append((location + "-" + field, record))
        record = copy.deepcopy(original)
        record["improvers"][1] = copy.deepcopy(record["improvers"][0]) | {"name": "evolved"}
        cases.append(("same-I-under-two-names", record))
        large = copy.deepcopy(original)
        for index in range(2, 8):
            actor = self.root / ("S" + str(index))
            actor.mkdir()
            (actor / "candidate.py").write_bytes(source("metadata-only-S" + str(index)))
            screen_record = copy.deepcopy(self.starts[0]["screen"])
            generation = screen_record["generation"]
            roots = {name: Path(value) for name, value in generation["roots"].items()} | {
                "agent": actor
            }
            selected = prepare_selection(
                self.engine.candidate.release, roots, capabilities=self.capabilities
            )
            generation.update(
                selection=selected.to_record(),
                roots={key: str(value) for key, value in roots.items()},
            )
            generation["executor"]["mounts"] = [
                ["/agent", str(actor)],
                ["/runner", str(roots["runner"])],
            ]
            large["starts"].append({"name": "S" + str(index), "screen": screen_record})
        large.update(repetitions=8, descendant_opportunities=8)
        large["selection"]["finalist_iteration"] = 8
        self.recompute_limits(large)
        # Every successful slot needs proposal1 + screen4 + witness2 owners;
        # manifest+ledger alone already exceed the unchanged full-tree ceiling.
        self.assertGreater(8 * 8 * 2 * 8 * 7 * 2, MAX_FILES)
        cases.append(("structural-whole-grid", large))
        authority = Authorization.create(
            self.root / "preowner-sufficient.sqlite3",
            authorization_id="offline-preowner",
            budget_microusd=max(row["limits"]["study"]["budget_microusd"] for _, row in cases) + 1,
            max_calls=max(row["limits"]["study"]["max_calls"] for _, row in cases) + 1,
            scope="source screen: " + self.base.comparison_key(),
        )
        for label, record in cases:
            declaration = self.root / (label + ".json")
            declaration.write_bytes(_json(record))
            destination = self.root / label
            before = (
                self.h.files(self.root),
                authority.summary(),
                len(self.events),
                self.engine.physical_sends,
            )
            with self.subTest(case=label), self.assertRaises(self.api.ImproverStudyError):
                self.api.prepare_improver_study(
                    destination,
                    declaration=declaration,
                    expected_sha256=sha(declaration.read_bytes()),
                    authorization=authority,
                    review=self.engine.fixture.review,
                    expected_runtime_sha256=self.engine.candidate.expected_runtime,
                )
            self.assertFalse(destination.exists())
            self.assertEqual(
                (
                    self.h.files(self.root),
                    authority.summary(),
                    len(self.events),
                    self.engine.physical_sends,
                ),
                before,
            )

    def test_actual_full_feedback_capacity_is_partial_and_final_fence_precedes_local_writers(self):
        self.fixture_before_new_api()
        from buddha import improver_study
        from buddha.releases import MAX_FEEDBACK_BYTES, ReleaseError

        self.api = improver_study
        record = self.declaration(improver_study)
        record.update(starts=record["starts"][:1], repetitions=1, descendant_opportunities=1)
        record["selection"]["finalist_iteration"] = 1
        self.recompute_limits(record)
        self.literal = '"' * (MAX_FEEDBACK_BYTES // 2 + 1024)
        directory, declaration, authority = self.prepare_study("capacity", record, trial=True)
        partial = self.run_study(directory)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["reason"], "feedback_capacity")
        self.assertEqual(
            partial["position"],
            {
                "start": 0,
                "repetition": 0,
                "arm": None,
                "slot": None,
                "stage": "common_witness_feedback",
            },
        )
        self.assertIsNone(partial["child"])
        self.assertEqual(
            partial["coverage"],
            {
                "expected_common": 1,
                "completed_common": 0,
                "expected_cells": 2,
                "completed_cells": 0,
                "expected_opportunities": 2,
                "attempted_opportunities": 0,
                "completed_opportunities": 0,
                "in_flight_opportunities": 0,
                "unattempted_opportunities": 2,
            },
        )
        self.assertTrue((directory / "common/0/0/screen/report.json").is_file())
        self.assertFalse((directory / "cells").exists())
        self.assertFalse((directory / "common/0/0/witness/proposal").exists())
        self.assertFalse((directory / "common/0/0/witness/feedback/feedback.json").exists())
        self.assertFalse((directory / "report.json").exists())
        self.assertFalse((directory / "freeze").exists())
        self.assertEqual(self.totals(authority, directory)["reserved_microusd"], 0)
        self.freeze_trial(directory, authority)
        before = (
            self.h.files(directory.parent.parent),
            authority.summary(),
            len(self.events),
            self.engine.physical_sends,
        )
        with patch(
            "buddha.native_pipeline._exclusive", side_effect=AssertionError("local writer lock")
        ) as local:
            with self.assertRaises(ReleaseError):
                self.run_study(directory)
            destination = directory.parent / "another-study"
            with self.assertRaises(ReleaseError):
                self.api.prepare_improver_study(
                    destination,
                    declaration=declaration,
                    expected_sha256=sha(declaration.read_bytes()),
                    authorization=authority,
                    review=self.engine.fixture.review,
                    expected_runtime_sha256=self.engine.candidate.expected_runtime,
                )
            local.assert_not_called()
        self.assertFalse(destination.exists())
        self.assertEqual(
            (
                self.h.files(directory.parent.parent),
                authority.summary(),
                len(self.events),
                self.engine.physical_sends,
            ),
            before,
        )

    def passive_and_corruptions(self, directory, declaration, authority, report):
        from buddha.gateway import RawHTTPTransport
        from buddha.releases import _json

        # Retire fixture producer source roots while keeping their original names
        # absent. Never rename or edit checkout application files.
        retired = []
        for name in ("I0", "I1", "S0", "S1"):
            original = self.root / name
            destination = self.root / (name + "-retired")
            original.rename(destination)
            retired.append((original, destination))
        before = self.h.files(directory), authority.summary(), self.engine.physical_sends
        try:
            with self.h.readonly(), patch.dict(os.environ, {}, clear=True):
                with self.subTest(contract="retired-source-inspection"):
                    self.assertEqual(self.inspect(directory, authority), report)
                with self.subTest(contract="retired-source-replay"):
                    self.assertEqual(
                        self.api.run_improver_study(
                            directory, transport=RawHTTPTransport(allow_paid=False)
                        ),
                        report,
                    )
            self.assertEqual(
                (self.h.files(directory), authority.summary(), self.engine.physical_sends), before
            )
        finally:
            for original, destination in retired:
                destination.rename(original)
        observation = directory / "observations/0.json"
        original_observation = observation.read_bytes()
        retained = json.loads(original_observation)
        self.assertEqual(retained["coverage"]["completed_common"], 4)
        self.assertEqual(
            report["provenance"]["observations"],
            {
                path.relative_to(directory).as_posix(): sha(path.read_bytes())
                for path in sorted((directory / "observations").glob("*.json"))
            },
        )
        corruptions = []
        forged = copy.deepcopy(retained)
        forged["coverage"]["completed_common"] = 0
        corruptions.append(forged)
        forged = copy.deepcopy(retained)
        forged["coverage"]["completed_cells"] = 1
        corruptions.append(forged)
        forged = copy.deepcopy(retained)
        forged["coverage"].update(
            attempted_opportunities=0,
            in_flight_opportunities=0,
            unattempted_opportunities=16,
        )
        corruptions.append(forged)
        forged = copy.deepcopy(retained)
        forged["position"]["stage"] = "common_screen"
        corruptions.append(forged)
        forged = copy.deepcopy(retained)
        # Identity and accounting stay genuine; the final provenance must also
        # bind an otherwise well-formed change to an unstructured reason.
        forged["reason"] = "forged-original-reason"
        forged["child"] = None
        corruptions.append(forged)
        for index, forged in enumerate(corruptions):
            observation.write_bytes(_json(forged))
            try:
                with self.subTest(contract="forged-observation", index=index):
                    self.refused(lambda: self.inspect(directory, authority))
            finally:
                observation.write_bytes(original_observation)
        with self.subTest(contract="restored-observation"):
            self.assertEqual(self.inspect(directory, authority), report)
        # After completion, retired external source files are not re-opened.
        # These mutations instead target original retained host metadata that
        # remains evidence in the study tree. Fixed-I source drift was tested
        # during active preparation above, before any prepared worker ran.
        for path in (directory / "declaration.json", directory / "cells/0/0/0/0/plan.json"):
            raw = path.read_bytes()
            path.write_bytes(raw + b" ")
            try:
                with self.subTest(contract="changed-retained-metadata", path=str(path)):
                    self.refused(lambda: self.run_study(directory))
            finally:
                path.write_bytes(raw)
        owner = directory / "cells/0/0/0/0/proposal/owners/0"
        hidden = owner.with_name("missing-original")
        owner.rename(hidden)
        try:
            with self.subTest(contract="missing-original-owner"):
                self.refused(lambda: self.inspect(directory, authority))
        finally:
            hidden.rename(owner)
        publication = directory / "report.json"
        raw = publication.read_bytes()
        forged = json.loads(raw)
        forged["decisions"] = forged["decisions"][1:]
        publication.write_bytes(_json(forged))
        try:
            with self.subTest(contract="truncated-publication"):
                self.refused(lambda: self.inspect(directory, authority))
        finally:
            publication.write_bytes(raw)

    def test_multitask_grid_requires_exact_prospective_caps_before_owner(self):
        self.fixture_before_new_api()
        from buddha import improver_study, source_screen
        from buddha.authorization import Authorization
        from buddha.releases import _json

        self.api = improver_study
        stale = self.declaration(improver_study)
        # Both typed tasks exist in the same original full TaskSet. No source,
        # profile, review, executor, runtime or native stage setting is changed.
        for start in stale["starts"]:
            start["screen"]["selected_ids"] = ["1", 1]
        self.assertEqual(
            stale["limits"],
            {
                "common_cell": {"budget_microusd": 50001, "max_calls": 16},
                "arm_cell": {"budget_microusd": 120002, "max_calls": 38},
                "study": {"budget_microusd": 1160020, "max_calls": 368},
            },
        )
        # Independent numerical oracle: two tasks each have generation10,000/3,
        # two native10,000/3 and summary1/1. The first-task mutation witness
        # remains one proposal10,000/3 plus one generation10,000/3.
        screen = {"budget_microusd": 60002, "max_calls": 20}
        witness = {"budget_microusd": 20000, "max_calls": 6}
        exact_limits = {
            "common_cell": {"budget_microusd": 80002, "max_calls": 26},
            "arm_cell": {"budget_microusd": 180004, "max_calls": 58},
            "study": {"budget_microusd": 1760040, "max_calls": 568},
        }
        self.assertEqual(
            exact_limits["common_cell"],
            {key: screen[key] + witness[key] for key in screen},
        )
        self.assertEqual(
            exact_limits["arm_cell"],
            {
                "budget_microusd": 2
                * (10000 + screen["budget_microusd"] + witness["budget_microusd"]),
                "max_calls": 2 * (3 + screen["max_calls"] + witness["max_calls"]),
            },
        )
        self.assertEqual(
            exact_limits["study"],
            {
                key: 4 * (exact_limits["common_cell"][key] + 2 * exact_limits["arm_cell"][key])
                for key in screen
            },
        )
        correct = copy.deepcopy(stale)
        correct["limits"] = exact_limits
        modified_screen = source_screen.SourceScreen.from_bytes(
            _json(correct["starts"][0]["screen"])
        )
        self.assertEqual([task.id for task in modified_screen.tasks.tasks], ["1", 1])
        purpose = "source screen: " + modified_screen.comparison_key()
        self.assertNotEqual(purpose, "source screen: " + self.base.comparison_key())
        sufficient = Authorization.create(
            self.root / "multitask-sufficient.sqlite3",
            authorization_id="offline-multitask-sufficient",
            scope=purpose,
            **exact_limits["study"],
        )
        insufficient = Authorization.create(
            self.root / "multitask-insufficient.sqlite3",
            authorization_id="offline-multitask-insufficient",
            scope=purpose,
            budget_microusd=1160020,
            max_calls=368,
        )
        for label, record, authority in (
            ("multitask-stale-limits", stale, sufficient),
            ("multitask-insufficient-authority", correct, insufficient),
        ):
            declaration = self.root / (label + ".json")
            declaration.write_bytes(_json(record))
            destination = self.root / label
            before = (
                self.h.files(self.root),
                sufficient.summary(),
                insufficient.summary(),
                len(self.events),
                self.engine.physical_sends,
            )
            # On the original faulty formula this harmless lower stub records
            # the forbidden prepare without creating an original owner. The
            # public refusal itself must precede even that call and directory.
            with patch.object(source_screen, "prepare_source_screen", return_value=None) as lower:
                with self.assertRaises(self.api.ImproverStudyError, msg=label):
                    self.api.prepare_improver_study(
                        destination,
                        declaration=declaration,
                        expected_sha256=sha(declaration.read_bytes()),
                        authorization=authority,
                        review=self.engine.fixture.review,
                        expected_runtime_sha256=self.engine.candidate.expected_runtime,
                    )
                lower.assert_not_called()
            self.assertFalse(destination.exists(), label)
            self.assertEqual(
                (
                    self.h.files(self.root),
                    sufficient.summary(),
                    insufficient.summary(),
                    len(self.events),
                    self.engine.physical_sends,
                ),
                before,
                label,
            )
            self.assertEqual(authority.summary()["runs"], [])
        label = "multitask-correct-limits"
        declaration = self.root / (label + ".json")
        declaration.write_bytes(_json(correct))
        directory = self.root / label
        before = len(self.events), self.engine.physical_sends
        self.api.prepare_improver_study(
            directory,
            declaration=declaration,
            expected_sha256=sha(declaration.read_bytes()),
            authorization=sufficient,
            review=self.engine.fixture.review,
            expected_runtime_sha256=self.engine.candidate.expected_runtime,
        )
        self.assertEqual((len(self.events), self.engine.physical_sends), before)
        owner = directory / "common/0/0/screen/tasks/0/generation/owners/0"
        self.assertTrue((owner / "manifest.json").is_file())
        self.assertEqual(
            {path.parent for path in directory.rglob("owners/*/manifest.json")},
            {owner},
        )
        manifest = json.loads((owner / "manifest.json").read_bytes())
        self.assertEqual(manifest["settings"], {"budget_microusd": 10000, "max_calls": 3})
        saved_screen = json.loads((directory / "common/0/0/screen/screen.json").read_bytes())
        self.assertEqual(saved_screen, correct["starts"][0]["screen"])
        self.assertEqual(saved_screen["selected_ids"], ["1", 1])
        runs = sufficient.summary()["runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["directory"], str(owner))
        self.assertEqual(runs[0]["operation_count"], 0)
        self.assertEqual(runs[0]["spent_microusd"], 0)
        self.assertEqual(runs[0]["reserved_microusd"], 0)
        self.assertEqual(runs[0]["committed_microusd"], 0)
        self.assertEqual(insufficient.summary()["runs"], [])

    def test_historical_common_coverage_edit_refuses_before_known_reply_resume(self):
        self.fixture_before_new_api()
        from buddha import improver_study
        from buddha.releases import _json

        self.api = improver_study
        record = self.declaration(improver_study)
        record.update(starts=record["starts"][:1], repetitions=1, descendant_opportunities=1)
        record["selection"]["finalist_iteration"] = 1
        self.recompute_limits(record)
        directory, _, authority = self.prepare_study("partial-coverage", record)
        self.known_once = True
        partial = self.run_study(directory)
        self.assertEqual(partial["status"], "incomplete")
        # The real wrapper reports protocol for this supplied worker interruption;
        # the original reply remains a completed operation in its original owner.
        self.assertEqual(partial["reason"], "protocol")
        self.assertEqual(partial["child"]["reason"], partial["reason"])
        self.assertEqual(partial["child"]["status"], "incomplete")
        self.assertEqual(
            partial["position"],
            {"start": 0, "repetition": 0, "arm": 0, "slot": 0, "stage": "proposal"},
        )
        self.assertEqual(
            partial["coverage"],
            {
                "expected_common": 1,
                "completed_common": 1,
                "expected_cells": 2,
                "completed_cells": 0,
                "expected_opportunities": 2,
                "attempted_opportunities": 1,
                "completed_opportunities": 0,
                "in_flight_opportunities": 1,
                "unattempted_opportunities": 1,
            },
        )
        owner = directory / "cells/0/0/0/0/proposal/owners/0"
        self.assertEqual(self.known_owner, owner)
        self.assertEqual(partial["child"]["owner"], str(owner))
        saved_child = copy.deepcopy(partial["child"])
        lower_observation = owner.parents[1] / saved_child["observation"]
        original_lower = lower_observation.read_bytes()
        self.assertEqual(json.loads(original_lower), saved_child)
        original_manifest = (owner / "manifest.json").read_bytes()
        original_run = next(
            row for row in authority.summary()["runs"] if row["directory"] == str(owner)
        )
        self.assertEqual(original_run["operation_count"], 1)
        self.assertEqual(original_run["reserved_microusd"], 0)
        observation = directory / partial["observation"]
        original_observation = observation.read_bytes()
        self.assertEqual(json.loads(original_observation), partial)
        # Retain the authentic bytes separately before the deliberate corruption.
        preserved = self.root / "partial-coverage-original-observation.json"
        preserved.write_bytes(original_observation)

        def refuse_changed_observation(changed):
            observation.write_bytes(_json(changed))
            before = (
                self.h.files(self.root),
                authority.summary(),
                self.owner_paths(directory),
                len(self.events),
                self.engine.physical_sends,
            )
            try:
                # A faulty reader may reach this sentinel and write another
                # partial, but cannot resume a worker or dispatch an API call.
                with patch.object(
                    self.lower,
                    "run_candidate_improvement",
                    return_value=copy.deepcopy(saved_child),
                ) as resume:
                    with self.assertRaises(self.api.ImproverStudyError):
                        self.run_study(directory)
                    resume.assert_not_called()
                self.assertEqual(
                    (
                        self.h.files(self.root),
                        authority.summary(),
                        self.owner_paths(directory),
                        len(self.events),
                        self.engine.physical_sends,
                    ),
                    before,
                )
                self.assertEqual((owner / "manifest.json").read_bytes(), original_manifest)
                self.assertEqual(lower_observation.read_bytes(), original_lower)
                self.assertEqual(preserved.read_bytes(), original_observation)
            finally:
                # Restore only the intentional corruption, retaining any extra
                # observation incorrectly created on a failing implementation.
                observation.write_bytes(original_observation)

        changed = copy.deepcopy(partial)
        changed["coverage"]["completed_common"] = 0
        refuse_changed_observation(changed)
        changed = copy.deepcopy(partial)
        snapshot = changed["authorization"]
        snapshot["runs"] = [
            row for row in snapshot["runs"] if row["run_id"] != original_run["run_id"]
        ]
        for key in TOTALS:
            snapshot[key] = sum(row[key] for row in snapshot["runs"])
        snapshot["available_microusd"] = (
            snapshot["budget_microusd"] - snapshot["committed_microusd"]
        )
        snapshot["remaining_calls"] = snapshot["max_calls"] - snapshot["operation_count"]
        refuse_changed_observation(changed)
        # The authentic old partial must remain valid after this same owner
        # completes and deactivates. Historical activity is not current activity.
        self.known_replay = True
        report = self.run_study(directory)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["coverage"]["completed_opportunities"], 2)
        current = next(row for row in authority.summary()["runs"] if row["directory"] == str(owner))
        self.assertFalse(current["active"])
        self.assertEqual(current["operation_count"], 1)
        self.assertEqual((owner / "manifest.json").read_bytes(), original_manifest)
        self.assertEqual(observation.read_bytes(), original_observation)
        self.assertEqual(lower_observation.read_bytes(), original_lower)


class ImproverStudyCapacityTests(unittest.TestCase):
    """Explicit v4 policies and original proposal capacity; supplied workers only."""

    def fixture(
        self,
        *,
        fail_role=None,
        unobserved=False,
        zero_calls=False,
        finite_fixture=None,
        output_tokens=32_768,
    ):
        from buddha import improver_study, source_capacity

        fixture = finite_fixture
        if fixture is None:
            fixture = FiniteImproverStudyTests("runTest")
            self.addCleanup(fixture.doCleanups)
            fixture.fixture_before_new_api(
                proposal_capacity=True, capacity_output_tokens=output_tokens
            )
            observe_fixture_workers(fixture, self)
        fixture.api = improver_study
        record = fixture.declaration(improver_study)
        record.update(
            format="buddha.improver-study.v4",
            starts=record["starts"][:1],
            repetitions=1,
            descendant_opportunities=1,
            feedback_comparison=copy.deepcopy(improver_study.FEEDBACK_COMPARISON_POLICY),
            proposal_capacity=source_capacity.proposal_capacity_policy(),
        )
        record["selection"]["finalist_iteration"] = 1
        fixture.recompute_limits(record)
        fixture.outcomes = {}
        original_improve = fixture.improve

        def improve(spec, initial, handle):
            import base64

            from buddha.releases import _json

            owner = handle.__self__.gateway.directory
            role = (
                "common"
                if "common" in owner.parts
                else "witness"
                if "witness" in owner.parts
                else "counted"
            )
            request, response = fixture.engine.candidate.request, fixture.engine.fixture.response

            def requested(*args, **kwargs):
                frame = request(*args, **kwargs)
                body = json.loads(base64.b64decode(frame["body_base64"]))
                body["max_completion_tokens"] = 32_768
                frame["body_base64"] = base64.b64encode(_json(body)).decode()
                return frame

            def responded(**kwargs):
                supplied = copy.deepcopy(kwargs)
                supplied["choices"][0]["finish_reason"] = "stop"
                if unobserved and role == "counted":
                    supplied["choices"][0]["message"]["content"] = "Complete procedural advice."
                supplied["usage"] = {
                    "prompt_tokens": 5,
                    "completion_tokens": 24_577 if role == fail_role else 3,
                }
                return response(**supplied)

            if zero_calls and role == "counted":
                # A worker can return source programmatically. This is not an
                # observed full replacement in the original model receipts.
                value = {
                    "source": source("programmatic-counted").decode(),
                    "hypothesis": "Supplied callback-free mutation.",
                }
                fixture.engine.workers += 1
                handle(
                    {
                        "type": "ready",
                        "agent_sha256": initial["agent_sha256"],
                        "parent_agent_sha256": initial["parent_bundle"]["agent_sha256"],
                        "feedback_sha256": sha(_json(initial["feedback"])),
                        "runtime_sha256": fixture.engine.candidate.expected_runtime,
                    }
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
                return fixture.engine.execution(spec)
            with (
                patch.object(fixture.engine.candidate, "request", side_effect=requested),
                patch.object(fixture.engine.fixture, "response", side_effect=responded),
            ):
                return original_improve(spec, initial, handle)

        fixture.improve = improve
        return fixture, record

    def test_v4_requires_both_exact_policies_and_preserves_legacy_schema_bytes(self):
        from buddha import improver_study
        from buddha.releases import ReleaseError, _json

        f, record = self.fixture()
        runtime = f.engine.candidate.expected_runtime
        before = f.h.files(f.root), f.engine.physical_sends, len(f.events)
        original = _json(record)
        parsed, _ = improver_study._declaration(record, runtime)
        self.assertEqual(_json(parsed), original)
        invalid = []
        for field in ("proposal_capacity", "feedback_comparison"):
            missing = copy.deepcopy(record)
            del missing[field]
            invalid.append(missing)
            for key in record[field]:
                changed = copy.deepcopy(record)
                changed[field][key] = "changed"
                invalid.append(changed)
            changed = copy.deepcopy(record)
            changed[field]["extra"] = True
            invalid.append(changed)
        for changed in invalid:
            with self.subTest(invalid=changed), self.assertRaises(ReleaseError):
                improver_study._declaration(changed, runtime)
        for version in (1, 2, 3):
            old = copy.deepcopy(record)
            old["format"] = "buddha.improver-study.v" + str(version)
            del old["proposal_capacity"]
            if version < 3:
                del old["feedback_comparison"]
            expected = _json(old)
            self.assertEqual(_json(improver_study._declaration(old, runtime)[0]), expected)
            with self.subTest(legacy=version), self.assertRaises(ReleaseError):
                improver_study._declaration(
                    old | {"proposal_capacity": copy.deepcopy(record["proposal_capacity"])}, runtime
                )
        self.assertEqual((f.h.files(f.root), f.engine.physical_sends, len(f.events)), before)

    def test_v4_capacity_helper_is_bound_without_expanding_old_input_closures(self):
        from buddha import improver_study, source_capacity
        from buddha.releases import _json

        f, record = self.fixture()
        helper = Path(source_capacity.__file__).absolute()
        self.assertNotIn(helper, f.shared._sources())
        before = f.engine.physical_sends, len(f.events)
        for version in (1, 2, 3, 4):
            selected = copy.deepcopy(record)
            selected["format"] = "buddha.improver-study.v" + str(version)
            if version < 4:
                del selected["proposal_capacity"]
            if version < 3:
                del selected["feedback_comparison"]
            path = f.root / ("intrinsic-v" + str(version) + ".json")
            path.write_bytes(_json(selected))
            controls, sources, _ = improver_study._intrinsic_inputs(
                selected,
                [f.base],
                path,
                sha(path.read_bytes()),
                f.engine.candidate.expected_runtime,
                active=False,
            )
            with self.subTest(version=version):
                self.assertEqual(helper in controls, version == 4)
                self.assertEqual(sources, [])
                if version == 4:
                    self.assertEqual(controls[helper], sha(helper.read_bytes()))
        self.assertEqual((f.engine.physical_sends, len(f.events)), before)

    def test_v4_unsupported_capacity_configuration_refuses_before_any_owner_or_worker(self):
        from buddha import improver_study
        from buddha.authorization import Authorization
        from buddha.releases import _json

        f, record = self.fixture(output_tokens=8_191)
        declaration, directory = f.root / "bad-capacity.json", f.root / "bad-capacity"
        declaration.write_bytes(_json(record))
        authority = Authorization.create(
            f.root / "bad-capacity-authority.sqlite3",
            authorization_id="offline-unsupported-capacity",
            scope="source screen: " + f.base.comparison_key(),
            **record["limits"]["study"],
        )
        before = authority.summary(), f.engine.physical_sends, len(f.events)
        with self.assertRaisesRegex(improver_study.ImproverStudyError, "capacity"):
            improver_study.prepare_improver_study(
                directory,
                declaration=declaration,
                expected_sha256=sha(declaration.read_bytes()),
                authorization=authority,
                review=f.engine.fixture.review,
                expected_runtime_sha256=f.engine.candidate.expected_runtime,
            )
        self.assertFalse(directory.exists())
        self.assertEqual((authority.summary(), f.engine.physical_sends, len(f.events)), before)

    def test_v4_all_three_capacity_failures_stop_before_child_and_reuse_original_receipts(self):
        for role, suffix, stage in (
            ("common", "common/0/0/witness", "common_witness_proposal_capacity"),
            ("counted", "cells/0/0/0/0", "proposal_capacity"),
            ("witness", "cells/0/0/0/0/witness", "witness_proposal_capacity"),
        ):
            with self.subTest(role=role):
                f, record = self.fixture(fail_role=role)
                directory, _, authority = f.prepare_study("capacity-" + role, record)
                partial = f.run_study(directory)
                self.assertEqual(
                    (partial["status"], partial["reason"]), ("incomplete", "proposal_capacity")
                )
                self.assertEqual(partial["position"]["stage"], stage)
                self.assertIsNone(partial["child"])
                location = directory / suffix
                checkpoint = json.loads((location / "proposal-capacity.json").read_bytes())
                self.assertEqual(
                    (checkpoint["measurement_status"], checkpoint["decision"]), ("complete", "fail")
                )
                self.assertFalse((location / "agent").exists())
                self.assertFalse(
                    (location / ("screen" if role == "counted" else "generation")).exists()
                )
                before = (
                    f.engine.physical_sends,
                    authority.summary()["spent_microusd"],
                    f.owner_paths(directory),
                )
                resumed = f.run_study(directory)
                self.assertEqual(resumed["reason"], "proposal_capacity")
                self.assertEqual(
                    (
                        f.engine.physical_sends,
                        authority.summary()["spent_microusd"],
                        f.owner_paths(directory),
                    ),
                    before,
                )
                self.assertEqual(authority.summary()["reserved_microusd"], 0)

    def test_v4_unobserved_and_callback_free_replacements_remain_incomplete(self):
        for option in ("unobserved", "zero_calls"):
            with self.subTest(option=option):
                f, record = self.fixture(**{option: True})
                directory, _, authority = f.prepare_study("capacity-" + option, record)
                partial = f.run_study(directory)
                self.assertEqual(
                    (partial["status"], partial["reason"]), ("incomplete", "proposal_capacity")
                )
                self.assertEqual(partial["position"]["stage"], "proposal_capacity")
                location = directory / "cells/0/0/0/0"
                checkpoint = json.loads((location / "proposal-capacity.json").read_bytes())
                self.assertEqual(
                    (
                        checkpoint["measurement_status"],
                        checkpoint["decision"],
                        checkpoint["replacement_count"],
                    ),
                    ("partial", "unavailable", 0),
                )
                self.assertFalse((location / "screen").exists())
                self.assertFalse((location / "agent").exists())
                self.assertFalse((location / "decision.json").exists())
                self.assertEqual(partial["coverage"]["completed_opportunities"], 0)
                before = f.engine.physical_sends, authority.summary()
                self.assertEqual(f.run_study(directory)["reason"], "proposal_capacity")
                self.assertEqual((f.engine.physical_sends, authority.summary()), before)

    def test_v4_complete_capacity_history_is_replayed_and_tampering_refused_keylessly(self):
        from buddha.releases import _json

        f, record = self.fixture()
        directory, _, authority = f.prepare_study("capacity-complete", record)
        report = f.run_study(directory)
        self.assertEqual(report["status"], "complete")
        checkpoints = sorted(directory.rglob("proposal-capacity.json"))
        self.assertEqual(len(checkpoints), 5)
        for path in checkpoints:
            checkpoint = json.loads(path.read_bytes())
            self.assertEqual(checkpoint["decision"], "pass")
            self.assertGreaterEqual(checkpoint["replacement_count"], 1)
        before = f.engine.physical_sends, authority.summary()
        with f.h.readonly(), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(f.inspect(directory, authority), report)
        self.assertEqual((f.engine.physical_sends, authority.summary()), before)
        for path in (
            directory / "common/0/0/witness/proposal-capacity.json",
            directory / "cells/0/0/0/0/proposal-capacity.json",
            directory / "cells/0/0/0/0/witness/proposal-capacity.json",
        ):
            original = path.read_bytes()
            try:
                changed = json.loads(original)
                changed["operations"][0]["measurement"]["context_slack"] += 1
                path.write_bytes(_json(changed))
                f.refused(lambda: f.inspect(directory, authority))
                path.unlink()
                f.refused(lambda: f.inspect(directory, authority))
            finally:
                path.write_bytes(original)
        counted = directory / "cells/0/0/0/0/proposal-capacity.json"
        other = directory / "cells/0/0/1/0/proposal-capacity.json"
        original = other.read_bytes()
        try:
            other.write_bytes(counted.read_bytes())
            f.refused(lambda: f.inspect(directory, authority))
        finally:
            other.write_bytes(original)
        orphan = directory / "cells/0/0/0/99/proposal-capacity.json"
        orphan.parent.mkdir()
        try:
            orphan.write_bytes(counted.read_bytes())
            f.refused(lambda: f.inspect(directory, authority))
        finally:
            orphan.unlink()
            orphan.parent.rmdir()
        self.assertEqual(f.inspect(directory, authority), report)

    def test_v4_counted_checkpoint_resume_blocks_premature_copy_without_new_proposal_send(self):
        from buddha.native_evidence import NativeEvidence
        from buddha.releases import _json

        f, record = self.fixture()
        directory, _, authority = f.prepare_study("capacity-resume", record)
        location = directory / "cells/0/0/0/0"
        publish = f.shared._publish_capacity
        interrupted = []

        def before_checkpoint(root, authorization, stage, policy, **kwargs):
            if stage == location and not interrupted:
                interrupted.append("before")
                raise KeyboardInterrupt
            return publish(root, authorization, stage, policy, **kwargs)

        with patch.object(f.shared, "_publish_capacity", side_effect=before_checkpoint):
            with self.assertRaises(KeyboardInterrupt):
                f.run_study(directory)
        self.assertEqual(interrupted, ["before"])
        self.assertTrue((location / "proposal/report.json").is_file())
        self.assertFalse((location / "proposal-capacity.json").exists())
        self.assertFalse((location / "screen").exists())
        original_proposal = f.h.files(location / "proposal")
        before = f.engine.physical_sends, authority.summary(), f.owner_paths(directory)
        private = location / "agent"
        private.mkdir()
        try:
            with (
                f.h.readonly(),
                self.assertRaisesRegex(
                    f.shared.SourceSearchError, "child work precedes.*capacity checkpoint"
                ),
            ):
                f.api._restore(directory, authority.path)
        finally:
            private.rmdir()
        self.assertEqual(
            (f.engine.physical_sends, authority.summary(), f.owner_paths(directory)), before
        )

        def after_checkpoint(root, authorization, stage, policy, **kwargs):
            result = publish(root, authorization, stage, policy, **kwargs)
            if stage == location and interrupted == ["before"]:
                interrupted.append("after")
                raise KeyboardInterrupt
            return result

        with patch.object(f.shared, "_publish_capacity", side_effect=after_checkpoint):
            with self.assertRaises(KeyboardInterrupt):
                f.run_study(directory)
        self.assertEqual(interrupted, ["before", "after"])
        self.assertTrue((location / "proposal-capacity.json").is_file())
        self.assertFalse((location / "screen").exists())
        self.assertFalse((location / "agent").exists())
        self.assertEqual(f.h.files(location / "proposal"), original_proposal)
        self.assertEqual(
            (f.engine.physical_sends, authority.summary(), f.owner_paths(directory)), before
        )
        reader, state = f.api._restore(directory, authority.path)
        reader.capture.finish()
        observation = directory / "observations/1.json"
        original_observation = observation.read_bytes()
        forged = json.loads(original_observation)
        forged["reason"] = "proposal_capacity"
        forged["position"]["stage"] = "proposal_capacity"
        try:
            observation.write_bytes(_json(forged))
            observed = NativeEvidence(
                directory, authority.path, error_type=f.api.ImproverStudyError
            )
            try:
                with self.assertRaisesRegex(f.api.ImproverStudyError, "negative checkpoint"):
                    f.api._observations(observed, dict(state, observations=[]))
            finally:
                observed.capture.finish()
        finally:
            observation.write_bytes(original_observation)
        result = f.run_study(directory)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(f.h.files(location / "proposal"), original_proposal)
        self.assertEqual(len(result["provenance"]["observations"]), 2)

    def test_v4_future_decisions_and_witnesses_cannot_hide_behind_capacity_action(self):
        from buddha.native_evidence import NativeEvidence
        from buddha.releases import ReleaseError, _json

        f, record = self.fixture(fail_role="counted")
        directory, _, authority = f.prepare_study("capacity-future", record)
        location = directory / "cells/0/0/0/0"
        prepare = f.api._prepare_proposal
        interrupted = []

        def before_proposal(state, action, authorization):
            if action["directory"] == location and not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt
            return prepare(state, action, authorization)

        with patch.object(f.api, "_prepare_proposal", side_effect=before_proposal):
            with self.assertRaises(KeyboardInterrupt):
                f.run_study(directory)
        self.assertEqual(interrupted, [True])
        self.assertFalse((location / "proposal").exists())
        with f.h.readonly():
            reader, state = f.api._restore(directory, authority.path)
            self.assertEqual(state["action"]["kind"], "prepare_proposal")
            reader.capture.finish()
        for artifact in ("agent", "screen", "witness", "decision.json"):
            path = location / artifact
            try:
                if artifact == "decision.json":
                    path.write_bytes(b"{}")
                else:
                    path.mkdir()
                with (
                    self.subTest(cut="before_proposal", artifact=artifact),
                    f.h.readonly(),
                    self.assertRaises(ReleaseError),
                ):
                    f.api._restore(directory, authority.path)
            finally:
                path.unlink() if artifact == "decision.json" else path.rmdir()

        partial = f.run_study(directory)
        self.assertEqual(
            (partial["status"], partial["reason"]), ("incomplete", "proposal_capacity")
        )
        with f.h.readonly():
            reader, state = f.api._restore(directory, authority.path)
            self.assertEqual(state["action"]["kind"], "proposal_capacity")
            reader.capture.finish()
        before = f.engine.physical_sends, authority.summary(), f.owner_paths(directory)
        for artifact in ("witness", "decision.json"):
            path = location / artifact
            try:
                if artifact == "witness":
                    path.mkdir()
                else:
                    path.write_bytes(b"{}")
                with (
                    self.subTest(artifact=artifact),
                    f.h.readonly(),
                    self.assertRaises(ReleaseError),
                ):
                    f.api._restore(directory, authority.path)
            finally:
                path.rmdir() if artifact == "witness" else path.unlink()
        # Exercise the observation boundary directly on this genuine retained
        # prefix; the complete controller has already established its custody.
        observation = directory / partial["observation"]
        original = observation.read_bytes()
        for corruption in ("stage", "child"):
            changed = copy.deepcopy(partial)
            if corruption == "stage":
                changed["position"]["stage"] = "screen"
            else:
                changed["child"] = {}
            try:
                observation.write_bytes(_json(changed))
                observed = NativeEvidence(
                    directory, authority.path, error_type=f.api.ImproverStudyError
                )
                try:
                    with (
                        self.subTest(observation=corruption),
                        self.assertRaisesRegex(f.api.ImproverStudyError, "proposal capacity stop"),
                    ):
                        f.api._observations(observed, dict(state, observations=[]))
                finally:
                    observed.capture.finish()
            finally:
                observation.write_bytes(original)
        self.assertEqual(
            (f.engine.physical_sends, authority.summary(), f.owner_paths(directory)), before
        )

    def test_v4_unknown_original_liability_stops_before_capacity_or_child(self):
        f, record = self.fixture()
        directory, _, authority = f.prepare_study("capacity-unknown", record)
        f.unknown_once, f.unknown_scope = True, directory / "common/0/0/witness"
        partial = f.run_study(directory)
        self.assertEqual((partial["status"], partial["reason"]), ("incomplete", "unknown"))
        self.assertGreater(authority.summary()["reserved_microusd"], 0)
        self.assertFalse((directory / "common/0/0/witness/proposal-capacity.json").exists())
        self.assertFalse((directory / "common/0/0/witness/agent").exists())
        self.assertFalse((directory / "common/0/0/witness/generation").exists())
        before = f.engine.physical_sends, authority.summary(), f.owner_paths(directory)
        self.assertEqual(f.run_study(directory)["reason"], "unknown")
        self.assertEqual(
            (f.engine.physical_sends, authority.summary(), f.owner_paths(directory)), before
        )


if __name__ == "__main__":
    unittest.main()
