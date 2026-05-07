# Deploy archive dead code script to server
# Phase 1, Day 5
# Usage: .\deploy_archive.ps1 [-DryRun]

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

Write-Host "=== Hermes Archive Deployment ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server: $SERVER" -ForegroundColor Gray
Write-Host "Path: $REMOTE_PATH" -ForegroundColor Gray
Write-Host ""

if ($DryRun) {
    Write-Host "🔍 DRY RUN MODE" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Would execute:" -ForegroundColor Yellow
    Write-Host "1. Copy archive script to server" -ForegroundColor Gray
    Write-Host "2. Run archive (dry-run)" -ForegroundColor Gray
    Write-Host "3. Run actual archive" -ForegroundColor Gray
    Write-Host "4. Verify no broken references" -ForegroundColor Gray
    exit 0
}

Write-Host "📤 Deploying archive script..." -ForegroundColor Cyan

# Copy script
Write-Host "Copying archive_dead_code.sh..." -ForegroundColor Gray
scp "hermes\scripts\archive_dead_code.sh" "${SERVER}:${REMOTE_PATH}/scripts/"

Write-Host "✅ Script copied" -ForegroundColor Green

# Make executable
Write-Host ""
Write-Host "Making script executable..." -ForegroundColor Gray
ssh $SERVER "chmod +x ${REMOTE_PATH}/scripts/archive_dead_code.sh"

Write-Host ""
Write-Host "🔍 Running archive (dry-run)..." -ForegroundColor Cyan
ssh $SERVER "cd $REMOTE_PATH && bash scripts/archive_dead_code.sh --dry-run"

Write-Host ""
$confirm = Read-Host "Run actual archive? (yes/no)"
if ($confirm -eq "yes") {
    Write-Host ""
    Write-Host "📦 Running archive..." -ForegroundColor Cyan
    ssh $SERVER "cd $REMOTE_PATH && bash scripts/archive_dead_code.sh"
    
    Write-Host ""
    Write-Host "🧪 Verifying no broken references..." -ForegroundColor Cyan
    
    # Check for broken imports
    Write-Host "Checking for broken imports..." -ForegroundColor Gray
    $nimImports = ssh $SERVER "cd $REMOTE_PATH && grep -r 'from nim' src/ 2>/dev/null || true"
    if ($nimImports) {
        Write-Host "⚠️  Found nim imports:" -ForegroundColor Yellow
        Write-Host $nimImports
    } else {
        Write-Host "✅ No nim imports found" -ForegroundColor Green
    }
    
    # Run tests
    Write-Host ""
    Write-Host "Running tests..." -ForegroundColor Gray
    ssh $SERVER "cd $REMOTE_PATH && python3 -m pytest tests/unit -v --tb=short"
    
    Write-Host ""
    Write-Host "✅ Archive complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Archived components:" -ForegroundColor Cyan
    Write-Host "  - nim-orchestrator/" -ForegroundColor Gray
    Write-Host "  - n8n-workflows/" -ForegroundColor Gray
    Write-Host "  - temp-files/" -ForegroundColor Gray
    Write-Host "  - htmlcov/" -ForegroundColor Gray
    Write-Host "  - pytest-cache/" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Archive location: archive/2026-05-06-day5/" -ForegroundColor Gray
}

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
