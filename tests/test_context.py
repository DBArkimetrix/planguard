"""Tests for project context, policy engine, session log, and verify."""

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

import yaml

from planguard.context.project_context import (
    init_context,
    has_context,
    load_policies,
    load_boundaries,
)
from planguard.context.session_log import log_event, read_log
from planguard.planning.generate_plan import generate_plan
from planguard.safety.check_policies import check_policies, check_boundary_violations


class ProjectContextTests(unittest.TestCase):
    def test_init_creates_context_files(self) -> None:
        with TemporaryDirectory() as tmp:
            created = init_context(
                tmp,
                name="test-project",
                languages=["python"],
                frameworks=["FastAPI"],
                source_dirs=["src"],
                test_dirs=["tests"],
            )
            self.assertTrue(has_context(tmp))
            ctx = Path(tmp) / ".planguard"
            self.assertTrue((ctx / "project.yaml").exists())
            self.assertTrue((ctx / "conventions.md").exists())
            self.assertTrue((ctx / "boundaries.md").exists())
            self.assertTrue((ctx / "glossary.md").exists())
            self.assertTrue((ctx / "policies.yaml").exists())

    def test_init_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            first = init_context(tmp, name="test")
            second = init_context(tmp, name="test")
            self.assertEqual(second, [])  # No new files created.

    def test_project_yaml_contains_detected_stack(self) -> None:
        with TemporaryDirectory() as tmp:
            init_context(tmp, name="myapp", languages=["typescript"], frameworks=["React"])
            content = (Path(tmp) / ".planguard" / "project.yaml").read_text()
            self.assertIn("typescript", content)
            self.assertIn("React", content)


class PolicyEngineTests(unittest.TestCase):
    def test_no_rules_no_violations(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(name="safe", objective="test", docs_dir=docs)
            violations = check_policies(plan_dir, {"rules": []})
            self.assertEqual(violations, [])

    def test_scope_overlap_triggers_rule(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="risky",
                objective="test",
                scope_included=["migrations/"],
                docs_dir=docs,
            )
            policies = {
                "rules": [
                    {
                        "name": "migration_needs_approval",
                        "description": "Migrations require approval",
                        "scope": ["migrations/**"],
                        "action": "require_approval",
                        "risk": "high",
                    }
                ]
            }
            violations = check_policies(plan_dir, policies)
            self.assertEqual(len(violations), 1)
            self.assertEqual(violations[0]["rule"], "migration_needs_approval")

    def test_no_overlap_no_violation(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="safe",
                objective="test",
                scope_included=["src/api"],
                docs_dir=docs,
            )
            policies = {
                "rules": [
                    {
                        "name": "no_touch_billing",
                        "scope": ["src/billing/**"],
                        "action": "block",
                    }
                ]
            }
            violations = check_policies(plan_dir, policies)
            self.assertEqual(violations, [])

    def test_pattern_rule_only_triggers_on_matching_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "db.py").write_text("cursor.execute('SELECT 1')", encoding="utf-8")
            docs = root / "docs"
            plan_dir = generate_plan(
                name="sql check",
                objective="test",
                scope_included=["src"],
                docs_dir=docs,
            )
            policies = {
                "rules": [
                    {
                        "name": "no_raw_sql",
                        "scope": ["src/**/*.py"],
                        "pattern": r"execute\(",
                        "action": "block",
                    }
                ]
            }
            violations = check_policies(plan_dir, policies, file_paths=["src/db.py"], root=root)
            self.assertEqual(len(violations), 1)
            self.assertEqual(violations[0]["rule"], "no_raw_sql")


class BoundaryTests(unittest.TestCase):
    def test_boundary_violation_detected(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="boundary test",
                objective="test",
                scope_included=["migrations/001.sql"],
                docs_dir=docs,
            )
            violations = check_boundary_violations(plan_dir, ["migrations/"])
            self.assertTrue(len(violations) > 0)

    def test_no_boundary_violation(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="safe plan",
                objective="test",
                scope_included=["src/api"],
                docs_dir=docs,
            )
            violations = check_boundary_violations(plan_dir, ["migrations/"])
            self.assertEqual(violations, [])

    def test_load_boundaries_from_file(self) -> None:
        with TemporaryDirectory() as tmp:
            ctx = Path(tmp) / ".planguard"
            ctx.mkdir()
            (ctx / "boundaries.md").write_text(
                "# Boundaries\n\n## Off-limits files\n- .env\n- secrets.json\n\n## Off-limits directories\n- vendor/\n"
            )
            boundaries = load_boundaries(tmp)
            self.assertIn(".env", boundaries)
            self.assertIn("secrets.json", boundaries)
            self.assertIn("vendor/", boundaries)


class SessionLogTests(unittest.TestCase):
    def test_log_and_read_events(self) -> None:
        with TemporaryDirectory() as tmp:
            log_event("plan_created", plan="test_plan", root=tmp)
            log_event("plan_activated", plan="test_plan", root=tmp)
            log_event("plan_created", plan="other_plan", root=tmp)

            all_entries = read_log(root=tmp)
            self.assertEqual(len(all_entries), 3)

            filtered = read_log(root=tmp, plan="test_plan")
            self.assertEqual(len(filtered), 2)

    def test_log_contains_details(self) -> None:
        with TemporaryDirectory() as tmp:
            log_event("verification", plan="p1", details={"passed": True}, root=tmp)
            entries = read_log(root=tmp)
            self.assertTrue(entries[0]["passed"])

    def test_empty_log_returns_empty_list(self) -> None:
        with TemporaryDirectory() as tmp:
            entries = read_log(root=tmp)
            self.assertEqual(entries, [])


class RollbackStrategyTests(unittest.TestCase):
    def test_plan_includes_rollback_strategy(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="rollback test",
                objective="test",
                rollback_strategy="Revert migration and restore backup",
                docs_dir=docs,
            )
            data = yaml.safe_load((plan_dir / "plan.yaml").read_text())
            self.assertEqual(data["rollback_strategy"], "Revert migration and restore backup")

    def test_default_rollback_strategy(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(name="default", objective="test", docs_dir=docs)
            data = yaml.safe_load((plan_dir / "plan.yaml").read_text())
            self.assertIn("git revert", data["rollback_strategy"])
