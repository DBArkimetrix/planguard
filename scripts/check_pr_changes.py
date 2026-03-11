import subprocess
import yaml
from pathlib import Path
import sys

files=subprocess.run(
["git","diff","--name-only","origin/main"],
capture_output=True,text=True
).stdout.splitlines()

plan=yaml.safe_load(Path("docs/planning/plan_file_map.yaml").read_text())

allowed=plan["plan_file_map"][0]["allowed_paths"]

violations=[f for f in files if not any(f.startswith(p) for p in allowed)]

if violations:
    print("Unauthorized changes:")
    for v in violations:
        print(v)
    sys.exit(1)