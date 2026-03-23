"""Helpers for capturing git-backed evidence about the current worktree."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess

from planguard.pathspec import normalize_path


def _run_git(args: list[str], root: Path | str = ".") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def is_git_repo(root: Path | str = ".") -> bool:
    result = _run_git(["rev-parse", "--is-inside-work-tree"], root=root)
    return result.returncode == 0 and result.stdout.strip() == "true"


def get_branch(root: Path | str = ".") -> str:
    if not is_git_repo(root):
        return ""
    result = _run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], root=root)
    return result.stdout.strip() if result.returncode == 0 else ""


def get_head_sha(root: Path | str = ".") -> str:
    if not is_git_repo(root):
        return ""
    result = _run_git(["rev-parse", "HEAD"], root=root)
    return result.stdout.strip() if result.returncode == 0 else ""


def get_changed_files(root: Path | str = ".") -> list[str]:
    """Return tracked and untracked files with worktree changes."""
    if not is_git_repo(root):
        return []

    result = _run_git(["status", "--porcelain"], root=root)
    if result.returncode != 0:
        return []

    changed: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        norm = normalize_path(path)
        if norm:
            changed.append(norm)

    return sorted(set(changed))


def build_fingerprints(file_paths: list[str], *, root: Path | str = ".") -> dict[str, str]:
    """Return stable content fingerprints for changed files."""
    base = Path(root)
    fingerprints: dict[str, str] = {}
    for relative_path in sorted(set(file_paths)):
        path = base / relative_path
        if path.exists() and path.is_file():
            fingerprints[relative_path] = sha256(path.read_bytes()).hexdigest()
        else:
            fingerprints[relative_path] = "MISSING"
    return fingerprints


def get_git_snapshot(root: Path | str = ".") -> dict:
    """Capture git state for audit and verification purposes."""
    changed_files = get_changed_files(root=root)
    return {
        "is_git_repo": is_git_repo(root),
        "branch": get_branch(root),
        "head": get_head_sha(root),
        "changed_files": changed_files,
        "fingerprints": build_fingerprints(changed_files, root=root),
    }
