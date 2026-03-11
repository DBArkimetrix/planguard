import yaml
from pathlib import Path

def load_boundaries():
    path = Path("docs/architecture/system_boundaries.yaml")
    return yaml.safe_load(path.read_text())

def build_mermaid(boundaries):

    lines = []
    lines.append("graph TD")

    systems = boundaries["systems"]

    for system, info in systems.items():

        downstream = info.get("downstream", [])

        for d in downstream:
            lines.append(f"{system} --> {d}")

    return "\n".join(lines)

def main():

    boundaries = load_boundaries()

    diagram = build_mermaid(boundaries)

    output = Path("docs/architecture/system_graph.mmd")

    output.write_text(diagram)

    print("Architecture diagram generated:")
    print(output)

if __name__ == "__main__":
    main()