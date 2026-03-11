from pathlib import Path
import yaml

data=yaml.safe_load(Path("docs/planning/plan_file_map.yaml").read_text())

rows=data["plan_file_map"]

if not rows:
    print("No plans registered. Skipping collision detection.")
    exit(0)

collisions=[]

for i in range(len(rows)):
    for j in range(i+1,len(rows)):
        a=rows[i]
        b=rows[j]

        overlap=set(a["allowed_paths"]).intersection(set(b["allowed_paths"]))

        if overlap:
            collisions.append({
                "plans":[a["plan"],b["plan"]],
                "overlap":list(overlap)
            })

Path("docs/planning/collision_registry.yaml").write_text(
yaml.safe_dump({"collisions":collisions})
)