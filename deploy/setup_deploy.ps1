#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Initial setup for deployment system
.DESCRIPTION
    Interactive setup wizard for configuring deployment to server
#>

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                        ║" -ForegroundColor Cyan
Write-Host "║          🚀 Deployment Setup Wizard                   ║" -ForegroundColor Cyan
Write-Host "║                                                        ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check if already configured
if (Test-Path ".deploy-config") {
    Write-Host "⚠️  Configuration already exists!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Overwrite existing config? (y/N)" -ForegroundColor Yellow -NoNewline
    Write-Host " " -NoNewline
    $overwrite = Read-Host
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-Host "Cancelled." -ForegroundColor DarkGray
        exit 0
    }
}

# Step 1: Server host
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "Step 1: Server Connection" -ForegroundColor Cyan
Write-Host ""
Write-Host "Enter SSH connection string (example: user@server.com or user@192.168.1.100)" -ForegroundColor White
$serverHost = Read-Host "Server host"

if (-not $serverHost) {
    Write-Host "❌ Server host is required!" -ForegroundColor Red
    exit 1
}

# Step 2: Test connection
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "Step 2: Testing Connection" -ForegroundColor Cyan
Write-Host ""
Write-Host "Testing SSH connection to $serverHost..." -ForegroundColor Yellow

try {
    $testResult = ssh -o ConnectTimeout=10 $serverHost "echo 'OK'" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Connection successful!" -ForegroundColor Green
    } else {
        Write-Host "❌ Connection failed!" -ForegroundColor Red
        Write-Host "Error: $testResult" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "Please check:" -ForegroundColor Yellow
        Write-Host "  • SSH is installed: ssh -V" -ForegroundColor White
        Write-Host "  • Server is reachable: ping server.com" -ForegroundColor White
        Write-Host "  • SSH key is configured: ssh-keygen -t ed25519" -ForegroundColor White
        exit 1
    }
} catch {
    Write-Host "❌ Connection test failed: $_" -ForegroundColor Red
    exit 1
}

# Step 3: Server path
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "Step 3: Workspace Path" -ForegroundColor Cyan
Write-Host ""
Write-Host "Enter workspace path on server (default: /home/Bilirubin/workspace)" -ForegroundColor White
$serverPath = Read-Host "Workspace path"
if (-not $serverPath) {
    $serverPath = "/home/Bilirubin/workspace"
}

# Verify path exists
Write-Host "Checking if path exists..." -ForegroundColor Yellow
$pathCheck = ssh $serverHost "if (Test-Path '$serverPath') { 'EXISTS' } else { 'MISSING' }"
if ($pathCheck -eq "EXISTS") {
    Write-Host "✅ Path exists: $serverPath" -ForegroundColor Green
} else {
    Write-Host "⚠️  Path not found: $serverPath" -ForegroundColor Yellow
    $create = Read-Host "Create this directory? (y/N)"
    if ($create -eq "y" -or $create -eq "Y") {
        ssh $serverHost "mkdir -p $serverPath"
        Write-Host "✅ Directory created" -ForegroundColor Green
    }
}

# Step 4: Extract username
$serverUser = $serverHost.Split("@")[0]

# Step 5: Save config
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "Step 4: Saving Configuration" -ForegroundColor Cyan
Write-Host ""

$config = @{
    server_host = $serverHost
    server_path = $serverPath
    server_user = $serverUser
} | ConvertTo-Json

$config | Out-File -FilePath ".deploy-config" -Encoding UTF8
Write-Host "✅ Configuration saved to .deploy-config" -ForegroundColor Green

# Step 6: Update .gitignore
if (Test-Path ".gitignore") {
    $gitignoreContent = Get-Content ".gitignore" -Raw
    if ($gitignoreContent -notmatch "\.deploy-config") {
        Add-Content ".gitignore" "`n# Deployment config`n.deploy-config"
        Write-Host "✅ Added .deploy-config to .gitignore" -ForegroundColor Green
    }
} else {
    ".deploy-config" | Out-File -FilePath ".gitignore" -Encoding UTF8
    Write-Host "✅ Created .gitignore with .deploy-config" -ForegroundColor Green
}

# Step 7: Test deployment system
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "Step 5: Testing Deployment System" -ForegroundColor Cyan
Write-Host ""

Write-Host "Running connection test..." -ForegroundColor Yellow
& "$PSScriptRoot\test_connection.ps1"

# Summary
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "✨ Setup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  Server: $serverHost" -ForegroundColor White
Write-Host "  Path:   $serverPath" -ForegroundColor White
Write-Host "  User:   $serverUser" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Read the guide:    Get-Content DEPLOY_CHEATSHEET.md" -ForegroundColor White
Write-Host "  2. Test deployment:   .\deploy_to_server.ps1 -DryRun" -ForegroundColor White
Write-Host "  3. Deploy changes:    .\deploy_to_server.ps1" -ForegroundColor White
Write-Host "  4. Quick commands:    .\quick_fix.ps1 -ShowLogs" -ForegroundColor White
Write-Host ""
Write-Host "📚 Full documentation: DEPLOY_README.md" -ForegroundColor DarkGray
Write-Host ""
