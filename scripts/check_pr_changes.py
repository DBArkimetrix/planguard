from pathlib import Path
import subprocess
import sys

import yaml


IGNORED_PREFIXES = (".venv/", "dist/")


def normalize(path: str) -> str:
    return path.replace("\\", "/")


def load_active_allowed_paths() -> tuple[set[str], list[str]]:
    active = yaml.safe_load(Path("docs/planning/active_plans.yaml").read_text(encoding="utf-8")) or {}
    plan_map = yaml.safe_load(Path("docs/planning/plan_file_map.yaml").read_text(encoding="utf-8")) or {}

    active_names = {row["name"] for row in active.get("active_plans", [])}
    rows = plan_map.get("plan_file_map", [])
    if active_names:
        rows = [row for row in rows if row["plan"] in active_names]

    allowed_paths = {normalize(path) for row in rows for path in row.get("allowed_paths", [])}
    selected_plans = [row["plan"] for row in rows]
    return allowed_paths, selected_plans


def main() -> int:
    files = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()

    allowed_paths, selected_plans = load_active_allowed_paths()
    normalized_files = [normalize(path) for path in files]

    violations = [
        file_name
        for file_name in normalized_files
        if not file_name.startswith(IGNORED_PREFIXES)
        and not any(file_name == allowed or file_name.startswith(f"{allowed}/") for allowed in allowed_paths)
    ]

    if violations:
        print("Unauthorized changes:")
        if selected_plans:
            print(f"Active plans checked: {', '.join(selected_plans)}")
        for violation in violations:
            print(violation)
        return 1

    print("All changes are within active plan ownership.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
