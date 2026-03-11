Write-Host "Running post-restructure fixes..."

$root = Get-Location

# -------------------------------------------------
# 1. Fix imports referencing scripts.*
# -------------------------------------------------

$files = Get-ChildItem -Recurse -Include *.py

foreach ($file in $files) {

    $content = Get-Content $file.FullName -Raw

    $content = $content -replace "from scripts\.validate_plan", "from agent_framework.validation.validate_plan"
    $content = $content -replace "from scripts\.compute_risk_score", "from agent_framework.safety.compute_risk_score"
    $content = $content -replace "from scripts\.detect_collisions", "from agent_framework.orchestration.detect_collisions"
    $content = $content -replace "from scripts\.build_execution_schedule", "from agent_framework.orchestration.build_execution_schedule"
    $content = $content -replace "from scripts\.analyze_change_impact", "from agent_framework.architecture.analyze_change_impact"

    Set-Content $file.FullName $content
}

Write-Host "Python imports updated."

# -------------------------------------------------
# 2. Update pre-commit hooks
# -------------------------------------------------

$precommit = ".pre-commit-config.yaml"

if (Test-Path $precommit) {

    $content = Get-Content $precommit -Raw

    $content = $content -replace "scripts/validate_plan.py", "agent_framework/validation/validate_plan.py"
    $content = $content -replace "scripts/detect_collisions.py", "agent_framework/orchestration/detect_collisions.py"
    $content = $content -replace "scripts/build_execution_schedule.py", "agent_framework/orchestration/build_execution_schedule.py"
    $content = $content -replace "scripts/compute_risk_score.py", "agent_framework/safety/compute_risk_score.py"

    Set-Content $precommit $content

    Write-Host "Pre-commit hooks updated."
}

# -------------------------------------------------
# 3. Ensure pyproject has CLI entry
# -------------------------------------------------

$pyproject = "pyproject.toml"

if (Test-Path $pyproject) {

    $content = Get-Content $pyproject -Raw

    if ($content -notmatch "\[project\.scripts\]") {

        Add-Content $pyproject @"

[project.scripts]
agent = "agent_framework.cli:main"

"@

        Write-Host "CLI entry added to pyproject.toml"
    }
}

# -------------------------------------------------
# 4. Verify package folder
# -------------------------------------------------

if (!(Test-Path "agent_framework")) {

    Write-Host "ERROR: agent_framework package missing."
    exit 1
}

Write-Host "Package structure verified."

# -------------------------------------------------
# 5. Run Poetry checks
# -------------------------------------------------

Write-Host "Checking Poetry configuration..."

poetry check

Write-Host "Post-restructure cleanup complete."