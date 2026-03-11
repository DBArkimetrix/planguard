Write-Host "Restructuring agent-engineering-framework..."

$root = Get-Location

# -----------------------------
# Create package structure
# -----------------------------

$dirs = @(
"agent_framework",
"agent_framework\planning",
"agent_framework\validation",
"agent_framework\safety",
"agent_framework\orchestration",
"agent_framework\architecture",
"agent_framework\utils"
)

foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "Created $dir"
    }
}

# -----------------------------
# Create __init__.py files
# -----------------------------

$initFiles = @(
"agent_framework\__init__.py",
"agent_framework\planning\__init__.py",
"agent_framework\validation\__init__.py",
"agent_framework\safety\__init__.py",
"agent_framework\orchestration\__init__.py",
"agent_framework\architecture\__init__.py",
"agent_framework\utils\__init__.py"
)

foreach ($file in $initFiles) {
    if (!(Test-Path $file)) {
        New-Item -ItemType File -Path $file | Out-Null
        Write-Host "Created $file"
    }
}

# -----------------------------
# Move existing scripts
# -----------------------------

function Move-Safely($src, $dst) {
    if (Test-Path $src) {
        Move-Item $src $dst -Force
        Write-Host "Moved $src -> $dst"
    }
}

Move-Safely "scripts\validate_plan.py" "agent_framework\validation\validate_plan.py"
Move-Safely "scripts\compute_risk_score.py" "agent_framework\safety\compute_risk_score.py"
Move-Safely "scripts\detect_collisions.py" "agent_framework\orchestration\detect_collisions.py"
Move-Safely "scripts\build_execution_schedule.py" "agent_framework\orchestration\build_execution_schedule.py"
Move-Safely "scripts\analyze_change_impact.py" "agent_framework\architecture\analyze_change_impact.py"
Move-Safely "scripts\generate_architecture_diagram.py" "agent_framework\architecture\generate_architecture_diagram.py"

# -----------------------------
# Create CLI file if missing
# -----------------------------

$cli = "agent_framework\cli.py"

if (!(Test-Path $cli)) {

@"
import typer

app = typer.Typer()

@app.command()
def validate():
    print("Running plan validation")

def main():
    app()

if __name__ == "__main__":
    main()
"@ | Out-File $cli

Write-Host "Created CLI entrypoint"
}

# -----------------------------
# Ensure pyproject has CLI
# -----------------------------

$pyproject = "pyproject.toml"

if (Test-Path $pyproject) {

$content = Get-Content $pyproject -Raw

if ($content -notmatch "\[project\.scripts\]") {

Add-Content $pyproject @"

[project.scripts]
agent = "agent_framework.cli:main"

"@

Write-Host "Added CLI entrypoint to pyproject.toml"
}

}

Write-Host ""
Write-Host "Framework restructuring complete."
Write-Host ""
Write-Host "Next steps:"
Write-Host "poetry install"
Write-Host "poetry build"
