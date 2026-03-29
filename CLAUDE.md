# CLAUDE.md

## Source of Truth

Agent rules and workflow are defined in `./AGENTS.md`.

## Quick Reference

```
planguard init          # Set up PlanGuard in a project
planguard init --refresh-agents  # Refresh the managed AGENTS.md workflow after upgrading
planguard upgrade       # Script the 0.5+ repository upgrade steps
planguard plan          # Create a plan (interactive wizard)
planguard plan --template <type>  # docs-only, refactor, schema-change, service-integration
planguard check         # Run all checks
planguard activate X    # Mark plan as ready to implement
planguard verify X      # Run verification commands
planguard complete X    # Mark plan as done
planguard suspend X     # Pause plan, unblock overlapping work
planguard resume X      # Resume a suspended plan
planguard guard         # Scan staged diff for database/schema risks
planguard status        # Show all plans
```

Plans are stored locally under `.planguard/plans/` by default and ignored via `.gitignore`.

## Instruction

For non-trivial changes (new features, refactors, multi-file edits):
1. Read AGENTS.md
2. Follow the workflow: PLAN -> CHECK -> ACTIVATE -> IMPLEMENT -> COMPLETE

For small changes (typos, single-line fixes, formatting, config tweaks):
- Proceed directly — no plan required.
- Exception: database/schema changes always require a plan. Run `planguard guard` if unsure.
