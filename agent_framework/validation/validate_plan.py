from __future__ import annotations

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


def discover_plan_dirs(docs_dir: Path) -> list[Path]:
    return [path for path in docs_dir.iterdir() if path.is_dir() and (path / "plan.yaml").exists()]


def validate_docs(docs_dir: Path | str = "docs") -> tuple[bool, list[str]]:
    docs_path = Path(docs_dir)
    messages: list[str] = []

    if not docs_path.exists():
        messages.append("No docs directory detected. Skipping validation.")
        return True, messages

    plan_dirs = discover_plan_dirs(docs_path)
    if not plan_dirs:
        messages.append("No plan directories detected. Skipping validation.")
        return True, messages

    errors = False
    for plan_dir in plan_dirs:
        missing = [name for name in REQUIRED if not (plan_dir / name).exists()]
        if missing:
            errors = True
            messages.append(f"Plan validation failed: {plan_dir}")
            messages.append("Missing required files:")
            messages.extend(f" - {name}" for name in missing)

    if not errors:
        messages.append("All plan structures valid.")

    return not errors, messages


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    docs_dir = Path(args[0]) if args else Path("docs")
    ok, messages = validate_docs(docs_dir)
    for message in messages:
        print(message)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
