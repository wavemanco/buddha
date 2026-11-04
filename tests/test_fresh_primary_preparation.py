"""Supplied metadata checks only; no frozen inputs or application imports."""

import copy
import importlib.util
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

DRIVER = Path(__file__).resolve().parents[1] / "docs/conformance/prepare-fresh-primary.py"
spec = importlib.util.spec_from_file_location("fresh_primary_supplied", DRIVER)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class FreshPrimaryInputTests(unittest.TestCase):
    def test_hash_only_reference_read_is_exact_scoped_and_reset(self):
        base, _ = self.fixture()
        item, copied = base / "evidence.bin", base / "copied-program.py"
        pin = "a" * 64
        calls, mode, controls = [], ["normal"], {}
        raw = b"\xff supplied opaque evidence"
        foreign_denials = []

        def original_read(target, expected):
            calls.append((target, expected))
            return raw

        def original_ref(value, bound, *, source=False):
            if mode[0] == "raise-before":
                raise RuntimeError("supplied before-read failure")
            target, expected = Path(value["path"]), value["sha256"]
            if mode[0] == "foreign-thread":

                def foreign_read():
                    try:
                        metadata_read(target, expected)
                    except driver.PreparationError:
                        foreign_denials.append(True)

                thread = threading.Thread(target=foreign_read)
                thread.start()
                thread.join()
            data = metadata_read(target, expected)
            if source:
                data.decode("utf-8")
            if mode[0] == "read-twice":
                metadata_read(target, expected)
            if mode[0] == "raise-after":
                raise RuntimeError("supplied after-read failure")
            bound[target] = expected
            return {"path": str(target), "sha256": expected}

        checked_ref, metadata_read = driver.reference_readers(
            original_ref, original_read, {item}, {item: pin}, {copied}
        )
        ref = {"path": str(item), "sha256": pin}
        with self.assertRaises(driver.PreparationError):
            metadata_read(item, pin)
        try:
            self.assertEqual(checked_ref(ref, controls), ref)
        except driver.PreparationError:
            self.fail("valid hash-only byte verification was blocked")
        self.assertEqual(calls, [(item, pin)])
        self.assertEqual(controls, {item: pin})
        for source in (True, 0):
            with self.subTest(source=source), self.assertRaises(driver.PreparationError):
                checked_ref(ref, controls, source=source)
        with self.assertRaises(driver.PreparationError):
            checked_ref(ref | {"sha256": "b" * 64}, controls)
        with self.assertRaises(driver.PreparationError):
            metadata_read(copied, pin)
        with self.assertRaises(driver.PreparationError):
            checked_ref({"path": str(copied), "sha256": pin}, controls)
        self.assertEqual(len(calls), 1)
        for behavior, error in (
            ("raise-before", RuntimeError),
            ("raise-after", RuntimeError),
            ("read-twice", driver.PreparationError),
        ):
            mode[0] = behavior
            with self.subTest(behavior=behavior), self.assertRaises(error):
                checked_ref(ref, controls)
            with self.assertRaises(driver.PreparationError):
                metadata_read(item, pin)
        mode[0] = "normal"
        self.assertEqual(checked_ref(ref, controls), ref)
        mode[0] = "foreign-thread"
        self.assertEqual(checked_ref(ref, controls), ref)
        self.assertEqual(foreign_denials, [True])
        with self.assertRaises(driver.PreparationError):
            metadata_read(item, pin)

    def test_only_consumed_metadata_roles_parse_and_list_panel_stays_opaque(self):
        raw = {name: b"{}" for name in driver.METADATA_NAMES}
        raw.update(
            panel=b'["supplied-a","supplied-b","supplied-c"]',
            split=b"[1,2,3]",
            source=b"opaque source artifact",
            rule=b"opaque rule artifact",
        )
        original = copy.deepcopy(raw)
        seen = []

        def parse(value):
            self.assertNotIn(value, (raw["panel"], raw["split"]), "opaque copied leaf was parsed")
            seen.append(value)
            return driver.load(value)

        result = driver.metadata_inputs(raw, parse)
        self.assertEqual(set(result), set(driver.METADATA_NAMES))
        self.assertEqual(len(seen), 6)
        self.assertEqual(raw, original)
        raw["study"] = b"[]"
        with self.assertRaisesRegex(driver.PreparationError, "invalid_metadata_study"):
            driver.metadata_inputs(raw, driver.load)

    def fixture(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        base = Path(folder.name).resolve()
        source = base / "public"
        source.mkdir()
        public = source / "helper.py"
        public.write_bytes(b"# public supplied source\n")
        metadata = base / "static.json"
        metadata.write_bytes(b'{"supplied":true}')
        first, second = base / "initial.py", base / "evolved.py"
        # No private bytes/preimages are present. These are metadata parser fixtures.
        record = {
            "format": "buddha.fresh-primary-inputs.v1",
            "driver_sha256": "d" * 64,
            "source_root": str(source),
            "source_sha256": {str(public): driver.sha(public.read_bytes())},
            "destination": str(base / "fresh"),
            "experiment_id": "supplied-primary",
            "files": {
                str(metadata): driver.sha(metadata.read_bytes()),
                str(first): driver.AGENTS["initial"],
                str(second): driver.AGENTS["evolved"],
            },
            "inputs": {name: str(metadata) for name in driver.INPUT_NAMES},
            "hash_only": [],
            "copies": {
                "components/initial-agent/candidate.py": str(first),
                "components/evolved-agent/candidate.py": str(second),
            },
            "provenance_receipts": [
                {"path": str(metadata), "sha256": driver.sha(metadata.read_bytes())}
            ],
        }
        return base, record

    def test_strict_metadata_and_exact_manifest_binding(self):
        _, record = self.fixture()
        parsed, _, _, _, opaque = driver.manifest(driver.canonical(record))
        self.assertEqual(parsed, record)
        self.assertEqual(len(opaque), 2)
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b"[]"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                driver.load(raw)
        changed = copy.deepcopy(record)
        changed["files"].pop(changed["inputs"]["custody"])
        with self.assertRaisesRegex(ValueError, "unbound_input_role"):
            driver.manifest(driver.canonical(changed))

    def test_database_history_escape_and_renamed_private_metadata_refuse(self):
        base, record = self.fixture()
        for item in (
            base / "ledger.sqlite3",
            base / "ledger.sqlite3-wal",
            base / "Owners" / "metadata.json",
            base / "search" / "x.json",
        ):
            with self.subTest(item=item), self.assertRaises(ValueError):
                driver.static_path(item)
        changed = copy.deepcopy(record)
        renamed = base / "not-program.json"
        changed["files"][str(renamed)] = driver.AGENTS["initial"]
        changed["inputs"]["custody"] = str(renamed)
        with self.assertRaisesRegex(ValueError, "selected_source_digest_as_metadata"):
            driver.manifest(driver.canonical(changed))
        changed = copy.deepcopy(record)
        changed["copies"]["components/host/profiles.json"] = str(base / "initial.py")
        with self.assertRaisesRegex(ValueError, "opaque_source_role_alias"):
            driver.manifest(driver.canonical(changed))
        changed = copy.deepcopy(record)
        changed["hash_only"] = [str(base / "initial.py")]
        with self.assertRaisesRegex(ValueError, "hash_only_as_copy"):
            driver.manifest(driver.canonical(changed))
        changed = copy.deepcopy(record)
        changed["copies"]["components/../escape.bin"] = str(base / "initial.py")
        with self.assertRaisesRegex(ValueError, "component_destination"):
            driver.manifest(driver.canonical(changed))

    def test_pinned_read_detects_drift_and_never_overwrites(self):
        base, _ = self.fixture()
        item = base / "static.json"
        original = item.read_bytes()
        self.assertEqual(driver.read_pinned(item, driver.sha(original)), original)
        item.write_bytes(b'{"supplied":false}')
        with self.assertRaisesRegex(ValueError, "input_hash_changed"):
            driver.read_pinned(item, driver.sha(original))
        _, record = self.fixture()
        Path(record["destination"]).mkdir()
        with self.assertRaisesRegex(ValueError, "destination_exists"):
            driver.manifest(driver.canonical(record))

    def test_hard_link_alias_is_refused_before_reading(self):
        base, _ = self.fixture()
        item = base / "static.json"
        pin = driver.sha(item.read_bytes())
        try:
            os.link(item, base / "alias.json")
        except OSError:
            self.skipTest("This temporary filesystem cannot create hard links")
        with self.assertRaisesRegex(ValueError, "input_type_link_or_size"):
            driver.read_pinned(item, pin)

    def test_same_bytes_replacement_between_inventory_and_open_is_refused(self):
        base, _ = self.fixture()
        item = base / "static.json"
        raw = item.read_bytes()
        original_open = Path.open
        replaced = []

        def open_replacement(current, *args, **kwargs):
            if current == item and args == ("rb",) and not replaced:
                replaced.append(True)
                item.rename(base / "retained-original.json")
                item.write_bytes(raw)
            return original_open(current, *args, **kwargs)

        with patch.object(Path, "open", open_replacement):
            with self.assertRaisesRegex(ValueError, "opened_input_changed"):
                driver.read_pinned(item, driver.sha(raw))
        self.assertEqual(replaced, [True])

    def test_new_supplied_rows_have_full_typed_coordinates_and_known_scores(self):
        population = {
            "tasks": [
                {
                    "task_id": [1, "1"][i] if i < 2 else f"task-{i}",
                    "family_id": f"family-{min(i, 24)}",
                    "count": 10,
                }
                for i in range(26)
            ]
        }
        slots, rows = driver.supplied_numerical(population, ["a" * 64, "b" * 64])
        self.assertEqual((len(slots), len(rows)), (8, 312))
        coordinates = [
            (r["start"], r["repetition"], r["role"], type(r["task_id"]), r["task_id"]) for r in rows
        ]
        self.assertEqual(len(set(coordinates)), 312)
        self.assertEqual({(r["utility"], r["distinct"]) for r in rows}, {(2, 3), (5, 5), (7, 6)})
        self.assertFalse(any("prompt" in r or "answer" in r for r in rows))


if __name__ == "__main__":
    unittest.main()
