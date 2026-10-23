"""One frozen capacity target through real shared accounting and mocked HTTPS."""

import hashlib
import io
import json
import os
import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import test_gateway as fixture

from buddha.authorization import Authorization
from buddha.releases import Release, prepare_selection


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class CapacityLaunchTests(unittest.TestCase):
    def setUp(self):
        from buddha import capacity_launch

        self.module = capacity_launch
        self.env = fixture.GatewayTests()
        self.env.setUp()
        self.addCleanup(self.env.doCleanups)
        self.root = self.env.root
        self.parent = b"# Synthetic parent; never executed.\n"
        (self.env.roots["agent"] / "identity.txt").unlink()
        (self.env.roots["agent"] / "candidate.py").write_bytes(self.parent)
        spec = replace(
            self.env.spec,
            model="gpt-6.1-sol",
            input_token_ceiling=1050000,
            max_output_tokens=32768,
            input_microusd_per_million=1,
            output_microusd_per_million=2,
        )
        self.env.profiles["profiles"]["primary"]["spec"] = asdict(spec)
        self.env.profiles["profiles"]["primary"]["response_models"] = [spec.model]
        self.env.write("host", "profiles/openai.json", json.dumps(self.env.profiles))
        self.selection = prepare_selection(
            Release.from_record(self.env.release_record),
            self.env.roots,
            capabilities={fixture.CAPABILITY: "profiles/openai.json"},
        )
        self.authority = Authorization.create(
            self.root / "capacity.sqlite3",
            authorization_id="capacity-synthetic-one",
            budget_microusd=10000,
            max_calls=1,
            scope="synthetic capacity only",
        )
        self.directory = self.root / "capacity-study"
        self.body = encoded(
            {
                "model": spec.model,
                "max_completion_tokens": 32768,
                "service_tier": "default",
                "reasoning_effort": "low",
                "messages": [{"role": "user", "content": "Synthetic frozen capacity request."}],
            }
        )
        self.request = self.root / "capacity-request.json"
        self.request.write_bytes(self.body)
        protocol = json.loads(
            (
                Path(capacity_launch.__file__).parents[1]
                / "docs/conformance/src02-capacity-protocol.json"
            ).read_bytes()
        )
        protocol["request"]["sha256"] = sha(self.body)
        protocol["request"]["bytes"] = len(self.body)
        protocol["custody"]["prospective_parent_agent_sha256"] = self.selection.agent_sha256
        protocol["custody"]["prospective_parent_source"] = {
            "bytes": len(self.parent),
            "sha256": sha(self.parent),
        }
        self.protocol = self.root / "capacity-protocol.json"
        self.protocol.write_bytes(encoded(protocol))
        pins = {
            str(path): sha(path.read_bytes())
            for path in [*capacity_launch._sources(), self.request, self.protocol]
        }
        self.record = {
            "format": "buddha.source-capacity-launch.v1",
            "directory": str(self.directory),
            "authorization_path": str(self.authority.path),
            "requested_terms": self.authority._terms(),
            "selection": self.selection.to_record(),
            "roots": {key: str(value) for key, value in self.env.roots.items()},
            "profile_id": "primary",
            "request_path": str(self.request),
            "protocol_path": str(self.protocol),
            "source_sha256": pins,
            "account_scope": "synthetic default public-price account assertion",
            "timeout_seconds": 120,
        }
        self.handoff = self.root / "capacity-launch.json"
        self.handoff.write_bytes(encoded(self.record))
        self.digest = sha(self.handoff.read_bytes())

    def run_launch(self, **changes):
        return self.module.run_launch(
            self.handoff,
            expected_sha256=self.digest,
            **(
                {
                    "live": True,
                    "prompt_keys": False,
                    "confirm_project_key": True,
                    "notice": lambda text: None,
                }
                | changes
            ),
        )

    def connection(self, *, finish="stop", content=None):
        value = {
            "model": "gpt-6.1-sol",
            "service_tier": "default",
            "choices": [
                {
                    "finish_reason": finish,
                    "message": {
                        "content": content
                        or json.dumps(
                            {
                                "source": "# Changed synthetic source.\n",
                                "hypothesis": "Synthetic change.",
                            }
                        ),
                        "refusal": None,
                    },
                }
            ],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
        }
        return self.env.connection(self.env.response(**value))

    def test_preflight_and_changed_body_refuse_before_keys_owner_or_spending(self):
        checked = self.module.check_launch(self.handoff, expected_sha256=self.digest)
        self.assertEqual(checked["state"], "fresh")
        self.assertFalse(self.directory.exists())
        self.request.write_bytes(self.body + b" ")
        with patch.object(self.module.credentials, "key_environment") as keys:
            with self.assertRaises(self.module.CapacityLaunchError):
                self.run_launch()
        keys.assert_not_called()
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.authority.summary()["operation_count"], 0)

    def test_pinned_unsupported_body_refuses_during_passive_preflight(self):
        body = encoded(json.loads(self.body) | {"tools": []})
        self.request.write_bytes(body)
        protocol = json.loads(self.protocol.read_bytes())
        protocol["request"].update(sha256=sha(body), bytes=len(body))
        self.protocol.write_bytes(encoded(protocol))
        for path in (self.request, self.protocol):
            self.record["source_sha256"][str(path)] = sha(path.read_bytes())
        self.handoff.write_bytes(encoded(self.record))
        self.digest = sha(self.handoff.read_bytes())
        with self.assertRaises(self.module.CapacityLaunchError):
            self.module.check_launch(self.handoff, expected_sha256=self.digest)
        with (
            patch.object(self.module.credentials, "key_environment") as keys,
            self.assertRaises(self.module.CapacityLaunchError),
        ):
            self.run_launch()
        keys.assert_not_called()
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.authority.summary()["operation_count"], 0)

    def test_complete_measurement_is_anchored_and_replays_keyless_without_send(self):
        connection = self.connection()
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": fixture.KEY}),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            result = self.run_launch()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["measurement"]["decision"], "pass")
        self.assertEqual(connection.request.call_count, 1)
        before = self.authority.summary()
        self.assertEqual(before["operation_count"], 1)
        self.assertEqual(before["reserved_microusd"], 0)
        self.assertFalse(before["runs"][0]["active"])
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(self.module.credentials, "key_environment") as keys,
            patch("http.client.HTTPSConnection") as network,
        ):
            replay = self.run_launch(live=False, confirm_project_key=False)
        self.assertEqual(replay, result)
        keys.assert_not_called()
        network.assert_not_called()
        self.assertEqual(self.authority.summary(), before)

        with self.assertRaises(self.module.CapacityLaunchError):
            self.run_launch(
                live=False,
                confirm_project_key=False,
                transport=self.module.gateway.RawHTTPTransport(
                    allow_paid=True, timeout_seconds=120
                ),
            )
        self.assertEqual(self.authority.summary(), before)

    def test_length_reply_is_terminal_partial_not_a_new_paid_opportunity(self):
        connection = self.connection(finish="length")
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": fixture.KEY}),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            result = self.run_launch()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["measurement"]["reason"], "output_limit")
        self.assertFalse(self.authority.summary()["runs"][0]["active"])
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("http.client.HTTPSConnection") as network,
        ):
            self.assertEqual(self.run_launch(live=False, confirm_project_key=False), result)
        network.assert_not_called()
        self.assertEqual(self.authority.summary()["operation_count"], 1)

    def test_unknown_stays_partial_and_blocks_key_entry_and_new_owner(self):
        connection = self.connection()
        connection.getresponse.side_effect = TimeoutError("synthetic timeout")
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": fixture.KEY}),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            result = self.run_launch()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["reason"], "provider_unknown")
        before = self.authority.summary()
        self.assertGreater(before["reserved_microusd"], 0)
        with (
            patch.object(self.module.credentials, "key_environment") as keys,
            patch("http.client.HTTPSConnection") as network,
        ):
            self.assertEqual(self.run_launch()["reason"], "provider_unknown")
        keys.assert_not_called()
        network.assert_not_called()
        self.assertEqual(self.authority.summary(), before)

    def test_tampered_completed_artifact_refuses_without_keys_or_send(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": fixture.KEY}),
            patch("http.client.HTTPSConnection", return_value=self.connection()),
        ):
            self.run_launch()
        (self.directory / "attempts/0-0/report.json").write_bytes(b"{}\n")
        before = self.authority.summary()
        with (
            patch.object(self.module.credentials, "key_environment") as keys,
            patch("http.client.HTTPSConnection") as network,
        ):
            with self.assertRaises(self.module.CapacityLaunchError):
                self.run_launch(live=False, confirm_project_key=False)
        keys.assert_not_called()
        network.assert_not_called()
        self.assertEqual(self.authority.summary(), before)

    def test_interrupted_assessment_reuses_only_the_completed_original_reply(self):
        connection = self.connection()
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": fixture.KEY}),
            patch("http.client.HTTPSConnection", return_value=connection),
            patch.object(
                self.module.source_capacity, "assess_reply", side_effect=KeyboardInterrupt
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_launch()
        before = self.authority.summary()
        self.assertEqual(before["operation_count"], 1)
        self.assertEqual(before["reserved_microusd"], 0)
        self.assertTrue(before["runs"][0]["active"])
        observation = json.loads((self.directory / "observations/0.json").read_bytes())
        self.assertEqual(
            (observation["status"], observation["reason"], observation["stage"]),
            ("partial", "cancelled", "assessment"),
        )
        raw = (self.directory / "attempts/0-0/raw-envelope.json").read_bytes()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(self.module.credentials, "key_environment") as keys,
            patch("http.client.HTTPSConnection") as network,
        ):
            result = self.run_launch(live=False, confirm_project_key=False)
        keys.assert_not_called()
        network.assert_not_called()
        self.assertEqual(result["status"], "complete")
        self.assertEqual((self.directory / "attempts/0-1/raw-envelope.json").read_bytes(), raw)
        self.assertEqual(connection.request.call_count, 1)
        self.assertEqual(self.authority.summary()["spent_microusd"], before["spent_microusd"])

    def test_seal_without_original_authority_anchor_is_never_repaired(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": fixture.KEY}),
            patch("http.client.HTTPSConnection", return_value=self.connection()),
            patch.object(Authorization, "deactivate", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            self.run_launch()
        self.assertTrue((self.directory / "completed/0.json").is_file())
        before = self.authority.summary()
        self.assertTrue(before["runs"][0]["active"])
        with (
            patch.object(self.module.credentials, "key_environment") as keys,
            patch("http.client.HTTPSConnection") as network,
            self.assertRaises(self.module.CapacityLaunchError),
        ):
            self.run_launch(live=False, confirm_project_key=False)
        keys.assert_not_called()
        network.assert_not_called()
        self.assertEqual(self.authority.summary(), before)

    def test_unsent_preparation_failure_is_recorded_and_reuses_original_reservation(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": fixture.KEY}),
            patch("http.client.HTTPSConnection", side_effect=OSError("synthetic local failure")),
        ):
            result = self.run_launch()
        self.assertEqual(
            (result["status"], result["reason"], result["stage"]),
            ("partial", "execution_stopped", "request"),
        )
        before = self.authority.summary()
        self.assertEqual(before["operation_count"], 1)
        self.assertGreater(before["reserved_microusd"], 0)
        manifest = (self.directory / "owner/manifest.json").read_bytes()
        connection = self.connection()
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": fixture.KEY}),
            patch("http.client.HTTPSConnection", return_value=connection),
        ):
            complete = self.run_launch()
        self.assertEqual(complete["status"], "complete")
        self.assertEqual(connection.request.call_count, 1)
        self.assertEqual(self.authority.summary()["operation_count"], 1)
        self.assertEqual((self.directory / "owner/manifest.json").read_bytes(), manifest)
        self.assertTrue((self.directory / "observations/0.json").exists())

    def test_cli_rejects_unknown_arguments_without_echoing_them(self):
        cli = Path(self.module.__file__).parents[1] / "docs/conformance/src02-capacity-run.py"
        canary = "synthetic-private-argument-canary"
        captured = io.StringIO()
        with (
            patch(
                "sys.argv",
                [
                    str(cli),
                    "--handoff",
                    str(self.handoff),
                    "--expected-sha256",
                    self.digest,
                    "--" + canary,
                ],
            ),
            redirect_stdout(captured),
            redirect_stderr(captured),
            self.assertRaises(SystemExit) as stopped,
        ):
            runpy.run_path(str(cli), run_name="__main__")
        self.assertEqual(stopped.exception.code, 2)
        self.assertNotIn(canary, captured.getvalue())
        self.assertIn("Checks or execution stopped", captured.getvalue())
