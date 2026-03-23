"""Check a plan against governance policies from .planguard/policies.yaml."""

from __future__ import annotations

from pathlib import Path
import re

import yaml

from planguard.pathspec import paths_overlap


def check_policies(
    plan_dir: Path | str,
    policies: dict,
    *,
    file_paths: list[str] | None = None,
    root: Path | str = ".",
) -> list[dict]:
    """Check a plan against policy rules.

    Returns a list of violation dicts:
      {"rule": name, "description": ..., "action": block|require_approval, "risk": ...}
    """
    plan_path = Path(plan_dir) / "plan.yaml"
    if not plan_path.exists():
        return []

    data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    scope_paths = data.get("scope", {}).get("included", [])
    rules = policies.get("rules", [])

    if not rules or not isinstance(rules, list):
        return []

    target_paths = file_paths if file_paths is not None else scope_paths
    violations: list[dict] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        name = rule.get("name", "unnamed")
        description = rule.get("description", "")
        action = rule.get("action", "block")
        risk = rule.get("risk", "medium")
        rule_scope = rule.get("scope", [])
        pattern = rule.get("pattern", "")

        matched_paths = _scope_overlaps(target_paths, rule_scope) if rule_scope else list(target_paths)
        if pattern:
            if file_paths is None:
                # Content-pattern rules only earn friction when evaluated against a real diff.
                continue
            matched_paths = [
                path for path in matched_paths
                if _file_matches_pattern(Path(root) / path, pattern)
            ]

        if matched_paths:
            violations.append({
                "rule": name,
                "description": description,
                "action": action,
                "risk": risk,
                "matched_paths": matched_paths,
            })

    return violations


def check_boundary_violations(
    plan_dir: Path | str,
    boundaries: list[str],
    *,
    file_paths: list[str] | None = None,
) -> list[str]:
    """Check if a plan's scope includes any off-limits paths.

    Returns list of boundary violations (paths that overlap).
    """
    if not boundaries:
        return []

    plan_path = Path(plan_dir) / "plan.yaml"
    if not plan_path.exists():
        return []

    data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    target_paths = file_paths if file_paths is not None else data.get("scope", {}).get("included", [])

    violations: list[str] = []
    for scope_path in target_paths:
        for boundary in boundaries:
            if paths_overlap(scope_path, boundary):
                violations.append(f"{scope_path} overlaps with boundary: {boundary}")

    return violations


def _scope_overlaps(plan_paths: list[str], rule_paths: list[str]) -> list[str]:
    """Return plan paths that overlap with any rule scope pattern."""
    matches: list[str] = []
    for pp in plan_paths:
        for rp in rule_paths:
            if paths_overlap(pp, rp):
                matches.append(pp)
                break
    return matches


def _file_matches_pattern(path: Path, pattern: str) -> bool:
    """Return True if a readable text file contains the regex pattern."""
    if not path.exists() or not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return re.search(pattern, content, re.MULTILINE) is not None
