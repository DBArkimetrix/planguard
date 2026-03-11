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

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_plan.py docs/<plan_name>")
        sys.exit(1)

    plan_dir = Path(sys.argv[1])
    missing = [f for f in REQUIRED if not (plan_dir / f).exists()]
    if missing:
        print("Missing required files:")
        for f in missing:
            print(f" - {f}")
        sys.exit(2)

    print("Plan structure validation passed.")

if __name__ == "__main__":
    main()
