"""Buffered artifacts retain the existing v1.1 evidence validation and arithmetic."""

import ast
import copy
import hashlib
import io
import json
import struct
import tempfile
import unittest
import warnings
import zipfile
import zlib
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

import test_benchmark as fixtures
import test_continuation_source as source_fixtures

from buddha import benchmark, continuation
from buddha.common import ValidationError

NAMES = (
    "generations.jsonl",
    "v1.1/partitions.jsonl",
    "v1.1/scores.jsonl",
    "v1.1/summary.json",
    "provenance.json",
)
DEFAULT_BLOBS = object()


def reseal(blobs):
    record = json.loads(blobs["provenance.json"])
    record["artifact_hashes"] = {name: fixtures.digest(blobs[name]) for name in NAMES[:-1]}
    record.pop("provenance_sha256", None)
    record["provenance_sha256"] = fixtures.digest(fixtures.canonical(record))
    blobs["provenance.json"] = fixtures.canonical(record) + b"\n"
    return blobs


def reassemble_importer(tree):
    """Reverse only this reviewed extraction, preserving every scientific AST node."""
    tree = copy.deepcopy(tree)
    path = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "import_evaluation"
    )
    pure = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "import_evaluation_bytes"
    )
    # Four new pure-boundary statements precede the original provenance body.
    assert ast.unparse(pure.body[0]) == "_check_protocol(protocol)"
    assert ast.unparse(pure.body[2]) == "blobs = dict(blobs)"
    assert ast.unparse(pure.body[4]) == (
        "provenance = _object(_parse(blobs.pop('provenance.json')))"
    )
    expected_tail = ast.parse(
        "blobs = {name: (source / name).read_bytes() for name in expected_files}\n"
        "return import_evaluation_bytes(blobs, protocol=protocol, "
        "expected_prompt_hashes=expected_prompt_hashes)"
    ).body
    assert ast.dump(ast.Module(body=path.body[-2:], type_ignores=[]), include_attributes=False) == (
        ast.dump(ast.Module(body=expected_tail, type_ignores=[]), include_attributes=False)
    )
    original_tail = pure.body[4:]
    original_tail[0] = ast.parse(
        "provenance = _object(_parse((source / 'provenance.json').read_bytes()))"
    ).body[0]
    original_tail.insert(
        7, ast.parse("blobs = {name: (source / name).read_bytes() for name in _ARTIFACTS}").body[0]
    )
    path.body = path.body[:-2] + original_tail
    tree.body.remove(pure)
    return tree


class EvaluationBytesTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ArtifactTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.export()
        self.blobs = {name: (self.fixture.destination / name).read_bytes() for name in NAMES}

    def read(self, blobs=DEFAULT_BLOBS, **changes):
        arguments = {
            "protocol": self.fixture.protocol,
            "expected_prompt_hashes": self.fixture.manifest,
        }
        arguments.update(changes)
        return benchmark.import_evaluation_bytes(
            self.blobs if blobs is DEFAULT_BLOBS else blobs, **arguments
        )

    def test_pure_buffered_import_api_exists(self):
        self.assertTrue(callable(getattr(benchmark, "import_evaluation_bytes", None)))

    def test_buffered_path_parity_exact_arithmetic_and_no_io(self):
        expected = self.fixture.read()
        with (
            patch("builtins.open", side_effect=AssertionError("pure importer opened a file")),
            patch.object(Path, "open", side_effect=AssertionError("pure importer opened a path")),
            patch("socket.socket", side_effect=AssertionError("pure importer used network")),
        ):
            actual = self.read(MappingProxyType(self.blobs))
        self.assertEqual(actual, expected)
        self.assertAlmostEqual(actual[0].mean_utility, 330 / 61)
        self.assertEqual(actual[0].mean_distinct, 2)
        self.assertEqual(actual[1][0]["partition_scores"], [10, 5])

    def test_exact_five_artifact_names_and_bytes_only(self):
        for invalid in (None, [], "artifacts", 1):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.read(invalid)
        for name in NAMES:
            missing = dict(self.blobs)
            del missing[name]
            with self.subTest(missing=name), self.assertRaises(ValidationError):
                self.read(missing)
        for extra in ("extra", "../provenance.json", "/provenance.json", "v1.0/summary.json"):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                self.read(self.blobs | {extra: b"{}"})
        for value in ("{}", bytearray(b"{}"), memoryview(b"{}"), None, 1):
            with self.subTest(value=type(value).__name__), self.assertRaises(ValidationError):
                self.read(self.blobs | {"provenance.json": value})

    def test_input_bytes_and_returned_rows_are_independent(self):
        before = dict(self.blobs)
        _, rows = self.read()
        rows[0]["generations"][0] = "mutated output"
        rows[0]["generation_config"]["model"] = "mutated configuration"
        self.assertEqual(self.blobs, before)
        self.assertEqual(self.read(), self.fixture.read())

    def test_path_importer_buffers_each_artifact_exactly_once_then_delegates(self):
        original = Path.read_bytes
        reads = []

        def consume(path):
            reads.append(path.relative_to(self.fixture.destination).as_posix())
            return original(path)

        with (
            patch.object(Path, "read_bytes", consume),
            patch.object(
                benchmark, "import_evaluation_bytes", wraps=benchmark.import_evaluation_bytes
            ) as delegate,
        ):
            self.assertEqual(self.fixture.read(), self.read())
        self.assertCountEqual(reads, NAMES)
        self.assertEqual(len(reads), len(NAMES))
        self.assertEqual(delegate.call_args_list[0].args[0], self.blobs)

    def test_resealed_cross_stage_identity_and_configuration_changes_fail(self):
        for name in NAMES[:3]:
            for changes in (
                {"id": "other"},
                {"generations": ["changed", "First again", "Second"]},
                {"model": "other"},
                {"protocol_fingerprint": "a" * 64},
                {"generation_config": fixtures.GENERATION_CONFIG | {"sampling": "in-context"}},
                {"fallback_judge": "other"},
                {"fallback_calls": [0]},
                {"unscored": "refused"},
            ):
                blobs = dict(self.blobs)
                blobs[name] = fixtures.canonical(json.loads(blobs[name]) | changes) + b"\n"
                with self.subTest(name=name, changes=changes), self.assertRaises(ValidationError):
                    self.read(reseal(blobs))
        for name in NAMES[1:3]:
            blobs = dict(self.blobs)
            row = json.loads(blobs[name])
            row["partition_config"]["seed"] = 7.0
            blobs[name] = fixtures.canonical(row) + b"\n"
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.read(reseal(blobs))

    def test_resealed_scoring_and_summary_forgery_still_fail(self):
        for changes in (
            {"utility": 10},
            {"generation_scores": [10, 9, 5]},
            {"partition_scores": [10, 9]},
            {"distinct": 3},
            {"partition": [0, 1, 1]},
        ):
            blobs = dict(self.blobs)
            blobs[NAMES[2]] = fixtures.canonical(json.loads(blobs[NAMES[2]]) | changes) + b"\n"
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.read(reseal(blobs))
        blobs = dict(self.blobs)
        blobs[NAMES[3]] = fixtures.canonical(json.loads(blobs[NAMES[3]]) | {"mean_utility": 10})
        with self.assertRaises(ValidationError):
            self.read(reseal(blobs))

    def test_prompt_coverage_protocol_origin_and_checksums_still_fail(self):
        for expected in (
            {"one": fixtures.digest("wrong")},
            self.fixture.manifest | {"missing": fixtures.digest("missing")},
        ):
            with self.subTest(expected=expected), self.assertRaises(ValidationError):
                self.read(expected_prompt_hashes=expected)
        with self.assertRaises(ValidationError):
            self.read(protocol=replace(self.fixture.protocol, metric_version="1.0"))
        for changes in ({"origin": "official"}, {"protocol_fingerprint": "f" * 64}):
            blobs = dict(self.blobs)
            blobs[NAMES[4]] = fixtures.canonical(json.loads(blobs[NAMES[4]]) | changes)
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.read(reseal(blobs))
        with self.assertRaises(ValidationError):
            self.read(self.blobs | {NAMES[0]: self.blobs[NAMES[0]] + b"\n"})
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b"\xff"):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                self.read(self.blobs | {NAMES[4]: raw})

    def test_original_scientific_importer_and_remainder_ast_are_preserved(self):
        # Independently captured from exact base21660311596edeec3ef729168782c2967416f09b.
        tree = reassemble_importer(ast.parse(Path(benchmark.__file__).read_bytes()))
        original = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "import_evaluation"
        )
        self.assertEqual(
            hashlib.sha256(ast.dump(original, include_attributes=False).encode()).hexdigest(),
            "cf1eab6e1075a241651b9a6d88a7e3bda4f0fcff3b8b7404e04c6a2e9ea354c9",
        )
        tree.body.remove(original)
        self.assertEqual(
            hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest(),
            "d636cd6fbb0df214cbcb877e20edac80b1abf35d9cee6ea2a9924c994edd019b",
        )


class SnapshotBytesTests(unittest.TestCase):
    def archive(self, payload, *, expected=None, compression=zipfile.ZIP_DEFLATED):
        expected = payload if expected is None else expected
        index = {
            "format": "buddha.runtime-source-snapshot.v1",
            "files_sha256": {"buddha/test.py": fixtures.digest(expected)},
        }
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=compression) as bundle:
            bundle.writestr("source-index.json", fixtures.canonical(index))
            bundle.writestr("buddha/test.py", payload)
        return stream.getvalue()

    def test_pure_snapshot_api_exists(self):
        self.assertTrue(callable(getattr(continuation, "_snapshot_bytes", None)))

    def test_buffered_source_archive_matches_path_without_io_or_execution(self):
        raw = source_fixtures.ARCHIVE.read_bytes()
        expected = continuation._snapshot(source_fixtures.ARCHIVE, source_fixtures.ARCHIVE_SHA)
        with (
            patch("builtins.open", side_effect=AssertionError("archive bytes opened a file")),
            patch.object(Path, "open", side_effect=AssertionError("archive bytes opened a path")),
            patch("builtins.exec", side_effect=AssertionError("archived source executed")),
            patch("builtins.compile", side_effect=AssertionError("archived source compiled")),
        ):
            self.assertEqual(
                continuation._snapshot_bytes(raw, source_fixtures.ARCHIVE_SHA), expected
            )

    def test_snapshot_outer_type_hash_and_actual_size_are_checked(self):
        raw = source_fixtures.ARCHIVE.read_bytes()
        for invalid in (bytearray(raw), memoryview(raw), "zip", None):
            with self.subTest(type=type(invalid).__name__), self.assertRaises(ValidationError):
                continuation._snapshot_bytes(invalid, source_fixtures.ARCHIVE_SHA)
        with self.assertRaises(ValidationError):
            continuation._snapshot_bytes(raw, "0" * 64)
        with patch.object(continuation, "_MAX_ARCHIVE", 4), self.assertRaises(ValidationError):
            continuation._snapshot_bytes(raw, source_fixtures.ARCHIVE_SHA)

    def test_archive_index_paths_duplicates_and_member_hash_are_still_validated(self):
        for name, changes in (
            ("module.py", {"missing_index": True}),
            ("module.py", {"bad_hash": True}),
            ("module.py", {"duplicate": True}),
            ("module.py", {"bad_format": True}),
            ("../module.py", {}),
        ):
            output = io.BytesIO()
            source = b"raise RuntimeError('must not execute')\n"
            with warnings.catch_warnings(), zipfile.ZipFile(output, "w") as archive:
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr(name, source)
                if changes.get("duplicate"):
                    archive.writestr(name, source)
                index = {
                    "format": "other"
                    if changes.get("bad_format")
                    else "buddha.runtime-source-snapshot.v1",
                    "files_sha256": {
                        name: "0" * 64 if changes.get("bad_hash") else fixtures.digest(source)
                    },
                }
                if not changes.get("missing_index"):
                    archive.writestr("source-index.json", fixtures.canonical(index))
            raw = output.getvalue()
            with self.subTest(name=name, changes=changes), self.assertRaises(ValidationError):
                continuation._snapshot_bytes(raw, fixtures.digest(raw))

    def test_path_snapshot_bounds_consumed_reads_and_rejects_postread_drift(self):
        raw = source_fixtures.ARCHIVE.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.zip"
            path.write_bytes(raw)
            original_stat, original_open = Path.stat, Path.open
            sizes = []

            def lie_size(selected, *args, **kwargs):
                information = original_stat(selected, *args, **kwargs)
                fields = {
                    name: getattr(information, name)
                    for name in dir(information)
                    if name.startswith("st_")
                }
                return SimpleNamespace(**(fields | {"st_size": 0}))

            class ObservedStream:
                def __enter__(self):
                    self.stream = original_open(path, "rb")
                    return self

                def read(self, maximum):
                    sizes.append(maximum)
                    return self.stream.read(maximum)

                def __exit__(self, *args):
                    self.stream.close()

            with (
                patch.object(continuation, "_MAX_ARCHIVE", 4),
                patch.object(Path, "stat", lie_size),
                patch.object(Path, "open", return_value=ObservedStream()),
                self.assertRaises(ValidationError),
            ):
                continuation._snapshot(path, source_fixtures.ARCHIVE_SHA)
            self.assertEqual(sizes, [5])
            original = continuation._snapshot_bytes

            def drift(data, expected):
                result = original(data, expected)
                path.write_bytes(data + b"changed after consumed snapshot")
                return result

            with (
                patch.object(continuation, "_snapshot_bytes", drift),
                self.assertRaises(ValidationError),
            ):
                continuation._snapshot(path, source_fixtures.ARCHIVE_SHA)

    def test_source_zip_validation_ast_matches_sealed_preextraction_body(self):
        # Base2166031 ZIP/index validator: only sealed ZipFile input and the two
        # explicitly bounded member reads are reversed for this comparison.
        tree = ast.parse(Path(continuation.__file__).read_bytes())
        pure = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_snapshot_bytes"
        )
        body = next(n for n in ast.walk(pure) if isinstance(n, ast.With))
        calls = [
            n
            for n in ast.walk(body)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_snapshot_member"
        ]
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(
                ast.dump(call.args[0]), ast.dump(ast.Name(id="bundle", ctx=ast.Load()))
            )
            self.assertEqual(len(call.args), 2)
            self.assertEqual(call.keywords, [])
            call.func = ast.Attribute(value=call.args.pop(0), attr="read", ctx=ast.Load())
        self.assertEqual(
            hashlib.sha256(ast.dump(body, include_attributes=False).encode()).hexdigest(),
            "60c13843d548f987935eab656c49cf421738b2d21f7e50100b1dd71e52939271",
        )

    def test_underdeclared_deflate_expansion_has_an_actual_output_bound(self):
        raw = bytearray(self.archive(b"A" * 32768, expected=b"A"))
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            local = bundle.getinfo("buddha/test.py").header_offset
        first_central = raw.find(b"PK\x01\x02")
        central = raw.find(b"PK\x01\x02", first_central + 4)
        for offset in (local + 14, central + 16):
            struct.pack_into("<I", raw, offset, zlib.crc32(b"A"))
        for offset in (local + 22, central + 24):
            struct.pack_into("<I", raw, offset, 1)
        observed = []
        factory = zipfile._get_decompressor

        class ObservedInflater:
            def __init__(self, inner):
                self.inner = inner

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def decompress(self, data, *args, **kwargs):
                output = self.inner.decompress(data, *args, **kwargs)
                observed.append(len(output))
                return output

            def flush(self, *args, **kwargs):
                output = self.inner.flush(*args, **kwargs)
                observed.append(len(output))
                return output

        with (
            patch.object(continuation, "_MAX_MEMBER", 8192),
            patch.object(
                zipfile,
                "_get_decompressor",
                side_effect=lambda kind: ObservedInflater(factory(kind)),
            ),
        ):
            result = continuation._snapshot_bytes(bytes(raw), fixtures.digest(bytes(raw)))
        self.assertEqual(result, {"buddha/test.py": b"A"})
        self.assertTrue(observed)
        self.assertLessEqual(max(observed), 8192)

    def test_corrupt_deflate_has_a_typed_error_and_other_codecs_fail_closed(self):
        raw = bytearray(self.archive(b"preserved data, never executed\n"))
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            local = bundle.getinfo("buddha/test.py").header_offset
        name_size, extra_size = struct.unpack_from("<HH", raw, local + 26)
        raw[local + 30 + name_size + extra_size] = 7
        with self.assertRaises(ValidationError):
            continuation._snapshot_bytes(bytes(raw), fixtures.digest(bytes(raw)))
        for compression in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            raw = self.archive(b"small harmless codec probe", compression=compression)
            with self.subTest(compression=compression), self.assertRaises(ValidationError):
                continuation._snapshot_bytes(raw, fixtures.digest(raw))
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raw = self.archive(b"small harmless codec probe", compression=compression)
            self.assertEqual(
                continuation._snapshot_bytes(raw, fixtures.digest(raw)),
                {"buddha/test.py": b"small harmless codec probe"},
            )


if __name__ == "__main__":
    unittest.main()
