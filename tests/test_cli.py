"""Exercise the public local commands and fail-closed budget parsing."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from authorization_helpers import authorized_run

from buddha.__main__ import _check_upstream, _key_environment, _settings, _usd, main
from buddha.benchmark import UPSTREAM_COMMIT
from buddha.evaluation import ValidationError


class CLITests(unittest.TestCase):
    def test_retired_launch_commands_refuse_before_keys_sources_or_argv_echo(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "NOT-CREATED"
            for command in (
                "prepare",
                "run",
                "search-prepare",
                "search-run",
                "continuation-prepare",
            ):
                for extra in (
                    [],
                    ["--out", str(destination), "--live", "--prompt-keys", "ARGV-SECRET-CANARY"],
                ):
                    with (
                        self.subTest(command=command, supplied_arguments=bool(extra)),
                        patch("buddha.__main__._key_environment") as keys,
                        patch("buddha.__main__._settings") as settings,
                        patch("buddha.__main__.load_run") as source,
                        patch("http.client.HTTPSConnection") as connection,
                        redirect_stdout(io.StringIO()) as output,
                        redirect_stderr(io.StringIO()) as notices,
                    ):
                        self.assertEqual(main([command, *extra]), 2)
                    record = json.loads(output.getvalue())
                    self.assertEqual(record["reason"], "retired_command")
                    self.assertEqual(record["command"], command)
                    self.assertNotIn("ARGV-SECRET-CANARY", output.getvalue() + notices.getvalue())
                    self.assertFalse(destination.exists())
                    keys.assert_not_called()
                    settings.assert_not_called()
                    source.assert_not_called()
                    connection.assert_not_called()

    def test_source_review_collection_forwards_explicit_and_empty_submissions(self):
        from buddha import source_review_handoff

        base = [
            "source-review-inspect",
            "--run",
            "original",
            "--kind",
            "final",
            "--report-sha256",
            "a" * 64,
            "--plan",
            "plan.json",
            "--plan-sha256",
            "b" * 64,
            "--round-plan",
            "round.json",
            "--round-plan-sha256",
            "c" * 64,
            "--out",
            "collection",
        ]
        for extra, refs, status, code in (
            ([], [], "incomplete", 3),
            (
                ["--submission", "human-a", "forms/a.json", "d" * 64],
                [
                    {
                        "reviewer_id": "human-a",
                        "path": str(Path("forms/a.json").absolute()),
                        "sha256": "d" * 64,
                    }
                ],
                "complete",
                0,
            ),
        ):
            summary = {"format": "buddha.source-review-collection.v1", "status": status}
            with (
                self.subTest(status=status),
                patch.object(
                    source_review_handoff, "collect_source_reviews", return_value=summary
                ) as collect,
                patch("buddha.__main__._key_environment") as keys,
                patch("http.client.HTTPSConnection") as connection,
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(base + extra), code)
            self.assertEqual(json.loads(output.getvalue()), summary)
            collect.assert_called_once_with(
                Path("original"),
                kind="final",
                expected_report_sha256="a" * 64,
                plan=Path("plan.json"),
                expected_plan_sha256="b" * 64,
                round_plan=Path("round.json"),
                expected_round_plan_sha256="c" * 64,
                submissions=refs,
                output=Path("collection"),
            )
            keys.assert_not_called()
            connection.assert_not_called()

    def test_source_review_collection_has_offline_refusal_and_interruption_output(self):
        from buddha import source_review_handoff
        from buddha.source_review import SourceReviewError

        argv = [
            "source-review-inspect",
            "--run",
            "original",
            "--kind",
            "improver",
            "--report-sha256",
            "a" * 64,
            "--plan",
            "plan.json",
            "--plan-sha256",
            "b" * 64,
            "--round-plan",
            "round.json",
            "--round-plan-sha256",
            "c" * 64,
            "--out",
            "collection",
        ]
        for error, code, reason in (
            (SourceReviewError("changed form"), 2, "refused"),
            (KeyboardInterrupt(), 130, "interrupted"),
        ):
            with (
                self.subTest(reason=reason),
                patch.object(source_review_handoff, "collect_source_reviews", side_effect=error),
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()) as notice,
            ):
                self.assertEqual(main(argv), code)
            record = json.loads(output.getvalue())
            self.assertEqual(record["format"], "buddha.source-review-collection.v1")
            self.assertEqual((record["stage"], record["reason"]), ("collection", reason))
            self.assertNotIn("reservation", notice.getvalue())

    def test_source_review_export_is_keyless_and_retains_incomplete_status(self):
        from buddha import source_review_handoff

        argv = [
            "source-review-export",
            "--run",
            "original",
            "--kind",
            "final",
            "--report-sha256",
            "a" * 64,
            "--plan",
            "plan.json",
            "--plan-sha256",
            "b" * 64,
            "--out",
            "review-output",
            "--reviewer",
            "reviewer-a",
            "human",
            "--reviewer",
            "reviewer-b",
            "model",
        ]
        for status, expected_code in (("complete", 0), ("incomplete", 3)):
            summary = {"format": "buddha.source-review-export.v1", "status": status}
            with (
                self.subTest(status=status),
                patch.object(
                    source_review_handoff, "export_source_review", return_value=summary
                ) as export,
                patch("buddha.__main__._key_environment") as keys,
                patch("http.client.HTTPSConnection") as connection,
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(argv), expected_code)
            self.assertEqual(json.loads(output.getvalue()), summary)
            export.assert_called_once_with(
                Path("original"),
                kind="final",
                expected_report_sha256="a" * 64,
                plan=Path("plan.json"),
                expected_plan_sha256="b" * 64,
                output=Path("review-output"),
                reviewers=[
                    {"id": "reviewer-a", "type": "human"},
                    {"id": "reviewer-b", "type": "model"},
                ],
            )
            keys.assert_not_called()
            connection.assert_not_called()

    def test_source_review_export_has_specific_refusal_and_interruption_output(self):
        from buddha import source_review_handoff
        from buddha.source_review import SourceReviewError

        argv = [
            "source-review-export",
            "--run",
            "original",
            "--kind",
            "improver",
            "--report-sha256",
            "a" * 64,
            "--plan",
            "plan.json",
            "--plan-sha256",
            "b" * 64,
            "--out",
            "review-output",
            "--reviewer",
            "reviewer-a",
            "human",
        ]
        for error, code, reason in (
            (SourceReviewError("review output conflict"), 2, "refused"),
            (KeyboardInterrupt(), 130, "interrupted"),
        ):
            with (
                self.subTest(reason=reason),
                patch.object(source_review_handoff, "export_source_review", side_effect=error),
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()) as notices,
            ):
                self.assertEqual(main(argv), code)
            record = json.loads(output.getvalue())
            self.assertEqual(
                (record["status"], record["stage"], record["reason"]), ("stopped", "export", reason)
            )
            self.assertEqual(record["output"], "review-output")
            self.assertNotIn("reservation", notices.getvalue())

    def test_continuation_source_is_read_only_and_requires_no_keys(self):
        source = SimpleNamespace(
            history=SimpleNamespace(
                run_id="source", manifest_sha256="a" * 64, ledger_sha256="b" * 64
            ),
            completed=tuple(SimpleNamespace(actual_microusd=190) for _ in range(9)),
            unknown=SimpleNamespace(operation_id="c" * 64, reserve_microusd=532373),
        )
        reader = Mock(return_value=source)
        module = ModuleType("buddha.continuation")
        module.read_source = reader
        with (
            patch.dict(sys.modules, {"buddha.continuation": module}),
            patch("buddha.__main__._key_environment") as keys,
            patch("http.client.HTTPSConnection") as connection,
            redirect_stdout(io.StringIO()) as output,
        ):
            result = main(
                [
                    "continuation-source",
                    "--source",
                    "source",
                    "--manifest-sha256",
                    "a" * 64,
                    "--ledger-sha256",
                    "b" * 64,
                    "--archive",
                    "source.zip",
                    "--archive-sha256",
                    "d" * 64,
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["completed_receipts"], 9)
        self.assertEqual(json.loads(output.getvalue())["model_calls"], 0)
        reader.assert_called_once_with(
            Path("source"),
            manifest_sha256="a" * 64,
            ledger_sha256="b" * 64,
            archived_runtime_zip=Path("source.zip"),
            archived_runtime_sha256="d" * 64,
        )
        keys.assert_not_called()
        connection.assert_not_called()

    def test_authorization_create_and_inspect_are_offline_and_inspection_is_readonly(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("http.client.HTTPSConnection") as connection,
            patch("buddha.__main__._key_environment") as keys,
        ):
            path = Path(temporary) / "authority.sqlite3"
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(
                    main(
                        [
                            "authorization-create",
                            "--out",
                            str(path),
                            "--budget-usd",
                            "1.25",
                            "--max-calls",
                            "4",
                            "--scope",
                            "A declared bounded offline fixture",
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(output.getvalue())["budget_microusd"], 1_250_000)
            before = path.read_bytes()
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(
                    main(
                        [
                            "authorization-inspect",
                            "--authorization",
                            str(path),
                        ]
                    ),
                    0,
                )
            summary = json.loads(output.getvalue())
            self.assertEqual(summary["scope"], "A declared bounded offline fixture")
            self.assertEqual(summary["remaining_calls"], 4)
            self.assertEqual(summary["operation_count"], 0)
            self.assertEqual(path.read_bytes(), before)
            connection.assert_not_called()
            keys.assert_not_called()

    def test_authorization_creation_rejects_blank_scope_without_storage(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            path = Path(temporary) / "authority.sqlite3"
            self.assertEqual(
                main(
                    [
                        "authorization-create",
                        "--out",
                        str(path),
                        "--budget-usd",
                        "1",
                        "--max-calls",
                        "4",
                        "--scope",
                        "  ",
                    ]
                ),
                2,
            )
            self.assertFalse(path.exists())

    def test_authorization_deactivate_is_offline_and_prevents_further_dispatch(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("http.client.HTTPSConnection") as connection,
            patch("buddha.__main__._key_environment") as keys,
        ):
            directory = Path(temporary) / "run"
            authority, _ = authorized_run(directory)
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(
                    main(
                        [
                            "authorization-deactivate",
                            "--authorization",
                            str(authority.path),
                            "--run-id",
                            "run",
                            "--reason",
                            "Preserve superseded attempt",
                        ]
                    ),
                    0,
                )
            summary = json.loads(output.getvalue())
            self.assertFalse(summary["runs"][0]["active"])
            with self.assertRaises(ValidationError):
                authority.for_run(directory).authorize_dispatch()
            self.assertEqual(summary["operation_count"], 0)
            connection.assert_not_called()
            keys.assert_not_called()

    def test_hidden_keys_are_process_local_and_removed_even_after_failure(self):
        settings = _settings(Path(__file__).parent.parent / "examples" / "live-config.json", "50")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.__main__.sys.stdin.isatty", return_value=True),
            patch("buddha.__main__.sys.stderr.isatty", return_value=True),
            patch("buddha.__main__.getpass.getpass", side_effect=["dummy-openai", "dummy-claude"]),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                with _key_environment(settings, prompt_keys=True):
                    self.assertEqual(os.environ["OPENAI_API_KEY"], "dummy-openai")
                    self.assertEqual(os.environ["ANTHROPIC_API_KEY"], "dummy-claude")
                    raise RuntimeError("stop")
            self.assertNotIn("OPENAI_API_KEY", os.environ)
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)

    def test_hidden_prompt_preserves_existing_environment_and_cleans_partial_input(self):
        settings = _settings(Path(__file__).parent.parent / "examples" / "live-config.json", "50")
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "dummy-existing"}, clear=True),
            patch("buddha.__main__.sys.stdin.isatty", return_value=True),
            patch("buddha.__main__.sys.stderr.isatty", return_value=True),
            patch("buddha.__main__.getpass.getpass", return_value="dummy-claude") as prompt,
        ):
            with _key_environment(settings, prompt_keys=True):
                self.assertEqual(os.environ["OPENAI_API_KEY"], "dummy-existing")
            prompt.assert_called_once()
            self.assertEqual(dict(os.environ), {"OPENAI_API_KEY": "dummy-existing"})
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.__main__.sys.stdin.isatty", return_value=True),
            patch("buddha.__main__.sys.stderr.isatty", return_value=True),
            patch("buddha.__main__.getpass.getpass", side_effect=["dummy-openai", EOFError]),
        ):
            with self.assertRaises(ValidationError):
                with _key_environment(settings, prompt_keys=True):
                    self.fail("incomplete input cannot execute a run")
            self.assertEqual(dict(os.environ), {})

    def test_hidden_prompt_never_falls_back_to_echoed_input(self):
        settings = _settings(Path(__file__).parent.parent / "examples" / "live-config.json", "50")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("buddha.__main__.sys.stdin.isatty", return_value=False),
            patch("buddha.__main__.getpass.getpass") as prompt,
        ):
            with self.assertRaises(ValidationError):
                with _key_environment(settings, prompt_keys=True):
                    self.fail("non-terminal input cannot execute")
            prompt.assert_not_called()

    def test_default_path_never_prompts_or_reads_stdin(self):
        settings = _settings(Path(__file__).parent.parent / "examples" / "live-config.json", "50")
        with patch("buddha.__main__.getpass.getpass") as prompt:
            with _key_environment(settings, prompt_keys=False):
                pass
            prompt.assert_not_called()

    def test_getpass_warning_fails_closed_and_preserves_empty_environment_entry(self):
        import getpass

        settings = _settings(Path(__file__).parent.parent / "examples" / "live-config.json", "50")
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=True),
            patch("buddha.__main__.sys.stdin.isatty", return_value=True),
            patch("buddha.__main__.sys.stderr.isatty", return_value=True),
            patch("buddha.__main__.getpass.getpass", side_effect=getpass.GetPassWarning),
        ):
            with self.assertRaises(ValidationError):
                with _key_environment(settings, prompt_keys=True):
                    self.fail("echoed input must never be used")
            self.assertEqual(dict(os.environ), {"OPENAI_API_KEY": ""})

    def test_current_upstream_is_required_before_a_new_cli_experiment(self):
        for status, sha, accepted in [
            (200, UPSTREAM_COMMIT, True),
            (200, "0" * 40, False),
            (503, UPSTREAM_COMMIT, False),
        ]:
            response = Mock(status=status)
            response.read.return_value = json.dumps({"object": {"sha": sha}}).encode()
            connection = Mock()
            connection.getresponse.return_value = response
            with (
                self.subTest(status=status, sha=sha),
                patch("buddha.__main__.http.client.HTTPSConnection", return_value=connection),
            ):
                if accepted:
                    _check_upstream()
                else:
                    with self.assertRaises(ValidationError):
                        _check_upstream()
                connection.close.assert_called_once()

    def test_demo_resume_inspect_and_verify_are_offline(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = str(Path(temporary) / "demo")
            for argv in [
                ["demo", "--out", target],
                ["demo", "--out", target],
                ["inspect", "--run", target],
                ["verify", "--run", target],
            ]:
                with self.subTest(argv=argv), redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(argv), 0)
                result = json.loads(output.getvalue())
                if argv[0] == "demo":
                    self.assertEqual(result["paid_calls"], 0)
                if argv[0] == "inspect":
                    self.assertEqual(result["ledger"]["operation_count"], 12)

    def test_search_demo_resume_and_inspection_are_offline(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = str(Path(temporary) / "search")
            results = []
            for argv in [
                ["search-demo", "--out", target],
                ["search-demo", "--out", target],
                ["search-inspect", "--run", target],
            ]:
                with self.subTest(argv=argv), redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(argv), 0)
                results.append(json.loads(output.getvalue()))
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[0]["paid_calls"], 0)
            self.assertGreaterEqual(len(results[0]["report"]["candidates"]), 3)

    def test_usd_requires_exact_positive_decimal(self):
        self.assertEqual(_usd("25"), 25000000)
        self.assertEqual(_usd("0.000001"), 1)
        for value in [None, True, 25, "0", "-1", "NaN", "Infinity", "1e100000", "0.0000001"]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                _usd(value)

    def test_shipped_configuration_has_no_spending_cap(self):
        path = Path(__file__).parent.parent / "examples" / "live-config.json"
        with self.assertRaises(ValidationError):
            _settings(path, None)
        settings = _settings(path, "25")
        self.assertEqual(settings.budget_microusd, 25000000)
        self.assertEqual(settings.quality.model, "claude-opus-5")

    def test_invalid_run_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["inspect", "--run", temporary]), 2)
        self.assertIn("error", json.loads(output.getvalue()))

    def test_watch_command_is_offline_and_preserves_json_stdout(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("buddha.progress.watch_run", return_value={"status": "needs_review"}) as watch,
            redirect_stdout(io.StringIO()) as output,
        ):
            (Path(temporary) / "manifest.json").write_text("{}")
            self.assertEqual(main(["watch", "--run", temporary]), 2)
            self.assertEqual(json.loads(output.getvalue()), {"status": "needs_review"})
            watch.assert_called_once_with(Path(temporary))


if __name__ == "__main__":
    unittest.main()
