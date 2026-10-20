"""Exercise the public local commands and fail-closed budget parsing."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from authorization_helpers import authorized_run

from buddha.__main__ import _check_upstream, _key_environment, _settings, _usd, main
from buddha.benchmark import UPSTREAM_COMMIT
from buddha.diagnostics import DiagnosticHTTPTransport
from buddha.evaluation import ValidationError
from buddha.provider import Reply
from buddha.run import prepare_run


class CLITests(unittest.TestCase):
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

    def bind_authorization(self, root, target):
        authorization = root / "authorization.sqlite3"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "authorization-create",
                        "--out",
                        str(authorization),
                        "--budget-usd",
                        "50",
                        "--max-calls",
                        "128",
                        "--scope",
                        "Mocked CLI integration only",
                    ]
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "authorization-bind",
                        "--authorization",
                        str(authorization),
                        "--run",
                        str(target),
                    ]
                ),
                0,
            )
        return authorization

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

    def test_prompted_key_sentinels_never_enter_artifacts_requests_or_output(self):
        settings = replace(
            _settings(Path(__file__).parent.parent / "examples" / "live-config.json", "50"),
            bounds_checked_on=datetime.now(UTC).date().isoformat(),
        )
        sentinels = ("dummy-secret-openai", "dummy-secret-anthropic")

        def received(prepared):
            for secret in sentinels:
                self.assertNotIn(secret.encode(), prepared.body)
            body = json.loads(prepared.body)
            name = body.get("response_format", {}).get("json_schema", {}).get("name")
            text = "Synthetic answer."
            if name == "Partition":
                text = '{"groups":[[0,1,2,3,4,5,6,7,8,9]]}'
            elif body["model"] == settings.quality.model:
                text = '{"score":8}'
            return Reply(text, body["model"], "dummy-receipt", 10, 5, "stop")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data.jsonl"
            data.write_text('{"id":"dev","prompt":"Offer a useful alternative."}\n')
            import hashlib

            target = root / "run"
            prepare_run(
                target,
                dataset_path=data,
                expected_dataset_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                settings=settings,
                synthetic=True,
            )
            authorization = self.bind_authorization(root, target)
            with (
                redirect_stderr(io.StringIO()) as progress,
                patch.dict(os.environ, {}, clear=True),
                patch("buddha.__main__.sys.stdin.isatty", return_value=True),
                patch("buddha.__main__.sys.stderr.isatty", return_value=True),
                patch("buddha.__main__.getpass.getpass", side_effect=sentinels),
                patch("buddha.provider.http.client.HTTPSConnection"),
                patch.object(
                    DiagnosticHTTPTransport, "send_prepared", side_effect=received
                ) as send,
                redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(
                    main(
                        [
                            "run",
                            "--run",
                            str(target),
                            "--live",
                            "--prompt-keys",
                            "--authorization",
                            str(authorization),
                        ]
                    ),
                    0,
                )
                self.assertEqual(send.call_count, 12)
                for secret in sentinels:
                    self.assertNotIn(secret, output.getvalue())
                    self.assertNotIn(secret, progress.getvalue())
                self.assertIn("OPENAI_API_KEY received", progress.getvalue())
                self.assertIn("ANTHROPIC_API_KEY received", progress.getvalue())
                self.assertIn("Starting", progress.getvalue())
                self.assertIn("Run complete", progress.getvalue())
                self.assertEqual(dict(os.environ), {})
            for path in target.rglob("*"):
                if path.is_file():
                    for secret in sentinels:
                        self.assertNotIn(secret.encode(), path.read_bytes(), str(path))

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

    def test_interrupted_execution_never_prints_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = str(Path(temporary) / "demo")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["demo", "--out", target]), 0)
            with (
                patch("buddha.__main__.run_baseline", side_effect=KeyboardInterrupt),
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()) as progress,
            ):
                self.assertEqual(main(["run", "--run", target]), 130)
            self.assertIn("interrupted", json.loads(output.getvalue())["error"])
            self.assertNotIn("Run complete", progress.getvalue())
            self.assertIn("Interrupted", progress.getvalue())

    def test_http_failure_surfaces_safe_diagnostics_without_retry(self):
        import hashlib

        settings = replace(
            _settings(Path(__file__).parent.parent / "examples" / "live-config.json", "50"),
            bounds_checked_on=datetime.now(UTC).date().isoformat(),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data.jsonl"
            data.write_text('{"id":"dev","prompt":"Offer a useful alternative."}\n')
            target = root / "run"
            prepare_run(
                target,
                dataset_path=data,
                expected_dataset_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                settings=settings,
                synthetic=True,
            )
            authorization = self.bind_authorization(root, target)
            response = Mock(status=429)
            response.read.return_value = b'{"error":{"message":"secret-error-sentinel"}}'
            response.getheader.return_value = "req_A12345678"
            connection = Mock()
            connection.getresponse.return_value = response
            with (
                patch.dict(
                    os.environ,
                    {
                        "OPENAI_API_KEY": "secret-key-sentinel",
                        "ANTHROPIC_API_KEY": "secret-key-sentinel",
                    },
                    clear=True,
                ),
                patch("http.client.HTTPSConnection", return_value=connection),
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()) as progress,
            ):
                self.assertEqual(
                    main(
                        [
                            "run",
                            "--run",
                            str(target),
                            "--live",
                            "--authorization",
                            str(authorization),
                        ]
                    ),
                    2,
                )
            result = json.loads(output.getvalue())
            self.assertEqual(result["diagnostic"]["http_status"], 429)
            self.assertEqual(result["diagnostic"]["provider_request_id"], "req_A12345678")
            connection.request.assert_called_once()
            for sentinel in ("secret-key-sentinel", "secret-error-sentinel"):
                self.assertNotIn(sentinel, output.getvalue() + progress.getvalue())
                for path in (target / "diagnostics").rglob("*.json"):
                    self.assertNotIn(sentinel, path.read_text())


if __name__ == "__main__":
    unittest.main()
