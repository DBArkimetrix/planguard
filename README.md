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

## What To Do After `agent init` And `agent plan`

`agent init` creates the shared documentation folders. `agent plan <name>` creates a starter plan folder in `docs/<plan_name>/`.

Those commands are the beginning of the workflow, not the end of it. After `agent plan`, the next steps are:

1. Review and complete the generated files in `docs/<plan_name>/`.
2. Make sure the plan has a real scope, allowed paths, risks, backlog phases, sprint sequencing, and handoff notes.
3. Add the plan to `docs/planning/active_plans.yaml` if it is now an active piece of work.
4. Add the plan's owned paths to `docs/planning/plan_file_map.yaml` so collision checks can detect overlap.
5. Run the validation and planning checks.
6. Only then start implementation work.

Typical command sequence:

```bash
poetry run agent init
poetry run agent plan "Implement pricing engine"
poetry run agent validate
poetry run python scripts/detect_collisions.py
poetry run python scripts/build_execution_schedule.py
poetry run python scripts/compute_risk_score.py
```

Important: in the current implementation, `agent validate` checks that the required plan files exist. It does not fully block implementation by itself.

To make the workflow actually govern agent behavior, the repository the agent is editing should contain a root-level `AGENTS.md` that says, in plain terms:

- the agent must not start implementation before the plan, backlog, sprint plan, safety review, and orchestration review are complete
- the agent must create and update the required files in `docs/<plan_name>/`
- the agent must update `docs/planning/active_plans.yaml` and `docs/planning/plan_file_map.yaml` for active work
- the agent must run the validation, collision, and orchestration checks before coding
- the agent must update progress and handoff docs when the work is done

That means the workflow is enforced operationally by:

- the root `AGENTS.md` instructions in the target repository
- the generated planning artifacts in `docs/`
- human review
- the validation, collision, and orchestration scripts

When working with Codex or another coding agent, the `AGENTS.md` file should sit in the root of the repository being changed. If the agent is working in `/path/to/my-app`, use:

```text
/path/to/my-app/AGENTS.md
```

A minimal `AGENTS.md` for a project using this framework can say something like:

```md
# AGENTS.md

This repository uses the agent-engineering-framework workflow.

Mandatory workflow:
PLAN -> BACKLOG -> SPRINT PLAN -> SAFETY CHECK -> ORCHESTRATE -> IMPLEMENT -> UPDATE DOCS -> HANDOFF

Agents must not implement code until:
- docs/<plan_name>/plan.yaml exists
- docs/<plan_name>/backlog.yaml exists
- docs/<plan_name>/sprint_plan.yaml exists
- safety review artifacts are complete
- orchestration review is complete
- collision, regression, conflict, and unintended-consequence checks are reviewed

Before implementation, agents must:
- update docs/planning/active_plans.yaml
- update docs/planning/plan_file_map.yaml
- run validation and planning checks

After implementation, agents must:
- update progress.yaml
- update handoff.yaml
```

You can keep more detailed instructions in that root `AGENTS.md`, but this is the minimum level of clarity needed if you want the agent to follow the process reliably.

If you are prompting the agent directly in addition to using `AGENTS.md`, a reliable instruction looks like this:

```text
Use the AGENTS.md workflow. Do not implement yet.
First complete or update docs/<plan_name>/, update active_plans.yaml and plan_file_map.yaml,
run validation/collision/orchestration checks, and only implement after the plan is ready.
```

## Using This Framework Inside Another Repository

There are two common ways to use the framework in an existing project.

### Recommended: Copy The Workflow Into The Project Root

Put the framework's operational files in the repository that the agent will actually modify:

- `AGENTS.md`
- `docs/`
- `scripts/`
- any project-specific templates or wrappers you want to keep

This is the simplest setup because the agent sees the workflow rules and the plan artifacts in the same repository it is editing. In most cases, this is the setup you want.

### Alternative: Keep The Framework In A Nested, Ignored Folder

You can clone this repository into something like `.agent-framework/` and add that folder to `.gitignore`, but that should be treated as a source of templates and helper scripts, not as the primary instruction location for the agent.

If you use this approach:

- the repository root that the agent works in should still contain the authoritative `AGENTS.md`
- that root `AGENTS.md` can either contain the full workflow instructions or point to the vendored framework copy
- the active plan artifacts should still live in the target repository's `docs/` folder, not only inside the ignored framework clone

In practice, the safest rule is:

- put `AGENTS.md` at the root of the repository the agent is operating on
- keep the active `docs/` planning files in that same repository
- use the ignored framework clone only as a local helper/tooling source

### Where `AGENTS.md` Should Live

If Codex is opened on `/path/to/my-app`, then the file should normally be:

```text
/path/to/my-app/AGENTS.md
```

If this framework is vendored into:

```text
/path/to/my-app/.agent-framework/
```

then keep the framework copy there if you want, but also place an `AGENTS.md` in `/path/to/my-app/` so the workflow instructions apply to work across the whole repository.

If you want, you can make the root `AGENTS.md` short and use it to reference or reproduce the policy from the vendored framework copy. What matters is that the root file is present and clearly tells the agent to use the workflow before making code changes.

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
