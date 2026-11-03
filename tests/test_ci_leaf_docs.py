"""Real shallow PR merges and unsafe inputs for the narrow CI report lane."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ci_leaf_docs as leaf

BASE, HEAD, MERGE = "1" * 40, "2" * 40, "3" * 40
EVENT = {"pull_request": {"base": {"sha": BASE}, "head": {"sha": HEAD}}}
GUIDE = "docs/FRESH-REQUEST-OBSERVATIONS.md"
REPORT = "docs/conformance/fresh-request-observations-delivery.json"


def raw(path, *, status="M", old="100644", new="100644"):
    before = "0" * 40 if status == "A" else BASE
    return f":{old} {new} {before} {HEAD} {status}\0{path}\0".encode()


class LeafScopeTests(unittest.TestCase):
    def test_only_the_five_exact_regular_paths_can_qualify(self):
        self.assertEqual(len(leaf.LEAVES), 5)
        for name in leaf.LEAVES:
            with self.subTest(path=name):
                self.assertEqual(leaf._changed(raw(name)), [name])
                self.assertEqual(leaf._changed(raw(name, status="A", old="000000")), [name])
        unsafe = [
            "buddha/gateway.py",
            "tests/test_gateway.py",
            "ci_test_shard.py",
            "ci_leaf_docs.py",
            ".github/workflows/ci.yml",
            "requirements-dev.txt",
            "requirements.txt",
            "docs/DESIGN.md",
            "docs/REVIEW-TRACKS.md",
            "docs/POLICY-COMPARISON.md",
            "THIRD_PARTY_NOTICES.md",
            "docs/conformance/src01-runtime-environment.json",
            "docs/conformance/meas02-target-proposal.json",
            "docs/conformance/new-delivery.json",
            "docs/new-guide.md",
            "docs/../docs/PLAN.md",
        ]
        for name in unsafe:
            with self.subTest(path=name):
                self.assertIsNone(leaf._changed(raw(name)))
                self.assertIsNone(leaf._changed(raw(GUIDE) + raw(name)))

    def test_deleted_renamed_nonregular_duplicate_and_incomplete_records_refuse(self):
        for value in (
            b"",
            raw(GUIDE)[:-1],
            raw(GUIDE) + b"truncated",
            raw(GUIDE, status="D"),
            raw(GUIDE, status="R100") + b"old-name\0",
            raw(GUIDE, new="120000"),
            raw(GUIDE, new="160000"),
            raw(GUIDE, new="100755"),
            raw(GUIDE, old="120000"),
            raw(GUIDE) * 2,
        ):
            with self.subTest(value=value):
                self.assertIsNone(leaf._changed(value))

    def test_non_pr_missing_or_mismatched_merge_context_keeps_full_suite(self):
        with patch.object(leaf, "_git") as git:
            self.assertFalse(leaf.leaf_documents(Path.cwd(), "push", EVENT, MERGE))
            git.assert_not_called()
        for event in ({}, None, {"pull_request": {"base": {}, "head": {}}}):
            self.assertFalse(leaf.leaf_documents(Path.cwd(), "pull_request", event, MERGE))
        for outputs in (
            [b"wrong-checkout\n"],
            [MERGE.encode(), f"{HEAD} {BASE}".encode()],
            [MERGE.encode(), f"{BASE} {HEAD}".encode(), b""],
            [MERGE.encode(), f"{BASE} {HEAD}".encode(), raw(GUIDE).replace(b"docs", b"\xffocs")],
        ):
            with self.subTest(outputs=outputs), patch.object(leaf, "_git", side_effect=outputs):
                self.assertFalse(leaf.leaf_documents(Path.cwd(), "pull_request", EVENT, MERGE))
        with patch.object(leaf, "_git", side_effect=subprocess.CalledProcessError(128, ["git"])):
            self.assertFalse(leaf.leaf_documents(Path.cwd(), "pull_request", EVENT, MERGE))

    def test_leaf_json_is_strict_utf8_and_the_exact_report_format(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / REPORT
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"format": leaf.REPORTS[REPORT]}), encoding="utf-8")
            leaf._validate(root, [REPORT])
            for value in (
                b"\xff",
                b"{",
                b"[]",
                b"null",
                b'{"format":"other"}',
                json.dumps({"format": leaf.REPORTS[REPORT], "value": float("nan")}).encode(),
                ('{"format":' + json.dumps(leaf.REPORTS[REPORT]) + ',"x":1,"x":2}').encode(),
                b" " * (leaf.MAX_BYTES + 1),
            ):
                with self.subTest(value=value[:60]):
                    path.write_bytes(value)
                    with self.assertRaises(leaf.InvalidLeaf):
                        leaf._validate(root, [REPORT])
            guide = root / GUIDE
            guide.write_bytes(b"\xff")
            with self.assertRaises(leaf.InvalidLeaf):
                leaf._validate(root, [GUIDE])

    def test_cli_emits_explicit_mode_and_invalid_leaf_cannot_quietly_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event, output = root / "event.json", root / "output.txt"
            event.write_text(json.dumps(EVENT), encoding="utf-8")
            environment = {
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
                "GITHUB_SHA": MERGE,
                "GITHUB_OUTPUT": str(output),
            }
            with patch.dict(os.environ, environment), contextlib.redirect_stdout(io.StringIO()):
                for result in (False, True):
                    with patch.object(leaf, "leaf_documents", return_value=result):
                        self.assertEqual(leaf.main(), 0)
                self.assertEqual(output.read_text(), "leaf_docs=false\nleaf_docs=true\n")
                before = output.read_bytes()
                with patch.object(leaf, "leaf_documents", side_effect=leaf.InvalidLeaf):
                    self.assertEqual(leaf.main(), 1)
                self.assertEqual(output.read_bytes(), before)

    def test_workflow_keeps_required_matrix_quality_and_genuine_progress_rule(self):
        project = Path(__file__).resolve().parents[1]
        workflow = (project / ".github/workflows/ci.yml").read_text()
        self.assertIn("os: [ubuntu-latest, windows-latest]", workflow)
        self.assertIn("shard: [0, 1, 2, 3, 4]", workflow)
        self.assertIn("fetch-depth: 2", workflow)
        self.assertIn("if: steps.leaf_docs.outputs.leaf_docs != 'true'", workflow)
        self.assertIn("--count 5 --index ${{ matrix.shard }} --idle-seconds 3600", workflow)
        self.assertEqual(workflow.count("        if:"), 1)
        for command in (
            "ruff check",
            "ruff format --check",
            "mypy --strict",
            "bandit -r",
            "compileall -q",
        ):
            self.assertIn(command, workflow)
        self.assertEqual(workflow.count("ci_test_shard.py ci_leaf_docs.py"), 5)
        self.assertNotIn("paths-ignore", workflow)
        self.assertIn("  contents: read", workflow)


@unittest.skipUnless(shutil.which("git"), "Git is required for the actual merge-tree fixtures")
class ShallowMergeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repository = self.root / "repo"
        self.repository.mkdir()
        self.environment = {
            key: os.environ[key]
            for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
            if key in os.environ
        } | {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "CI supplied fixture")
        self.git("config", "user.email", "ci-fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write(GUIDE, "Original guide\n")
        self.write(REPORT, json.dumps({"format": leaf.REPORTS[REPORT]}) + "\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD")
        self.git("checkout", "-b", "feature")

    def git(self, *args):
        return (
            subprocess.run(
                ["git", "-C", str(self.repository), *args],
                check=True,
                capture_output=True,
                timeout=15,
                env=self.environment,
            )
            .stdout.decode()
            .strip()
        )

    def write(self, name, value):
        path = self.repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8", newline="\n")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-m", "supplied fixture")

    def merge(self):
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "main")
        self.git("merge", "--no-ff", "-m", "supplied PR merge", "feature")
        event = {
            "pull_request": {
                "base": {"sha": self.base},
                "head": {"sha": head, "repo": {"full_name": "contributor/fork"}},
            }
        }
        return event, self.git("rev-parse", "HEAD")

    def test_depth_two_fork_merge_validates_the_complete_multicommit_doc_diff(self):
        self.write(GUIDE, "First PR commit\n")
        self.commit()
        self.write(REPORT, json.dumps({"format": leaf.REPORTS[REPORT], "observation": 2}) + "\n")
        self.commit()
        event, merge = self.merge()
        clone = self.root / "depth-two"
        self.git("clone", "--depth", "2", "--no-local", str(self.repository), str(clone))
        self.assertTrue((clone / ".git/shallow").is_file())
        self.assertTrue(leaf.leaf_documents(clone, "pull_request", event, merge))

    def test_an_earlier_code_change_cannot_hide_behind_a_doc_only_tip(self):
        self.write("buddha/changed.py", "VALUE = 1\n")
        self.commit()
        self.write(GUIDE, "Only the last PR commit is documentary\n")
        self.commit()
        event, merge = self.merge()
        self.assertFalse(leaf.leaf_documents(self.repository, "pull_request", event, merge))

    def test_actual_added_whitespace_fails_document_validation(self):
        self.write(GUIDE, "A newly added line has trailing space \n")
        self.commit()
        event, merge = self.merge()
        with self.assertRaises(leaf.InvalidLeaf):
            leaf.leaf_documents(self.repository, "pull_request", event, merge)


if __name__ == "__main__":
    unittest.main()
