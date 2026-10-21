"""Exact-byte AST reuse must never reuse file identity or spending permission."""

import ast
import hashlib
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import test_gateway as fixtures

from buddha import gateway


class CoreSourceCacheTests(unittest.TestCase):
    def setUp(self):
        cached = getattr(gateway, "_cached_core_source", None)
        if cached is not None:
            cached.cache_clear()
            self.addCleanup(cached.cache_clear)

    @contextmanager
    def installed(self):
        # Real temporary reads/hashes; only module path attributes are redirected.
        with tempfile.TemporaryDirectory() as name, ExitStack() as stack:
            root = Path(name).resolve()
            paths = {}
            for module_name in sorted(gateway.CORE):
                filename = (
                    "__init__.py" if module_name == "buddha" else module_name.split(".")[-1] + ".py"
                )
                path = root / filename
                path.write_bytes(("pass\n# " + module_name + "\n").encode())
                stack.enter_context(patch.object(sys.modules[module_name], "__file__", str(path)))
                paths[module_name] = path
            yield paths

    def test_identical_bytes_skip_ast_but_every_module_is_freshly_hashed_and_read(self):
        with self.installed():
            first = gateway._core_sources()
            original_read = Path.read_bytes
            with (
                patch.object(gateway.ast, "parse", wraps=ast.parse) as parse,
                patch.object(gateway.ast, "walk", wraps=ast.walk) as walk,
                patch.object(gateway, "file_hash", wraps=gateway.file_hash) as hashed,
                patch.object(Path, "read_bytes", autospec=True, side_effect=original_read) as read,
            ):
                second = gateway._core_sources()
            self.assertEqual(first, second)
            self.assertEqual(hashed.call_count, len(gateway.CORE))
            self.assertEqual(read.call_count, len(gateway.CORE))
            self.assertEqual(parse.call_count, 0)
            self.assertEqual(walk.call_count, 0)

    def test_warm_cache_rejects_changed_malicious_bytes_with_same_size_and_mtime(self):
        for bad in (b"import buddha.unbound\n", b"eval('1')\n", b"from . import common\n"):
            with self.subTest(source=bad), self.installed() as paths:
                path = paths["buddha.common"]
                good = b"pass\n#" + b" " * (len(bad) - 7) + b"\n"
                self.assertEqual(len(good), len(bad))
                path.write_bytes(good)
                first = gateway._core_sources()
                metadata = path.stat()
                path.write_bytes(bad)
                os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
                self.assertEqual(path.stat().st_size, metadata.st_size)
                self.assertEqual(path.stat().st_mtime_ns, metadata.st_mtime_ns)
                self.assertNotEqual(hashlib.sha256(bad).hexdigest(), first["buddha.common"])
                with self.assertRaises(gateway.GatewayError):
                    gateway._core_sources()

    def test_cache_key_includes_the_immutable_allowed_closure(self):
        cached = gateway._cached_core_source
        raw = b"import buddha.future\n"
        permitted = gateway.CORE | {"buddha.future"}
        cached(raw, permitted)
        with self.assertRaisesRegex(gateway.GatewayError, "unbound package module"):
            cached(raw, gateway.CORE)
        with patch.object(gateway.ast, "parse", wraps=ast.parse) as parse:
            cached(raw, permitted)
        self.assertEqual(parse.call_count, 0)
        self.assertEqual(cached.cache_info().currsize, 1)

    def test_rejected_sources_and_syntax_errors_are_never_cached(self):
        cached = gateway._cached_core_source
        cases = (
            (b"import buddha_unbound\n", gateway.GatewayError, "unbound package module"),
            (b"from buddha import future\n", gateway.GatewayError, "unbound package module"),
            (b"from . import common\n", gateway.GatewayError, "relative core imports"),
            (b"exec('pass')\n", gateway.GatewayError, "dynamic core loading"),
            (b"importlib.import_module('x')\n", gateway.GatewayError, "dynamic core loading"),
            (b"def broken(\n", SyntaxError, None),
        )
        for raw, error, message in cases:
            with (
                self.subTest(source=raw),
                patch.object(gateway.ast, "parse", wraps=ast.parse) as parse,
            ):
                for _ in range(2):
                    with self.assertRaises(error) as caught:
                        cached(raw, gateway.CORE)
                    if message is not None:
                        self.assertIn(message, str(caught.exception))
                self.assertEqual(parse.call_count, 2)
                self.assertEqual(cached.cache_info().currsize, 0)

    def test_inclusive_byte_limit_and_oversized_uncached_validation(self):
        with self.installed() as paths:
            path = paths["buddha.common"]
            boundary = b"#" + b"x" * (512 * 1024 - 2) + b"\n"
            path.write_bytes(boundary)
            gateway._core_sources()
            with patch.object(gateway.ast, "parse", wraps=ast.parse) as parse:
                gateway._core_sources()
            self.assertEqual(parse.call_count, 0)
            oversized = boundary + b"\n"
            path.write_bytes(oversized)
            with patch.object(gateway.ast, "parse", wraps=ast.parse) as parse:
                for _ in range(2):
                    self.assertEqual(
                        gateway._core_sources()["buddha.common"],
                        hashlib.sha256(oversized).hexdigest(),
                    )
            self.assertEqual(parse.call_count, 2)
            path.write_bytes(oversized + b"eval('1')\n")
            with self.assertRaisesRegex(gateway.GatewayError, "dynamic core loading"):
                gateway._core_sources()

    def test_lru_retains_at_most_sixteen_successful_byte_keys(self):
        cached = gateway._cached_core_source
        self.assertEqual(cached.cache_parameters()["maxsize"], 16)
        sources = [("pass\n# " + str(index)).encode() for index in range(17)]
        for raw in sources:
            cached(raw, gateway.CORE)
        self.assertEqual(cached.cache_info().currsize, 16)
        with patch.object(gateway.ast, "parse", wraps=ast.parse) as parse:
            cached(sources[0], gateway.CORE)
        self.assertEqual(parse.call_count, 1)

    def test_warm_cache_keeps_read_after_hash_path_and_inventory_guards(self):
        with self.installed() as paths:
            gateway._core_sources()
            target = paths["buddha.common"]
            original_read = Path.read_bytes

            def changed(path):
                raw = original_read(path)
                return raw + b"# drift\n" if path == target else raw

            with (
                patch.object(Path, "read_bytes", autospec=True, side_effect=changed),
                self.assertRaisesRegex(gateway.GatewayError, "changed during verification"),
            ):
                gateway._core_sources()
            with (
                patch.object(
                    sys.modules["buddha.common"], "__file__", str(target.parent / "other.py")
                ),
                self.assertRaisesRegex(gateway.GatewayError, "outside its installed package"),
            ):
                gateway._core_sources()
            with (
                patch.object(gateway, "CORE", gateway.CORE | {"buddha.future"}),
                self.assertRaisesRegex(gateway.GatewayError, "inventory is incomplete"),
            ):
                gateway._core_sources()

    def test_valid_changed_bytes_still_fail_the_original_owner_identity_before_spending(self):
        fixture = fixtures.GatewayTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original = gateway._core_sources()
        target = Path(sys.modules["buddha.common"].__file__).absolute()
        modified = target.read_bytes() + b"\n# valid changed core bytes\n"
        original_hash, original_read = gateway.file_hash, Path.read_bytes

        def hashed(path, **kwargs):
            if path == target:
                return hashlib.sha256(modified).hexdigest()
            return original_hash(path, **kwargs)

        def read(path):
            return modified if path == target else original_read(path)

        before = fixture.authority.path.read_bytes()
        with (
            patch.object(gateway, "file_hash", side_effect=hashed),
            patch.object(Path, "read_bytes", autospec=True, side_effect=read),
        ):
            self.assertNotEqual(gateway._core_sources(), original)
            with self.assertRaisesRegex(gateway.GatewayError, "core or runtime changed"):
                gateway.execution_identity(fixture.directory)
        self.assertEqual(fixture.authority.path.read_bytes(), before)
        self.assertEqual(fixture.ledger.totals()["operation_count"], 0)


if __name__ == "__main__":
    unittest.main()
