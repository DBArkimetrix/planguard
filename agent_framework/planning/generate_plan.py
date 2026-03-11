from __future__ import annotations

from datetime import date
from pathlib import Path
import re

import yaml


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "new_plan"


def infer_allowed_paths(prompt: str) -> list[str]:
    normalized = prompt.lower()
    paths: list[str] = []

    if any(token in normalized for token in ["api", "endpoint", "route", "controller"]):
        paths.extend(["src/api", "tests/api"])
    if any(token in normalized for token in ["schema", "database", "migration", "sql", "table"]):
        paths.extend(["src/db", "migrations", "tests/db"])
    if any(token in normalized for token in ["ui", "frontend", "screen", "page"]):
        paths.extend(["src/ui", "tests/ui"])
    if any(token in normalized for token in ["service", "engine", "pricing", "logic"]):
        paths.extend(["src/services", "tests/services"])

    if not paths:
        paths.extend(["src", "tests"])

    deduped: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def generate_plan(prompt: str, docs_dir: Path | str = "docs") -> Path:
    plan_name = slugify(prompt)
    today = str(date.today())
    plan_dir = Path(docs_dir) / plan_name
    plan_dir.mkdir(parents=True, exist_ok=True)

    allowed_paths = infer_allowed_paths(prompt)

    plan = {
        "plan": {
            "name": plan_name,
            "created": today,
            "owner": "unassigned",
            "priority": "medium",
        },
        "objective": {
            "description": prompt,
        },
        "scope": {
            "included": allowed_paths,
            "excluded": ["unrelated modules", "out-of-scope architectural changes"],
        },
        "allowed_paths": allowed_paths,
        "dependencies": [],
    }

    backlog = {
        "phases": [
            {
                "phase": "analysis",
                "tasks": [
                    "analyze current implementation",
                    "identify dependencies",
                    "review collision and regression risks",
                ],
            },
            {
                "phase": "implementation",
                "tasks": [
                    "implement minimal safe change set",
                    "keep changes sequenced for robust testing",
                ],
            },
            {
                "phase": "validation",
                "tasks": [
                    "run unit tests",
                    "run regression tests",
                    "review unintended consequences",
                ],
            },
        ]
    }

    sprint_plan = {
        "sprints": [
            {
                "sprint": 1,
                "objective": "planning and analysis",
                "tasks": [
                    "finalize plan",
                    "finalize backlog",
                    "review dependencies and impact surface",
                ],
            },
            {
                "sprint": 2,
                "objective": "implementation in safe slices",
                "tasks": [
                    "implement isolated changes",
                    "validate incrementally",
                ],
            },
            {
                "sprint": 3,
                "objective": "validation and handoff",
                "tasks": [
                    "run regression checks",
                    "update progress and handoff",
                ],
            },
        ]
    }

    risk_register = {
        "risks": [
            {
                "id": "RISK-001",
                "description": "regression impact on existing behavior",
                "mitigation": "add and run targeted regression tests",
            },
            {
                "id": "RISK-002",
                "description": "changes may exceed intended scope",
                "mitigation": "restrict work to allowed_paths and review collisions",
            },
        ]
    }

    dependency_map = {
        "dependencies": [
            {
                "id": "initial_analysis",
                "depends_on": [],
                "impact": "establish current state and refine dependencies",
            },
            {
                "id": "safe_implementation",
                "depends_on": ["initial_analysis"],
                "impact": "deliver the minimal scoped change",
            },
            {
                "id": "validation_and_handoff",
                "depends_on": ["safe_implementation"],
                "impact": "confirm regressions and complete handoff",
            },
        ]
    }

    collision_detection = {
        "collision_checks": [
            {"check": "overlapping file modifications", "status": "pending"},
            {"check": "schema conflicts", "status": "pending"},
            {"check": "endpoint contract conflicts", "status": "pending"},
            {"check": "service boundary violations", "status": "pending"},
            {"check": "unintended downstream consequences", "status": "pending"},
        ]
    }

    progress = {
        "status": {
            "phase": "planning",
            "progress_percent": 0,
        },
        "completed_steps": [],
        "remaining_steps": [
            "complete analysis",
            "complete safety review",
            "complete orchestration review",
            "implement",
            "validate",
        ],
    }

    handoff = {
        "handoff": {
            "summary": f"Auto-generated starter plan for: {prompt}",
        },
        "current_state": {
            "implementation_complete": False,
            "safety_gate_passed": False,
            "orchestration_ready": False,
        },
        "next_actions": [
            "review and refine generated plan",
            "complete safety artifacts",
            "complete orchestration review before implementation",
        ],
    }

    regression_test_plan = {
        "regression_tests": [
            {
                "area": "existing functionality in allowed paths",
                "validation": "confirm no unintended behavior changes",
            }
        ]
    }

    write_yaml(plan_dir / "plan.yaml", plan)
    write_yaml(plan_dir / "backlog.yaml", backlog)
    write_yaml(plan_dir / "sprint_plan.yaml", sprint_plan)
    write_yaml(plan_dir / "risk_register.yaml", risk_register)
    write_yaml(plan_dir / "dependency_map.yaml", dependency_map)
    write_yaml(plan_dir / "collision_detection.yaml", collision_detection)
    write_yaml(plan_dir / "progress.yaml", progress)
    write_yaml(plan_dir / "handoff.yaml", handoff)
    write_yaml(plan_dir / "regression_test_plan.yaml", regression_test_plan)

    return plan_dir
