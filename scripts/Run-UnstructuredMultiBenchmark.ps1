[CmdletBinding()]
param(
    [string]$SystemId = "customer_db",
    [string]$BaseUrl = "http://localhost:8000",
    [string]$ApiKey = "",
    [int]$Requests = 200,
    [int]$Concurrency = 20,
    [double]$ThroughputSla = 200,
    [double]$P95SlaMs = 150,
    [switch]$SkipDeanonymize,
    [switch]$NoBuild
)

. (Join-Path $PSScriptRoot "BenchmarkHelpers.ps1")

if (-not $ApiKey) {
    $ApiKey = Get-ConfigValue -Name "API_KEY" -Default "dev_api_key_12345"
}

Assert-CommandExists -CommandName "docker"
Assert-CommandExists -CommandName "uv"

$composeFile = (Get-ComposePaths).Multi
$outputPath = New-BenchmarkOutputPath -Prefix "unstructured-multi"

Write-BenchmarkBanner -Title "Unstructured Benchmark - Multi Stack"
Write-Host "Output: $outputPath"
Write-Host "API base URL: $BaseUrl"
Write-Host "Requests per scenario: $Requests"
Write-Host "Concurrency: $Concurrency"

Stop-BenchmarkStacks
Start-BenchmarkStack -ComposeFile $composeFile -NoBuild:$NoBuild
Wait-ServiceHealthy -BaseUrl $BaseUrl
Invoke-UnstructuredWarmUp -BaseUrl $BaseUrl -SystemId $SystemId -ApiKey $ApiKey

$arguments = @(
    "benchmarks/benchmark_unstructured.py",
    "--base-url", $BaseUrl,
    "--system-id", $SystemId,
    "--api-key", $ApiKey,
    "--requests", $Requests.ToString(),
    "--concurrency", $Concurrency.ToString(),
    "--throughput-sla", $ThroughputSla.ToString([System.Globalization.CultureInfo]::InvariantCulture),
    "--p95-sla-ms", $P95SlaMs.ToString([System.Globalization.CultureInfo]::InvariantCulture),
    "--output", $outputPath
)

if ($SkipDeanonymize) {
    $arguments += "--skip-deanonymize"
}

Invoke-UvPython -Arguments $arguments

Write-Host "Unstructured multi benchmark results saved to $outputPath" -ForegroundColor Green
