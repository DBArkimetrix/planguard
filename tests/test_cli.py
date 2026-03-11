from pathlib import Path
import unittest

from typer.testing import CliRunner

from agent_framework.cli import app


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_plan_command_creates_required_files(self) -> None:
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(app, ["plan", "Implement pricing engine"])
            self.assertEqual(result.exit_code, 0, result.output)

            plan_dir = Path("docs/implement_pricing_engine")
            self.assertTrue((plan_dir / "plan.yaml").exists())
            self.assertTrue((plan_dir / "backlog.yaml").exists())
            self.assertTrue((plan_dir / "sprint_plan.yaml").exists())
            self.assertTrue((plan_dir / "dependency_map.yaml").exists())

    def test_validate_command_succeeds_for_generated_plan(self) -> None:
        with self.runner.isolated_filesystem():
            create_result = self.runner.invoke(app, ["plan", "Smoke plan"])
            self.assertEqual(create_result.exit_code, 0, create_result.output)

            validate_result = self.runner.invoke(app, ["validate"])
            self.assertEqual(validate_result.exit_code, 0, validate_result.output)
            self.assertIn("All plan structures valid.", validate_result.output)

    def test_graph_command_reads_dependency_format(self) -> None:
        with self.runner.isolated_filesystem():
            plan_dir = Path("docs/example")
            plan_dir.mkdir(parents=True)
            (plan_dir / "dependency_map.yaml").write_text(
                "\n".join(
                    [
                        "dependencies:",
                        "  - id: analyze",
                        "    depends_on: []",
                        "  - id: implement",
                        "    depends_on:",
                        "      - analyze",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.runner.invoke(app, ["graph", "example"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Execution order:", result.output)
            self.assertIn("analyze", result.output)
            self.assertIn("implement", result.output)
