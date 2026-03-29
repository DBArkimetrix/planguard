"""Detect path collisions between active plans.

Only considers plans with status 'draft' or 'active' — completed and
archived plans are excluded from collision checks.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from planguard.config import get_plans_root
from planguard.pathspec import paths_overlap


_ACTIVE_STATUSES = {"draft", "active"}


def _load_plan_scope(plan_dir: Path) -> dict | None:
    """Read a plan.yaml and return its name, status, and included scope paths."""
    plan_path = plan_dir / "plan.yaml"
    if not plan_path.exists():
        return None
    try:
        data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    meta = data.get("plan", {})
    status = meta.get("status", "draft")
    if status not in _ACTIVE_STATUSES:
        return None
    return {
        "plan": meta.get("name", plan_dir.name),
        "paths": data.get("scope", {}).get("included", []),
    }


def detect_collisions(docs_dir: Path | str | None = None) -> list[dict]:
    """Scan all active plans under docs_dir for overlapping scope paths."""
    if docs_dir is None:
        docs_dir = get_plans_root()
    docs_path = Path(docs_dir)
    if not docs_path.is_dir():
        return []

    plans: list[dict] = []
    for entry in sorted(docs_path.iterdir()):
        if entry.is_dir() and (entry / "plan.yaml").exists():
            info = _load_plan_scope(entry)
            if info:
                plans.append(info)

    collisions: list[dict] = []
    for i, left in enumerate(plans):
        for right in plans[i + 1:]:
            overlap: list[str] = []
            for left_path in left["paths"]:
                for right_path in right["paths"]:
                    if paths_overlap(left_path, right_path):
                        overlap.append(
                            left_path if left_path == right_path else f"{left_path} <-> {right_path}"
                        )
            if overlap:
                collisions.append({
                    "plans": [left["plan"], right["plan"]],
                    "overlap": sorted(set(overlap)),
                })

    return collisions


def main() -> int:
    collisions = detect_collisions(get_plans_root())
    if not collisions:
        print("No collisions between active plans.")
    else:
        print("Detected collisions:")
        for c in collisions:
            print(f"  {c['plans'][0]} <-> {c['plans'][1]}: {', '.join(c['overlap'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
