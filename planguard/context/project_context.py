"""Manage the .planguard/ project context directory.

The project context captures what AI agents need to know about a codebase
before they start working: what the system does, what conventions to follow,
what's off-limits, and what domain terms mean in code.

Files:
  .planguard/project.yaml     — system purpose, stack, architecture overview
  .planguard/conventions.md   — coding patterns, naming, style constraints
  .planguard/boundaries.md    — files/modules the agent must never modify
  .planguard/glossary.md      — domain terms mapped to code entities
  .planguard/policies.yaml    — governance rules (pattern-based checks)
  .planguard/log.jsonl        — append-only session history
"""

from __future__ import annotations

from pathlib import Path

import yaml


CONTEXT_DIR = ".planguard"

# Stubs generated during init — the human (or agent) refines them.

_PROJECT_YAML_TEMPLATE = """\
# What does this system do?
# Fill this in so that agents understand the codebase before they touch it.

system:
  name: "{name}"
  description: ""

stack:
  languages: {languages}
  frameworks: {frameworks}

architecture:
  source_dirs: {source_dirs}
  test_dirs: {test_dirs}
  entry_points: []

notes: |
  # Add anything an agent should know before working in this repo.
  # Examples: "The billing module talks to Stripe via src/billing/gateway.py",
  # "All database access goes through the ORM, never raw SQL."
"""

_CONVENTIONS_MD_TEMPLATE = """\
# Conventions

<!-- What patterns, naming rules, and style constraints apply to this project? -->
<!-- Agents read this before writing code. Only include rules they can't infer from the code itself. -->

## Naming
- (e.g. snake_case for Python, camelCase for JS, etc.)

## Patterns
- (e.g. "All API handlers go in src/api/", "Use dependency injection for services")

## Testing
- (e.g. "Every module has a matching test file in tests/", "Use fixtures, not mocks")

## Commits
- (e.g. "Conventional commits: feat:, fix:, chore:", "Reference ticket IDs")
"""

_BOUNDARIES_MD_TEMPLATE = """\
# Boundaries

<!-- What must agents NEVER modify? List files, directories, or patterns. -->
<!-- This is a hard rule — agents must refuse to touch these even if asked. -->

## Off-limits files
- (e.g. .env, credentials.json, production config)

## Off-limits directories
- migrations/ — database migrations require an active plan
- (e.g. vendor/, third_party/)

## Off-limits patterns
- (e.g. "Do not modify authentication logic without security review")
- Do not delete or rename database columns without an active plan
"""

_GLOSSARY_MD_TEMPLATE = """\
# Glossary

<!-- Map domain terms to code entities so agents understand your business language. -->

| Term | Code entity | Notes |
|------|------------|-------|
| (e.g. Customer) | (e.g. src/models/customer.py) | (e.g. Includes both B2B and B2C) |
"""

_POLICIES_YAML_TEMPLATE = """\
# Governance policies — checked automatically by `planguard check`.
# Add pattern-based rules to block or flag risky changes.

rules:
  - name: migration_requires_plan
    description: "Database migrations require an active plan"
    scope: ["migrations/**", "alembic/**", "**/migrations/**"]
    action: require_approval
    risk: high

  - name: schema_change_requires_plan
    description: "Database schema changes require an active plan"
    pattern: "CREATE TABLE|ALTER TABLE|DROP TABLE|ADD COLUMN|DROP COLUMN|CREATE INDEX|DROP INDEX"
    scope: ["**/*.sql", "**/*.py"]
    action: require_approval
    risk: high

  # Security examples — uncomment rules relevant to your project:
  #
  # - name: no_hardcoded_secrets
  #   description: "Do not hardcode API keys, tokens, or passwords"
  #   pattern: "(api_key|apikey|secret_key|password|token)\\s*=\\s*[\"'][^\"']{8,}"
  #   scope: ["**/*.py", "**/*.js", "**/*.ts"]
  #   action: block
  #   risk: critical
  #
  # - name: no_raw_sql
  #   description: "Do not use raw SQL — use parameterized queries or the ORM"
  #   pattern: "execute\\(\\s*f[\"']|execute\\(.*%\\s*\\(|execute\\(.*\\.format\\("
  #   scope: ["**/*.py"]
  #   action: block
  #   risk: high
  #
  # - name: no_eval_or_exec
  #   description: "Do not use eval() or exec() — risk of code injection"
  #   pattern: "\\beval\\s*\\(|\\bexec\\s*\\("
  #   scope: ["**/*.py"]
  #   action: block
  #   risk: critical
  #
  # - name: no_shell_injection
  #   description: "Do not pass unsanitized input to shell commands"
  #   pattern: "subprocess\\.(call|run|Popen)\\(.*shell\\s*=\\s*True"
  #   scope: ["**/*.py"]
  #   action: require_approval
  #   risk: high
  #
  # - name: no_disabled_auth
  #   description: "Do not disable authentication or authorization checks"
  #   pattern: "@(no_auth|skip_auth|allow_anonymous|csrf_exempt)"
  #   scope: ["**/*.py"]
  #   action: require_approval
  #   risk: high
  #
  # Additional examples:
  # - name: no_new_dependencies
  #   description: "Do not add new package dependencies without approval"
  #   trigger: dependencies_added
  #   action: require_approval

risk_levels:
  high:   [auth, billing, schema_changes, config, deletes]
  medium: [new_api_endpoints, refactors]
  low:    [tests, documentation, formatting]

approval_policy:
  low: auto
  medium: review
  high: mandatory
"""


def context_dir(root: Path | str = ".") -> Path:
    return Path(root) / CONTEXT_DIR


def has_context(root: Path | str = ".") -> bool:
    return context_dir(root).is_dir()


def init_context(
    root: Path | str = ".",
    *,
    name: str = "",
    languages: list[str] | None = None,
    frameworks: list[str] | None = None,
    source_dirs: list[str] | None = None,
    test_dirs: list[str] | None = None,
) -> list[Path]:
    """Create the .planguard/ context directory with starter files.

    Returns list of created paths.
    """
    ctx = context_dir(root)
    ctx.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    files: dict[str, str] = {
        "project.yaml": _PROJECT_YAML_TEMPLATE.format(
            name=name or Path(root).resolve().name,
            languages=yaml.dump(languages or [], default_flow_style=True).strip(),
            frameworks=yaml.dump(frameworks or [], default_flow_style=True).strip(),
            source_dirs=yaml.dump(source_dirs or [], default_flow_style=True).strip(),
            test_dirs=yaml.dump(test_dirs or [], default_flow_style=True).strip(),
        ),
        "conventions.md": _CONVENTIONS_MD_TEMPLATE,
        "boundaries.md": _BOUNDARIES_MD_TEMPLATE,
        "glossary.md": _GLOSSARY_MD_TEMPLATE,
        "policies.yaml": _POLICIES_YAML_TEMPLATE,
    }

    for filename, content in files.items():
        path = ctx / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(path)

    return created


def load_policies(root: Path | str = ".") -> dict:
    """Load policies.yaml from the context directory."""
    path = context_dir(root) / "policies.yaml"
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def load_boundaries(root: Path | str = ".") -> list[str]:
    """Extract off-limits paths from boundaries.md.

    Looks for lines starting with '- ' under the off-limits sections
    and returns them as a list of path patterns.
    """
    path = context_dir(root) / "boundaries.md"
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8")
    boundaries: list[str] = []
    in_section = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Off-limits"):
            in_section = True
            continue
        if stripped.startswith("## ") and in_section:
            in_section = True  # Still an off-limits subsection.
            continue
        if stripped.startswith("# ") and not stripped.startswith("## "):
            in_section = False
            continue
        if in_section and stripped.startswith("- "):
            entry = stripped[2:].strip()
            # Skip template placeholders.
            if entry and not entry.startswith("(e.g."):
                boundaries.append(entry)
    return boundaries
