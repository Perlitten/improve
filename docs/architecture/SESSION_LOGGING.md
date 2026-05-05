# Session Logging System

## Обзор

Система логирования сессий Hermes в Postgres для структурированного хранения и поиска истории работы агента.

## Компоненты

### 1. База данных

**Таблица `automation.sessions`:**
- `session_id` — уникальный ID сессии
- `started_at`, `ended_at` — временные метки
- `platform` — telegram, discord, cli, etc.
- `user_id`, `user_name` — информация о пользователе
- `chat_id`, `thread_id` — контекст чата
- `model`, `provider` — используемая модель
- `total_turns`, `total_tool_calls` — счётчики активности
- `status` — active, completed, interrupted, error
- `summary` — краткое описание сессии
- `tags` — метки для поиска
- `metadata` — дополнительные данные (JSONB)

**Таблица `automation.session_events`:**
- `session_id` — ссылка на сессию
- `event_type` — user_message, assistant_message, tool_call, error, context_compaction
- `timestamp` — время события
- `role` — user, assistant, tool
- `content` — текст сообщения
- `tool_name`, `tool_args`, `tool_result` — данные вызова инструмента
- `metadata` — дополнительные данные (JSONB)

### 2. CLI инструмент: `/srv/automation/session_logger.py`

**Команды:**

```bash
# Начать сессию
python3 session_logger.py start \
  --session-id "session-123" \
  --platform telegram \
  --user-id "322158958" \
  --user-name "Andrei Yahontov" \
  --model "claude-sonnet-4.5" \
  --provider "anthropic"

# Записать событие
python3 session_logger.py event \
  --session-id "session-123" \
  --event-type "user_message" \
  --role "user" \
  --content "Текст сообщения"

# Записать вызов инструмента
python3 session_logger.py event \
  --session-id "session-123" \
  --event-type "tool_call" \
  --tool-name "mcp_control_plane_infra_readiness" \
  --tool-args '{"param": "value"}' \
  --tool-result '{"ok": true}'

# Завершить сессию
python3 session_logger.py end \
  --session-id "session-123" \
  --status "completed" \
  --summary "Краткое описание что делали" \
  --tags "tag1" "tag2"

# Получить сводку
python3 session_logger.py summary --session-id "session-123"
```

### 3. MCP Tools (brain-mcp)

**`mcp_control_plane_session_list`**
```python
session_list(limit=20, status=None, platform=None)
# Возвращает список последних сессий с метаданными
```

**`mcp_control_plane_session_detail`**
```python
session_detail(session_id, include_events=False, event_limit=100)
# Детальная информация о сессии, опционально с событиями
```

**`mcp_control_plane_session_search`**
```python
session_search(query, limit=10)
# Поиск по summary, tags, user_name
```

## Интеграция с Hermes Gateway

Для автоматического логирования всех сессий нужно добавить хуки в hermes-gateway:

1. **При старте сессии** — вызвать `session_logger.py start`
2. **При каждом сообщении** — вызвать `session_logger.py event`
3. **При завершении** — вызвать `session_logger.py end`

## Примеры использования

### Найти все сессии пользователя
```python
from brain_mcp_server import session_list
result = session_list(platform="telegram")
```

### Найти сессии по теме
```python
from brain_mcp_server import session_search
result = session_search(query="postgres")
```

### Получить детали с событиями
```python
from brain_mcp_server import session_detail
result = session_detail("session-123", include_events=True)
```

## Преимущества

1. **Структурированный поиск** — быстрый поиск по тегам, пользователям, темам
2. **Аналитика** — статистика по использованию инструментов, моделей, времени работы
3. **Отладка** — детальная история событий для воспроизведения проблем
4. **Дополнение к session_search** — session_search ищет по транскриптам, session_* работает с метаданными

## TODO

- [ ] Автоматическая интеграция с hermes-gateway
- [ ] Генерация summary через LLM при завершении сессии
- [ ] Автоматическое тегирование на основе содержимого
- [ ] Dashboard для визуализации статистики
- [ ] Экспорт сессий в markdown/JSON
