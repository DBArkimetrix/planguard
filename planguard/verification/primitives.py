"""Structured verification primitives for plan verification.

Supports both legacy shell commands (plain strings) and declarative checks
(dicts with a 'check' or 'command' key).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
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
      - A dict with 'command' or 'argv' key (command with optional env/shell settings)
    """
    if isinstance(entry, str):
        return _run_command(entry, root=Path(root))

    if not isinstance(entry, dict):
        return VerifyResult(label=str(entry), passed=False, detail="Invalid entry type")

    if "check" in entry:
        return _run_primitive(entry, root=Path(root))
    if "command" in entry or "argv" in entry:
        timeout = entry.get("timeout", 300)
        if not isinstance(timeout, int) or timeout <= 0:
            return VerifyResult(label=str(entry), passed=False, detail="Command entries require a positive integer 'timeout'")

        env, env_error = _normalize_env(entry.get("env"))
        if env_error:
            return VerifyResult(label=str(entry), passed=False, detail=env_error)

        if "command" in entry and "argv" in entry:
            return VerifyResult(
                label=str(entry),
                passed=False,
                detail="Command entries must define either 'command' or 'argv', not both",
            )

        if "command" in entry:
            command = entry.get("command")
            if not isinstance(command, str) or not command.strip():
                return VerifyResult(
                    label=str(entry),
                    passed=False,
                    detail="Command entries require a non-empty 'command' string",
                )
            shell = entry.get("shell", True)
            if not isinstance(shell, bool):
                return VerifyResult(
                    label=str(entry),
                    passed=False,
                    detail="Command entries require 'shell' to be true or false",
                )
            return _run_command(
                command,
                root=Path(root),
                interpreter=entry.get("interpreter"),
                timeout=timeout,
                env=env,
                shell=shell,
            )

        argv = entry.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(part, str) or not part for part in argv)
        ):
            return VerifyResult(
                label=str(entry),
                passed=False,
                detail="Command entries require 'argv' to be a non-empty list of non-empty strings",
            )
        if entry.get("interpreter"):
            return VerifyResult(
                label=str(entry),
                passed=False,
                detail="Command entries with 'argv' do not support 'interpreter'",
            )
        shell = entry.get("shell", False)
        if not isinstance(shell, bool):
            return VerifyResult(
                label=str(entry),
                passed=False,
                detail="Command entries require 'shell' to be true or false",
            )
        if shell:
            return VerifyResult(
                label=str(entry),
                passed=False,
                detail="Command entries with 'argv' must set 'shell' to false",
            )
        return _run_command(
            argv,
            root=Path(root),
            timeout=timeout,
            env=env,
            shell=False,
        )

    return VerifyResult(label=str(entry), passed=False, detail="Entry must have 'check', 'command', or 'argv' key")


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
        if "command" in entry or "argv" in entry:
            interp = entry.get("interpreter", "")
            shell = entry.get("shell", True)
            cmd = entry.get("command") if "command" in entry else entry.get("argv")
            label = _display_command(cmd)
            if interp:
                return f"{label} (via {interp})"
            if "argv" in entry or shell is False:
                return f"{label} (shell=false)"
            return label
    return str(entry)


def _run_command(
    cmd: str | list[str],
    *,
    root: Path,
    interpreter: str | None = None,
    timeout: int = 300,
    env: dict[str, str] | None = None,
    shell: bool = True,
) -> VerifyResult:
    """Execute a command and return the result."""
    label = _display_command(cmd)
    if interpreter:
        label = f"{label} (via {interpreter})"
    elif not shell:
        label = f"{label} (shell=false)"

    start = time.monotonic()
    try:
        run_env = None
        if env:
            run_env = os.environ.copy()
            run_env.update(env)

        if interpreter:
            result = subprocess.run(
                _build_interpreter_command(interpreter, cmd),
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
            )
        elif shell:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
            )
        else:
            result = subprocess.run(
                _coerce_argv(cmd),
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
            )
        elapsed = time.monotonic() - start
        passed = result.returncode == 0
        detail = ""
        if not passed:
            detail = _format_process_detail(result.stdout, result.stderr)
        return VerifyResult(label=label, passed=passed, detail=detail, duration_seconds=round(elapsed, 2))
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        return VerifyResult(
            label=label,
            passed=False,
            detail=_format_process_detail(exc.stdout, exc.stderr, timeout=timeout),
            duration_seconds=round(elapsed, 2),
        )
    except ValueError as exc:
        elapsed = time.monotonic() - start
        return VerifyResult(
            label=label,
            passed=False,
            detail=f"Invalid non-shell command: {exc}",
            duration_seconds=round(elapsed, 2),
        )
    except FileNotFoundError:
        elapsed = time.monotonic() - start
        return VerifyResult(
            label=label, passed=False,
            detail=f"Interpreter not found: {interpreter}" if interpreter else "Shell not found",
            duration_seconds=round(elapsed, 2),
        )


def _normalize_env(raw_env: object) -> tuple[dict[str, str] | None, str | None]:
    if raw_env is None:
        return None, None
    if not isinstance(raw_env, dict):
        return None, "Command entries require 'env' to be a mapping of environment variables"

    normalized: dict[str, str] = {}
    for key, value in raw_env.items():
        if not isinstance(key, str) or not key:
            return None, "Command entry env keys must be non-empty strings"
        if isinstance(value, (dict, list, tuple, set)):
            return None, f"Environment variable '{key}' must be a scalar value"
        normalized[key] = str(value)
    return normalized, None


def _display_command(command: str | list[str] | None) -> str:
    if isinstance(command, list):
        return shlex.join(command)
    return command or ""


def _coerce_argv(command: str | list[str]) -> list[str]:
    if isinstance(command, list):
        return command
    return shlex.split(command, posix=os.name != "nt")


def _format_process_detail(stdout: str | bytes | None, stderr: str | bytes | None, *, timeout: int | None = None) -> str:
    lines: list[str] = []
    if timeout is not None:
        lines.append(f"Timed out after {timeout}s")

    for stream_name, content in (("stdout", stdout), ("stderr", stderr)):
        excerpt = _render_output_excerpt(content)
        if excerpt:
            lines.append(f"{stream_name} (last {len(excerpt)} line(s)):")
            lines.extend(excerpt)

    return "\n".join(lines)


def _render_output_excerpt(content: str | bytes | None, *, max_lines: int = 5) -> list[str]:
    if content is None:
        return []
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    lines = [line for line in content.strip().splitlines() if line.strip()]
    return lines[-max_lines:]


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


def _build_interpreter_command(interpreter: str, command: str | list[str]) -> list[str]:
    command_text = _display_command(command)
    name = Path(interpreter).name.lower()
    if name in {"cmd", "cmd.exe"}:
        return [interpreter, "/C", command_text]
    if name in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        return [interpreter, "-Command", command_text]
    if name in {"python", "python.exe", "python3", "python3.exe", "py"}:
        return [interpreter, "-c", command_text]
    return [interpreter, "-c", command_text]


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
