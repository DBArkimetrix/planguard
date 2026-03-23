"""Detect the current project's stack, structure, and state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


# Map of marker files/dirs to (language, framework) tuples.
_MARKERS: list[tuple[str, str, str | None]] = [
    ("package.json", "javascript", None),
    ("tsconfig.json", "typescript", None),
    ("pyproject.toml", "python", None),
    ("setup.py", "python", None),
    ("requirements.txt", "python", None),
    ("Cargo.toml", "rust", None),
    ("go.mod", "go", None),
    ("pom.xml", "java", "maven"),
    ("build.gradle", "java", "gradle"),
    ("build.gradle.kts", "kotlin", "gradle"),
    ("Gemfile", "ruby", None),
    ("composer.json", "php", None),
    ("mix.exs", "elixir", None),
    ("Package.swift", "swift", None),
    ("CMakeLists.txt", "c/c++", "cmake"),
    ("Makefile", "unknown", "make"),
]

_FRAMEWORK_HINTS: dict[str, list[tuple[str, str]]] = {
    "package.json": [
        ("next", "Next.js"),
        ("react", "React"),
        ("vue", "Vue"),
        ("angular", "Angular"),
        ("express", "Express"),
        ("fastify", "Fastify"),
        ("svelte", "Svelte"),
        ("nuxt", "Nuxt"),
    ],
    "pyproject.toml": [
        ("django", "Django"),
        ("flask", "Flask"),
        ("fastapi", "FastAPI"),
        ("typer", "Typer"),
        ("streamlit", "Streamlit"),
    ],
    "Gemfile": [
        ("rails", "Rails"),
        ("sinatra", "Sinatra"),
    ],
    "composer.json": [
        ("laravel", "Laravel"),
        ("symfony", "Symfony"),
    ],
}


@dataclass
class ProjectInfo:
    """Detected information about a project."""

    root: Path
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    source_dirs: list[str] = field(default_factory=list)
    test_dirs: list[str] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    lint_commands: list[str] = field(default_factory=list)
    has_git: bool = False
    has_ci: bool = False
    has_agents_md: bool = False
    has_claude_md: bool = False
    has_existing_plans: bool = False
    existing_plan_names: list[str] = field(default_factory=list)
    is_empty: bool = False

    def summary(self) -> str:
        """Human-readable summary of what was detected."""
        lines: list[str] = []
        if self.is_empty:
            lines.append("This looks like a new/empty project.")
        else:
            if self.languages:
                lines.append(f"Languages: {', '.join(self.languages)}")
            if self.frameworks:
                lines.append(f"Frameworks: {', '.join(self.frameworks)}")
            if self.source_dirs:
                lines.append(f"Source directories: {', '.join(self.source_dirs)}")
            if self.test_dirs:
                lines.append(f"Test directories: {', '.join(self.test_dirs)}")
            if self.build_commands:
                lines.append(f"Build: {', '.join(self.build_commands)}")
            if self.test_commands:
                lines.append(f"Test: {', '.join(self.test_commands)}")
            if self.lint_commands:
                lines.append(f"Lint: {', '.join(self.lint_commands)}")
            if self.has_git:
                lines.append("Git repository: yes")
            if self.has_ci:
                lines.append("CI/CD config detected")
        if self.has_existing_plans:
            lines.append(f"Existing plans: {', '.join(self.existing_plan_names)}")
        if self.has_agents_md:
            lines.append("AGENTS.md already present")
        if self.has_claude_md:
            lines.append("CLAUDE.md already present")
        return "\n".join(lines) if lines else "Could not detect project details."


def _detect_frameworks(root: Path, marker: str) -> list[str]:
    """Read a marker file and check for known framework keywords."""
    hints = _FRAMEWORK_HINTS.get(marker)
    if not hints:
        return []
    path = root / marker
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8").lower()
    except Exception:
        return []
    return [name for keyword, name in hints if keyword in content]


def _find_dirs(root: Path, candidates: list[str]) -> list[str]:
    """Return which candidate directory names exist under root."""
    return [name for name in candidates if (root / name).is_dir()]


def detect_project(root: Path | str = ".") -> ProjectInfo:
    """Scan a directory and return detected project information."""
    root = Path(root).resolve()
    info = ProjectInfo(root=root)

    # Check if effectively empty (no meaningful files beyond dotfiles).
    meaningful = [
        p for p in root.iterdir()
        if not p.name.startswith(".") and p.name not in {"docs", "AGENTS.md", "CLAUDE.md"}
    ]
    info.is_empty = len(meaningful) == 0

    # Git
    info.has_git = (root / ".git").is_dir()

    # CI/CD
    info.has_ci = any([
        (root / ".github" / "workflows").is_dir(),
        (root / ".gitlab-ci.yml").exists(),
        (root / "Jenkinsfile").exists(),
        (root / ".circleci").is_dir(),
    ])

    # AGENTS.md / CLAUDE.md
    info.has_agents_md = (root / "AGENTS.md").exists()
    info.has_claude_md = (root / "CLAUDE.md").exists()

    # Existing plans
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        plan_dirs = [
            p.name for p in docs_dir.iterdir()
            if p.is_dir() and (p / "plan.yaml").exists()
        ]
        if plan_dirs:
            info.has_existing_plans = True
            info.existing_plan_names = sorted(plan_dirs)

    # Languages and frameworks
    seen_langs: set[str] = set()
    for marker, lang, framework in _MARKERS:
        if (root / marker).exists():
            if lang != "unknown" and lang not in seen_langs:
                info.languages.append(lang)
                seen_langs.add(lang)
            if framework:
                info.frameworks.append(framework)
            # Check for deeper framework hints.
            info.frameworks.extend(_detect_frameworks(root, marker))

    # Deduplicate frameworks
    seen: set[str] = set()
    deduped: list[str] = []
    for fw in info.frameworks:
        if fw not in seen:
            seen.add(fw)
            deduped.append(fw)
    info.frameworks = deduped

    # Source and test directories
    source_candidates = ["src", "lib", "app", "pkg", "cmd", "internal", "server", "client"]
    test_candidates = ["tests", "test", "spec", "__tests__", "e2e", "integration_tests"]
    info.source_dirs = _find_dirs(root, source_candidates)
    info.test_dirs = _find_dirs(root, test_candidates)

    # Infer build, test, and lint commands from detected stack.
    info.build_commands, info.test_commands, info.lint_commands = _infer_commands(root, info)

    return info


# Maps detected markers to likely commands.
_COMMAND_RULES: list[tuple[str, list[str], list[str], list[str]]] = [
    # (marker_file, build_cmds, test_cmds, lint_cmds)
    ("package.json", ["npm run build"], ["npm test"], ["npm run lint"]),
    ("Cargo.toml", ["cargo build"], ["cargo test"], ["cargo clippy"]),
    ("go.mod", ["go build ./..."], ["go test ./..."], ["go vet ./..."]),
    ("pom.xml", ["mvn compile"], ["mvn test"], []),
    ("build.gradle", ["./gradlew build"], ["./gradlew test"], []),
    ("build.gradle.kts", ["./gradlew build"], ["./gradlew test"], []),
    ("Gemfile", [], ["bundle exec rspec"], ["bundle exec rubocop"]),
    ("mix.exs", ["mix compile"], ["mix test"], ["mix credo"]),
    ("composer.json", [], ["composer test"], ["composer lint"]),
]


def _infer_commands(
    root: Path,
    info: ProjectInfo,
) -> tuple[list[str], list[str], list[str]]:
    """Return (build, test, lint) command lists based on detected markers."""
    build: list[str] = []
    test: list[str] = []
    lint: list[str] = []

    for marker, b, t, l in _COMMAND_RULES:
        if (root / marker).exists():
            build.extend(b)
            test.extend(t)
            lint.extend(l)

    # Python-specific: detect the runner (poetry, pytest, etc.)
    if "python" in info.languages:
        has_poetry = (root / "poetry.lock").exists()
        has_pytest = (root / "pyproject.toml").exists() and "pytest" in (
            (root / "pyproject.toml").read_text(encoding="utf-8") if (root / "pyproject.toml").exists() else ""
        )
        if has_poetry:
            build.append("poetry install")
            test.append("poetry run pytest" if has_pytest else "poetry run python -m unittest")
        elif has_pytest:
            test.append("pytest")
        else:
            test.append("python -m unittest discover")

        # Lint
        if (root / "pyproject.toml").exists():
            content = (root / "pyproject.toml").read_text(encoding="utf-8")
            if "ruff" in content:
                lint.append("ruff check .")
            elif "flake8" in content:
                lint.append("flake8")
            if "mypy" in content:
                lint.append("mypy .")

    # Deduplicate while preserving order.
    def _dedup(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    return _dedup(build), _dedup(test), _dedup(lint)
