# 🚀 Deployment System Summary

## Что было создано

Полная система для деплоя фиксов с Windows на Linux сервер.

### 📁 Файлы

| Файл | Назначение |
|------|-----------|
| `setup_deploy.ps1` | **Интерактивный мастер настройки** (запусти первым!) |
| `test_connection.ps1` | Проверка подключения к серверу |
| `deploy_to_server.ps1` | Деплой через Git (commit → push → pull) |
| `sync_to_server.ps1` | Прямая синхронизация файлов через SCP |
| `quick_fix.ps1` | Быстрое выполнение команд на сервере |
| `setup_webhook_deploy.sh` | Настройка автоматического деплоя (для сервера) |
| `.deploy-config.example` | Пример конфигурации |
| `.gitignore` | Игнорирование credentials |
| `DEPLOY_README.md` | Полная документация |
| `DEPLOY_CHEATSHEET.md` | Быстрая шпаргалка |

## 🎯 Быстрый старт

### 1. Первоначальная настройка (один раз)

```powershell
# Запусти интерактивный мастер
.\setup_deploy.ps1
```

Мастер:
- ✅ Спросит SSH адрес сервера
- ✅ Проверит подключение
- ✅ Создаст `.deploy-config`
- ✅ Добавит в `.gitignore`
- ✅ Протестирует систему

### 2. Ежедневное использование

```powershell
# Деплой изменений
.\deploy_to_server.ps1 -Message "Fix bug in health loop"

# Или быстрая синхронизация
.\sync_to_server.ps1

# Проверка логов
.\quick_fix.ps1 -ShowLogs

# Перезапуск сервиса
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"
```

## 🔧 Способы деплоя

### Способ 1: Git Push + Pull (Рекомендуется)
```powershell
.\deploy_to_server.ps1
```
**Плюсы:** Версионность, история, откат  
**Когда использовать:** Для всех изменений кода

### Способ 2: Прямая синхронизация
```powershell
.\sync_to_server.ps1
```
**Плюсы:** Быстро, без коммитов  
**Когда использовать:** Для тестирования, временных фиксов

### Способ 3: Быстрая команда
```powershell
.\quick_fix.ps1 -Command "команда"
```
**Плюсы:** Мгновенно  
**Когда использовать:** Перезапуск сервисов, просмотр логов

### Способ 4: Автоматический webhook
```bash
# На сервере (один раз)
./setup_webhook_deploy.sh
```
**Плюсы:** Полностью автоматический  
**Когда использовать:** Для продакшена

## 📊 Типичные сценарии

### Сценарий 1: Фикс бага в Python скрипте
```powershell
# 1. Редактируешь файл
notepad health_optimization_loop.py

# 2. Деплоишь
.\deploy_to_server.ps1 -Message "Fix error handling"

# 3. Перезапускаешь
.\quick_fix.ps1 -Command "sudo systemctl restart infra-health-loop.timer"

# 4. Проверяешь
.\quick_fix.ps1 -Command "sudo journalctl -u infra-health-loop -n 20"
```

### Сценарий 2: Обновление systemd сервиса
```powershell
# 1. Редактируешь
notepad brain-mcp.service

# 2. Синхронизируешь
.\sync_to_server.ps1 -Files "brain-mcp.service"

# 3. Применяешь
.\quick_fix.ps1 -Command @"
sudo cp /home/Bilirubin/workspace/brain-mcp.service /etc/systemd/system/ && \
sudo systemctl daemon-reload && \
sudo systemctl restart brain-mcp
"@
```

### Сценарий 3: Диагностика проблемы
```powershell
# Полная диагностика
.\quick_fix.ps1 -ShowLogs

# Конкретный сервис
.\quick_fix.ps1 -Command "sudo journalctl -u brain-mcp -n 100"

# Проверка здоровья
.\quick_fix.ps1 -Command "/home/Bilirubin/workspace/host_checklist.sh"
```

### Сценарий 4: Откат изменений
```powershell
# Откат на предыдущий коммит
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git reset --hard HEAD~1"

# Перезапуск сервисов
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp hermes-gateway"
```

## 🛡️ Безопасность

✅ **Всегда используй DryRun перед реальным деплоем:**
```powershell
.\deploy_to_server.ps1 -DryRun
```

✅ **Проверяй изменения:**
```powershell
git status
git diff
```

✅ **Делай бэкапы:**
```powershell
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git branch backup-$(date +%Y%m%d)"
```

## 📚 Документация

- **Быстрая шпаргалка:** `DEPLOY_CHEATSHEET.md`
- **Полная документация:** `DEPLOY_README.md`
- **Проверка подключения:** `.\test_connection.ps1`

## 🆘 Помощь

### Проблемы с SSH
```powershell
# Проверка SSH
ssh -v user@server

# Генерация ключа
ssh-keygen -t ed25519

# Копирование ключа
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh user@server "cat >> ~/.ssh/authorized_keys"
```

### Проблемы с Git
```powershell
# Проверка remote
git remote -v

# Проверка авторизации
git config --global user.name
git config --global user.email
```

### Проблемы с сервисами
```powershell
# Статус всех сервисов
.\quick_fix.ps1 -Command "systemctl status brain-mcp hermes-gateway n8n --no-pager"

# Логи с ошибками
.\quick_fix.ps1 -Command "sudo journalctl -p err -n 50"
```

## 🎉 Готово!

Теперь у тебя есть полная система для деплоя фиксов на сервер.

**Начни с:**
```powershell
.\setup_deploy.ps1
```

**Затем используй:**
```powershell
.\deploy_to_server.ps1  # Для деплоя
.\quick_fix.ps1 -ShowLogs  # Для диагностики
```

**Читай:**
```powershell
Get-Content DEPLOY_CHEATSHEET.md  # Шпаргалка
Get-Content DEPLOY_README.md  # Полная документация
```
