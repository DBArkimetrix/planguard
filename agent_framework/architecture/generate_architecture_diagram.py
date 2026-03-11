from __future__ import annotations

from pathlib import Path

import yaml


def load_boundaries(path: Path | str = "docs/architecture/system_boundaries.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def build_mermaid(boundaries: dict) -> str:
    lines = ["graph TD"]
    systems = boundaries.get("systems", {})
    for system, info in systems.items():
        for downstream in info.get("downstream", []):
            lines.append(f"{system} --> {downstream}")
    return "\n".join(lines)


def main() -> int:
    boundaries = load_boundaries()
    diagram = build_mermaid(boundaries)
    output = Path("docs/architecture/system_graph.mmd")
    output.write_text(diagram, encoding="utf-8")
    print("Architecture diagram generated:")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
