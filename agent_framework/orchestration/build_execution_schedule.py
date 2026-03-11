from __future__ import annotations

from pathlib import Path

import yaml


def build_execution_schedule(active_plans_path: Path | str = "docs/planning/active_plans.yaml") -> dict:
    data = yaml.safe_load(Path(active_plans_path).read_text(encoding="utf-8")) or {}
    plans = [row["name"] for row in data.get("active_plans", [])]
    if not plans:
        return {}
    return {"phase_1": plans}


def main() -> int:
    schedule = build_execution_schedule()
    if not schedule:
        print("No active plans. Skipping execution schedule.")
        return 0

    Path("docs/planning/execution_schedule.yaml").write_text(
        yaml.safe_dump({"execution_schedule": schedule}, sort_keys=False),
        encoding="utf-8",
    )
    print("Execution schedule written to docs/planning/execution_schedule.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
