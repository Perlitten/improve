# Deploy Phase 1 Gate monitoring script to server
# Usage: .\deploy_gate_monitoring.ps1

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

Write-Host "=== Phase 1 Gate Monitoring Deployment ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server: $SERVER" -ForegroundColor Gray
Write-Host "Path: $REMOTE_PATH" -ForegroundColor Gray
Write-Host ""

Write-Host "📤 Deploying gate monitoring script..." -ForegroundColor Cyan

# Copy script
Write-Host "Copying gate_monitoring.sh..." -ForegroundColor Gray
scp "hermes\scripts\gate_monitoring.sh" "${SERVER}:${REMOTE_PATH}/scripts/"

Write-Host "✅ Script copied" -ForegroundColor Green

# Make executable
Write-Host ""
Write-Host "Making script executable..." -ForegroundColor Gray
ssh $SERVER "chmod +x ${REMOTE_PATH}/scripts/gate_monitoring.sh"

Write-Host ""
Write-Host "🧪 Running initial gate check..." -ForegroundColor Cyan
ssh $SERVER "cd $REMOTE_PATH && bash scripts/gate_monitoring.sh"

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Cyan
Write-Host "1. Run gate monitoring daily for 7 days:" -ForegroundColor Gray
Write-Host "   ssh $SERVER 'cd $REMOTE_PATH && bash scripts/gate_monitoring.sh'" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Review logs daily:" -ForegroundColor Gray
Write-Host "   ssh $SERVER 'cat /home/Bilirubin/.hermes/logs/gate_monitoring_*.log'" -ForegroundColor Gray
Write-Host ""
Write-Host "3. After 7 days, create gate report" -ForegroundColor Gray
Write-Host ""
Write-Host "See: hermes/PHASE1_GATE_GUIDE.md for details" -ForegroundColor Gray
