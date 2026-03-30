param(
    [int]$Days = 7,
    [string]$OpenAIAdminKey = "",
    [string]$OrganizationId = "",
    [string]$ProjectId = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptRoot)
$envFilePath = Join-Path $repoRoot ".env"

if ($Days -le 0) {
    throw "Days must be greater than 0."
}

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }

    $prefix = "$Name="
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

if (-not $OpenAIAdminKey) {
    $OpenAIAdminKey = $env:OPENAI_ADMIN_KEY
}
if (-not $OpenAIAdminKey) {
    $OpenAIAdminKey = $env:OPENAI_KEY
}
if (-not $OpenAIAdminKey) {
    $OpenAIAdminKey = Get-DotEnvValue -Path $envFilePath -Name "OPENAI_ADMIN_KEY"
}
if (-not $OpenAIAdminKey) {
    $OpenAIAdminKey = Get-DotEnvValue -Path $envFilePath -Name "OPENAI_KEY"
}
if (-not $OpenAIAdminKey) {
    throw "Set OPENAI_ADMIN_KEY or OPENAI_KEY, add one of them to the repo root .env, or pass -OpenAIAdminKey."
}

$startTime = [DateTimeOffset]::UtcNow.AddDays(-$Days)
$startUnix = [int][Math]::Floor($startTime.ToUnixTimeSeconds())

function New-Headers {
    $headers = @{
        Authorization = "Bearer $OpenAIAdminKey"
        "Content-Type" = "application/json"
    }
    if ($OrganizationId) {
        $headers["OpenAI-Organization"] = $OrganizationId
    }
    if ($ProjectId) {
        $headers["OpenAI-Project"] = $ProjectId
    }
    return $headers
}

function Invoke-OpenAIGet {
    param(
        [string]$Path,
        [hashtable]$Query
    )

    $pairs = @()
    foreach ($entry in $Query.GetEnumerator()) {
        if ($null -eq $entry.Value -or $entry.Value -eq "") {
            continue
        }
        if ($entry.Value -is [System.Array]) {
            foreach ($item in $entry.Value) {
                $pairs += ("{0}={1}" -f $entry.Key, [uri]::EscapeDataString([string]$item))
            }
        } else {
            $pairs += ("{0}={1}" -f $entry.Key, [uri]::EscapeDataString([string]$entry.Value))
        }
    }

    $queryString = ""
    if ($pairs.Count -gt 0) {
        $queryString = "?" + ($pairs -join "&")
    }

    $url = "https://api.openai.com$Path$queryString"
    return Invoke-RestMethod -Method Get -Uri $url -Headers (New-Headers)
}

function Get-AllPages {
    param(
        [string]$Path,
        [hashtable]$Query
    )

    $allData = @()
    $page = $null

    while ($true) {
        $effectiveQuery = @{}
        foreach ($entry in $Query.GetEnumerator()) {
            $effectiveQuery[$entry.Key] = $entry.Value
        }
        if ($page) {
            $effectiveQuery["page"] = $page
        }

        $response = Invoke-OpenAIGet -Path $Path -Query $effectiveQuery
        if ($response.data) {
            $allData += @($response.data)
        }

        if (-not $response.has_more -or -not $response.next_page) {
            break
        }
        $page = [string]$response.next_page
    }

    return $allData
}

function Sum-UsageField {
    param(
        [object[]]$Buckets,
        [string]$FieldName
    )

    $total = 0.0
    foreach ($bucket in $Buckets) {
        foreach ($result in @($bucket.results)) {
            $value = $result.$FieldName
            if ($null -ne $value) {
                $total += [double]$value
            }
        }
    }
    return $total
}

function Sum-Costs {
    param([object[]]$Buckets)

    $total = 0.0
    $currency = "usd"
    foreach ($bucket in $Buckets) {
        foreach ($result in @($bucket.results)) {
            if ($result.amount -and $null -ne $result.amount.value) {
                $total += [double]$result.amount.value
            }
            if ($result.amount -and $result.amount.currency) {
                $currency = [string]$result.amount.currency
            }
        }
    }
    return @{
        total = [Math]::Round($total, 4)
        currency = $currency
    }
}

function Format-Int {
    param([double]$Value)
    return ("{0:N0}" -f [Math]::Round($Value, 0))
}

function Get-ScopeLabel {
    if ($ProjectId) {
        return "project"
    }
    if ($OrganizationId) {
        return "organization"
    }
    return "scope"
}

try {
    $costBuckets = Get-AllPages -Path "/v1/organization/costs" -Query @{
        start_time = $startUnix
        bucket_width = "1d"
        limit = [Math]::Min($Days, 180)
        group_by = @("line_item")
    }

    $completionBuckets = Get-AllPages -Path "/v1/organization/usage/completions" -Query @{
        start_time = $startUnix
        bucket_width = "1d"
        limit = [Math]::Min($Days, 31)
        group_by = @("model")
    }

    $embeddingBuckets = Get-AllPages -Path "/v1/organization/usage/embeddings" -Query @{
        start_time = $startUnix
        bucket_width = "1d"
        limit = [Math]::Min($Days, 31)
        group_by = @("model")
    }

    $audioBuckets = Get-AllPages -Path "/v1/organization/usage/audio_transcriptions" -Query @{
        start_time = $startUnix
        bucket_width = "1d"
        limit = [Math]::Min($Days, 31)
        group_by = @("model")
    }
} catch {
    throw (
        "OpenAI usage request failed. Confirm the key has organization usage access. " +
        "Details: {0}" -f $_.Exception.Message
    )
}

$costSummary = Sum-Costs -Buckets $costBuckets
$completionInput = Sum-UsageField -Buckets $completionBuckets -FieldName "input_tokens"
$completionOutput = Sum-UsageField -Buckets $completionBuckets -FieldName "output_tokens"
$completionRequests = Sum-UsageField -Buckets $completionBuckets -FieldName "num_model_requests"
$embeddingInput = Sum-UsageField -Buckets $embeddingBuckets -FieldName "input_tokens"
$embeddingRequests = Sum-UsageField -Buckets $embeddingBuckets -FieldName "num_model_requests"
$audioInput = Sum-UsageField -Buckets $audioBuckets -FieldName "input_tokens"
$audioRequests = Sum-UsageField -Buckets $audioBuckets -FieldName "num_model_requests"
$scopeLabel = Get-ScopeLabel

Write-Host ""
Write-Host (
    "OpenAI usage summary for the last {0} day(s): total {1} cost = {2} {3}." -f
    $Days,
    $scopeLabel,
    $costSummary.total,
    $costSummary.currency.ToUpperInvariant()
)
Write-Host ("Window start (UTC): {0}" -f $startTime.ToString("u"))
if ($OrganizationId) {
    Write-Host ("Organization: {0}" -f $OrganizationId)
}
if ($ProjectId) {
    Write-Host ("Project: {0}" -f $ProjectId)
}
Write-Host ""
Write-Host ("Costs: {0} {1}" -f $costSummary.total, $costSummary.currency.ToUpperInvariant())
Write-Host ("Completions: requests={0}, input_tokens={1}, output_tokens={2}" -f (Format-Int $completionRequests), (Format-Int $completionInput), (Format-Int $completionOutput))
Write-Host ("Embeddings: requests={0}, input_tokens={1}" -f (Format-Int $embeddingRequests), (Format-Int $embeddingInput))
Write-Host ("Audio transcriptions: requests={0}, input_tokens={1}" -f (Format-Int $audioRequests), (Format-Int $audioInput))

if ($costBuckets.Count -gt 0) {
    Write-Host ""
    Write-Host "Cost buckets:"
    foreach ($bucket in $costBuckets) {
        $bucketDate = [DateTimeOffset]::FromUnixTimeSeconds([int64]$bucket.start_time).UtcDateTime.ToString("yyyy-MM-dd")
        $bucketTotal = 0.0
        foreach ($result in @($bucket.results)) {
            if ($result.amount -and $null -ne $result.amount.value) {
                $bucketTotal += [double]$result.amount.value
            }
        }
        Write-Host ("- {0}: {1} {2}" -f $bucketDate, ([Math]::Round($bucketTotal, 4)), $costSummary.currency.ToUpperInvariant())
    }
}
