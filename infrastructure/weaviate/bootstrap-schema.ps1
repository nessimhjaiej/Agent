param(
    [string]$BaseUrl = "http://localhost:8080",
    [string]$SchemaPath = ".\schema.chunk.json"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SchemaPath)) {
    throw "Schema file not found: $SchemaPath"
}

$schema = Get-Content -Raw -Path $SchemaPath | ConvertFrom-Json
$className = $schema.class

if (-not $className) {
    throw "Schema JSON must contain 'class'."
}

$existing = Invoke-RestMethod -Method Get -Uri "$BaseUrl/v1/schema"
$classExists = $false
if ($existing.classes) {
    $classExists = $existing.classes | Where-Object { $_.class -eq $className } | ForEach-Object { $true }
}

if ($classExists) {
    Write-Host "Class '$className' already exists. Skipping create."
    exit 0
}

$body = Get-Content -Raw -Path $SchemaPath
Invoke-RestMethod -Method Post -Uri "$BaseUrl/v1/schema" -ContentType "application/json" -Body $body | Out-Null
Write-Host "Class '$className' created successfully."
