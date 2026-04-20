param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $OutputPath = "C:\kb-search-api\evidence\remaining100_2026-04-20\runtime_health_matrix_$timestamp.tsv"
}

$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

$containers = docker ps --format "{{.Names}}"

$targets = @(
    @{ url = "http://localhost:3000/api/health"; containerPattern = "infra-grafana" },
    @{ url = "http://localhost:9090/-/healthy"; containerPattern = "infra-prometheus" },
    @{ url = "http://localhost:6333/readyz"; containerPattern = "infra-qdrant" },
    @{ url = "http://localhost:3100/ready"; containerPattern = "infra-loki" },
    @{ url = "http://localhost:4000/health/readiness"; containerPattern = "apex-litellm" },
    @{ url = "http://localhost:8001/api/v1/health"; containerPattern = "kb_search_api" },
    @{ url = "http://localhost:8010/api/v1/health"; containerPattern = "kb_search_api_service" },
    @{ url = "http://localhost:8110/health"; containerPattern = "automation-master" },
    @{ url = "http://localhost:8301/arena/health"; containerPattern = "automation-arena" },
    @{ url = "http://localhost:3001/api/health"; containerPattern = "webapp-grafana-staging" },
    @{ url = "http://localhost:9091/-/healthy"; containerPattern = "webapp-prometheus-staging" },
    @{ url = "http://localhost:3002/api/health"; containerPattern = "kb_grafana" },
    @{ url = "http://localhost:9095/-/healthy"; containerPattern = "kb_prometheus" },
    @{ url = "http://localhost:8400/health"; containerPattern = "openmythos-api" }
)

"status`thttp_code`turl`tcontainer_pattern`tcontainer_present`tbody_excerpt" | Set-Content -Path $OutputPath -Encoding UTF8

foreach ($t in $targets) {
    $pattern = $t.containerPattern
    $present = ($containers | Select-String -SimpleMatch $pattern | Measure-Object).Count -gt 0

    if (-not $present) {
        "SKIP_NO_CONTAINER`t-`t$($t.url)`t$pattern`tNO`tcontainer not running" | Add-Content -Path $OutputPath -Encoding UTF8
        continue
    }

    try {
        $resp = Invoke-WebRequest -Uri $t.url -Method GET -TimeoutSec 10
        $code = [int]$resp.StatusCode
        $body = [string]$resp.Content -replace "`r|`n", " "
        if ($body.Length -gt 160) { $body = $body.Substring(0, 160) }

        if ($code -eq 200) {
            "OK`t$code`t$($t.url)`t$pattern`tYES`t$body" | Add-Content -Path $OutputPath -Encoding UTF8
        }
        else {
            "WARN_NON200`t$code`t$($t.url)`t$pattern`tYES`t$body" | Add-Content -Path $OutputPath -Encoding UTF8
        }
    }
    catch {
        $statusCode = "ERR"
        $body = $_.Exception.Message
        $response = $_.Exception.Response
        if ($response -and $response.StatusCode) {
            $statusCode = [int]$response.StatusCode
            try {
                $stream = $response.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $body = $reader.ReadToEnd()
                }
            } catch {
                # Keep exception message when body cannot be read
            }
        }
        $body = ([string]$body) -replace "`r|`n", " "
        if ($body.Length -gt 160) { $body = $body.Substring(0, 160) }
        if ($statusCode -eq 200) {
            "OK`t$statusCode`t$($t.url)`t$pattern`tYES`t$body" | Add-Content -Path $OutputPath -Encoding UTF8
        } elseif ($statusCode -eq "ERR") {
            "FAIL_REQUEST`t$statusCode`t$($t.url)`t$pattern`tYES`t$body" | Add-Content -Path $OutputPath -Encoding UTF8
        } else {
            "WARN_NON200`t$statusCode`t$($t.url)`t$pattern`tYES`t$body" | Add-Content -Path $OutputPath -Encoding UTF8
        }
    }
}

Write-Output "WROTE=$OutputPath"
