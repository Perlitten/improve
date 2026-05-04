# Phase 10.0: Reliable Agent Runtime

**Статус:** READY TO START (после Phase 9.9)  
**Приоритет:** HIGH  
**Зависимости:** Phase 9.9 Provider Router должен быть завершён

---

## 🎯 Цель

Hermes должен работать не как интерактивный чат, а как устойчивый task runtime:
- Входящие сообщения не прерывают текущую задачу
- Новые запросы попадают в persistent queue
- Long-running tasks имеют durable plan/progress/checkpoints
- После restart Hermes восстанавливается сам
- `/resume` остаётся fallback, но не основной механизм

---

## 📋 Задача для Hermes

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

---

## 1. Persistent Inbound Queue

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS agent_inbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source TEXT NOT NULL,  -- telegram, custom_gpt, cli, webhook
    user_id TEXT,
    channel TEXT,
    raw_text TEXT NOT NULL,  -- after secret redaction
    redacted_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    -- new, classified, queued, attached_to_task, processed, ignored, failed
    priority TEXT NOT NULL DEFAULT 'normal',  -- low, normal, high, urgent
    classification TEXT,
    -- interrupt, append_to_current, new_task, cancel_request, status_request, ignore, needs_user
    active_task_id UUID,
    related_task_id UUID,
    requires_user BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_inbox_status ON agent_inbox(status);
CREATE INDEX idx_inbox_priority ON agent_inbox(priority);
CREATE INDEX idx_inbox_created ON agent_inbox(created_at);
```

### Правило

**Каждое входящее сообщение** сначала пишется в очередь, **не обрабатывается напрямую**.

---

## 2. Intake Classifier

### Файл

`/home/Bilirubin/.hermes/scripts/intake_classifier.py`

### Input

```json
{
  "new_message": "текст сообщения",
  "active_task": {
    "id": "uuid",
    "title": "Phase 10.0",
    "status": "active",
    "current_phase": "checkpoint",
    "current_story_id": "S3"
  },
  "recent_context": "summary of last 5 messages"
}
```

### Output

```json
{
  "classification": "append_to_current|new_task|interrupt|cancel_request|status_request|ignore|needs_user",
  "priority": "low|normal|high|urgent",
  "reason": "User is clarifying current checkpoint implementation",
  "related_task_id": "uuid",
  "suggested_action": "Add to task inbox, continue current iteration",
  "should_interrupt_current_task": false
}
```

### Правила классификации

**append_to_current:**
- Пользователь уточняет текущую задачу
- Прислал ошибку/скрин/новое ограничение
- Пишет "вот ещё", "добавь", "смотри", "это касается этой задачи"

**new_task:**
- Новый независимый запрос
- Не связан с текущей задачей
- Можно положить в backlog

**interrupt:**
- Срочно
- Безопасность
- Сервер падает
- Пользователь явно пишет "стоп", "останови", "срочно", "не делай это"

**cancel_request:**
- Пользователь просит отменить текущую задачу

**status_request:**
- "что происходит?", "где мы?", "покажи статус"

**ignore:**
- Casual chatter без задачи

**needs_user:**
- Нужен секрет, UI action, billing/domain/manual confirmation

### Implementation

```python
#!/usr/bin/env python3
"""
Intake classifier for agent messages.
Classifies incoming messages without interrupting active task.
"""

import json
import sys
from typing import Dict, Optional


def classify_message(
    new_message: str,
    active_task: Optional[Dict],
    recent_context: str
) -> Dict:
    """
    Classify incoming message.
    
    Returns classification dict.
    """
    msg_lower = new_message.lower()
    
    # Check for interrupt keywords
    interrupt_keywords = [
        "стоп", "останови", "cancel", "не делай",
        "срочно", "emergency", "urgent"
    ]
    if any(kw in msg_lower for kw in interrupt_keywords):
        return {
            "classification": "interrupt",
            "priority": "urgent",
            "reason": "User requested immediate stop",
            "related_task_id": active_task["id"] if active_task else None,
            "suggested_action": "Pause current task immediately",
            "should_interrupt_current_task": True
        }
    
    # Check for status request
    status_keywords = [
        "что происходит", "где мы", "статус", "status",
        "покажи", "show me", "what's happening"
    ]
    if any(kw in msg_lower for kw in status_keywords):
        return {
            "classification": "status_request",
            "priority": "normal",
            "reason": "User requested status update",
            "related_task_id": active_task["id"] if active_task else None,
            "suggested_action": "Send status update, continue task",
            "should_interrupt_current_task": False
        }
    
    # Check for append to current
    if active_task:
        append_keywords = [
            "вот ещё", "добавь", "смотри", "также",
            "кстати", "ещё", "по этой задаче"
        ]
        if any(kw in msg_lower for kw in append_keywords):
            return {
                "classification": "append_to_current",
                "priority": "normal",
                "reason": "User is adding to current task",
                "related_task_id": active_task["id"],
                "suggested_action": "Add to task inbox, process at next iteration boundary",
                "should_interrupt_current_task": False
            }
    
    # Check for needs_user
    needs_user_keywords = [
        "пароль", "password", "секрет", "secret",
        "подтверди", "confirm", "approve"
    ]
    if any(kw in msg_lower for kw in needs_user_keywords):
        return {
            "classification": "needs_user",
            "priority": "high",
            "reason": "Message requires user input/approval",
            "related_task_id": active_task["id"] if active_task else None,
            "suggested_action": "Queue for user interaction",
            "should_interrupt_current_task": False
        }
    
    # Default: new task
    return {
        "classification": "new_task",
        "priority": "normal",
        "reason": "Independent new request",
        "related_task_id": None,
        "suggested_action": "Queue as new task",
        "should_interrupt_current_task": False
    }


if __name__ == "__main__":
    # Test
    test_cases = [
        {
            "message": "стоп, не делай это",
            "expected": "interrupt"
        },
        {
            "message": "где мы сейчас?",
            "expected": "status_request"
        },
        {
            "message": "вот ещё одна ошибка по этой задаче",
            "expected": "append_to_current"
        },
        {
            "message": "создай новый проект",
            "expected": "new_task"
        }
    ]
    
    active_task = {
        "id": "test-uuid",
        "title": "Test Task",
        "status": "active"
    }
    
    print("Testing intake classifier:\n")
    for test in test_cases:
        result = classify_message(test["message"], active_task, "")
        status = "✅" if result["classification"] == test["expected"] else "❌"
        print(f"{status} '{test['message']}' → {result['classification']}")
```

---

## 3. Task Orchestrator

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS agent_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    title TEXT NOT NULL,
    domain TEXT NOT NULL,  -- hermes, infra, memory, etc
    status TEXT NOT NULL DEFAULT 'queued',
    -- queued, active, paused, blocked, done, cancelled, failed, interrupted, recovering
    priority TEXT NOT NULL DEFAULT 'normal',
    
    current_phase TEXT,
    current_story_id TEXT,
    goal TEXT,
    
    plan_path TEXT,  -- /home/Bilirubin/.hermes/tasks/<id>/task_plan.json
    progress_path TEXT,
    last_checkpoint_path TEXT,
    
    requires_user BOOLEAN DEFAULT false,
    risk_level TEXT DEFAULT 'low',  -- low, medium, high, critical
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_tasks_status ON agent_tasks(status);
CREATE INDEX idx_tasks_priority ON agent_tasks(priority);
CREATE INDEX idx_tasks_updated ON agent_tasks(updated_at);
```

### Файл

`/home/Bilirubin/.hermes/scripts/task_orchestrator.py`

### Responsibilities

1. Следить за active task
2. Читать agent_inbox
3. Не запускать две write-heavy задачи одновременно
4. При новом сообщении:
   - Классифицировать
   - Либо attached_to_task
   - Либо queued as new task
   - Либо interrupt только если high/urgent/manual cancel
5. Вести task state

---

## 4. Ralph-style Task Workspace

### Structure

```
/home/Bilirubin/.hermes/tasks/<task_id>/
├── task_plan.json
├── progress.md
├── checkpoints/
│   ├── checkpoint_001.json
│   ├── checkpoint_002.json
│   └── latest.json
├── reports/
│   ├── story_S1_report.md
│   └── story_S2_report.md
├── artifacts/
├── evals/
│   └── operator_standard_eval.json
└── inbox.md
```

### task_plan.json

```json
{
  "task_id": "uuid",
  "title": "Phase 10.0 Reliable Agent Runtime",
  "domain": "hermes",
  "status": "active",
  "current_phase": "checkpoint_manager",
  "stories": [
    {
      "id": "S1",
      "title": "Create persistent inbound queue",
      "status": "done",
      "acceptance_criteria": [
        "agent_inbox table exists",
        "new message is stored before processing",
        "secrets are redacted"
      ],
      "risk": "medium"
    },
    {
      "id": "S2",
      "title": "Implement intake classifier",
      "status": "done",
      "acceptance_criteria": [
        "classifier.py exists",
        "classifies interrupt correctly",
        "classifies append_to_current correctly"
      ],
      "risk": "low"
    },
    {
      "id": "S3",
      "title": "Build checkpoint manager",
      "status": "in_progress",
      "acceptance_criteria": [
        "checkpoint saved before restart",
        "checkpoint restored on startup",
        "no manual /resume required"
      ],
      "risk": "high"
    }
  ],
  "stop_conditions": [
    "secret required",
    "manual UI required",
    "destructive action required",
    "acceptance test failed",
    "system health unsafe"
  ],
  "requires_user": false
}
```

### progress.md

```markdown
# Progress

## 2026-05-04 10:00 UTC
- Current story: S3
- Action: Created checkpoint manager
- Verification: Checkpoint saved successfully
- Result: passed
- Next: Test auto-resume

## 2026-05-04 09:30 UTC
- Current story: S2
- Action: Implemented intake classifier
- Verification: All test cases passed
- Result: passed
- Next: Build checkpoint manager
```

---

## 5. Checkpoint + Auto Resume

### Checkpoint Format

```json
{
  "checkpoint_id": "uuid",
  "timestamp": "2026-05-04T10:00:00Z",
  "session_id": "session-uuid",
  "active_task_id": "task-uuid",
  "current_phase": "checkpoint_manager",
  "current_story_id": "S3",
  "last_user_intent": "Build reliable runtime",
  "context_pack_goal": "Complete Phase 10.0",
  "last_successful_step": "Created checkpoint manager",
  "pending_user_action": null,
  "pending_risky_action": null,
  "restore_mode": "auto"
}
```

### Auto-Resume Logic

```python
def auto_resume_on_startup():
    """
    Auto-resume active tasks on startup.
    """
    # 1. Find active/interrupted tasks
    active_tasks = db.query(
        "SELECT * FROM agent_tasks WHERE status IN ('active', 'interrupted')"
    )
    
    if not active_tasks:
        return
    
    for task in active_tasks:
        # 2. Load latest checkpoint
        checkpoint = load_checkpoint(task["last_checkpoint_path"])
        
        if not checkpoint:
            continue
        
        # 3. Check restore mode
        if checkpoint["restore_mode"] == "manual_required":
            notify_user(f"Task {task['title']} requires manual resume")
            continue
        
        # 4. Check for pending risky actions
        if checkpoint["pending_risky_action"]:
            notify_user(f"Task {task['title']} has pending risky action")
            continue
        
        # 5. Rebuild context pack
        context = rebuild_context_from_checkpoint(checkpoint)
        
        # 6. Restore task state
        task["status"] = "active"
        db.update_task(task)
        
        # 7. Notify user
        notify_user(f"""
Session restored from checkpoint.
Active task: {task['title']}
Current story: {checkpoint['current_story_id']}
Continuing from last safe step.
        """)
        
        # 8. Continue execution
        continue_task(task, context)
```

### Telegram Notification

```
Session restored from checkpoint.
Active task: Phase 10.0 Reliable Agent Runtime
Current story: S3 - Build checkpoint manager
Continuing from last safe step.
```

**НЕ должно быть:**
```
Conversation history cleared. Use /resume.
```

---

## 6. MCP Auto-Reconnect

### Requirements

- brain-mcp restart не должен требовать restart hermes-gateway
- Gateway должен пробовать reconnect
- Backoff: 1s, 2s, 5s, 10s, 30s, max 60s
- При восстановлении обновлять runtime status

### Logs

```
mcp_disconnected at 2026-05-04T10:00:00Z
mcp_reconnect_attempt 1
mcp_reconnect_attempt 2
mcp_reconnected=true downtime_seconds=5 active_session_restored=true
```

---

## 7. Interruption Policy

### Правило

Новое сообщение **НЕ должно** прерывать текущую задачу, кроме:

1. **User says:**
   - стоп
   - останови
   - cancel
   - не делай
   - срочно
   - emergency

2. **Security issue:**
   - Leaked secret
   - Destructive action detected
   - Public endpoint exposure
   - Data loss risk

3. **System issue:**
   - Disk critical > 90%
   - Gateway down
   - Database down
   - Backup failed during destructive operation

### Иначе

```
Новое сообщение 
  ↓
agent_inbox 
  ↓
classified 
  ↓
queued/attached 
  ↓
Current task continues
```

### User Response

```
Принял. Я добавил это к текущей задаче и учту на следующей итерации.
```

или

```
Принял. Это новая задача, поставил в очередь после текущей.
```

---

## 8. Background Planner Worker

### Цель

Когда пользователь пишет новое сообщение во время long-running task, основной executor не должен отвлекаться.

### Planner Worker

- Читает agent_inbox
- Классифицирует
- Обновляет task_plan/inbox.md
- **НЕ выполняет** risky actions
- **НЕ запускает** shell
- **НЕ меняет** систему
- Только планирует/очередит/прикрепляет

### Файл

`/home/Bilirubin/.hermes/scripts/planner_worker.py`

### Systemd Service

```ini
[Unit]
Description=Hermes Planner Worker
After=network.target

[Service]
Type=simple
User=Bilirubin
ExecStart=/home/Bilirubin/.hermes/venv/bin/python3 \
  /home/Bilirubin/.hermes/scripts/planner_worker.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

## 9. Ralph-style Iteration Runner

### Command

```bash
/home/Bilirubin/.hermes/scripts/hermes_task_loop.py run <task_id> --max-iterations 5
```

### Each Iteration

1. Load task_plan.json
2. Load progress.md
3. Load pending task inbox
4. Build Memory OS context pack
5. Pick next todo/in_progress story
6. Execute one story only
7. Run acceptance tests
8. Write implementation report
9. Run operator_standard_eval.py on report
10. Update progress.md
11. Save checkpoint
12. Process queued messages at boundary
13. Stop if:
    - All stories done
    - Test failed
    - Manual/risky/secret action required
    - Max iterations reached
    - System health unsafe

---

## 10. Runtime Health

### Status Fields

```json
{
  "active_task_id": "uuid",
  "active_task_title": "Phase 10.0",
  "current_story_id": "S3",
  "executor_status": "running",
  "planner_worker_status": "running",
  "inbox_new_count": 2,
  "inbox_queued_count": 1,
  "last_checkpoint_at": "2026-05-04T10:00:00Z",
  "restore_status": "auto_resumed",
  "mcp_connected": true,
  "last_mcp_disconnect_at": null,
  "last_mcp_reconnect_at": null,
  "interrupted_tasks_count": 0,
  "last_resume_required_at": null
}
```

### Files

- `/home/Bilirubin/.hermes/scripts/hermes_status.py`
- `/home/Bilirubin/.hermes/memory/state/system_status.md`

---

## 11. Acceptance Tests

### Test 1: Persistent Queue

```bash
# Send message while no task active
# Expected: appears in agent_inbox, gets classified
```

### Test 2: Long Task Interruption

```bash
# Start sample long-running task
# Send unrelated message during execution
# Expected:
#   - current task continues
#   - message queued as new_task
#   - no session reset
```

### Test 3: Append to Current

```bash
# Start task
# Send "добавь это к текущей задаче..."
# Expected:
#   - message attached_to_task
#   - current iteration continues
#   - task inbox updated
```

### Test 4: Cancel

```bash
# Send "стоп / останови"
# Expected:
#   - current task pauses safely
#   - checkpoint saved
#   - status = paused/cancelled
```

### Test 5: Gateway Restart

```bash
# Start sample task
# Restart hermes-gateway
# Expected:
#   - checkpoint restored
#   - task state restored
#   - no manual /resume required
```

### Test 6: brain-mcp Restart

```bash
# Restart brain-mcp
# Expected:
#   - MCP reconnects automatically
#   - gateway remains running
#   - task state preserved
```

### Test 7: Telegram Reset

```bash
# Expected:
#   - Telegram shows restored session automatically
#   - /resume is fallback only
```

### Test 8: Ralph-style Loop

```bash
# Run hermes_task_loop.py on sample task with 2 stories
# Expected:
#   - progress.md updated
#   - report created
#   - operator_standard_eval passes
#   - checkpoint saved
```

### Test 9: Runtime Health

```bash
# hermes_status.py includes runtime fields
```

### Test 10: Security

```bash
# Fake secret in inbound message is redacted
# secret-scan clean
```

### Test 11: Memory

```bash
# Operational restart observations are not promoted to canonical memory spam
# They are classified as operational_event/temporary unless incident
```

### Test 12: Final

```bash
# audit clean
# hygiene clean
# secret-scan clean
# operator_standard_eval passed
```

---

## 12. Symphony Design Note

**НЕ внедрять** Symphony-style multi-agent orchestration сейчас.

Создать только future design note:

`/home/Bilirubin/.hermes/memory/design/SYMPHONY_LIKE_ORCHESTRATION.md`

Описать:
- Когда оно понадобится
- Отличие от Ralph-style loop
- Возможная архитектура
- Prerequisites
- Почему сейчас не внедряем

---

## 13. Final Report Requirements

Финальный отчёт Phase 10.0 должен пройти Hermes Senior Operator Standard.

### Report Structure

```markdown
# Status
reliable_runtime_foundation_complete

# Context
Почему эта фаза была нужна.

# Diagnosis
Что ломалось:
- session reset
- manual /resume
- message interruption
- MCP reconnect issue

# Plan
Что было реализовано.

# Execution
Файлы, DB, services, timers.

# Proof
Acceptance tests with commands/results.

# Risks
Что остаётся ограничением.

# Rollback
Как откатить.

# Next Step
Phase 10 Observability + Memory Evals.
```

Также:
- Update deployment_status in Memory OS
- Run audit/hygiene/secret-scan
- Run operator_standard_eval.py on final report

---

## ✅ Phase 10.0 Complete Criteria

- ✅ Persistent inbox queue created
- ✅ Intake classifier implemented
- ✅ Task orchestrator working
- ✅ Ralph-style task workspace structure
- ✅ Checkpoint + auto resume working
- ✅ MCP auto-reconnect implemented
- ✅ Interruption policy enforced
- ✅ Background planner worker running
- ✅ Runtime health monitoring
- ✅ All acceptance tests pass
- ✅ No manual /resume required
- ✅ Documentation complete

---

## 📊 Status Label

After completion: `reliable_runtime_foundation_complete`

NOT: `production_ready` (that comes after observability)

---

## 🔜 Next Step

After Phase 10.0:

**Phase 10: Observability + Memory Evals**

---

**READY TO START** (после Phase 9.9)
