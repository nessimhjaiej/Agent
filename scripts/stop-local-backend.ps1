$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot ".local-backend-pids.json"

function Stop-ServiceProcessTree {
    param(
        [int]$RootPid
    )

    $children = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ParentProcessId -eq $RootPid })
    foreach ($child in $children) {
        Stop-ServiceProcessTree -RootPid $child.ProcessId
    }

    try {
        Stop-Process -Id $RootPid -Force -ErrorAction Stop
    } catch {
    }
}

if (Test-Path $pidFile) {
    $entries = Get-Content $pidFile | ConvertFrom-Json
    foreach ($entry in $entries) {
        try {
            Stop-ServiceProcessTree -RootPid ([int]$entry.pid)
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
