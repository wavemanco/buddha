"""Reviewed helper extraction preserves the sealed pilot's scientific boundary."""

import ast
import hashlib
import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

import test_continuation_source as fixtures

from buddha import benchmark, common, continuation, evaluation, provider
from buddha.common import ValidationError

NB01_REVISION = (
    "9e131a9f4fd92197b256518ea778984875d9aee2a58efb3ccc759d6553a79ae2",
    "15b57b974c702d69c7b9e172c73798bd555db5eedb3286bd8c792d1fe0568763",
)
EXTRACTION_REVISIONS = {
    "buddha.benchmark": (
        "15b57b974c702d69c7b9e172c73798bd555db5eedb3286bd8c792d1fe0568763",
        "b72c74a0b9b7e786b9969c72a400f449ab5758938ee9f24af660a887d866c2a9",
    ),
    "buddha.evaluation": (
        "87e23a9afbdbc466da7ed44cc1bb2b2fd8622d480efd9db95155d75ddda77e78",
        "4cabb1a48689a140fc6f6129ed8d9eae1d047d3e09eae794170c74479413b8d6",
    ),
}
COMMON_SHA256 = "3a0a693a0f4a0f2eed3b858d0b3ac42148871dbca284e56e0e368726309393c0"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ContinuationCommonTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ContinuationSourceTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def denied_source(self, module, raw):
        # These are source-data mutations, never imported or executed.
        before = self.fixture.files()
        altered = self.fixture.root / (module.__name__.rsplit(".", 1)[-1] + "-changed.py")
        altered.write_bytes(raw)
        with patch.object(module, "__file__", str(altered)), self.assertRaises(ValidationError):
            self.fixture.read()
        self.assertEqual(before, self.fixture.files())

    def test_reviewed_common_extraction_reads_nine_receipts_and_preserves_unknown_hold(self):
        before = self.fixture.files()
        source = self.fixture.read()
        self.assertEqual([item.reply for item in source.completed], self.fixture.receipts)
        self.assertEqual(source.unknown.status, "unknown")
        self.assertEqual(source.history.totals()["spent_microusd"], 135)
        self.assertEqual(source.history.totals()["reserved_microusd"], 104096)
        self.assertEqual(before, self.fixture.files())

    def test_identical_current_snapshot_does_not_need_extraction_mapping(self):
        # A source-data fixture, not a new historical claim or archived execution.
        from buddha import search

        contracts = search._contracts()
        names = [*contracts["source_sha256"], "buddha.search"]
        snapshot = {
            name.replace(".", "/") + ".py": Path(
                importlib.import_module(name).__file__
            ).read_bytes()
            for name in names
        }
        snapshot["buddha/common.py"] = Path(common.__file__).read_bytes()
        before = self.fixture.files()
        continuation._science(snapshot, contracts)
        for archived_common in (None, b"# changed archived common source\n"):
            changed = dict(snapshot)
            if archived_common is None:
                del changed["buddha/common.py"]
            else:
                changed["buddha/common.py"] = archived_common
            with self.subTest(archived_common=archived_common), self.assertRaises(ValidationError):
                continuation._science(changed, contracts)
        for module in (benchmark, evaluation):
            changed = self.fixture.root / (module.__name__ + "-unequal.py")
            changed.write_bytes(Path(module.__file__).read_bytes() + b"\n# unequal source\n")
            with (
                self.subTest(module=module.__name__),
                patch.object(module, "__file__", str(changed)),
                self.assertRaises(ValidationError),
            ):
                continuation._science(snapshot, contracts)
        self.assertEqual(before, self.fixture.files())

    def test_archived_provider_common_dependency_is_sealed_even_with_original_wrappers(self):
        snapshot = continuation._snapshot(fixtures.ARCHIVE, fixtures.ARCHIVE_SHA)
        contracts = fixtures.old_contracts()
        snapshot["buddha/provider.py"] = Path(provider.__file__).read_bytes()
        contracts["source_sha256"]["buddha.provider"] = sha(snapshot["buddha/provider.py"])
        snapshot["buddha/common.py"] = Path(common.__file__).read_bytes()
        before = self.fixture.files()
        # All other archived files, including old benchmark/evaluation, are unchanged.
        continuation._science(snapshot, contracts)
        for archived_common in (None, b"# changed archived common source\n"):
            changed = dict(snapshot)
            if archived_common is None:
                del changed["buddha/common.py"]
            else:
                changed["buddha/common.py"] = archived_common
            with self.subTest(archived_common=archived_common), self.assertRaises(ValidationError):
                continuation._science(changed, contracts)
        self.assertEqual(before, self.fixture.files())

    def test_nonhelper_scientific_ast_matches_sealed_preextraction_modules(self):
        # Captured from exact 7d1ebd2325788f928b6f8da7b5347eabca2d42a8 blobs.
        # Only moved definitions, their exact common aliases and the now-unused
        # single json/re import are removed. Every other AST node is retained.
        for module, helpers, unused, expected in [
            (
                benchmark,
                {"_canonical", "_object", "_unique_pairs", "_invalid_constant", "_parse"},
                "json",
                "7eb7555e4d1a16426fd726b196c0cfac690dab9ad28dfde88bb1657cba416a29",
            ),
            (
                evaluation,
                {"ValidationError", "_integer", "_hex", "_text"},
                "re",
                "b9f03454b734dd633061270fe4698f8d54e97205bd0b28a908acf76c182a3c13",
            ),
        ]:
            with self.subTest(module=module.__name__):
                tree = ast.parse(Path(module.__file__).read_bytes())
                nodes = []
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in helpers:
                        continue
                    if isinstance(node, ast.Import) and [
                        (name.name, name.asname) for name in node.names
                    ] == [(unused, None)]:
                        continue
                    if (
                        isinstance(node, ast.ImportFrom)
                        and node.level == 0
                        and node.module == "buddha.common"
                        and len(node.names) == 1
                        and node.names[0].name in helpers
                        and node.names[0].asname == node.names[0].name
                    ):
                        continue
                    nodes.append(node)
                tree.body = nodes
                self.assertEqual(sha(ast.dump(tree, include_attributes=False).encode()), expected)

    def test_only_the_reviewed_extraction_hashes_and_original_nb01_pair_are_declared(self):
        # Captured before implementation: no Git ancestor lookup at test runtime.
        self.assertEqual(continuation._BENCHMARK_VALIDATION_REVISION, NB01_REVISION)
        self.assertEqual(continuation._GENERIC_EXTRACTION_MODULES, EXTRACTION_REVISIONS)
        self.assertEqual(continuation._GENERIC_COMMON_SHA256, COMMON_SHA256)
        self.assertEqual(sha(Path(common.__file__).read_bytes()), COMMON_SHA256)
        for module in (benchmark, evaluation):
            self.assertEqual(
                sha(Path(module.__file__).read_bytes()), EXTRACTION_REVISIONS[module.__name__][1]
            )
        self.assertEqual(len(self.fixture.read().completed), 9)

    def test_changed_common_definition_rebinding_or_unreviewed_source_is_rejected(self):
        self.fixture.read()
        raw = Path(common.__file__).read_bytes()
        for label, changed in [
            ("integer", raw.replace(b"value < minimum", b"value <= minimum")),
            ("canonical", raw.replace(b"ensure_ascii=True", b"ensure_ascii=False")),
            ("parser", raw.replace(b"object_pairs_hook=_unique_pairs", b"object_pairs_hook=dict")),
            (
                "error",
                raw.replace(b"ValidationError(ValueError)", b"ValidationError(RuntimeError)"),
            ),
            ("binding", raw + b"\n_canonical = lambda value: b'changed'\n"),
            ("comment", raw + b"\n# unreviewed common revision\n"),
        ]:
            self.assertNotEqual(raw, changed)
            with self.subTest(label=label):
                self.denied_source(common, changed)

    def test_missing_or_unavailable_common_source_fails_without_mutating_history(self):
        self.fixture.read()
        before = self.fixture.files()
        for source in (None, str(self.fixture.root / "missing-common.py")):
            with (
                self.subTest(source=source),
                patch.object(common, "__file__", source),
                self.assertRaises(ValidationError),
            ):
                self.fixture.read()
        self.assertEqual(before, self.fixture.files())

    def test_extracted_benchmark_and_evaluation_aliases_and_rebindings_stay_protected(self):
        self.fixture.read()
        for module, old, new, rebound in [
            (
                benchmark,
                b"_canonical as _canonical",
                b"_parse as _canonical",
                b"\n_canonical = lambda value: b'changed'\n",
            ),
            (
                evaluation,
                b"_integer as _integer",
                b"_text as _integer",
                b"\n_integer = lambda value, name, minimum: 0\n",
            ),
        ]:
            raw = Path(module.__file__).read_bytes()
            self.assertIn(old, raw)
            for changed in (raw.replace(old, new), raw + rebound, raw + b"\n# unreviewed\n"):
                with self.subTest(module=module.__name__, digest=sha(changed)):
                    self.denied_source(module, changed)

    def test_provider_import_exception_does_not_accept_aliases_or_extra_common_bindings(self):
        self.fixture.read()
        raw = Path(provider.__file__).read_bytes()
        original = b"from buddha.common import ValidationError"
        self.assertEqual(raw.count(original), 1)
        for replacement in [
            b"from buddha.common import ValidationError as ValidationError",
            b"from buddha.common import ValidationError, _text",
            b"from buddha.common import *",
            b"import buddha.common as common\nValidationError = common.ValidationError",
        ]:
            with self.subTest(replacement=replacement):
                self.denied_source(provider, raw.replace(original, replacement))

    def test_provider_module_and_class_rebinding_still_fail_closed(self):
        self.fixture.read()
        raw = Path(provider.__file__).read_bytes()
        marker = b"\n\nclass BudgetBroker:"
        self.assertIn(marker, raw)
        for changed in [
            raw + b"\nValidationError = RuntimeError\n",
            raw + b"\nHTTPTransport._reply = staticmethod(lambda *args: None)\n",
            raw.replace(marker, b"\n    _reply = staticmethod(lambda *args: None)\n" + marker),
        ]:
            with self.subTest(digest=sha(changed)):
                self.denied_source(provider, changed)


if __name__ == "__main__":
    unittest.main()
