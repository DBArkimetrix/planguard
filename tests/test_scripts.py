from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class ScriptWrapperTests(unittest.TestCase):
    def test_generate_plan_wrapper_uses_package_logic(self) -> None:
        with TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "generate_plan.py"), "Wrapper smoke plan"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(Path(temp_dir, "docs", "wrapper_smoke_plan", "dependency_map.yaml").exists())
