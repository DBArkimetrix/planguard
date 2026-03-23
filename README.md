# PlanGuard

Control how AI coding agents make changes in your project.

PlanGuard makes AI-assisted development safer without turning it into paperwork. It records intent up front, then enforces the controls that matter against the real git-backed working state: scope drift, protected areas, verification, and an auditable lifecycle log.

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

## Adding to an Existing Project

### Step 1: Navigate to your project

```bash
cd /path/to/your-project
```

### Step 2: Run init

```bash
planguard init
```

The wizard:
1. **Scans your project** — detects language, frameworks, source/test directories, build/test/lint commands, git status, CI/CD config
2. **Shows what it found** and asks you to confirm
3. **Creates three things:**
   - `docs/` — where plans will live
   - `.planguard/` — project context that agents read before working
   - `AGENTS.md` — workflow rules (appended if the file already exists)

**What gets added to your repo:**

```
your-project/
  AGENTS.md                          <-- new, or appended to
  .planguard/
    project.yaml                     <-- what this system does, detected stack
    conventions.md                   <-- coding patterns and style rules
    boundaries.md                    <-- files/dirs agents must never modify
    glossary.md                      <-- domain terms mapped to code entities
    policies.yaml                    <-- governance rules (pattern-based checks)
  docs/
    planning/
      active_plans.yaml              <-- plan registry
  ... your existing files unchanged
```

The `.planguard/` context files are generated with your detected stack pre-filled, but you should review and complete them. The boundaries and conventions files are especially important — they tell agents what's off-limits and what patterns to follow.

If AGENTS.md already exists, PlanGuard appends its section (marked with an HTML comment for idempotent re-runs). Your existing rules stay intact.

### Step 3: Commit the framework files

```bash
git add AGENTS.md docs/
git commit -m "Add PlanGuard"
```

Now every AI agent that reads `AGENTS.md` (Claude, Codex, Copilot Workspace, etc.) will see the workflow rules before it starts coding.

## Starting a New Project

```bash
mkdir my-new-project && cd my-new-project
git init
planguard init
```

The wizard detects an empty project and asks what language/stack you plan to use. It creates the same `docs/` and `AGENTS.md` structure.

## Creating a Plan

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

- `docs/<plan_name>/plan.yaml` — objective, scope, phases, risks, dependencies, test strategy
- `docs/<plan_name>/status.yaml` — progress tracking and handoff notes

**Agents and scripts** can skip the wizard by passing flags:

```bash
planguard plan "your plan name" --objective "Describe the goal" --scope "src/api, tests" --priority high --no-wizard
```

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

## Activating and Implementing

When checks pass:

```bash
planguard activate your_plan_name
```

This re-runs checks, then marks the plan as active. The agent can now implement.

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
planguard init  -->  planguard plan  -->  planguard check  -->  planguard activate  -->  implement  -->  planguard check  -->  planguard verify  -->  planguard complete
```

| Step | What happens |
|------|-------------|
| `planguard init` | Detects project, creates docs/, .planguard/ context, and AGENTS.md |
| `planguard plan` | Wizard creates plan.yaml and status.yaml |
| `planguard check` | Validates structure, dependencies, declared scope, and for active plans enforces real post-activation changes against scope/policies/boundaries |
| `planguard activate` | Runs checks, records a baseline git snapshot, marks plan as ready to implement |
| implement | The agent (or you) writes code within the plan's scope |
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
