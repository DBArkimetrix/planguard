from __future__ import annotations

from pathlib import Path

import typer
from rich import print

from agent_framework.orchestration.plan_graph import build_plan_graph, print_analysis
from agent_framework.planning.generate_plan import generate_plan
from agent_framework.validation.validate_plan import validate_docs


app = typer.Typer(help="CLI for the agent engineering framework.")


def initialize_project_structure(root: Path | str = ".") -> list[Path]:
    base = Path(root)
    directories = [
        base / "docs",
        base / "docs" / "architecture",
        base / "docs" / "planning",
        base / "docs" / "planning" / "orchestration",
        base / "docs" / "planning" / "registry",
        base / "docs" / "safety",
        base / "docs" / "testing",
        base / "docs" / "contracts",
        base / "docs" / "decision_log",
        base / "docs" / "governance",
        base / "docs" / "tasks",
        base / "scripts",
    ]
    created: list[Path] = []
    for directory in directories:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created.append(directory)

    default_files = {
        base / "docs" / "planning" / "active_plans.yaml": "active_plans: []\n",
        base / "docs" / "planning" / "plan_file_map.yaml": "plan_file_map: []\n",
        base / "docs" / "planning" / "orchestration" / "orchestration_status.yaml": (
            "orchestration_status:\n"
            "  last_run: null\n"
            "  computed_ready_plans: []\n"
            "  blocked_plans: []\n"
            "  parallel_safe_groups: []\n"
        ),
        base / "docs" / "planning" / "registry" / "active_plans.yaml": "active_plans: []\n",
        base / "docs" / "planning" / "registry" / "plan_registry.yaml": "plan_registry: []\n",
    }
    for path, contents in default_files.items():
        if not path.exists():
            path.write_text(contents, encoding="utf-8")
            created.append(path)

    return created


@app.command()
def graph(plan: str):
    graph_obj = build_plan_graph(Path("docs") / plan)
    raise typer.Exit(code=print_analysis(graph_obj))


@app.command()
def validate(docs_dir: str = "docs"):
    ok, messages = validate_docs(docs_dir)
    for message in messages:
        print(f"[green]{message}[/green]" if ok else f"[red]{message}[/red]")
    raise typer.Exit(code=0 if ok else 2)


@app.command()
def plan(name: str):
    plan_dir = generate_plan(name)
    print(f"[cyan]Created plan scaffold:[/cyan] {plan_dir}")


@app.command()
def init(root: str = "."):
    created = initialize_project_structure(root)
    if not created:
        print("[yellow]Project structure already present.[/yellow]")
        return
    print("[yellow]Initialized project structure:[/yellow]")
    for path in created:
        print(f" - {path}")


def main():
    app()


if __name__ == "__main__":
    main()
