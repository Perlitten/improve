# 🚀 Deploy Cheatsheet

## Быстрый старт

```powershell
# 1. Настройка (один раз)
Copy-Item .deploy-config.example .deploy-config
notepad .deploy-config  # Заполни server_host

# 2. Проверка подключения
.\test_connection.ps1

# 3. Деплой
.\deploy_to_server.ps1
```

## Основные команды

| Задача | Команда |
|--------|---------|
| **Проверить подключение** | `.\test_connection.ps1` |
| **Деплой через Git** | `.\deploy_to_server.ps1` |
| **Быстрая синхронизация** | `.\sync_to_server.ps1` |
| **Посмотреть логи** | `.\quick_fix.ps1 -ShowLogs` |
| **Перезапустить сервис** | `.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"` |
| **Выполнить команду** | `.\quick_fix.ps1 -Command "команда"` |

## Типичные сценарии

### Фикс Python скрипта
```powershell
# Редактируешь файл → деплоишь → перезапускаешь
.\deploy_to_server.ps1 -Message "Fix bug in health_loop"
.\quick_fix.ps1 -Command "sudo systemctl restart infra-health-loop.timer"
```

### Обновление сервиса
```powershell
.\sync_to_server.ps1 -Files "brain-mcp.service"
.\quick_fix.ps1 -Command "sudo cp /home/Bilirubin/workspace/brain-mcp.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart brain-mcp"
```

### Диагностика проблемы
```powershell
.\quick_fix.ps1 -ShowLogs
.\quick_fix.ps1 -Command "sudo journalctl -u brain-mcp -n 50"
.\quick_fix.ps1 -Command "/home/Bilirubin/workspace/host_checklist.sh"
```

### Откат изменений
```powershell
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git reset --hard HEAD~1"
```

## Проверка здоровья сервера

```powershell
# Быстрая проверка
.\quick_fix.ps1 -Command "systemctl is-active brain-mcp hermes-gateway n8n"

# Полная диагностика
.\quick_fix.ps1 -Command "/home/Bilirubin/workspace/host_checklist.sh"

# Проверка БД
.\quick_fix.ps1 -Command "/home/Bilirubin/workspace/db_checklist.sh"
```

## Перезапуск сервисов

```powershell
# Один сервис
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"

# Все основные сервисы
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp hermes-gateway n8n"

# С перезагрузкой конфигов
.\quick_fix.ps1 -Command "sudo systemctl daemon-reload && sudo systemctl restart brain-mcp"
```

## Просмотр логов

```powershell
# Последние 50 строк
.\quick_fix.ps1 -Command "sudo journalctl -u brain-mcp -n 50"

# Следить в реальном времени
.\quick_fix.ps1 -Command "sudo journalctl -u brain-mcp -f"

# Только ошибки
.\quick_fix.ps1 -Command "sudo journalctl -u brain-mcp -p err -n 20"
```

## Работа с Git на сервере

```powershell
# Статус
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git status"

# Последние коммиты
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git log --oneline -5"

# Откат на коммит
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git reset --hard abc123"
```

## Безопасность

✅ **Всегда делай dry-run перед деплоем:**
```powershell
.\deploy_to_server.ps1 -DryRun
.\sync_to_server.ps1 -DryRun
```

✅ **Проверяй изменения перед коммитом:**
```powershell
git status
git diff
```

✅ **Делай бэкапы перед большими изменениями:**
```powershell
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git branch backup-$(date +%Y%m%d)"
```

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| SSH не подключается | `ssh -v user@server` для диагностики |
| Git push не работает | Проверь `git remote -v` и GitHub авторизацию |
| Сервис не стартует | `.\quick_fix.ps1 -Command "sudo journalctl -u service-name -n 100"` |
| Нет прав sudo | Настрой passwordless sudo на сервере |

## Полезные ссылки

- Полная документация: `Get-Content DEPLOY_README.md`
- Проверка подключения: `.\test_connection.ps1`
- Конфиг пример: `.deploy-config.example`
