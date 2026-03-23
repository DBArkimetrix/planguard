from __future__ import annotations

from pathlib import Path
import subprocess

import yaml


def get_changed_files(base_ref: str = "origin/main") -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line]


def load_boundaries(path: Path | str = "docs/architecture/system_boundaries.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def detect_systems(changed_files: list[str], boundaries: dict) -> set[str]:
    impacted: set[str] = set()
    systems = boundaries.get("systems", {})

    for file_name in changed_files:
        for system, info in systems.items():
            for path in info.get("paths", []):
                if file_name.startswith(path):
                    impacted.add(system)
    return impacted


def downstream_systems(impacted: set[str], boundaries: dict) -> set[str]:
    downstream: set[str] = set()
    for system in impacted:
        info = boundaries.get("systems", {}).get(system, {})
        downstream.update(info.get("downstream", []))
    return downstream


def analyze_change_impact(base_ref: str = "origin/main") -> tuple[list[str], list[str], list[str]]:
    files = get_changed_files(base_ref)
    boundaries = load_boundaries()
    impacted = sorted(detect_systems(files, boundaries))
    downstream = sorted(downstream_systems(set(impacted), boundaries))
    return files, impacted, downstream


def main() -> int:
    files, impacted, downstream = analyze_change_impact()

    print("Changed files:")
    for file_name in files:
        print(file_name)

    print("\nImpacted systems:")
    for system in impacted:
        print(system)

    print("\nPotential downstream impact:")
    for system in downstream:
        print(system)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
