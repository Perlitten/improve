#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Deploy fixes to the remote server via Git push + SSH pull
.DESCRIPTION
    This script commits local changes, pushes to GitHub, and triggers a pull on the server
.PARAMETER Message
    Commit message (default: "Auto-deploy from Windows")
.PARAMETER ServerHost
    SSH host (default: read from .deploy-config)
.PARAMETER ServerPath
    Path on server (default: /home/Bilirubin/workspace)
.PARAMETER DryRun
    Show what would be done without executing
#>

param(
    [string]$Message = "Auto-deploy from Windows $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    [string]$ServerHost = "",
    [string]$ServerPath = "/home/Bilirubin/workspace",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Load config if exists
$configPath = Join-Path $PSScriptRoot ".deploy-config"
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    if (-not $ServerHost) { $ServerHost = $config.server_host }
    if ($config.server_path) { $ServerPath = $config.server_path }
}

if (-not $ServerHost) {
    Write-Host "❌ Server host not configured!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Create .deploy-config file with:" -ForegroundColor Yellow
    Write-Host @"
{
    "server_host": "user@your-server.com",
    "server_path": "/home/Bilirubin/workspace"
}
"@
    exit 1
}

Write-Host "🚀 Deploy to Server" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "Server: $ServerHost" -ForegroundColor White
Write-Host "Path:   $ServerPath" -ForegroundColor White
Write-Host "Message: $Message" -ForegroundColor White
Write-Host ""

# Step 1: Check git status
Write-Host "📋 Checking git status..." -ForegroundColor Yellow
$status = git status --porcelain
if (-not $status) {
    Write-Host "✅ No changes to deploy" -ForegroundColor Green
    exit 0
}

Write-Host "Changes detected:" -ForegroundColor White
git status --short

# Step 2: Commit changes
Write-Host ""
Write-Host "📦 Committing changes..." -ForegroundColor Yellow
if ($DryRun) {
    Write-Host "[DRY RUN] Would run: git add -A" -ForegroundColor DarkGray
    Write-Host "[DRY RUN] Would run: git commit -m '$Message'" -ForegroundColor DarkGray
} else {
    git add -A
    git commit -m $Message
    Write-Host "✅ Committed" -ForegroundColor Green
}

# Step 3: Push to GitHub
Write-Host ""
Write-Host "⬆️  Pushing to GitHub..." -ForegroundColor Yellow
if ($DryRun) {
    Write-Host "[DRY RUN] Would run: git push origin master" -ForegroundColor DarkGray
} else {
    git push origin master
    Write-Host "✅ Pushed to GitHub" -ForegroundColor Green
}

# Step 4: Pull on server
Write-Host ""
Write-Host "⬇️  Pulling on server..." -ForegroundColor Yellow
$sshCommand = @"
cd $ServerPath && \
git fetch origin && \
git reset --hard origin/master && \
echo '✅ Server updated successfully'
"@

if ($DryRun) {
    Write-Host "[DRY RUN] Would run SSH command:" -ForegroundColor DarkGray
    Write-Host $sshCommand -ForegroundColor DarkGray
} else {
    ssh $ServerHost $sshCommand
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Server updated successfully!" -ForegroundColor Green
    } else {
        Write-Host "❌ Server update failed!" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "✨ Deploy complete!" -ForegroundColor Green
