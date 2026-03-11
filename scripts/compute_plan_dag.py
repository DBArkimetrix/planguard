from pathlib import Path
import yaml

def main():
    path = Path("docs/planning/graphs/plan_dependency_graph.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    plans = data.get("plan_dependency_graph", {}).get("plans", [])

    print("Plan dependency summary:")
    for p in plans:
        print(f"- {p['plan']} depends_on={p.get('depends_on', [])}")

if __name__ == "__main__":
    main()

