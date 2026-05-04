# 👋 Начни здесь!

## Что я сделал для тебя

Я создал **полную систему для деплоя фиксов** с твоей Windows машины на Linux сервер.

## 🎯 Что теперь делать?

### Шаг 1: Настройка (5 минут)

```powershell
# Запусти интерактивный мастер
.\setup_deploy.ps1
```

Мастер спросит:
- SSH адрес сервера (например: `bilirubin@your-server.com`)
- Путь к workspace (по умолчанию: `/home/Bilirubin/workspace`)

Он автоматически:
- ✅ Проверит подключение
- ✅ Создаст конфиг `.deploy-config`
- ✅ Добавит в `.gitignore`
- ✅ Протестирует систему

### Шаг 2: Первый деплой

```powershell
# Проверь что будет сделано (безопасно)
.\deploy_to_server.ps1 -DryRun

# Реальный деплой
.\deploy_to_server.ps1 -Message "Initial setup"
```

### Шаг 3: Проверка

```powershell
# Посмотри логи и состояние сервера
.\quick_fix.ps1 -ShowLogs
```

## 📚 Что читать дальше?

### Для быстрого старта
👉 **[DEPLOY_CHEATSHEET.md](DEPLOY_CHEATSHEET.md)** — шпаргалка с основными командами

### Для понимания системы
👉 **[DEPLOY_SUMMARY.md](DEPLOY_SUMMARY.md)** — обзор всех возможностей

### Для глубокого изучения
👉 **[DEPLOY_README.md](DEPLOY_README.md)** — полная документация

### Для понимания проекта
👉 **[README.md](README.md)** — описание всей инфраструктуры

## 🚀 Основные команды

```powershell
# Деплой изменений
.\deploy_to_server.ps1

# Быстрая синхронизация
.\sync_to_server.ps1

# Просмотр логов
.\quick_fix.ps1 -ShowLogs

# Перезапуск сервиса
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"

# Проверка подключения
.\test_connection.ps1
```

## 🎁 Что я создал

### Скрипты для деплоя
- ✅ `setup_deploy.ps1` — интерактивная настройка
- ✅ `deploy_to_server.ps1` — деплой через Git
- ✅ `sync_to_server.ps1` — прямая синхронизация файлов
- ✅ `quick_fix.ps1` — быстрые команды на сервере
- ✅ `test_connection.ps1` — проверка подключения

### Документация
- ✅ `DEPLOY_CHEATSHEET.md` — быстрая шпаргалка
- ✅ `DEPLOY_SUMMARY.md` — обзор системы
- ✅ `DEPLOY_README.md` — полная документация
- ✅ `README.md` — описание проекта
- ✅ `START_HERE.md` — этот файл

### Конфигурация
- ✅ `.deploy-config.example` — пример конфига
- ✅ `.gitignore` — игнорирование credentials
- ✅ `setup_webhook_deploy.sh` — автоматический деплой (для сервера)

## 💡 Типичные сценарии

### Фикс бага
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

### Диагностика проблемы
```powershell
# Полная диагностика
.\quick_fix.ps1 -ShowLogs

# Конкретный сервис
.\quick_fix.ps1 -Command "sudo journalctl -u brain-mcp -n 100"

# Проверка здоровья
.\quick_fix.ps1 -Command "/home/Bilirubin/workspace/host_checklist.sh"
```

### Откат изменений
```powershell
# Откат на предыдущий коммит
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git reset --hard HEAD~1"
```

## 🛡️ Безопасность

✅ **Всегда используй DryRun** перед реальным деплоем:
```powershell
.\deploy_to_server.ps1 -DryRun
```

✅ **Проверяй изменения** перед коммитом:
```powershell
git status
git diff
```

✅ **Делай бэкапы** перед большими изменениями:
```powershell
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git branch backup-$(date +%Y%m%d)"
```

## 🆘 Нужна помощь?

### SSH не подключается
```powershell
# Проверка SSH
ssh -v user@server

# Генерация ключа
ssh-keygen -t ed25519

# Копирование ключа на сервер
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh user@server "cat >> ~/.ssh/authorized_keys"
```

### Git не работает
```powershell
# Проверка remote
git remote -v

# Проверка авторизации
git config --global user.name
git config --global user.email
```

### Сервис не стартует
```powershell
# Логи
.\quick_fix.ps1 -Command "sudo journalctl -u service-name -n 100"

# Статус
.\quick_fix.ps1 -Command "systemctl status service-name --no-pager"
```

## 🎉 Готово!

Теперь у тебя есть всё для работы с сервером.

**Начни прямо сейчас:**
```powershell
.\setup_deploy.ps1
```

**Вопросы?** Читай документацию:
- [DEPLOY_CHEATSHEET.md](DEPLOY_CHEATSHEET.md) — шпаргалка
- [DEPLOY_README.md](DEPLOY_README.md) — полная документация
- [README.md](README.md) — описание проекта

---

**P.S.** Все скрипты безопасны и имеют DryRun режим. Не бойся экспериментировать! 🚀
