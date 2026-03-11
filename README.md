# AI Agent Engineering Framework

A lightweight governance framework for safely using AI coding agents in software projects.

The framework enforces a documentation-first workflow:

`PLAN -> BACKLOG -> SPRINT PLAN -> SAFETY CHECK -> ORCHESTRATE -> IMPLEMENT -> UPDATE DOCS -> HANDOFF`

It is designed for repositories where AI agents and human developers need explicit planning, collision detection, safety review, and orchestration before code changes are implemented.

## What It Provides

- Plan scaffolding under `docs/<plan_name>/`
- Plan validation against required workflow artifacts
- Collision detection across registered plan ownership
- Execution scheduling for active plans
- Architecture impact analysis from changed files
- A package CLI plus compatible `scripts/*.py` wrappers

## Installation

For local development in this repository:

```bash
pip install -r requirements.txt
pip install -e .
```

For package usage in another repository:

```bash
pip install agent-engineering-framework
```

## CLI Usage

The installed console script is `agent`.

```bash
agent init
agent plan "Implement pricing engine"
agent validate
agent graph example_plan
```

Equivalent module entrypoint:

```bash
python -m agent_framework.cli --help
```

## Legacy Script Wrappers

The repository also keeps script wrappers for direct invocation from the repo root:

```bash
python scripts/generate_plan.py "Implement pricing engine"
python scripts/validate_plan.py
python scripts/compute_risk_score.py
python scripts/detect_collisions.py
python scripts/build_execution_schedule.py
python scripts/analyze_change_impact.py
python scripts/generate_architecture_diagram.py
```

## Required Plan Files

Each implementation plan must contain:

```text
docs/<plan_name>/
    plan.yaml
    backlog.yaml
    sprint_plan.yaml
    progress.yaml
    handoff.yaml
    risk_register.yaml
    regression_test_plan.yaml
    dependency_map.yaml
    collision_detection.yaml
```

## Typical Workflow

1. Initialize the framework structure if the repository does not already contain it.
2. Generate a plan scaffold.
3. Complete backlog, sprint, safety, and orchestration artifacts.
4. Run validation and collision checks.
5. Implement only after the safety gate and orchestration status are ready.
6. Update progress and handoff artifacts before merge.

## Notes

- `agent graph` reads `dependency_map.yaml` entries with `id` and optional `depends_on`.
- `scripts/check_pr_changes.py` validates changes against the active plans listed in `docs/planning/active_plans.yaml`.
- The Python `graphviz` dependency provides diagram generation support; rendering images may still require the Graphviz system binary on the host machine.

## License

MIT
