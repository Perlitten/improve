# 🚀 Deployment Guide

Инструкции по деплою фиксов на сервер с Windows машины.

## 🔧 Первоначальная настройка

### 1. Настройка SSH доступа

Убедись, что у тебя есть SSH доступ к серверу:

```powershell
# Проверка SSH подключения
ssh user@your-server.com "echo 'Connection OK'"
```

Если нужно настроить SSH ключ:

```powershell
# Генерация ключа (если нет)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Копирование ключа на сервер
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh user@your-server.com "cat >> ~/.ssh/authorized_keys"
```

### 2. Создание конфига деплоя

Скопируй пример конфига и заполни своими данными:

```powershell
Copy-Item .deploy-config.example .deploy-config
notepad .deploy-config
```

Пример `.deploy-config`:

```json
{
    "server_host": "bilirubin@your-server.com",
    "server_path": "/home/Bilirubin/workspace",
    "server_user": "Bilirubin"
}
```

**⚠️ Важно:** Добавь `.deploy-config` в `.gitignore`, чтобы не коммитить credentials!

```powershell
Add-Content .gitignore "`n.deploy-config"
```

## 📦 Способы деплоя

### Способ 1: Git Push + Pull (Рекомендуется)

**Плюсы:** Версионность, откат, история изменений  
**Минусы:** Требует коммита

```powershell
# Деплой всех изменений
.\deploy_to_server.ps1 -Message "Fix brain-mcp service"

# Dry-run (посмотреть что будет сделано)
.\deploy_to_server.ps1 -DryRun
```

**Как это работает:**
1. Коммитит локальные изменения
2. Пушит в GitHub
3. На сервере делает `git pull`

### Способ 2: Прямая синхронизация файлов (SCP)

**Плюсы:** Быстро, без коммитов  
**Минусы:** Нет версионности

```powershell
# Синхронизация изменённых файлов
.\sync_to_server.ps1

# Синхронизация конкретных файлов
.\sync_to_server.ps1 -Files "brain_mcp_server.py","health_optimization_loop.py"

# Dry-run
.\sync_to_server.ps1 -DryRun
```

### Способ 3: Быстрая команда

**Плюсы:** Мгновенное выполнение  
**Минусы:** Только для простых команд

```powershell
# Перезапуск сервиса
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"

# Просмотр логов
.\quick_fix.ps1 -ShowLogs

# Выполнение скрипта
.\quick_fix.ps1 -Script "fix_script.sh"
```

### Способ 4: Автоматический деплой через Webhook

**Плюсы:** Полностью автоматический  
**Минусы:** Требует настройки на сервере

**Настройка на сервере (один раз):**

```bash
# На сервере
cd /home/Bilirubin/workspace
chmod +x setup_webhook_deploy.sh
./setup_webhook_deploy.sh
```

**Настройка в GitHub:**

1. Открой настройки репозитория: `Settings` → `Webhooks` → `Add webhook`
2. Заполни:
   - **Payload URL:** `http://your-server:9876/hooks/workspace-deploy`
   - **Content type:** `application/json`
   - **Secret:** (тот же что в `WEBHOOK_SECRET`)
   - **Events:** Just the push event
3. Сохрани

Теперь каждый `git push` автоматически деплоится на сервер!

## 🔍 Диагностика проблем

### Проверка состояния сервера

```powershell
# Полная диагностика
.\quick_fix.ps1 -ShowLogs

# Или напрямую через SSH
ssh user@server "/home/Bilirubin/workspace/host_checklist.sh"
```

### Проверка конкретного сервиса

```powershell
.\quick_fix.ps1 -Command "sudo journalctl -u brain-mcp -n 50 --no-pager"
.\quick_fix.ps1 -Command "sudo systemctl status brain-mcp"
```

### Перезапуск сервисов

```powershell
# Один сервис
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"

# Несколько сервисов
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp hermes-gateway n8n"

# Перезагрузка конфигурации
.\quick_fix.ps1 -Command "sudo systemctl daemon-reload"
```

## 🛠️ Типичные сценарии

### Сценарий 1: Фикс Python скрипта

```powershell
# 1. Редактируешь файл локально
notepad health_optimization_loop.py

# 2. Деплоишь
.\deploy_to_server.ps1 -Message "Fix health loop error handling"

# 3. Перезапускаешь сервис
.\quick_fix.ps1 -Command "sudo systemctl restart infra-health-loop.timer"

# 4. Проверяешь логи
.\quick_fix.ps1 -Command "sudo journalctl -u infra-health-loop -n 20"
```

### Сценарий 2: Обновление systemd сервиса

```powershell
# 1. Редактируешь .service файл
notepad brain-mcp.service

# 2. Деплоишь
.\sync_to_server.ps1 -Files "brain-mcp.service"

# 3. Копируешь в systemd и перезапускаешь
.\quick_fix.ps1 -Command @"
sudo cp /home/Bilirubin/workspace/brain-mcp.service /etc/systemd/system/ && \
sudo systemctl daemon-reload && \
sudo systemctl restart brain-mcp
"@
```

### Сценарий 3: Экстренный откат

```powershell
# Откат на предыдущий коммит
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git reset --hard HEAD~1"

# Или на конкретный коммит
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git reset --hard abc123"
```

## 📊 Мониторинг после деплоя

```powershell
# Проверка что всё работает
.\quick_fix.ps1 -Command @"
echo '=== Services ===' && \
systemctl is-active brain-mcp hermes-gateway n8n && \
echo '' && \
echo '=== Health ===' && \
curl -s http://127.0.0.1:5678/healthz/readiness && \
curl -s http://127.0.0.1:8788/health
"@
```

## 🔐 Безопасность

- ✅ Всегда используй SSH ключи вместо паролей
- ✅ Не коммить `.deploy-config` в Git
- ✅ Используй `DryRun` перед реальным деплоем
- ✅ Делай бэкапы перед большими изменениями
- ⚠️ Webhook требует HTTPS в продакшене

## 🆘 Troubleshooting

### SSH не подключается

```powershell
# Проверка SSH конфига
ssh -v user@server

# Проверка ключей
ssh-add -l
```

### Git push не работает

```powershell
# Проверка remote
git remote -v

# Проверка авторизации GitHub
git config --global user.name
git config --global user.email
```

### Сервис не перезапускается

```powershell
# Проверка sudo прав
.\quick_fix.ps1 -Command "sudo -l"

# Проверка статуса
.\quick_fix.ps1 -Command "systemctl status brain-mcp --no-pager"
```

## 📚 Дополнительные ресурсы

- [SSH Key Setup](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)
- [Git Basics](https://git-scm.com/book/en/v2/Getting-Started-Git-Basics)
- [Systemd Services](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
