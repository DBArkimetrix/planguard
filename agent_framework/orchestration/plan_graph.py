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


def build_plan_graph(plan_dir: Path | str):
    plan_file = Path(plan_dir) / "dependency_map.yaml"
    if not plan_file.exists():
        print("No dependency map found.")
        return None

    data = yaml.safe_load(plan_file.read_text(encoding="utf-8"))
    graph = nx.DiGraph()

    for task in _iter_dependency_items(data):
        task_id = task.get("id") or task.get("component")
        if not task_id:
            continue
        graph.add_node(task_id)
        for dependency in task.get("depends_on", []):
            graph.add_edge(dependency, task_id)

    return graph


def analyze_graph(graph) -> list[str]:
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


def print_analysis(graph) -> int:
    messages = analyze_graph(graph)
    if not messages:
        return 0
    for message in messages:
        print(message)
    return 1 if messages[0].startswith("ERROR:") else 0
