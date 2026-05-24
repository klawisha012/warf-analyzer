<#
.SYNOPSIS
  One-button stack starter: ensures decrypt-agent is running on the host,
  then brings up docker-compose, then waits for backend /healthz.

.NOTES
  Run from the project root.
#>

[CmdletBinding()]
param(
    [switch]$NoAgent,     # skip starting the host agent (already running externally)
    [switch]$Detached,    # leave the script after up
    [int]$AgentPort = 8788,
    [int]$ApiPort   = 8765,
    [int]$WebPort   = 3000
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Get-Item -Path $PSScriptRoot).Parent.FullName
Set-Location $projectRoot

Write-Host "== AlecaFrame stack starter ==" -ForegroundColor Cyan

# --- 1. decrypt-agent ----------------------------------------------------
if (-not $NoAgent) {
    $agentUp = $false
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$AgentPort/healthz" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $agentUp = $true }
    } catch { }

    if ($agentUp) {
        Write-Host "decrypt-agent already running on :$AgentPort" -ForegroundColor Green
    } else {
        Write-Host "starting decrypt-agent in a new PowerShell window..." -ForegroundColor Yellow
        Start-Process -FilePath "pwsh" -ArgumentList @(
            "-NoExit", "-NoProfile", "-Command",
            "Set-Location '$projectRoot'; uv run alecaframe-decrypt-agent"
        )
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline) {
            try {
                $r = Invoke-WebRequest -Uri "http://127.0.0.1:$AgentPort/healthz" -TimeoutSec 1 -UseBasicParsing
                if ($r.StatusCode -eq 200) { $agentUp = $true; break }
            } catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $agentUp) { throw "decrypt-agent did not become healthy in 30s" }
        Write-Host "decrypt-agent up." -ForegroundColor Green
    }
}

# --- 2. docker compose ---------------------------------------------------
if (-not (Test-Path ".env")) {
    Write-Host "no .env found; copying .env.example -> .env (review before reuse!)" -ForegroundColor Yellow
    Copy-Item .env.example .env
}

Write-Host "docker compose up -d ..." -ForegroundColor Cyan
docker compose up -d

# --- 3. wait for backend -------------------------------------------------
$deadline = (Get-Date).AddSeconds(60)
$apiUp = $false
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$ApiPort/healthz" -TimeoutSec 1 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $apiUp = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}

if ($apiUp) {
    Write-Host "backend healthy on :$ApiPort" -ForegroundColor Green
} else {
    Write-Warning "backend did not become healthy in 60s; check 'docker compose logs backend'"
}

Write-Host ""
Write-Host "open: http://127.0.0.1:$WebPort" -ForegroundColor Cyan
Write-Host "api:  http://127.0.0.1:$ApiPort/docs" -ForegroundColor Cyan
Write-Host "rmq:  http://127.0.0.1:15672  (aleca / aleca-local)" -ForegroundColor DarkGray

if (-not $Detached) {
    Write-Host ""
    Write-Host "tailing backend + poller logs (Ctrl+C to detach; stack keeps running)" -ForegroundColor DarkGray
    docker compose logs -f backend poller
}
