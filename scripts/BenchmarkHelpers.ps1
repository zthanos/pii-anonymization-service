Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Split-Path -Parent $PSScriptRoot)
}

function Get-ComposePaths {
    $repoRoot = Get-RepoRoot
    return @{
        Single = Join-Path $repoRoot "docker-compose.yml"
        Multi  = Join-Path $repoRoot "docker-compose.multi.yml"
    }
}

function Get-EnvFileMap {
    $repoRoot = Get-RepoRoot
    $envPath = Join-Path $repoRoot ".env"
    $values = @{}

    if (-not (Test-Path $envPath)) {
        return $values
    }

    foreach ($line in Get-Content $envPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }

        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.Length -ge 2) {
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        $values[$key] = $value
    }

    return $values
}

function Get-ConfigValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Default
    )

    $processValue = [Environment]::GetEnvironmentVariable($Name)
    if ($processValue) {
        return $processValue
    }

    $envMap = Get-EnvFileMap
    if ($envMap.ContainsKey($Name) -and $envMap[$Name]) {
        return $envMap[$Name]
    }

    return $Default
}

function Assert-CommandExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandName
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Required command '$CommandName' was not found in PATH."
    }
}

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ComposeFile,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & docker compose -f $ComposeFile @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed for '$ComposeFile' with arguments: $($Arguments -join ' ')"
    }
}

function Stop-BenchmarkStacks {
    $composePaths = Get-ComposePaths
    foreach ($composeFile in @($composePaths.Single, $composePaths.Multi)) {
        if (-not (Test-Path $composeFile)) {
            continue
        }

        try {
            & docker compose -f $composeFile down -v --remove-orphans | Out-Host
        }
        catch {
            Write-Host "Ignoring shutdown issue for ${composeFile}: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

function Start-BenchmarkStack {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ComposeFile,
        [switch]$NoBuild
    )

    $args = @("up", "-d", "--force-recreate")
    if (-not $NoBuild) {
        $args += "--build"
    }

    Invoke-Compose -ComposeFile $ComposeFile -Arguments $args
}

function Wait-ServiceHealthy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [int]$TimeoutSeconds = 240,
        [int]$IntervalSeconds = 5
    )

    $healthUrl = "$($BaseUrl.TrimEnd('/'))/health"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 10
            if ($response.StatusCode -eq 200) {
                Write-Host "Service is healthy at $healthUrl" -ForegroundColor Green
                return
            }
        }
        catch {
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        Start-Sleep -Seconds $IntervalSeconds
    }

    throw "Service did not become healthy within $TimeoutSeconds seconds: $healthUrl"
}

function Invoke-UnstructuredWarmUp {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$SystemId,
        [Parameter(Mandatory = $true)]
        [string]$ApiKey
    )

    $headers = @{
        "X-System-ID"   = $SystemId
        "Authorization" = "Bearer $ApiKey"
        "Content-Type"  = "application/json"
    }

    $body = @{
        text = "Warmup text for customer John Smith with email warmup@example.com and phone 6912345678"
        return_entity_map = $false
    } | ConvertTo-Json

    $url = "$($BaseUrl.TrimEnd('/'))/unstructured/anonymize"
    Write-Host "Warming up unstructured detector pipeline..." -ForegroundColor Cyan
    $null = Invoke-RestMethod -Uri $url -Method Post -Headers $headers -Body $body -TimeoutSec 300
}

function New-BenchmarkOutputPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prefix
    )

    $repoRoot = Get-RepoRoot
    $outputDir = Join-Path $repoRoot "data\benchmark_results"
    if (-not (Test-Path $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir | Out-Null
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    return (Join-Path $outputDir "$Prefix-$timestamp.json")
}

function Invoke-UvPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $repoRoot = Get-RepoRoot
    Push-Location $repoRoot
    try {
        & uv run python @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "uv run python failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Write-BenchmarkBanner {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title
    )

    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
}
