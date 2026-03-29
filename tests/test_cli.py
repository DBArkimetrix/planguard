from pathlib import Path
import subprocess
import unittest

import yaml
from typer.testing import CliRunner

from planguard import __version__
from planguard.config import get_default_plans_root, get_plans_root, get_registry_path, get_status_path
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
        plan_path = get_plans_root() / plan_name / "plan.yaml"
        data = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        data["verify_commands"] = commands
        plan_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def _legacy_status(self, phase: str = "planning") -> dict:
        return {"status": {"phase": phase}}

    def _legacy_plan_data(self, name: str, *, status: str, scope: list[str]) -> dict:
        phase_name = "implementation"
        backlog_id = "BL-001"
        return {
            "plan": {
                "name": name,
                "status": status,
                "created": "2025-01-01",
                "priority": "medium",
            },
            "objective": name.replace("_", " "),
            "scope": {"included": scope},
            "phases": [{"name": phase_name, "tasks": ["Review legacy content"]}],
            "backlog": [{
                "id": backlog_id,
                "title": "Review legacy content",
                "type": "task",
                "phase": phase_name,
                "scope": scope,
                "depends_on": [],
                "deliverables": ["Reviewed legacy content"],
                "tests": ["Document expected behaviour"],
                "done_when": ["Legacy content reviewed"],
            }],
            "sprints": [{
                "id": "SPRINT-01",
                "name": "Sprint 1",
                "goal": "Review legacy content",
                "backlog_items": [backlog_id],
                "focus_paths": scope,
                "exit_criteria": ["Legacy content reviewed"],
            }],
            "risks": [],
            "dependencies": [],
        }

    def _write_legacy_plan(
        self,
        name: str,
        *,
        plan_data: dict | None = None,
        raw_plan: str | None = None,
        status_data: dict | None = None,
    ) -> Path:
        plan_dir = Path("docs") / name
        plan_dir.mkdir(parents=True, exist_ok=True)
        if raw_plan is not None:
            (plan_dir / "plan.yaml").write_text(raw_plan, encoding="utf-8")
        else:
            (plan_dir / "plan.yaml").write_text(
                yaml.safe_dump(plan_data, sort_keys=False),
                encoding="utf-8",
            )
        if status_data is not None:
            (plan_dir / "status.yaml").write_text(
                yaml.safe_dump(status_data, sort_keys=False),
                encoding="utf-8",
            )
        return plan_dir

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

            plan_dir = get_default_plans_root() / "test_plan"
            self.assertTrue((plan_dir / "plan.yaml").exists())
            self.assertTrue(get_status_path("test_plan").exists())

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

    def test_validate_uses_configured_plans_root_by_default(self) -> None:
        with self.runner.isolated_filesystem():
            Path(".planguard").mkdir()
            Path(".planguard/config.yaml").write_text("plans_root: plans\n", encoding="utf-8")

            create_result = self.runner.invoke(app, [
                "plan", "custom root",
                "--objective", "Use custom plans root",
                "--no-wizard",
            ])
            self.assertEqual(create_result.exit_code, 0, create_result.output)
            self.assertTrue(Path("plans/custom_root/plan.yaml").exists())

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

    def test_check_reports_malformed_plan_yaml_without_traceback(self) -> None:
        with self.runner.isolated_filesystem():
            good_result = self.runner.invoke(app, [
                "plan", "alpha plan",
                "--objective", "Valid plan",
                "--no-wizard",
            ])
            self.assertEqual(good_result.exit_code, 0, good_result.output)

            bad_dir = get_default_plans_root() / "broken_yaml"
            bad_dir.mkdir(parents=True, exist_ok=True)
            (bad_dir / "plan.yaml").write_text(
                "\n".join([
                    "plan:",
                    "  name: broken_yaml",
                    "  status: draft",
                    "  created: '2025-01-01'",
                    "  priority: medium",
                    "objective: Broken verify commands",
                    "scope:",
                    "  included:",
                    "    - src/bad",
                    "phases:",
                    "  - name: review",
                    "    tasks:",
                    "      - inspect",
                    "backlog:",
                    "  - id: BL-001",
                    "    title: Inspect",
                    "    type: analysis",
                    "    phase: review",
                    "    scope:",
                    "      - src/bad",
                    "    depends_on: []",
                    "    deliverables:",
                    "      - notes",
                    "    tests:",
                    "      - inspect",
                    "    done_when:",
                    "      - inspected",
                    "sprints:",
                    "  - id: SPRINT-01",
                    "    name: Sprint 1",
                    "    goal: Inspect",
                    "    backlog_items:",
                    "      - BL-001",
                    "    focus_paths:",
                    "      - src/bad",
                    "    exit_criteria:",
                    "      - inspected",
                    "risks: []",
                    "dependencies: []",
                    "verify_commands:",
                    "  - [python -c \"print('a: b')\"",
                    "",
                ]),
                encoding="utf-8",
            )

            result = self.runner.invoke(app, ["check"])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Plan: alpha_plan", result.output)
            self.assertIn("Plan: broken_yaml", result.output)
            self.assertIn("Invalid YAML in plan.yaml:", result.output)
            self.assertRegex(result.output, r"broken_yaml/plan\.yaml:\d+:\d+")
            self.assertNotIn("Traceback", result.output)

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
            self.assertTrue(Path("AGENTS.md").exists())
            self.assertTrue(Path(".planguard").is_dir())
            self.assertTrue((get_default_plans_root()).is_dir())
            self.assertTrue(Path(".planguard/project.yaml").exists())
            self.assertTrue(Path(".planguard/conventions.md").exists())
            self.assertTrue(Path(".planguard/boundaries.md").exists())
            self.assertTrue(Path(".planguard/policies.yaml").exists())
            self.assertIn(".planguard/plans/", Path(".gitignore").read_text(encoding="utf-8"))
            self.assertIn(".planguard/state/", Path(".gitignore").read_text(encoding="utf-8"))
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

    def test_init_refresh_agents_updates_existing_framework_section(self) -> None:
        with self.runner.isolated_filesystem():
            Path("AGENTS.md").write_text(
                "# AGENTS.md\n\n## Local Rules\n\n- Keep this.\n\n<!-- agent-engineering-framework -->\n\nOLD FRAMEWORK TEXT\n",
                encoding="utf-8",
            )

            result = self.runner.invoke(app, ["init", ".", "--no-wizard", "--refresh-agents"])
            self.assertEqual(result.exit_code, 0, result.output)

            content = Path("AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Local Rules", content)
            self.assertIn("Keep this.", content)
            self.assertIn("Run verification: `planguard verify <plan_name>`", content)
            self.assertNotIn("OLD FRAMEWORK TEXT", content)

    def test_upgrade_refreshes_existing_framework_section(self) -> None:
        with self.runner.isolated_filesystem():
            Path("AGENTS.md").write_text(
                "# AGENTS.md\n\n## Local Rules\n\n- Keep this.\n\n<!-- agent-engineering-framework -->\n\nOLD FRAMEWORK TEXT\n",
                encoding="utf-8",
            )

            result = self.runner.invoke(app, ["upgrade", ".", "--no-wizard"])
            self.assertEqual(result.exit_code, 0, result.output)

            content = Path("AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Useful variations:", content)
            self.assertNotIn("OLD FRAMEWORK TEXT", content)

    def test_upgrade_migrates_plan_storage_to_new_root(self) -> None:
        with self.runner.isolated_filesystem():
            Path("docs/migrate_me").mkdir(parents=True)
            Path("docs/migrate_me/plan.yaml").write_text("plan:\n  name: migrate_me\n", encoding="utf-8")
            self.assertTrue(Path("docs/migrate_me/plan.yaml").exists())

            result = self.runner.invoke(app, [
                "upgrade", ".",
                "--no-wizard",
                "--plans-root", ".planguard/plans",
            ])
            self.assertEqual(result.exit_code, 0, result.output)

            self.assertTrue((get_default_plans_root() / "migrate_me" / "plan.yaml").exists())
            self.assertFalse(Path("docs/migrate_me").exists())
            self.assertFalse(Path(".planguard/config.yaml").exists())
            self.assertTrue(get_registry_path().exists())

    def test_upgrade_defaults_legacy_docs_repo_to_local_plans_root(self) -> None:
        with self.runner.isolated_filesystem():
            Path("docs/legacy_plan").mkdir(parents=True)
            Path("docs/legacy_plan/plan.yaml").write_text("plan:\n  name: legacy_plan\n", encoding="utf-8")

            result = self.runner.invoke(app, ["upgrade", ".", "--no-wizard"])
            self.assertEqual(result.exit_code, 0, result.output)

            self.assertTrue((get_default_plans_root() / "legacy_plan" / "plan.yaml").exists())
            self.assertFalse(Path("docs/legacy_plan").exists())
            self.assertFalse(Path(".planguard/config.yaml").exists())

    def test_upgrade_moves_legacy_runtime_state_into_planguard_state(self) -> None:
        with self.runner.isolated_filesystem():
            Path("docs/legacy_plan").mkdir(parents=True)
            Path("docs/planning").mkdir(parents=True)
            Path("docs/legacy_plan/plan.yaml").write_text(
                yaml.safe_dump({
                    "plan": {
                        "name": "legacy_plan",
                        "status": "draft",
                        "created": "2026-03-29",
                        "priority": "medium",
                    },
                    "objective": "Legacy migration",
                    "scope": {"included": ["src"]},
                    "phases": [{"name": "analysis", "tasks": ["Review"]}],
                    "backlog": [{
                        "id": "B1",
                        "title": "Review",
                        "type": "task",
                        "phase": "analysis",
                        "scope": ["src"],
                        "depends_on": [],
                        "deliverables": ["notes"],
                        "tests": [],
                        "done_when": ["Reviewed"],
                    }],
                    "sprints": [{
                        "id": "S1",
                        "name": "Sprint 1",
                        "goal": "Review",
                        "backlog_items": ["B1"],
                        "focus_paths": ["src"],
                        "exit_criteria": ["Reviewed"],
                    }],
                    "risks": [],
                    "dependencies": [],
                }),
                encoding="utf-8",
            )
            Path("docs/legacy_plan/status.yaml").write_text(
                yaml.safe_dump({
                    "status": {"phase": "planning", "progress_percent": 0},
                    "activation": {
                        "activated_at": "",
                        "git_branch": "",
                        "git_head": "",
                        "baseline_changed_files": [],
                        "baseline_fingerprints": {},
                    },
                    "verification": {
                        "passed": False,
                        "last_run": "",
                        "git_branch": "",
                        "git_head": "",
                        "changed_files": [],
                        "fingerprints": {},
                        "commands": [],
                    },
                    "remaining_steps": [],
                    "completed_steps": [],
                    "handoff": {"summary": "", "notes": []},
                }),
                encoding="utf-8",
            )
            Path("docs/planning/active_plans.yaml").write_text(
                "active_plans:\n  - name: legacy_plan\n    status: draft\n",
                encoding="utf-8",
            )

            result = self.runner.invoke(app, ["upgrade", ".", "--no-wizard"])
            self.assertEqual(result.exit_code, 0, result.output)

            self.assertTrue(get_registry_path().exists())
            self.assertTrue(get_status_path("legacy_plan").exists())
            self.assertFalse(Path("docs/planning/active_plans.yaml").exists())
            self.assertFalse(Path("docs/legacy_plan/status.yaml").exists())

    def test_upgrade_suspends_placeholder_plan_and_backfills_review_structure(self) -> None:
        with self.runner.isolated_filesystem():
            placeholder = {
                "plan": {
                    "name": "gateway_agent_ui",
                    "status": "placeholder",
                    "created": "2025-01-01",
                    "priority": "medium",
                },
                "objective": "Gateway agent UI",
                "scope": {"included": ["src/gateway/ui"]},
            }
            self._write_legacy_plan(
                "gateway_agent_ui",
                plan_data=placeholder,
                status_data=self._legacy_status(),
            )

            result = self.runner.invoke(app, ["upgrade", ".", "--no-wizard"])
            self.assertEqual(result.exit_code, 0, result.output)

            migrated_plan = yaml.safe_load(
                (get_default_plans_root() / "gateway_agent_ui" / "plan.yaml").read_text(encoding="utf-8")
            )
            migrated_status = yaml.safe_load(
                get_status_path("gateway_agent_ui").read_text(encoding="utf-8")
            )

            self.assertEqual(migrated_plan["plan"]["status"], "suspended")
            self.assertTrue(migrated_plan["phases"])
            self.assertTrue(migrated_plan["backlog"])
            self.assertTrue(migrated_plan["sprints"])
            self.assertIn("tests", migrated_plan["backlog"][0])
            self.assertIn("focus_paths", migrated_plan["sprints"][0])
            self.assertIn("remaining_steps", migrated_status)
            self.assertEqual(migrated_status["status"]["phase"], "suspended")
            self.assertIn("Suspended for review:", result.output)
            self.assertIn("gateway_agent_ui", result.output)

    def test_upgrade_backfills_legacy_completed_plan_and_status_fields(self) -> None:
        with self.runner.isolated_filesystem():
            legacy_completed = self._legacy_plan_data(
                "reporting_cleanup",
                status="completed",
                scope=["src/reporting"],
            )
            legacy_completed["backlog"][0].pop("tests")
            legacy_completed["sprints"][0].pop("focus_paths")
            self._write_legacy_plan(
                "reporting_cleanup",
                plan_data=legacy_completed,
                status_data=self._legacy_status("completed"),
            )

            result = self.runner.invoke(app, ["upgrade", ".", "--no-wizard"])
            self.assertEqual(result.exit_code, 0, result.output)

            migrated_plan = yaml.safe_load(
                (get_default_plans_root() / "reporting_cleanup" / "plan.yaml").read_text(encoding="utf-8")
            )
            migrated_status = yaml.safe_load(
                get_status_path("reporting_cleanup").read_text(encoding="utf-8")
            )

            self.assertEqual(migrated_plan["plan"]["status"], "completed")
            self.assertEqual(migrated_plan["backlog"][0]["tests"], [])
            self.assertEqual(migrated_plan["sprints"][0]["focus_paths"], ["src/reporting"])
            self.assertIn("activation", migrated_status)
            self.assertIn("verification", migrated_status)
            self.assertIn("remaining_steps", migrated_status)
            self.assertIn("handoff", migrated_status)

    def test_upgrade_and_check_handle_mixed_legacy_repo(self) -> None:
        with self.runner.isolated_filesystem():
            placeholder = {
                "plan": {
                    "name": "gateway_agent_ui",
                    "status": "placeholder",
                    "created": "2025-01-01",
                    "priority": "medium",
                },
                "objective": "Gateway agent UI",
                "scope": {"included": ["src/gateway/ui"]},
            }
            self._write_legacy_plan(
                "gateway_agent_ui",
                plan_data=placeholder,
                status_data=self._legacy_status(),
            )

            missing_focus_paths = self._legacy_plan_data(
                "draft_missing_focus_paths",
                status="draft",
                scope=["src/draft"],
            )
            missing_focus_paths["sprints"][0].pop("focus_paths")
            self._write_legacy_plan(
                "draft_missing_focus_paths",
                plan_data=missing_focus_paths,
                status_data=self._legacy_status(),
            )

            completed_missing_tests = self._legacy_plan_data(
                "completed_missing_tests",
                status="completed",
                scope=["src/completed"],
            )
            completed_missing_tests["backlog"][0].pop("tests")
            self._write_legacy_plan(
                "completed_missing_tests",
                plan_data=completed_missing_tests,
                status_data=self._legacy_status("completed"),
            )

            self._write_legacy_plan(
                "malformed_verify_yaml",
                raw_plan="\n".join([
                    "plan:",
                    "  name: malformed_verify_yaml",
                    "  status: draft",
                    "  created: '2025-01-01'",
                    "  priority: medium",
                    "objective: Malformed verify commands",
                    "scope:",
                    "  included:",
                    "    - src/bad",
                    "phases:",
                    "  - name: review",
                    "    tasks:",
                    "      - inspect",
                    "backlog:",
                    "  - id: BL-001",
                    "    title: Inspect",
                    "    type: analysis",
                    "    phase: review",
                    "    scope:",
                    "      - src/bad",
                    "    depends_on: []",
                    "    deliverables:",
                    "      - notes",
                    "    tests:",
                    "      - inspect",
                    "    done_when:",
                    "      - inspected",
                    "sprints:",
                    "  - id: SPRINT-01",
                    "    name: Sprint 1",
                    "    goal: Inspect",
                    "    backlog_items:",
                    "      - BL-001",
                    "    focus_paths:",
                    "      - src/bad",
                    "    exit_criteria:",
                    "      - inspected",
                    "risks: []",
                    "dependencies: []",
                    "verify_commands:",
                    "  - [python -c \"print('a: b')\"",
                    "",
                ]),
                status_data=self._legacy_status(),
            )
            Path("docs/planning").mkdir(parents=True, exist_ok=True)
            Path("docs/planning/active_plans.yaml").write_text(
                "\n".join([
                    "active_plans:",
                    "  - name: gateway_agent_ui",
                    "    status: placeholder",
                    "  - name: draft_missing_focus_paths",
                    "    status: draft",
                    "  - name: completed_missing_tests",
                    "    status: completed",
                    "  - name: malformed_verify_yaml",
                    "    status: draft",
                    "",
                ]),
                encoding="utf-8",
            )

            upgrade_result = self.runner.invoke(app, ["upgrade", ".", "--no-wizard"])
            self.assertEqual(upgrade_result.exit_code, 0, upgrade_result.output)
            self.assertIn("Normalized plans:", upgrade_result.output)
            self.assertIn("Suspended for review:", upgrade_result.output)
            self.assertIn("Manual review needed:", upgrade_result.output)
            self.assertTrue((get_default_plans_root() / "gateway_agent_ui" / "plan.yaml").exists())
            self.assertTrue(get_status_path("completed_missing_tests").exists())

            check_result = self.runner.invoke(app, ["check"])
            self.assertNotEqual(check_result.exit_code, 0)
            self.assertEqual(check_result.output.count("Structure valid"), 3)
            self.assertIn("Invalid YAML in plan.yaml:", check_result.output)
            self.assertIn("malformed_verify_yaml", check_result.output)
            self.assertNotIn("Traceback", check_result.output)

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

    def test_plan_invalid_template_returns_friendly_error(self) -> None:
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(app, [
                "plan", "bad template",
                "--objective", "Template failure",
                "--template", "nope",
                "--no-wizard",
            ])
            self.assertEqual(result.exit_code, 1, result.output)
            self.assertIn("Unknown template", result.output)
            self.assertNotIn("Traceback", result.output)

    def test_check_allows_declared_rename_with_content_change(self) -> None:
        with self.runner.isolated_filesystem():
            self._init_git_repo()
            Path("src").mkdir()
            Path("src/original.txt").write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "add", "src/original.txt"], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "add source file"], check=True, capture_output=True)

            result = self.runner.invoke(app, [
                "plan", "rename plan",
                "--objective", "Allow a declared rename",
                "--scope", "src/original.txt",
                "--no-wizard",
            ])
            self.assertEqual(result.exit_code, 0, result.output)

            plan_path = get_plans_root() / "rename_plan" / "plan.yaml"
            data = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            data["renames"] = [{"from": "src/original.txt", "to": "src/renamed.txt"}]
            plan_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            activate_result = self.runner.invoke(app, ["activate", "rename_plan"])
            self.assertEqual(activate_result.exit_code, 0, activate_result.output)

            Path("src/original.txt").rename("src/renamed.txt")
            Path("src/renamed.txt").write_text("two\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], check=True, capture_output=True)

            check_result = self.runner.invoke(app, ["check", "rename_plan"])
            self.assertEqual(check_result.exit_code, 0, check_result.output)
            self.assertNotIn("Changed files outside declared scope", check_result.output)
