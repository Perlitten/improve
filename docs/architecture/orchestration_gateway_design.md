# Orchestration Gateway — Детальный дизайн

**Дата:** 2026-05-03  
**Версия:** 1.0  
**Статус:** Design Phase

---

## 🎯 Цели

1. **Минимизация затрат** — использовать бесплатные модели для 80-90% запросов
2. **Высокая доступность** — автоматический fallback при ошибках провайдеров
3. **Умная маршрутизация** — выбор модели по типу задачи
4. **Прозрачность** — OpenAI-совместимый API, drop-in replacement

---

## ✅ Проверенные провайдеры

| Провайдер | Статус | Latency | Лимиты | Стоимость |
|-----------|--------|---------|--------|-----------|
| **OpenRouter :free** | ✅ OK | 1817ms | Rate limits | $0 |
| **NVIDIA NIM** | ✅ OK | 5139ms | Бесплатный tier | $0 |
| **Pollinations AI** | ✅ OK | 943ms | Без ключей | $0 |
| **LongCat** | ❌ Failed | - | - | - |

**Итого:** 3 рабочих бесплатных провайдера

---

## 🏗️ Архитектура

### Компоненты

```
┌─────────────────────────────────────────────────────────────┐
│                      Hermes Agent                           │
│                 (config.yaml: base_url)                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│          Orchestration Gateway (FastAPI)                    │
│                  http://127.0.0.1:8899                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  /v1/chat/completions (OpenAI-compatible)            │   │
│  │  /v1/models (список доступных моделей)               │   │
│  │  /health (health check)                              │   │
│  │  /metrics (Prometheus metrics)                       │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Request Classifier                                  │   │
│  │  - Анализ промпта (keywords, length, complexity)    │   │
│  │  - Определение tier (1/2/3)                         │   │
│  │  - Выбор модели из tier                             │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Provider Manager                                    │   │
│  │  - Credential pool (OpenRouter, NVIDIA, Pollinations)│   │
│  │  - Health tracking (последние N запросов)           │   │
│  │  - Rate limit tracking (429 counter)                │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Fallback Engine                                     │   │
│  │  1. Попытка с выбранной моделью                     │   │
│  │  2. При 429/402 → следующая модель в tier           │   │
│  │  3. При 500/503 → retry с exp backoff               │   │
│  │  4. Если tier исчерпан → fallback на tier выше      │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Cost Tracker                                        │   │
│  │  - Запись в БД: timestamp, model, tokens, cost      │   │
│  │  - Агрегация по провайдерам/моделям                 │   │
│  │  - Алерты при превышении лимитов                    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   OpenRouter         NVIDIA NIM         Pollinations
   :free models       deepseek-v4        openai proxy
```

---

## 🎚️ Tier System

### Tier 1: Бесплатные модели (черновая работа)

**Модели:**
1. `pollinations/openai` (943ms latency) — **PRIMARY**
2. `openrouter/nvidia/nemotron-3-super-120b-a12b:free` (1817ms)
3. `openrouter/openai/gpt-oss-120b:free`
4. `openrouter/google/gemma-4-31b-it:free`

**Триггеры:**
- Keywords: `summarize`, `list`, `extract`, `analyze logs`, `draft`, `translate`
- Prompt length < 500 tokens
- Temperature = 0 (детерминированные задачи)
- Вспомогательные задачи (не критичные)

**Применение:**
- Суммаризация логов
- Извлечение данных
- Простые списки и перечисления
- Черновики документации

---

### Tier 2: Средние модели (основная работа)

**Модели:**
1. `nvidia/deepseek-ai/deepseek-v4-flash` (5139ms) — **PRIMARY**
2. `openrouter/qwen/qwen3-next-80b-a3b-instruct:free` (fallback)
3. `pollinations/openai` (fallback при недоступности NVIDIA)

**Триггеры:**
- Keywords: `implement`, `refactor`, `debug`, `review`, `test`, `optimize`
- Prompt length 500-2000 tokens
- Код-генерация и рефакторинг
- Основные задачи агента

**Применение:**
- Написание кода
- Рефакторинг
- Код-ревью
- Отладка
- Тестирование

---

### Tier 3: Топовые модели (критические задачи)

**Модели:**
1. `nvidia/deepseek-ai/deepseek-v4-pro` — **PRIMARY**
2. `omniroute/kr/claude-sonnet-4.6` (fallback, если есть кредиты)
3. `nvidia/deepseek-ai/deepseek-v4-flash` (fallback при недоступности pro)

**Триггеры:**
- Keywords: `architecture`, `critical`, `production`, `security`, `design`
- Prompt length > 2000 tokens
- Явный запрос пользователя на топовую модель
- Критические баги

**Применение:**
- Архитектурные решения
- Критические баги в production
- Дизайн систем
- Аудит безопасности

---

## 🔄 Fallback Chain

### Сценарий 1: Rate Limit (429)

```
Request → Tier 1 Model A (429)
       → Tier 1 Model B (429)
       → Tier 1 Model C (success)
```

### Сценарий 2: Payment Required (402)

```
Request → Tier 3 Model (402, OpenRouter без кредитов)
       → Tier 3 Fallback (NVIDIA NIM, success)
```

### Сценарий 3: Server Error (500/503)

```
Request → Model A (500)
       → Retry after 1s (500)
       → Retry after 2s (500)
       → Fallback to Model B (success)
```

### Сценарий 4: Все модели tier недоступны

```
Request → Tier 1 (все модели 429/500)
       → Escalate to Tier 2
       → Tier 2 Model A (success)
```

---

## 📊 Request Classifier

### Алгоритм классификации

```python
def classify_request(messages: list, model: str = None) -> int:
    """
    Возвращает tier (1, 2, или 3)
    """
    # Явный запрос на конкретную модель
    if model and "claude" in model.lower():
        return 3
    if model and "gpt-4" in model.lower():
        return 3
    
    # Анализ последнего сообщения пользователя
    last_message = messages[-1]["content"].lower()
    
    # Tier 3 keywords (критические задачи)
    tier3_keywords = [
        "architecture", "critical", "production", "security",
        "design system", "audit", "vulnerability", "exploit"
    ]
    if any(kw in last_message for kw in tier3_keywords):
        return 3
    
    # Tier 2 keywords (основная работа)
    tier2_keywords = [
        "implement", "refactor", "debug", "review", "test",
        "optimize", "fix bug", "write code", "create function"
    ]
    if any(kw in last_message for kw in tier2_keywords):
        return 2
    
    # Tier 1 keywords (черновая работа)
    tier1_keywords = [
        "summarize", "list", "extract", "analyze logs",
        "draft", "translate", "what is", "explain"
    ]
    if any(kw in last_message for kw in tier1_keywords):
        return 1
    
    # По длине промпта
    total_length = sum(len(m["content"]) for m in messages)
    if total_length > 8000:  # ~2000 tokens
        return 3
    elif total_length > 2000:  # ~500 tokens
        return 2
    else:
        return 1
```

---

## 💾 Database Schema

### Таблица: `llm_requests`

```sql
CREATE TABLE llm_requests (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Request info
    requested_model VARCHAR(255),
    actual_model VARCHAR(255) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    tier INTEGER NOT NULL,
    
    -- Tokens
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    
    -- Cost (estimated)
    cost_usd DECIMAL(10, 6) DEFAULT 0,
    
    -- Performance
    latency_ms INTEGER,
    
    -- Status
    status_code INTEGER,
    error_message TEXT,
    
    -- Fallback tracking
    attempt_number INTEGER DEFAULT 1,
    fallback_reason VARCHAR(100),
    
    -- Indexes
    INDEX idx_timestamp (timestamp),
    INDEX idx_provider (provider),
    INDEX idx_tier (tier),
    INDEX idx_status (status_code)
);
```

### Таблица: `provider_health`

```sql
CREATE TABLE provider_health (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    provider VARCHAR(100) NOT NULL,
    model VARCHAR(255) NOT NULL,
    
    -- Health metrics
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    rate_limit_count INTEGER DEFAULT 0,
    avg_latency_ms INTEGER,
    
    -- Window (последние N минут)
    window_minutes INTEGER DEFAULT 60,
    
    INDEX idx_provider_model (provider, model),
    INDEX idx_timestamp (timestamp)
);
```

---

## 🚀 API Endpoints

### POST /v1/chat/completions

**Request:**
```json
{
  "model": "gpt-4",  // Опционально, будет переназначен
  "messages": [
    {"role": "user", "content": "Implement a binary search"}
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

**Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1714723806,
  "model": "nvidia/deepseek-v4-flash",  // Фактическая модель
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Here's a binary search implementation..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 120,
    "total_tokens": 135
  },
  "x-orchestration": {
    "requested_model": "gpt-4",
    "actual_model": "nvidia/deepseek-v4-flash",
    "tier": 2,
    "provider": "nvidia",
    "attempt": 1,
    "latency_ms": 5139
  }
}
```

### GET /v1/models

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "tier1-auto",
      "object": "model",
      "owned_by": "orchestration-gateway",
      "tier": 1,
      "description": "Automatic tier 1 model selection"
    },
    {
      "id": "tier2-auto",
      "object": "model",
      "owned_by": "orchestration-gateway",
      "tier": 2,
      "description": "Automatic tier 2 model selection"
    },
    {
      "id": "tier3-auto",
      "object": "model",
      "owned_by": "orchestration-gateway",
      "tier": 3,
      "description": "Automatic tier 3 model selection"
    },
    {
      "id": "pollinations/openai",
      "object": "model",
      "owned_by": "pollinations",
      "tier": 1
    },
    {
      "id": "nvidia/deepseek-v4-flash",
      "object": "model",
      "owned_by": "nvidia",
      "tier": 2
    }
  ]
}
```

### GET /health

**Response:**
```json
{
  "status": "healthy",
  "providers": {
    "openrouter": {"status": "healthy", "last_check": "2026-05-03T06:50:00Z"},
    "nvidia": {"status": "healthy", "last_check": "2026-05-03T06:50:00Z"},
    "pollinations": {"status": "healthy", "last_check": "2026-05-03T06:50:00Z"}
  },
  "database": {"status": "connected"},
  "uptime_seconds": 3600
}
```

### GET /metrics (Prometheus)

```
# HELP llm_requests_total Total number of LLM requests
# TYPE llm_requests_total counter
llm_requests_total{provider="nvidia",tier="2",status="200"} 150

# HELP llm_request_duration_seconds Request duration in seconds
# TYPE llm_request_duration_seconds histogram
llm_request_duration_seconds_bucket{provider="nvidia",le="1.0"} 10
llm_request_duration_seconds_bucket{provider="nvidia",le="5.0"} 140

# HELP llm_tokens_total Total tokens processed
# TYPE llm_tokens_total counter
llm_tokens_total{provider="nvidia",type="prompt"} 50000
llm_tokens_total{provider="nvidia",type="completion"} 30000
```

---

## 🔧 Конфигурация

### orchestration_gateway.yaml

```yaml
server:
  host: 127.0.0.1
  port: 8899
  workers: 2

providers:
  openrouter:
    enabled: true
    api_key_env: OPENROUTER_API_KEY
    base_url: https://openrouter.ai/api/v1
    timeout: 30
    retry_attempts: 2
    
  nvidia:
    enabled: true
    api_key_env: NVIDIA_API_KEY
    base_url: https://integrate.api.nvidia.com/v1
    timeout: 60
    retry_attempts: 2
    
  pollinations:
    enabled: true
    api_key_env: null  # Не требует ключа
    base_url: https://text.pollinations.ai
    timeout: 30
    retry_attempts: 2

tiers:
  tier1:
    models:
      - provider: pollinations
        model: openai
        priority: 1
      - provider: openrouter
        model: nvidia/nemotron-3-super-120b-a12b:free
        priority: 2
      - provider: openrouter
        model: openai/gpt-oss-120b:free
        priority: 3
        
  tier2:
    models:
      - provider: nvidia
        model: deepseek-ai/deepseek-v4-flash
        priority: 1
      - provider: openrouter
        model: qwen/qwen3-next-80b-a3b-instruct:free
        priority: 2
      - provider: pollinations
        model: openai
        priority: 3
        
  tier3:
    models:
      - provider: nvidia
        model: deepseek-ai/deepseek-v4-pro
        priority: 1
      - provider: nvidia
        model: deepseek-ai/deepseek-v4-flash
        priority: 2

database:
  host: 127.0.0.1
  port: 5432
  dbname: postgres
  user_env: POSTGRES_USER
  password_env: POSTGRES_PASSWORD
  options: "-c search_path=automation,public"

monitoring:
  prometheus_enabled: true
  prometheus_port: 9101
  health_check_interval: 60  # seconds
  
logging:
  level: INFO
  format: json
  file: /var/log/orchestration-gateway/gateway.log
```

---

## 📦 Структура проекта

```
/srv/orchestration-gateway/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Загрузка конфигурации
│   ├── models.py               # Pydantic models
│   ├── classifier.py           # Request classifier
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py             # BaseProvider
│   │   ├── openrouter.py
│   │   ├── nvidia.py
│   │   └── pollinations.py
│   ├── fallback.py             # Fallback engine
│   ├── cost_tracker.py         # Cost tracking
│   └── health.py               # Health checks
├── config.yaml
├── requirements.txt
├── systemd/
│   └── orchestration-gateway.service
└── README.md
```

---

## 🎯 Следующие шаги

1. ✅ Анализ использования — **ЗАВЕРШЕНО**
2. ✅ Проверка провайдеров — **ЗАВЕРШЕНО**
3. 🔄 Детальный дизайн — **ТЕКУЩИЙ ШАГ**
4. ⏳ Реализация базового gateway
5. ⏳ Интеграция с Hermes Agent
6. ⏳ Тестирование и оптимизация

---

## 📈 Ожидаемые результаты

- **Экономия:** 80-95% затрат на инференс
- **Доступность:** 99%+ (3 независимых провайдера)
- **Latency:** 1-5 секунд (зависит от tier)
- **Прозрачность:** Drop-in replacement для Hermes Agent
