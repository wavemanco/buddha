"""The forward CLI guards key entry and preserves completed keyless inspection."""

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from buddha.__main__ import main


class SourceForwardCLITests(unittest.TestCase):
    def test_nonlive_and_missing_definition_refuse_before_keys_or_edge_checks(self):
        base = ["source-edge-run", "--run", "not-a-prepared-edge"]
        for extra, parsing in (
            (["--definition-sha256", "a" * 64, "--prompt-keys"], False),
            (["--live", "--prompt-keys"], True),
        ):
            with (
                self.subTest(parsing=parsing),
                patch("buddha.__main__._key_environment") as keys,
                patch("buddha.source_forward.check_source_edge") as check,
                patch("buddha.source_forward.run_source_edge") as run,
                patch("buddha.gateway.RawHTTPTransport") as transport,
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()),
            ):
                if parsing:
                    with self.assertRaises(SystemExit) as stopped:
                        main([*base, *extra])
                    self.assertEqual(stopped.exception.code, 2)
                else:
                    self.assertEqual(main([*base, *extra]), 2)
                    self.assertEqual(
                        json.loads(output.getvalue())["error"],
                        "source-edge-run requires explicit --live",
                    )
                keys.assert_not_called()
                check.assert_not_called()
                run.assert_not_called()
                transport.assert_not_called()

    def test_invalid_definition_stops_before_keys_and_transport(self):
        from buddha.source_forward import SourceForwardError

        with (
            patch("buddha.__main__._key_environment") as keys,
            patch(
                "buddha.source_forward.check_source_edge",
                side_effect=SourceForwardError("edge definition differs"),
            ),
            patch("buddha.source_forward.run_source_edge") as run,
            patch("buddha.gateway.RawHTTPTransport") as transport,
            redirect_stdout(io.StringIO()) as output,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(
                main(
                    [
                        "source-edge-run",
                        "--run",
                        "not-a-prepared-edge",
                        "--definition-sha256",
                        "a" * 64,
                        "--live",
                        "--prompt-keys",
                    ]
                ),
                2,
            )
            self.assertEqual(json.loads(output.getvalue())["error"], "edge definition differs")
            keys.assert_not_called()
            run.assert_not_called()
            transport.assert_not_called()

    def test_completed_run_inspects_pinned_report_without_keys_or_current_execution_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw = b'{"retained":true}'
            (directory / "report.json").write_bytes(raw)
            result = {"status": "complete", "claim": "supplied CLI result"}
            with (
                patch("buddha.__main__._key_environment") as keys,
                patch("buddha.source_forward.check_source_edge") as check,
                patch("buddha.source_forward.run_source_edge") as run,
                patch("buddha.gateway.RawHTTPTransport") as transport,
                patch(
                    "buddha.source_forward_results.inspect_source_edge", return_value=result
                ) as inspect,
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    main(
                        [
                            "source-edge-run",
                            "--run",
                            str(directory),
                            "--definition-sha256",
                            "a" * 64,
                            "--live",
                            "--prompt-keys",
                        ]
                    ),
                    0,
                )
                self.assertEqual(json.loads(output.getvalue()), result)
                inspect.assert_called_once_with(
                    directory,
                    expected_definition_sha256="a" * 64,
                    expected_report_sha256=hashlib.sha256(raw).hexdigest(),
                )
                keys.assert_not_called()
                check.assert_not_called()
                run.assert_not_called()
                transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
