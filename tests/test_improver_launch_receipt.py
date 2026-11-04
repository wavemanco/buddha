"""Pinned descriptor closure protects receipt destinations without execution."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from buddha.launch_common import _receipt_roots
from buddha.releases import ReleaseError, _json


class ImproverLaunchReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def save(self, name, record):
        path = self.root / name
        raw = _json(record)
        path.write_bytes(raw)
        return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}

    def roots(self, reference):
        return _receipt_roots(Path(reference["path"]), reference["sha256"])

    def test_matched_graph_excludes_all_grants_components_and_assessment_inputs(self):
        grants = {
            phase: self.root / (phase + ".sqlite3") for phase in ("search", "validation", "final")
        }
        components = {role: str(self.root / role) for role in ("agent", "host", "official")}
        control = self.root / "selected-control.py"
        unopened = self.root / "not-a-descriptor.json"
        development = self.save(
            "development.json",
            {
                "format": "buddha.improver-study.v4",
                "nested": [{"roots": components, "source_sha256": {str(control): "0" * 64}}],
                "proposal": {"path": str(unopened), "sha256": "0" * 64},
            },
        )
        inputs = {"development": development}
        for name in ("tasks", "custody", "analysis_plan", "improvement_rule"):
            inputs[name] = self.save(name + ".json", {"format": "toy.input.v1"})
        assessment = self.save(
            "assessment.json", {"format": "buddha.improver-assessment-trial.v4", **inputs}
        )
        handoff = self.save(
            "handoff.json", {"format": "buddha.improver-handoff.v1", "assessment": assessment}
        )
        approval = self.save(
            "approval.json",
            {
                "format": "toy.approval.v1",
                "authorizations": {phase: {"path": str(path)} for phase, path in grants.items()},
            },
        )
        directory, review = self.root / "trial", self.root / "review.json"
        launch = self.save(
            "launch.json",
            {
                "format": "buddha.improver-launch.v1",
                "proposal": handoff,
                "approval": approval,
                "directory": str(directory),
                "review": str(review),
            },
        )
        before = {path: path.read_bytes() for path in self.root.iterdir()}
        expected = {
            *(
                Path(ref["path"])
                for ref in (*inputs.values(), assessment, handoff, approval, launch)
            ),
            *grants.values(),
            *(Path(path) for path in components.values()),
            control,
            unopened,
            directory,
            review,
        }
        self.assertEqual(self.roots(launch), sorted(expected))
        self.assertEqual({path: path.read_bytes() for path in self.root.iterdir()}, before)
        # Arbitrary nested path declarations are exclusions, never opened inputs.
        self.assertFalse(unopened.exists())
        self.assertFalse(control.exists())
        self.assertTrue(all(not path.exists() for path in grants.values()))

    def test_existing_source_and_policy_root_formats_retain_their_closures(self):
        leaf = self.save("leaf.json", {"format": "toy.input.v1"})
        source = self.save(
            "source.json", {"format": "buddha.source-launch.v1", "proposal": leaf, "approval": leaf}
        )
        self.assertEqual(set(self.roots(source)), {Path(source["path"]), Path(leaf["path"])})
        handoff = self.save(
            "policy-handoff.json",
            {"format": "buddha.policy-handoff.v1", "study": leaf, "baseline": leaf},
        )
        execution = self.save(
            "policy-execution.json",
            {"format": "buddha.policy-execution.v1", "study": leaf, "baseline": leaf},
        )
        policy = self.save(
            "policy.json",
            {
                "format": "buddha.policy-launch.v1",
                "proposal": handoff,
                "execution": execution,
                "approval": leaf,
            },
        )
        self.assertEqual(
            set(self.roots(policy)),
            {Path(ref["path"]) for ref in (leaf, handoff, execution, policy)},
        )

    def test_unknown_root_format_cannot_authorize_exclusions(self):
        unknown = self.save("unknown.json", {"format": "buddha.improver-launch.v999"})
        with self.assertRaisesRegex(ReleaseError, "known pinned launch"):
            self.roots(unknown)

    def test_wrong_root_or_referenced_pin_is_refused(self):
        leaf = self.save("leaf.json", {"format": "toy.input.v1"})
        launch = self.save(
            "launch.json",
            {"format": "buddha.improver-launch.v1", "proposal": leaf, "approval": leaf},
        )
        with self.assertRaises(ReleaseError):
            self.roots({**launch, "sha256": "0" * 64})
        launch = self.save(
            "launch.json",
            {
                "format": "buddha.improver-launch.v1",
                "proposal": {**leaf, "sha256": "0" * 64},
                "approval": self.save("approval.json", {"format": "toy.approval.v1"}),
            },
        )
        with self.assertRaises(ReleaseError):
            self.roots(launch)

    def test_conflicting_duplicate_reference_is_refused(self):
        leaf = self.save("leaf.json", {"format": "toy.input.v1"})
        launch = self.save(
            "launch.json",
            {
                "format": "buddha.improver-launch.v1",
                "proposal": leaf,
                "approval": {**leaf, "sha256": "0" * 64},
            },
        )
        with self.assertRaisesRegex(ReleaseError, "conflicting receipt exclusion"):
            self.roots(launch)

    def test_closure_accepts_sixteen_descriptors_and_refuses_seventeen(self):
        leaf = self.save("leaf.json", {"format": "toy.input.v1"})
        previous = leaf
        for index in range(15):
            previous = self.save(
                str(index) + ".json",
                {"format": "buddha.improver-handoff.v1", "assessment": previous},
            )
            if index >= 13:
                launch = self.save(
                    "launch.json",
                    {"format": "buddha.improver-launch.v1", "proposal": previous, "approval": leaf},
                )
                if index == 13:
                    self.assertEqual(len(self.roots(launch)), 16)
                else:
                    with self.assertRaisesRegex(ReleaseError, "closure exceeds its boundary"):
                        self.roots(launch)

    def test_back_reference_to_earlier_root_bytes_is_refused_as_conflicting(self):
        leaf = self.save("leaf.json", {"format": "toy.input.v1"})
        earlier_root = self.save(
            "launch.json",
            {"format": "buddha.improver-launch.v1", "proposal": leaf, "approval": leaf},
        )
        back_reference = self.save(
            "cycle.json", {"format": "buddha.improver-handoff.v1", "assessment": earlier_root}
        )
        launch = self.save(
            "launch.json",
            {"format": "buddha.improver-launch.v1", "proposal": back_reference, "approval": leaf},
        )
        with self.assertRaisesRegex(ReleaseError, "conflicting receipt exclusion"):
            self.roots(launch)


if __name__ == "__main__":
    unittest.main()
