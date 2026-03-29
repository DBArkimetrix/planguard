"""Generate a consolidated plan from wizard answers or CLI flags."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import yaml

from planguard.config import (
    find_project_root_for_plan,
    get_plans_root,
    get_registry_path,
    get_status_path,
)
from planguard.planning.build_work_breakdown import build_backlog, build_sprints
from planguard.planning.templates import get_template


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
    template: str = "default",
    docs_dir: Path | str | None = None,
) -> Path:
    """Create a plan.yaml plus runtime status from the provided details.

    Returns the path to the created plan directory.
    """
    if docs_dir is None:
        docs_dir = get_plans_root()
    plan_name = slugify(name)
    today = str(date.today())
    plan_dir = Path(docs_dir) / plan_name
    plan_dir.mkdir(parents=True, exist_ok=True)
    project_root = find_project_root_for_plan(plan_dir)

    included = scope_included or ["src", "tests"]
    excluded = scope_excluded or ["unrelated modules"]
    plan_done_when = done_when or [
        "All tests pass",
        "No regressions in existing functionality",
    ]
    plan_verify_commands = verify_commands or []

    # Apply template defaults.
    tmpl = get_template(template)
    tmpl_phases = tmpl["phases"]
    tmpl_risks = tmpl["risks"]
    tmpl_test_strategy = tmpl.get("test_strategy", [
        {"area": "Existing functionality in scope paths", "validation": "Confirm no unintended behaviour changes"},
    ])
    tmpl_rollback = tmpl.get("rollback_strategy", "git revert to prior commit")

    backlog = build_backlog(
        included,
        done_when=plan_done_when,
        verify_commands=plan_verify_commands,
    )
    sprints = build_sprints(backlog)

    # Build phase dependency chain from template phases.
    phase_names = [p["name"] for p in tmpl_phases]
    dependencies = []
    for i, pname in enumerate(phase_names):
        dependencies.append({"id": pname, "depends_on": [phase_names[i - 1]] if i > 0 else []})

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
        "phases": tmpl_phases,
        "risks": risks or tmpl_risks,
        "dependencies": dependencies,
        "backlog": backlog,
        "sprints": sprints,
        "done_when": plan_done_when,
        "verify_commands": plan_verify_commands,
        "rollback_strategy": rollback_strategy or tmpl_rollback,
        "test_strategy": tmpl_test_strategy,
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
    status_path = get_status_path(plan_name, project_root)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(status_path, status_data)

    # Register in runtime state.
    _register_plan(plan_name, root=project_root)

    return plan_dir


def _register_plan(plan_name: str, root: Path | str = ".") -> None:
    """Add a plan to the active plans registry if not already present."""
    registry_path = get_registry_path(root)
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
