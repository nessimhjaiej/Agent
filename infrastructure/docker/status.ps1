$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)

Push-Location $repoRoot
try {
    docker ps --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}"
} finally {
    Pop-Location
}

