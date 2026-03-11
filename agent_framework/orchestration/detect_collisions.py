from __future__ import annotations

from pathlib import Path

import yaml


def detect_collisions(plan_file_map_path: Path | str = "docs/planning/plan_file_map.yaml") -> list[dict]:
    data = yaml.safe_load(Path(plan_file_map_path).read_text(encoding="utf-8")) or {}
    rows = data.get("plan_file_map", [])
    collisions: list[dict] = []

    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            overlap = sorted(set(left.get("allowed_paths", [])).intersection(right.get("allowed_paths", [])))
            if overlap:
                collisions.append(
                    {
                        "plans": [left["plan"], right["plan"]],
                        "overlap": overlap,
                    }
                )

    return collisions


def main() -> int:
    registry_path = Path("docs/planning/collision_registry.yaml")
    collisions = detect_collisions()
    if not collisions:
        print("No plan collisions detected.")
    else:
        print("Detected plan collisions:")
        for collision in collisions:
            print(f" - {collision['plans'][0]} vs {collision['plans'][1]}: {', '.join(collision['overlap'])}")

    registry_path.write_text(yaml.safe_dump({"collisions": collisions}, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
