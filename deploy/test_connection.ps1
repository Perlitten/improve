#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Test connection to the deployment server
.DESCRIPTION
    Verifies SSH access, workspace existence, and key services.
#>

param(
    [string]$ServerHost = "",
    [string]$ServerPath = "/home/Bilirubin/workspace"
)

# Load config
$configPath = Join-Path $PSScriptRoot ".deploy-config"
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    if (-not $ServerHost) { $ServerHost = $config.server_host }
    if ($config.server_path) { $ServerPath = $config.server_path }
}

if (-not $ServerHost) {
    Write-Host "ERROR: Server host not configured!" -ForegroundColor Red
    exit 1
}

Write-Host "Testing connection to $ServerHost..." -ForegroundColor Cyan

# Identity file check
$identity = ""
$keyPath = Join-Path $env:USERPROFILE ".ssh\google_compute_engine"
if (Test-Path $keyPath) { $identity = "-i '$keyPath'" }

# 1. Basic SSH check
Write-Host "[1/4] SSH Connection... " -NoNewline
$check = if ($identity) { ssh -i $keyPath -o ConnectTimeout=5 -o BatchMode=yes $ServerHost "echo OK" } else { ssh -o ConnectTimeout=5 -o BatchMode=yes $ServerHost "echo OK" }
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK" -ForegroundColor Green
} else {
    Write-Host "FAILED" -ForegroundColor Red
    Write-Host "Check your SSH keys and host availability."
    exit 1
}

# 2. Workspace check
Write-Host "[2/4] Workspace directory... " -NoNewline
$workspaceCheck = if ($identity) { ssh -i $keyPath $ServerHost "test -d $ServerPath && echo OK" } else { ssh $ServerHost "test -d $ServerPath && echo OK" }
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK" -ForegroundColor Green
} else {
    Write-Host "NOT FOUND" -ForegroundColor Yellow
    Write-Host "Workspace will be created during first sync."
}

# 3. Services check
Write-Host "[3/4] Services status:" -ForegroundColor White
$services = @("brain-mcp", "hermes-gateway")
foreach ($svc in $services) {
    Write-Host "  - $svc: " -NoNewline
    $status = if ($identity) { ssh -i $keyPath $ServerHost "systemctl is-active $svc" } else { ssh $ServerHost "systemctl is-active $svc" }
    if ($LASTEXITCODE -eq 0) {
        Write-Host "ACTIVE" -ForegroundColor Green
    } else {
        Write-Host "INACTIVE/MISSING" -ForegroundColor Red
    }
}

# 4. Sudo check
Write-Host "[4/4] Sudo access... " -NoNewline
$sudoCheck = if ($identity) { ssh -i $keyPath $ServerHost "sudo -n true" } else { ssh $ServerHost "sudo -n true" }
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK" -ForegroundColor Green
} else {
    Write-Host "REQUIRED" -ForegroundColor Yellow
    Write-Host "Some operations might require manual password entry."
}

Write-Host "DONE: Connection test complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  - Sync files:     .\sync_to_server.ps1" -ForegroundColor White
Write-Host "  - Quick command:  .\quick_fix.ps1 -ShowLogs" -ForegroundColor White
Write-Host "  - Read guide:     Get-Content DEPLOY_README.md" -ForegroundColor White
