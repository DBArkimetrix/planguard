"""Generate a consolidated plan from wizard answers or CLI flags."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import yaml


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "new_plan"


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False), encoding="utf-8")


def generate_plan(
    *,
    name: str,
    objective: str,
    scope_included: list[str] | None = None,
    scope_excluded: list[str] | None = None,
    priority: str = "medium",
    owner: str = "unassigned",
    risks: list[dict] | None = None,
    done_when: list[str] | None = None,
    verify_commands: list[str] | None = None,
    rollback_strategy: str = "",
    docs_dir: Path | str = "docs",
) -> Path:
    """Create a plan.yaml and status.yaml from the provided details.

    Returns the path to the created plan directory.
    """
    plan_name = slugify(name)
    today = str(date.today())
    plan_dir = Path(docs_dir) / plan_name
    plan_dir.mkdir(parents=True, exist_ok=True)

    included = scope_included or ["src", "tests"]
    excluded = scope_excluded or ["unrelated modules"]

    plan_data = {
        "plan": {
            "name": plan_name,
            "status": "draft",
            "created": today,
            "owner": owner,
            "priority": priority,
        },
        "objective": objective,
        "scope": {
            "included": included,
            "excluded": excluded,
        },
        "phases": [
            {
                "name": "analysis",
                "tasks": [
                    "Analyze current implementation",
                    "Identify dependencies and risks",
                ],
            },
            {
                "name": "implementation",
                "tasks": [
                    "Implement changes in safe, testable slices",
                ],
            },
            {
                "name": "validation",
                "tasks": [
                    "Run tests and review for regressions",
                ],
            },
        ],
        "risks": risks or [
            {
                "id": "RISK-001",
                "description": "Regression impact on existing behaviour",
                "severity": "medium",
                "mitigation": "Add targeted regression tests before changing code",
            },
        ],
        "dependencies": [
            {"id": "analysis", "depends_on": []},
            {"id": "implementation", "depends_on": ["analysis"]},
            {"id": "validation", "depends_on": ["implementation"]},
        ],
        "done_when": done_when or [
            "All tests pass",
            "No regressions in existing functionality",
        ],
        "verify_commands": verify_commands or [],
        "rollback_strategy": rollback_strategy or "git revert to prior commit",
        "test_strategy": [
            {
                "area": "Existing functionality in scope paths",
                "validation": "Confirm no unintended behaviour changes",
            },
        ],
    }

    status_data = {
        "status": {
            "phase": "planning",
            "progress_percent": 0,
        },
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
        "completed_steps": [],
        "remaining_steps": [
            "Review and refine plan",
            "Run checks (planguard check)",
            "Activate plan (planguard activate)",
            "Implement",
            "Verify (planguard verify)",
            "Complete plan (planguard complete)",
        ],
        "blockers": [],
        "handoff": {
            "summary": "",
            "notes": [],
        },
    }

    write_yaml(plan_dir / "plan.yaml", plan_data)
    write_yaml(plan_dir / "status.yaml", status_data)

    # Register in active_plans.yaml
    _register_plan(plan_name, docs_dir)

    return plan_dir


def _register_plan(plan_name: str, docs_dir: Path | str = "docs") -> None:
    """Add a plan to the active plans registry if not already present."""
    registry_path = Path(docs_dir) / "planning" / "active_plans.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    if registry_path.exists():
        data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    else:
        data = {}

    plans = data.get("active_plans", [])
    existing_names = {p["name"] if isinstance(p, dict) else p for p in plans}

    if plan_name not in existing_names:
        plans.append({"name": plan_name, "status": "draft"})
        data["active_plans"] = plans
        write_yaml(registry_path, data)
