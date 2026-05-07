# Deploy disk cleanup scripts to server
# Phase 1, Day 4
# Usage: .\deploy_cleanup.ps1 [-DryRun]

param(
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

# Load server config
$configPath = Join-Path $PSScriptRoot ".deploy-config"
if (-not (Test-Path $configPath)) {
    Write-Host "❌ Config file not found: $configPath" -ForegroundColor Red
    Write-Host "Run setup_deploy.ps1 first" -ForegroundColor Yellow
    exit 1
}

$config = Get-Content $configPath | ConvertFrom-StringData
$SERVER = "$($config.SERVER_USER)@$($config.SERVER_HOST)"
$REMOTE_PATH = $config.REMOTE_PATH

Write-Host "=== Hermes Cleanup Deployment ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server: $SERVER" -ForegroundColor Gray
Write-Host "Path: $REMOTE_PATH" -ForegroundColor Gray
Write-Host ""

if ($DryRun) {
    Write-Host "🔍 DRY RUN MODE" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Would execute:" -ForegroundColor Yellow
    Write-Host "1. Copy cleanup scripts to server" -ForegroundColor Gray
    Write-Host "2. Run cleanup (dry-run)" -ForegroundColor Gray
    Write-Host "3. Setup automatic cleanup" -ForegroundColor Gray
    Write-Host "4. Verify disk usage" -ForegroundColor Gray
    exit 0
}

Write-Host "📤 Deploying cleanup scripts..." -ForegroundColor Cyan

# Copy scripts
Write-Host "Copying cleanup_disk.sh..." -ForegroundColor Gray
scp "hermes\scripts\cleanup_disk.sh" "${SERVER}:${REMOTE_PATH}/scripts/"

Write-Host "Copying setup_automatic_cleanup.sh..." -ForegroundColor Gray
scp "hermes\scripts\setup_automatic_cleanup.sh" "${SERVER}:${REMOTE_PATH}/scripts/"

Write-Host "✅ Scripts copied" -ForegroundColor Green

# Make executable
Write-Host ""
Write-Host "Making scripts executable..." -ForegroundColor Gray
ssh $SERVER "chmod +x ${REMOTE_PATH}/scripts/cleanup_disk.sh"
ssh $SERVER "chmod +x ${REMOTE_PATH}/scripts/setup_automatic_cleanup.sh"

Write-Host ""
Write-Host "🔍 Running cleanup (dry-run)..." -ForegroundColor Cyan
ssh $SERVER "cd $REMOTE_PATH && bash scripts/cleanup_disk.sh --dry-run"

Write-Host ""
$confirm = Read-Host "Run actual cleanup? (yes/no)"
if ($confirm -eq "yes") {
    Write-Host ""
    Write-Host "🧹 Running cleanup..." -ForegroundColor Cyan
    ssh $SERVER "cd $REMOTE_PATH && bash scripts/cleanup_disk.sh"
}

Write-Host ""
$setupAuto = Read-Host "Setup automatic cleanup? (yes/no)"
if ($setupAuto -eq "yes") {
    Write-Host ""
    Write-Host "🔧 Setting up automatic cleanup..." -ForegroundColor Cyan
    ssh $SERVER "cd $REMOTE_PATH && sudo bash scripts/setup_automatic_cleanup.sh"
}

Write-Host ""
Write-Host "📊 Final disk usage:" -ForegroundColor Cyan
ssh $SERVER "df -h / | grep -E 'Filesystem|/$'"

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
