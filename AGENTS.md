# AGENTS.md

This repository uses a strict documentation-first workflow.

## Mandatory workflow

PLAN → BACKLOG → SPRINT PLAN → SAFETY CHECK → ORCHESTRATE → IMPLEMENT → UPDATE DOCS → HANDOFF

Implementation must never begin until all of the following are true:

1. A plan exists in /docs/<plan_name>/plan.yaml
2. A phased backlog exists in /docs/<plan_name>/backlog.yaml
3. A sprint plan exists in /docs/<plan_name>/sprint_plan.yaml
4. Safety review artifacts are complete
5. Orchestration status confirms the plan is ready
6. Collision, regression, conflict, and unintended-consequence checks have been reviewed

## Required planning expectations

After planning, the next mandatory step is to create:

- a phased backlog
- a sprint plan sequenced for robust testing
- explicit checks for:
  - collisions
  - conflicts
  - regressions
  - security risks
  - architectural inconsistencies
  - data integrity risks
  - unintended consequences

## Required plan files

Each plan folder must contain:

- plan.yaml
- acklog.yaml
- sprint_plan.yaml
- progress.yaml
- handoff.yaml
- isk_register.yaml
- egression_test_plan.yaml
- dependency_map.yaml
- collision_detection.yaml

## Safety gate

Implementation is blocked until the safety gate passes.

## Orchestration

Before implementation, agents must review plan dependencies, ownership, collisions, and execution sequencing.

## Forbidden actions

Agents must not:

- implement code without a plan
- skip backlog or sprint planning
- ignore safety or orchestration review
- modify blocked surfaces without documentation
- leave unfinished work undocumented
