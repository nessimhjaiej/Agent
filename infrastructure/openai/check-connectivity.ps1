param(
    [string]$OpenAIKey = "",
    [string]$OrganizationId = "",
    [string]$ProjectId = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)
$envFilePath = Join-Path $repoRoot ".env"

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed -match ('^{0}\s*=\s*(.*)$' -f [regex]::Escape($Name))) {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }

    return ""
}

if (-not $OpenAIKey) {
    $OpenAIKey = $env:OPENAI_KEY
}
if (-not $OpenAIKey) {
    $OpenAIKey = Get-DotEnvValue -Path $envFilePath -Name "OPENAI_KEY"
}
if (-not $OpenAIKey) {
    throw "Set OPENAI_KEY, add it to the repo root .env, or pass -OpenAIKey."
}

$headers = @{
    Authorization = "Bearer $OpenAIKey"
    "Content-Type" = "application/json"
}
if ($OrganizationId) {
    $headers["OpenAI-Organization"] = $OrganizationId
}
if ($ProjectId) {
    $headers["OpenAI-Project"] = $ProjectId
}

try {
    $response = Invoke-RestMethod -Method Get -Uri "https://api.openai.com/v1/models" -Headers $headers
} catch {
    throw ("OpenAI connectivity check failed. Details: {0}" -f $_.Exception.Message)
}

$models = @($response.data)
$modelCount = $models.Count
$sampleModels = $models | Select-Object -First 10 -ExpandProperty id

Write-Host ""
Write-Host "OpenAI connectivity check succeeded."
if ($OrganizationId) {
    Write-Host ("Organization: {0}" -f $OrganizationId)
}
if ($ProjectId) {
    Write-Host ("Project: {0}" -f $ProjectId)
}
Write-Host ("Models visible to this key: {0}" -f $modelCount)
Write-Host "Sample model IDs:"
foreach ($modelId in $sampleModels) {
    Write-Host ("- {0}" -f $modelId)
}

