"""Validate plan structure against the consolidated format.

Each plan directory must contain:
  - plan.yaml with required sections: plan, objective, scope, phases, backlog,
    sprints, risks, dependencies
  - status.yaml with required sections: status, activation, verification,
    remaining_steps, completed_steps, handoff
"""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


REQUIRED_FILES = ["plan.yaml", "status.yaml"]

REQUIRED_PLAN_SECTIONS = [
    "plan",
    "objective",
    "scope",
    "phases",
    "backlog",
    "sprints",
    "risks",
    "dependencies",
]

REQUIRED_PLAN_FIELDS = ["name", "status", "created", "priority"]

VALID_STATUSES = {"draft", "active", "completed", "archived"}

REQUIRED_STATUS_SECTIONS = [
    "status",
    "activation",
    "verification",
    "remaining_steps",
    "completed_steps",
    "handoff",
]

REQUIRED_BACKLOG_FIELDS = ["id", "title", "type", "phase", "scope", "depends_on", "deliverables", "tests", "done_when"]
REQUIRED_SPRINT_FIELDS = ["id", "name", "goal", "backlog_items", "focus_paths", "exit_criteria"]


def discover_plan_dirs(docs_dir: Path) -> list[Path]:
    """Find all directories under docs_dir that contain a plan.yaml."""
    if not docs_dir.is_dir():
        return []
    return sorted(
        p for p in docs_dir.iterdir()
        if p.is_dir() and (p / "plan.yaml").exists()
    )


def validate_plan(plan_dir: Path) -> tuple[bool, list[str]]:
    """Validate a single plan directory. Returns (ok, messages)."""
    messages: list[str] = []
    errors = False

    # Check required files exist.
    for filename in REQUIRED_FILES:
        if not (plan_dir / filename).exists():
            messages.append(f"Missing required file: {filename}")
            errors = True

    # If plan.yaml is missing we cannot validate further.
    plan_path = plan_dir / "plan.yaml"
    if not plan_path.exists():
        return False, messages

    try:
        data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        messages.append(f"Invalid YAML in plan.yaml: {exc}")
        return False, messages

    # Check required top-level sections.
    for section in REQUIRED_PLAN_SECTIONS:
        if section not in data:
            messages.append(f"Missing required section in plan.yaml: {section}")
            errors = True

    # Check plan metadata fields.
    plan_meta = data.get("plan", {})
    if isinstance(plan_meta, dict):
        for field_name in REQUIRED_PLAN_FIELDS:
            if field_name not in plan_meta:
                messages.append(f"Missing field in plan metadata: {field_name}")
                errors = True

        status = plan_meta.get("status")
        if status and status not in VALID_STATUSES:
            messages.append(
                f"Invalid plan status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
            errors = True

    # Check scope has included paths.
    scope = data.get("scope", {})
    if isinstance(scope, dict) and not scope.get("included"):
        messages.append("Scope must include at least one path in 'included'")
        errors = True

    # Check phases are non-empty.
    phases = data.get("phases", [])
    if not phases:
        messages.append("Plan must have at least one phase")
        errors = True

    backlog = data.get("backlog", [])
    if not backlog:
        messages.append("Plan must include at least one backlog item")
        errors = True
    elif isinstance(backlog, list):
        for index, item in enumerate(backlog, start=1):
            if not isinstance(item, dict):
                messages.append(f"Backlog item {index} must be a mapping")
                errors = True
                continue
            for field_name in REQUIRED_BACKLOG_FIELDS:
                if field_name not in item:
                    messages.append(f"Backlog item {index} missing field: {field_name}")
                    errors = True

    sprints = data.get("sprints", [])
    if not sprints:
        messages.append("Plan must include at least one sprint")
        errors = True
    elif isinstance(sprints, list):
        for index, sprint in enumerate(sprints, start=1):
            if not isinstance(sprint, dict):
                messages.append(f"Sprint {index} must be a mapping")
                errors = True
                continue
            for field_name in REQUIRED_SPRINT_FIELDS:
                if field_name not in sprint:
                    messages.append(f"Sprint {index} missing field: {field_name}")
                    errors = True

    status_path = plan_dir / "status.yaml"
    if status_path.exists():
        try:
            status_data = yaml.safe_load(status_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            messages.append(f"Invalid YAML in status.yaml: {exc}")
            return False, messages

        for section in REQUIRED_STATUS_SECTIONS:
            if section not in status_data:
                messages.append(f"Missing required section in status.yaml: {section}")
                errors = True

        phase = status_data.get("status", {}).get("phase") if isinstance(status_data.get("status"), dict) else None
        if not phase:
            messages.append("status.yaml must include status.phase")
            errors = True

        activation = status_data.get("activation", {})
        if not isinstance(activation, dict):
            messages.append("status.yaml activation section must be a mapping")
            errors = True
        else:
            for field_name in ["activated_at", "git_branch", "git_head", "baseline_changed_files", "baseline_fingerprints"]:
                if field_name not in activation:
                    messages.append(f"status.yaml activation missing field: {field_name}")
                    errors = True

        verification = status_data.get("verification", {})
        if not isinstance(verification, dict):
            messages.append("status.yaml verification section must be a mapping")
            errors = True
        else:
            for field_name in ["passed", "last_run", "git_branch", "git_head", "changed_files", "fingerprints", "commands"]:
                if field_name not in verification:
                    messages.append(f"status.yaml verification missing field: {field_name}")
                    errors = True

    if not errors:
        messages.append("Valid")

    return not errors, messages


def validate_docs(docs_dir: Path | str = "docs") -> tuple[bool, list[str]]:
    """Validate all plans under a docs directory."""
    docs_path = Path(docs_dir)
    messages: list[str] = []

    if not docs_path.exists():
        messages.append("No docs directory found. Run 'agent init' to set up.")
        return True, messages

    plan_dirs = discover_plan_dirs(docs_path)
    if not plan_dirs:
        messages.append("No plans found. Run 'agent plan' to create one.")
        return True, messages

    all_ok = True
    for plan_dir in plan_dirs:
        ok, plan_messages = validate_plan(plan_dir)
        name = plan_dir.name
        if ok:
            messages.append(f"  {name}: valid")
        else:
            all_ok = False
            messages.append(f"  {name}: INVALID")
            messages.extend(f"    - {m}" for m in plan_messages)

    return all_ok, messages


def get_plan_status(plan_dir: Path) -> str | None:
    """Read the status field from a plan's plan.yaml."""
    plan_path = plan_dir / "plan.yaml"
    if not plan_path.exists():
        return None
    try:
        data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
        return data.get("plan", {}).get("status")
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    docs_dir = Path(args[0]) if args else Path("docs")
    ok, messages = validate_docs(docs_dir)
    for message in messages:
        print(message)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
