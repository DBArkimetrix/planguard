# AGENTS.md

<!-- agent-engineering-framework -->

## PlanGuard

This repository uses a documentation-first workflow for AI agent work.

### Commands

Build:
  poetry install

Test:
  poetry run pytest tests/ -v

### Workflow

PLAN -> CHECK -> ACTIVATE -> IMPLEMENT -> COMPLETE

Before writing any code, agents must:

1. Create a plan: `planguard plan`
2. Run checks: `planguard check`
3. Activate the plan: `planguard activate <plan_name>`
4. Only then begin implementation

After implementation, agents must:

1. Run verification: `planguard verify <plan_name>`
2. Update status.yaml with completed steps
3. Mark the plan complete: `planguard complete <plan_name>`

### Rules

- Never implement without an active plan
- Never skip the check step
- Never modify files outside the plan's declared scope
- Always document risks and test strategy before coding
- Never complete a plan without a passing verification run
- Update handoff notes when the work is done
- Always add any handoff document you create to `.gitignore`
- When changing the package version, always keep package metadata and runtime version reporting in sync

### Best Practices

- Read existing code before proposing changes
- Use a local `HANDOFF*.md` file for temporary transition notes when needed
- For releases, update both `pyproject.toml` and `planguard/__init__.py` together
- Write or update tests for every change
- Run the test suite and confirm it passes before marking work complete
- Keep changes small, scoped, and independently verifiable
- Commit with descriptive messages that explain why, not just what
- If something breaks, fix it before moving on
