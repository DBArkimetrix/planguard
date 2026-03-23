# PlanGuard

Plan and control how AI coding agents make changes in your project.

PlanGuard is a lightweight framework for AI-assisted development. It helps a developer or agent define the work first, approve the scope, implement against that plan, and prove the result before closing the change.

In practice, the workflow is:

1. Run `planguard init` to add project context and agent rules to the repo.
2. Create a plan with `planguard plan`, then review the generated scope, backlog, sprints, risks, and verification commands. See [Ask the Agent to Create the Plan](#ask-the-agent-to-create-the-plan).
3. Run `planguard check` and `planguard activate <plan_name>`. See [Running Checks](#running-checks).
4. Only after activation should you start prompting the agent to implement. For the detailed rules and the first implementation prompt, see [When the Agent Is Allowed to Change Code](#when-the-agent-is-allowed-to-change-code) and [Activate the Plan and Implement](#activate-the-plan-and-implement).
5. Run `planguard verify <plan_name>` and `planguard complete <plan_name>` to record the proof and close the work. See [Activate the Plan and Implement](#activate-the-plan-and-implement).

The framework stays tied to git, your IDE, and your normal CLI workflow. Its main controls are scope enforcement, protected-area checks, verification, and an auditable lifecycle log.

Works with any language or stack. Runs on Linux, macOS, and Windows.

## Install

### For any project (recommended)

Use [pipx](https://pipx.pypa.io/) to install the `planguard` command globally without touching your project's dependencies:

```bash
pipx install planguard
```

This works whether your project is Python, JavaScript, Rust, Go, Java, or anything else. The `planguard` command is available system-wide.

### For Python projects

Add it as a dev dependency:

```bash
pip install planguard
```

Or with Poetry:

```bash
poetry add --group dev planguard
```

### Windows

The same commands work in PowerShell or Windows Terminal:

```powershell
pipx install planguard
```

Or with pip:

```powershell
pip install planguard
```

Requires Python 3.9 or newer. If you don't have Python, install it from [python.org](https://www.python.org/downloads/) or via `winget install Python.Python.3.12`.

### Verify

```bash
planguard --help
planguard --version
```

## End-to-End Workflow

PlanGuard is meant to fit around normal git and IDE work. The sequence is:

1. Put PlanGuard into the repo.
2. Give the agent enough context to plan safely.
3. Have the agent create or refine a plan.
4. Review the plan.
5. Run `planguard check`.
6. Run `planguard activate <plan_name>`.
7. Only after activation may the agent change code or docs in scope.
8. Run `planguard verify <plan_name>`.
9. Run `planguard complete <plan_name>`.

If you skip the planning or activation steps, the agent should not implement.

## Put PlanGuard in an Existing Project

### Step 1: Open the repository

```bash
cd /path/to/your-project
```

### Step 2: Initialize PlanGuard

```bash
planguard init
```

The wizard:
1. Scans your repo for language, framework, source paths, test paths, build/test/lint commands, git status, and CI config.
2. Shows what it detected so you can confirm or correct it.
3. Writes the framework files the agent will use.

**What gets added to your repo:**

```
your-project/
  AGENTS.md                          <-- new, or appended to
  .planguard/
    project.yaml                     <-- what this system does, detected stack
    conventions.md                   <-- coding patterns and style rules
    boundaries.md                    <-- files/dirs agents must never modify
    glossary.md                      <-- domain terms mapped to code entities
    policies.yaml                    <-- governance rules
  docs/
    planning/
      active_plans.yaml              <-- plan registry
  ... your existing files unchanged
```

### Step 3: Review the generated context

Before asking an agent to plan or code, review:
- `.planguard/project.yaml`
- `.planguard/conventions.md`
- `.planguard/boundaries.md`
- `.planguard/policies.yaml`
- `AGENTS.md`

This is where you tell the agent what the system does, what patterns to follow, and what must not be changed.

### Step 4: Commit the framework files

```bash
git add AGENTS.md .planguard docs/
git commit -m "Add PlanGuard"
```

From this point on, any agent that reads `AGENTS.md` can follow the same workflow rules.

## Put PlanGuard in a New Project

### Step 1: Create the repository

```bash
mkdir my-new-project
cd my-new-project
git init
```

### Step 2: Initialize PlanGuard

```bash
planguard init
```

In a new repo, the wizard will ask what stack or language you expect to use and create the same `.planguard/`, `docs/`, and `AGENTS.md` structure.

### Step 3: Fill in the project context

For a new project, this step matters more because there is less code for the agent to infer from. Add enough detail that the first plan can be grounded in reality:
- system purpose
- main modules or layers you expect
- naming and code conventions
- directories the agent must never touch
- required tests and quality gates

### Step 4: Commit the framework files

```bash
git add AGENTS.md .planguard docs/
git commit -m "Initialize PlanGuard project context"
```

## Ask the Agent to Create the Plan

PlanGuard expects the agent to plan before it edits. You can either run the plan wizard yourself or ask the agent to do it.

### Option 1: You run the wizard

```bash
planguard plan
```

The wizard walks you through:

| Question | What it's for |
|----------|--------------|
| What is the objective? | A plain-language description of what you want to accomplish |
| Short name for this plan | Creates a folder like `docs/your_plan_name/` |
| Which directories are in scope? | Restricts what the agent is allowed to modify (auto-detected from your project) |
| Priority | low, medium, high, or critical |
| Who owns this plan? | Person or team responsible |
| How will you know this is done? | Observable conditions that must be true before the work is complete |
| Commands to verify correctness | Test/lint commands to run (auto-detected from your project) |
| How would you undo this? | Rollback strategy if things go wrong |
| Known risks? | Optional: describe risks and how to mitigate them |

The wizard creates two files:

- `docs/<plan_name>/plan.yaml` — objective, scope, phases, backlog, sprints, risks, dependencies, test strategy
- `docs/<plan_name>/status.yaml` — progress tracking and handoff notes

PlanGuard now treats that backlog-and-sprints shape as the required plan format. Older plan-only layouts are not supported.

### Option 2: The agent runs the command

Tell the agent to read `AGENTS.md` and create the plan before making changes. Example:

```text
Read AGENTS.md and the .planguard context. Create a PlanGuard plan for "add JWT authentication to the API". Propose scope, backlog items, sprints, risks, done criteria, and verification commands. Do not change application code yet.
```

If the agent already knows the objective and likely scope, it can skip the wizard:

```bash
planguard plan "your plan name" --objective "Describe the goal" --scope "src/api, tests" --priority high --no-wizard
```

### What the developer should review before approving the plan

Open `docs/<plan_name>/plan.yaml` and confirm:
- the objective is correct
- the scope only includes the files and directories you want touched
- the backlog and sprints are broken into sensible slices
- the risks are real and not generic filler
- the verification commands will actually prove the change works

Until this review is done, the agent should still be in planning mode, not implementation mode.

## Running Checks

```bash
planguard check
```

Runs everything at once and prints a pass/fail report:

```
Plan: your_plan_name
  [OK] Structure valid
  [OK] Risk score: 2 (threshold: 6)
  [OK] Dependency graph is acyclic
  Status: draft

Cross-plan checks:
  No collisions between active plans

All checks passed
```

What it checks:
- **Validation** — plan.yaml has all required sections
- **Risk score** — severity-weighted total vs threshold
- **Dependency graph** — no circular dependencies
- **Collisions** — no two active plans declare overlapping paths
- **Scope drift** — active-plan changes after activation must stay inside scope
- **Policies and boundaries** — protected areas and content rules can be enforced against real changed files

Check a specific plan:

```bash
planguard check your_plan_name
```

## When the Agent Is Allowed to Change Code

The answer should be simple:

- Before `planguard activate <plan_name>`: the agent may read files, analyze the repo, and create or refine the plan.
- After `planguard activate <plan_name>`: the agent may implement, but only inside the declared scope.

Activation is the point where planning ends and implementation is allowed.

## Activate the Plan and Implement

```bash
planguard activate your_plan_name
```

This re-runs checks, records the git-backed baseline, and marks the plan as active.

Only at this stage should you start prompting the agent to implement the change. The first implementation prompt should tell the agent to work from the approved plan, stay inside scope, update tests, and report what it changed.

Example initial implementation prompt:

```text
The plan is now active. Implement the approved work for <plan_name>. Only modify files inside the declared scope, update or add tests as needed, run the relevant checks, and summarize what changed and anything still pending.
```

What to do next:

1. Open the files listed in the plan scope.
2. Let the agent implement only that planned slice of work.
3. Run the normal edit, test, and diff loop in your IDE or CLI.
4. If the agent needs to touch files outside scope, stop and update the plan first.
5. Run `planguard check your_plan_name` again before verification.

After implementation:

```bash
planguard verify your_plan_name
planguard complete your_plan_name
```

`verify` records the exact git-backed snapshot that passed. `complete` only succeeds if the current state still matches that verified snapshot.

## PyPI Distribution

PlanGuard is packaged for PyPI through the metadata in `pyproject.toml` and the console script entry point:

```bash
poetry build
```

This produces both an sdist and a wheel in `dist/`. Before publishing, validate the artifacts:

```bash
python -m twine check dist/*
```

## Workflow

```
install PlanGuard  -->  planguard init  -->  create/refine plan  -->  planguard check  -->  planguard activate  -->  agent implements in scope  -->  planguard check  -->  planguard verify  -->  planguard complete
```

| Step | What happens |
|------|-------------|
| install PlanGuard | Install the `planguard` CLI with `pipx`, `pip`, or Poetry |
| `planguard init` | Detects the project, creates `.planguard/` context, creates `docs/`, and writes `AGENTS.md` rules |
| create/refine plan | The developer or agent creates `plan.yaml` and `status.yaml`; the agent may analyze but must not implement yet |
| `planguard check` | Validates structure, dependencies, scope, and for active plans enforces real changes against scope, policies, and boundaries |
| `planguard activate` | Re-runs checks, records a baseline git snapshot, and explicitly allows implementation |
| agent implements in scope | The agent may now change code, tests, or docs, but only in the declared scope |
| `planguard verify` | Runs verification commands and stores the exact snapshot that passed |
| `planguard complete` | Marks plan as done only if the verified snapshot still matches the current state |

## Plan Lifecycle

Every plan has a status: **draft -> active -> completed -> archived**

| Status | Meaning |
|--------|---------|
| `draft` | Plan exists but is not yet approved for implementation |
| `active` | Checks passed, implementation is allowed |
| `completed` | Work is done |
| `archived` | Removed from all active consideration |

Only `draft` and `active` plans appear in collision checks and scheduling.

## All Commands

```bash
planguard init                    # Set up PlanGuard in a project (wizard)
planguard plan                    # Create a plan (wizard)
planguard check                   # Run all checks (structure, risk, collisions, scope/policy enforcement)
planguard check <name>            # Check a specific plan
planguard activate <name>         # Mark plan as ready to implement
planguard verify <name>           # Run verification commands from the plan
planguard complete <name>         # Mark plan as done
planguard archive <name>          # Archive a plan
planguard status                  # Table of all plans with status, priority, owner
planguard list                    # List active plans
planguard list --all              # Include completed and archived
planguard log                     # Show session log (audit trail)
planguard log <name>              # Show log for a specific plan
planguard graph <name>            # Show dependency graph for a plan
planguard validate                # Validate plan structure (prefer 'planguard check')
```

## How Multiple Plans Work

When several agents or developers work in the same repo:

1. Each piece of work gets its own plan (`planguard plan`)
2. Each plan declares which directories it will modify (the scope)
3. `planguard check` detects when two active plans have overlapping or nested scope
4. Collisions must be resolved (change scope or sequence the work) before both plans can be active
5. `planguard status` shows a table of all plans and their state
6. Completed plans stop interfering with active work

## Plan Files

Each plan is two files:

**plan.yaml** — everything about the plan:

```yaml
plan:
  name: your_plan_name
  status: draft
  created: '2025-03-23'
  owner: your-team
  priority: high

objective: Describe what you are trying to accomplish

scope:
  included:
    - src/your_module
    - tests/your_module
  excluded:
    - unrelated modules

phases:
  - name: analysis
    tasks:
      - Analyze current implementation
      - Identify dependencies
  - name: implementation
    tasks:
      - Implement changes in safe slices
  - name: validation
    tasks:
      - Run regression tests

backlog:
  - id: BL-001
    title: Analyze scope, architecture touchpoints, and test impact
    type: analysis
    phase: analysis
    scope:
      - src/your_module
      - tests/your_module
    depends_on: []
    deliverables:
      - Impacted modules and dependencies are identified
    tests:
      - Identify the regression coverage that must be preserved before coding begins
    done_when:
      - The implementation approach is clear

  - id: BL-002
    title: Implement changes in src/your_module
    type: implementation
    phase: implementation
    scope:
      - src/your_module
    depends_on: [BL-001]
    deliverables:
      - Code changes in src/your_module are implemented in safe, reviewable slices
    tests:
      - Add or update focused regression tests covering src/your_module
    done_when:
      - The planned work for src/your_module is complete

  - id: BL-003
    title: Run verification, regression checks, and handoff review
    type: validation
    phase: validation
    scope:
      - src/your_module
      - tests/your_module
    depends_on: [BL-002]
    deliverables:
      - Verification commands pass
    tests:
      - npm test
      - npm run lint
    done_when:
      - All tests pass

sprints:
  - id: SPRINT-01
    name: Discovery and test design
    goal: Confirm scope, architecture impact, and required regression coverage before implementation starts.
    backlog_items: [BL-001]
    focus_paths:
      - src/your_module
      - tests/your_module
    exit_criteria:
      - The implementation approach is clear

  - id: SPRINT-02
    name: Implementation slice 1
    goal: Deliver a reviewable subset of the planned change set with matching test updates.
    backlog_items: [BL-002]
    focus_paths:
      - src/your_module
    exit_criteria:
      - The planned work for src/your_module is complete

  - id: SPRINT-03
    name: Verification and handoff
    goal: Prove the change set works, document residual risk, and prepare completion.
    backlog_items: [BL-003]
    focus_paths:
      - src/your_module
      - tests/your_module
    exit_criteria:
      - All tests pass

risks:
  - id: RISK-001
    description: May break existing functionality
    severity: high
    mitigation: Add regression tests before making changes

done_when:
  - All tests pass
  - No regressions in existing functionality

verify_commands:
  - npm test
  - npm run lint

rollback_strategy: git revert to prior commit

dependencies:
  - id: analysis
    depends_on: []
  - id: implementation
    depends_on: [analysis]
  - id: validation
    depends_on: [implementation]

test_strategy:
  - area: Existing functionality in scope paths
    validation: Confirm no unintended behaviour changes
```

**status.yaml** — progress tracking:

```yaml
status:
  phase: planning
  progress_percent: 0

activation:
  activated_at: ''
  git_branch: ''
  git_head: ''
  baseline_changed_files: []
  baseline_fingerprints: {}

verification:
  passed: false
  last_run: ''
  git_branch: ''
  git_head: ''
  changed_files: []
  fingerprints: {}
  commands: []

completed_steps: []
remaining_steps:
  - Review and refine plan
  - Run checks (planguard check)
  - Activate plan (planguard activate)
  - Implement
  - Verify (planguard verify)
  - Complete plan (planguard complete)

blockers: []

handoff:
  summary: ''
  notes: []
```

## Verification

After implementation, run the plan's verification commands:

```bash
planguard verify your_plan_name
```

This runs every command listed in `verify_commands` from plan.yaml and reports pass/fail. If the plan omitted them, PlanGuard falls back to detected project test/lint commands when it can:

```
Running: pytest
  [OK] pytest
Running: npm run lint
  [OK] npm run lint

Verification passed
```

Verification must pass before you mark the plan complete.

## Policies and Boundaries

`.planguard/policies.yaml` defines rules that `planguard check` enforces. Scope-only rules can gate sensitive paths before implementation; pattern rules are evaluated against actual changed files after activation:

```yaml
rules:
  - name: no_raw_sql
    description: "Do not use raw SQL queries"
    pattern: "execute.*SELECT|INSERT|UPDATE|DELETE"
    scope: ["src/**/*.py"]
    action: block

  - name: migration_requires_approval
    description: "Database migrations need human approval"
    scope: ["migrations/**"]
    action: require_approval
    risk: high
```

`.planguard/boundaries.md` defines files and directories that agents must never modify. If a plan's scope overlaps with a boundary, `planguard check` blocks it.

## Session Log

Every lifecycle event is logged to `.planguard/log.jsonl`:

```bash
planguard log                     # Show all events
planguard log your_plan_name      # Filter by plan
```

Output:

```
  2025-03-23 14:02  plan_created [your_plan_name] — Describe the goal
  2025-03-23 14:05  plan_activated [your_plan_name]
  2025-03-23 15:30  verification [your_plan_name] passed
  2025-03-23 15:31  plan_completed [your_plan_name]
```

This is your audit trail — what the agent did, when, whether it worked, and which git state it was operating against.

## What AGENTS.md Does

`AGENTS.md` is a convention that AI coding agents read before they start working. It tells them:

- Do not write code without a plan
- Run checks before implementing
- Stay within the plan's declared scope
- Verify before completing

The `planguard init` command generates this file. You can customise it for your team's specific rules. Any AI agent that respects project-root instruction files (Claude, Codex, Copilot, etc.) will follow it.

## Compatibility with Agent Cookbooks

PlanGuard incorporates best practices from the [OpenAI Codex cookbook](https://developers.openai.com/codex/learn/best-practices) and [Claude Code best practices](https://code.claude.com/docs/en/best-practices):

| Practice | How PlanGuard implements it |
|----------|-------------------------------|
| Include build/test/lint commands in agent instructions | `planguard init` detects your stack and writes commands into AGENTS.md |
| Define observable "done when" criteria | The plan wizard asks "How will you know this is done?" |
| Include verification commands | The wizard asks for commands to verify correctness |
| Explore before editing | AGENTS.md best practices section includes this rule |
| Validation-gated progression | `planguard activate` runs checks before allowing implementation |
| Scope changes to declared paths | plan.yaml declares included/excluded paths |
| Keep a written record of risks and decisions | plan.yaml captures risks, mitigation, and test strategy |
| Write or update tests for every change | Encoded in AGENTS.md best practices and plan test_strategy |

PlanGuard works with any agent that reads AGENTS.md (Codex, Claude, Cursor, Copilot, etc.). If your project also uses CLAUDE.md, PlanGuard detects it and does not interfere — AGENTS.md and CLAUDE.md serve complementary roles.

## Requirements

- Python 3.9 or newer
- Works on Linux, macOS, and Windows
- No system dependencies beyond Python

## License

MIT
