"""Executable scientific compatibility with the sealed historical constructors.

This compares declared request/scoring/archive behavior, not runtime provenance
fingerprints or future proposal packets whose feedback contains new metadata.
Only fixed, hash-verified historical Python is executed, outside the checkout.
"""

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path, PurePosixPath

REPOSITORY = Path(__file__).resolve().parents[1]
ARCHIVE = REPOSITORY / "docs/snapshots/pilot-runtime-2026-10-19.zip"
ARCHIVE_SHA = "bd32c4d50339e2f2e1cadf01f5872fa3c1cdf12c196e7676a18d6fe96bd534e0"

HARNESS = textwrap.dedent(
    """
    import json, os, socket, sys
    from dataclasses import asdict
    from pathlib import Path

    root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(root))

    def reject(*args, **kwargs):
        raise AssertionError("scientific compatibility must never use model APIs or network")

    def audit(event, args):
        if event.startswith("socket."):
            reject()

    sys.addaudithook(audit)
    socket.socket.connect = reject
    socket.create_connection = reject
    assert not any(name.endswith("_API_KEY") for name in os.environ)

    from buddha import run
    from buddha.archive import Candidate, active_pool, frontier, select_parent
    from buddha.benchmark import PARTITION_SYSTEM, SCORE_SYSTEM, Prompt, render_responses
    from buddha.policy import Policy, propose_call
    from buddha.provider import BudgetBroker, HTTPTransport, ModelSpec, Reply

    assert Path(run.__file__).resolve() == root / "buddha/run.py"
    HTTPTransport.send = reject
    HTTPTransport.preflight = reject
    BudgetBroker.execute = reject

    def profile(provider, model, cap):
        return ModelSpec(provider, model, 100000, cap, 1000000, 2000000,
                         "https://example.org/offline-scientific-fixture")

    def encoded(call):
        return {"body": json.loads(call.body_json), "fingerprint": call.fingerprint()}

    prompt = Prompt("dev-a", "Give one concrete idea with a coherent central mechanism.")
    partition = profile("openai", "partition-fixture", 16000)
    quality = profile("anthropic", "quality-fixture", 16000)
    result = {"constructors": [], "evaluations": {}, "archive": {}}
    feedback = [{"id": "dev-a", "protocol_fingerprint": "declared-fixed-metadata",
                 "generations": ["First idea", "Second idea"], "distinct": 2,
                 "utility": 7.25}]

    for provider in ("openai", "anthropic"):
        generation = profile(provider, "generator-fixture", 4096)
        for instructions in ("", "Use one central mechanism."):
            for history in ((), ("Earlier idea", "[empty]", "[refused]")):
                result["constructors"].append(encoded(run._generation(
                    generation, prompt.prompt, instructions=instructions, history=history)))
        judge = profile(provider, "judge-fixture", 16000)
        result["constructors"].extend([
            encoded(run._judge(judge, PARTITION_SYSTEM,
                              render_responses(prompt.prompt, ["[empty]", "[refused]", "Idea"]),
                              "Partition")),
            encoded(run._judge(judge, SCORE_SYSTEM,
                              "<prompt>\\nTask\\n</prompt>\\n\\n<response>\\nIdea\\n</response>",
                              "Score")),
        ])
        for method in ("archive", "latest", "uninformed"):
            result["constructors"].append(encoded(propose_call(
                generation, parent=Policy("Use one central mechanism.", "in-context"),
                feedback=feedback if method != "uninformed" else [], method=method)))

        settings = run.RunSettings(generation, partition, quality, 1000000, 128, False, 7)
        protocol = run._protocol(settings, "a" * 64, [prompt])
        for mode in ("regenerate", "in-context"):
            calls = []

            def execute(prompt_id, stage, index, call):
                calls.append({"stage": stage, "index": index, **encoded(call)})
                if stage == "generation":
                    text = "   " if index == 0 else "Refusal text" if index == 1 else (
                        "A coherent idea " + str(index))
                    return Reply(text, call.spec.model, "fixture-" + str(index), 10, 5,
                                 "refusal" if index == 1 else "stop", index == 1)
                if stage == "partition":
                    text = json.dumps({"groups": [[0, 1]] + [[i] for i in range(2, 10)]})
                else:
                    text = '{"score":8}'
                return Reply(text, call.spec.model, "fixture-judge", 10, 5, "stop")

            def generate(selected_prompt, previous):
                return run._generation(generation, selected_prompt.prompt,
                                       instructions="Use one central mechanism.",
                                       history=previous if mode == "in-context" else ())

            rows = run.evaluate_prompts([prompt], settings=settings, protocol=protocol,
                                        execute=execute, generate=generate)
            for row in rows:
                row.pop("protocol_fingerprint")
            assert rows[0]["generations"][:2] == ["[empty]", "[refused]"]
            assert len([call for call in calls if call["stage"] == "generation"]) == 10
            result["evaluations"][provider + "/" + mode] = {"calls": calls, "rows": rows}

    items = [Candidate(f"{i:064x}", None, i, 11 - i) for i in range(1, 11)]
    items += [Candidate(f"{20:064x}", f"{1:064x}", 1, 1),
              Candidate(f"{21:064x}", f"{1:064x}", 1, 1),
              Candidate(f"{22:064x}", f"{20:064x}", 1, 1)]
    result["archive"]["frontier"] = [asdict(item) for item in frontier(items)]
    for capacity in (2, 5, 8):
        result["archive"]["active-" + str(capacity)] = [
            asdict(item) for item in active_pool(items, max_active=capacity)]
        for method in ("archive", "latest", "uninformed"):
            result["archive"][str(capacity) + "/" + method] = [
                select_parent(items, method=method, max_active=capacity,
                              seed=seed, iteration=iteration).candidate_id
                for seed in (0, 7) for iteration in range(50)]
    print(json.dumps(result, sort_keys=True))
    """
)


def extract_verified_source(destination):
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != ARCHIVE_SHA:
        raise AssertionError("historical source ZIP differs from its reviewed seal")
    with zipfile.ZipFile(ARCHIVE) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)):
            raise AssertionError("duplicate snapshot entry")
        index = json.loads(bundle.read("source-index.json"))
        if index.get("format") != "buddha.runtime-source-snapshot.v1":
            raise AssertionError("unexpected historical source index")
        files = index["files_sha256"]
        if set(names) != {"source-index.json", *files}:
            raise AssertionError("historical index does not cover exact ZIP contents")
        checked = {}
        for name, expected in files.items():
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or stat.S_ISLNK(bundle.getinfo(name).external_attr >> 16)
            ):
                raise AssertionError("unsafe historical source entry")
            raw = bundle.read(name)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise AssertionError("historical source entry differs from index")
            checked[name] = raw
        # Validate every indexed file before materializing any executable input.
        for name, raw in checked.items():
            if name.startswith("buddha/") and name.endswith(".py"):
                target = destination.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)


def scientific_behavior(source):
    # No ambient credentials, user site packages, PYTHONPATH or bytecode writes.
    environment = {name: os.environ[name] for name in ("SYSTEMROOT",) if name in os.environ}
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", HARNESS, str(source)],
        cwd=source,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(result.stdout)


class ContinuationScienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        historical = Path(temporary.name)
        extract_verified_source(historical)
        cls.historical = scientific_behavior(historical)
        cls.current = scientific_behavior(REPOSITORY)

    def test_generation_judging_and_fixed_feedback_request_bodies_match(self):
        self.assertEqual(self.current["constructors"], self.historical["constructors"])

    def test_both_sampling_modes_preserve_empty_refused_and_scoring_behavior(self):
        self.assertEqual(
            set(self.current["evaluations"]),
            {
                provider + "/" + mode
                for provider in ("openai", "anthropic")
                for mode in ("regenerate", "in-context")
            },
        )
        self.assertEqual(self.current["evaluations"], self.historical["evaluations"])

    def test_archive_frontier_active_pool_and_seeded_parent_selection_match(self):
        self.assertEqual(self.current["archive"], self.historical["archive"])


if __name__ == "__main__":
    unittest.main()
