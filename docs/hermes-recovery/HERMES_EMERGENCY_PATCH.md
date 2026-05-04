# 🚨 HERMES EMERGENCY PATCH

**Статус:** READY TO APPLY  
**Дата:** 2026-05-04  
**Приоритет:** CRITICAL  
**Проблема:** Runtime fallback loop на несовместимой модели

---

## 📋 Проблема

### Что произошло

1. Primary model (Claude/GPT) словил rate limit
2. Hermes автоматически переключился на fallback: `meta/llama-3.3-70b-instruct via nvidia`
3. Fallback модель **НЕ поддерживает** parallel tool calls
4. Hermes отправил multi-tool payload
5. HTTP 400: "This model only supports single tool-calls at once!"
6. Попытка retry → тот же fallback → HTTP 400 → **бесконечный loop**

### Текущее поведение (СЛОМАНО)

```
Primary rate limited 
  ↓
NVIDIA llama fallback 
  ↓
Multi-tool payload 
  ↓
HTTP 400 
  ↓
Retry → тот же fallback → HTTP 400 → LOOP
```

### Нужное поведение

```
Primary rate limited 
  ↓
Compatible fallback exists?
  ├─ YES → Use compatible fallback
  └─ NO → Checkpoint + Pause + Report blocked
```

---

## 🎯 Emergency Patch (Отправить Hermes ПЕРВЫМ сообщением)

```
Primary model recovered. Before any other work, apply emergency safe-mode patch.

Goal: Disable incompatible fallback meta/llama-3.3-70b-instruct via nvidia for tool-heavy/multi-tool tasks.

Requirements:
1. Backup config before edits.
2. Do not continue roadmap.
3. Do not run Phase 10.0.
4. Patch router/config so that if primary model is rate limited and no compatible tool-capable fallback exists, Hermes checkpoints and pauses instead of falling back to NVIDIA llama.
5. Do not retry the same multi-tool payload.
6. Show proof:
   - changed file paths;
   - config diff;
   - restart status;
   - logs showing no "only supports single tool-calls" loop;
   - current task marked paused/blocked, not failed.

Status label: incident hotfix, not production ready.
```

---

## 🔧 Что должен сделать Hermes

### 1. Backup конфига

```bash
cp /home/Bilirubin/.hermes/config.yaml \
   /home/Bilirubin/.hermes/config.yaml.bak.$(date -u +%Y%m%d_%H%M%S)
```

### 2. Найти fallback конфигурацию

```bash
grep -RniE "fallback|nvidia|llama-3.3|parallel_tool|tool_calls" \
  /home/Bilirubin/.hermes/config.yaml \
  /home/Bilirubin/.hermes/hermes-agent \
  2>/dev/null | head -50
```

### 3. Отключить несовместимый fallback

Добавить в конфиг логику:

```yaml
fallback:
  enabled: true
  disable_incompatible_tool_fallbacks: true
  
disabled_for_tool_heavy_tasks:
  - meta/llama-3.3-70b-instruct
  
single_tool_only_models:
  - meta/llama-3.3-70b-instruct
  
on_primary_rate_limit:
  if_no_compatible_tool_fallback: pause_and_checkpoint
  do_not_use_incompatible_fallback: true
```

**ИЛИ** временно жёстко:

```yaml
fallback_providers: []
```

### 4. Обновить router логику

В `/home/Bilirubin/.hermes/hermes-agent/` найти код fallback и добавить проверку:

```python
def select_fallback_model(task_requires_tools: bool, task_requires_parallel_tools: bool):
    if task_requires_parallel_tools:
        # Не использовать модели, которые не поддерживают parallel tools
        compatible_fallbacks = [
            m for m in fallback_models 
            if m.supports_parallel_tool_calls
        ]
        if not compatible_fallbacks:
            return None  # Checkpoint + pause
    
    # ... остальная логика
```

### 5. Перезапустить сервис

```bash
sudo systemctl restart hermes-gateway
```

### 6. Проверить логи

```bash
# Не должно быть "single tool-calls" ошибок
sudo journalctl -u hermes-gateway --since "5 minutes ago" | \
  grep -i "single tool-calls\|HTTP 400\|llama-3.3"
```

---

## ✅ Acceptance Criteria

После патча должно быть:

- ✅ Config backup создан
- ✅ NVIDIA llama отключён для tool-heavy tasks
- ✅ При rate limit primary model → checkpoint + pause (не fallback)
- ✅ Нет HTTP 400 "single tool-calls" в логах
- ✅ hermes-gateway перезапущен успешно
- ✅ Current task marked as `paused/blocked`, не `failed`
- ✅ Нет retry loop

---

## 🔍 Проверка после патча

### Команды для проверки

```bash
# 1. Проверка конфига
grep -i "llama-3.3\|nvidia.*fallback" /home/Bilirubin/.hermes/config.yaml

# 2. Проверка логов (не должно быть ошибок)
sudo journalctl -u hermes-gateway --since "10 minutes ago" | \
  grep -i "single tool-calls\|HTTP 400"

# 3. Статус сервиса
systemctl status hermes-gateway

# 4. Проверка что задача в правильном статусе
ls -la /home/Bilirubin/.hermes/tasks/*/task_plan.json
cat /home/Bilirubin/.hermes/tasks/*/task_plan.json | grep -i status
```

### Ожидаемые результаты

```bash
# grep конфига - должен показать что llama-3.3 отключён
disabled_for_tool_heavy_tasks:
  - meta/llama-3.3-70b-instruct

# grep логов - должен быть пустой вывод (нет ошибок)
# (пустой вывод = хорошо)

# systemctl status - должен быть active
● hermes-gateway.service - Hermes Gateway
   Active: active (running)

# task status - должен быть paused/blocked
"status": "paused"
```

---

## 🚫 Что НЕ делать после патча

- ❌ Не продолжать Phase 10.0 сразу
- ❌ Не запускать roadmap
- ❌ Не давать большие multi-step задачи
- ❌ Не использовать NVIDIA llama для tool-heavy работы

---

## ✅ Что делать после патча

1. **Проверить proof** (см. выше)
2. **Подождать 5-10 минут** и убедиться что нет новых ошибок
3. **Создать incident report**
4. **Только потом** продолжать Phase 9.9: Provider Capability Router (полный)
5. **Только после Phase 9.9** продолжать Phase 10.0

---

## 📊 Timeline

| Время | Действие |
|-------|----------|
| **Сейчас** | Ждём сброс rate limit (30-60 мин) |
| **После сброса** | Отправить emergency patch Hermes |
| **+5 мин** | Hermes применяет patch |
| **+10 мин** | Проверка proof |
| **+15 мин** | Incident report |
| **+30 мин** | Phase 9.9: Provider Capability Router |
| **+2 часа** | Phase 10.0: Reliable Agent Runtime |

---

## 🆘 Если патч не помог

### Fallback план

Если Hermes снова падает в loop:

```bash
# 1. Остановить сервис
sudo systemctl stop hermes-gateway

# 2. Жёстко отключить все fallbacks
echo "fallback_providers: []" >> /home/Bilirubin/.hermes/config.yaml

# 3. Запустить сервис
sudo systemctl start hermes-gateway

# 4. Проверить
systemctl status hermes-gateway
```

### Manual fix через SSH

Если нужно чинить руками:

```bash
# Подключиться к серверу
ssh bilirubin@your-server.com

# Backup
cp /home/Bilirubin/.hermes/config.yaml \
   /home/Bilirubin/.hermes/config.yaml.emergency.bak

# Редактировать конфиг
nano /home/Bilirubin/.hermes/config.yaml

# Найти секцию fallback и отключить NVIDIA llama
# Сохранить: Ctrl+O, Enter, Ctrl+X

# Перезапустить
sudo systemctl restart hermes-gateway

# Проверить
sudo journalctl -u hermes-gateway -n 50
```

---

## 📝 Incident Report Template

После успешного патча Hermes должен создать:

```markdown
# Incident Report: Provider Fallback Loop

## Status
incident hotfix applied

## Timeline
- 2026-05-04 08:00 UTC: Primary model rate limited
- 2026-05-04 08:01 UTC: Fallback to NVIDIA llama
- 2026-05-04 08:01 UTC: HTTP 400 loop detected
- 2026-05-04 08:30 UTC: Emergency patch applied
- 2026-05-04 08:35 UTC: Verified no loop

## Root Cause
Provider router did not check model capability before fallback.
NVIDIA llama does not support parallel tool calls.

## Fix Applied
- Disabled NVIDIA llama for tool-heavy tasks
- Added checkpoint + pause on incompatible fallback
- No retry on HTTP 400 capability mismatch

## Verification
- Config diff: [показать]
- Logs clean: [показать]
- Service restarted: [показать]
- Task paused correctly: [показать]

## Next Steps
- Phase 9.9: Full Provider Capability Router
- Phase 10.0: Reliable Agent Runtime
```

---

## 🎯 Success Criteria

Патч считается успешным когда:

1. ✅ Hermes применил patch без ошибок
2. ✅ Нет HTTP 400 loop в логах
3. ✅ hermes-gateway работает стабильно
4. ✅ При следующем rate limit → checkpoint + pause (не crash)
5. ✅ Incident report создан
6. ✅ Можно продолжать Phase 9.9

---

**ГОТОВО К ПРИМЕНЕНИЮ**

Отправь Hermes текст из секции "Emergency Patch" когда primary model восстановится.
