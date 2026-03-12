$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot ".local-backend-pids.json"

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
    }
)

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
    $command = "Set-Location '$($service.Path)'; python -m uvicorn app.main:app --host 0.0.0.0 --port $($service.Port) --reload"
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
Write-Host "  curl.exe http://localhost:8080/v1/.well-known/ready"
