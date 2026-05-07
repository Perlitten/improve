# 🧠 n8n Integration Design: Peripheral Nervous System

**Date:** 2026-05-06  
**Status:** DESIGN APPROVED  
**Philosophy:** Hermes = Brain, n8n = Hands/Sensors

---

## 🎯 Core Principle

> **Hermes thinks. n8n executes.**

```
External World (Telegram, Gmail, GitHub, Webhooks, Cron, APIs)
         ↓
    n8n (event intake, integrations, approvals, notifications)
         ↓
Hermes Gateway (task creation, routing, memory, checkpoints)
         ↓
Hermes Runtime (planner → executor → verifier → memory learning)
         ↓
    Tools (code sandbox, shell, browser, repo, db, MCP, n8n workflows)
```

---

## 🚫 Anti-Pattern: n8n as Competing Agent

**DON'T:**
```
n8n AI Agent → decides everything → calls LLM → breaks
```

**DO:**
```
n8n → normalizes event → Hermes task → Hermes decides → n8n executes
```

---

## 🏗️ Architecture

### Responsibility Split

**Hermes Owns:**
- Task queue
- Checkpoints
- Provider routing
- Memory
- Learning
- Execution state
- Cost tracking
- Tool policy
- Code repair runtime
- Reasoning

**n8n Owns:**
- External triggers (Telegram, Gmail, GitHub, etc.)
- Webhook intake
- Notifications (Telegram, Slack, Email)
- Human approvals
- Scheduled triggers (cron)
- Low-risk external API workflows
- Event normalization

---

## 🔄 Integration Patterns

### Pattern 1: n8n → Hermes (Event Intake)

**Flow:**
```
External event → n8n → normalize → POST /hermes/tasks/from-n8n → task created
```

**Example:**
```json
// Telegram message arrives
{
  "source": "n8n",
  "workflow": "telegram_inbound",
  "event_type": "message.received",
  "priority": "normal",
  "user_id": "andrei",
  "payload": {
    "text": "Check why gateway crashed",
    "attachments": []
  }
}

// Hermes creates task
{
  "task_id": "hms_2026_05_06_001",
  "status": "queued",
  "source": "n8n.telegram",
  "checkpoint": "created"
}
```

### Pattern 2: Hermes → n8n (Tool Execution)

**Flow:**
```
Hermes needs notification → calls n8n tool → n8n executes → returns result
```

**Example:**
```python
# Hermes calls n8n tool
result = call_tool("n8n.telegram.send_message", {
    "chat_id": "andrei",
    "text": "Gateway restarted successfully",
    "parse_mode": "Markdown"
})
```

### Pattern 3: Hermes ↔ n8n (Human Approval)

**Flow:**
```
Hermes needs approval → n8n sends buttons → user clicks → n8n callback → Hermes resumes
```

**Example:**
```json
// Hermes requests approval
{
  "action": "restart_service",
  "risk": "medium",
  "summary": "Restart hermes-gateway after config change",
  "approve_options": ["approve", "reject", "modify"]
}

// n8n sends Telegram buttons
// User clicks "approve"

// n8n callback to Hermes
{
  "task_id": "hms_2026_05_06_001",
  "approval": "approved",
  "approved_by": "andrei",
  "timestamp": "2026-05-06T10:30:00Z"
}

// Hermes resumes from checkpoint
```

---

## 📋 Standard Task Schema

**All n8n → Hermes events must use this schema:**

```json
{
  "task_id": null,
  "source": "n8n",
  "source_workflow": "telegram_inbound",
  "actor": "andrei",
  "type": "user_request",
  "priority": "normal",
  "requires_approval": false,
  "input": {
    "text": "Fix provider fallback",
    "files": [],
    "links": []
  },
  "constraints": {
    "do_not_start_s2_if_s1_failed": true,
    "no_secrets_in_logs": true
  },
  "callback": {
    "url": "https://n8n.../webhook/hermes-callback",
    "events": ["completed", "failed", "needs_approval"]
  }
}
```

---

## 🛠️ n8n Tool Registry

**n8n workflows exposed as Hermes tools:**

```yaml
tools:
  - name: n8n.telegram.send_message
    input_schema:
      chat_id: string
      text: string
      parse_mode: Markdown
    output_schema:
      ok: boolean
      message_id: string
      error: string|null
    risk_level: low
    
  - name: n8n.human.request_approval
    input_schema:
      action: string
      risk: low|medium|high
      summary: string
      options: array
    output_schema:
      approved: boolean
      approved_by: string
      timestamp: string
    risk_level: low
    
  - name: n8n.gmail.search
    input_schema:
      query: string
      max_results: number
    output_schema:
      messages: array
      count: number
    risk_level: low
    
  - name: n8n.notion.create_page
    input_schema:
      database_id: string
      properties: object
    output_schema:
      page_id: string
      url: string
    risk_level: low
```

---

## 🚀 MVP: 5 Essential Workflows

### Workflow 1: telegram_inbound_to_hermes

**Trigger:** Telegram message  
**Action:** Create Hermes task  
**Priority:** P0

```
Telegram message
  ↓
n8n receives
  ↓
Normalize payload
  ↓
POST /hermes/tasks/from-n8n
  ↓
Hermes creates task
  ↓
n8n sends "Task accepted: hms_xxx"
```

### Workflow 2: hermes_to_telegram_notify

**Trigger:** Hermes webhook  
**Action:** Send Telegram notification  
**Priority:** P0

```
Hermes completes task
  ↓
POST n8n webhook
  ↓
n8n sends Telegram message
```

### Workflow 3: human_approval_request

**Trigger:** Hermes approval request  
**Action:** Send approval buttons, wait for response  
**Priority:** P0

```
Hermes needs approval
  ↓
n8n sends buttons
  ↓
User clicks
  ↓
n8n callback to Hermes
  ↓
Hermes resumes
```

### Workflow 4: cron_self_monitor

**Trigger:** Schedule (every 15 min)  
**Action:** Create self-monitor task  
**Priority:** P1

```
Cron trigger
  ↓
POST /hermes/tasks/from-n8n
  {
    "type": "self_monitor",
    "priority": "low"
  }
```

### Workflow 5: memory_ingest_external

**Trigger:** New doc/email/file  
**Action:** Ingest to Hermes memory  
**Priority:** P2

```
New content
  ↓
n8n extracts metadata
  ↓
Hermes decides whether to ingest
  ↓
Hermes chunks/embeds/stores
```

---

## 🔌 API Endpoints

### Hermes → n8n

```
POST /api/hermes/tasks/from-n8n
POST /api/hermes/n8n/callback
POST /api/hermes/n8n/approval-result
GET  /api/hermes/tools/n8n
POST /api/hermes/tools/n8n/{tool_name}/execute
```

### n8n → Hermes

```
POST /n8n/webhook/hermes-callback
POST /n8n/webhook/approval-request
POST /n8n/webhook/task-status
```

---

## 📦 Implementation Structure

```
hermes/integrations/n8n/
├── __init__.py
├── client.py              # n8n API client
├── tool_registry.py       # n8n tools as Hermes tools
├── schemas.py             # Standard task schema
├── callbacks.py           # Webhook handlers
├── workflow_catalog.py    # Available workflows
└── approval.py            # Approval flow
```

---

## 🎯 Success Criteria

### Phase 10.1: n8n Organic Integration

**Deliverables:**
1. ✅ Standard n8n → Hermes task schema
2. ✅ Hermes callback API for n8n
3. ✅ n8n tool registry in Hermes
4. ✅ Telegram inbound workflow
5. ✅ Telegram notification workflow
6. ✅ Human approval workflow
7. ✅ Self-monitor cron workflow
8. ✅ Memory ingest workflow

**Success Criteria:**
- ✅ Telegram command creates persistent Hermes task
- ✅ Hermes task survives restart
- ✅ Hermes can request approval through n8n
- ✅ Hermes resumes after approval
- ✅ Hermes can call at least 3 n8n tools
- ✅ All n8n executions logged against Hermes task_id
- ✅ n8n does NOT own reasoning or task state

---

## 🧪 Vertical Slice Test

**End-to-end scenario:**

```
1. User sends Telegram: "Check why gateway crashed"
   ↓
2. n8n receives message
   ↓
3. Hermes creates task (hms_001)
   ↓
4. Hermes reads logs
   ↓
5. Hermes checks docker services
   ↓
6. Hermes builds summary
   ↓
7. Hermes needs restart → requests approval via n8n
   ↓
8. n8n sends Telegram buttons
   ↓
9. User clicks "Approve"
   ↓
10. n8n callback to Hermes
    ↓
11. Hermes restarts service
    ↓
12. Hermes checks health
    ↓
13. Hermes saves outcome to memory
    ↓
14. Hermes sends final report via n8n
```

**This is the gold standard.**

---

## 🚨 Security Boundaries

**n8n CANNOT:**
- Execute shell commands directly
- Access production database directly
- Modify Hermes config
- Delete data
- Deploy code
- Restart services without approval

**n8n CAN:**
- Create tasks
- Send notifications
- Request approvals
- Call safe external APIs
- Trigger scheduled checks

---

## 📊 Observability

**All n8n → Hermes interactions must be logged:**

```json
{
  "timestamp": "2026-05-06T10:30:00Z",
  "source": "n8n",
  "workflow": "telegram_inbound",
  "task_id": "hms_001",
  "event": "task_created",
  "actor": "andrei",
  "payload_size": 256
}
```

**Metrics:**
- `n8n_tasks_created_total`
- `n8n_approvals_requested_total`
- `n8n_approvals_approved_total`
- `n8n_notifications_sent_total`
- `n8n_workflow_execution_duration_seconds`

---

## 🎓 Weak Model → Strong Agent

**How n8n + Hermes runtime makes weak models powerful:**

```
Weak LLM alone:
"Maybe restart the service?"

Weak LLM + Hermes runtime:
1. Check logs (via tool)
2. Check Prometheus (via tool)
3. Find recent errors (via memory)
4. Check config (via tool)
5. Build hypothesis
6. Generate patch
7. Run tests (via tool)
8. If tests pass → request approval (via n8n)
9. If approved → apply patch
10. Save outcome to memory
```

**This is Claude Code-like behavior from a weak model.**

---

## 📝 Implementation Phases

### Phase 1: Foundation (Week 2)

- [ ] Create n8n integration module
- [ ] Implement standard task schema
- [ ] Create Hermes callback API
- [ ] Build n8n tool registry

### Phase 2: MVP Workflows (Week 3)

- [ ] Telegram inbound workflow
- [ ] Telegram notification workflow
- [ ] Human approval workflow

### Phase 3: Advanced (Week 4+)

- [ ] Cron self-monitor workflow
- [ ] Memory ingest workflow
- [ ] Gmail integration
- [ ] GitHub integration

---

## ✅ Decision

**n8n is NOT dead code.**  
**n8n is the peripheral nervous system.**

**Hermes = Brain**  
**n8n = Hands, Eyes, Ears**

---

**Status:** DESIGN APPROVED  
**Next:** Implement after Week 1 stabilization complete  
**Priority:** P1 (after task queue + checkpoint/resume)
