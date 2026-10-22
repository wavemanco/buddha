"""Derived formats reuse validated state while artifact views stay detached."""

import copy
import hashlib
import inspect
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import test_source_screen as fixtures

from buddha import answers, source_screen
from buddha.releases import _json


class SourceScreenFormatTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch("buddha.executor.run_container", side_effect=AssertionError("worker forbidden"))
        )
        self.enterContext(
            patch("http.client.HTTPSConnection", side_effect=AssertionError("HTTPS forbidden"))
        )
        self.fixture = fixtures.SourceScreenTests("runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def tearDown(self):
        self.assertEqual(self.fixture.engine.physical_sends, 0)
        self.assertEqual(self.fixture.engine.workers, 0)
        self.assertEqual(self.fixture.engine.native_workers, 0)

    def screen(self, version):
        record = copy.deepcopy(self.fixture.record)
        record["format"] = "buddha.source-screen." + version
        return source_screen.SourceScreen.from_bytes(_json(record)), record

    @staticmethod
    def formats(version):
        return {
            "context": "buddha.candidate-generation-context." + version,
            "seal": "buddha.candidate-generation-stage." + version,
            "anchor": (
                "candidate generation completed: "
                if version == "v1"
                else "candidate generation outcome completed: "
            ),
            "source": "buddha.candidate-generation-source." + version,
        }

    def test_repeated_format_reads_do_not_decode_the_full_validated_artifact(self):
        for version in ("v1", "v2"):
            with self.subTest(version=version):
                screen, _ = self.screen(version)
                with patch.object(answers, "_load", wraps=answers._load) as decoded:
                    for _ in range(3):
                        for stem in (
                            "candidate-generation",
                            "source-screen-context",
                            "source-screen-report",
                        ):
                            self.assertEqual(
                                source_screen._version(screen, stem),
                                "buddha." + stem + "." + version,
                            )
                        exposed = source_screen._generation_formats(screen)
                        self.assertEqual(exposed, self.formats(version))
                        exposed["source"] = "changed detached mapping"
                self.assertEqual(decoded.call_count, 0, "format access decoded the full artifact")

    def test_derived_scalar_and_data_are_immutable_and_not_constructor_inputs(self):
        self.assertEqual(list(inspect.signature(source_screen.SourceScreen).parameters), ["data"])
        for version in ("v1", "v2"):
            screen, _ = self.screen(version)
            with self.subTest(version=version):
                with self.assertRaises(FrozenInstanceError):
                    screen.data = b"{}"
                with self.assertRaises(FrozenInstanceError):
                    screen._format_version = "v2" if version == "v1" else "v1"
                with self.assertRaises(FrozenInstanceError):
                    del screen._format_version
                with self.assertRaises(TypeError):
                    source_screen.SourceScreen(screen.to_bytes(), _format_version="v3")
                self.assertEqual(
                    source_screen._version(screen, "source-screen-context"),
                    "buddha.source-screen-context." + version,
                )

    def test_record_views_still_decode_fresh_and_cannot_change_formats_or_identity(self):
        for version in ("v1", "v2"):
            with self.subTest(version=version):
                screen, original = self.screen(version)
                saved, fingerprint = screen.to_bytes(), screen.fingerprint()
                original["format"] = "buddha.source-screen.v3"
                original["selected_ids"].reverse()
                with patch.object(answers, "_load", wraps=answers._load) as decoded:
                    first, second = screen.to_record(), screen.to_record()
                self.assertEqual(decoded.call_count, 2)
                first["format"] = "buddha.source-screen.v3"
                first["selected_ids"].reverse()
                first["generation"]["config"]["instructions"] = "mutated exposed instructions"
                first["source"]["tasks"][0]["prompt"] = "mutated exposed task"
                self.assertEqual(second["format"], "buddha.source-screen." + version)
                self.assertEqual(second["selected_ids"], ["1", 1])
                self.assertEqual(screen.to_record(), second)
                self.assertEqual(screen.to_bytes(), saved)
                self.assertEqual(screen.fingerprint(), fingerprint)
                self.assertEqual(source_screen._generation_formats(screen), self.formats(version))

    def test_canonical_bytes_equality_hash_and_v1_v2_identities_are_preserved(self):
        screens = []
        for version in ("v1", "v2"):
            with self.subTest(version=version):
                screen, record = self.screen(version)
                record["generation"]["config"]["instructions"] = "Literal café 🍃\ntext"
                canonical = _json(record)
                decorated = json.dumps(record, indent=2, ensure_ascii=False).encode("utf-8")
                screen = source_screen.SourceScreen.from_bytes(decorated)
                clone = source_screen.SourceScreen(canonical)
                self.assertEqual(screen.to_bytes(), canonical)
                self.assertEqual(screen.to_record(), record)
                self.assertEqual(screen.fingerprint(), hashlib.sha256(canonical).hexdigest())
                self.assertEqual(screen, clone)
                self.assertEqual(hash(screen), hash(clone))
                self.assertEqual(repr(screen), "SourceScreen()")
                self.assertEqual(source_screen._generation_formats(screen), self.formats(version))
                screens.append(screen)
        self.assertEqual(screens[0].candidate_id, screens[1].candidate_id)
        self.assertEqual(screens[0].tasks.to_bytes(), screens[1].tasks.to_bytes())
        self.assertNotEqual(screens[0], screens[1])
        self.assertNotEqual(screens[0].fingerprint(), screens[1].fingerprint())
        self.assertNotEqual(screens[0].comparison_key(), screens[1].comparison_key())
        replaced = replace(screens[0], data=screens[1].to_bytes())
        self.assertEqual(replaced, screens[1])
        self.assertEqual(source_screen._generation_formats(replaced), self.formats("v2"))

    def test_invalid_formats_and_controls_still_fail_full_artifact_validation(self):
        for version in ("v1", "v2"):
            _, original = self.screen(version)
            variants = []
            for label, change in (
                ("format", lambda r: r.update(format="buddha.source-screen.v3")),
                ("private field", lambda r: r.update(_format_version="v1")),
                ("heldout", lambda r: r.update(selected_ids=["final"])),
                ("bool ID", lambda r: r.update(selected_ids=[True])),
                ("bool quota", lambda r: r["generation"].update(max_callbacks=True)),
                ("bool cap", lambda r: r["generation"]["config"].update(max_output_tokens=True)),
                ("runtime", lambda r: r["generation"]["runtime"].update(sha256="0" * 64)),
                ("mounts", lambda r: r["generation"]["executor"].update(mounts=[])),
            ):
                record = copy.deepcopy(original)
                change(record)
                variants.append((label, _json(record)))
            variants.append(
                (
                    "duplicate format",
                    _json(original).replace(
                        b'{"format":', b'{"format":"buddha.source-screen.v1","format":', 1
                    ),
                )
            )
            for label, raw in variants:
                with self.subTest(version=version, invalid=label):
                    with self.assertRaises(source_screen.SourceScreenError):
                        source_screen.SourceScreen.from_bytes(raw)


if __name__ == "__main__":
    unittest.main()
