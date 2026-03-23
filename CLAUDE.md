# CLAUDE.md

## Source of Truth

Agent rules and workflow are defined in `./AGENTS.md`.

## Quick Reference

```
planguard init          # Set up PlanGuard in a project
planguard plan          # Create a plan (interactive wizard)
planguard check         # Run all checks
planguard activate X    # Mark plan as ready to implement
planguard complete X    # Mark plan as done
planguard status        # Show all plans
```

## Instruction

Before executing any task:
1. Read AGENTS.md
2. Follow the workflow: PLAN -> CHECK -> ACTIVATE -> IMPLEMENT -> COMPLETE
