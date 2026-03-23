"""Append-only session log for tracking agent activity.

Writes JSON lines to .planguard/log.jsonl. Each entry records a lifecycle
event: plan created, checks run, plan activated, verification result, etc.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from planguard.context.project_context import context_dir
from planguard.safety.git_state import get_git_snapshot


def _log_path(root: Path | str = ".") -> Path:
    ctx = context_dir(root)
    ctx.mkdir(parents=True, exist_ok=True)
    return ctx / "log.jsonl"


def log_event(
    event: str,
    *,
    plan: str = "",
    details: dict | None = None,
    root: Path | str = ".",
) -> None:
    """Append a structured event to the session log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    if plan:
        entry["plan"] = plan
    if details:
        entry.update(details)

    snapshot = get_git_snapshot(root)
    if snapshot.get("is_git_repo"):
        entry.setdefault("git_branch", snapshot.get("branch", ""))
        entry.setdefault("git_head", snapshot.get("head", ""))
        entry.setdefault("changed_files", snapshot.get("changed_files", []))

    path = _log_path(root)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_log(root: Path | str = ".", plan: str | None = None) -> list[dict]:
    """Read all log entries, optionally filtered by plan name."""
    path = _log_path(root)
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if plan and entry.get("plan") != plan:
                continue
            entries.append(entry)
        except json.JSONDecodeError:
            continue
    return entries
