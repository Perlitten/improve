#!/usr/bin/env pwsh
param(
    [string[]]$Files = @(),
    [string]$ServerHost = "",
    [string]$ServerPath = "/home/Bilirubin/workspace",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Repo root is one level up from script
$repoRoot = (Get-Item $PSScriptRoot).Parent.FullName
Push-Location $repoRoot

# Load config
$configPath = Join-Path $repoRoot ".deploy-config"
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    if (-not $ServerHost) { $ServerHost = $config.server_host }
    if ($config.server_path) { $ServerPath = $config.server_path }
}

if (-not $ServerHost) {
    Write-Host "ERROR: Server host not configured!" -ForegroundColor Red
    Pop-Location
    exit 1
}

# Auto-detect changed/new files if not specified
if ($Files.Count -eq 0) {
    $gitStatus = git status --porcelain -uall
    if ($gitStatus) {
        $Files = $gitStatus | ForEach-Object {
            $status = $_.Substring(0, 2)
            $f = $_.Substring(3).Trim()
            
            # Remove quotes if present
            if ($f -match '^"(.*)"$') { $f = $matches[1] }
            
            # Skip deletions and large/irrelevant files
            if ($status -match "D") { return }
            if ($f -match '\.(exe|zip|msi|7z)$' -or $f -match '(\.venv|\.git|node_modules|__pycache__)') {
                return
            }
            $f
        } | Where-Object { $_ -and (Test-Path $_) }
    } else {
        Write-Host "OK: No changes detected" -ForegroundColor Green
        Pop-Location
        exit 0
    }
}

if ($Files.Count -eq 0) {
    Write-Host "OK: No files to sync" -ForegroundColor Green
    Pop-Location
    exit 0
}

Write-Host "Syncing $($Files.Count) files to $ServerHost (optimized via TAR)..." -ForegroundColor Cyan

# Identity file check
$keyPath = Join-Path $env:USERPROFILE ".ssh\google_compute_engine"
$sshArgs = if (Test-Path $keyPath) { "-i ""$keyPath""" } else { "" }

if ($DryRun) {
    foreach ($f in $Files) { Write-Host "   [DRY RUN] Would sync: $f" -ForegroundColor Gray }
    Pop-Location
    exit 0
}

# 1. Create bundle
Write-Host "   [1/3] Packing files... " -NoNewline
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$tarFile = "sync_bundle_$timestamp.tar.gz"

# We use a loop to avoid command line length limits or file list issues
# On Windows, tar can take multiple arguments directly
tar -czf $tarFile $Files
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAILED" -ForegroundColor Red
    Pop-Location
    exit 1
}
Write-Host "OK" -ForegroundColor Green

try {
    # 2. Transfer bundle
    Write-Host "   [2/3] Transferring bundle... " -NoNewline
    if ($sshArgs) {
        scp -i $keyPath $tarFile "$ServerHost`:$ServerPath/"
    } else {
        scp $tarFile "$ServerHost`:$ServerPath/"
    }
    Write-Host "OK" -ForegroundColor Green

    # 3. Extract on server
    Write-Host "   [3/3] Extracting on server... " -NoNewline
    $remoteCmd = "cd $ServerPath && tar -xzf $tarFile && rm $tarFile"
    if ($sshArgs) {
        ssh -i $keyPath $ServerHost $remoteCmd
    } else {
        ssh $ServerHost $remoteCmd
    }
    Write-Host "OK" -ForegroundColor Green

    Write-Host ""
    Write-Host "DONE: Sync complete!" -ForegroundColor Green
} finally {
    if (Test-Path $tarFile) { Remove-Item $tarFile }
    Pop-Location
}
