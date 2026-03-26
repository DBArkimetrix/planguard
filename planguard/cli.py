"""CLI for PlanGuard.

Provides an interactive wizard-driven workflow for setting up governance,
creating plans, running checks, and managing plan lifecycle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
import yaml
from rich import print
from rich.panel import Panel
from rich.table import Table

from planguard import __version__
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
from planguard.safety.git_state import get_git_snapshot
from planguard.safety.guard import run_guard
from planguard.validation.validate_plan import (
    discover_plan_dirs,
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
) -> None:
    """PlanGuard commands."""


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
        "2. Update status.yaml with completed steps and handoff notes",
        "3. Mark the plan complete: `planguard complete <plan_name>`",
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
    return Path("docs")


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
    status_path = plan_dir / "status.yaml"
    if not status_path.exists():
        return {}
    return yaml.safe_load(status_path.read_text(encoding="utf-8")) or {}


def _write_status_yaml(plan_dir: Path, data: dict) -> None:
    (plan_dir / "status.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capture_git_state() -> dict:
    snapshot = get_git_snapshot()
    return {
        "is_git_repo": snapshot.get("is_git_repo", False),
        "git_branch": snapshot.get("branch", ""),
        "git_head": snapshot.get("head", ""),
        "changed_files": snapshot.get("changed_files", []),
        "fingerprints": snapshot.get("fingerprints", {}),
        "captured_at": _now_iso(),
    }


def _plan_bookkeeping_files(plan_dir: Path) -> set[str]:
    return {
        f"docs/{plan_dir.name}/plan.yaml",
        f"docs/{plan_dir.name}/status.yaml",
        "docs/planning/active_plans.yaml",
        ".planguard/log.jsonl",
    }


def _files_changed_since_activation(plan_dir: Path, current_snapshot: dict) -> list[str]:
    status_data = _read_status_yaml(plan_dir)
    activation = status_data.get("activation", {})
    baseline = activation.get("baseline_fingerprints", {}) if isinstance(activation, dict) else {}
    if not isinstance(activation, dict) or not activation.get("activated_at"):
        return []
    if not baseline:
        return sorted(set(current_snapshot.get("changed_files", [])))

    changed: list[str] = []
    for path in current_snapshot.get("changed_files", []):
        current_fingerprint = current_snapshot.get("fingerprints", {}).get(path)
        if current_fingerprint != baseline.get(path):
            changed.append(path)
    return sorted(set(changed))


def _scope_mismatches(plan_dir: Path, scope_paths: list[str], file_paths: list[str]) -> list[str]:
    ignored = _plan_bookkeeping_files(plan_dir)
    out_of_scope: list[str] = []
    for path in file_paths:
        if path in ignored:
            continue
        if any(path_matches(path, scope_path) for scope_path in scope_paths):
            continue
        out_of_scope.append(path)
    return sorted(set(out_of_scope))


def _verification_matches_current_state(plan_dir: Path) -> bool:
    status_data = _read_status_yaml(plan_dir)
    verification = status_data.get("verification", {})
    if not isinstance(verification, dict) or not verification.get("passed"):
        return False

    current = _capture_git_state()
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
    registry_path = _docs_dir() / "planning" / "active_plans.yaml"
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
):
    """Set up PlanGuard in a project.

    Detects the project's stack and structure, then creates docs/,
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
    dirs_to_create = [
        base / "docs",
        base / "docs" / "planning",
    ]
    created: list[Path] = []
    for d in dirs_to_create:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(d)

    # Seed active_plans.yaml.
    registry = base / "docs" / "planning" / "active_plans.yaml"
    if not registry.exists():
        registry.write_text("active_plans: []\n", encoding="utf-8")
        created.append(registry)

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
            print("[dim]AGENTS.md already contains the framework workflow. Skipping.[/dim]")
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
    print(Panel(
        "[bold]Next step:[/bold] Create a plan with [cyan]planguard plan[/cyan]",
        style="green",
    ))


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
    no_wizard: bool = typer.Option(False, "--no-wizard", help="Skip interactive questions."),
):
    """Create a new plan. Launches an interactive wizard when run without flags."""
    print(Panel("[bold]New Plan[/bold]", style="cyan"))
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
        docs_dir=_docs_dir(),
    )

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
    data = _read_plan_yaml(plan_dir)
    status = data.get("plan", {}).get("status", "unknown")
    current_snapshot = _capture_git_state()
    diff_paths = _files_changed_since_activation(plan_dir, current_snapshot) if status == "active" else []

    # 1. Validation.
    ok, messages = validate_plan(plan_dir)
    if ok:
        print(f"{_PASS} Structure valid")
    else:
        print(f"{_FAIL} Structure invalid")
        for m in messages:
            print(f"    {m}")
        all_ok = False

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
    scope_paths = data.get("scope", {}).get("included", [])
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
def status():
    """Show all plans and their current status."""
    docs = _docs_dir()
    plan_dirs = discover_plan_dirs(docs)

    if not plan_dirs:
        print("[yellow]No plans found. Run 'planguard plan' to create one.[/yellow]")
        raise typer.Exit(code=0)

    table = Table(title="Plans")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Priority")
    table.add_column("Owner")
    table.add_column("Phase")

    for pd in plan_dirs:
        data = _read_plan_yaml(pd)
        meta = data.get("plan", {})

        # Read status.yaml for phase info.
        status_path = pd / "status.yaml"
        phase = "—"
        if status_path.exists():
            try:
                sdata = yaml.safe_load(status_path.read_text(encoding="utf-8")) or {}
                phase = sdata.get("status", {}).get("phase", "—")
            except Exception:
                pass

        plan_status = meta.get("status", "unknown")
        status_style = {
            "draft": "yellow",
            "active": "green",
            "completed": "dim",
            "archived": "dim",
        }.get(plan_status, "white")

        table.add_row(
            meta.get("name", pd.name),
            f"[{status_style}]{plan_status}[/{status_style}]",
            meta.get("priority", "—"),
            meta.get("owner", "—"),
            phase,
        )

    print(table)


# ---------------------------------------------------------------------------
# activate
# ---------------------------------------------------------------------------

@app.command()
def activate(name: str = typer.Argument(..., help="Plan name to activate.")):
    """Mark a plan as active (ready for implementation)."""
    plan_dir = _resolve_plan(name)
    if not plan_dir:
        print(f"[red]Plan not found: {name}[/red]")
        raise typer.Exit(code=1)

    current = _read_plan_yaml(plan_dir).get("plan", {}).get("status")
    if current == "active":
        print(f"[yellow]{name} is already active.[/yellow]")
        raise typer.Exit(code=0)

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
    baseline = _capture_git_state()
    status_data["activation"] = {
        "activated_at": baseline["captured_at"],
        "git_branch": baseline["git_branch"],
        "git_head": baseline["git_head"],
        "baseline_changed_files": baseline["changed_files"],
        "baseline_fingerprints": baseline["fingerprints"],
    }
    _write_status_yaml(plan_dir, status_data)
    log_event("plan_activated", plan=name, details={
        "baseline_changed_files": baseline["changed_files"],
    })
    print()
    print(f"[green]{name} is now active. You may begin implementation.[/green]")


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

    current = _read_plan_yaml(plan_dir).get("plan", {}).get("status")
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
# list
# ---------------------------------------------------------------------------

@app.command(name="list")
def list_plans(
    show_all: bool = typer.Option(False, "--all", "-a", help="Include completed and archived plans."),
):
    """List plans, filtered by status."""
    docs = _docs_dir()
    plan_dirs = discover_plan_dirs(docs)
    if not plan_dirs:
        print("[yellow]No plans found.[/yellow]")
        raise typer.Exit(code=0)

    for pd in plan_dirs:
        data = _read_plan_yaml(pd)
        meta = data.get("plan", {})
        plan_status = meta.get("status", "unknown")
        if not show_all and plan_status in ("completed", "archived"):
            continue
        priority = meta.get("priority", "—")
        print(f"  {plan_status}  {meta.get('name', pd.name)}  (priority: {priority})")


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@app.command()
def verify(name: str = typer.Argument(..., help="Plan name to verify.")):
    """Run the plan's verify_commands and report results.

    This confirms that the implementation actually works. Verification must
    pass before marking a plan complete.
    """
    import subprocess

    plan_dir = _resolve_plan(name)
    if not plan_dir:
        print(f"[red]Plan not found: {name}[/red]")
        raise typer.Exit(code=1)

    data = _read_plan_yaml(plan_dir)
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
    for cmd in commands:
        print(f"[bold]Running:[/bold] {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
        )
        passed = result.returncode == 0
        results.append({"command": cmd, "passed": passed, "returncode": result.returncode})

        if passed:
            print(f"{_PASS} {cmd}")
        else:
            print(f"{_FAIL} {cmd} (exit code {result.returncode})")
            if result.stdout.strip():
                # Show last few lines of output.
                lines = result.stdout.strip().splitlines()
                for line in lines[-5:]:
                    print(f"    {line}")
            if result.stderr.strip():
                lines = result.stderr.strip().splitlines()
                for line in lines[-5:]:
                    print(f"    {line}")
            all_passed = False

    status_data = _read_status_yaml(plan_dir)
    verification_snapshot = _capture_git_state()
    status_data["verification"] = {
        "passed": all_passed,
        "last_run": _now_iso(),
        "git_branch": verification_snapshot["git_branch"],
        "git_head": verification_snapshot["git_head"],
        "changed_files": verification_snapshot["changed_files"],
        "fingerprints": verification_snapshot["fingerprints"],
        "commands": commands,
    }
    if all_passed:
        status_data.setdefault("completed_steps", [])
        if "Verify (planguard verify)" not in status_data["completed_steps"]:
            status_data["completed_steps"].append("Verify (planguard verify)")
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
def validate(docs_dir: str = typer.Argument("docs", help="Docs directory to validate.")):
    """Validate all plan structures. (Prefer 'planguard check' for full checks.)"""
    ok, messages = validate_docs(docs_dir)
    for message in messages:
        print(f"[green]{message}[/green]" if ok else f"[red]{message}[/red]")
    raise typer.Exit(code=0 if ok else 2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app()


if __name__ == "__main__":
    main()
