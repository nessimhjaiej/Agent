param(
    [string[]]$Services,
    [int]$DelaySeconds = 2
)

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

function Stop-ProcessesOnPort {
    param(
        [int]$Port
    )

    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    foreach ($connection in $connections) {
        Stop-ServiceProcessTree -RootPid $connection.OwningProcess
    }
}

$serviceMap = @{
    "auth-service" = @{
        Path = Join-Path $repoRoot "services/auth-service"
        Port = 8001
    }
    "preprocessing-service" = @{
        Path = Join-Path $repoRoot "services/preprocessing-service"
        Port = 8000
    }
    "embedding-service" = @{
        Path = Join-Path $repoRoot "services/embedding-service"
        Port = 8002
    }
    "retrieval-service" = @{
        Path = Join-Path $repoRoot "services/retrieval-service"
        Port = 8003
    }
    "generation-service" = @{
        Path = Join-Path $repoRoot "services/generation-service"
        Port = 8004
    }
    "ingestion-service" = @{
        Path = Join-Path $repoRoot "services/ingestion-service"
        Port = 8005
    }
    "admin-service" = @{
        Path = Join-Path $repoRoot "services/admin-service"
        Port = 8006
    }
    "security-service" = @{
        Path = Join-Path $repoRoot "services/security-service"
        Port = 8007
    }
}

if (-not $Services -or $Services.Count -eq 0) {
    $Services = @(
        "auth-service",
        "preprocessing-service",
        "embedding-service",
        "retrieval-service",
        "generation-service",
        "ingestion-service",
        "admin-service",
        "security-service"
    )
}

Start-Sleep -Seconds $DelaySeconds

$entries = @()
if (Test-Path $pidFile) {
    $entries = Read-PidEntries -Path $pidFile
}

$updatedEntries = @()
foreach ($entry in $entries) {
    if ($Services -contains $entry.name) {
        try {
            $entryPid = Get-EntryPid -Entry $entry
            if ($null -ne $entryPid) {
                Stop-ServiceProcessTree -RootPid $entryPid
            }
            Write-Host ("Stopped {0} (PID {1})" -f $entry.name, $entry.pid)
        } catch {
            Write-Host ("Skipped {0} (PID {1})" -f $entry.name, $entry.pid)
        }
    } else {
        $updatedEntries += $entry
    }
}

foreach ($serviceName in $Services) {
    if (-not $serviceMap.ContainsKey($serviceName)) {
        throw "Unsupported service name: $serviceName"
    }

    $service = $serviceMap[$serviceName]
    Stop-ProcessesOnPort -Port ([int]$service.Port)
    Write-Host ("Starting {0} on port {1}..." -f $serviceName, $service.Port)
    $command = "`$env:SECURITY_BASE_URL='http://localhost:8007'; `$env:AUTH_BASE_URL='http://localhost:8001'; Set-Location '$($service.Path)'; python -m uvicorn app.main:app --host 0.0.0.0 --port $($service.Port) --reload"
    $process = Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", $command `
        -WorkingDirectory $service.Path `
        -PassThru

    $updatedEntries += [PSCustomObject]@{
        name = $serviceName
        pid = $process.Id
        port = $service.Port
    }
}

$updatedEntries | ConvertTo-Json | Set-Content -Path $pidFile
