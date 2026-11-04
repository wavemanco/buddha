"""Pre-extraction helper behavior and benchmark-free generic core imports."""

import ast
import hashlib
import importlib
import json
import math
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from typing import cast

from buddha import common
from buddha.common import ValidationError, _canonical, _hex, _integer, _object, _parse, _text

FROZEN_SOURCE = r'''class ValidationError(ValueError):
    """Evidence or configuration violates the experiment contract."""


def _integer(value: object, name: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ValidationError(f"{name} must be an integer >= {minimum}")
    return value


def _hex(value: object, name: str, length: int = 64) -> None:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValidationError(f"{name} must be {length} lowercase hexadecimal characters")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be nonblank text")
    return value


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("configuration or evidence is not finite JSON") from error


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValidationError("expected a JSON object with string keys")
    return cast(dict[str, object], value)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("duplicate JSON object key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValidationError("nonfinite JSON number")


def _parse(raw: bytes) -> object:
    try:
        return cast(
            object,
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_pairs,
                parse_constant=_invalid_constant,
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError("invalid UTF-8 JSON") from error
'''

FROZEN_SHA256 = "3ded6351dc82fb3ef05e9f0d569f4ffd9bfe5fffe497ee81b5faa918efa31ae0"


class Text(str):
    pass


class Integer(int):
    pass


class Object(dict):
    pass


def outcome(function, *arguments):
    try:
        return "value", function(*arguments)
    except Exception as error:
        return (
            "error",
            type(error).__name__,
            str(error),
            type(error.__cause__).__name__ if error.__cause__ is not None else None,
        )


class CommonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Nine generic definitions captured from evaluation.py and benchmark.py at
        # 7d1ebd2325788f928b6f8da7b5347eabca2d42a8. No scientific module executes,
        # and shallow CI checkouts never need the old Git object at test runtime.
        if hashlib.sha256(FROZEN_SOURCE.encode()).hexdigest() != FROZEN_SHA256:
            raise AssertionError("frozen generic-helper oracle changed")
        tree = ast.parse(FROZEN_SOURCE)
        if len(tree.body) != 9 or any(
            not isinstance(node, (ast.ClassDef, ast.FunctionDef)) for node in tree.body
        ):
            raise AssertionError("oracle must contain only the selected generic definitions")
        cls.reference = {"json": json, "re": re, "cast": cast}
        exec(compile(tree, "<pre-extraction-generic-helpers>", "exec"), cls.reference)

    def compare(self, name, *arguments):
        self.assertEqual(
            outcome(getattr(common, name), *arguments),
            outcome(self.reference[name], *arguments),
        )

    def test_canonical_ascii_bytes_unicode_numeric_forms_and_key_order_are_frozen(self):
        value = {"z": [1.0, -0.0, True, None], "雪": "café 🌱\n", "a": {"b": 2}}
        expected = (
            b'{"a":{"b":2},"z":[1.0,-0.0,true,null],"\\u96ea":"caf\\u00e9 \\ud83c\\udf31\\n"}'
        )
        self.assertEqual(_canonical(value), expected)
        for item in [value, ["\ud800"], {1: "numeric JSON key"}, (), 2**1000, Text("literal")]:
            with self.subTest(kind=type(item).__name__):
                self.compare("_canonical", item)
        self.assertEqual(_canonical("\ud800"), b'"\\ud800"')

    def test_canonical_invalid_values_preserve_exception_message_and_cause(self):
        recursive = []
        recursive.append(recursive)
        for item in [
            float("nan"),
            float("inf"),
            -float("inf"),
            {"a": object()},
            {1: 1, "a": 2},
            {1},
            recursive,
        ]:
            with self.subTest(kind=type(item).__name__):
                self.compare("_canonical", item)
        failure = outcome(_canonical, float("nan"))
        self.assertEqual(
            failure,
            (
                "error",
                "ValidationError",
                "configuration or evidence is not finite JSON",
                "ValueError",
            ),
        )

    def test_parse_valid_json_utf8_scalar_and_historical_float_overflow(self):
        for raw in [
            b' {"z":[1,-0.0,true,null],"a":"\\u96ea"}\n',
            '"café 🌱"'.encode(),
            b'"\\ud800"',
            b"null",
            b"true",
            b"12",
            b"1e999",
            b"-1e999",
            bytearray(b"[1,2]"),
        ]:
            with self.subTest(raw=repr(raw)):
                self.compare("_parse", raw)
        # Extraction preserves this old distinction; finite-number validation is separate.
        self.assertTrue(math.isinf(_parse(b"1e999")))
        self.assertEqual(_parse(b'"\\ud800"'), "\ud800")

    def test_parse_duplicate_nonfinite_utf8_and_json_errors_preserve_exact_behavior(self):
        cases = [
            b'{"a":1,"a":2}',
            b'{"nested":{"a":1,"a":2}}',
            b"NaN",
            b"Infinity",
            b"-Infinity",
            b'{"x":NaN}',
            b"\xff",
            b"",
            b"{bad}",
            b"{} {}",
            b"\xef\xbb\xbf{}",
            "{}",
            None,
        ]
        for raw in cases:
            with self.subTest(raw=repr(raw)):
                self.compare("_parse", raw)
        self.assertEqual(
            outcome(_parse, b'{"a":1,"a":2}'),
            ("error", "ValidationError", "duplicate JSON object key", None),
        )
        self.assertEqual(
            outcome(_parse, b"NaN"), ("error", "ValidationError", "nonfinite JSON number", None)
        )
        self.assertEqual(
            outcome(_parse, b"\xff"),
            ("error", "ValidationError", "invalid UTF-8 JSON", "UnicodeDecodeError"),
        )

    def test_integer_exact_type_lower_bounds_and_unbounded_upper_range_are_preserved(self):
        for minimum in (-5, 0, 1):
            for value in [minimum, minimum - 1, 2**1000, True, False, Integer(3), 1.0, None, "3"]:
                with self.subTest(minimum=minimum, kind=type(value).__name__):
                    self.compare("_integer", value, "sample count", minimum)
        self.assertEqual(_integer(2**1000, "large", 0), 2**1000)
        self.assertEqual(
            outcome(_integer, True, "count", 0),
            ("error", "ValidationError", "count must be an integer >= 0", None),
        )

    def test_hex_default_custom_length_case_and_string_subclasses_are_preserved(self):
        for value, length in [
            ("a" * 64, 64),
            ("0123456789abcdef" * 4, 64),
            ("a" * 40, 40),
            (Text("a" * 64), 64),
            ("", 0),
            ("a" * 63, 64),
            ("A" * 64, 64),
            ("g" * 64, 64),
            (None, 64),
            (True, 64),
        ]:
            with self.subTest(value=value, length=length):
                self.compare("_hex", value, "digest", length)
        self.assertIsNone(_hex("a" * 64, "digest"))

    def test_text_preserves_literal_data_and_existing_permissive_limits(self):
        for value in [
            " literal \n",
            Text("subclass"),
            "\x00",
            "\ud800",
            "x" * 10000,
            "",
            " \t\n",
            "\u00a0",
            None,
            1,
            b"bytes",
        ]:
            with self.subTest(kind=type(value).__name__):
                self.compare("_text", value, "label")
        literal = Text(" literal \n")
        self.assertIs(_text(literal, "label"), literal)
        self.assertEqual(
            outcome(_text, " ", "label"),
            ("error", "ValidationError", "label must be nonblank text", None),
        )

    def test_object_keeps_identity_and_original_subclass_behavior(self):
        for value in [{}, {"x": [None]}, Object({Text("key"): 1}), {1: "bad"}, [], None]:
            with self.subTest(kind=type(value).__name__):
                self.compare("_object", value)
        value = Object({Text("key"): 1})
        self.assertIs(_object(value), value)
        self.assertEqual(
            outcome(_object, {1: "bad"}),
            ("error", "ValidationError", "expected a JSON object with string keys", None),
        )

    def test_legacy_exports_and_financial_exceptions_are_actual_common_aliases(self):
        evaluation = importlib.import_module("buddha.evaluation")
        benchmark = importlib.import_module("buddha.benchmark")
        for name in ["ValidationError", "_integer", "_hex", "_text"]:
            self.assertIs(getattr(evaluation, name), getattr(common, name))
        for name in [
            "ValidationError",
            "_canonical",
            "_object",
            "_parse",
            "_unique_pairs",
            "_invalid_constant",
        ]:
            self.assertIs(getattr(benchmark, name), getattr(common, name))
        for name in ["authorization", "history", "ledger", "provider", "gateway"]:
            module = importlib.import_module("buddha." + name)
            self.assertIs(module.ValidationError, ValidationError)
        self.assertTrue(issubclass(ValidationError, ValueError))

    def test_fresh_generic_core_prepares_real_authority_without_scientific_imports(self):
        project = Path(__file__).resolve().parent.parent
        script = textwrap.dedent("""
            import hashlib, http.client, importlib.abc, json, sys, tempfile
            from dataclasses import asdict
            from datetime import UTC, datetime
            from pathlib import Path
            sys.path.insert(0, PROJECT)
            banned = {'buddha.benchmark', 'buddha.evaluation'}
            attempts = []
            class BlockScience(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname in banned:
                        attempts.append(fullname)
                        raise ImportError('scientific import blocked')
            sys.meta_path.insert(0, BlockScience())
            def no_http(*args, **kwargs):
                raise AssertionError('offline preparation attempted HTTPS')
            http.client.HTTPSConnection = no_http
            from buddha.authorization import Authorization
            from buddha.gateway import (
                CORE, Gateway, RawHTTPTransport, execution_identity, prepare_gateway,
            )
            from buddha.provider import ModelSpec
            from buddha.releases import Release, inventory, prepare_selection
            capability = 'openai.chat-completions.v1'
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                roles = ('official','environment','runner','host','agent')
                roots = {name: root/name for name in roles}
                for name, path in roots.items():
                    path.mkdir()
                    (path/'identity.txt').write_text(name)
                (roots['official']/'uv.lock').write_text('sealed fixture lock')
                (roots['official']/'tasks.jsonl').write_bytes(b'{"id":"a","prompt":"literal"}\\n')
                (roots['official']/'evaluate.py').write_text('def main(): pass\\n')
                spec = ModelSpec('openai','synthetic-model',100,100,1000000,2000000,'https://example.org/bounds')
                profile = {
                    'format':'buddha.gateway-profiles.v1',
                    'profiles':{'primary':{'spec':asdict(spec),'response_models':['synthetic-model'],
                        'request_tiers':['auto','default'],'response_tiers':['','default'],
                        'allow_omitted_tier':True}},
                }
                (roots['host']/'profile.json').write_text(json.dumps(profile))
                release = Release.from_record({
                    'format':'buddha.benchmark-release.v1','benchmark':'fixture','release':'portable',
                    'upstream':{'url':'https://example.org/official','revision':'a'*40},
                    'source':inventory(roots['official']),'dependency_lock':'uv.lock',
                    'task':{'dataset':'tasks.jsonl','id_field':'id','prompt_field':'prompt',
                        'answers_field':'responses','count':2},
                    'commands':[{'module':'evaluate','argv':['{artifacts}']}],
                    'artifacts':{'answers':'answers.jsonl','results':['results.jsonl'],'summary':'summary.json'},
                    'requires':[capability],
                })
                selected = prepare_selection(
                    release, roots, capabilities={capability:'profile.json'})
                authority = Authorization.create(
                    root/'authority.sqlite3',authorization_id='generic-fixture',
                    budget_microusd=1000,max_calls=4,scope='offline generic import acceptance')
                input_file = root/'input.jsonl'
                input_file.write_bytes(b'{"literal":"not sent"}\\n')
                credential_digest = hashlib.sha256(b'offline synthetic fingerprint').hexdigest()
                directory = prepare_gateway(
                    root/'run',selection=selected,roots=roots,authorization=authority,
                    budget_microusd=1000,max_calls=4,input_files=[input_file],review={
                        'checked_on':datetime.now(UTC).date().isoformat(),
                        'credential_sha256':{'openai':credential_digest},
                        'account_scope':'offline generic fixture review'},run_id='generic-run')
                gateway = Gateway(directory,transport=RawHTTPTransport(allow_paid=False))
                manifest = json.loads((directory/'manifest.json').read_bytes())
                identity = execution_identity(directory)
                print(json.dumps({'core':sorted(CORE),'actual_core':sorted(manifest['core']),
                    'loaded_banned':sorted(banned.intersection(sys.modules)),'blocked_attempts':attempts,
                    'operation_count':gateway.ledger.totals()['operation_count'],
                    'bound_runs':len(authority.summary()['runs']),'identity':identity}))
        """)
        script = "PROJECT=" + repr(str(project)) + "\n" + script
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        expected = {
            "buddha",
            *(
                "buddha." + name
                for name in [
                    "gateway",
                    "wire",
                    "releases",
                    "authorization",
                    "ledger",
                    "history",
                    "provider",
                    "common",
                    "trial_fence",
                ]
            ),
        }
        self.assertEqual(set(report["core"]), expected)
        self.assertEqual(set(report["actual_core"]), expected)
        self.assertEqual(report["loaded_banned"], [])
        self.assertEqual(report["blocked_attempts"], [])
        self.assertEqual((report["operation_count"], report["bound_runs"]), (0, 1))
        self.assertRegex(report["identity"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
