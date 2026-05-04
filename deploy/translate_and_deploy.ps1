#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Translate Russian text to English and deploy to server
.DESCRIPTION
    This script translates remaining Russian text in Hermes files and deploys everything
#>

param(
    [switch]$SkipTranslation,
    [switch]$DeployOnly
)

$ErrorActionPreference = "Stop"

Write-Host "🌐 Translation and Deployment Script" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host ""

# Translation mappings for common Russian phrases
$translations = @{
    "Дата:" = "Date:"
    "Статус:" = "Status:"
    "Приоритет:" = "Priority:"
    "Проблема:" = "Problem:"
    "Цель" = "Goal"
    "Задача для Hermes" = "Task for Hermes"
    "Зависимости:" = "Dependencies:"
    "Создать файл:" = "Create file:"
    "Файл" = "File"
    "Правило" = "Rule"
    "Требования" = "Requirements"
    "Ожидаемый результат" = "Expected Result"
    "Проверка после патча" = "Verification After Patch"
    "Команды для проверки" = "Verification Commands"
    "Ожидаемые результаты" = "Expected Results"
    "Что НЕ делать после патча" = "What NOT to Do After Patch"
    "Что делать после патча" = "What to Do After Patch"
    "Если патч не помог" = "If Patch Didn't Help"
    "Когда запускать" = "When to Start"
    "Что отправить Hermes" = "What to Send to Hermes"
    "Проверка Phase" = "Phase Verification"
    "Когда применять" = "When to Apply"
    "Что должен сделать Hermes" = "What Hermes Should Do"
    "Финальная цель" = "Final Goal"
    "Созданные файлы" = "Created Files"
    "Где читать" = "Where to Read"
    "Быстрый старт:" = "Quick Start:"
    "Главный файл:" = "Main File:"
    "Детали:" = "Details:"
    "Во время ожидания rate limit" = "While Waiting for Rate Limit"
    "После Emergency Patch" = "After Emergency Patch"
    "После Phase" = "After Phase"
    "Если что-то пошло не так" = "If Something Went Wrong"
    "не помог" = "didn't help"
    "тесты не прошли" = "tests failed"
    "не работает" = "doesn't work"
    "Проверить логи" = "Check logs"
    "Откатить изменения" = "Rollback changes"
    "Проверить БД" = "Check database"
    "Откатить если нужно" = "Rollback if needed"
    "Документация" = "Documentation"
    "emergency patch инструкции" = "emergency patch instructions"
    "полная спецификация" = "full specification"
    "этот чеклист" = "this checklist"
    "Нет HTTP 400 loop" = "No HTTP 400 loop"
    "hermes-gateway stable" = "hermes-gateway stable"
    "Task paused correctly" = "Task paused correctly"
    "не failed" = "not failed"
    "All acceptance tests passed" = "All acceptance tests passed"
    "Router выбирает compatible models" = "Router selects compatible models"
    "Single tool mode enforced" = "Single tool mode enforced"
    "Нет HTTP 400 в логах" = "No HTTP 400 in logs"
    "Нет manual /resume required" = "No manual /resume required"
    "Messages не прерывают tasks" = "Messages don't interrupt tasks"
    "MCP auto-reconnect работает" = "MCP auto-reconnect works"
    "Runtime health monitoring работает" = "Runtime health monitoring works"
    "Не падает на rate limit" = "Doesn't crash on rate limit"
    "Не требует manual /resume" = "Doesn't require manual /resume"
    "Не прерывается новыми сообщениями" = "Doesn't get interrupted by new messages"
    "Восстанавливается сам после restart" = "Recovers itself after restart"
    "Имеет persistent queue и checkpoints" = "Has persistent queue and checkpoints"
    "это после observability" = "that comes after observability"
    "ГОТОВО К ВЫПОЛНЕНИЮ" = "READY TO EXECUTE"
    "Начинай с Шага 1:" = "Start with Step 1:"
    "Ждём сброс rate limit" = "Wait for rate limit reset"
}

if (-not $SkipTranslation -and -not $DeployOnly) {
    Write-Host "1️⃣  Translating files..." -ForegroundColor Yellow
    
    $filesToTranslate = @(
        "HERMES_RECOVERY_CHECKLIST.md",
        "HERMES_EMERGENCY_PATCH.md",
        "HERMES_PHASE_9_9_PROVIDER_ROUTER.md",
        "HERMES_PHASE_10_0_RELIABLE_RUNTIME.md"
    )
    
    foreach ($file in $filesToTranslate) {
        if (Test-Path $file) {
            Write-Host "   Translating $file..." -ForegroundColor White
            $content = Get-Content $file -Raw -Encoding UTF8
            
            foreach ($key in $translations.Keys) {
                $content = $content -replace [regex]::Escape($key), $translations[$key]
            }
            
            $content | Out-File -FilePath $file -Encoding UTF8 -NoNewline
            Write-Host "   ✅ Done" -ForegroundColor Green
        }
    }
    
    Write-Host ""
}

# Now deploy
Write-Host "2️⃣  Deploying to server..." -ForegroundColor Yellow
Write-Host ""

if (Test-Path ".\deploy_to_server.ps1") {
    Write-Host "   Running deployment script..." -ForegroundColor White
    & ".\deploy_to_server.ps1" -Message "Translate to English and deploy Hermes recovery plan"
} else {
    Write-Host "   ⚠️  deploy_to_server.ps1 not found" -ForegroundColor Yellow
    Write-Host "   Run setup_deploy.ps1 first" -ForegroundColor White
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host "✅ Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Check server: .\quick_fix.ps1 -ShowLogs" -ForegroundColor White
Write-Host "  2. Read checklist: Get-Content HERMES_RECOVERY_CHECKLIST.md" -ForegroundColor White
Write-Host "  3. Wait for rate limit reset (30-60 min)" -ForegroundColor White
Write-Host "  4. Send emergency patch to Hermes" -ForegroundColor White
