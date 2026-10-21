"""Only consumed sealed materializer source may define this research controller."""

import json
import os
import py_compile
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/conformance/meas02-native-audit.py"
MATERIALIZER = ROOT / "docs/conformance/meas02-materialize.py"


class NativeAuditSourceTests(unittest.TestCase):
    def copies(self, directory):
        target = directory / "docs/conformance"
        target.mkdir(parents=True)
        controller = target / SOURCE.name
        materializer = target / MATERIALIZER.name
        controller.write_bytes(SOURCE.read_bytes())
        materializer.write_bytes(MATERIALIZER.read_bytes())
        return controller, materializer

    def child(self, controller, tail):
        # Execute this checked first-party controller copy from its actual bytes;
        # the regression deliberately targets only its materializer loader.
        script = (
            "import json,sys,types\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            f"path=Path({str(controller)!r})\n"
            "module=types.ModuleType('native_audit_source_fixture')\n"
            "module.__file__=str(path)\n"
            "exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)\n" + tail
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=ROOT,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
        return json.loads(completed.stdout)

    def test_adjacent_valid_bytecode_cannot_replace_sealed_materializer_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            controller, materializer = self.copies(Path(temporary))
            original = materializer.read_bytes()
            poison = b"POISON = True\n"
            poison += b"#" * (len(original) - len(poison))
            self.assertEqual(len(poison), len(original))
            materializer.write_bytes(poison)
            stamp = materializer.stat().st_mtime_ns
            py_compile.compile(str(materializer), doraise=True)
            materializer.write_bytes(original)
            os.utime(materializer, ns=(stamp, stamp))
            result = self.child(
                controller,
                "print(json.dumps({'poison':module.materializer.__dict__.get('POISON',False)}))\n",
            )
            self.assertEqual(result, {"poison": False})
            self.assertEqual(materializer.read_bytes(), original)

    def test_consumed_source_cannot_change_before_invocation_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            controller, _ = self.copies(Path(temporary))
            result = self.child(
                controller,
                "path=module.MATERIALIZER\n"
                "path.write_bytes(path.read_bytes()+b'\\n')\n"
                "try:\n"
                " module._sources()\n"
                "except module.NativeAuditError:\n"
                " rejected=True\n"
                "else:\n"
                " rejected=False\n"
                "print(json.dumps({'source_change_rejected':rejected}))\n",
            )
            self.assertEqual(result, {"source_change_rejected": True})


if __name__ == "__main__":
    unittest.main()
