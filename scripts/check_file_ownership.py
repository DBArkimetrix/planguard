from pathlib import Path
import yaml

def main():
    path = Path("docs/planning/orchestration/file_ownership_map.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    owners = data.get("file_ownership", [])
    print("Registered ownership areas:")
    for row in owners:
        print(f"- {row['area']} -> {row['primary_owner_plan']}")

if __name__ == "__main__":
    main()

