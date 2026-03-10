param(
    [Parameter(Mandatory = $true)]
    [string[]]$Services,
    [int]$DelaySeconds = 2
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot ".local-backend-pids.json"

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
    "admin-service" = @{
        Path = Join-Path $repoRoot "services/admin-service"
        Port = 8006
    }
}

Start-Sleep -Seconds $DelaySeconds

$entries = @()
if (Test-Path $pidFile) {
    $entries = @(Get-Content $pidFile | ConvertFrom-Json)
}

$updatedEntries = @()
foreach ($entry in $entries) {
    if ($Services -contains $entry.name) {
        try {
            Stop-Process -Id $entry.pid -Force -ErrorAction Stop
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
    Write-Host ("Starting {0} on port {1}..." -f $serviceName, $service.Port)
    $command = "Set-Location '$($service.Path)'; python -m uvicorn app.main:app --host 0.0.0.0 --port $($service.Port) --reload"
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
