"""Small recipe boundaries; never build a capacity fixture or launch a child."""

import builtins
import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
RECIPE = PROJECT / "docs/conformance/forward-capacity.py"


class ForwardCapacityRecipeTests(unittest.TestCase):
    @contextmanager
    def no_workload_imports(self):
        original = builtins.__import__

        def imported(name, *args, **kwargs):
            if (
                name == "buddha"
                or name.startswith("buddha.")
                or name
                in {
                    "scale_replay_fixture",
                    "scale_native_environment",
                    "test_improver_study",
                }
            ):
                raise AssertionError("capacity workload import")
            return original(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=imported):
            yield

    def recipe(self):
        spec = importlib.util.spec_from_file_location("checked_forward_capacity_recipe", RECIPE)
        module = importlib.util.module_from_spec(spec)
        with self.no_workload_imports(), patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(module)
        return module

    def binding(self, recipe):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        project = base / "source"
        project.mkdir()
        for name in ("buddha/public.py", "agents/public.py", "tests/public.py", "ci_test_shard.py"):
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"# supplied public input\n")
        for name in (recipe.RECIPE, recipe.PROTOCOL):
            path = project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((PROJECT / name).read_bytes())
        self.enterContext(patch.object(recipe, "PROJECT", project))
        record = {
            "format": "buddha.forward-capacity-binding.v1",
            "project": str(project),
            "head": "a" * 40,
            "tree": "b" * 40,
            "sources": recipe.source_snapshot(project),
        }
        binding = base / "binding.json"
        binding.write_text(json.dumps(record), encoding="utf-8")
        return base, project, binding, record, base / "output"

    def test_import_and_check_leave_files_unchanged_without_loading_workload(self):
        recipe = self.recipe()
        base, _, binding, record, output = self.binding(recipe)
        before = recipe.tree_snapshot(base)

        def git(command, **kwargs):
            self.assertTrue(Path(command[0]).is_absolute())
            self.assertIn(Path(command[0]).name.lower(), {"git", "git.exe"})
            self.assertIn("--no-optional-locks", command)
            value = (
                record["tree"]
                if "HEAD^{tree}" in command
                else (record["head"] if "HEAD" in command else "")
            )
            return SimpleNamespace(stdout=value, returncode=0)

        stdout = io.StringIO()
        with (
            self.no_workload_imports(),
            patch.object(recipe.subprocess, "run", side_effect=git),
            patch.object(recipe, "parent", side_effect=AssertionError("parent started")),
            patch.object(recipe, "child", side_effect=AssertionError("child started")),
            redirect_stdout(stdout),
        ):
            code = recipe.main(
                [
                    "--binding",
                    str(binding),
                    "--sha256",
                    recipe.sha(binding),
                    "--out",
                    str(output),
                    "--check",
                ]
            )
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(
            (result["status"], result["workload_children"], result["files_written"]),
            ("checked", 0, 0),
        )
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(output.exists())
        self.assertEqual(recipe.tree_snapshot(base), before)

    def test_changed_source_protocol_or_unknown_binding_path_refuses_before_output(self):
        recipe = self.recipe()
        _, project, binding, record, output = self.binding(recipe)
        original_binding = binding.read_bytes()
        recipe.checked_binding(binding, recipe.sha(binding), output, git_check=False)
        public = project / "buddha/public.py"
        public.write_bytes(b"# changed public input\n")
        with self.assertRaises(ValueError):
            recipe.checked_binding(
                binding, hashlib.sha256(original_binding).hexdigest(), output, git_check=False
            )
        self.assertFalse(output.exists())
        public.write_bytes(b"# supplied public input\n")
        protocol_path = project / recipe.PROTOCOL
        original_protocol = protocol_path.read_bytes()
        protocol = json.loads(original_protocol)
        protocol["total_seconds"] += 1
        protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
        changed = record | {"sources": recipe.source_snapshot(project)}
        binding.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(ValueError):
            recipe.checked_binding(binding, recipe.sha(binding), output, git_check=False)
        self.assertFalse(output.exists())
        protocol_path.write_bytes(original_protocol)
        changed = copy.deepcopy(record)
        changed["sources"]["../outside.py"] = "0" * 64
        binding.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(ValueError):
            recipe.checked_binding(binding, recipe.sha(binding), output, git_check=False)
        self.assertFalse(output.exists())

    def test_reader_cap_uses_only_remaining_total_and_cannot_restart_deadline(self):
        recipe = self.recipe()
        with patch.object(recipe.time, "monotonic", side_effect=[100.0, 1005.0, 1010.0]):
            self.assertEqual(recipe.remaining_seconds(10.0, 1000.0), 910.0)
            self.assertEqual(recipe.remaining_seconds(10.0, 1000.0, 900.0), 5.0)
            with self.assertRaises(TimeoutError):
                recipe.remaining_seconds(10.0, 1000.0, 900.0)

    def test_phase_acceptance_requires_terminal_sources_and_collected_bounded_memory(self):
        recipe = self.recipe()
        protocol = {"peak_working_set_bytes": 1024}
        complete = {
            "status": "complete",
            "sources_unchanged": True,
            "memory": {"collected": True, "peak_working_set_bytes": 1024},
        }
        self.assertTrue(recipe.phase_passes(complete, protocol))
        candidates = [
            {},
            complete | {"status": "partial"},
            {key: value for key, value in complete.items() if key != "sources_unchanged"},
            complete | {"sources_unchanged": False},
            {key: value for key, value in complete.items() if key != "memory"},
        ]
        for peak in (None, 0, True, 1025):
            candidates.append(
                complete | {"memory": {"collected": True, "peak_working_set_bytes": peak}}
            )
        candidates.append(
            complete | {"memory": {"collected": False, "peak_working_set_bytes": 1024}}
        )
        for candidate in candidates:
            with self.subTest(result=candidate):
                self.assertFalse(recipe.phase_passes(candidate, protocol))

    def test_partial_or_timed_out_writer_never_starts_fresh_reader(self):
        recipe = self.recipe()
        for outcome in ("partial", "timeout"):
            with self.subTest(writer=outcome):
                _, _, binding, record, output = self.binding(recipe)
                protocol = json.loads((PROJECT / recipe.PROTOCOL).read_bytes())
                calls = []

                def child(
                    command,
                    *,
                    expected_outcome=outcome,
                    recorded=calls,
                    destination=output,
                    **kwargs,
                ):
                    phase = command[command.index("--phase") + 1]
                    recorded.append(phase)
                    self.assertEqual(phase, "build")
                    if expected_outcome == "timeout":
                        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                    recipe.write(
                        destination / "build-result.json",
                        {
                            "status": "partial",
                            "reason": "supplied writer partial",
                            "sources_unchanged": True,
                            "memory": {"collected": True, "peak_working_set_bytes": 1},
                        },
                    )
                    return SimpleNamespace(returncode=3)

                args = SimpleNamespace(binding=binding, sha256=recipe.sha(binding), out=output)
                with (
                    self.no_workload_imports(),
                    patch.object(recipe, "checked_binding", return_value=(record, protocol)),
                    patch.object(recipe.subprocess, "run", side_effect=child),
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(recipe.parent(args), 3)
                self.assertEqual(calls, ["build"])
                result = json.loads((output / "result.json").read_bytes())
                self.assertEqual(result["status"], "partial")
                self.assertFalse(result["automatic_retry_resume_extension"])
                self.assertFalse((output / "read-result.json").exists())
                self.assertFalse((output / "read-stdout.log").exists())


if __name__ == "__main__":
    unittest.main()
