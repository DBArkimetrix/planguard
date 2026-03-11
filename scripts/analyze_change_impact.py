import subprocess
import yaml
from pathlib import Path

def get_changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        capture_output=True,
        text=True
    )
    return result.stdout.splitlines()

def load_boundaries():
    return yaml.safe_load(
        Path("docs/architecture/system_boundaries.yaml").read_text()
    )

def detect_systems(changed_files, boundaries):
    impacted=set()

    for file in changed_files:
        for system,info in boundaries["systems"].items():
            for path in info["paths"]:
                if file.startswith(path):
                    impacted.add(system)

    return impacted

def downstream_systems(impacted,boundaries):

    downstream=set()

    for system in impacted:
        info=boundaries["systems"].get(system,{})
        for d in info.get("downstream",[]):
            downstream.add(d)

    return downstream

def main():

    files=get_changed_files()

    boundaries=load_boundaries()

    impacted=detect_systems(files,boundaries)

    downstream=downstream_systems(impacted,boundaries)

    print("\nChanged files:")
    for f in files:
        print(f)

    print("\nImpacted systems:")
    for s in impacted:
        print(s)

    print("\nPotential downstream impact:")
    for d in downstream:
        print(d)

if __name__=="__main__":
    main()