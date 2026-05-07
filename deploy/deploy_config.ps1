# Deploy unified config to server
# Phase 1, Day 3: Config Consolidation
# Usage: .\deploy_config.ps1 [-DryRun]

param(
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

# Configuration
$SERVER = "Bilirubin@192.168.1.100"
$REMOTE_PATH = "/home/Bilirubin/workspace/hermes"

Write-Host "=== Hermes Config Deployment ===" -ForegroundColor Cyan
Write-Host ""

# Check if files exist
$filesToDeploy = @(
    "hermes\src\config_loader.py",
    "hermes\config\config.yaml.template",
    "hermes\scripts\migrate_config.sh"
)

foreach ($file in $filesToDeploy) {
    if (-not (Test-Path $file)) {
        Write-Host "❌ Error: File not found: $file" -ForegroundColor Red
        exit 1
    }
}

Write-Host "📄 Files to deploy:" -ForegroundColor Green
foreach ($file in $filesToDeploy) {
    Write-Host "  - $file" -ForegroundColor Gray
}
Write-Host ""

if ($DryRun) {
    Write-Host "🔍 DRY RUN MODE - No changes will be made" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Would execute:" -ForegroundColor Yellow
    Write-Host "1. Copy config_loader.py to server" -ForegroundColor Gray
    Write-Host "2. Copy config.yaml.template to server" -ForegroundColor Gray
    Write-Host "3. Copy migrate_config.sh to server" -ForegroundColor Gray
    Write-Host "4. Run migration script" -ForegroundColor Gray
    Write-Host "5. Test config loading" -ForegroundColor Gray
    Write-Host "6. Restart services (optional)" -ForegroundColor Gray
    exit 0
}

# Confirm
Write-Host "⚠️  This will deploy config changes to production" -ForegroundColor Yellow
$confirm = Read-Host "Continue? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "❌ Aborted" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "📤 Deploying config files..." -ForegroundColor Cyan

# Copy config loader
Write-Host "  Copying config_loader.py..." -ForegroundColor Gray
scp "hermes\src\config_loader.py" "${SERVER}:${REMOTE_PATH}/src/"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to copy config_loader.py" -ForegroundColor Red
    exit 1
}
Write-Host "  ✅ Copied config_loader.py" -ForegroundColor Green

# Copy template
Write-Host "  Copying config template..." -ForegroundColor Gray
scp "hermes\config\config.yaml.template" "${SERVER}:${REMOTE_PATH}/config/"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to copy config template" -ForegroundColor Red
    exit 1
}
Write-Host "  ✅ Copied config template" -ForegroundColor Green

# Copy migration script
Write-Host "  Copying migration script..." -ForegroundColor Gray
scp "hermes\scripts\migrate_config.sh" "${SERVER}:${REMOTE_PATH}/scripts/"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to copy migration script" -ForegroundColor Red
    exit 1
}
Write-Host "  ✅ Copied migration script" -ForegroundColor Green

# Make script executable
Write-Host ""
Write-Host "🔧 Making script executable..." -ForegroundColor Cyan
ssh $SERVER "chmod +x ${REMOTE_PATH}/scripts/migrate_config.sh"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to make script executable" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Script is executable" -ForegroundColor Green

Write-Host ""
Write-Host "🔧 Running migration..." -ForegroundColor Cyan
Write-Host ""

# Run migration
ssh $SERVER "cd $REMOTE_PATH && bash scripts/migrate_config.sh"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ Migration failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🧪 Testing config loading..." -ForegroundColor Cyan

# Test config loading
$testResult = ssh $SERVER "cd $REMOTE_PATH && source ~/.hermes/automation.env && python3 -c 'from src.config_loader import ConfigLoader; c = ConfigLoader(); c.load(); c.validate(); print(\"OK\")' 2>&1"
if ($LASTEXITCODE -eq 0 -and $testResult -match "OK") {
    Write-Host "✅ Config loads successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Config loading failed:" -ForegroundColor Red
    Write-Host $testResult -ForegroundColor Red
    Write-Host ""
    Write-Host "Check environment variables in ~/.hermes/automation.env" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "✅ Config deployment complete!" -ForegroundColor Green
Write-Host ""

# Ask about restarting services
Write-Host "Restart services now? (yes/no)" -ForegroundColor Yellow
$restart = Read-Host
if ($restart -eq "yes") {
    Write-Host ""
    Write-Host "🔄 Restarting services..." -ForegroundColor Cyan
    
    ssh $SERVER "sudo systemctl restart hermes-gateway"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ hermes-gateway restarted" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Failed to restart hermes-gateway" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "Checking service status..." -ForegroundColor Cyan
    ssh $SERVER "sudo systemctl status hermes-gateway --no-pager -l"
}

Write-Host ""
Write-Host "📊 Summary:" -ForegroundColor Cyan
Write-Host "  ✅ Config loader deployed" -ForegroundColor Green
Write-Host "  ✅ Config template deployed" -ForegroundColor Green
Write-Host "  ✅ Migration completed" -ForegroundColor Green
Write-Host "  ✅ Config validated" -ForegroundColor Green
Write-Host ""
Write-Host "Config location: ~/.hermes/config.yaml" -ForegroundColor Gray
Write-Host "Backup location: ~/.hermes/config_backup_*" -ForegroundColor Gray
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Review config: ssh $SERVER 'cat ~/.hermes/config.yaml'" -ForegroundColor Gray
Write-Host "2. Check logs: ssh $SERVER 'sudo journalctl -u hermes-gateway -n 50'" -ForegroundColor Gray
Write-Host "3. Run tests: ssh $SERVER 'cd $REMOTE_PATH && pytest tests/unit/test_config_loader.py -v'" -ForegroundColor Gray
