# PlanGuard

Plan and control how AI coding agents make changes in your project.

PlanGuard is a lightweight, language-agnostic framework that makes AI-assisted development safer and auditable. It enforces a simple rule: **plan first, then implement**.

## Why

AI agents are powerful but unconstrained. Without guardrails they can:

- Modify files you didn't intend them to touch
- Skip tests or verification steps
- Make "small" database changes that break production
- Leave no audit trail of what they did or why

PlanGuard fixes this with scope enforcement, safety checks, verification gates, and an immutable session log — all driven from the CLI, with no external services required.

## Quick Start

```bash
# Install or upgrade
pipx install planguard          # or: pip install planguard

# Set up in your project
cd /path/to/your-project
planguard init                  # detects stack, creates context files and AGENTS.md

# Plan → Check → Activate → Implement → Verify → Complete
planguard plan                  # interactive wizard to define scope, risks, verification
planguard check                 # validate structure, risk score, collisions
planguard activate my_plan      # record baseline, allow implementation
# ... now prompt the agent — see "Activation and Implementation" below ...
planguard verify my_plan        # run verification commands
planguard complete my_plan      # mark done (only if verified snapshot matches)
```

That's the whole workflow. Everything below is detail you can read as you need it.

## Install

```bash
pipx install planguard          # any project (recommended)
pip install planguard            # or as a Python dependency
poetry add --group dev planguard # or with Poetry
```

Works on Linux, macOS, and Windows. Requires Python 3.9+.

## Upgrade

Existing `0.5+` installs should upgrade in place:

```bash
pipx upgrade planguard
pip install -U planguard
poetry add --group dev planguard@latest
```

For existing repositories, prefer the scripted upgrade path:

```bash
planguard upgrade --no-wizard
planguard check
```

On legacy repositories that still keep plans under `docs/`, `planguard upgrade --no-wizard` now migrates them to the local default `.planguard/plans/`, refreshes the managed AGENTS workflow, and keeps runtime state under `.planguard/state/`.

### Manual Fallback

If you only need to refresh the managed AGENTS workflow without migrating plan storage, the manual fallback is:

```bash
planguard init --refresh-agents --no-wizard
planguard check
```

### Adopt the Newer Features

Existing plans remain compatible. Once upgraded, you can use the newer capabilities where they help:

- use `planguard plan --template <name>` for tailored plan generation
- use structured `verify_commands` entries for deterministic or shell-free verification
- add `renames:` mappings to plans that intentionally move files after activation
- use `planguard suspend <plan>` / `planguard resume <plan>` when overlapping work needs to pause safely

## Setting Up a Project

```bash
planguard init
```

The wizard scans your repo, detects languages, frameworks, test/build commands, and creates:

| File | Purpose |
|------|---------|
| `AGENTS.md` | Workflow rules that AI agents read before working |
| `.planguard/project.yaml` | System description and detected stack |
| `.planguard/conventions.md` | Coding patterns and style constraints |
| `.planguard/boundaries.md` | Files/directories agents must never modify |
| `.planguard/policies.yaml` | Governance rules (database, security, custom) |
| `.gitignore` | Updated to keep local plans and runtime state out of commits |
| `.planguard/state/active_plans.yaml` | Local runtime registry of active plans |

Review these files, then commit them. Any agent that reads `AGENTS.md` will follow the workflow.

## Creating a Plan

Run the wizard yourself:

```bash
planguard plan
```

Or tell the agent to create one:

```text
Read AGENTS.md and the .planguard context. Create a PlanGuard plan for
"add JWT authentication to the API". Do not change application code yet.
```

Or skip the wizard entirely:

```bash
planguard plan "jwt-auth" --objective "Add JWT auth" --scope "src/api, tests" --priority high --no-wizard
```

Each plan produces:

- `<plans_root>/<plan_name>/plan.yaml` for the local plan definition
- `.planguard/state/plans/<plan_name>/status.yaml` for local runtime progress state

That split is intentional: keep both plan definitions and runtime churn local by default, while only the install scaffold stays commit-worthy.

By default, plan definitions are stored under `.planguard/plans/` and ignored via `.gitignore`. If you need a different local path, create `.planguard/config.yaml`:

```yaml
plans_root: .planguard/plans    # or any relative path
```

### Templates

Use `--template` to generate plans tailored to specific change types:

```bash
planguard plan --template docs-only "update-readme" --objective "..." --no-wizard
planguard plan --template schema-change "add-users-table" --objective "..." --no-wizard
```

Available templates: `default`, `docs-only`, `refactor`, `schema-change`, `service-integration`. Each adjusts the generated phases, risks, and test strategy. When omitted, `default` is used — identical to the current behaviour.

Review the plan before activating.

## Running Checks

```bash
planguard check              # all plans
planguard check my_plan      # specific plan
```

Checks: structure validation, risk scoring (severity-weighted, threshold 6), dependency graph cycles, scope collisions between plans, scope drift after activation, policy and boundary enforcement.

## Activation and Implementation

```bash
planguard activate my_plan
```

This re-runs checks, records a git-backed baseline, and marks the plan as active. Only now may the agent write code — and only within the declared scope. If the agent needs to touch files outside scope, update the plan first.

Example first prompt after activation:

```text
The plan is now active. Implement the approved work for <plan_name>.
Only modify files inside the declared scope, update or add tests as
needed, run the relevant checks, and summarize what changed.
```

After implementation:

```bash
planguard verify my_plan     # runs verify_commands, records passing snapshot
planguard complete my_plan   # succeeds only if snapshot still matches
```

## Small Changes

Not everything needs a plan. Typos, single-line fixes, formatting, and config tweaks can proceed directly.

**Exception: database and schema changes are never small.** Even adding a single column can require a migration, lock a table, or break downstream consumers. See [Database Safety](#database-safety) below.

## Database Safety

PlanGuard ships with default protections for database work:

- **Migration policy** — plans touching `migrations/**`, `alembic/**`, or `**/migrations/**` are flagged as high-risk
- **Schema-change policy** — diffs containing SQL DDL or ORM migration operations are flagged
- **Migration boundary** — `migrations/` is off-limits without an active plan

These are enforced by `planguard check` when a plan exists. For changes that bypass planning entirely, use **guard**:

```bash
planguard guard
```

Guard scans the staged diff (or unstaged changes) for migration files, schema DDL, and ORM operations — no plan required. It exits with code 1 if anything is found, making it suitable as a pre-commit hook.

## Security

PlanGuard is not a security scanner — use [Bandit](https://bandit.readthedocs.io/), [Semgrep](https://semgrep.dev/), or [CodeQL](https://codeql.github.com/) for that. But it complements them in two ways:

1. **Policy rules** — `.planguard/policies.yaml` includes commented-out security rules you can enable (hardcoded secrets, SQL injection, eval/exec, shell injection, disabled auth). These are regex-based guardrails, not a substitute for AST-aware analysis.

2. **Verification commands** — add security scanners to a plan's `verify_commands` (e.g., `bandit -r src/ -ll`) so they run during `planguard verify` and become part of the auditable lifecycle.

## Verification Commands

`verify_commands` in `plan.yaml` supports three formats:

```yaml
verify_commands:
  # Plain string — runs via default shell (backward compatible)
  - "pytest tests/ -v"

  # Shell command with explicit interpreter — avoids cross-platform shell issues
  - command: "Get-ChildItem *.ps1 | ForEach-Object { & $_.FullName }"
    interpreter: pwsh
    timeout: 120

  # Structured assertion — no shell, declarative
  - check: file_exists
    path: src/config.py
  - check: text_contains
    path: README.md
    pattern: "## Installation"
  - check: file_moved
    from: src/old_module.py
    to: src/new_module.py
  - check: text_not_contains
    path: src/app.py
    pattern: "TODO: remove"
```

Available structured checks: `file_exists`, `file_not_exists`, `file_moved`, `text_contains`, `text_not_contains`.

The `interpreter` field solves cross-platform issues: when set, the command runs as `[interpreter, "-c", command]` instead of through the default system shell. Use `bash`, `sh`, `pwsh`, `python3`, or any executable on `PATH`.

All three formats can be mixed in the same list. Existing plans with plain string commands continue to work unchanged.

## Policies and Boundaries

`.planguard/policies.yaml` defines pattern-based rules enforced by `planguard check`. Rules can `block` or `require_approval`, and are scoped to specific paths. Content-pattern rules are evaluated against actual changed files after activation.

`.planguard/boundaries.md` lists files and directories agents must never modify. If a plan's scope overlaps a boundary, `planguard check` blocks it.

## Plan Lifecycle

Every plan moves through: **draft** → **active** → **completed** → **archived**

| Status | Meaning |
|--------|---------|
| `draft` | Plan exists, not yet approved for implementation |
| `active` | Checks passed, implementation allowed |
| `suspended` | Paused — other plans can proceed on overlapping scope |
| `completed` | Work done, verified |
| `archived` | Removed from active consideration |

### Suspend and Resume

When one plan needs to pause while a smaller change goes through:

```bash
planguard suspend my_plan --reason "waiting on API deploy"
# ... other work proceeds, even on overlapping scope ...
planguard resume my_plan                    # picks up where it left off
planguard resume my_plan --refresh-baseline # re-capture baseline if repo changed significantly
```

Suspended plans retain their activation data and are excluded from collision detection.

## Multiple Plans

Each piece of work gets its own plan with a declared scope. `planguard check` detects when two active plans have overlapping paths — collisions must be resolved before both can be active. `planguard status` shows a table of all plans.

## Session Log

Every lifecycle event is logged to `.planguard/state/log.jsonl` — an append-only audit trail of what happened, when, and against which git state.

```bash
planguard log                # all events
planguard log my_plan        # filter by plan
```

## All Commands

```bash
planguard init                    # Set up PlanGuard in a project (wizard)
planguard plan                    # Create a plan (wizard)
planguard plan --template <name>  # Create from template: docs-only, refactor, schema-change, service-integration
planguard check [name]            # Run all checks, or check a specific plan
planguard activate <name>         # Mark plan as ready to implement
planguard verify <name>           # Run verification commands (strings, interpreter, or structured checks)
planguard complete <name>         # Mark plan as done (auto-fills handoff metadata)
planguard suspend <name>          # Pause plan, unblock overlapping work
planguard resume <name>           # Resume a suspended plan
planguard archive <name>          # Archive a plan
planguard guard                   # Scan staged diff for database/schema risks
planguard status                  # Table of all plans with status, priority, owner
planguard list [--all]            # List plans (--all includes completed/archived)
planguard log [name]              # Show session log (optionally filtered by plan)
planguard graph <name>            # Show dependency graph for a plan
```

## Compatibility

PlanGuard works with any agent that reads `AGENTS.md` — Claude, Codex, Cursor, Copilot, and others. It incorporates practices from the [OpenAI Codex cookbook](https://developers.openai.com/codex/learn/best-practices) and [Claude Code best practices](https://code.claude.com/docs/en/best-practices).

## Disabling or Removing

**Override the risk threshold** — add `risk_threshold: 12` to the `plan:` section of any `plan.yaml` (default is 6).

**Remove PlanGuard** — delete `.planguard/`, the PlanGuard section from `AGENTS.md`, and uninstall the CLI (`pipx uninstall planguard`).

## Requirements

- Python 3.9 or newer
- Works on Linux, macOS, and Windows
- No system dependencies beyond Python

## License

MIT
