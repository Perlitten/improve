# Apply database schema to remote server
# Phase 1, Day 2: Task Queue Schema
# Usage: .\apply_schema.ps1 [-DryRun]

param(
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

# Configuration
$SERVER = "Bilirubin@192.168.1.100"
$REMOTE_PATH = "/home/Bilirubin/workspace/hermes"
$SQL_FILE = "sql/001_create_task_queue.sql"

Write-Host "=== Hermes Schema Deployment ===" -ForegroundColor Cyan
Write-Host ""

# Check if SQL file exists locally
$localSqlPath = Join-Path $PSScriptRoot "..\$SQL_FILE"
if (-not (Test-Path $localSqlPath)) {
    Write-Host "❌ Error: SQL file not found: $localSqlPath" -ForegroundColor Red
    exit 1
}

Write-Host "📄 SQL File: $SQL_FILE" -ForegroundColor Green
Write-Host "🖥️  Server: $SERVER" -ForegroundColor Green
Write-Host ""

if ($DryRun) {
    Write-Host "🔍 DRY RUN MODE - No changes will be made" -ForegroundColor Yellow
    Write-Host ""
    
    # Show what would be done
    Write-Host "Would execute:" -ForegroundColor Yellow
    Write-Host "1. Copy $SQL_FILE to server" -ForegroundColor Gray
    Write-Host "2. Run: bash scripts/apply_schema.sh" -ForegroundColor Gray
    Write-Host ""
    
    # Show SQL content
    Write-Host "SQL Content:" -ForegroundColor Yellow
    Get-Content $localSqlPath | Select-Object -First 20
    Write-Host "..." -ForegroundColor Gray
    
    exit 0
}

# Confirm
Write-Host "⚠️  This will apply database schema changes to production" -ForegroundColor Yellow
$confirm = Read-Host "Continue? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "❌ Aborted" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "📤 Copying SQL file to server..." -ForegroundColor Cyan

# Copy SQL file
scp $localSqlPath "${SERVER}:${REMOTE_PATH}/$SQL_FILE"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to copy SQL file" -ForegroundColor Red
    exit 1
}

Write-Host "✅ SQL file copied" -ForegroundColor Green
Write-Host ""

Write-Host "🔧 Applying schema..." -ForegroundColor Cyan

# Apply schema
ssh $SERVER "cd $REMOTE_PATH && bash scripts/apply_schema.sh"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to apply schema" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ Schema applied successfully!" -ForegroundColor Green
Write-Host ""

# Verify
Write-Host "🔍 Verifying tables..." -ForegroundColor Cyan
ssh $SERVER "cd $REMOTE_PATH && source ~/.hermes/automation.env && PGPASSWORD=\$POSTGRES_PASSWORD psql -h 127.0.0.1 -U \$POSTGRES_USER -d rag -c '\dt agent_*'"

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Deploy task_orchestrator.py: .\deploy_to_server.ps1" -ForegroundColor Gray
Write-Host "2. Update hermes-gateway to use task queue" -ForegroundColor Gray
Write-Host "3. Run tests: ssh $SERVER 'cd $REMOTE_PATH && pytest tests/unit/test_task_orchestrator.py -v'" -ForegroundColor Gray
