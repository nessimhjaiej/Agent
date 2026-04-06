param(
    [string[]]$Services = @(),
    [int]$Tail = 120,
    [switch]$Follow
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)

if ($Tail -le 0) {
    throw "Tail must be greater than 0."
}

$command = @("docker", "compose", "logs", "--tail", "$Tail")
if ($Follow) {
    $command += "--follow"
}
if ($Services.Count -gt 0) {
    $command += $Services
}

Push-Location $repoRoot
try {
    & $command[0] $command[1..($command.Count - 1)]
} finally {
    Pop-Location
}

