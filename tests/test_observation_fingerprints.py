"""Stable observation identities without changing historical doctor output."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from buddha.doctor import _Busy, _Capture


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class ObservationFingerprintsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "observation"
        self.root.mkdir()
        self.local = self.root / "local.txt"
        self.first = self.base / "left" / "same-name.txt"
        self.second = self.base / "right" / "same-name.txt"
        for path, raw in (
            (self.local, b"local bytes"),
            (self.first, b"first:AAAA"),
            (self.second, b"second:CCC"),
        ):
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(raw)

    def capture(self, *paths):
        capture = _Capture(self.root)
        for path in paths:
            capture.read(path)
        return capture

    def test_external_identities_are_complete_order_independent_and_change_sensitive(self):
        forward = self.capture(self.local, self.first, self.second)
        legacy = {
            "local.txt": digest(self.local.read_bytes()),
            "authorization": digest(self.second.read_bytes()),
        }
        # Existing doctor output retains its original key convention. The new
        # state-seal input must distinguish both outside files, even when their
        # basenames match, instead of changing that historical output schema.
        self.assertEqual(forward.finish(), legacy)
        first = forward.fingerprints()
        self.assertEqual(
            first,
            {
                str(path): digest(path.read_bytes())
                for path in (self.local, self.first, self.second)
            },
        )
        self.assertEqual(forward.finish(), legacy)
        self.assertEqual(self.capture(self.second, self.first, self.local).fingerprints(), first)
        self.first.write_bytes(b"first:BBBB")
        after = self.capture(self.local, self.first, self.second).fingerprints()
        self.assertNotEqual(after[str(self.first)], first[str(self.first)])
        self.assertEqual(after[str(self.second)], first[str(self.second)])
        self.assertEqual(after[str(self.local)], first[str(self.local)])
        after[str(self.second)] = "caller mutation"
        self.assertEqual(
            self.capture(self.local, self.first, self.second).fingerprints()[str(self.second)],
            first[str(self.second)],
        )

    def test_fingerprints_refuse_consumed_byte_drift_and_late_local_entries(self):
        capture = self.capture(self.local, self.first, self.second)
        self.first.write_bytes(b"first:BBBB")
        with self.assertRaises(_Busy):
            capture.fingerprints()
        capture = self.capture(self.local, self.first, self.second)
        (self.root / "late-entry.txt").write_bytes(b"late")
        with self.assertRaises(_Busy):
            capture.fingerprints()

    def test_fingerprints_recheck_late_database_sidecars(self):
        capture = _Capture(self.root)
        # _Capture consumes raw bounded bytes; this test needs no SQLite
        # connection or database parser to establish sidecar exclusion.
        capture.database(self.first)
        self.first.with_name(self.first.name + "-wal").write_bytes(b"live sidecar")
        with self.assertRaises(_Busy):
            capture.fingerprints()


if __name__ == "__main__":
    unittest.main()
