#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Execute a quick fix command on the server
.DESCRIPTION
    Run arbitrary commands on the server for quick fixes
.EXAMPLE
    .\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"
.EXAMPLE
    .\quick_fix.ps1 -Script "fix_script.sh"
#>

param(
    [string]$Command = "",
    [string]$Script = "",
    [string]$ServerHost = "",
    [switch]$ShowLogs
)

$ErrorActionPreference = "Stop"

# Load config
$configPath = Join-Path $PSScriptRoot ".deploy-config"
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    if (-not $ServerHost) { $ServerHost = $config.server_host }
}

if (-not $ServerHost) {
    Write-Host "❌ Server host not configured!" -ForegroundColor Red
    exit 1
}

Write-Host "⚡ Quick Fix" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray

if ($ShowLogs) {
    Write-Host "📋 Fetching recent logs..." -ForegroundColor Yellow
    Write-Host ""
    
    $logCommands = @(
        "echo '=== Service Status ==='",
        "systemctl status brain-mcp hermes-gateway n8n --no-pager | head -50",
        "echo ''",
        "echo '=== Recent Errors ==='",
        "sudo journalctl -p err -n 20 --no-pager",
        "echo ''",
        "echo '=== Health Check ==='",
        "/home/Bilirubin/workspace/host_checklist.sh"
    )
    
    ssh $ServerHost ($logCommands -join " && ")
    exit 0
}

if ($Script) {
    if (-not (Test-Path $Script)) {
        Write-Host "❌ Script not found: $Script" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "📤 Uploading script: $Script" -ForegroundColor Yellow
    $remotePath = "/tmp/quick_fix_$(Get-Date -Format 'yyyyMMdd_HHmmss').sh"
    scp $Script "$ServerHost`:$remotePath"
    
    Write-Host "▶️  Executing script..." -ForegroundColor Yellow
    ssh $ServerHost "chmod +x $remotePath && $remotePath && rm $remotePath"
    
} elseif ($Command) {
    Write-Host "▶️  Executing: $Command" -ForegroundColor Yellow
    Write-Host ""
    ssh $ServerHost $Command
    
} else {
    Write-Host "❌ No command or script specified!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\quick_fix.ps1 -Command 'sudo systemctl restart brain-mcp'"
    Write-Host "  .\quick_fix.ps1 -Script 'fix_script.sh'"
    Write-Host "  .\quick_fix.ps1 -ShowLogs"
    exit 1
}

Write-Host ""
Write-Host "✅ Done!" -ForegroundColor Green
