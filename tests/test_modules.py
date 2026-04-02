"""Tests for individual framework modules."""

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

import yaml

from planguard.config import get_default_plans_root, get_execution_schedule_path, get_plans_root, get_registry_path, get_status_path
from planguard.planning.detect_project import detect_project
from planguard.planning.generate_plan import generate_plan
from planguard.orchestration.build_execution_schedule import build_execution_schedule
from planguard.validation.validate_plan import validate_plan, validate_docs
from planguard.orchestration.detect_collisions import detect_collisions
from planguard.safety.compute_risk_score import compute_risk_score


class DetectProjectTests(unittest.TestCase):
    def test_default_plans_root_is_local_for_fresh_repo(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertEqual(get_plans_root(tmp), get_default_plans_root())

    def test_detects_empty_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            info = detect_project(tmp)
            self.assertTrue(info.is_empty)

    def test_detects_python_project(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n")
            (Path(tmp) / "src").mkdir()
            info = detect_project(tmp)
            self.assertIn("python", info.languages)
            self.assertIn("src", info.source_dirs)

    def test_detects_node_project(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text('{"name": "test", "dependencies": {"react": "^18"}}')
            info = detect_project(tmp)
            self.assertIn("javascript", info.languages)
            self.assertIn("React", info.frameworks)

    def test_detects_build_and_test_commands(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text('{"name": "test"}')
            info = detect_project(tmp)
            self.assertIn("npm run build", info.build_commands)
            self.assertIn("npm test", info.test_commands)

    def test_detects_python_test_commands(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "pyproject.toml").write_text('[tool.poetry]\nname = "x"\n[tool.pytest]\n')
            (Path(tmp) / "poetry.lock").write_text("")
            info = detect_project(tmp)
            self.assertTrue(any("pytest" in cmd for cmd in info.test_commands))

    def test_detects_poetry_unittest_with_test_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "pyproject.toml").write_text('[tool.poetry]\nname = "x"\n')
            (Path(tmp) / "poetry.lock").write_text("")
            (Path(tmp) / "tests").mkdir()
            info = detect_project(tmp)
            self.assertIn("poetry run python -m unittest discover -s tests", info.test_commands)

    def test_detects_existing_plans(self) -> None:
        with TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "docs" / "my_plan"
            plan_dir.mkdir(parents=True)
            (plan_dir / "plan.yaml").write_text("plan:\n  name: my_plan\n")
            self.assertEqual(get_plans_root(tmp), Path("docs"))
            info = detect_project(tmp)
            self.assertTrue(info.has_existing_plans)
            self.assertIn("my_plan", info.existing_plan_names)

    def test_detects_existing_plans_in_configured_root(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / ".planguard").mkdir()
            (Path(tmp) / ".planguard" / "config.yaml").write_text("plans_root: plans\n", encoding="utf-8")
            plan_dir = Path(tmp) / "plans" / "my_plan"
            plan_dir.mkdir(parents=True)
            (plan_dir / "plan.yaml").write_text("plan:\n  name: my_plan\n")
            info = detect_project(tmp)
            self.assertTrue(info.has_existing_plans)
            self.assertIn("my_plan", info.existing_plan_names)


class GeneratePlanTests(unittest.TestCase):
    def test_generates_plan_and_status(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="test plan",
                objective="Test the generator",
                docs_dir=docs,
            )
            self.assertTrue((plan_dir / "plan.yaml").exists())
            self.assertTrue(get_status_path("test_plan", tmp).exists())

            data = yaml.safe_load((plan_dir / "plan.yaml").read_text())
            self.assertEqual(data["plan"]["status"], "draft")
            self.assertEqual(data["objective"], "Test the generator")
            self.assertIn("done_when", data)
            self.assertIn("verify_commands", data)
            self.assertIn("backlog", data)
            self.assertIn("sprints", data)
            self.assertGreaterEqual(len(data["backlog"]), 3)
            self.assertGreaterEqual(len(data["sprints"]), 2)

    def test_generates_plan_with_done_when_and_verify(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="verified plan",
                objective="Test verification fields",
                done_when=["API returns 200", "All tests pass"],
                verify_commands=["pytest", "curl localhost:8000/health"],
                docs_dir=docs,
            )
            data = yaml.safe_load((plan_dir / "plan.yaml").read_text())
            self.assertEqual(data["done_when"], ["API returns 200", "All tests pass"])
            self.assertEqual(data["verify_commands"], ["pytest", "curl localhost:8000/health"])
            validation_item = data["backlog"][-1]
            self.assertEqual(validation_item["tests"], ["pytest", "curl localhost:8000/health"])
            self.assertEqual(validation_item["done_when"], ["API returns 200", "All tests pass"])

    def test_generates_scope_backlog_items(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="scope breakdown",
                objective="Test backlog structure",
                scope_included=["src/api", "tests/api", "README.md"],
                docs_dir=docs,
            )
            data = yaml.safe_load((plan_dir / "plan.yaml").read_text())
            titles = [item["title"] for item in data["backlog"]]
            self.assertTrue(any("src/api" in title for title in titles))
            self.assertTrue(any("tests/api" in title for title in titles))
            self.assertTrue(any("README.md" in title for title in titles))
            implementation_sprints = [s for s in data["sprints"] if "Implementation slice" in s["name"]]
            self.assertTrue(implementation_sprints)

    def test_registers_plan_in_active_plans(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            generate_plan(name="registered plan", objective="test", docs_dir=docs)
            registry = yaml.safe_load(get_registry_path(tmp).read_text())
            names = [p["name"] for p in registry["active_plans"]]
            self.assertIn("registered_plan", names)

    def test_build_execution_schedule_uses_configured_root_by_default(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".planguard").mkdir()
            (root / ".planguard" / "config.yaml").write_text("plans_root: plans\n", encoding="utf-8")
            plans_dir = root / "plans"
            generate_plan(name="scheduled plan", objective="test", docs_dir=plans_dir)

            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                schedule = build_execution_schedule()
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(schedule, {"phase_medium": ["scheduled_plan"]})
            self.assertTrue(get_execution_schedule_path(root).parent.exists())


class ValidatePlanTests(unittest.TestCase):
    def test_valid_plan_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(name="valid", objective="test", docs_dir=docs)
            ok, messages = validate_plan(plan_dir)
            self.assertTrue(ok, messages)

    def test_missing_status_yaml_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "incomplete"
            plan_dir.mkdir()
            (plan_dir / "plan.yaml").write_text(
                yaml.safe_dump({
                    "plan": {"name": "incomplete", "status": "draft", "created": "2024-01-01", "priority": "low"},
                    "objective": "test",
                    "scope": {"included": ["src"]},
                    "phases": [{"name": "do it", "tasks": ["task"]}],
                    "backlog": [],
                    "sprints": [],
                    "risks": [],
                    "dependencies": [],
                })
            )
            ok, messages = validate_plan(plan_dir)
            self.assertFalse(ok)
            self.assertTrue(any(".planguard/state/plans/<plan_name>/status.yaml" in m for m in messages))

    def test_invalid_status_value_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "bad_status"
            plan_dir.mkdir()
            (plan_dir / "plan.yaml").write_text(
                yaml.safe_dump({
                    "plan": {"name": "bad", "status": "invalid_value", "created": "2024-01-01", "priority": "low"},
                    "objective": "test",
                    "scope": {"included": ["src"]},
                    "phases": [{"name": "x", "tasks": ["y"]}],
                    "backlog": [],
                    "sprints": [],
                    "risks": [],
                    "dependencies": [],
                })
            )
            status_path = get_status_path("bad_status", tmp)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("status:\n  phase: planning\n")
            ok, messages = validate_plan(plan_dir)
            self.assertFalse(ok)
            self.assertTrue(any("Invalid plan status" in m for m in messages))

    def test_missing_status_sections_fail(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(name="status check", objective="test", docs_dir=docs)
            get_status_path("status_check", tmp).write_text("status:\n  phase: planning\n", encoding="utf-8")
            ok, messages = validate_plan(plan_dir)
            self.assertFalse(ok)
            self.assertTrue(any("remaining_steps" in m for m in messages))

    def test_missing_backlog_or_sprints_fail(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(name="shape check", objective="test", docs_dir=docs)
            data = yaml.safe_load((plan_dir / "plan.yaml").read_text())
            del data["backlog"]
            del data["sprints"]
            (plan_dir / "plan.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
            ok, messages = validate_plan(plan_dir)
            self.assertFalse(ok)
            self.assertTrue(any("backlog" in m for m in messages))
            self.assertTrue(any("sprints" in m for m in messages))

    def test_incomplete_backlog_item_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(name="backlog fields", objective="test", docs_dir=docs)
            data = yaml.safe_load((plan_dir / "plan.yaml").read_text())
            data["backlog"][0].pop("tests")
            (plan_dir / "plan.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
            ok, messages = validate_plan(plan_dir)
            self.assertFalse(ok)
            self.assertTrue(any("Backlog item 1 missing field: tests" in m for m in messages))


class CollisionDetectionTests(unittest.TestCase):
    def test_no_collisions_between_disjoint_plans(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            generate_plan(name="plan a", objective="a", scope_included=["src/api"], docs_dir=docs)
            generate_plan(name="plan b", objective="b", scope_included=["src/ui"], docs_dir=docs)
            collisions = detect_collisions(str(docs))
            self.assertEqual(collisions, [])

    def test_detects_overlapping_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            generate_plan(name="plan x", objective="x", scope_included=["src/shared"], docs_dir=docs)
            generate_plan(name="plan y", objective="y", scope_included=["src/shared"], docs_dir=docs)
            collisions = detect_collisions(str(docs))
            self.assertEqual(len(collisions), 1)
            self.assertIn("src/shared", collisions[0]["overlap"])

    def test_detects_nested_path_collisions(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            generate_plan(name="plan parent", objective="x", scope_included=["src"], docs_dir=docs)
            generate_plan(name="plan child", objective="y", scope_included=["src/api"], docs_dir=docs)
            collisions = detect_collisions(str(docs))
            self.assertEqual(len(collisions), 1)
            self.assertTrue(any("src" in item and "src/api" in item for item in collisions[0]["overlap"]))

    def test_completed_plans_excluded(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(name="done", objective="done", scope_included=["src"], docs_dir=docs)
            generate_plan(name="new", objective="new", scope_included=["src"], docs_dir=docs)

            # Mark first plan as completed.
            data = yaml.safe_load((plan_dir / "plan.yaml").read_text())
            data["plan"]["status"] = "completed"
            (plan_dir / "plan.yaml").write_text(yaml.safe_dump(data))

            collisions = detect_collisions(str(docs))
            self.assertEqual(collisions, [])


class RiskScoreTests(unittest.TestCase):
    def test_score_from_plan_risks(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="risky",
                objective="test",
                risks=[
                    {"id": "R1", "description": "high risk", "severity": "high", "mitigation": "careful"},
                    {"id": "R2", "description": "low risk", "severity": "low", "mitigation": "ok"},
                ],
                docs_dir=docs,
            )
            total, status, details = compute_risk_score(plan_dir)
            self.assertEqual(total, 4)  # high=3 + low=1
            self.assertEqual(status, "pass")

    def test_blocked_when_exceeds_threshold(self) -> None:
        with TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            plan_dir = generate_plan(
                name="very risky",
                objective="test",
                risks=[
                    {"id": "R1", "severity": "critical", "description": "a", "mitigation": "x"},
                    {"id": "R2", "severity": "critical", "description": "b", "mitigation": "y"},
                ],
                docs_dir=docs,
            )
            total, status, _ = compute_risk_score(plan_dir, threshold=6)
            self.assertEqual(total, 10)  # critical=5 * 2
            self.assertEqual(status, "blocked")
