"""Utilities for matching repo-relative paths against plan scopes and policies."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath


def normalize_path(value: str) -> str:
    """Return a normalized, repo-relative path-like string."""
    return value.replace("\\", "/").strip().strip("/")


def path_matches(path: str, pattern: str) -> bool:
    """Check if a path matches a glob-like pattern or a directory prefix."""
    norm_path = normalize_path(path)
    norm_pattern = normalize_path(pattern)
    if not norm_path or not norm_pattern:
        return False

    patterns = {norm_pattern}
    if "/**/" in norm_pattern:
        patterns.add(norm_pattern.replace("/**/", "/"))
    if norm_pattern.startswith("**/"):
        patterns.add(norm_pattern[3:])
    for candidate in patterns:
        if fnmatch(norm_path, candidate) or PurePosixPath(norm_path).match(candidate):
            return True

    pattern_base = norm_pattern.replace("/**", "").replace("/*", "").rstrip("/")
    if not pattern_base:
        return False

    return norm_path == pattern_base or norm_path.startswith(f"{pattern_base}/")


def paths_overlap(left: str, right: str) -> bool:
    """Return True when either side could include the other."""
    return path_matches(left, right) or path_matches(right, left)
