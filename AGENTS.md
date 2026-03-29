# AGENTS.md

<!-- agent-engineering-framework -->

## Agent Engineering Framework

This repository uses a documentation-first workflow for AI agent work.

### Commands

Build:
  poetry install

Test:
  poetry run python -m unittest

### Workflow

PLAN -> CHECK -> ACTIVATE -> IMPLEMENT -> COMPLETE

For non-trivial changes (new features, refactors, multi-file edits), agents must:

1. Create a plan: `planguard plan`
2. Run checks: `planguard check`
3. Activate the plan: `planguard activate <plan_name>`
4. Only then begin implementation

For small changes (typos, single-line fixes, formatting, config tweaks), agents may proceed directly without a plan.
However, database and schema changes are never small — even adding a single field requires a plan.
When in doubt, run `planguard guard` to check.

After implementation, agents must:

1. Run verification: `planguard verify <plan_name>`
2. Update runtime status and handoff notes
3. Mark the plan complete: `planguard complete <plan_name>`

Useful variations:

- Use `planguard plan --template <name>` for docs-only, refactor, schema-change, and service-integration work
- Use `planguard suspend <plan_name>` / `planguard resume <plan_name>` when overlapping work needs to pause safely

### Rules

- Never implement without an active plan
- Never skip the check step
- Never modify files outside the plan's declared scope
- Always document risks and test strategy before coding
- Never complete a plan without a passing verification run
- Update handoff notes when the work is done

### Best Practices

- Read existing code before proposing changes
- Write or update tests for every change
- Run the test suite and confirm it passes before marking work complete
- Keep changes small, scoped, and independently verifiable
- Commit with descriptive messages that explain why, not just what
- If something breaks, fix it before moving on

