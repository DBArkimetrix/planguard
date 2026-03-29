"""Build an execution schedule from active plans.

Groups plans by priority and filters out completed/archived plans.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from planguard.config import get_execution_schedule_path, get_plans_root


_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_ACTIVE_STATUSES = {"draft", "active"}


def build_execution_schedule(docs_dir: Path | str | None = None) -> dict:
    """Read all plan.yaml files and return a prioritised execution schedule.

    Only plans with status draft or active are included.
    """
    if docs_dir is None:
        docs_dir = get_plans_root()
    docs_path = Path(docs_dir)
    if not docs_path.is_dir():
        return {}

    plans: list[dict] = []
    for entry in sorted(docs_path.iterdir()):
        plan_path = entry / "plan.yaml"
        if not entry.is_dir() or not plan_path.exists():
            continue
        try:
            data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue

        meta = data.get("plan", {})
        status = meta.get("status", "draft")
        if status not in _ACTIVE_STATUSES:
            continue

        plans.append({
            "name": meta.get("name", entry.name),
            "priority": meta.get("priority", "medium"),
            "status": status,
        })

    if not plans:
        return {}

    # Sort by priority, then name.
    plans.sort(key=lambda p: (_PRIORITY_ORDER.get(p["priority"], 2), p["name"]))

    # Group into phases by priority tier.
    phases: dict[str, list[str]] = {}
    for plan in plans:
        tier = plan["priority"]
        phase_key = f"phase_{tier}"
        phases.setdefault(phase_key, []).append(plan["name"])

    return phases


def main() -> int:
    schedule = build_execution_schedule()
    if not schedule:
        print("No active plans to schedule.")
        return 0

    print("Execution schedule:")
    for phase, names in schedule.items():
        print(f"  {phase}: {', '.join(names)}")

    # Write to file.
    out_path = get_execution_schedule_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump({"execution_schedule": schedule}, sort_keys=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
