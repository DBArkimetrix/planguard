import yaml
from pathlib import Path

data=yaml.safe_load(Path("docs/planning/active_plans.yaml").read_text())

if not data["active_plans"]:
    print("No active plans. Skipping execution schedule.")
    exit(0)

plans=[p["name"] for p in data["active_plans"]]

schedule={"phase_1":plans}

Path("docs/planning/execution_schedule.yaml").write_text(
yaml.safe_dump({"execution_schedule":schedule})
)