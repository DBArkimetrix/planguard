"""Compute a risk score from a plan's risks section.

Reads risks directly from plan.yaml rather than requiring a separate file.
Severity weights: low=1, medium=2, high=3, critical=5.
"""

from __future__ import annotations

from pathlib import Path

import yaml


_SEVERITY_WEIGHTS = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 5,
}

DEFAULT_THRESHOLD = 6


def compute_risk_score(
    plan_dir: Path | str,
    threshold: int = DEFAULT_THRESHOLD,
) -> tuple[int, str, list[dict]]:
    """Compute risk score for a plan.

    Returns (total_score, status, risk_details) where status is 'pass' or 'blocked'.
    """
    plan_path = Path(plan_dir) / "plan.yaml"
    if not plan_path.exists():
        return 0, "pass", []

    data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    risks = data.get("risks", [])

    # Allow per-plan threshold override via plan.yaml
    plan_meta = data.get("plan", {})
    if isinstance(plan_meta, dict) and "risk_threshold" in plan_meta:
        threshold = int(plan_meta["risk_threshold"])

    details: list[dict] = []
    total = 0
    for risk in risks:
        severity = risk.get("severity", "medium").lower()
        weight = _SEVERITY_WEIGHTS.get(severity, 2)
        total += weight
        details.append({
            "id": risk.get("id", "unknown"),
            "severity": severity,
            "weight": weight,
            "description": risk.get("description", ""),
            "mitigation": risk.get("mitigation", ""),
        })

    status = "pass" if total <= threshold else "blocked"
    return total, status, details


def main() -> int:
    import sys

    plan_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs")
    # If pointed at docs/, check all plans.
    if plan_dir.name == "docs":
        for entry in sorted(plan_dir.iterdir()):
            if entry.is_dir() and (entry / "plan.yaml").exists():
                total, status, _ = compute_risk_score(entry)
                print(f"  {entry.name}: score={total} status={status}")
        return 0

    total, status, details = compute_risk_score(plan_dir)
    print(f"Risk score: {total}")
    print(f"Status: {status}")
    for d in details:
        print(f"  {d['id']} ({d['severity']}={d['weight']}): {d['description']}")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
