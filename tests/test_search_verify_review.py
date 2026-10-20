"""Regressions for independently reproduced verifier inventory and binding gaps."""

import copy
import unittest
from pathlib import Path

import test_continuation_source as archives
from search_verify_helpers import (
    corrupt_database,
    evidence_for,
    linked,
    ordinary,
    readonly_boundary,
    sha,
    source_snapshot,
)

from buddha import benchmark, common
from buddha.common import ValidationError
from buddha.continuation import _snapshot_bytes
from buddha.search_evidence import read_authority, read_search_evidence
from buddha.search_verify import (
    _archive_contract,
    _financial,
    _initial_context,
    _record,
    verify_search,
)


class SearchVerificationReviewTests(unittest.TestCase):
    def verify(self, fixture):
        evidence = evidence_for(fixture)
        before = source_snapshot(evidence)
        declaration = copy.deepcopy(evidence)
        try:
            with readonly_boundary():
                return verify_search(fixture.directory, evidence=evidence).to_record()
        finally:
            self.assertEqual(before, source_snapshot(evidence))
            self.assertEqual(declaration, evidence)

    def test_known_extracted_archive_requires_its_sealed_common_dependency(self):
        snapshot = _snapshot_bytes(archives.ARCHIVE.read_bytes(), archives.ARCHIVE_SHA)
        contracts = archives.old_contracts()
        original = copy.deepcopy(contracts)
        # The original pre-extraction archive legitimately has no common module.
        with readonly_boundary():
            _archive_contract(snapshot, contracts)
        self.assertEqual(contracts, original)
        source = Path(benchmark.__file__).read_bytes()
        snapshot["buddha/benchmark.py"] = source
        contracts["source_sha256"]["buddha.benchmark"] = sha(source)
        snapshot["buddha/common.py"] = Path(common.__file__).read_bytes()
        declaration = copy.deepcopy(contracts)
        with readonly_boundary():
            _archive_contract(snapshot, contracts)
        self.assertEqual(contracts, declaration)
        for raw in (None, b"# a different dependency\n"):
            mutated = dict(snapshot)
            if raw is None:
                del mutated["buddha/common.py"]
            else:
                mutated["buddha/common.py"] = raw
            with (
                self.subTest(raw=raw),
                readonly_boundary(),
                self.assertRaises(ValidationError),
            ):
                _archive_contract(mutated, contracts)
            self.assertEqual(contracts, declaration)

    def test_extra_file_inside_checked_candidate_cannot_be_reported_verified(self):
        fixture = ordinary(self)
        self.assertEqual(self.verify(fixture)["status"], "verified")
        candidate = fixture.report["candidates"][0]["candidate_id"]
        path = fixture.directory / "candidates" / candidate / "policy.backup.json"
        path.write_bytes(b'{"extra":"not part of the candidate artifact contract"}\n')
        with self.assertRaises(ValidationError):
            self.verify(fixture)

    def test_bound_local_ledger_must_identify_the_explicit_shared_authority(self):
        fixture = linked(self)
        self.assertEqual(self.verify(fixture)["status"], "verified")
        path = fixture.directory / "operations.sqlite3"
        original = path.read_bytes()
        for field, value in (
            ("authorization_id", "a-different-authority"),
            ("authority_path", "different-recorded-authority.sqlite3"),
            ("terms_sha256", "a" * 64),
            (None, None),
        ):
            with self.subTest(field=field):
                path.write_bytes(original)
                if field is None:
                    corrupt_database(path, "DROP TABLE authorization_binding")
                else:
                    corrupt_database(path, f"UPDATE authorization_binding SET {field}=?", (value,))
                with self.assertRaises(ValidationError):
                    self.verify(fixture)

    def test_initial_historical_context_matches_sources_while_current_totals_are_separate(self):
        fixture = linked(self)
        evidence = evidence_for(fixture)
        before = source_snapshot(evidence)
        with readonly_boundary():
            snapshot = read_search_evidence(fixture.directory, evidence=evidence)
            histories = {run.directory: _financial(run) for run in snapshot.runs}
            authority = read_authority(snapshot.authorization)
            metadata = _record(snapshot.runs[0].blob("manifest.json"))["continuation"]
            context = metadata["authorization_context"]
            # The current mirror includes the completed continuation, so valid
            # earlier context totals genuinely differ from current shared costs.
            self.assertNotEqual(context["spent_microusd"], authority["totals"]["spent_microusd"])
            _initial_context(context, histories, authority)
            altered = copy.deepcopy(context)
            other = next(
                row for row in altered["runs"] if row["run_id"] != metadata["source_run_id"]
            )
            self.assertGreater(other["spent_microusd"], 0)
            for target in (other, altered):
                target["spent_microusd"] -= 1
                target["committed_microusd"] -= 1
            altered["available_microusd"] += 1
            with self.assertRaises(ValidationError):
                _initial_context(altered, histories, authority)
            snapshot.finish()
        self.assertEqual(before, source_snapshot(evidence))
