param(
    [Parameter(Mandatory = $true)]
    [string[]]$Services
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)

if ($Services.Count -eq 0) {
    throw "Provide at least one service name."
}

Push-Location $repoRoot
try {
    docker compose restart @Services
} finally {
    Pop-Location
}

