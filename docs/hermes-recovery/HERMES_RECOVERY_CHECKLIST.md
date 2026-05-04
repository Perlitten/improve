# 🚨 HERMES RECOVERY CHECKLIST

**Date:** 2026-05-04  
**Status:** READY TO EXECUTE  
**Problem:** Runtime fallback loop + missing reliable runtime

---

## 📋 Current Situation

### What's Broken

1. ✅ **Provider fallback loop** — Hermes crashes with HTTP 400 on rate limit
2. ✅ **Session reset** — requires manual /resume after restart
3. ✅ **Message interruption** — new message interrupts current task
4. ✅ **MCP reconnect** — requires gateway restart

### What Needs Fixing

1. **Emergency Patch** — disable incompatible fallback
2. **Phase 9.9** — Provider Capability Router
3. **Phase 10.0** — Reliable Agent Runtime

---

## ⏰ Timeline

| Stage | Time | Status |
|------|------|--------|
| **Wait for rate limit reset** | 30-60 min | ⏳ In progress |
| **Emergency Patch** | +5 min | 📝 Ready to apply |
| **Verify patch** | +10 min | ⏸️ Waiting |
| **Phase 9.9** | +30 min | ⏸️ Waiting |
| **Phase 10.0** | +2 hours | ⏸️ Waiting |

---

## 🎯 Step 1: Wait for Rate Limit Reset

### What to Do NOW

**DON'T:**
- ❌ Don't give Hermes large tasks
- ❌ Don't continue Phase 10.0
- ❌ Don't start roadmap
- ❌ Don't try to fix through broken runtime

**WAIT:**
- ⏳ 30-60 minutes for rate limit reset
- ⏳ Primary model (Claude/GPT) will recover

### How to Check if Rate Limit Reset

```bash
# Check logs
sudo journalctl -u hermes-gateway --since "5 minutes ago" | grep -i "rate limit\|429"

# If empty — limit reset
```

---

## 🎯 Step 2: Emergency Patch

### When to Apply

✅ **ONLY AFTER** rate limit reset

### What to Send to Hermes

Copy and send as **FIRST message**:

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

### What Hermes Should Do

1. ✅ Backup config
2. ✅ Disable NVIDIA llama for tool-heavy tasks
3. ✅ Update router logic
4. ✅ Restart hermes-gateway
5. ✅ Show proof

### Verification After Patch

```bash
# 1. Проверка конфига
grep -i "llama-3.3\|nvidia.*fallback" /home/Bilirubin/.hermes/config.yaml

# 2. Проверка логов (должно быть пусто)
sudo journalctl -u hermes-gateway --since "10 minutes ago" | \
  grep -i "single tool-calls\|HTTP 400"

# 3. Статус сервиса
systemctl status hermes-gateway

# 4. Проверка задачи
cat /home/Bilirubin/.hermes/tasks/*/task_plan.json | grep -i status
```

### Ожидаемый результат

- ✅ Config backup создан
- ✅ NVIDIA llama отключён для tool-heavy tasks
- ✅ Нет HTTP 400 в логах
- ✅ hermes-gateway active
- ✅ Task status = paused/blocked (не failed)

---

## 🎯 Шаг 3: Phase 9.9 Provider Router

### Когда запускать

✅ **ТОЛЬКО ПОСЛЕ** успешного emergency patch

### Что отправить Hermes

```
Start Phase 9.9: Provider Capability Router.

Prerequisites:
- Emergency patch applied and verified
- No HTTP 400 loop in logs
- hermes-gateway stable

Goal:
Build capability-aware model router that prevents incompatible fallback.

Components:
1. Model Capability Registry
2. Capability-Aware Router
3. Single Tool Mode
4. HTTP 400 Handler
5. Rate Limit Handler
6. Acceptance Tests
7. Documentation

Do not start Phase 10.0 until Phase 9.9 passes all acceptance tests.
```

### Acceptance Tests

```bash
# Запустить тесты
/home/Bilirubin/.hermes/venv/bin/python3 \
  /home/Bilirubin/.hermes/tests/test_provider_router.py

# Ожидаемый результат
✅ All tests passed!
```

### Проверка Phase 9.9

- ✅ Model capability registry создан
- ✅ Router работает
- ✅ Single tool mode enforced
- ✅ HTTP 400 handler не создаёт loop
- ✅ Rate limit handler использует compatible fallback
- ✅ Все acceptance tests passed
- ✅ Нет HTTP 400 в логах

---

## 🎯 Шаг 4: Phase 10.0 Reliable Runtime

### Когда запускать

✅ **ТОЛЬКО ПОСЛЕ** Phase 9.9 complete

### Что отправить Hermes

```
Start Phase 10.0: Reliable Agent Runtime.

Prerequisites:
- Phase 9.9 Provider Router complete
- All acceptance tests passed
- No HTTP 400 loop

Goal:
Transform Hermes from interactive chat to reliable task runtime.

Components:
1. Persistent Inbound Queue
2. Intake Classifier
3. Task Orchestrator
4. Ralph-style Task Workspace
5. Checkpoint + Auto Resume
6. MCP Auto-Reconnect
7. Interruption Policy
8. Background Planner Worker
9. Runtime Health
10. Acceptance Tests

Status label after completion: reliable_runtime_foundation_complete
NOT: production_ready (that comes after observability)
```

### Acceptance Tests

12 тестов (см. HERMES_PHASE_10_0_RELIABLE_RUNTIME.md)

### Проверка Phase 10.0

- ✅ Persistent inbox queue работает
- ✅ Intake classifier классифицирует правильно
- ✅ Task orchestrator не прерывает задачи
- ✅ Checkpoint + auto resume работает
- ✅ MCP auto-reconnect работает
- ✅ Interruption policy enforced
- ✅ Runtime health monitoring
- ✅ Все acceptance tests passed
- ✅ Нет manual /resume required

---

## 📊 Проверка успеха

### После Emergency Patch

```bash
# Нет HTTP 400 loop
sudo journalctl -u hermes-gateway --since "1 hour ago" | \
  grep -i "single tool-calls" | wc -l
# Ожидается: 0

# Gateway stable
systemctl is-active hermes-gateway
# Ожидается: active
```

### После Phase 9.9

```bash
# Acceptance tests passed
/home/Bilirubin/.hermes/venv/bin/python3 \
  /home/Bilirubin/.hermes/tests/test_provider_router.py
# Ожидается: ✅ All tests passed!

# Router работает
/home/Bilirubin/.hermes/venv/bin/python3 \
  /home/Bilirubin/.hermes/scripts/model_router.py
# Ожидается: Model Capabilities Registry loaded
```

### После Phase 10.0

```bash
# Runtime health
/home/Bilirubin/.hermes/venv/bin/python3 \
  /home/Bilirubin/.hermes/scripts/hermes_status.py
# Ожидается: все поля заполнены

# Inbox queue работает
psql -U automation -d rag -c "SELECT count(*) FROM agent_inbox;"
# Ожидается: > 0

# Tasks работают
psql -U automation -d rag -c "SELECT count(*) FROM agent_tasks;"
# Ожидается: > 0
```

---

## 🚫 Что НЕ делать

### Во время ожидания rate limit

- ❌ Не давать Hermes большие задачи
- ❌ Не пытаться чинить через сломанный runtime
- ❌ Не продолжать roadmap

### После Emergency Patch

- ❌ Не продолжать Phase 10.0 сразу
- ❌ Не пропускать Phase 9.9
- ❌ Не давать большие multi-step задачи

### После Phase 9.9

- ❌ Не пропускать acceptance tests
- ❌ Не продолжать если тесты не прошли

---

## 🆘 Если что-то пошло не так

### Emergency Patch не помог

```bash
# Жёстко отключить все fallbacks
sudo systemctl stop hermes-gateway
echo "fallback_providers: []" >> /home/Bilirubin/.hermes/config.yaml
sudo systemctl start hermes-gateway
```

### Phase 9.9 тесты не прошли

```bash
# Проверить логи
sudo journalctl -u hermes-gateway -n 100

# Откатить изменения
cd /home/Bilirubin/.hermes
git log --oneline -5
git reset --hard <commit-before-phase-9.9>
sudo systemctl restart hermes-gateway
```

### Phase 10.0 не работает

```bash
# Проверить БД
psql -U automation -d rag -c "\dt"

# Проверить таблицы
psql -U automation -d rag -c "SELECT * FROM agent_inbox LIMIT 5;"
psql -U automation -d rag -c "SELECT * FROM agent_tasks LIMIT 5;"

# Откатить если нужно
cd /home/Bilirubin/.hermes
git reset --hard <commit-before-phase-10.0>
sudo systemctl restart hermes-gateway
```

---

## 📝 Документация

### Созданные файлы

1. ✅ `HERMES_EMERGENCY_PATCH.md` — emergency patch инструкции
2. ✅ `HERMES_PHASE_9_9_PROVIDER_ROUTER.md` — Phase 9.9 полная спецификация
3. ✅ `HERMES_PHASE_10_0_RELIABLE_RUNTIME.md` — Phase 10.0 полная спецификация
4. ✅ `HERMES_RECOVERY_CHECKLIST.md` — этот чеклист

### Где читать

- **Быстрый старт:** Этот файл
- **Emergency Patch:** `HERMES_EMERGENCY_PATCH.md`
- **Phase 9.9:** `HERMES_PHASE_9_9_PROVIDER_ROUTER.md`
- **Phase 10.0:** `HERMES_PHASE_10_0_RELIABLE_RUNTIME.md`

---

## ✅ Success Criteria

### Emergency Patch Success

- ✅ Нет HTTP 400 loop
- ✅ hermes-gateway stable
- ✅ Task paused correctly (не failed)

### Phase 9.9 Success

- ✅ All acceptance tests passed
- ✅ Router выбирает compatible models
- ✅ Single tool mode enforced
- ✅ Нет HTTP 400 в логах

### Phase 10.0 Success

- ✅ All acceptance tests passed
- ✅ Нет manual /resume required
- ✅ Messages не прерывают tasks
- ✅ MCP auto-reconnect работает
- ✅ Runtime health monitoring работает

---

## 🎯 Финальная цель

После всех трёх этапов:

**Hermes должен работать как reliable task runtime:**
- ✅ Не падает на rate limit
- ✅ Не требует manual /resume
- ✅ Не прерывается новыми сообщениями
- ✅ Восстанавливается сам после restart
- ✅ Имеет persistent queue и checkpoints

**Status label:** `reliable_runtime_foundation_complete`

**NOT:** `production_ready` (это после observability)

---

**ГОТОВО К ВЫПОЛНЕНИЮ**

Начинай с Шага 1: Ждём сброс rate limit (30-60 мин)
