from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from planguard.orchestration.plan_graph import analyze_graph, build_plan_graph


class PlanGraphTests(unittest.TestCase):
    def test_build_plan_graph_supports_dependencies_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            plan_dir = Path(temp_dir)
            (plan_dir / "dependency_map.yaml").write_text(
                "\n".join([
                    "dependencies:",
                    "  - id: first",
                    "    depends_on: []",
                    "  - id: second",
                    "    depends_on:",
                    "      - first",
                ]),
                encoding="utf-8",
            )

            graph = build_plan_graph(plan_dir)
            self.assertIsNotNone(graph)
            self.assertEqual(
                analyze_graph(graph),
                ["Execution order:", " - first", " - second"],
            )

    def test_build_plan_graph_reads_plan_yaml_dependencies(self) -> None:
        """The new plan format stores dependencies inside plan.yaml."""
        with TemporaryDirectory() as temp_dir:
            plan_dir = Path(temp_dir)
            (plan_dir / "plan.yaml").write_text(
                "\n".join([
                    "plan:",
                    "  name: test",
                    "  status: draft",
                    "dependencies:",
                    "  - id: analysis",
                    "    depends_on: []",
                    "  - id: implementation",
                    "    depends_on:",
                    "      - analysis",
                ]),
                encoding="utf-8",
            )

            graph = build_plan_graph(plan_dir)
            self.assertIsNotNone(graph)
            messages = analyze_graph(graph)
            self.assertIn(" - analysis", messages)
            self.assertIn(" - implementation", messages)
