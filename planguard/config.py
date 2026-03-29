"""Load PlanGuard configuration from .planguard/config.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml


_DEFAULTS = {
    "plans_root": ".planguard/plans",
}

_LEGACY_PLANS_ROOT = Path("docs")


def _read_config_data(root: Path | str = ".") -> dict:
    """Read raw config data without applying PlanGuard defaults."""
    config_path = Path(root) / ".planguard" / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def get_default_plans_root() -> Path:
    """Return the default local plans directory for new installs."""
    return Path(_DEFAULTS["plans_root"])


def has_legacy_docs_plans(root: Path | str = ".") -> bool:
    """Return whether a repo still stores plan definitions under docs/."""
    docs_root = Path(root) / _LEGACY_PLANS_ROOT
    if not docs_root.is_dir():
        return False
    return any(entry.is_dir() and (entry / "plan.yaml").exists() for entry in docs_root.iterdir())


def load_config(root: Path | str = ".") -> dict:
    """Read .planguard/config.yaml, returning defaults for missing keys."""
    data = _read_config_data(root)
    if "plans_root" not in data:
        data["plans_root"] = str(get_plans_root(root))
    return {**_DEFAULTS, **data}


def get_plans_root(root: Path | str = ".") -> Path:
    """Return the configured plans root directory as a Path."""
    root_path = Path(root)
    data = _read_config_data(root_path)
    if "plans_root" in data:
        return Path(data["plans_root"])
    if has_legacy_docs_plans(root_path):
        return _LEGACY_PLANS_ROOT
    return get_default_plans_root()


def get_state_root(root: Path | str = ".") -> Path:
    """Return the runtime state directory for local PlanGuard metadata."""
    return Path(root) / ".planguard" / "state"


def get_plan_state_dir(plan_name: str, root: Path | str = ".") -> Path:
    """Return the runtime state directory for a single plan."""
    return get_state_root(root) / "plans" / plan_name


def get_status_path(plan_name: str, root: Path | str = ".") -> Path:
    """Return the runtime status.yaml path for a plan."""
    return get_plan_state_dir(plan_name, root) / "status.yaml"


def get_registry_path(root: Path | str = ".") -> Path:
    """Return the active plans registry path."""
    return get_state_root(root) / "active_plans.yaml"


def get_execution_schedule_path(root: Path | str = ".") -> Path:
    """Return the execution schedule path."""
    return get_state_root(root) / "execution_schedule.yaml"


def get_log_path(root: Path | str = ".") -> Path:
    """Return the session log path."""
    return get_state_root(root) / "log.jsonl"


def find_project_root_for_plan(plan_dir: Path | str) -> Path:
    """Infer the repository root for a given plan directory."""
    plan_path = Path(plan_dir).resolve()
    plan_name = plan_path.name
    for candidate in [plan_path.parent, *plan_path.parents]:
        expected = (candidate / get_plans_root(candidate) / plan_name).resolve()
        if expected == plan_path:
            return candidate
    return plan_path.parent.parent
