<#
.SYNOPSIS
    Rebuild and restart the services affected by the admin-agent fixes.

.DESCRIPTION
    Rebuilds admin-service (all the agent/routing/executor fixes) and
    generation-service (Ragas dependency required by run_evaluation), then
    recreates just those two containers. Other services are left running.

    generation-service is rebuilt with --no-cache by default because the live
    image was built from a requirements set without a working Ragas install;
    a cache-busting build guarantees the dependency is (re)installed cleanly.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\update-services.ps1

.EXAMPLE
    # Skip the slow no-cache generation build (use layer cache):
    powershell -ExecutionPolicy Bypass -File .\scripts\update-services.ps1 -FastGeneration

.EXAMPLE
    # Also run the admin-service test suite inside the rebuilt image:
    powershell -ExecutionPolicy Bypass -File .\scripts\update-services.ps1 -RunTests
#>
[CmdletBinding()]
param(
    [switch]$FastGeneration,   # use docker layer cache for generation-service
    [switch]$RunTests          # run admin-service pytest inside the rebuilt image
)

$ErrorActionPreference = "Stop"

# Always operate from the repo root (folder that holds docker-compose.yml).
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
Write-Host "==> Repo root: $repoRoot" -ForegroundColor Cyan

if (-not (Test-Path ".\docker-compose.yml")) {
    throw "docker-compose.yml not found in $repoRoot. Run this from the project that builds your containers."
}

function Invoke-Step([string]$Title, [scriptblock]$Action) {
    Write-Host ""
    Write-Host "==> $Title" -ForegroundColor Green
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "Step failed: $Title (exit $LASTEXITCODE)" }
}

# 1) Rebuild admin-service (code-only changes; pip layer stays cached).
Invoke-Step "Building admin-service" { docker compose build admin-service }

# 2) Rebuild generation-service (needs working Ragas for run_evaluation).
if ($FastGeneration) {
    Invoke-Step "Building generation-service (cached)" { docker compose build generation-service }
} else {
    Invoke-Step "Building generation-service (--no-cache)" { docker compose build --no-cache generation-service }
}

# 3) Recreate just these two containers.
Invoke-Step "Recreating containers" {
    docker compose up -d --force-recreate admin-service generation-service
}

# 4) Wait for health endpoints.
Write-Host ""
Write-Host "==> Waiting for services to report healthy..." -ForegroundColor Green
$targets = @(
    @{ Name = "admin-service";      Url = "http://localhost:8006/health" },
    @{ Name = "generation-service"; Url = "http://localhost:8004/health" }
)
foreach ($t in $targets) {
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $t.Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { Start-Sleep -Seconds 2 }
    }
    if ($ok) {
        Write-Host ("    [OK]  {0,-20} {1}" -f $t.Name, $t.Url) -ForegroundColor Green
    } else {
        Write-Host ("    [FAIL] {0,-20} {1} did not become healthy" -f $t.Name, $t.Url) -ForegroundColor Red
    }
}

# 5) Optionally run the admin-service test suite inside the freshly built image.
if ($RunTests) {
    Invoke-Step "Running admin-service tests in container" {
        docker compose run --rm --no-deps `
            -e PYTHONPATH=/app/services/admin-service `
            admin-service python -m pytest services/admin-service/tests -q
    }
}

Write-Host ""
Write-Host "==> Done. Current status:" -ForegroundColor Cyan
docker compose ps admin-service generation-service
