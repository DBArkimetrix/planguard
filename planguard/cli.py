"""CLI for PlanGuard.

Provides an interactive wizard-driven workflow for setting up governance,
creating plans, running checks, and managing plan lifecycle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import warnings

import typer
import yaml
from rich import print
from rich.panel import Panel
from rich.table import Table

from planguard import __version__
from planguard.config import (
    find_project_root_for_plan,
    get_default_plans_root,
    get_log_path,
    get_plans_root,
    get_registry_path,
    get_state_root,
    get_status_path,
    has_legacy_docs_plans,
    load_config,
)
from planguard.context.project_context import (
    has_context,
    init_context,
    load_boundaries,
    load_policies,
)
from planguard.context.session_log import log_event, read_log
from planguard.orchestration.detect_collisions import detect_collisions
from planguard.orchestration.plan_graph import build_plan_graph, analyze_graph
from planguard.pathspec import path_matches
from planguard.planning.detect_project import detect_project
from planguard.planning.generate_plan import generate_plan
from planguard.safety.check_policies import check_boundary_violations, check_policies
from planguard.safety.compute_risk_score import compute_risk_score
from planguard.safety.git_state import (
    build_fingerprints,
    detect_git_renames,
    get_git_snapshot,
    resolve_renames,
)
from planguard.safety.guard import run_guard
from planguard.validation.validate_plan import (
    discover_plan_dirs,
    format_yaml_error,
    validate_plan,
    validate_docs,
)

# Windows-safe symbols — Rich handles encoding, but we avoid raw Unicode
# in case output is piped or the console codepage is limited.
_PASS = "[green]  [OK][/green]"
_FAIL = "[red]  [FAIL][/red]"


app = typer.Typer(
    help="PlanGuard — govern how AI agents make changes in your project.",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRAMEWORK_MARKER = "<!-- agent-engineering-framework -->"
_IGNORE_BLOCK_HEADER = "# PlanGuard local artifacts"
_STATE_IGNORE_ENTRY = ".planguard/state/"
_VALID_PLAN_STATUSES = {"draft", "active", "suspended", "completed", "archived"}
_LEGACY_STATUS_MAP = {
    "placeholder": "suspended",
    "deferred": "suspended",
}
_TERMINAL_PLAN_STATUSES = {"completed", "archived"}
_DEFAULT_REMAINING_STEPS = [
    "Review and refine plan",
    "Run checks (planguard check)",
    "Activate plan (planguard activate)",
    "Implement",
    "Verify (planguard verify)",
    "Complete plan (planguard complete)",
]
_VERBOSE = False
_KNOWN_WARNING_FILTERS = [
    (DeprecationWarning, r"'BaseCommand' is deprecated and will be removed in Click 9\.0\."),
    (DeprecationWarning, r"'parser\.split_arg_string' is deprecated and will be removed in Click 9\.0\."),
    (DeprecationWarning, r"pkg_resources is deprecated as an API\."),
    (UserWarning, r"pkg_resources is deprecated as an API\."),
]


def _configure_warning_filters() -> None:
    """Suppress known third-party warning noise during normal CLI usage."""
    for category, message in _KNOWN_WARNING_FILTERS:
        warnings.filterwarnings("ignore", message=message, category=category)


_configure_warning_filters()


def _version_callback(value: bool) -> None:
    if value:
        print(__version__)
        raise typer.Exit()


@app.callback()
def app_callback(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed PlanGuard version and exit.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show full tracebacks for unexpected internal errors.",
    ),
) -> None:
    """PlanGuard commands."""
    global _VERBOSE
    _VERBOSE = verbose


def _build_workflow_section(info: "ProjectInfo | None" = None) -> str:
    """Generate the AGENTS.md workflow section, tailored to the detected project."""
    from planguard.planning.detect_project import ProjectInfo

    lines = [
        _FRAMEWORK_MARKER,
        "",
        "## Agent Engineering Framework",
        "",
        "This repository uses a documentation-first workflow for AI agent work.",
        "",
    ]

    # Commands section — only if we detected something.
    if info and (info.build_commands or info.test_commands or info.lint_commands):
        lines.append("### Commands")
        lines.append("")
        if info.build_commands:
            lines.append("Build:")
            for cmd in info.build_commands:
                lines.append(f"  {cmd}")
            lines.append("")
        if info.test_commands:
            lines.append("Test:")
            for cmd in info.test_commands:
                lines.append(f"  {cmd}")
            lines.append("")
        if info.lint_commands:
            lines.append("Lint:")
            for cmd in info.lint_commands:
                lines.append(f"  {cmd}")
            lines.append("")

    lines.extend([
        "### Workflow",
        "",
        "PLAN -> CHECK -> ACTIVATE -> IMPLEMENT -> COMPLETE",
        "",
        "For non-trivial changes (new features, refactors, multi-file edits), agents must:",
        "",
        "1. Create a plan: `planguard plan`",
        "2. Run checks: `planguard check`",
        "3. Activate the plan: `planguard activate <plan_name>`",
        "4. Only then begin implementation",
        "",
        "For small changes (typos, single-line fixes, formatting, config tweaks), agents may proceed directly without a plan.",
        "However, database and schema changes are never small — even adding a single field requires a plan.",
        "When in doubt, run `planguard guard` to check.",
        "",
        "After implementation, agents must:",
        "",
        "1. Run verification: `planguard verify <plan_name>`",
        "2. Update runtime status and handoff notes",
        "3. Mark the plan complete: `planguard complete <plan_name>`",
        "",
        "Useful variations:",
        "",
        "- Use `planguard plan --template <name>` for docs-only, refactor, schema-change, and service-integration work",
        "- Use `planguard suspend <plan_name>` / `planguard resume <plan_name>` when overlapping work needs to pause safely",
        "",
        "### Rules",
        "",
        "- Never implement without an active plan",
        "- Never skip the check step",
        "- Never modify files outside the plan's declared scope",
        "- Always document risks and test strategy before coding",
        "- Never complete a plan without a passing verification run",
        "- Update handoff notes when the work is done",
        "",
        "### Best Practices",
        "",
        "- Read existing code before proposing changes",
        "- Write or update tests for every change",
        "- Run the test suite and confirm it passes before marking work complete",
        "- Keep changes small, scoped, and independently verifiable",
        "- Commit with descriptive messages that explain why, not just what",
        "- If something breaks, fix it before moving on",
        "",
    ])

    return "\n".join(lines)


def _docs_dir() -> Path:
    return get_plans_root()


def _replace_framework_section(existing: str, workflow_section: str) -> str:
    """Replace the managed framework section while preserving user content."""
    prefix, marker, _ = existing.partition(_FRAMEWORK_MARKER)
    if not marker:
        return existing.rstrip() + "\n\n" + workflow_section
    prefix = prefix.rstrip()
    if not prefix:
        return workflow_section + "\n"
    return prefix + "\n\n" + workflow_section + "\n"


def _ensure_plan_storage(base: Path, plans_root: Path) -> list[Path]:
    created: list[Path] = []
    plan_root = base / plans_root
    if not plan_root.exists():
        plan_root.mkdir(parents=True, exist_ok=True)
        created.append(plan_root)
    return created


def _ensure_local_storage_ignored(base: Path, plans_root: Path) -> list[Path]:
    """Ensure local PlanGuard plans and runtime state stay out of commits."""
    plan_ignore_entry = str(plans_root).replace("\\", "/").rstrip("/") + "/"
    ignore_entries = [
        plan_ignore_entry,
        _STATE_IGNORE_ENTRY,
    ]
    gitignore_path = base / ".gitignore"
    if gitignore_path.exists():
        lines = gitignore_path.read_text(encoding="utf-8-sig").splitlines()
    else:
        lines = []

    if all(entry in lines for entry in ignore_entries):
        return []

    updated = list(lines)
    if updated and updated[-1] != "":
        updated.append("")
    if _IGNORE_BLOCK_HEADER not in updated:
        updated.append(_IGNORE_BLOCK_HEADER)
    for entry in ignore_entries:
        if entry not in updated:
            updated.append(entry)

    gitignore_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
    return [gitignore_path]


def _ensure_runtime_state(base: Path) -> list[Path]:
    created: list[Path] = []
    state_root = get_state_root(base)
    for path in [state_root, state_root / "plans"]:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)

    registry = get_registry_path(base)
    if not registry.exists():
        legacy_candidates = [
            base / "docs" / "planning" / "active_plans.yaml",
            base / get_plans_root(base) / "planning" / "active_plans.yaml",
        ]
        for legacy_registry in legacy_candidates:
            if legacy_registry.exists():
                registry.write_text(legacy_registry.read_text(encoding="utf-8"), encoding="utf-8")
                break
        else:
            registry.write_text("active_plans: []\n", encoding="utf-8")
        created.append(registry)
    return created


def _migrate_legacy_runtime_state(base: Path, plan_dirs: list[Path]) -> list[str]:
    migrated: list[str] = []

    registry = get_registry_path(base)
    legacy_registry_candidates = [
        base / "docs" / "planning" / "active_plans.yaml",
        base / get_plans_root(base) / "planning" / "active_plans.yaml",
    ]
    for legacy_registry in legacy_registry_candidates:
        if not legacy_registry.exists() or legacy_registry == registry:
            continue
        if not registry.exists():
            registry.parent.mkdir(parents=True, exist_ok=True)
            legacy_registry.rename(registry)
            migrated.append(f"{legacy_registry.relative_to(base)} -> {registry.relative_to(base)}")
        else:
            legacy_registry.unlink()
            migrated.append(f"{legacy_registry.relative_to(base)} removed")
        break

    for plan_dir in plan_dirs:
        legacy_status = plan_dir / "status.yaml"
        if not legacy_status.exists():
            continue
        runtime_status = get_status_path(plan_dir.name, base)
        if runtime_status.exists():
            continue
        runtime_status.parent.mkdir(parents=True, exist_ok=True)
        legacy_status.rename(runtime_status)
        migrated.append(f"{legacy_status.relative_to(base)} -> {runtime_status.relative_to(base)}")

    legacy_log = base / ".planguard" / "log.jsonl"
    runtime_log = get_log_path(base)
    if legacy_log.exists():
        if not runtime_log.exists():
            runtime_log.parent.mkdir(parents=True, exist_ok=True)
            legacy_log.rename(runtime_log)
            migrated.append(f"{legacy_log.relative_to(base)} -> {runtime_log.relative_to(base)}")
        else:
            legacy_log.unlink()
            migrated.append(f"{legacy_log.relative_to(base)} removed")

    return migrated


def _write_config(base: Path, *, plans_root: str) -> None:
    config_dir = base / ".planguard"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    data = load_config(base) if config_path.exists() else {}
    data["plans_root"] = plans_root
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _clear_default_plans_root_config(base: Path) -> None:
    """Remove plans_root from config when the repo uses the built-in default."""
    config_path = base / ".planguard" / "config.yaml"
    if not config_path.exists():
        return
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return
    if not isinstance(data, dict) or "plans_root" not in data:
        return
    data.pop("plans_root", None)
    if data:
        config_path.write_text(
            yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    else:
        config_path.unlink()


def _read_plan_yaml(plan_dir: Path) -> dict:
    plan_path = plan_dir / "plan.yaml"
    if not plan_path.exists():
        return {}
    return yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}


def _write_plan_yaml(plan_dir: Path, data: dict) -> None:
    (plan_dir / "plan.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _read_status_yaml(plan_dir: Path) -> dict:
    root = find_project_root_for_plan(plan_dir)
    status_path = get_status_path(plan_dir.name, root)
    if not status_path.exists():
        legacy_path = plan_dir / "status.yaml"
        if not legacy_path.exists():
            return {}
        status_path = legacy_path
    return yaml.safe_load(status_path.read_text(encoding="utf-8")) or {}


def _write_status_yaml(plan_dir: Path, data: dict) -> None:
    root = find_project_root_for_plan(plan_dir)
    status_path = get_status_path(plan_dir.name, root)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _safe_read_plan_yaml(plan_dir: Path) -> tuple[dict | None, str | None]:
    try:
        return _read_plan_yaml(plan_dir), None
    except yaml.YAMLError as exc:
        return None, format_yaml_error(plan_dir / "plan.yaml", exc)
    except OSError as exc:
        return None, f"{plan_dir / 'plan.yaml'}: {exc}"


def _safe_read_status_yaml(plan_dir: Path) -> tuple[dict | None, str | None]:
    root = find_project_root_for_plan(plan_dir)
    status_path = get_status_path(plan_dir.name, root)
    if not status_path.exists():
        legacy_path = plan_dir / "status.yaml"
        if legacy_path.exists():
            status_path = legacy_path
    try:
        return _read_status_yaml(plan_dir), None
    except yaml.YAMLError as exc:
        return None, format_yaml_error(status_path, exc)
    except OSError as exc:
        return None, f"{status_path}: {exc}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_string_list(value) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped


def _phase_for_status(status: str) -> str:
    return {
        "draft": "planning",
        "active": "implementation",
        "suspended": "suspended",
        "completed": "completed",
        "archived": "archived",
    }.get(status, "planning")


def _progress_for_status(status: str) -> int:
    return {
        "draft": 0,
        "active": 25,
        "suspended": 25,
        "completed": 100,
        "archived": 100,
    }.get(status, 0)


def _infer_scope_paths(data: dict, fallback_scope: str) -> tuple[list[str], bool]:
    inferred: list[str] = []

    scope = data.get("scope", {})
    if isinstance(scope, dict):
        inferred.extend(_coerce_string_list(scope.get("included")))
    else:
        inferred.extend(_coerce_string_list(scope))

    backlog = data.get("backlog", [])
    if isinstance(backlog, list):
        for item in backlog:
            if isinstance(item, dict):
                inferred.extend(_coerce_string_list(item.get("scope")))

    sprints = data.get("sprints", [])
    if isinstance(sprints, list):
        for sprint in sprints:
            if isinstance(sprint, dict):
                inferred.extend(_coerce_string_list(sprint.get("focus_paths")))

    normalized = _dedupe_preserving_order(inferred)
    if normalized:
        return normalized, False
    return [fallback_scope], True


def _normalize_phases(phases, backlog: list[dict], *, needs_review: bool) -> list[dict]:
    normalized: list[dict] = []
    if isinstance(phases, list):
        for index, phase in enumerate(phases, start=1):
            if not isinstance(phase, dict):
                continue
            name = str(phase.get("name") or f"phase_{index}").strip() or f"phase_{index}"
            tasks = _coerce_string_list(phase.get("tasks"))
            if not tasks:
                tasks = ["Review migrated legacy plan content"]
            normalized.append({
                "name": name,
                "tasks": tasks,
            })

    if not normalized:
        phase_names = _dedupe_preserving_order([
            str(item.get("phase", "")).strip()
            for item in backlog
            if isinstance(item, dict) and str(item.get("phase", "")).strip()
        ])
        normalized = [{"name": name, "tasks": ["Review migrated legacy plan content"]} for name in phase_names]

    if not normalized:
        task = "Review migrated placeholder content before resuming execution" if needs_review else "Review migrated legacy plan content"
        normalized = [{"name": "legacy_review", "tasks": [task]}]

    return normalized


def _normalize_backlog(
    backlog,
    *,
    included_scope: list[str],
    default_phase: str,
    needs_review: bool,
) -> list[dict]:
    normalized: list[dict] = []
    if isinstance(backlog, list):
        for index, item in enumerate(backlog, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or f"Legacy backlog item {index}").strip() or f"Legacy backlog item {index}"
            deliverables = _coerce_string_list(item.get("deliverables")) or [title]
            done_when = _coerce_string_list(item.get("done_when")) or [f"{title} is preserved in the migrated plan"]
            normalized.append({
                "id": str(item.get("id") or f"LEGACY-{index:03d}"),
                "title": title,
                "type": str(item.get("type") or "task"),
                "phase": str(item.get("phase") or default_phase),
                "scope": _coerce_string_list(item.get("scope")) or list(included_scope),
                "depends_on": _coerce_string_list(item.get("depends_on")),
                "deliverables": deliverables,
                "tests": _coerce_string_list(item.get("tests")),
                "done_when": done_when,
            })

    if normalized:
        return normalized

    title = "Review migrated placeholder contents" if needs_review else "Review migrated legacy plan contents"
    done_when = (
        ["The plan has concrete backlog, sprint, and verification details before execution resumes"]
        if needs_review
        else ["The migrated plan content has been reviewed and preserved"]
    )
    return [{
        "id": "LEGACY-REVIEW",
        "title": title,
        "type": "documentation",
        "phase": default_phase,
        "scope": list(included_scope),
        "depends_on": [],
        "deliverables": ["Legacy plan content is preserved for follow-up review"],
        "tests": ["Review migrated content and add concrete verification steps before resuming"],
        "done_when": done_when,
    }]


def _normalize_sprints(
    sprints,
    *,
    backlog: list[dict],
    included_scope: list[str],
    needs_review: bool,
) -> list[dict]:
    backlog_by_id = {item["id"]: item for item in backlog}
    normalized: list[dict] = []
    if isinstance(sprints, list):
        for index, sprint in enumerate(sprints, start=1):
            if not isinstance(sprint, dict):
                continue
            backlog_items = _coerce_string_list(sprint.get("backlog_items"))
            if not backlog_items:
                backlog_items = [item["id"] for item in backlog]

            focus_paths = _coerce_string_list(sprint.get("focus_paths"))
            if not focus_paths:
                for backlog_id in backlog_items:
                    focus_paths.extend(_coerce_string_list(backlog_by_id.get(backlog_id, {}).get("scope")))
                focus_paths = _dedupe_preserving_order(focus_paths) or list(included_scope)

            exit_criteria = _coerce_string_list(sprint.get("exit_criteria"))
            if not exit_criteria:
                for backlog_id in backlog_items:
                    exit_criteria.extend(_coerce_string_list(backlog_by_id.get(backlog_id, {}).get("done_when")))
                exit_criteria = _dedupe_preserving_order(exit_criteria) or ["The sprint goals are reviewed"]

            normalized.append({
                "id": str(sprint.get("id") or f"SPRINT-{index:02d}"),
                "name": str(sprint.get("name") or f"Legacy Sprint {index}"),
                "goal": str(sprint.get("goal") or "Review migrated legacy work"),
                "backlog_items": backlog_items,
                "focus_paths": focus_paths,
                "exit_criteria": exit_criteria,
            })

    if normalized:
        return normalized

    goal = "Review migrated placeholder plan before resuming execution" if needs_review else "Review migrated legacy plan"
    exit_criteria = _dedupe_preserving_order([
        criterion
        for item in backlog
        for criterion in _coerce_string_list(item.get("done_when"))
    ]) or ["The migrated plan has been reviewed"]
    return [{
        "id": "SPRINT-LEGACY",
        "name": "Legacy review",
        "goal": goal,
        "backlog_items": [item["id"] for item in backlog],
        "focus_paths": list(included_scope),
        "exit_criteria": exit_criteria,
    }]


def _normalize_status_data(status_data, *, plan_status: str) -> dict:
    if not isinstance(status_data, dict):
        status_data = {}

    status_section = status_data.get("status")
    if not isinstance(status_section, dict):
        status_section = {}
    expected_phase = _phase_for_status(plan_status)
    if not status_section.get("phase") or plan_status in {"active", "suspended", "completed", "archived"}:
        status_section["phase"] = expected_phase
    current_progress = status_section.get("progress_percent", 0)
    try:
        current_progress = int(current_progress)
    except (TypeError, ValueError):
        current_progress = 0
    status_section["progress_percent"] = max(current_progress, _progress_for_status(plan_status))
    status_data["status"] = status_section

    activation = status_data.get("activation")
    if not isinstance(activation, dict):
        activation = {}
    activation.setdefault("activated_at", "")
    activation.setdefault("git_branch", "")
    activation.setdefault("git_head", "")
    activation.setdefault("baseline_changed_files", [])
    activation.setdefault("baseline_fingerprints", {})
    status_data["activation"] = activation

    verification = status_data.get("verification")
    if not isinstance(verification, dict):
        verification = {}
    verification.setdefault("passed", False)
    verification.setdefault("last_run", "")
    verification.setdefault("git_branch", "")
    verification.setdefault("git_head", "")
    verification.setdefault("changed_files", [])
    verification.setdefault("fingerprints", {})
    verification.setdefault("commands", [])
    status_data["verification"] = verification

    completed_steps = status_data.get("completed_steps")
    status_data["completed_steps"] = completed_steps if isinstance(completed_steps, list) else []

    remaining_steps = status_data.get("remaining_steps")
    if not isinstance(remaining_steps, list):
        remaining_steps = [] if plan_status in _TERMINAL_PLAN_STATUSES else list(_DEFAULT_REMAINING_STEPS)
    status_data["remaining_steps"] = remaining_steps

    blockers = status_data.get("blockers")
    status_data["blockers"] = blockers if isinstance(blockers, list) else []

    handoff = status_data.get("handoff")
    if not isinstance(handoff, dict):
        handoff = {}
    handoff.setdefault("summary", "")
    notes = handoff.get("notes")
    handoff["notes"] = notes if isinstance(notes, list) else _coerce_string_list(notes)
    status_data["handoff"] = handoff

    return status_data


def _sync_registry_status(base: Path, plan_name: str, status: str) -> None:
    registry_path = get_registry_path(base)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except Exception:
        registry = {}

    active_plans = registry.get("active_plans", [])
    if not isinstance(active_plans, list):
        active_plans = []

    for entry in active_plans:
        if isinstance(entry, dict) and entry.get("name") == plan_name:
            entry["status"] = status
            break
    else:
        active_plans.append({"name": plan_name, "status": status})

    registry["active_plans"] = active_plans
    registry_path.write_text(
        yaml.safe_dump(registry, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _normalize_legacy_plan(plan_dir: Path, base: Path) -> dict:
    summary = {
        "name": plan_dir.name,
        "normalized": False,
        "suspended": False,
        "manual_review": [],
        "notes": [],
    }
    plan_path = plan_dir / "plan.yaml"

    try:
        data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        summary["manual_review"].append(f"plan.yaml parse error: {format_yaml_error(plan_path, exc)}")
        return summary

    if not isinstance(data, dict):
        summary["manual_review"].append(f"plan.yaml must contain a mapping: {plan_path}")
        return summary

    original_dump = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    plan_meta = data.get("plan")
    if not isinstance(plan_meta, dict):
        plan_meta = {}
    original_status = str(plan_meta.get("status") or data.get("status") or "draft").strip().lower() or "draft"
    normalized_status = _LEGACY_STATUS_MAP.get(original_status, original_status)
    if normalized_status not in _VALID_PLAN_STATUSES:
        summary["notes"].append(f"unknown legacy status '{original_status}' normalized to draft")
        normalized_status = "draft"
    if normalized_status != original_status:
        summary["notes"].append(f"status {original_status} -> {normalized_status}")
        summary["suspended"] = normalized_status == "suspended"

    fallback_scope = str((plan_dir / "plan.yaml").relative_to(base)).replace("\\", "/")
    included_scope, used_fallback_scope = _infer_scope_paths(data, fallback_scope)
    needs_review = normalized_status == "suspended"
    if used_fallback_scope:
        needs_review = True
        summary["notes"].append("scope could not be inferred; restricted to the migrated plan file until manual review")

    phases = _normalize_phases(data.get("phases"), data.get("backlog") if isinstance(data.get("backlog"), list) else [], needs_review=needs_review)
    default_phase = phases[0]["name"]
    backlog = _normalize_backlog(
        data.get("backlog"),
        included_scope=included_scope,
        default_phase=default_phase,
        needs_review=needs_review,
    )
    sprints = _normalize_sprints(
        data.get("sprints"),
        backlog=backlog,
        included_scope=included_scope,
        needs_review=needs_review,
    )

    if needs_review and normalized_status != "suspended":
        normalized_status = "suspended"
        summary["suspended"] = True
        summary["notes"].append("status changed to suspended until the migrated plan is reviewed")

    plan_meta.setdefault("name", plan_dir.name)
    plan_meta["status"] = normalized_status
    plan_meta.setdefault("created", _now_iso()[:10])
    plan_meta.setdefault("priority", "medium")
    plan_meta.setdefault("owner", "unassigned")
    data["plan"] = plan_meta
    data["objective"] = data.get("objective") or plan_dir.name.replace("_", " ")
    data["scope"] = {
        "included": included_scope,
        "excluded": _coerce_string_list(data.get("scope", {}).get("excluded") if isinstance(data.get("scope"), dict) else []),
    }
    data["phases"] = phases
    data["backlog"] = backlog
    data["sprints"] = sprints
    data["risks"] = data.get("risks") if isinstance(data.get("risks"), list) else []
    data["dependencies"] = data.get("dependencies") if isinstance(data.get("dependencies"), list) else []

    migration = data.get("migration")
    if not isinstance(migration, dict):
        migration = {}
    migration["upgraded_from_legacy"] = True
    migration.setdefault("normalized_at", _now_iso())
    if summary["notes"]:
        migration["notes"] = _dedupe_preserving_order(_coerce_string_list(migration.get("notes")) + summary["notes"])
    if needs_review:
        migration["needs_manual_review"] = True
    data["migration"] = migration

    normalized_dump = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    if normalized_dump != original_dump:
        _write_plan_yaml(plan_dir, data)
        summary["normalized"] = True

    _sync_registry_status(base, plan_dir.name, normalized_status)

    status_path = get_status_path(plan_dir.name, base)
    if not status_path.exists():
        legacy_status = plan_dir / "status.yaml"
        if legacy_status.exists():
            status_path = legacy_status

    status_data: dict = {}
    if status_path.exists():
        try:
            status_data = yaml.safe_load(status_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            summary["manual_review"].append(f"status.yaml parse error: {format_yaml_error(status_path, exc)}")
            return summary

    existing_status_dump = yaml.safe_dump(status_data, sort_keys=False, default_flow_style=False)
    normalized_status_data = _normalize_status_data(status_data, plan_status=normalized_status)
    normalized_status_dump = yaml.safe_dump(normalized_status_data, sort_keys=False, default_flow_style=False)
    if normalized_status_dump != existing_status_dump or not status_path.exists():
        _write_status_yaml(plan_dir, normalized_status_data)
        summary["normalized"] = True

    return summary


def _capture_git_state(scope_paths: list[str] | None = None) -> dict:
    snapshot = get_git_snapshot(scope_paths=scope_paths)
    return {
        "is_git_repo": snapshot.get("is_git_repo", False),
        "git_branch": snapshot.get("branch", ""),
        "git_head": snapshot.get("head", ""),
        "changed_files": snapshot.get("changed_files", []),
        "fingerprints": snapshot.get("fingerprints", {}),
        "context_changed_files": snapshot.get("context_changed_files", []),
        "context_fingerprints": snapshot.get("context_fingerprints", {}),
        "captured_at": _now_iso(),
    }


def _plan_bookkeeping_files(plan_dir: Path) -> set[str]:
    root = str(_docs_dir())
    repo_root = find_project_root_for_plan(plan_dir)
    return {
        f"{root}/{plan_dir.name}",
        f"{root}/{plan_dir.name}/plan.yaml",
        str(get_status_path(plan_dir.name, repo_root).relative_to(repo_root)),
        str(get_registry_path(repo_root).relative_to(repo_root)),
        str(get_log_path(repo_root).relative_to(repo_root)),
        ".planguard/log.jsonl",
        "docs/planning/active_plans.yaml",
    }


def _files_changed_since_activation(plan_dir: Path, current_snapshot: dict) -> list[str]:
    status_data = _read_status_yaml(plan_dir)
    activation = status_data.get("activation", {})
    baseline = activation.get("baseline_fingerprints", {}) if isinstance(activation, dict) else {}
    if not isinstance(activation, dict) or not activation.get("activated_at"):
        return []
    if not baseline:
        return sorted(set(current_snapshot.get("changed_files", [])))

    # Apply declared renames so intentional moves don't show as changes.
    plan_data = _read_plan_yaml(plan_dir)
    renames = plan_data.get("renames", [])
    if renames:
        baseline = resolve_renames(baseline, renames)

    current_fingerprints = current_snapshot.get("fingerprints", {})
    rename_targets_by_source = {
        rename.get("from", ""): rename.get("to", "")
        for rename in renames
        if rename.get("from") and rename.get("to")
    }
    ignored_sources = {
        source
        for source, target in rename_targets_by_source.items()
        if current_fingerprints.get(source) == "MISSING" and target in current_fingerprints
    }

    changed: list[str] = []
    for path in current_snapshot.get("changed_files", []):
        if path in ignored_sources:
            continue
        current_fingerprint = current_fingerprints.get(path)
        if current_fingerprint != baseline.get(path):
            changed.append(path)
    return sorted(set(changed))


def _scope_mismatches(plan_dir: Path, scope_paths: list[str], file_paths: list[str]) -> list[str]:
    ignored = _plan_bookkeeping_files(plan_dir)
    renames = _read_plan_yaml(plan_dir).get("renames", [])
    out_of_scope: list[str] = []
    for path in file_paths:
        if path in ignored:
            continue
        if any(path_matches(path, scope_path) for scope_path in scope_paths):
            continue
        if any(
            path == rename.get("to") and any(path_matches(rename.get("from", ""), scope_path) for scope_path in scope_paths)
            for rename in renames
        ):
            continue
        out_of_scope.append(path)
    return sorted(set(out_of_scope))


def _verification_matches_current_state(plan_dir: Path, *, current_snapshot: dict | None = None) -> bool:
    status_data = _read_status_yaml(plan_dir)
    verification = status_data.get("verification", {})
    if not isinstance(verification, dict) or not verification.get("passed"):
        return False

    plan_data = _read_plan_yaml(plan_dir)
    scope_included = plan_data.get("scope", {}).get("included", [])
    current = current_snapshot or _capture_git_state(scope_paths=scope_included or None)
    expected_head = verification.get("git_head", "")
    if expected_head and expected_head != current.get("git_head", ""):
        return False

    ignored = _plan_bookkeeping_files(plan_dir)
    expected = {
        path: fingerprint
        for path, fingerprint in verification.get("fingerprints", {}).items()
        if path not in ignored
    }
    current_fingerprints = {
        path: fingerprint
        for path, fingerprint in current.get("fingerprints", {}).items()
        if path not in ignored
    }

    return expected == current_fingerprints


def _summarize_issue(message: str, limit: int = 88) -> str:
    compact = " ".join(str(message).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _cached_verification_state(status_data: dict | None) -> str:
    if not isinstance(status_data, dict):
        return "—"
    verification = status_data.get("verification", {})
    if not isinstance(verification, dict):
        return "—"
    if verification.get("passed") is True:
        return "passed"
    if verification.get("last_run"):
        return "failed"
    return "—"


def _verification_refresh_snapshot(plan_dir: Path, snapshot_cache: dict[tuple[str, ...], dict]) -> dict:
    plan_data = _read_plan_yaml(plan_dir)
    scope_included = plan_data.get("scope", {}).get("included", [])
    cache_key = tuple(sorted(scope_included))
    if cache_key not in snapshot_cache:
        snapshot_cache[cache_key] = _capture_git_state(scope_paths=scope_included or None)
    return snapshot_cache[cache_key]


def _verification_state(
    plan_dir: Path,
    status_data: dict | None,
    *,
    refresh_verification: bool = False,
    snapshot_cache: dict[tuple[str, ...], dict] | None = None,
) -> str:
    cached_state = _cached_verification_state(status_data)
    if cached_state != "passed" or not refresh_verification:
        return cached_state
    if snapshot_cache is None:
        snapshot_cache = {}
    current_snapshot = _verification_refresh_snapshot(plan_dir, snapshot_cache)
    return "passed" if _verification_matches_current_state(plan_dir, current_snapshot=current_snapshot) else "stale"


def _plan_overview(
    plan_dir: Path,
    *,
    refresh_verification: bool = False,
    snapshot_cache: dict[tuple[str, ...], dict] | None = None,
) -> dict:
    plan_data, plan_error = _safe_read_plan_yaml(plan_dir)
    status_data: dict | None = None
    status_error: str | None = None
    if plan_error is None:
        status_data, status_error = _safe_read_status_yaml(plan_dir)

    meta = plan_data.get("plan", {}) if isinstance(plan_data, dict) else {}
    plan_status = meta.get("status", "unknown")
    phase = "—"
    if isinstance(status_data, dict):
        phase = status_data.get("status", {}).get("phase", "—")

    issue = ""
    display_status = plan_status
    if plan_error:
        display_status = "invalid"
        phase = "error"
        issue = _summarize_issue(plan_error)
    elif status_error:
        phase = "error"
        issue = _summarize_issue(status_error)

    return {
        "name": meta.get("name", plan_dir.name) if isinstance(meta, dict) else plan_dir.name,
        "status": display_status,
        "priority": meta.get("priority", "—") if isinstance(meta, dict) else "—",
        "owner": meta.get("owner", "—") if isinstance(meta, dict) else "—",
        "phase": phase,
        "verified": _verification_state(
            plan_dir,
            status_data,
            refresh_verification=refresh_verification,
            snapshot_cache=snapshot_cache,
        ) if not plan_error else "—",
        "issue": issue,
        "plan_error": plan_error,
        "status_error": status_error,
    }


def _baseline_mode_for_plan(plan_dir: Path) -> str:
    status_data, status_error = _safe_read_status_yaml(plan_dir)
    if status_error or not isinstance(status_data, dict):
        return "scoped"
    activation = status_data.get("activation", {})
    if not isinstance(activation, dict):
        return "scoped"
    return activation.get("baseline_mode", "scoped")


def _out_of_scope_context_since_activation(plan_dir: Path, current_snapshot: dict) -> tuple[list[str], list[str]]:
    status_data = _read_status_yaml(plan_dir)
    activation = status_data.get("activation", {})
    if not isinstance(activation, dict) or activation.get("baseline_mode", "scoped") != "scoped":
        return [], []

    baseline_context = activation.get("context_fingerprints", {})
    if not isinstance(baseline_context, dict):
        baseline_context = {}

    ignored = _plan_bookkeeping_files(plan_dir)
    current_context = [
        path for path in current_snapshot.get("context_changed_files", [])
        if path not in ignored
    ]
    current_context_fingerprints = current_snapshot.get("context_fingerprints", {})
    plan_data = _read_plan_yaml(plan_dir)
    renames = plan_data.get("renames", [])

    new_or_changed: list[str] = []
    for path in current_context:
        if any(
            path == rename.get("to") and any(path_matches(rename.get("from", ""), scope_path) for scope_path in plan_data.get("scope", {}).get("included", []))
            for rename in renames
        ):
            continue
        if current_context_fingerprints.get(path) != baseline_context.get(path):
            new_or_changed.append(path)

    baseline_context_paths = [
        path for path in activation.get("context_changed_files", [])
        if path not in ignored
    ]
    return sorted(set(baseline_context_paths)), sorted(set(new_or_changed))


def _capture_activation_snapshot(plan_dir: Path, plan_data: dict, *, baseline_mode: str) -> dict:
    scope_included = plan_data.get("scope", {}).get("included", [])
    scope_paths = scope_included if baseline_mode == "scoped" else None
    baseline = _capture_git_state(scope_paths=scope_paths or None)
    ignored = _plan_bookkeeping_files(plan_dir)
    baseline["changed_files"] = [
        path for path in baseline.get("changed_files", [])
        if path not in ignored
    ]
    baseline["fingerprints"] = {
        path: fingerprint
        for path, fingerprint in baseline.get("fingerprints", {}).items()
        if path not in ignored
    }
    baseline["context_changed_files"] = [
        path for path in baseline.get("context_changed_files", [])
        if path not in ignored
    ]
    baseline["context_fingerprints"] = {
        path: fingerprint
        for path, fingerprint in baseline.get("context_fingerprints", {}).items()
        if path not in ignored
    }
    rename_sources = [rename.get("from", "") for rename in plan_data.get("renames", []) if rename.get("from")]
    if rename_sources:
        baseline["fingerprints"].update(build_fingerprints(rename_sources))
    baseline["baseline_mode"] = baseline_mode
    return baseline


def _default_verify_commands(info) -> list[str]:
    commands: list[str] = []
    for cmd in info.test_commands + info.lint_commands:
        if cmd not in commands:
            commands.append(cmd)
    return commands


def _set_plan_status(plan_dir: Path, new_status: str) -> None:
    data = _read_plan_yaml(plan_dir)
    if "plan" not in data:
        data["plan"] = {}
    data["plan"]["status"] = new_status
    _write_plan_yaml(plan_dir, data)

    # Also update the registry.
    repo_root = find_project_root_for_plan(plan_dir)
    registry_path = get_registry_path(repo_root)
    if registry_path.exists():
        reg = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        plans = reg.get("active_plans", [])
        for entry in plans:
            if isinstance(entry, dict) and entry.get("name") == plan_dir.name:
                entry["status"] = new_status
        reg["active_plans"] = plans
        registry_path.write_text(
            yaml.safe_dump(reg, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )

    status_data = _read_status_yaml(plan_dir)
    if status_data:
        status_data.setdefault("status", {})
        if new_status == "active":
            status_data["status"]["phase"] = "implementation"
            status_data["status"]["progress_percent"] = max(status_data["status"].get("progress_percent", 0), 25)
        elif new_status == "suspended":
            status_data["status"]["phase"] = "suspended"
        elif new_status == "completed":
            status_data["status"]["phase"] = "completed"
            status_data["status"]["progress_percent"] = 100
        elif new_status == "archived":
            status_data["status"]["phase"] = "archived"
        _write_status_yaml(plan_dir, status_data)


def _resolve_plan(name: str) -> Path | None:
    """Find a plan directory by name."""
    candidate = _docs_dir() / name
    if candidate.is_dir() and (candidate / "plan.yaml").exists():
        return candidate
    # Try slugified match.
    from planguard.planning.generate_plan import slugify

    slug = slugify(name)
    candidate = _docs_dir() / slug
    if candidate.is_dir() and (candidate / "plan.yaml").exists():
        return candidate
    return None


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@app.command()
def init(
    root: str = typer.Argument(".", help="Project root directory."),
    no_wizard: bool = typer.Option(False, "--no-wizard", help="Skip interactive questions."),
    refresh_agents: bool = typer.Option(False, "--refresh-agents", help="Refresh the managed framework section in AGENTS.md."),
):
    """Set up PlanGuard in a project.

    Detects the project's stack and structure, then creates the plans root,
    .planguard/ context, and AGENTS.md tailored for the project.
    """
    base = Path(root).resolve()

    print(Panel("[bold]PlanGuard Setup[/bold]", style="cyan"))

    # ---- Detect project ----
    info = detect_project(base)
    print()
    print("[bold]Project detected:[/bold]")
    print(info.summary())
    print()

    if not no_wizard:
        # Let user confirm or correct.
        if info.is_empty:
            print("[yellow]This looks like a new project.[/yellow]")
            lang = typer.prompt(
                "What language/stack will this project use?",
                default="not decided yet",
            )
            print(f"[dim]Noted: {lang}[/dim]")
        else:
            correct = typer.confirm("Does this look right?", default=True)
            if not correct:
                notes = typer.prompt("What should be different? (brief note)")
                print(f"[dim]Noted: {notes}[/dim]")

    # ---- Create structure ----
    plans_root = get_plans_root(base)
    created = _ensure_plan_storage(base, plans_root)
    created.extend(_ensure_runtime_state(base))
    created.extend(_ensure_local_storage_ignored(base, plans_root))

    # ---- .planguard/ project context ----
    if has_context(base):
        print("[dim].planguard/ context already exists.[/dim]")
    else:
        ctx_created = init_context(
            base,
            name=base.name,
            languages=info.languages,
            frameworks=info.frameworks,
            source_dirs=info.source_dirs,
            test_dirs=info.test_dirs,
        )
        created.extend(ctx_created)
        if ctx_created:
            print("[green]Created .planguard/ project context[/green]")
            print("[dim]  Review and fill in: project.yaml, conventions.md, boundaries.md, glossary.md[/dim]")

    # ---- AGENTS.md ----
    workflow_section = _build_workflow_section(info)
    agents_path = base / "AGENTS.md"
    if agents_path.exists():
        existing = agents_path.read_text(encoding="utf-8")
        if _FRAMEWORK_MARKER in existing:
            if refresh_agents:
                agents_path.write_text(_replace_framework_section(existing, workflow_section), encoding="utf-8")
                print("[green]Refreshed framework workflow in AGENTS.md[/green]")
            else:
                print("[dim]AGENTS.md already contains the framework workflow. Skipping.[/dim]")
                print("[dim]Upgrade tip: rerun with --refresh-agents to refresh the managed section.[/dim]")
        else:
            print("[yellow]AGENTS.md already exists with your own content.[/yellow]")
            print("[dim]The framework workflow section will be appended to the end.[/dim]")
            if not no_wizard:
                append = typer.confirm("Append the framework workflow to AGENTS.md?", default=True)
                if not append:
                    print("[dim]Skipped. You can add the section manually later.[/dim]")
                else:
                    updated = existing.rstrip() + "\n\n" + workflow_section
                    agents_path.write_text(updated, encoding="utf-8")
                    print("[green]Appended framework workflow to AGENTS.md[/green]")
            else:
                updated = existing.rstrip() + "\n\n" + workflow_section
                agents_path.write_text(updated, encoding="utf-8")
                print("[green]Appended framework workflow to AGENTS.md[/green]")
    else:
        full = "# AGENTS.md\n\n" + workflow_section
        agents_path.write_text(full, encoding="utf-8")
        created.append(agents_path)
        print("[green]Created AGENTS.md[/green]")

    if created:
        print()
        print("[green]Created:[/green]")
        for p in created:
            print(f"  {p.relative_to(base)}")
    else:
        print("[yellow]Everything already in place.[/yellow]")

    print()
    print(f"[dim]Plans default to local storage under {get_default_plans_root()} and are ignored via .gitignore[/dim]")
    print("[dim]Upgrade tip: existing repos can refresh agent instructions with planguard upgrade --no-wizard[/dim]")
    print()
    print(Panel(
        "[bold]Next step:[/bold] Create a plan with [cyan]planguard plan[/cyan]",
        style="green",
    ))


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

@app.command()
def upgrade(
    root: str = typer.Argument(".", help="Project root directory."),
    plans_root: str = typer.Option(None, "--plans-root", help="Optional new plans root to migrate plan storage into."),
    refresh_agents: bool = typer.Option(True, "--refresh-agents/--no-refresh-agents", help="Refresh the managed framework section in AGENTS.md."),
    no_wizard: bool = typer.Option(False, "--no-wizard", help="Skip interactive questions."),
):
    """Upgrade an existing PlanGuard repository to newer workflow defaults."""
    base = Path(root).resolve()
    print(Panel("[bold]PlanGuard Upgrade[/bold]", style="cyan"))

    info = detect_project(base)
    workflow_section = _build_workflow_section(info)
    current_plans_root = get_plans_root(base)
    selected_plans_root = plans_root

    if plans_root is None and has_legacy_docs_plans(base):
        selected_plans_root = str(get_default_plans_root())

    if not no_wizard and plans_root is None and has_legacy_docs_plans(base):
        change_storage = typer.confirm(
            f"Current plans root is '{current_plans_root}'. Do you want to migrate plans to the local default '{get_default_plans_root()}'?",
            default=True,
        )
        if change_storage:
            selected_plans_root = typer.prompt(
                "New plans root",
                default=str(get_default_plans_root()),
            )
        else:
            selected_plans_root = None

    ignore_root = Path(selected_plans_root) if selected_plans_root else current_plans_root

    created = _ensure_plan_storage(base, current_plans_root)
    created.extend(_ensure_runtime_state(base))
    created.extend(_ensure_local_storage_ignored(base, ignore_root))
    migrated: list[str] = []
    normalized_summaries: list[dict] = []

    if refresh_agents:
        agents_path = base / "AGENTS.md"
        if agents_path.exists():
            existing = agents_path.read_text(encoding="utf-8")
            if _FRAMEWORK_MARKER in existing:
                agents_path.write_text(_replace_framework_section(existing, workflow_section), encoding="utf-8")
                print("[green]Refreshed framework workflow in AGENTS.md[/green]")
            else:
                agents_path.write_text(existing.rstrip() + "\n\n" + workflow_section, encoding="utf-8")
                print("[green]Appended framework workflow to AGENTS.md[/green]")
        else:
            agents_path.write_text("# AGENTS.md\n\n" + workflow_section, encoding="utf-8")
            created.append(agents_path)
            print("[green]Created AGENTS.md[/green]")

    if selected_plans_root:
        target_root = Path(selected_plans_root)
        if target_root != current_plans_root:
            _ensure_plan_storage(base, target_root)
            source_root = base / current_plans_root
            target_base = base / target_root

            for plan_dir in discover_plan_dirs(source_root):
                target_plan_dir = target_base / plan_dir.name
                if target_plan_dir.exists():
                    print(f"[red]Cannot migrate {plan_dir.name}: target already exists at {target_plan_dir}[/red]")
                    raise typer.Exit(code=1)
                plan_dir.rename(target_plan_dir)
                migrated.append(f"{plan_dir.relative_to(base)} -> {target_plan_dir.relative_to(base)}")

            if target_root == get_default_plans_root():
                _clear_default_plans_root_config(base)
                print(f"[green]Using default local plans_root: {target_root}[/green]")
            else:
                _write_config(base, plans_root=str(target_root))
                print(f"[green]Configured plans_root: {target_root}[/green]")
            current_plans_root = target_root
        elif (base / ".planguard" / "config.yaml").exists():
            print(f"[dim]plans_root already set to {current_plans_root}[/dim]")

    plan_dirs = discover_plan_dirs(base / current_plans_root)
    migrated.extend(_migrate_legacy_runtime_state(base, plan_dirs))
    plan_dirs = discover_plan_dirs(base / current_plans_root)
    normalized_summaries = [_normalize_legacy_plan(plan_dir, base) for plan_dir in plan_dirs]

    if created:
        print()
        print("[green]Created:[/green]")
        for path in created:
            print(f"  {path.relative_to(base)}")

    if migrated:
        print()
        print("[green]Migrated plans:[/green]")
        for item in migrated:
            print(f"  {item}")

    print()
    print("[bold]Upgrade summary:[/bold]")
    print(f"  Plans scanned: {len(plan_dirs)}")

    normalized = [item for item in normalized_summaries if item["normalized"]]
    suspended = [item for item in normalized_summaries if item["suspended"]]
    manual_review = [item for item in normalized_summaries if item["manual_review"]]

    if normalized:
        print("[green]  Normalized plans:[/green]")
        for item in normalized:
            details = f" ({'; '.join(item['notes'])})" if item["notes"] else ""
            print(f"    {item['name']}{details}")
    else:
        print("[dim]  No legacy normalization changes were needed[/dim]")

    if suspended:
        print("[yellow]  Suspended for review:[/yellow]")
        for item in suspended:
            details = f" ({'; '.join(item['notes'])})" if item["notes"] else ""
            print(f"    {item['name']}{details}")

    if manual_review:
        print("[yellow]  Manual review needed:[/yellow]")
        for item in manual_review:
            for note in item["manual_review"]:
                print(f"    {item['name']}: {note}")

    print()
    print("[bold]Next step:[/bold] Run [cyan]planguard check[/cyan] to confirm the upgraded repo state.")


# ---------------------------------------------------------------------------
# plan (wizard)
# ---------------------------------------------------------------------------

@app.command()
def plan(
    name: str = typer.Argument(None, help="Plan name (slug). Omit to use the wizard."),
    objective: str = typer.Option(None, "--objective", "-o", help="What this plan will accomplish."),
    scope: str = typer.Option(None, "--scope", "-s", help="Comma-separated paths in scope."),
    priority: str = typer.Option(None, "--priority", "-p", help="low, medium, high, or critical."),
    owner: str = typer.Option(None, "--owner", help="Who owns this plan."),
    template: str = typer.Option("default", "--template", "-t", help="Plan template: default, docs-only, refactor, schema-change, service-integration."),
    no_wizard: bool = typer.Option(False, "--no-wizard", help="Skip interactive questions."),
):
    """Create a new plan. Launches an interactive wizard when run without flags."""
    print(Panel("[bold]New Plan[/bold]", style="cyan"))
    if template != "default":
        print(f"[dim]Using template: {template}[/dim]")
    risks: list[dict] = []
    done_when_list: list[str] = []
    verify_list: list[str] = []
    rollback_input = "git revert to prior commit"

    # ---- Detect project context ----
    info = detect_project(".")
    if info.source_dirs or info.test_dirs:
        detected_paths = info.source_dirs + info.test_dirs
        print(f"[dim]Detected project paths: {', '.join(detected_paths)}[/dim]")
    if info.has_existing_plans:
        print(f"[dim]Existing plans: {', '.join(info.existing_plan_names)}[/dim]")
    print()

    # ---- Wizard ----
    if not no_wizard:
        if not objective:
            objective = typer.prompt(
                "What is the objective? (What are you trying to accomplish?)"
            )
        if not name:
            suggested = objective[:60] if objective else "new plan"
            name = typer.prompt("Short name for this plan", default=suggested)
        if not scope:
            if info.source_dirs:
                default_scope = ", ".join(info.source_dirs + info.test_dirs)
            else:
                default_scope = "src, tests"
            scope = typer.prompt(
                "Which directories/paths are in scope? (comma-separated)",
                default=default_scope,
            )
        if not priority:
            priority = typer.prompt(
                "Priority (low / medium / high / critical)",
                default="medium",
            )
        if not owner:
            owner = typer.prompt("Who owns this plan?", default="unassigned")

        # Done-when criteria.
        print()
        print("[bold]How will you know this is done?[/bold]")
        done_input = typer.prompt(
            "Done-when criteria (comma-separated, or press Enter for defaults)",
            default="",
        )
        done_when_list: list[str] = [
            s.strip() for s in done_input.split(",") if s.strip()
        ] if done_input.strip() else []

        # Verification commands.
        if info.test_commands:
            default_verify = ", ".join(_default_verify_commands(info))
        else:
            default_verify = ""
        verify_input = typer.prompt(
            "Commands to verify correctness (comma-separated, or press Enter to skip)",
            default=default_verify,
        )
        verify_list: list[str] = [
            s.strip() for s in verify_input.split(",") if s.strip()
        ] if verify_input.strip() else []

        # Rollback strategy.
        rollback_input = typer.prompt(
            "How would you undo this if it goes wrong?",
            default="git revert to prior commit",
        )

        # Ask about known risks.
        print()
        risks: list[dict] = []
        add_risk = typer.confirm("Do you want to add any known risks?", default=False)
        risk_counter = 1
        while add_risk:
            desc = typer.prompt("Risk description")
            severity = typer.prompt("Severity (low / medium / high / critical)", default="medium")
            mitigation = typer.prompt("Mitigation strategy")
            risks.append({
                "id": f"RISK-{risk_counter:03d}",
                "description": desc,
                "severity": severity,
                "mitigation": mitigation,
            })
            risk_counter += 1
            add_risk = typer.confirm("Add another risk?", default=False)
    else:
        # Non-wizard: require at least name and objective.
        if not name:
            print("[red]--name is required in --no-wizard mode.[/red]")
            raise typer.Exit(code=1)
        if not objective:
            objective = name
        verify_list = _default_verify_commands(info)

    # Defaults.
    scope_list = [s.strip() for s in (scope or "src, tests").split(",") if s.strip()]
    priority = priority or "medium"
    owner = owner or "unassigned"
    risk_list = risks or None
    done_list = done_when_list or None
    verify = verify_list or None
    rollback = rollback_input

    try:
        plan_dir = generate_plan(
            name=name,
            objective=objective,
            scope_included=scope_list,
            priority=priority,
            owner=owner,
            risks=risk_list,
            done_when=done_list,
            verify_commands=verify,
            rollback_strategy=rollback,
            template=template,
            docs_dir=_docs_dir(),
        )
    except KeyError as exc:
        print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    log_event("plan_created", plan=plan_dir.name, details={
        "objective": objective,
        "priority": priority,
        "owner": owner,
        "scope": scope_list,
    })

    print()
    print(f"[green]Plan created:[/green] {plan_dir}")
    print()
    print(Panel(
        "[bold]Next steps:[/bold]\n"
        "1. Review and refine the generated [cyan]plan.yaml[/cyan]\n"
        "2. Run [cyan]planguard check[/cyan] to validate\n"
        "3. Run [cyan]planguard activate " + plan_dir.name + "[/cyan] when ready to implement",
        style="green",
    ))


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

@app.command()
def check(
    name: str = typer.Argument(None, help="Check a specific plan. Omit to check all."),
):
    """Run all checks: validation, collisions, risk score, dependency graph.

    Produces a single pass/fail report.
    """
    print(Panel("[bold]Running Checks[/bold]", style="cyan"))

    docs = _docs_dir()

    if name:
        plan_dir = _resolve_plan(name)
        if not plan_dir:
            print(f"[red]Plan not found: {name}[/red]")
            raise typer.Exit(code=1)
        ok = _check_single(plan_dir)
        if not ok:
            raise typer.Exit(code=1)
    else:
        plan_dirs = discover_plan_dirs(docs)
        if not plan_dirs:
            print("[yellow]No plans found. Run 'planguard plan' to create one.[/yellow]")
            raise typer.Exit(code=0)
        all_ok = True
        for pd in plan_dirs:
            ok = _check_single(pd)
            if not ok:
                all_ok = False
            print()

        # Cross-plan checks.
        print("[bold]Cross-plan checks:[/bold]")
        collisions = detect_collisions(str(docs))
        if collisions:
            print("[red]  Collisions detected:[/red]")
            for c in collisions:
                print(f"    {c['plans'][0]} <-> {c['plans'][1]}: {', '.join(c['overlap'])}")
            all_ok = False
        else:
            print("[green]  No collisions between active plans[/green]")

        print()
        if all_ok:
            print(Panel("[bold green]All checks passed[/bold green]", style="green"))
        else:
            print(Panel("[bold red]Some checks failed — review above[/bold red]", style="red"))
            raise typer.Exit(code=1)


def _check_single(plan_dir: Path) -> bool:
    """Run checks on a single plan and print results. Returns True if all pass."""
    name = plan_dir.name
    print(f"\n[bold]Plan: {name}[/bold]")

    all_ok = True

    # 1. Validation.
    ok, messages = validate_plan(plan_dir)
    if ok:
        print(f"{_PASS} Structure valid")
    else:
        print(f"{_FAIL} Structure invalid")
        for m in messages:
            print(f"    {m}")
        all_ok = False

    if any(message.startswith("Invalid YAML in plan.yaml:") for message in messages):
        print("[dim]  Status: unknown[/dim]")
        return False

    try:
        data = _read_plan_yaml(plan_dir)
    except yaml.YAMLError as exc:
        print(f"{_FAIL} Unable to read plan.yaml")
        print(f"    {format_yaml_error(plan_dir / 'plan.yaml', exc)}")
        print("[dim]  Status: unknown[/dim]")
        return False

    status = data.get("plan", {}).get("status", "unknown")
    scope_paths = data.get("scope", {}).get("included", [])
    baseline_mode = _baseline_mode_for_plan(plan_dir)
    current_snapshot = _capture_git_state(
        scope_paths=None if baseline_mode == "repo" else (scope_paths or None)
    ) if status == "active" else {}
    diff_paths = _files_changed_since_activation(plan_dir, current_snapshot) if status == "active" else []

    # 2. Risk score.
    total, risk_status, details = compute_risk_score(plan_dir)
    if risk_status == "pass":
        print(f"{_PASS} Risk score: {total} (threshold: 6)")
    else:
        print(f"{_FAIL} Risk score: {total} exceeds threshold 6")
        for d in details:
            print(f"    {d['id']} ({d['severity']}={d['weight']}): {d['description']}")
        all_ok = False

    # 2b. Scope enforcement against real changes after activation.
    if diff_paths:
        out_of_scope = _scope_mismatches(plan_dir, scope_paths, diff_paths)
        if out_of_scope:
            print(f"{_FAIL} Changed files outside declared scope:")
            for path in out_of_scope:
                print(f"    {path}")
            all_ok = False
        else:
            print(f"{_PASS} Changed files remain within declared scope")
    elif status == "active" and current_snapshot.get("is_git_repo"):
        print("[dim]  - No post-activation changes detected[/dim]")

    if status == "active" and baseline_mode == "scoped":
        activation_context, new_out_of_scope = _out_of_scope_context_since_activation(plan_dir, current_snapshot)
        if new_out_of_scope:
            print(f"{_FAIL} Changed files outside declared scope:")
            for path in new_out_of_scope:
                print(f"    {path}")
            all_ok = False
        elif activation_context:
            print("[dim]  - Out-of-scope repo changes are tracked separately from the scoped baseline[/dim]")

    # 2c. Rename hints — suggest adding a renames section for detected git renames.
    if status == "active":
        git_renames = detect_git_renames()
        plan_renames = data.get("renames", [])
        declared_froms = {r.get("from", "") for r in plan_renames}
        suggestions = [r for r in git_renames if r["from"] not in declared_froms]
        if suggestions:
            print("[yellow]  [HINT] Detected renames — consider adding to plan.yaml:[/yellow]")
            print("[dim]  renames:[/dim]")
            for s in suggestions:
                print(f"[dim]    - from: {s['from']}[/dim]")
                print(f"[dim]      to: {s['to']}[/dim]")

    # 3. Dependency graph.
    graph = build_plan_graph(plan_dir)
    if graph is not None:
        graph_messages = analyze_graph(graph)
        if graph_messages and graph_messages[0].startswith("ERROR:"):
            print(f"{_FAIL} {graph_messages[0]}")
            all_ok = False
        else:
            print(f"{_PASS} Dependency graph is acyclic")
    else:
        print("[dim]  - No dependency graph to check[/dim]")

    # 4. Policy checks.
    policies = load_policies()
    if policies.get("rules"):
        violations = check_policies(
            plan_dir,
            policies,
            file_paths=diff_paths or None,
        )
        blocking = [v for v in violations if v["action"] == "block"]
        warnings = [v for v in violations if v["action"] != "block"]
        if blocking:
            print(f"{_FAIL} Policy violations (blocking):")
            for v in blocking:
                print(f"    {v['rule']}: {v['description']}")
            all_ok = False
        elif warnings:
            print(f"[yellow]  [WARN] Policy warnings:[/yellow]")
            for v in warnings:
                print(f"    {v['rule']}: {v['description']}")
        else:
            print(f"{_PASS} Policies satisfied")
    else:
        print("[dim]  - No policies configured[/dim]")

    # 5. Boundary checks.
    boundaries = load_boundaries()
    if boundaries:
        boundary_violations = check_boundary_violations(
            plan_dir,
            boundaries,
            file_paths=diff_paths or None,
        )
        if boundary_violations:
            print(f"{_FAIL} Boundary violations:")
            for bv in boundary_violations:
                print(f"    {bv}")
            all_ok = False
        else:
            print(f"{_PASS} No boundary violations")
    else:
        print("[dim]  - No boundaries configured[/dim]")

    # 6. Status.
    print(f"[dim]  Status: {status}[/dim]")

    return all_ok


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status(
    refresh_verification: bool = typer.Option(
        False,
        "--refresh-verification",
        help="Recompute freshness for previously passed verifications.",
    ),
):
    """Show all plans and their current status.

    Uses cached verification results by default. Pass
    ``--refresh-verification`` to recompute live freshness for previously
    passed plans.
    """
    docs = _docs_dir()
    plan_dirs = discover_plan_dirs(docs)

    if not plan_dirs:
        print("[yellow]No plans found. Run 'planguard plan' to create one.[/yellow]")
        raise typer.Exit(code=0)

    table = Table(title="Plans")
    table.add_column("Name", style="cyan", overflow="fold")
    table.add_column("Status", style="bold")
    table.add_column("Priority")
    table.add_column("Owner")
    table.add_column("Phase")
    table.add_column("Verified")
    issues: list[tuple[str, str]] = []
    snapshot_cache: dict[tuple[str, ...], dict] = {}

    for pd in plan_dirs:
        overview = _plan_overview(
            pd,
            refresh_verification=refresh_verification,
            snapshot_cache=snapshot_cache,
        )
        plan_status = overview["status"]
        status_style = {
            "draft": "yellow",
            "active": "green",
            "suspended": "yellow",
            "completed": "dim",
            "archived": "dim",
            "invalid": "red",
        }.get(plan_status, "white")

        table.add_row(
            overview["name"],
            f"[{status_style}]{plan_status}[/{status_style}]",
            overview["priority"],
            overview["owner"],
            overview["phase"],
            overview["verified"],
        )
        if overview["issue"]:
            issues.append((overview["name"], overview["issue"]))

    print(table)
    if issues:
        print("[yellow]Plan issues:[/yellow]")
        for name, issue in issues:
            print(f"  {name}: {issue}")


# ---------------------------------------------------------------------------
# activate
# ---------------------------------------------------------------------------

@app.command()
def activate(
    name: str = typer.Argument(..., help="Plan name to activate."),
    baseline_mode: str = typer.Option(
        "scoped",
        "--baseline-mode",
        help="Capture baseline from the declared scope only ('scoped') or the whole repo ('repo').",
    ),
):
    """Mark a plan as active (ready for implementation)."""
    plan_dir = _resolve_plan(name)
    if not plan_dir:
        print(f"[red]Plan not found: {name}[/red]")
        raise typer.Exit(code=1)

    if baseline_mode not in {"scoped", "repo"}:
        print(f"[red]Unsupported baseline mode: {baseline_mode}. Use 'scoped' or 'repo'.[/red]")
        raise typer.Exit(code=1)

    plan_data, plan_error = _safe_read_plan_yaml(plan_dir)
    if plan_error:
        print(f"[red]Cannot activate malformed plan:[/red] {plan_error}")
        raise typer.Exit(code=1)

    current = plan_data.get("plan", {}).get("status")
    if current == "active":
        print(f"[yellow]{name} is already active.[/yellow]")
        raise typer.Exit(code=0)

    if current == "suspended":
        print(f"[yellow]{name} is suspended. Use 'planguard resume {name}' instead.[/yellow]")
        raise typer.Exit(code=1)

    if current in ("completed", "archived"):
        print(f"[red]Cannot activate a {current} plan. Create a new plan instead.[/red]")
        raise typer.Exit(code=1)

    # Run checks first.
    print(f"Running checks before activating [cyan]{name}[/cyan]...")
    ok = _check_single(plan_dir)
    if not ok:
        print()
        print("[red]Fix the issues above before activating.[/red]")
        raise typer.Exit(code=1)

    collisions = [
        collision for collision in detect_collisions(_docs_dir())
        if name in collision["plans"] or plan_dir.name in collision["plans"]
    ]
    if collisions:
        print()
        print(f"{_FAIL} Cross-plan collisions detected:")
        for collision in collisions:
            print(f"    {collision['plans'][0]} <-> {collision['plans'][1]}: {', '.join(collision['overlap'])}")
        raise typer.Exit(code=1)

    _set_plan_status(plan_dir, "active")
    status_data = _read_status_yaml(plan_dir)
    baseline = _capture_activation_snapshot(plan_dir, plan_data, baseline_mode=baseline_mode)
    status_data["activation"] = {
        "activated_at": baseline["captured_at"],
        "git_branch": baseline["git_branch"],
        "git_head": baseline["git_head"],
        "baseline_changed_files": baseline["changed_files"],
        "baseline_fingerprints": baseline["fingerprints"],
        "baseline_mode": baseline_mode,
        "context_changed_files": baseline["context_changed_files"],
        "context_fingerprints": baseline["context_fingerprints"],
    }
    _write_status_yaml(plan_dir, status_data)
    log_event("plan_activated", plan=name, details={
        "baseline_changed_files": baseline["changed_files"],
        "baseline_mode": baseline_mode,
        "context_changed_files": baseline["context_changed_files"],
    })
    print()
    print(f"[green]{name} is now active. You may begin implementation.[/green]")
    if baseline_mode == "scoped" and baseline["context_changed_files"]:
        print("[dim]Out-of-scope repo changes were recorded as context only:[/dim]")
        for path in baseline["context_changed_files"]:
            print(f"[dim]  {path}[/dim]")


# ---------------------------------------------------------------------------
# complete
# ---------------------------------------------------------------------------

@app.command()
def complete(name: str = typer.Argument(..., help="Plan name to mark as completed.")):
    """Mark a plan as completed."""
    plan_dir = _resolve_plan(name)
    if not plan_dir:
        print(f"[red]Plan not found: {name}[/red]")
        raise typer.Exit(code=1)

    plan_data, plan_error = _safe_read_plan_yaml(plan_dir)
    if plan_error:
        print(f"[red]Cannot complete malformed plan:[/red] {plan_error}")
        raise typer.Exit(code=1)

    current = plan_data.get("plan", {}).get("status")
    if current != "active":
        print("[red]Only active plans can be completed.[/red]")
        raise typer.Exit(code=1)

    if not _verification_matches_current_state(plan_dir):
        print("[red]Plan cannot be completed until verification passes against the current state.[/red]")
        print("[dim]Run planguard verify " + name + " and retry.[/dim]")
        raise typer.Exit(code=1)

    _set_plan_status(plan_dir, "completed")
    status_data = _read_status_yaml(plan_dir)
    status_data.setdefault("completed_steps", [])
    if "Verify (planguard verify)" not in status_data["completed_steps"]:
        status_data["completed_steps"].append("Verify (planguard verify)")
    if "Complete plan (planguard complete)" not in status_data["completed_steps"]:
        status_data["completed_steps"].append("Complete plan (planguard complete)")
    status_data["remaining_steps"] = []

    # Auto-fill handoff skeleton.
    verification = status_data.get("verification", {})
    handoff = status_data.get("handoff", {})
    if not handoff.get("summary"):
        handoff["summary"] = f"Plan {name} completed on {_now_iso()[:10]}"
    handoff["completed_at"] = _now_iso()
    handoff["verification_passed"] = verification.get("passed", False)
    handoff["scope_files_changed"] = len(verification.get("changed_files", []))
    if not handoff.get("notes"):
        handoff["notes"] = []
    status_data["handoff"] = handoff

    _write_status_yaml(plan_dir, status_data)
    log_event("plan_completed", plan=name)
    print(f"[green]{name} marked as completed.[/green]")


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------

@app.command()
def archive(name: str = typer.Argument(..., help="Plan name to archive.")):
    """Archive a plan (removes it from active consideration)."""
    plan_dir = _resolve_plan(name)
    if not plan_dir:
        print(f"[red]Plan not found: {name}[/red]")
        raise typer.Exit(code=1)

    _set_plan_status(plan_dir, "archived")
    log_event("plan_archived", plan=name)
    print(f"[dim]{name} archived.[/dim]")


# ---------------------------------------------------------------------------
# suspend
# ---------------------------------------------------------------------------

@app.command()
def suspend(
    name: str = typer.Argument(..., help="Plan name to suspend."),
    reason: str = typer.Option("", "--reason", "-r", help="Why this plan is being suspended."),
):
    """Suspend an active plan so overlapping work can proceed."""
    plan_dir = _resolve_plan(name)
    if not plan_dir:
        print(f"[red]Plan not found: {name}[/red]")
        raise typer.Exit(code=1)

    plan_data, plan_error = _safe_read_plan_yaml(plan_dir)
    if plan_error:
        print(f"[red]Cannot suspend malformed plan:[/red] {plan_error}")
        raise typer.Exit(code=1)

    current = plan_data.get("plan", {}).get("status")
    if current != "active":
        print(f"[red]Only active plans can be suspended (current: {current}).[/red]")
        raise typer.Exit(code=1)

    _set_plan_status(plan_dir, "suspended")
    status_data = _read_status_yaml(plan_dir)
    status_data.setdefault("suspension", {})
    status_data["suspension"]["suspended_at"] = _now_iso()
    status_data["suspension"]["reason"] = reason
    _write_status_yaml(plan_dir, status_data)
    log_event("plan_suspended", plan=name, details={"reason": reason})
    print(f"[yellow]{name} suspended.[/yellow]")
    if reason:
        print(f"[dim]Reason: {reason}[/dim]")
    print("[dim]Resume with: planguard resume " + name + "[/dim]")


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------

@app.command()
def resume(
    name: str = typer.Argument(..., help="Plan name to resume."),
    refresh_baseline: bool = typer.Option(False, "--refresh-baseline", help="Re-capture baseline snapshot."),
    baseline_mode: str = typer.Option(
        None,
        "--baseline-mode",
        help="Override baseline capture mode when refreshing the baseline ('scoped' or 'repo').",
    ),
):
    """Resume a suspended plan."""
    plan_dir = _resolve_plan(name)
    if not plan_dir:
        print(f"[red]Plan not found: {name}[/red]")
        raise typer.Exit(code=1)

    plan_data, plan_error = _safe_read_plan_yaml(plan_dir)
    if plan_error:
        print(f"[red]Cannot resume malformed plan:[/red] {plan_error}")
        raise typer.Exit(code=1)

    current = plan_data.get("plan", {}).get("status")
    if current != "suspended":
        print(f"[red]Only suspended plans can be resumed (current: {current}).[/red]")
        raise typer.Exit(code=1)

    _set_plan_status(plan_dir, "active")
    status_data = _read_status_yaml(plan_dir)
    status_data.setdefault("suspension", {})
    status_data["suspension"]["resumed_at"] = _now_iso()

    if refresh_baseline:
        selected_mode = baseline_mode or _baseline_mode_for_plan(plan_dir)
        if selected_mode not in {"scoped", "repo"}:
            print(f"[red]Unsupported baseline mode: {selected_mode}. Use 'scoped' or 'repo'.[/red]")
            raise typer.Exit(code=1)
        baseline = _capture_activation_snapshot(plan_dir, plan_data, baseline_mode=selected_mode)
        status_data["activation"] = {
            "activated_at": baseline["captured_at"],
            "git_branch": baseline["git_branch"],
            "git_head": baseline["git_head"],
            "baseline_changed_files": baseline["changed_files"],
            "baseline_fingerprints": baseline["fingerprints"],
            "baseline_mode": selected_mode,
            "context_changed_files": baseline["context_changed_files"],
            "context_fingerprints": baseline["context_fingerprints"],
        }
        print(f"[green]{name} resumed with refreshed baseline.[/green]")
        if selected_mode == "scoped" and baseline["context_changed_files"]:
            print("[dim]Out-of-scope repo changes were recorded as context only:[/dim]")
            for path in baseline["context_changed_files"]:
                print(f"[dim]  {path}[/dim]")
    else:
        print(f"[green]{name} resumed.[/green]")

    _write_status_yaml(plan_dir, status_data)
    log_event("plan_resumed", plan=name, details={
        "refresh_baseline": refresh_baseline,
        "baseline_mode": baseline_mode or _baseline_mode_for_plan(plan_dir),
    })


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command(name="list")
def list_plans(
    show_all: bool = typer.Option(False, "--all", "-a", help="Include completed and archived plans."),
    refresh_verification: bool = typer.Option(
        False,
        "--refresh-verification",
        help="Recompute freshness for previously passed verifications.",
    ),
):
    """List plans, filtered by status.

    Uses cached verification results by default. Pass
    ``--refresh-verification`` to recompute live freshness for previously
    passed plans.
    """
    docs = _docs_dir()
    plan_dirs = discover_plan_dirs(docs)
    if not plan_dirs:
        print("[yellow]No plans found.[/yellow]")
        raise typer.Exit(code=0)

    snapshot_cache: dict[tuple[str, ...], dict] = {}
    for pd in plan_dirs:
        overview = _plan_overview(
            pd,
            refresh_verification=refresh_verification,
            snapshot_cache=snapshot_cache,
        )
        plan_status = overview["status"]
        if not show_all and plan_status in ("completed", "archived"):
            continue
        line = f"  {plan_status}  {overview['name']}  (priority: {overview['priority']})"
        if overview["verified"] != "—":
            line += f" verify={overview['verified']}"
        if overview["issue"]:
            line += f"\n    issue: {overview['issue']}"
        print(line)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@app.command()
def verify(name: str = typer.Argument(..., help="Plan name to verify.")):
    """Run the plan's verify_commands and report results.

    This confirms that the implementation actually works. Verification must
    pass before marking a plan complete.

    Supports both plain shell commands (strings) and structured checks (dicts):
      - check: file_exists / file_not_exists / file_moved / text_contains / text_not_contains
      - command: shell command with optional interpreter
    """
    from planguard.verification.primitives import run_check, format_label

    plan_dir = _resolve_plan(name)
    if not plan_dir:
        print(f"[red]Plan not found: {name}[/red]")
        raise typer.Exit(code=1)

    data, plan_error = _safe_read_plan_yaml(plan_dir)
    if plan_error:
        print(f"[red]Cannot verify malformed plan:[/red] {plan_error}")
        raise typer.Exit(code=1)
    commands = data.get("verify_commands", [])
    done_when = data.get("done_when", [])
    inferred = False

    if not commands:
        commands = _default_verify_commands(detect_project("."))
        inferred = True
    if inferred:
        print("[dim]No verify_commands defined; using detected project test/lint commands.[/dim]")
    if not commands:
        print(f"[red]No verification commands available for {name}.[/red]")
        print("[dim]Add verify_commands to your plan.yaml or configure a detectable project test command.[/dim]")
        raise typer.Exit(code=1)

    print(Panel(f"[bold]Verifying: {name}[/bold]", style="cyan"))

    if done_when:
        print("[bold]Done-when criteria:[/bold]")
        for criterion in done_when:
            print(f"  - {criterion}")
        print()

    all_passed = True
    results: list[dict] = []
    for entry in commands:
        label = format_label(entry)
        print(f"[bold]Running:[/bold] {label}")
        result = run_check(entry)
        results.append({
            "command": label,
            "passed": result.passed,
            "duration_seconds": result.duration_seconds,
        })

        if result.passed:
            print(f"{_PASS} {label}")
        else:
            print(f"{_FAIL} {label}")
            if result.detail:
                for line in result.detail.splitlines()[-5:]:
                    print(f"    {line}")
            all_passed = False

    scope_included = data.get("scope", {}).get("included", [])
    status_data = _read_status_yaml(plan_dir)
    verification_snapshot = _capture_git_state(scope_paths=scope_included or None)
    status_data["verification"] = {
        "passed": all_passed,
        "last_run": _now_iso(),
        "git_branch": verification_snapshot["git_branch"],
        "git_head": verification_snapshot["git_head"],
        "changed_files": verification_snapshot["changed_files"],
        "fingerprints": verification_snapshot["fingerprints"],
        "commands": [format_label(e) for e in commands],
        "results": results,
    }
    if all_passed:
        status_data.setdefault("completed_steps", [])
        status_data.setdefault("remaining_steps", [])
        if "Verify (planguard verify)" not in status_data["completed_steps"]:
            status_data["completed_steps"].append("Verify (planguard verify)")
        # Auto-migrate matching remaining_steps.
        for step in list(status_data["remaining_steps"]):
            if "verify" in step.lower():
                status_data["remaining_steps"].remove(step)
                if step not in status_data["completed_steps"]:
                    status_data["completed_steps"].append(step)
        status_data["status"]["phase"] = "validation"
        status_data["status"]["progress_percent"] = max(status_data["status"].get("progress_percent", 0), 75)
    _write_status_yaml(plan_dir, status_data)

    log_event("verification", plan=name, details={
        "passed": all_passed,
        "results": results,
    })

    print()
    if all_passed:
        print(Panel("[bold green]Verification passed[/bold green]", style="green"))
    else:
        print(Panel("[bold red]Verification failed[/bold red]", style="red"))
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------

@app.command()
def log(
    name: str = typer.Argument(None, help="Show log for a specific plan. Omit for all."),
    last: int = typer.Option(20, "--last", "-n", help="Number of recent entries to show."),
):
    """Show the session log (audit trail of agent activity)."""
    entries = read_log(plan=name)
    if not entries:
        print("[yellow]No log entries found.[/yellow]")
        raise typer.Exit(code=0)

    # Show the last N entries.
    for entry in entries[-last:]:
        ts = entry.get("timestamp", "")[:19].replace("T", " ")
        event = entry.get("event", "?")
        plan_name = entry.get("plan", "")
        extra = ""
        if "passed" in entry:
            extra = " passed" if entry["passed"] else " FAILED"
        if "objective" in entry:
            extra = f" — {entry['objective'][:60]}"
        plan_label = f" [{plan_name}]" if plan_name else ""
        print(f"  {ts}  {event}{plan_label}{extra}")


# ---------------------------------------------------------------------------
# graph (kept for power users)
# ---------------------------------------------------------------------------

@app.command()
def graph(name: str = typer.Argument(..., help="Plan name to show dependency graph for.")):
    """Show the dependency graph for a plan."""
    plan_dir = _resolve_plan(name)
    if not plan_dir:
        print(f"[red]Plan not found: {name}[/red]")
        raise typer.Exit(code=1)

    from planguard.orchestration.plan_graph import print_analysis

    graph_obj = build_plan_graph(plan_dir)
    raise typer.Exit(code=print_analysis(graph_obj))


# ---------------------------------------------------------------------------
# guard
# ---------------------------------------------------------------------------

@app.command()
def guard(
    root: str = typer.Argument(".", help="Project root directory."),
):
    """Inspect staged (or unstaged) changes for database and schema risks.

    Use this before committing to catch database-related changes that should
    have an active plan. Unlike 'planguard check', guard works without a plan —
    it scans the git diff directly and flags migration files, schema DDL,
    and ORM migration operations regardless of whether a plan exists.

    Exits with code 1 if risky changes are found.
    """
    print(Panel("[bold]PlanGuard Guard[/bold]", style="cyan"))

    report = run_guard(root)
    if not report.flagged:
        print("[green]No database or schema risks detected in staged changes.[/green]")
        raise typer.Exit(code=0)

    print(f"[red][bold]Found {len(report.findings)} database-related change(s) that should require a plan:[/bold][/red]")
    print()
    for finding in report.findings:
        print(f"  [red][FLAGGED][/red] {finding.path}")
        print(f"           {finding.reason}")
    print()
    print(Panel(
        "[bold yellow]These changes affect database state and should not be treated as small changes.[/bold yellow]\n"
        "Create a plan first: [cyan]planguard plan[/cyan]",
        style="yellow",
    ))
    log_event("guard_flagged", details={
        "findings_count": len(report.findings),
        "paths": list({f.path for f in report.findings}),
    })
    raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# validate (kept for backward compat, but check is preferred)
# ---------------------------------------------------------------------------

@app.command()
def validate(docs_dir: str | None = typer.Argument(None, help="Plans directory to validate.")):
    """Validate all plan structures. (Prefer 'planguard check' for full checks.)"""
    ok, messages = validate_docs(docs_dir)
    for message in messages:
        print(f"[green]{message}[/green]" if ok else f"[red]{message}[/red]")
    raise typer.Exit(code=0 if ok else 2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    try:
        app()
    except Exception as exc:
        if _VERBOSE:
            raise
        print(f"[red]Unexpected internal error:[/red] {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
