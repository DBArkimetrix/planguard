"""Build and analyze a directed acyclic graph of plan dependencies."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import yaml


def _iter_dependency_items(data: dict | None) -> list[dict]:
    if not data:
        return []
    if isinstance(data.get("tasks"), list):
        return data["tasks"]
    if isinstance(data.get("dependencies"), list):
        return data["dependencies"]
    return []


def build_plan_graph(plan_dir: Path | str) -> nx.DiGraph | None:
    """Build a dependency graph from a plan directory.

    Checks for dependencies in:
      1. dependency_map.yaml (legacy)
      2. plan.yaml (new consolidated format)
    """
    plan_dir = Path(plan_dir)
    data: dict | None = None

    # Try legacy dependency_map.yaml first.
    dep_map = plan_dir / "dependency_map.yaml"
    if dep_map.exists():
        data = yaml.safe_load(dep_map.read_text(encoding="utf-8"))

    # Fall back to plan.yaml dependencies section.
    if not _iter_dependency_items(data):
        plan_path = plan_dir / "plan.yaml"
        if plan_path.exists():
            data = yaml.safe_load(plan_path.read_text(encoding="utf-8"))

    items = _iter_dependency_items(data)
    if not items:
        return None

    graph = nx.DiGraph()
    for task in items:
        task_id = task.get("id") or task.get("component")
        if not task_id:
            continue
        graph.add_node(task_id)
        for dependency in task.get("depends_on", []):
            graph.add_edge(dependency, task_id)

    return graph


def analyze_graph(graph: nx.DiGraph | None) -> list[str]:
    if graph is None:
        return []

    messages: list[str] = []
    if not nx.is_directed_acyclic_graph(graph):
        messages.append("ERROR: Circular dependency detected")
        return messages

    messages.append("Execution order:")
    for step in nx.topological_sort(graph):
        messages.append(f" - {step}")
    return messages


def print_analysis(graph: nx.DiGraph | None) -> int:
    messages = analyze_graph(graph)
    if not messages:
        return 0
    for message in messages:
        print(message)
    return 1 if messages[0].startswith("ERROR:") else 0
