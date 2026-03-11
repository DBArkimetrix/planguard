from pathlib import Path
import sys

REQUIRED = [
    "plan.yaml",
    "backlog.yaml",
    "sprint_plan.yaml",
    "progress.yaml",
    "handoff.yaml",
    "risk_register.yaml",
    "regression_test_plan.yaml",
    "dependency_map.yaml",
    "collision_detection.yaml",
]

docs_dir = Path("docs")

if not docs_dir.exists():
    print("No docs directory detected. Skipping validation.")
    sys.exit(0)

plan_dirs = []

for p in docs_dir.iterdir():
    if p.is_dir() and (p / "plan.yaml").exists():
        plan_dirs.append(p)

if not plan_dirs:
    print("No plan directories detected. Skipping validation.")
    sys.exit(0)

errors = False

for plan_dir in plan_dirs:

    missing = [f for f in REQUIRED if not (plan_dir / f).exists()]

    if missing:
        print(f"\nPlan validation failed: {plan_dir}")
        print("Missing required files:")

        for f in missing:
            print(f" - {f}")

        errors = True

if errors:
    sys.exit(2)

print("All plan structures valid.")