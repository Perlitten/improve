# 🤖 Hermes Infrastructure Workspace

Автономная инфраструктура для AI-агентов с долговременной памятью, автоматическим мониторингом и самовосстановлением.

## 🏗️ Архитектура

### Основные компоненты

- **Hermes** — агентская платформа (gateway + dashboard)
- **n8n** — workflow automation
- **PostgreSQL** — долговременная память (БД `rag`)
- **Brain MCP** — control plane для агентов (порт 8791)
- **Knowledge Optimizer** — система для работы с Obsidian vault
- **Мониторинг** — автоматические health checks и оптимизация

### Сервисы

| Сервис | Порт | Назначение |
|--------|------|-----------|
| `hermes-gateway` | 8642 | API для агентов |
| `hermes-dashboard` | 9119 | Web UI |
| `n8n` | 5678 | Workflow automation |
| `automation-gateway` | 8788 | Orchestration webhooks |
| `brain-mcp` | 8791 | MCP control plane |
| `nginx` | 80/443 | Reverse proxy |

## 🚀 Deployment

### Быстрый старт

```powershell
# 1. Настройка деплоя (один раз)
.\setup_deploy.ps1

# 2. Деплой изменений
.\deploy_to_server.ps1

# 3. Проверка состояния
.\quick_fix.ps1 -ShowLogs
```

### Документация по деплою

- **📋 Быстрая шпаргалка:** [DEPLOY_CHEATSHEET.md](DEPLOY_CHEATSHEET.md)
- **📚 Полная документация:** [DEPLOY_README.md](DEPLOY_README.md)
- **📝 Обзор системы:** [DEPLOY_SUMMARY.md](DEPLOY_SUMMARY.md)

## 🔧 Основные скрипты

### Деплой и синхронизация

```powershell
# Интерактивная настройка
.\setup_deploy.ps1

# Проверка подключения
.\test_connection.ps1

# Деплой через Git
.\deploy_to_server.ps1 -Message "Fix bug"

# Прямая синхронизация файлов
.\sync_to_server.ps1

# Быстрая команда на сервере
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"

# Просмотр логов
.\quick_fix.ps1 -ShowLogs
```

### Диагностика на сервере

```bash
# Проверка состояния хоста
/home/Bilirubin/workspace/host_checklist.sh

# Проверка базы данных
/home/Bilirubin/workspace/db_checklist.sh

# Проверка готовности агента
/home/Bilirubin/workspace/agent_readiness_check.sh
```

## 📊 Мониторинг

### Автоматические проверки

- **Health Loop** — каждый час проверяет состояние сервисов
- **Infra Snapshot** — каждый час сохраняет снимок инфраструктуры
- **Self Monitor** — следит за здоровьем системы
- **Auto Remediation** — автоматически перезапускает упавшие сервисы

### Systemd сервисы

```bash
# Статус сервисов
systemctl status brain-mcp hermes-gateway n8n

# Логи
journalctl -u brain-mcp -n 50
journalctl -u infra-health-loop -f

# Перезапуск
sudo systemctl restart brain-mcp
sudo systemctl daemon-reload
```

## 🗄️ База данных

### Структура

- **База `rag`** — долговременная память
  - `workspaces` — рабочие пространства
  - `projects` — проекты
  - `artifacts` — артефакты
  - `artifact_versions` — версии артефактов
  - `rag_documents` — документы для поиска
  - `insights` — инсайты
  - `infra_snapshots` — снимки инфраструктуры

- **База `n8n`** — workflow runtime

### Коллекции RAG

- `host-state` — состояние хоста
- `host-insights` — инсайты о хосте
- `host-optimization` — рекомендации по оптимизации
- `obsidian-main` — основной контент Obsidian
- `obsidian-rules` — правила из Obsidian

## 🧠 Knowledge Optimizer

Система для работы с Obsidian vault:

```powershell
cd knowledge-optimizer

# Запуск web app
.\scripts\run_app.ps1

# Запуск MCP сервера
.\scripts\run_mcp.ps1

# Полный цикл обслуживания
.\scripts\run_full_cycle.ps1

# Установка автономного режима
.\scripts\install_autonomy_schedule.ps1 -MaintenanceAt 03:00
```

Подробнее: [knowledge-optimizer/README.md](knowledge-optimizer/README.md)

## 🔐 Безопасность

### Credentials

- **НЕ коммить** `.deploy-config` (содержит SSH credentials)
- **НЕ коммить** `.env` файлы
- **Использовать** SSH ключи вместо паролей
- **Проверять** изменения перед деплоем

### Best Practices

```powershell
# Всегда делай dry-run
.\deploy_to_server.ps1 -DryRun

# Проверяй изменения
git status
git diff

# Делай бэкапы
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git branch backup-$(date +%Y%m%d)"
```

## 📚 Документация

### Основная

- [MCP_CONTROL_PLANE.md](MCP_CONTROL_PLANE.md) — MCP control plane
- [POSTGRES_MEMORY.md](POSTGRES_MEMORY.md) — структура памяти
- [knowledge-optimizer/README.md](knowledge-optimizer/README.md) — Knowledge Optimizer

### Deployment

- [DEPLOY_SUMMARY.md](DEPLOY_SUMMARY.md) — обзор системы деплоя
- [DEPLOY_CHEATSHEET.md](DEPLOY_CHEATSHEET.md) — быстрая шпаргалка
- [DEPLOY_README.md](DEPLOY_README.md) — полная документация

### Skills

- [kilo-claude45.SKILL.md](kilo-claude45.SKILL.md) — навыки для Claude
- [postgres-memory.SKILL.md](postgres-memory.SKILL.md) — работа с памятью
- [server-ops.SKILL.md](server-ops.SKILL.md) — операции на сервере

## 🆘 Troubleshooting

### Сервисы не работают

```powershell
# Проверка состояния
.\quick_fix.ps1 -ShowLogs

# Перезапуск
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp hermes-gateway n8n"

# Логи
.\quick_fix.ps1 -Command "sudo journalctl -u brain-mcp -n 100"
```

### База данных недоступна

```powershell
# Проверка PostgreSQL
.\quick_fix.ps1 -Command "sudo docker ps | grep postgres"
.\quick_fix.ps1 -Command "sudo docker logs automation-postgres --tail 50"

# Перезапуск
.\quick_fix.ps1 -Command "sudo docker restart automation-postgres"
```

### Проблемы с деплоем

```powershell
# Проверка подключения
.\test_connection.ps1

# Проверка Git
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git status"

# Откат изменений
.\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git reset --hard HEAD~1"
```

## 🎯 Быстрые команды

```powershell
# Деплой
.\deploy_to_server.ps1

# Диагностика
.\quick_fix.ps1 -ShowLogs

# Перезапуск сервиса
.\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"

# Проверка здоровья
.\quick_fix.ps1 -Command "/home/Bilirubin/workspace/host_checklist.sh"

# Проверка БД
.\quick_fix.ps1 -Command "/home/Bilirubin/workspace/db_checklist.sh"
```

## 📞 Контакты

- GitHub: [Perlitten/knowledge-optimizer](https://github.com/Perlitten/knowledge-optimizer)
- Документация: См. файлы `*.md` в корне проекта

## 📄 Лицензия

См. LICENSE файл в репозитории.
