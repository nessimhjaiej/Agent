$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot ".local-backend-pids.json"

if (Test-Path $pidFile) {
    $entries = Get-Content $pidFile | ConvertFrom-Json
    foreach ($entry in $entries) {
        try {
            Stop-Process -Id $entry.pid -Force -ErrorAction Stop
            Write-Host ("Stopped {0} (PID {1})" -f $entry.name, $entry.pid)
        } catch {
            Write-Host ("Skipped {0} (PID {1})" -f $entry.name, $entry.pid)
        }
    }
    Remove-Item $pidFile -Force
} else {
    Write-Host "No PID file found. Nothing to stop."
}

Push-Location $repoRoot
try {
    docker compose stop weaviate | Out-Host
} finally {
    Pop-Location
}
