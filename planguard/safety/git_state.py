"""Helpers for capturing git-backed evidence about the current worktree."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess

from planguard.pathspec import normalize_path, path_matches


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


def get_changed_files(
    root: Path | str = ".",
    scope_paths: list[str] | None = None,
) -> list[str]:
    """Return tracked and untracked files with worktree changes.

    When *scope_paths* is provided, only files matching at least one scope
    pattern are returned (uses the same matching as plan scope enforcement).
    """
    if not is_git_repo(root):
        return []

    result = _run_git(["status", "--porcelain", "--untracked-files=all"], root=root)
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

    if scope_paths:
        changed = [
            p for p in changed
            if any(path_matches(p, sp) for sp in scope_paths)
        ]

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


def resolve_renames(
    fingerprints: dict[str, str],
    renames: list[dict],
    *,
    root: Path | str = ".",
) -> dict[str, str]:
    """Adjust fingerprints for declared renames.

    Declared renames are compared against the activation baseline, so the
    baseline key must be remapped from the source path to the destination path.
    This lets later comparisons treat a pure rename as equivalent work when the
    file contents are unchanged.
    """
    result = dict(fingerprints)
    for rename in renames:
        from_path = normalize_path(rename.get("from", ""))
        to_path = normalize_path(rename.get("to", ""))
        if not from_path or not to_path:
            continue
        if from_path in result and to_path not in result:
            result[to_path] = result.pop(from_path)
    return result


def detect_git_renames(root: Path | str = ".") -> list[dict]:
    """Detect renames from git's rename detection in the working tree."""
    if not is_git_repo(root):
        return []
    result = _run_git(["status", "--porcelain", "--untracked-files=all"], root=root)
    if result.returncode != 0:
        return []
    renames: list[dict] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        status = line[:2].strip()
        if status.startswith("R"):
            path_part = line[3:]
            if " -> " in path_part:
                old, new = path_part.split(" -> ", 1)
                renames.append({
                    "from": normalize_path(old),
                    "to": normalize_path(new),
                })
    return renames


def get_git_snapshot(
    root: Path | str = ".",
    scope_paths: list[str] | None = None,
) -> dict:
    """Capture git state for audit and verification purposes."""
    all_changed_files = get_changed_files(root=root)
    if scope_paths:
        changed_files = [
            path for path in all_changed_files
            if any(path_matches(path, scope_path) for scope_path in scope_paths)
        ]
    else:
        changed_files = list(all_changed_files)
    context_changed_files = [
        path for path in all_changed_files
        if path not in changed_files
    ]
    return {
        "is_git_repo": is_git_repo(root),
        "branch": get_branch(root),
        "head": get_head_sha(root),
        "changed_files": changed_files,
        "fingerprints": build_fingerprints(changed_files, root=root),
        "context_changed_files": context_changed_files,
        "context_fingerprints": build_fingerprints(context_changed_files, root=root),
    }
