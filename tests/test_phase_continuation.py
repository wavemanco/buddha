"""Explicit phase projections; synthetic fixtures, no helper compatibility claim."""

import hashlib
import json
import unittest
from pathlib import Path

from buddha import launch_common as common
from buddha import plain_comparison
from buddha.releases import ReleaseError, _json


class PhaseContinuationTests(unittest.TestCase):
    def test_assessment_binds_historical_absolute_helpers_and_original_analysis_map(self):
        from test_improver_assessment import ImproverAssessmentTests

        from buddha import doctor, improver_analysis

        case = ImproverAssessmentTests("runTest")
        self.addCleanup(case.doCleanups)
        case.setUp()
        _, definition = case.capacity_definition()
        current_doctor = Path(doctor.__file__).absolute()
        old_doctor = case.root / "original-helper/doctor.py"
        old_doctor.parent.mkdir()
        old_doctor.write_bytes(current_doctor.read_bytes() + b"\n# original fixture helper\n")
        old_pin = hashlib.sha256(old_doctor.read_bytes()).hexdigest()
        plan = json.loads(Path(definition["analysis_plan"]["path"]).read_bytes())
        self.assertIn("buddha/doctor.py", improver_analysis._source_hashes())
        plan["analyzer_sources"]["buddha/doctor.py"] = old_pin
        definition["analysis_plan"] = case.write("historical-analysis.json", plan)
        definition["consumer_sources"]["buddha/doctor.py"] = old_pin

        def historical(current, *, relative):
            if relative:
                return dict(current) | {"buddha/doctor.py": old_pin}
            return {
                str(old_doctor) if name == str(current_doctor) else name: old_pin
                if name == str(current_doctor)
                else pin
                for name, pin in current.items()
            }

        raw = _json(definition)
        runtime = case.engine.candidate.expected_runtime
        with (
            common._phase_continuation(historical, lambda trial, phase, pins: dict(pins)),
            case.f.h.readonly(),
        ):
            state = case.api._definition(raw, runtime, active=False)
            self.assertEqual(state["record"], definition)
            self.assertEqual(
                state["plan"].to_record()["analyzer_sources"], plan["analyzer_sources"]
            )
            self.assertEqual(state["controls"][old_doctor], old_pin)
            self.assertNotIn(current_doctor, state["controls"])

    def test_source_projection_cannot_drop_required_roles(self):
        with common._phase_continuation(
            lambda current, relative=False: {}, lambda trial, phase, pins: dict(pins)
        ):
            with self.assertRaises(ReleaseError):
                common._historical_sources({str(Path(__file__).absolute()): "a" * 64})

    def test_defaults_return_detached_original_maps(self):
        sources = {"buddha/example.py": "a" * 64}
        pins = {Path(__file__).absolute(): "b" * 64}
        copied = common._historical_sources(sources, relative=True)
        copied.clear()
        self.assertEqual(sources, {"buddha/example.py": "a" * 64})
        projected = common._continued_phase_controls(
            Path(__file__).absolute().parent, "final", pins
        )
        projected.clear()
        self.assertEqual(len(pins), 1)

    def test_explicit_callbacks_receive_detached_maps_and_reset_after_error(self):
        events = []
        root = Path(__file__).absolute().parent
        sources = {"buddha/example.py": "a" * 64}
        pins = {root / "original.json": "b" * 64}

        def historical(current, *, relative):
            events.append((dict(current), relative))
            current.clear()
            return {"buddha/example.py": "c" * 64}

        def controls(trial, phase, current):
            self.assertEqual((trial, phase), (root, "plain"))
            current.clear()
            return {root / "actual.json": "d" * 64}

        with (
            self.assertRaisesRegex(RuntimeError, "supplied"),
            common._phase_continuation(historical, controls),
        ):
            self.assertEqual(
                common._historical_sources(sources, relative=True), {"buddha/example.py": "c" * 64}
            )
            self.assertEqual(
                common._continued_phase_controls(root, "plain", pins),
                {root / "actual.json": "d" * 64},
            )
            with self.assertRaises(ReleaseError), common._phase_continuation(historical, controls):
                pass
            raise RuntimeError("supplied")
        self.assertEqual(events, [(sources, True)])
        self.assertEqual(common._historical_sources(sources), sources)
        self.assertEqual(common._continued_phase_controls(root, "final", pins), pins)

    def test_plain_plan_keeps_original_identity_and_strict_method_guard(self):
        current = plain_comparison._source_hashes()
        root = Path(__file__).absolute().parent
        original = {str(root / "old-host" / Path(name).name): pin for name, pin in current.items()}
        record = {
            "format": "buddha.plain-comparison-plan.v1",
            "method": "all_conditions_then_equal_prompts_descriptive.v1",
            "trial": str(root / "trial"),
            "definition_sha256": "a" * 64,
            "references": [
                {
                    "name": "regenerate",
                    "directory": str(root / "plain"),
                    "authorization": str(root / "grant.sqlite3"),
                    "definition": str(root / "baseline.json"),
                    "sha256": "b" * 64,
                }
            ],
            "consumer_sources": original,
        }
        raw = _json(record)
        with self.assertRaises(plain_comparison.PlainComparisonError):
            plain_comparison._plan(raw)

        def historical(sources, *, relative):
            self.assertFalse(relative)
            self.assertEqual(sources, current)
            return original

        with common._phase_continuation(historical, lambda trial, phase, pins: dict(pins)):
            self.assertEqual(_json(plain_comparison._plan(raw)), raw)
            with self.assertRaises(plain_comparison.PlainComparisonError):
                plain_comparison._plan(_json(record | {"method": "changed"}))


if __name__ == "__main__":
    unittest.main()
