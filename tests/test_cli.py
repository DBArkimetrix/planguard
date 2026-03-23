from pathlib import Path
import subprocess
import unittest

import yaml
from typer.testing import CliRunner

from planguard import __version__
from planguard.cli import app


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def _init_git_repo(self) -> None:
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], check=True, capture_output=True)
        Path("README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], check=True, capture_output=True)

    def _set_verify_commands(self, plan_name: str, commands: list[str]) -> None:
        plan_path = Path("docs") / plan_name / "plan.yaml"
        data = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        data["verify_commands"] = commands
        plan_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def test_plan_command_creates_plan_and_status(self) -> None:
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(app, [
                "plan", "test plan",
                "--objective", "Test objective",
                "--scope", "src, tests",
                "--priority", "medium",
                "--no-wizard",
            ])
            self.assertEqual(result.exit_code, 0, result.output)

            plan_dir = Path("docs/test_plan")
            self.assertTrue((plan_dir / "plan.yaml").exists())
            self.assertTrue((plan_dir / "status.yaml").exists())

    def test_validate_command_succeeds_for_generated_plan(self) -> None:
        with self.runner.isolated_filesystem():
            create_result = self.runner.invoke(app, [
                "plan", "smoke plan",
                "--objective", "Smoke test",
                "--no-wizard",
            ])
            self.assertEqual(create_result.exit_code, 0, create_result.output)

            validate_result = self.runner.invoke(app, ["validate"])
            self.assertEqual(validate_result.exit_code, 0, validate_result.output)

    def test_check_command_passes_for_valid_plan(self) -> None:
        with self.runner.isolated_filesystem():
            self.runner.invoke(app, [
                "plan", "check test",
                "--objective", "Testing checks",
                "--no-wizard",
            ])
            result = self.runner.invoke(app, ["check", "check_test"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("OK", result.output)

    def test_activate_sets_status_to_active(self) -> None:
        with self.runner.isolated_filesystem():
            self.runner.invoke(app, [
                "plan", "activate test",
                "--objective", "Activation test",
                "--no-wizard",
            ])
            result = self.runner.invoke(app, ["activate", "activate_test"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("active", result.output)

    def test_complete_sets_status_to_completed(self) -> None:
        with self.runner.isolated_filesystem():
            self.runner.invoke(app, [
                "plan", "complete test",
                "--objective", "Completion test",
                "--no-wizard",
            ])
            self._set_verify_commands("complete_test", ["python -c \"print('ok')\""])
            self.runner.invoke(app, ["activate", "complete_test"])
            self.runner.invoke(app, ["verify", "complete_test"])
            result = self.runner.invoke(app, ["complete", "complete_test"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("completed", result.output)

    def test_list_excludes_completed_by_default(self) -> None:
        with self.runner.isolated_filesystem():
            # Create two plans.
            self.runner.invoke(app, [
                "plan", "plan one",
                "--objective", "First",
                "--scope", "src/one",
                "--no-wizard",
            ])
            self.runner.invoke(app, [
                "plan", "plan two",
                "--objective", "Second",
                "--scope", "src/two",
                "--no-wizard",
            ])
            # Complete one.
            self._set_verify_commands("plan_one", ["python -c \"print('ok')\""])
            self.runner.invoke(app, ["activate", "plan_one"])
            self.runner.invoke(app, ["verify", "plan_one"])
            self.runner.invoke(app, ["complete", "plan_one"])

            result = self.runner.invoke(app, ["list"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("plan_two", result.output)
            self.assertNotIn("plan_one", result.output)

    def test_list_all_includes_completed(self) -> None:
        with self.runner.isolated_filesystem():
            self.runner.invoke(app, [
                "plan", "done plan",
                "--objective", "Done",
                "--scope", "src/done",
                "--no-wizard",
            ])
            self._set_verify_commands("done_plan", ["python -c \"print('ok')\""])
            self.runner.invoke(app, ["activate", "done_plan"])
            self.runner.invoke(app, ["verify", "done_plan"])
            self.runner.invoke(app, ["complete", "done_plan"])

            result = self.runner.invoke(app, ["list", "--all"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("done_plan", result.output)

    def test_graph_command_reads_dependency_format(self) -> None:
        with self.runner.isolated_filesystem():
            # Create plan with the new format (has dependencies section).
            self.runner.invoke(app, [
                "plan", "graph test",
                "--objective", "Graph test",
                "--no-wizard",
            ])
            result = self.runner.invoke(app, ["graph", "graph_test"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Execution order:", result.output)

    def test_status_command_shows_table(self) -> None:
        with self.runner.isolated_filesystem():
            self.runner.invoke(app, [
                "plan", "status test",
                "--objective", "Status test",
                "--no-wizard",
            ])
            result = self.runner.invoke(app, ["status"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("status_test", result.output)

    def test_init_creates_structure(self) -> None:
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(app, ["init", ".", "--no-wizard"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(Path("docs").is_dir())
            self.assertTrue(Path("AGENTS.md").exists())
            self.assertTrue(Path(".planguard").is_dir())
            self.assertTrue(Path(".planguard/project.yaml").exists())
            self.assertTrue(Path(".planguard/conventions.md").exists())
            self.assertTrue(Path(".planguard/boundaries.md").exists())
            self.assertTrue(Path(".planguard/policies.yaml").exists())
            content = Path("AGENTS.md").read_text()
            self.assertIn("agent-engineering-framework", content)

    def test_init_appends_to_existing_agents_md(self) -> None:
        with self.runner.isolated_filesystem():
            # Pre-existing AGENTS.md with custom rules.
            Path("AGENTS.md").write_text("# AGENTS.md\n\n## Custom Rules\n\n- Do not touch prod.\n")
            result = self.runner.invoke(app, ["init", ".", "--no-wizard"])
            self.assertEqual(result.exit_code, 0, result.output)

            content = Path("AGENTS.md").read_text()
            # Original content preserved.
            self.assertIn("Custom Rules", content)
            self.assertIn("Do not touch prod", content)
            # Framework section appended.
            self.assertIn("agent-engineering-framework", content)
            self.assertIn("PLAN -> CHECK -> ACTIVATE", content)

    def test_init_idempotent_agents_md(self) -> None:
        with self.runner.isolated_filesystem():
            # First init.
            self.runner.invoke(app, ["init", ".", "--no-wizard"])
            first_content = Path("AGENTS.md").read_text()

            # Second init — should not duplicate.
            result = self.runner.invoke(app, ["init", ".", "--no-wizard"])
            self.assertEqual(result.exit_code, 0, result.output)
            second_content = Path("AGENTS.md").read_text()
            self.assertEqual(first_content, second_content)

    def test_version_option(self) -> None:
        result = self.runner.invoke(app, ["--version"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(__version__, result.output)

    def test_check_blocks_changed_files_outside_scope_after_activation(self) -> None:
        with self.runner.isolated_filesystem():
            self._init_git_repo()
            Path("src").mkdir()
            result = self.runner.invoke(app, [
                "plan", "scope test",
                "--objective", "Scope enforcement",
                "--scope", "src",
                "--no-wizard",
            ])
            self.assertEqual(result.exit_code, 0, result.output)
            self.runner.invoke(app, ["activate", "scope_test"])

            Path("README.md").write_text("changed\n", encoding="utf-8")
            result = self.runner.invoke(app, ["check", "scope_test"])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Changed files outside declared scope", result.output)

    def test_complete_requires_fresh_verification(self) -> None:
        with self.runner.isolated_filesystem():
            self._init_git_repo()
            result = self.runner.invoke(app, [
                "plan", "verified completion",
                "--objective", "Completion requires verify",
                "--scope", "README.md",
                "--no-wizard",
            ])
            self.assertEqual(result.exit_code, 0, result.output)
            self._set_verify_commands("verified_completion", ["python -c \"print('ok')\""])

            self.runner.invoke(app, ["activate", "verified_completion"])
            Path("README.md").write_text("change one\n", encoding="utf-8")

            verify_result = self.runner.invoke(app, ["verify", "verified_completion"])
            self.assertEqual(verify_result.exit_code, 0, verify_result.output)

            complete_result = self.runner.invoke(app, ["complete", "verified_completion"])
            self.assertEqual(complete_result.exit_code, 0, complete_result.output)

    def test_complete_fails_if_state_changes_after_verification(self) -> None:
        with self.runner.isolated_filesystem():
            self._init_git_repo()
            result = self.runner.invoke(app, [
                "plan", "stale verify",
                "--objective", "Verification should go stale on new edits",
                "--scope", "README.md",
                "--no-wizard",
            ])
            self.assertEqual(result.exit_code, 0, result.output)
            self._set_verify_commands("stale_verify", ["python -c \"print('ok')\""])

            self.runner.invoke(app, ["activate", "stale_verify"])
            Path("README.md").write_text("change one\n", encoding="utf-8")
            self.runner.invoke(app, ["verify", "stale_verify"])
            Path("README.md").write_text("change two\n", encoding="utf-8")

            complete_result = self.runner.invoke(app, ["complete", "stale_verify"])
            self.assertNotEqual(complete_result.exit_code, 0)
            self.assertIn("Run planguard verify", complete_result.output)

    def test_verify_can_infer_commands_when_plan_omits_them(self) -> None:
        with self.runner.isolated_filesystem():
            Path("requirements.txt").write_text("pytest\n", encoding="utf-8")
            result = self.runner.invoke(app, [
                "plan", "infer verify",
                "--objective", "Infer verification commands",
                "--no-wizard",
            ])
            self.assertEqual(result.exit_code, 0, result.output)
            self.runner.invoke(app, ["activate", "infer_verify"])

            verify_result = self.runner.invoke(app, ["verify", "infer_verify"])
            self.assertEqual(verify_result.exit_code, 0, verify_result.output)
            self.assertIn("python -m unittest discover", verify_result.output)
