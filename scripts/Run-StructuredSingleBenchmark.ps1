[CmdletBinding()]
param(
    [string]$SystemId = "customer_db",
    [string]$BaseUrl = "http://localhost:8000",
    [string]$GrpcHost = "localhost:50051",
    [string]$ApiKey = "",
    [switch]$NoBuild
)

. (Join-Path $PSScriptRoot "BenchmarkHelpers.ps1")

if (-not $ApiKey) {
    $ApiKey = Get-ConfigValue -Name "API_KEY" -Default "dev_api_key_12345"
}

Assert-CommandExists -CommandName "docker"
Assert-CommandExists -CommandName "uv"

$composeFile = (Get-ComposePaths).Single
$outputPath = New-BenchmarkOutputPath -Prefix "structured-single"

Write-BenchmarkBanner -Title "Structured Benchmark - Single Stack"
Write-Host "Output: $outputPath"
Write-Host "API base URL: $BaseUrl"
Write-Host "gRPC host: $GrpcHost"

Stop-BenchmarkStacks
Start-BenchmarkStack -ComposeFile $composeFile -NoBuild:$NoBuild
Wait-ServiceHealthy -BaseUrl $BaseUrl

Invoke-UvPython -Arguments @(
    "benchmarks/benchmark_structured.py",
    "--base-url", $BaseUrl,
    "--grpc-host", $GrpcHost,
    "--system-id", $SystemId,
    "--api-key", $ApiKey,
    "--output", $outputPath
)

Write-Host "Structured single benchmark results saved to $outputPath" -ForegroundColor Green
