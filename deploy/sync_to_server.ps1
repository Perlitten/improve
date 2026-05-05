#!/usr/bin/env pwsh
param(
    [string[]]$Files = @(),
    [string]$ServerHost = "",
    [string]$ServerPath = "/home/Bilirubin/workspace",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

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

# Auto-detect changed files if not specified
if ($Files.Count -eq 0) {
    $gitStatus = git status --porcelain
    if ($gitStatus) {
        $Files = $gitStatus | ForEach-Object {
            $f = $_.Substring(3).Trim()
            if ($f -match '\.(exe|zip|msi|7z)$') {
                Write-Host "SKIP: Binary file $f" -ForegroundColor Gray
                return
            }
            $f
        } | Where-Object { $_ }
    } else {
        Write-Host "OK: No changes detected" -ForegroundColor Green
        exit 0
    }
}

Write-Host "Syncing files to $ServerHost..." -ForegroundColor Cyan

# Identity file check
$keyPath = Join-Path $env:USERPROFILE ".ssh\google_compute_engine"
$sshCmd = if (Test-Path $keyPath) { "ssh -i '$keyPath'" } else { "ssh" }
$scpCmd = if (Test-Path $keyPath) { "scp -i '$keyPath'" } else { "scp" }

foreach ($file in $Files) {
    if (-not (Test-Path $file)) {
        Write-Host "SKIP: $file" -ForegroundColor Yellow
        continue
    }

    $remoteFile = $file -replace '\\', '/'
    $remotePath = "$ServerHost`:$ServerPath/$remoteFile"
    
    Write-Host "SEND: $file" -ForegroundColor White
    
    if ($DryRun) {
        Write-Host "   [DRY RUN]"
    } else {
        # Create remote directory
        $dir = Split-Path $remoteFile -Parent
        if ($dir) {
            $remoteDir = "$ServerPath/$($dir -replace '\\', '/')"
            Invoke-Expression "$sshCmd $ServerHost 'mkdir -p ""$remoteDir""'"
        }
        
        # Copy
        if (Test-Path $file -PathType Container) {
            Invoke-Expression "$scpCmd -r $file ""$remotePath"""
        } else {
            Invoke-Expression "$scpCmd $file ""$remotePath"""
        }
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   OK" -ForegroundColor Green
        } else {
            Write-Host "   FAILED" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "DONE: Sync complete!" -ForegroundColor Green
