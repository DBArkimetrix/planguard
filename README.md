# AI Agent Engineering Framework

A way to control how AI coding agents make changes in a software project.

If you are using an AI agent to write code, this framework gives the agent a process to follow before it starts changing files. Instead of letting the agent jump straight into implementation, you require it to first write down the plan, list the work in phases, check for risks, and confirm that its changes will not collide with other work.

The framework enforces a documentation-first workflow:

`PLAN -> BACKLOG -> SPRINT PLAN -> SAFETY CHECK -> ORCHESTRATE -> IMPLEMENT -> UPDATE DOCS -> HANDOFF`

In plain terms, this tool is for teams who want AI agents to behave more like careful contributors and less like unchecked autocomplete.

## What This Is For

Use this framework when:

- you want an AI agent to propose work before touching the code
- you want a human to review the work plan before implementation starts
- several agents or people may work in the same repository at the same time
- you want a written record of risks, dependencies, testing, and handoff

Do not think of this as the thing that builds your product. Think of it as the rulebook and paperwork system that sits around the agent and controls how the agent is allowed to work.

## How A Non-Programmer Would Use It

1. You give the agent a task, such as "add a customer billing feature" or "fix the approval workflow."
2. The agent uses this framework to create a folder in `docs/<plan_name>/` for that task.
3. Inside that folder, the agent must write the plan, backlog, sprint plan, risk review, regression test plan, and handoff documents.
4. A human reviews those documents to make sure the task is sensible, safe, and not overlapping with other work.
5. Only after that review passes should the agent start changing code.
6. When the work is done, the agent updates the progress and handoff documents so the next person can see what changed and what risks remain.

The main idea is simple: make the agent explain itself before it acts.

## What It Provides

- templates and commands for creating the required planning documents
- checks that confirm the required documents exist before implementation
- collision checks to spot when two plans may touch the same area
- orchestration support so active plans can be sequenced safely
- architecture and change-impact analysis helpers
- a CLI and script wrappers so agents can run the workflow consistently

## Installation

For local development in this repository:

```bash
poetry install
```

Run the CLI in the Poetry environment:

```bash
poetry run agent --help
poetry run agent validate
```

If you need to build distribution artifacts locally:

```bash
poetry build
```

Alternative editable install without Poetry:

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

Typical use with an agent:

- ask the agent to create a plan first
- review the generated documents in `docs/<plan_name>/`
- ask the agent to run validation and safety checks
- only then allow implementation work

```bash
poetry run agent init
poetry run agent plan "Implement pricing engine"
poetry run agent validate
poetry run agent graph example_plan
```

Equivalent module entrypoint:

```bash
poetry run python -m agent_framework.cli --help
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
