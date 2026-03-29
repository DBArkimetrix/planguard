"""Structured verification primitives for plan verification.

Supports both legacy shell commands (plain strings) and declarative checks
(dicts with a 'check' or 'command' key).
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VerifyResult:
    """Result of a single verification check."""

    label: str
    passed: bool
    detail: str = ""
    duration_seconds: float = 0.0


def run_check(entry: str | dict, *, root: Path | str = ".") -> VerifyResult:
    """Dispatch a single verify_commands entry.

    Accepts either:
      - A plain string (legacy shell command)
      - A dict with 'check' key (structured primitive)
      - A dict with 'command' key (shell command with optional interpreter)
    """
    if isinstance(entry, str):
        return _run_shell(entry, root=Path(root))

    if not isinstance(entry, dict):
        return VerifyResult(label=str(entry), passed=False, detail="Invalid entry type")

    if "check" in entry:
        return _run_primitive(entry, root=Path(root))
    if "command" in entry:
        return _run_shell(
            entry["command"],
            root=Path(root),
            interpreter=entry.get("interpreter"),
            timeout=entry.get("timeout", 300),
        )

    return VerifyResult(label=str(entry), passed=False, detail="Entry must have 'check' or 'command' key")


def format_label(entry: str | dict) -> str:
    """Return a human-readable label for a verify_commands entry."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        if "check" in entry:
            check = entry["check"]
            path = entry.get("path", "")
            pattern = entry.get("pattern", "")
            from_path = entry.get("from", "")
            to_path = entry.get("to", "")
            if check == "file_moved":
                return f"{check}: {from_path} -> {to_path}"
            if pattern:
                return f"{check}: {path} ~ {pattern!r}"
            return f"{check}: {path}" if path else check
        if "command" in entry:
            interp = entry.get("interpreter", "")
            cmd = entry["command"]
            return f"{cmd} (via {interp})" if interp else cmd
    return str(entry)


def _run_shell(
    cmd: str,
    *,
    root: Path,
    interpreter: str | None = None,
    timeout: int = 300,
) -> VerifyResult:
    """Execute a shell command and return the result."""
    label = cmd
    if interpreter:
        label = f"{cmd} (via {interpreter})"

    start = time.monotonic()
    try:
        if interpreter:
            result = subprocess.run(
                [interpreter, "-c", cmd],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        else:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        elapsed = time.monotonic() - start
        passed = result.returncode == 0
        detail = ""
        if not passed:
            lines = (result.stdout.strip() + "\n" + result.stderr.strip()).strip().splitlines()
            detail = "\n".join(lines[-5:])
        return VerifyResult(label=label, passed=passed, detail=detail, duration_seconds=round(elapsed, 2))
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return VerifyResult(
            label=label, passed=False, detail=f"Timed out after {timeout}s", duration_seconds=round(elapsed, 2)
        )
    except FileNotFoundError:
        elapsed = time.monotonic() - start
        return VerifyResult(
            label=label, passed=False,
            detail=f"Interpreter not found: {interpreter}" if interpreter else "Shell not found",
            duration_seconds=round(elapsed, 2),
        )


def _run_primitive(entry: dict, *, root: Path) -> VerifyResult:
    """Dispatch a structured check primitive."""
    check = entry.get("check", "")
    start = time.monotonic()

    handlers = {
        "file_exists": _check_file_exists,
        "file_not_exists": _check_file_not_exists,
        "file_moved": _check_file_moved,
        "text_contains": _check_text_contains,
        "text_not_contains": _check_text_not_contains,
    }

    handler = handlers.get(check)
    if not handler:
        return VerifyResult(
            label=f"unknown check: {check}",
            passed=False,
            detail=f"Supported checks: {', '.join(sorted(handlers))}",
        )

    result = handler(entry, root=root)
    result.duration_seconds = round(time.monotonic() - start, 2)
    return result


def _check_file_exists(entry: dict, *, root: Path) -> VerifyResult:
    path = entry.get("path", "")
    label = f"file_exists: {path}"
    if not path:
        return VerifyResult(label=label, passed=False, detail="Missing 'path'")
    exists = (root / path).exists()
    return VerifyResult(label=label, passed=exists, detail="" if exists else f"{path} does not exist")


def _check_file_not_exists(entry: dict, *, root: Path) -> VerifyResult:
    path = entry.get("path", "")
    label = f"file_not_exists: {path}"
    if not path:
        return VerifyResult(label=label, passed=False, detail="Missing 'path'")
    exists = (root / path).exists()
    return VerifyResult(label=label, passed=not exists, detail="" if not exists else f"{path} still exists")


def _check_file_moved(entry: dict, *, root: Path) -> VerifyResult:
    from_path = entry.get("from", "")
    to_path = entry.get("to", "")
    label = f"file_moved: {from_path} -> {to_path}"
    if not from_path or not to_path:
        return VerifyResult(label=label, passed=False, detail="Requires 'from' and 'to'")
    old_gone = not (root / from_path).exists()
    new_exists = (root / to_path).exists()
    passed = old_gone and new_exists
    detail = ""
    if not old_gone:
        detail = f"Source still exists: {from_path}"
    elif not new_exists:
        detail = f"Destination not found: {to_path}"
    return VerifyResult(label=label, passed=passed, detail=detail)


def _check_text_contains(entry: dict, *, root: Path) -> VerifyResult:
    path = entry.get("path", "")
    pattern = entry.get("pattern", "")
    label = f"text_contains: {path} ~ {pattern!r}"
    if not path or not pattern:
        return VerifyResult(label=label, passed=False, detail="Requires 'path' and 'pattern'")
    target = root / path
    if not target.exists():
        return VerifyResult(label=label, passed=False, detail=f"{path} does not exist")
    content = target.read_text(encoding="utf-8", errors="replace")
    found = pattern in content
    return VerifyResult(label=label, passed=found, detail="" if found else f"Pattern not found in {path}")


def _check_text_not_contains(entry: dict, *, root: Path) -> VerifyResult:
    path = entry.get("path", "")
    pattern = entry.get("pattern", "")
    label = f"text_not_contains: {path} ~ {pattern!r}"
    if not path or not pattern:
        return VerifyResult(label=label, passed=False, detail="Requires 'path' and 'pattern'")
    target = root / path
    if not target.exists():
        return VerifyResult(label=label, passed=True, detail="File does not exist (vacuously true)")
    content = target.read_text(encoding="utf-8", errors="replace")
    found = pattern in content
    return VerifyResult(label=label, passed=not found, detail="" if not found else f"Pattern found in {path}")
