[CmdletBinding()]
param(
    [string]$Text,
    [string]$TextPath,
    [string[]]$ExpectedValue,
    [string]$ExpectedValuesPath,
    [string]$BaseUrl = "http://localhost:8000",
    [string]$SystemId = "customer_db",
    [string]$ApiKey = "",
    [string]$OutputPath
)

. (Join-Path $PSScriptRoot "BenchmarkHelpers.ps1")

if (-not $ApiKey) {
    $ApiKey = Get-ConfigValue -Name "API_KEY" -Default "dev_api_key_12345"
}

function Resolve-InputText {
    if ($Text -and $TextPath) {
        throw "Use either -Text or -TextPath, not both."
    }

    if ($TextPath) {
        if (-not (Test-Path $TextPath)) {
            throw "Text file not found: $TextPath"
        }
        return (Get-Content $TextPath -Raw)
    }

    if ($Text) {
        return $Text
    }

    throw "You must provide either -Text or -TextPath."
}

function Resolve-ExpectedItems {
    if ($ExpectedValue -and $ExpectedValuesPath) {
        throw "Use either -ExpectedValue or -ExpectedValuesPath, not both."
    }

    if ($ExpectedValuesPath) {
        if (-not (Test-Path $ExpectedValuesPath)) {
            throw "Expected values file not found: $ExpectedValuesPath"
        }

        $parsed = Get-Content $ExpectedValuesPath -Raw | ConvertFrom-Json
        $items = @()
        foreach ($entry in $parsed) {
            if ($entry -is [string]) {
                $items += [pscustomobject]@{
                    value = $entry
                    type = $null
                }
                continue
            }

            $items += [pscustomobject]@{
                value = [string]$entry.value
                type = if ($null -ne $entry.type) { [string]$entry.type } else { $null }
            }
        }
        return $items
    }

    if ($ExpectedValue) {
        return @($ExpectedValue | ForEach-Object {
            [pscustomobject]@{
                value = $_
                type = $null
            }
        })
    }

    throw "You must provide either -ExpectedValue or -ExpectedValuesPath."
}

function Get-EntityMapEntries {
    param(
        [Parameter(Mandatory = $true)]
        $EntityMap
    )

    if ($null -eq $EntityMap) {
        return @()
    }

    $entries = @()
    foreach ($property in $EntityMap.PSObject.Properties) {
        $entries += [pscustomobject]@{
            token = $property.Name
            type = [string]$property.Value.type
            value = [string]$property.Value.value
            start = [int]$property.Value.start
            end = [int]$property.Value.end
        }
    }
    return $entries
}

Assert-CommandExists -CommandName "powershell"

$inputText = Resolve-InputText
$expectedItems = Resolve-ExpectedItems

$headers = @{
    "X-System-ID"   = $SystemId
    "Authorization" = "Bearer $ApiKey"
    "Content-Type"  = "application/json"
}

$requestBody = @{
    text = $inputText
    return_entity_map = $true
} | ConvertTo-Json -Depth 5

Write-BenchmarkBanner -Title "Unstructured Quality Check"
Write-Host "Calling $($BaseUrl.TrimEnd('/'))/unstructured/anonymize" -ForegroundColor Cyan

$response = Invoke-RestMethod `
    -Uri "$($BaseUrl.TrimEnd('/'))/unstructured/anonymize" `
    -Method Post `
    -Headers $headers `
    -Body $requestBody `
    -TimeoutSec 300

$anonymizedText = [string]$response.anonymized_text
$entityEntries = Get-EntityMapEntries -EntityMap $response.entity_map
$results = @()

foreach ($expected in $expectedItems) {
    $matchingEntries = @($entityEntries | Where-Object {
        $_.value -eq $expected.value -and (
            -not $expected.type -or $_.type -eq $expected.type
        )
    })

    $foundViaEntityMap = $matchingEntries.Count -gt 0
    $stillPresent = $anonymizedText.Contains($expected.value)
    $matched = $foundViaEntityMap -or (-not $stillPresent)

    $results += [pscustomobject]@{
        value = $expected.value
        expected_type = $expected.type
        matched = $matched
        match_mode = if ($foundViaEntityMap) { "entity_map" } elseif (-not $stillPresent) { "removed_from_output" } else { "missed" }
        detected_type = if ($foundViaEntityMap) { $matchingEntries[0].type } else { $null }
        still_present_in_output = $stillPresent
    }
}

$expectedValuesSet = @{}
foreach ($expected in $expectedItems) {
    $expectedValuesSet[$expected.value] = $true
}

$unexpectedEntityMapEntries = @($entityEntries | Where-Object {
    -not $expectedValuesSet.ContainsKey($_.value)
})

$matchedCount = @($results | Where-Object { $_.matched }).Count
$missedCount = @($results | Where-Object { -not $_.matched }).Count
$totalExpected = $results.Count
$successRate = if ($totalExpected -gt 0) {
    [math]::Round(($matchedCount / $totalExpected) * 100, 2)
}
else {
    0.0
}

Write-Host ""
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "Expected values: $totalExpected"
Write-Host "Matched: $matchedCount"
Write-Host "Missed: $missedCount"
Write-Host "Unexpected tokenized values: $($unexpectedEntityMapEntries.Count)"
Write-Host "Success rate: $successRate%"

Write-Host ""
Write-Host "Per-value results" -ForegroundColor Cyan
$results | Select-Object value, expected_type, matched, match_mode, detected_type, still_present_in_output | Format-Table -AutoSize

if ($unexpectedEntityMapEntries.Count -gt 0) {
    Write-Host ""
    Write-Host "Unexpected tokenized values" -ForegroundColor Yellow
    $unexpectedEntityMapEntries | Select-Object value, type, token | Format-Table -AutoSize
}

if ($OutputPath) {
    $report = [pscustomobject]@{
        generated_at = (Get-Date).ToString("o")
        base_url = $BaseUrl
        system_id = $SystemId
        success_rate = $successRate
        expected_count = $totalExpected
        matched_count = $matchedCount
        missed_count = $missedCount
        unexpected_tokenized_count = $unexpectedEntityMapEntries.Count
        anonymized_text = $anonymizedText
        results = $results
        unexpected_tokenized_values = $unexpectedEntityMapEntries
    }

    $outputDirectory = Split-Path -Parent $OutputPath
    if ($outputDirectory -and -not (Test-Path $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory | Out-Null
    }

    $report | ConvertTo-Json -Depth 8 | Set-Content -Path $OutputPath -Encoding UTF8
    Write-Host ""
    Write-Host "Saved report to $OutputPath" -ForegroundColor Green
}
