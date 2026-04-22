$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot ".local-backend-pids.json"

function Read-PidEntries {
    param(
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return @()
    }

    $raw = Get-Content -Raw -Path $Path
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return @()
    }

    $parsed = $raw | ConvertFrom-Json
    if ($parsed -is [System.Collections.IEnumerable] -and -not ($parsed -is [string])) {
        return @($parsed)
    }

    return @($parsed)
}

function Get-EntryPid {
    param(
        $Entry
    )

    $value = $Entry.pid
    if ($value -is [array]) {
        $value = $value | Select-Object -First 1
    }

    $parsedPid = 0
    if ([int]::TryParse([string]$value, [ref]$parsedPid)) {
        return $parsedPid
    }

    return $null
}

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
    $entries = Read-PidEntries -Path $pidFile
    foreach ($entry in $entries) {
        try {
            $entryPid = Get-EntryPid -Entry $entry
            if ($null -ne $entryPid) {
                Stop-ServiceProcessTree -RootPid $entryPid
            }
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
