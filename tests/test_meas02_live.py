"""First-live review derives only a key fingerprint and preserves original authority."""

import copy
import hashlib
import json
import os
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_meas02_native_audit as fixtures
from test_meas02_operator import Terminal
from test_meas02_operator import namespace as operator_namespace

from buddha.authorization import Authorization
from buddha.gateway import Gateway, RawHTTPTransport
from buddha.provider import ModelSpec
from buddha.releases import Release, _json, prepare_selection

HELPER = Path(__file__).resolve().parents[1] / "docs/conformance/meas02-live.py"
namespace = {"__name__": "meas02_live_test", "__file__": str(HELPER)}
exec(compile(HELPER.read_bytes(), str(HELPER), "exec"), namespace)  # nosec B102
main = namespace["main"]
KEY = "offline-first-live-key-not-real"


class LiveHandoffTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture = fixtures.NativeAuditTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root, self.study = fixture.root, fixture.directory
        self.review = self.root / "account-review.json"
        self.handoff = self.root / "handoff.json"
        self.extra = self.root / "approved-source.txt"
        self.extra.write_bytes(b"unchanged approved source")
        self.spec = ModelSpec(
            "openai",
            "gpt-5.6-luna",
            1_050_000,
            128_000,
            500_000,
            1_800_000,
            "https://developers.openai.com/api/docs/pricing",
        )
        fixture.authority = Authorization.create(
            self.root / "live-authorization.sqlite3",
            authorization_id="synthetic-15-dollar-grant",
            budget_microusd=15_000_000,
            max_calls=120,
            scope="synthetic handoff test of approved scope; zero provider calls",
        )
        host = fixture.fixture.roots["host"] / "profiles/openai.json"
        profile_file = json.loads(host.read_bytes())
        profile = profile_file["profiles"]["primary"]
        profile["spec"] = asdict(self.spec)
        profile["response_models"] = [self.spec.model]
        profile["request_tiers"] = ["auto", "default"]
        profile["response_tiers"] = ["", "default"]
        profile["allow_omitted_tier"] = True
        profile["headers"], profile["account_headers"] = {}, {}
        profile_file["format"] = "buddha.gateway-profiles.v2"
        host.write_bytes(_json(profile_file))
        fixture.fixture.release_record["commands"] = [
            {"module": "src.partition", "argv": fixtures.audit.arguments(self.spec.model, seed)}
            for seed in (None, None, 0, 20261020)
        ]
        selected = prepare_selection(
            Release.from_record(fixture.fixture.release_record),
            fixture.fixture.roots,
            capabilities={"openai.chat-completions.v1": "profiles/openai.json"},
        )
        fixture.record["native"].update(
            selection=selected.to_record(),
            profiles={"openai": {self.spec.model: "primary"}},
            budget_microusd=15_000_000,
            max_calls=120,
        )
        fixture.descriptor.write_bytes(_json(fixture.record))
        self.operator = SimpleNamespace(
            _controller=lambda: fixtures.audit,
            _Profiles=operator_namespace["_Profiles"],
            _credentials=operator_namespace["_credentials"],
            _Parser=operator_namespace["_Parser"],
            public_result=operator_namespace["public_result"],
            execute=Mock(return_value={"status": "complete", "target_count": 40}),
        )
        total = fixture.authority.summary()
        self.record = {
            "format": "buddha.meas02-live-handoff.v1",
            "study": str(self.study),
            "descriptor": str(fixture.descriptor),
            "review": str(self.review),
            "account_scope": (
                "User affirms project-scoped key, Standard public PAYG, no account overrides"
            ),
            "authorization": {
                "path": str(fixture.authority.path),
                "id": total["authorization_id"],
                "terms_sha256": total["terms_sha256"],
                "budget_microusd": 15_000_000,
                "max_calls": 120,
                "scope": total["scope"],
            },
            "source_sha256": {},
        }
        self.seal()
        self.out, self.err = Terminal(), Terminal()

    def seal(self):
        sources = [
            HELPER,
            namespace["OPERATOR"],
            self.fixture.descriptor,
            self.extra,
            *fixtures.audit._sources(),
            *(Path(self.fixture.record[name]) for name in ("pack", "proposal", "provenance")),
            *(HELPER.parents[2] / "buddha").glob("*.py"),
        ]
        self.record["source_sha256"] = {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources
        }
        self.handoff.write_bytes(_json(self.record))

    @contextmanager
    def local(self, *, key="", prompt=None):
        with (
            patch.dict(namespace, {"_operator": lambda: self.operator}),
            patch.dict(os.environ, {"OPENAI_API_KEY": key}),
            patch("buddha.__main__.sys.stdin.isatty", return_value=True),
            patch("buddha.__main__.getpass.getpass", side_effect=prompt) as getpass,
            patch("http.client.HTTPSConnection", side_effect=AssertionError("provider forbidden")),
            patch("socket.create_connection", side_effect=AssertionError("network forbidden")),
            patch.object(
                Authorization, "create", side_effect=AssertionError("new grant forbidden")
            ),
            redirect_stdout(self.out),
            redirect_stderr(self.err),
        ):
            yield getpass

    def command(self, *, flags=True):
        args = ["--handoff", str(self.handoff)]
        return main(args + (["--live", "--prompt-keys", "--confirm-project-key"] if flags else []))

    def test_first_launch_one_hidden_entry_actual_review_and_four_original_owners(self):
        def run(study, **options):
            self.assertEqual(study, self.study)
            self.assertEqual(options, {"live": True, "prompt_keys": False})
            self.assertEqual(os.environ["OPENAI_API_KEY"], KEY)
            self.assertEqual(len(self.fixture.authority.summary()["runs"]), 4)
            return {"status": "complete", "target_count": 40}

        self.operator.execute.side_effect = run
        with self.local(prompt=lambda _: KEY) as getpass:
            self.assertEqual(self.command(), 0)
            getpass.assert_called_once()
            self.assertEqual(os.environ["OPENAI_API_KEY"], "")
        review = json.loads(self.review.read_bytes())
        self.assertEqual(
            review["credential_sha256"], {"openai": hashlib.sha256(KEY.encode()).hexdigest()}
        )
        self.assertEqual(review["account_scope"], self.record["account_scope"])
        self.assertIn("received", self.err.getvalue())
        for path in [self.review, *self.study.rglob("*")]:
            if path.is_file():
                self.assertNotIn(KEY.encode(), path.read_bytes())
        self.assertNotIn(KEY, self.out.getvalue() + self.err.getvalue())

    def test_live_and_project_confirmation_flags_are_required_before_key_entry(self):
        for flags in ([], ["--live"], ["--confirm-project-key"]):
            with self.subTest(flags=flags), self.local() as getpass:
                self.assertEqual(main(["--handoff", str(self.handoff), *flags, "--prompt-keys"]), 2)
                getpass.assert_not_called()
                self.operator.execute.assert_not_called()
        self.assertFalse(self.study.exists())
        self.assertFalse(self.review.exists())

    def test_all_approved_source_hashes_and_required_closure_checked_before_keys(self):
        self.extra.write_bytes(b"source drift")
        with self.local() as getpass:
            self.assertEqual(self.command(), 2)
            getpass.assert_not_called()
        self.extra.write_bytes(b"unchanged approved source")
        del self.record["source_sha256"][str(HELPER)]
        self.handoff.write_bytes(_json(self.record))
        with self.local() as getpass:
            self.assertEqual(self.command(), 2)
            getpass.assert_not_called()
        self.assertFalse(self.review.exists())

    def test_authority_identity_terms_scope_and_caps_must_match_without_new_grant(self):
        original = copy.deepcopy(self.record)
        for field, value in (
            ("id", "foreign"),
            ("terms_sha256", "0" * 64),
            ("scope", "foreign"),
            ("budget_microusd", 15_000_001),
            ("max_calls", 121),
        ):
            self.record = copy.deepcopy(original)
            self.record["authorization"][field] = value
            self.handoff.write_bytes(_json(self.record))
            with self.subTest(field=field), self.local() as getpass:
                self.assertEqual(self.command(), 2)
                getpass.assert_not_called()
        self.assertEqual(self.fixture.authority.summary()["operation_count"], 0)

    def test_resealed_wrong_model_profile_or_account_override_stops_before_keys(self):
        host = self.fixture.fixture.roots["host"] / "profiles/openai.json"
        record = json.loads(host.read_bytes())
        record["profiles"]["primary"]["account_headers"] = {"openai-project": "foreign-project"}
        host.write_bytes(_json(record))
        self.fixture.record["native"]["selection"] = prepare_selection(
            Release.from_record(self.fixture.fixture.release_record),
            self.fixture.fixture.roots,
            capabilities={"openai.chat-completions.v1": "profiles/openai.json"},
        ).to_record()
        self.fixture.descriptor.write_bytes(_json(self.fixture.record))
        self.seal()
        with self.local() as getpass:
            self.assertEqual(self.command(), 2)
            getpass.assert_not_called()
        self.assertFalse(self.review.exists())

    def test_review_location_and_partial_preparation_are_rejected_before_keys(self):
        original = self.record["review"]
        self.record["review"] = str(self.fixture.fixture.roots["host"] / "review.json")
        self.handoff.write_bytes(_json(self.record))
        with self.local() as getpass:
            self.assertEqual(self.command(), 2)
            getpass.assert_not_called()
        self.record["review"] = original
        self.handoff.write_bytes(_json(self.record))
        self.study.mkdir()
        with self.local() as getpass:
            self.assertEqual(self.command(), 2)
            getpass.assert_not_called()
        self.assertTrue(self.study.exists())
        self.assertEqual(self.fixture.authority.summary()["runs"], [])

    def test_resume_reuses_unchanged_review_owners_and_requires_same_key(self):
        self.operator.execute.return_value = {
            "status": "incomplete",
            "result": "partial",
            "stop": {"reason": "budget", "codes": ["budget"]},
            "observation": "observations/partial.json",
            "untrusted_error": KEY,
        }
        with self.local(prompt=lambda _: KEY):
            self.assertEqual(self.command(), 3)
        self.assertEqual(
            json.loads(self.out.getvalue().splitlines()[-1]),
            {
                "format": "buddha.meas02-live-launch.v1",
                "status": "incomplete",
                "result": "partial",
                "reason": "budget",
                "reason_codes": ["budget"],
                "observation": "observations/partial.json",
            },
        )
        self.assertNotIn(KEY, self.out.getvalue())
        saved = {
            path: path.read_bytes()
            for path in [self.review, *self.study.glob("owners/*/manifest.json")]
        }
        self.operator.execute.reset_mock()
        with self.local(key="different-key") as getpass:
            self.assertEqual(self.command(), 2)
            getpass.assert_not_called()
            self.operator.execute.assert_not_called()
        with self.local(prompt=lambda _: KEY) as getpass:
            self.assertEqual(self.command(), 3)
            getpass.assert_called_once()
        self.assertEqual(len(self.fixture.authority.summary()["runs"]), 4)
        for path, raw in saved.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_cancelled_key_entry_or_partial_failure_does_not_claim_completion(self):
        with self.local(prompt=KeyboardInterrupt):
            self.assertEqual(self.command(), 130)
        self.assertFalse(self.review.exists())
        self.assertFalse(self.study.exists())
        self.operator.execute.side_effect = RuntimeError("PRIVATE-KEY-ERROR-" + KEY)
        with self.local(prompt=lambda _: KEY):
            self.assertEqual(self.command(), 2)
            self.assertEqual(os.environ["OPENAI_API_KEY"], "")
        self.assertTrue(self.review.exists())
        self.assertEqual(len(self.fixture.authority.summary()["runs"]), 4)
        self.assertNotIn(KEY, self.out.getvalue() + self.err.getvalue())

    def test_invalid_json_and_overlong_key_are_typed_stops_without_review(self):
        original = self.handoff.read_bytes()
        self.handoff.write_bytes(b'{"format":0,"format":1}')
        with self.local() as getpass:
            self.assertEqual(self.command(), 2)
            getpass.assert_not_called()
        self.handoff.write_bytes(original)
        with self.local(prompt=lambda _: "k" * 4097):
            self.assertEqual(self.command(), 2)
        self.assertFalse(self.review.exists())
        self.assertFalse(self.study.exists())

    def test_source_drift_during_key_entry_is_detected_before_review_or_prepare(self):
        def key(_):
            self.extra.write_bytes(b"changed while waiting")
            return KEY

        with self.local(prompt=key):
            self.assertEqual(self.command(), 2)
        self.assertFalse(self.review.exists())
        self.assertFalse(self.study.exists())
        self.operator.execute.assert_not_called()

    def stopped_prepared_study(self, *, unknown):
        with self.local(prompt=lambda _: KEY):
            self.assertEqual(self.command(), 0)
        owner = Gateway(
            self.study / "owners" / ("0" if unknown else "3"),
            transport=RawHTTPTransport(allow_paid=False),
        )
        owner.ledger.reserve("synthetic-stop", "0" * 64, 1 if unknown else 14_999_999)
        if unknown:
            owner.ledger.dispatch("synthetic-stop")
            owner.ledger.mark_unknown("synthetic-stop")
        before = {
            path: path.read_bytes()
            for path in [self.review, *self.study.glob("owners/*/manifest.json")]
        }
        totals = self.fixture.authority.summary()
        self.out.seek(0)
        self.out.truncate()
        self.operator.execute.side_effect = operator_namespace["execute"]
        with (
            self.local() as getpass,
            patch.dict(operator_namespace, {"_controller": lambda: fixtures.audit}),
            patch("buddha.native_run.NativeSession.run", side_effect=AssertionError("worker")),
            patch.object(Gateway, "execute", side_effect=AssertionError("dispatch")),
        ):
            self.assertEqual(self.command(), 3)
            getpass.assert_not_called()
        public = json.loads(self.out.getvalue().splitlines()[-1])
        self.assertEqual(public["result"], "partial")
        self.assertEqual(public["reason"], "unknown" if unknown else "money")
        saved = json.loads((self.study / public["observation"]).read_bytes())
        self.assertEqual(saved["stop"]["reason"], public["reason"])
        self.assertEqual(self.fixture.authority.summary(), totals)
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(
            owner.ledger.get("synthetic-stop").status, "unknown" if unknown else "reserved"
        )
        self.assertNotIn(KEY, self.out.getvalue() + self.err.getvalue())

    def test_prepared_unknown_stops_with_durable_partial_before_keys_or_worker(self):
        self.stopped_prepared_study(unknown=True)

    def test_prepared_exhausted_money_stops_with_durable_partial_before_keys_or_worker(self):
        self.stopped_prepared_study(unknown=False)
