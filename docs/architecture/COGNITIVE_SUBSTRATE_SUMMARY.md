# 🧠 Cognitive Substrate: Executive Summary

**TL;DR:** Memory is not a tool. Memory is middleware.

---

## 🎯 Core Idea

**No task can start without context pack.**

RAG должен быть не "кнопкой /memory search", а **обязательным слоем runtime** перед каждым действием.

---

## 🏗️ Architecture Change

### Before (Bad)

```
Task → Planner → Executor → Done
```

Agent decides whether to search memory.

### After (Good)

```
Task → Context Builder (ОБЯЗАТЕЛЬНО) → Planner → Executor → Verifier → Outcome Writer → Graph Update
```

Runtime enforces context pack.

---

## 📊 7-Level Memory Hierarchy

```
L0: Raw Evidence (logs, files, commands, alerts)
L1: Chunks (vector search)
L2: Entities (services, providers, models, files, errors)
L3: Relations (caused_by, fixed_by, failed_with, blocked_by)
L4: Episodes (past task executions with lessons)
L5: Playbooks (proven workflows from successful episodes)
L6: Communities (high-level domains: Provider Routing, Task Runtime, etc.)
L7: Meta-Knowledge (confidence, verification status, freshness)
```

---

## 🎯 Context Pack

**Every task gets:**

```json
{
  "task_summary": "Fix provider fallback",
  "relevant_constraints": ["Do not start S2 if S1 failed"],
  "related_entities": ["provider_router", "OpenRouter", "HTTP_400"],
  "recent_episodes": [{"lesson": "Fallback must validate capabilities"}],
  "known_failures": ["Incompatible model causes HTTP 400"],
  "recommended_playbooks": ["Provider Fallback Stabilization"],
  "files_to_inspect": ["provider_router.py"],
  "tools_that_helped": ["docker ps", "journalctl"],
  "retrieval_confidence": 0.82
}
```

---

## 🔍 5 Retrieval Modes

1. **Local Entity Retrieval** — точечные задачи (OpenRouter → HTTP_400 → fixed_by → playbook)
2. **Global Community Retrieval** — большие вопросы ("что вообще с архитектурой?")
3. **Episode Retrieval** — "почини как в прошлый раз"
4. **Policy/Constraint Retrieval** — правила пользователя (высокий приоритет)
5. **Tool Retrieval** — какие tools помогали

---

## 🔄 Execution Flow

```python
def run_task(task):
    # 1. Intake
    task = intake.normalize(task)
    
    # 2. Context Builder (ОБЯЗАТЕЛЬНО!)
    context_pack = cognitive_substrate.build_context_pack(task)
    if not context_pack:
        raise RuntimeError("Cannot start without context pack")
    
    # 3. Planner (with context)
    plan = planner.create_plan(task, context_pack)
    
    # 4. Executor
    result = executor.execute(plan, context_pack)
    
    # 5. Verifier
    verification = verifier.check(result)
    
    # 6. Outcome Writer (ОБЯЗАТЕЛЬНО!)
    episode = memory.write_outcome(task, context_pack, plan, result, verification)
    
    # 7. Graph Update
    memory.update_graph(episode)
```

---

## 📋 Memory Policy Engine

**Each task type has mandatory retrieval policy:**

```yaml
task_type: code_repair
context_policy:
  required:
    - user_constraints
    - related_files
    - recent_failures
    - similar_episodes
    - known_playbooks
  max_tokens: 12000
  freshness_days: 30
  min_confidence: 0.65
```

**Hermes не спрашивает "искать в памяти?" — он обязан это сделать.**

---

## 🎓 How Weak Model Becomes Strong

### Without Cognitive Substrate

```
Weak model: "Try restarting service"
```

### With Cognitive Substrate

```
Context:
- Last restart did not help
- HTTP 400 caused by incompatible fallback
- S1 rule: do not start S2 if S1 failed
- Relevant file: agent_inbox.py line 58
- Playbook: run migration before tests

Weak model:
"First fix indentation, then run migration,
then run tests, then generate report.
Do not start S2 until tests pass."
```

**Вот это уже мощно.**

---

## 📊 Implementation Plan

### MVP 1: Context Pack Before Every Task (2 days)
- Create `context_orchestrator.py`
- Enforce context pack in task runner
- 100% of tasks have `context_pack_id`

### MVP 2: Outcome Writer After Every Task (2 days)
- Create `outcome_writer.py`
- Every completed task writes episode + lessons
- Episodes link to entities/files/tools

### MVP 3: Graph Traversal (3 days)
- Entity extraction
- Relation extraction
- Graph traversal retriever
- Combine vector + graph

### MVP 4: Memory Policy Engine (1 day)
- Define task type taxonomy
- Create retrieval policies
- Enforce policies

### MVP 5: n8n Event Intake (2 days)
- n8n → Hermes event webhook
- Store as raw evidence
- Extract entities from events

**Total:** 10 days (2 weeks)

---

## 🚦 Success Criteria

1. ✅ 100% of tasks have `context_pack_id`
2. ✅ 100% of completed tasks write outcome memory
3. ✅ Hermes retrieves similar past episodes automatically
4. ✅ Hermes applies user/project constraints without being prompted
5. ✅ Hermes can explain which memories influenced a decision
6. ✅ Stale or unverified memories are marked as such
7. ✅ Failed tasks become reusable lessons
8. ✅ `tasks_without_context_pack_total = 0`

---

## 📊 Metrics

```
context_pack_created_total
memory_retrieval_latency_ms
retrieved_episodes_count
constraints_applied_count
outcome_verified_total
tasks_without_context_pack_total  # MUST BE 0
```

---

## 🎯 Integration with Phases

- **Phase 1 (Week 1):** Stop bleeding — no memory yet
- **Phase 2 (Week 2):** Observability — start collecting raw evidence
- **Phase 3 (Week 3):** Maintainability — clean code
- **Phase 4 (Week 4-5):** Cognitive Substrate — **MEMORY IS CORE**

---

## ✨ Key Insight

**Hermes не должен "иметь RAG". Hermes должен быть построен поверх RAG-графа.**

**Идеальная формула:**
```
Task Runtime
+ Always-On Context Pack
+ Graph Memory
+ Episode Learning
+ n8n Event Intake
+ Tool/Model Router
+ Verifier
= Внешний мозг
```

**Самое важное — встроить память в execution path:**
```
intake → context → plan → act → verify → learn
```

---

**Full Spec:** [PHASE_10_2_COGNITIVE_SUBSTRATE.md](PHASE_10_2_COGNITIVE_SUBSTRATE.md)  
**Execution Plan:** [REALISTIC_EXECUTION_PLAN.md](REALISTIC_EXECUTION_PLAN.md)

**Status:** DESIGN APPROVED  
**Priority:** P1 (after Phase 1 + Phase 2)  
**Estimated:** 2 weeks

