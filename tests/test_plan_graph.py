from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agent_framework.orchestration.plan_graph import analyze_graph, build_plan_graph


class PlanGraphTests(unittest.TestCase):
    def test_build_plan_graph_supports_dependencies_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            plan_dir = Path(temp_dir)
            (plan_dir / "dependency_map.yaml").write_text(
                "\n".join(
                    [
                        "dependencies:",
                        "  - id: first",
                        "    depends_on: []",
                        "  - id: second",
                        "    depends_on:",
                        "      - first",
                    ]
                ),
                encoding="utf-8",
            )

            graph = build_plan_graph(plan_dir)
            self.assertIsNotNone(graph)
            self.assertEqual(analyze_graph(graph), ["Execution order:", " - first", " - second"])
