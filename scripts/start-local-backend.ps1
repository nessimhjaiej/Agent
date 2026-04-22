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

function Stop-ProcessesOnPort {
    param(
        [int]$Port
    )

    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    foreach ($connection in $connections) {
        Stop-ServiceProcessTree -RootPid $connection.OwningProcess
    }
}

$services = @(
    @{
        Name = "auth-service"
        Path = Join-Path $repoRoot "services/auth-service"
        Port = 8001
    },
    @{
        Name = "preprocessing-service"
        Path = Join-Path $repoRoot "services/preprocessing-service"
        Port = 8000
    },
    @{
        Name = "embedding-service"
        Path = Join-Path $repoRoot "services/embedding-service"
        Port = 8002
    },
    @{
        Name = "retrieval-service"
        Path = Join-Path $repoRoot "services/retrieval-service"
        Port = 8003
    },
    @{
        Name = "generation-service"
        Path = Join-Path $repoRoot "services/generation-service"
        Port = 8004
    },
    @{
        Name = "ingestion-service"
        Path = Join-Path $repoRoot "services/ingestion-service"
        Port = 8005
    },
    @{
        Name = "admin-service"
        Path = Join-Path $repoRoot "services/admin-service"
        Port = 8006
    },
    @{
        Name = "security-service"
        Path = Join-Path $repoRoot "services/security-service"
        Port = 8007
    }
)

if (Test-Path $pidFile) {
    $existingEntries = @(Get-Content $pidFile | ConvertFrom-Json)
    foreach ($entry in $existingEntries) {
        Stop-ServiceProcessTree -RootPid ([int]$entry.pid)
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

foreach ($service in $services) {
    Stop-ProcessesOnPort -Port ([int]$service.Port)
}

Write-Host "Starting Weaviate with Docker Compose..."
Push-Location $repoRoot
try {
    docker compose up -d weaviate | Out-Host
} finally {
    Pop-Location
}

$processes = @()

foreach ($service in $services) {
    Write-Host ("Starting {0} on port {1}..." -f $service.Name, $service.Port)
    $command = "`$env:SECURITY_BASE_URL='http://localhost:8007'; `$env:AUTH_BASE_URL='http://localhost:8001'; Set-Location '$($service.Path)'; python -m uvicorn app.main:app --host 0.0.0.0 --port $($service.Port) --reload"
    $process = Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", $command `
        -WorkingDirectory $service.Path `
        -PassThru

    $processes += [PSCustomObject]@{
        name = $service.Name
        pid = $process.Id
        port = $service.Port
    }
}

$processes | ConvertTo-Json | Set-Content -Path $pidFile

Write-Host ""
Write-Host "Backend startup launched."
Write-Host ("PID file: {0}" -f $pidFile)
Write-Host "Health checks:"
Write-Host "  curl.exe http://localhost:8000/health"
Write-Host "  curl.exe http://localhost:8001/health"
Write-Host "  curl.exe http://localhost:8002/health"
Write-Host "  curl.exe http://localhost:8003/health"
Write-Host "  curl.exe http://localhost:8004/health"
Write-Host "  curl.exe http://localhost:8005/health"
Write-Host "  curl.exe http://localhost:8006/health"
Write-Host "  curl.exe http://localhost:8007/health"
Write-Host "  curl.exe http://localhost:8080/v1/.well-known/ready"
