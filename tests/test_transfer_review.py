"""The transfer review bridge keeps its source phase explicit at every entry."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


class TransferReviewTests(unittest.TestCase):
    def test_review_commands_forward_explicit_transfer_kind_and_status(self):
        from buddha import source_review_handoff
        from buddha.__main__ import main

        common = [
            "--run",
            "original",
            "--kind",
            "transfer",
            "--report-sha256",
            "a" * 64,
            "--plan",
            "plan.json",
            "--plan-sha256",
            "b" * 64,
            "--out",
            "review-output",
        ]
        values = {
            "kind": "transfer",
            "expected_report_sha256": "a" * 64,
            "plan": Path("plan.json"),
            "expected_plan_sha256": "b" * 64,
            "output": Path("review-output"),
        }
        for command, function, extra, arguments, status, code in (
            (
                "source-review-export",
                "export_source_review",
                ["--reviewer", "reviewer-a", "human"],
                {"reviewers": [{"id": "reviewer-a", "type": "human"}]},
                "complete",
                0,
            ),
            (
                "source-review-inspect",
                "collect_source_reviews",
                [
                    "--round-plan",
                    "round.json",
                    "--round-plan-sha256",
                    "c" * 64,
                    "--submission",
                    "reviewer-a",
                    "forms/a.json",
                    "d" * 64,
                ],
                {
                    "round_plan": Path("round.json"),
                    "expected_round_plan_sha256": "c" * 64,
                    "submissions": [
                        {
                            "reviewer_id": "reviewer-a",
                            "path": str(Path("forms/a.json").absolute()),
                            "sha256": "d" * 64,
                        }
                    ],
                },
                "incomplete",
                3,
            ),
        ):
            summary = {
                "format": "buddha.source-review-"
                + ("export" if command.endswith("export") else "collection")
                + ".v1",
                "status": status,
            }
            with (
                self.subTest(command=command),
                patch.object(source_review_handoff, function, return_value=summary) as handoff,
                patch("buddha.__main__._key_environment") as keys,
                patch("http.client.HTTPSConnection") as connection,
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main([command, *common, *extra]), code)
                self.assertEqual(json.loads(output.getvalue()), summary)
                handoff.assert_called_once_with(Path("original"), **values, **arguments)
                keys.assert_not_called()
                connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
