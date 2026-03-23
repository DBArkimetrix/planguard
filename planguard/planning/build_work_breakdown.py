"""Build backlog items and sprint groupings for generated plans."""

from __future__ import annotations

from math import ceil


def _classify_scope(path: str) -> str:
    normalized = path.strip().lower()
    if normalized.startswith("tests") or "/tests" in normalized:
        return "testing"
    if normalized.startswith("docs") or normalized.endswith(".md") or normalized.endswith(".rst"):
        return "documentation"
    return "implementation"


def _title_for_scope(path: str, item_type: str) -> str:
    if item_type == "testing":
        return f"Update automated coverage for {path}"
    if item_type == "documentation":
        return f"Document the change set for {path}"
    return f"Implement changes in {path}"


def _deliverables_for_scope(path: str, item_type: str) -> list[str]:
    if item_type == "testing":
        return [f"Targeted tests in {path} reflect the new behaviour"]
    if item_type == "documentation":
        return [f"Documentation in {path} explains the updated workflow or behaviour"]
    return [f"Code changes in {path} are implemented in safe, reviewable slices"]


def _tests_for_scope(path: str, item_type: str) -> list[str]:
    if item_type == "testing":
        return [f"Run the tests in or affected by {path}"]
    if item_type == "documentation":
        return [f"Review documentation accuracy for {path} against the implemented behaviour"]
    return [f"Add or update focused regression tests covering {path}"]


def build_backlog(
    scope_included: list[str],
    *,
    done_when: list[str],
    verify_commands: list[str],
) -> list[dict]:
    """Return backlog items for the generated plan."""
    implementation_items: list[dict] = []

    for index, scope_path in enumerate(scope_included, start=2):
        item_type = _classify_scope(scope_path)
        implementation_items.append({
            "id": f"BL-{index:03d}",
            "title": _title_for_scope(scope_path, item_type),
            "type": item_type,
            "phase": "implementation",
            "scope": [scope_path],
            "depends_on": ["BL-001"],
            "deliverables": _deliverables_for_scope(scope_path, item_type),
            "tests": _tests_for_scope(scope_path, item_type),
            "done_when": [f"The planned work for {scope_path} is complete"],
        })

    if not implementation_items:
        implementation_items.append({
            "id": "BL-002",
            "title": "Implement the planned change set",
            "type": "implementation",
            "phase": "implementation",
            "scope": [],
            "depends_on": ["BL-001"],
            "deliverables": ["Planned implementation is complete in safe, reviewable slices"],
            "tests": ["Add or update targeted regression coverage for the changed behaviour"],
            "done_when": ["Implementation is complete"],
        })

    validation_dependencies = [item["id"] for item in implementation_items]

    return [
        {
            "id": "BL-001",
            "title": "Analyze scope, architecture touchpoints, and test impact",
            "type": "analysis",
            "phase": "analysis",
            "scope": list(scope_included),
            "depends_on": [],
            "deliverables": [
                "Impacted modules and dependencies are identified",
                "Required tests and rollback considerations are documented",
            ],
            "tests": [
                "Identify the regression coverage that must be preserved before coding begins",
            ],
            "done_when": [
                "The implementation approach is clear",
                "The test strategy covers the affected areas",
            ],
        },
        *implementation_items,
        {
            "id": f"BL-{len(implementation_items) + 2:03d}",
            "title": "Run verification, regression checks, and handoff review",
            "type": "validation",
            "phase": "validation",
            "scope": list(scope_included),
            "depends_on": validation_dependencies,
            "deliverables": [
                "Verification commands pass",
                "Handoff notes capture any residual risk or follow-up work",
            ],
            "tests": verify_commands or ["Run the planned verification commands before completion"],
            "done_when": list(done_when),
        },
    ]


def build_sprints(backlog: list[dict]) -> list[dict]:
    """Group backlog items into small, ordered sprints."""
    if not backlog:
        return []

    analysis_items = [item for item in backlog if item.get("phase") == "analysis"]
    implementation_items = [item for item in backlog if item.get("phase") == "implementation"]
    validation_items = [item for item in backlog if item.get("phase") == "validation"]

    sprints: list[dict] = []

    if analysis_items:
        sprints.append({
            "id": "SPRINT-01",
            "name": "Discovery and test design",
            "goal": "Confirm scope, architecture impact, and required regression coverage before implementation starts.",
            "backlog_items": [item["id"] for item in analysis_items],
            "focus_paths": sorted({path for item in analysis_items for path in item.get("scope", [])}),
            "exit_criteria": analysis_items[0].get("done_when", []),
        })

    sprint_size = 2
    impl_sprint_count = max(1, ceil(len(implementation_items) / sprint_size)) if implementation_items else 0
    for idx in range(impl_sprint_count):
        chunk = implementation_items[idx * sprint_size:(idx + 1) * sprint_size]
        sprint_number = len(sprints) + 1
        sprints.append({
            "id": f"SPRINT-{sprint_number:02d}",
            "name": f"Implementation slice {idx + 1}",
            "goal": "Deliver a reviewable subset of the planned change set with matching test updates.",
            "backlog_items": [item["id"] for item in chunk],
            "focus_paths": sorted({path for item in chunk for path in item.get("scope", [])}),
            "exit_criteria": [
                criterion
                for item in chunk
                for criterion in item.get("done_when", [])
            ],
        })

    if validation_items:
        sprint_number = len(sprints) + 1
        sprints.append({
            "id": f"SPRINT-{sprint_number:02d}",
            "name": "Verification and handoff",
            "goal": "Prove the change set works, document residual risk, and prepare completion.",
            "backlog_items": [item["id"] for item in validation_items],
            "focus_paths": sorted({path for item in validation_items for path in item.get("scope", [])}),
            "exit_criteria": validation_items[0].get("done_when", []),
        })

    return sprints
