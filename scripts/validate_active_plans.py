from pathlib import Path
import yaml
import sys

def main():
    active = yaml.safe_load(Path("docs/planning/active_plans.yaml").read_text(encoding="utf-8"))
    mapped = yaml.safe_load(Path("docs/planning/plan_file_map.yaml").read_text(encoding="utf-8"))

    active_names = {p["name"] for p in active.get("active_plans", [])}
    mapped_names = {p["plan"] for p in mapped.get("plan_file_map", [])}

    missing = sorted(active_names - mapped_names)
    if missing:
        print("Active plans missing file mappings:")
        for m in missing:
            print(f" - {m}")
        sys.exit(1)

    print("All active plans have file mappings.")

if __name__ == "__main__":
    main()