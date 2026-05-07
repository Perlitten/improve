# Hermes vs Hermes Agent — отношение

## Кратко

- **`hermes-agent/`** (в корне репо) — это **upstream код** [Hermes Agent от Nous Research](https://github.com/NousResearch/hermes-agent), MIT. Сам агент. На сервере живёт в `/home/Bilirubin/.hermes/hermes-agent/`, запускается systemd-сервисом `hermes-gateway`.
- **`hermes/`** (этот каталог) — **твой operational layer вокруг агента**. На сервере деплоится в `/home/Bilirubin/workspace/hermes/` отдельным sync-ом ([deploy/sync_to_server.ps1](deploy/sync_to_server.ps1)).

Это **не дубли**. Это две роли: агент vs менеджер агента.

## Что лежит здесь (а не в hermes-agent)

| Компонент | Назначение |
|---|---|
| `src/brain_mcp_server.py` | MCP-сервер для долговременной памяти агента в PostgreSQL+pgvector |
| `src/canonical_memory.py`, `canonical_memory_bootstrap.py` | Схема и бутстрап canonical memory |
| `src/health_optimization_loop.py` | Self-healing loop (systemd timer каждые 15 мин) |
| `src/gdrive_backup.py` | Ежедневный бэкап в Google Drive |
| `src/model_router.py`, `strategy.py` | Multi-LLM роутер (OpenRouter + NVIDIA NIM fallback) |
| `src/obsidian_rag_import.py` | Импорт Obsidian-vault'а в RAG |
| `services/*.service`, `*.timer` | systemd-юниты для всех вспомогательных процессов |
| `services/prometheus.yml`, `n8n_self_heal_workflow.json` | Observability и оркестрация |
| `deploy/*.ps1` | Windows→GCP deploy-скрипты |

## Когда что трогать

- **Изменения в самом агенте** (CLI, gateway, ACP, skills runtime, MCP plumbing) → upstream issue или PR в [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent). Локальные правки в `hermes-agent/` снесёт следующее обновление.
- **Изменения в memory/cron/мониторинге/deploy** → этот каталог.
- **Скрипты, относящиеся к запуску `hermes-gateway`** (типа `safe_restart_gateway.sh`) → `hermes-agent/scripts/` (они часть лайфцикла upstream-сервиса).

## Если правишь upstream

Веди список локальных патчей в `UPSTREAM_PATCHES.md` (создай при необходимости): commit-hash + что меняется + как накатить заново после `git pull` upstream.
