"""Guard: inspect staged git changes for risky patterns regardless of plan status.

This module provides a safety net for changes that bypass the planning workflow.
It scans the staged diff for database-related patterns (migrations, schema changes,
SQL DDL) and flags them so they don't slip through as "small changes".
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# Paths that strongly indicate database work.
_DB_PATH_PATTERNS: list[str] = [
    "migrations/",
    "alembic/",
    "migrate/",
    "db/migrate/",
    "flyway/",
    "liquibase/",
    "schema/",
]

# File extensions commonly associated with schema definitions.
_DB_FILE_EXTENSIONS: set[str] = {".sql", ".migration", ".migrate"}

# Content patterns in diffs that suggest schema changes.
_SCHEMA_CONTENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(CREATE|ALTER|DROP)\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\b(ADD|DROP|ALTER|RENAME)\s+COLUMN\b", re.IGNORECASE),
    re.compile(r"\b(CREATE|DROP)\s+(UNIQUE\s+)?INDEX\b", re.IGNORECASE),
    re.compile(r"\bop\.(add_column|drop_column|create_table|drop_table|alter_column)\b"),
    re.compile(r"\b(CreateModel|AddField|RemoveField|AlterField|RenameField|DeleteModel)\b"),
    re.compile(r"\b(create_table|drop_table|add_column|remove_column|rename_column|change_column)\b"),
]


@dataclass
class GuardFinding:
    """A single finding from the guard scan."""

    path: str
    reason: str
    severity: str = "high"


@dataclass
class GuardReport:
    """Summary of guard findings."""

    findings: list[GuardFinding] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return len(self.findings) > 0


def get_staged_files(root: str | Path = ".") -> list[str]:
    """Return list of file paths staged for commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_staged_diff(root: str | Path = ".") -> str:
    """Return the full staged diff content."""
    result = subprocess.run(
        ["git", "diff", "--cached", "-U3"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def get_unstaged_changed_files(root: str | Path = ".") -> list[str]:
    """Return list of tracked files with unstaged modifications (fallback when nothing is staged)."""
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_unstaged_diff(root: str | Path = ".") -> str:
    """Return the full unstaged diff content."""
    result = subprocess.run(
        ["git", "diff", "-U3"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def scan_files_for_db_paths(file_paths: list[str]) -> list[GuardFinding]:
    """Check file paths against known database/migration path patterns."""
    findings: list[GuardFinding] = []
    for path in file_paths:
        normalized = path.replace("\\", "/")
        for pattern in _DB_PATH_PATTERNS:
            if pattern in normalized:
                findings.append(GuardFinding(
                    path=path,
                    reason=f"File is in a database-related directory ({pattern.rstrip('/')})",
                ))
                break
        else:
            ext = Path(path).suffix.lower()
            if ext in _DB_FILE_EXTENSIONS:
                findings.append(GuardFinding(
                    path=path,
                    reason=f"File has a database-related extension ({ext})",
                ))
    return findings


def scan_diff_for_schema_changes(diff_content: str) -> list[GuardFinding]:
    """Scan diff content for database schema change patterns."""
    findings: list[GuardFinding] = []
    current_file = ""

    for line in diff_content.splitlines():
        if line.startswith("diff --git"):
            parts = line.split(" b/", 1)
            current_file = parts[1] if len(parts) > 1 else ""
        elif line.startswith("+") and not line.startswith("+++"):
            added_line = line[1:]
            for pattern in _SCHEMA_CONTENT_PATTERNS:
                if pattern.search(added_line):
                    findings.append(GuardFinding(
                        path=current_file,
                        reason=f"Schema change detected: {pattern.pattern}",
                    ))
                    break

    # Deduplicate by (path, reason).
    seen: set[tuple[str, str]] = set()
    unique: list[GuardFinding] = []
    for f in findings:
        key = (f.path, f.reason)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def run_guard(root: str | Path = ".") -> GuardReport:
    """Run the full guard scan on staged changes.

    Falls back to unstaged changes if nothing is staged.
    """
    staged_files = get_staged_files(root)
    if staged_files:
        diff = get_staged_diff(root)
        files = staged_files
    else:
        files = get_unstaged_changed_files(root)
        diff = get_unstaged_diff(root)

    findings: list[GuardFinding] = []
    findings.extend(scan_files_for_db_paths(files))
    findings.extend(scan_diff_for_schema_changes(diff))

    return GuardReport(findings=findings)
