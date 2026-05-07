# 🧠 Phase 10.2: Cognitive Substrate — Always-On Graph Memory

**Date:** 2026-05-05  
**Status:** DESIGN  
**Priority:** P1 (after Phase 1 + Phase 2)  
**Philosophy:** Memory is not a tool. Memory is middleware.

---

## 🎯 Core Principle

> **No task can start without context pack.**

RAG должен быть не "кнопкой", а **обязательным слоем runtime** перед каждым действием.

```
User / n8n / cron / GitHub / Telegram
         ↓
    Task Intake
         ↓
Context Builder ← ОБЯЗАТЕЛЬНО (не опционально!)
         ↓
    Planner
         ↓
    Executor
         ↓
    Verifier
         ↓
Outcome Writer
         ↓
Graph Memory Update
```

---

## 🚫 Anti-Pattern: RAG as Tool

**ПЛОХО:**
```python
# Agent decides whether to search
if agent_thinks_memory_needed:
    memory.search(query)
```

**ХОРОШО:**
```python
# Runtime enforces context pack
def run_task(task):
    if not context_pack:
        raise RuntimeError("Task cannot start without context pack")
    
    context_pack = cognitive_substrate.build_context_pack(task)
    plan = planner.create_plan(task, context_pack)
    result = executor.execute(plan)
    verification = verifier.check(result)
    memory.write_outcome(task, plan, result, verification)
```

---

## 🏗️ Architecture: Cognitive Substrate

```
Hermes Runtime
  ├── Task Queue
  ├── Provider Router
  ├── Tool Executor
  ├── Checkpoint/Resume
  └── Cognitive Substrate ← NEW
        ├── Vector Memory (semantic search)
        ├── Graph Memory (relations, traversal)
        ├── Episode Memory (past executions)
        ├── Outcome Memory (success/failure lessons)
        ├── Playbook Memory (proven workflows)
        ├── Constraint Memory (user/project rules)
        └── Context Orchestrator (builds context packs)
```

---

## 📊 7-Level Memory Hierarchy

### L0: Raw Evidence

**Сырые источники (никакая память не живёт без evidence):**

- Logs
- Terminal output
- Code files
- Docs
- GitHub issues
- n8n executions
- Telegram commands
- Test results
- Prometheus alerts

**Schema:**
```sql
CREATE TABLE raw_evidence (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50),  -- 'log', 'file', 'command', 'alert'
    source_id VARCHAR(255),
    content TEXT,
    timestamp TIMESTAMPTZ,
    hash VARCHAR(64)
);
```

### L1: Chunks / Snippets

**Классический vector search:**

```sql
CREATE TABLE memory_chunks (
    chunk_id SERIAL PRIMARY KEY,
    evidence_id INT REFERENCES raw_evidence(id),
    text TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ,
    freshness_days INT,
    hash VARCHAR(64)
);

CREATE INDEX idx_chunks_embedding ON memory_chunks 
USING ivfflat (embedding vector_cosine_ops);
```

### L2: Entities

**Извлечённые сущности:**

```sql
CREATE TABLE entities (
    entity_id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    type VARCHAR(50),  -- Service, Provider, Model, File, Module, Error, Task, etc.
    properties JSONB,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    confidence FLOAT
);
```

**Примеры:**
- `Hermes Gateway` (Service)
- `OpenRouter` (Provider)
- `qwen/qwen3` (Model)
- `run_loop.py` (File)
- `agent_inbox` (Module)
- `HTTP_400` (Error)
- `task_queue` (Module)
- `S1` (Phase)

### L3: Relations

**Граф связей:**

```sql
CREATE TABLE relations (
    relation_id SERIAL PRIMARY KEY,
    from_entity_id INT REFERENCES entities(entity_id),
    to_entity_id INT REFERENCES entities(entity_id),
    relation_type VARCHAR(50),
    properties JSONB,
    evidence_id INT REFERENCES raw_evidence(id),
    confidence FLOAT,
    created_at TIMESTAMPTZ
);
```

**Типы связей:**
- `depends_on`
- `caused_by`
- `fixed_by`
- `failed_with`
- `blocked_by`
- `supersedes`
- `implemented_in`
- `configured_by`
- `tested_by`
- `observed_in`
- `owned_by`
- `related_to`

**Примеры:**
```cypher
(:Provider {name:"OpenRouter"})
  -[:FAILED_WITH]-> (:Error {type:"HTTP_400"})
  -[:CAUSED_BY]-> (:Cause {name:"incompatible fallback model"})
  -[:FIXED_BY]-> (:Playbook {name:"Capability-aware routing"})

(:Task {name:"S1"})
  -[:BLOCKS]-> (:Task {name:"S2"})

(:File {name:"run_loop.py"})
  -[:CONTAINS]-> (:Module {name:"provider_fallback_logic"})
```

### L4: Episodes

**История выполнения задач (самый важный слой для обучения):**

```sql
CREATE TABLE episodes (
    episode_id VARCHAR(50) PRIMARY KEY,
    goal TEXT,
    task_type VARCHAR(50),
    steps_taken JSONB,
    result VARCHAR(20),  -- 'success', 'failure', 'partial_success'
    tests_run JSONB,
    lessons JSONB,
    created_at TIMESTAMPTZ,
    duration_seconds INT
);

CREATE TABLE episode_entities (
    episode_id VARCHAR(50) REFERENCES episodes(episode_id),
    entity_id INT REFERENCES entities(entity_id),
    role VARCHAR(50)  -- 'touched', 'used', 'fixed', 'broke'
);
```

**Пример:**
```json
{
  "episode_id": "ep_2026_05_05_provider_fallback",
  "goal": "fix HTTP 400 fallback loop",
  "task_type": "code_repair",
  "steps_taken": [
    "inspected model catalog",
    "found incompatible fallback",
    "added capability-aware routing"
  ],
  "result": "partial_success",
  "tests": {
    "provider_routing_tests": "passed",
    "gateway_clean_start": "not_verified"
  },
  "lessons": [
    "fallback must validate capabilities before request",
    "unavailable/auth_failed provider must be selectable=false",
    "provider routing tests insufficient without runtime verification"
  ],
  "next_time": [
    "run provider probe",
    "verify gateway boot",
    "check logs for 400 loop"
  ]
}
```

### L5: Playbooks

**Проверенные workflow из успешных эпизодов:**

```sql
CREATE TABLE playbooks (
    playbook_id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    description TEXT,
    triggers JSONB,
    steps JSONB,
    required_tests JSONB,
    success_rate FLOAT,
    times_used INT,
    created_from_episode VARCHAR(50) REFERENCES episodes(episode_id)
);
```

**Пример:**
```yaml
playbook: Fix Provider Fallback Loop

triggers:
  - HTTP 400 after fallback
  - incompatible model selected
  - provider unavailable/auth_failed

steps:
  1. Check provider status
  2. Check model capability matrix
  3. Disable incompatible fallback
  4. Run targeted provider routing tests
  5. Verify clean gateway start
  6. Save outcome

required_tests:
  - test_provider_router.py
  - test_gateway_clean_start.sh

success_rate: 0.85
times_used: 3
```

### L6: Communities / Domains

**Верхний слой (GraphRAG community summaries):**

```sql
CREATE TABLE communities (
    community_id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    summary TEXT,
    entities INT[],  -- Array of entity_ids
    relations INT[],  -- Array of relation_ids
    updated_at TIMESTAMPTZ
);
```

**Примеры:**
- Provider Routing
- Task Runtime
- Memory System
- Monitoring
- n8n Integration
- Disk Hygiene
- Code Repair
- Telegram Agent

**Польза:** Отвечать на "глобальные" вопросы:
- "Что у нас вообще происходит с Hermes за последние две недели?"
- "Какие recurring failure patterns?"
- "Почему он всё ещё нестабилен?"

### L7: Meta-Knowledge

**Знание о знании:**

```sql
CREATE TABLE knowledge_status (
    knowledge_id SERIAL PRIMARY KEY,
    claim TEXT,
    status VARCHAR(20),  -- 'observed', 'inferred', 'verified', 'failed', 'deprecated', 'superseded'
    confidence FLOAT,
    evidence_ids INT[],
    verified_by VARCHAR(255),
    contradicted_by INT[],
    superseded_by INT,
    freshness_days INT,
    created_at TIMESTAMPTZ
);
```

**Статусы знания:**
- `observed` — видели в логах/файлах
- `inferred` — модель сделала вывод
- `verified` — подтверждено тестом/командой
- `failed` — попытка провалилась
- `deprecated` — больше не актуально
- `superseded` — заменено новым решением

**Приоритет доверия:**
```
verified > observed > inferred
fresh > old
test-backed > untested
project-specific > generic advice
```

---

## 🎯 Context Pack: Центральный Объект

**На каждую задачу Hermes собирает compact context pack:**

```json
{
  "context_pack_id": "ctx_2026_05_05_001",
  "task_id": "hms_001",
  "task_summary": "Fix provider fallback HTTP 400 loop",
  
  "relevant_constraints": [
    "Do not start S2 if S1 failed",
    "Do not expose secrets",
    "Do not simplify architecture without approval"
  ],
  
  "related_entities": [
    {"name": "provider_router", "type": "Module", "relevance": 0.95},
    {"name": "model_catalog", "type": "File", "relevance": 0.88},
    {"name": "OpenRouter", "type": "Provider", "relevance": 0.82},
    {"name": "NVIDIA", "type": "Provider", "relevance": 0.75},
    {"name": "qwen/qwen3", "type": "Model", "relevance": 0.70}
  ],
  
  "recent_episodes": [
    {
      "episode_id": "ep_2026_05_03_s1_failed",
      "title": "S1 failed due to agent_inbox.py indentation and missing table",
      "outcome": "failed",
      "lesson": "Do not continue to next phase until tests pass"
    }
  ],
  
  "known_failures": [
    "Fallback to incompatible model causes HTTP 400",
    "Gateway clean-start not verified"
  ],
  
  "recommended_playbooks": [
    {
      "name": "Provider Fallback Stabilization",
      "success_rate": 0.85,
      "steps": 5
    }
  ],
  
  "files_to_inspect": [
    "src/provider_router.py",
    "src/model_catalog.py",
    "src/gateway.py",
    "src/run_loop.py"
  ],
  
  "tools_that_helped": [
    "docker ps",
    "journalctl",
    "provider_probe",
    "test_provider_router.py"
  ],
  
  "retrieval_stats": {
    "vector_search_hits": 12,
    "graph_traversal_depth": 3,
    "episodes_found": 2,
    "constraints_applied": 3,
    "confidence": 0.82,
    "latency_ms": 145
  }
}
```

**Planner получает это ПЕРЕД любым reasoning.**

---

## 🔍 5 Retrieval Modes

### 1. Local Entity Retrieval

**Для точечных задач:**

```python
# Query: "Почему падает OpenRouter fallback?"

# Step 1: Vector search
similar_nodes = vector_search("OpenRouter fallback failure")

# Step 2: Graph traversal
graph_context = traverse_graph(
    start_nodes=similar_nodes,
    relations=['failed_with', 'caused_by', 'fixed_by'],
    max_depth=3
)

# Result:
# OpenRouter → failed_with → HTTP_400
# HTTP_400 → caused_by → incompatible_model
# incompatible_model → fixed_by → capability_aware_routing
```

### 2. Global Community Retrieval

**Для больших вопросов:**

```python
# Query: "Что у нас вообще с архитектурой Hermes?"

# Retrieve community summaries
communities = [
    "Provider Routing Summary",
    "Task Runtime Summary",
    "Memory System Summary",
    "Monitoring Summary"
]

# Build high-level context
```

### 3. Episode Retrieval

**Для задач "почини как в прошлый раз":**

```python
# Query: "Опять упала эта модель"

# Find similar episodes
episodes = search_episodes(
    filters={
        'result': ['failed', 'partial_success'],
        'entities': ['model', 'provider', 'fallback'],
        'recency_days': 30
    },
    limit=5
)

# Return lessons learned
```

### 4. Policy/Constraint Retrieval

**Для правил пользователя (высокий приоритет):**

```python
# Always retrieve constraints for task type
constraints = get_constraints(
    task_type='code_repair',
    priority='high'
)

# Examples:
# - Do not start S2 if S1 failed
# - Do not change fixed architecture without approval
# - Do not remove visualizations
# - Do not expose secrets
```

### 5. Tool Retrieval

**Какие tools помогали:**

```python
# Query: "gateway down"

# Find tools used in similar episodes
tools = search_tools(
    problem='gateway_down',
    success_rate_min=0.7
)

# Result:
# - docker ps
# - journalctl -u hermes-gateway
# - gateway_audit.log
# - provider_probe
# - prometheus query
```

---

## 🛠️ Context Orchestrator

**Новый компонент: `hermes/core/context_orchestrator.py`**

**Ответственность:**
1. Classify task type
2. Choose retrieval policy
3. Run vector retrieval
4. Run graph traversal
5. Fetch recent episodes
6. Fetch constraints
7. Compress context
8. Detect contradictions
9. Produce context pack

**Жёсткое правило:**
```python
if not context_pack:
    raise RuntimeError("Task cannot start without context pack")
```

**Или мягче:**
```python
if context_pack.confidence < threshold:
    planner_mode = "cautious"
    require_more_inspection = True
```

---

## 📋 Memory Policy Engine

**Каждый task type получает обязательную policy:**

```yaml
task_type: code_repair
context_policy:
  required:
    - user_constraints
    - related_files
    - recent_failures
    - similar_episodes
    - known_playbooks
  optional:
    - global_architecture_summary
    - cost_history
  max_tokens: 12000
  freshness_days: 30
  min_confidence: 0.65

task_type: provider_fix
context_policy:
  required:
    - provider_capabilities
    - recent_provider_errors
    - model_catalog
    - fallback_decisions
    - test_results
  max_tokens: 16000
  freshness_days: 14
  min_confidence: 0.70

task_type: n8n_workflow
context_policy:
  required:
    - n8n_workflow_catalog
    - webhook_contracts
    - approval_policy
    - related_tasks
  max_tokens: 10000
  freshness_days: 60
  min_confidence: 0.60
```

**Hermes не спрашивает "искать в памяти?" — он обязан это сделать.**

---

## 🔄 Execution Flow with Cognitive Substrate

```python
def run_task(task):
    # 1. Intake
    task = intake.normalize(task)
    
    # 2. Context Builder (ОБЯЗАТЕЛЬНО!)
    context_pack = cognitive_substrate.build_context_pack(task)
    
    if not context_pack:
        raise RuntimeError("Cannot start task without context pack")
    
    # 3. Planner (with context)
    plan = planner.create_plan(task, context_pack)
    
    # 4. Executor
    result = executor.execute(plan, context_pack)
    
    # 5. Verifier
    verification = verifier.check(result)
    
    # 6. Outcome Writer (ОБЯЗАТЕЛЬНО!)
    episode = memory.write_outcome(
        task=task,
        context_pack=context_pack,
        plan=plan,
        result=result,
        verification=verification
    )
    
    # 7. Graph Update
    memory.update_graph(episode)
    
    return result
```

---

## 📝 Outcome Writer: Learning from Own Outputs

**После каждой задачи сохраняем обучающий след:**

```json
{
  "episode_id": "ep_2026_05_05_001",
  "task_id": "hms_001",
  "goal": "Fix provider fallback",
  
  "context_used": [
    "episode:provider_fallback_2026_05_03",
    "playbook:capability_aware_routing",
    "constraint:do_not_start_s2_if_s1_failed"
  ],
  
  "actions": [
    "patched model catalog",
    "disabled invalid fallback",
    "ran tests"
  ],
  
  "result": "partial_success",
  
  "failure_reason": "gateway clean-start not verified",
  
  "lesson": "Provider routing tests are insufficient without runtime clean-start verification",
  
  "next_time": [
    "run provider probe",
    "verify gateway boot",
    "check logs for 400 loop"
  ],
  
  "verification": {
    "tests_passed": ["test_provider_router.py"],
    "tests_failed": [],
    "tests_skipped": ["test_gateway_clean_start.sh"]
  },
  
  "confidence": 0.6,
  "status": "unverified"
}
```

**Память критична к себе:**
- `confidence` — уверенность
- `evidence` — доказательства
- `status` — статус знания
- `verified_by` — кем/чем подтверждено
- `superseded_by` — заменено чем

---

## 🎓 How Weak Model Becomes Strong

### Without Cognitive Substrate

```
Weak model: "Try restarting service"
```

### With Cognitive Substrate

```
Context Pack:
- Last restart did not help
- HTTP 400 caused by incompatible fallback model
- S1 rule: do not start S2 if S1 failed
- Relevant file: agent_inbox.py line 58
- DB table agent_inbox missing
- Playbook: run migration before tests
- Previous failure: report file missing

Weak model: 
"First fix indentation in agent_inbox.py line 58,
then run migration to create agent_inbox table,
then run test_agent_inbox.py,
then generate S1 report.
Do not start S2 until all tests pass."
```

**Вот это уже реально мощно.**

---

## 📊 Implementation Plan

### MVP 1: Context Pack Before Every Task

**Goal:** No task starts without context pack

**Tasks:**
1. Create `context_orchestrator.py`
2. Define `ContextPack` schema
3. Implement basic retrieval (constraints + episodes)
4. Enforce context pack in task runner
5. Add logging: `context_pack_id`, `retrieved_memories_count`

**Success Criteria:**
- ✅ 100% of tasks have `context_pack_id`
- ✅ Logs show retrieved memories
- ✅ Task fails if context pack missing

**Time:** 2 days

---

### MVP 2: Outcome Writer After Every Task

**Goal:** Every completed task writes episode + outcome

**Tasks:**
1. Create `outcome_writer.py`
2. Define `Episode` schema
3. Implement outcome extraction
4. Save lessons learned
5. Link to entities/files/tools

**Success Criteria:**
- ✅ 100% of completed tasks write episode
- ✅ Episodes have lessons
- ✅ Episodes link to entities

**Time:** 2 days

---

### MVP 3: Graph Traversal on Top of Vector Search

**Goal:** Not just "find similar text", but "understand relations"

**Tasks:**
1. Implement entity extraction
2. Implement relation extraction
3. Build graph traversal retriever
4. Combine vector + graph results
5. Compress to context pack

**Success Criteria:**
- ✅ Context pack includes graph-traversed entities
- ✅ Context pack includes related playbooks
- ✅ Context pack includes constraints

**Time:** 3 days

---

### MVP 4: Memory Policy Engine

**Goal:** Each task type has mandatory retrieval policy

**Tasks:**
1. Define task type taxonomy
2. Create retrieval policies per task type
3. Implement policy enforcement
4. Add policy validation

**Success Criteria:**
- ✅ All task types have policy
- ✅ Policy enforced automatically
- ✅ Logs show policy applied

**Time:** 1 day

---

### MVP 5: n8n Event Intake

**Goal:** n8n events become raw evidence

**Tasks:**
1. Create n8n → Hermes event webhook
2. Normalize n8n events
3. Store as raw evidence
4. Extract entities from events
5. Update graph

**Success Criteria:**
- ✅ n8n executions stored as evidence
- ✅ Entities extracted from n8n events
- ✅ Graph updated from n8n

**Time:** 2 days

---

## 📊 Metrics

**Context Pack Metrics:**
```
context_pack_created_total
context_pack_empty_total
memory_retrieval_latency_ms
retrieved_nodes_count
retrieved_edges_count
retrieved_episodes_count
constraints_applied_count
```

**Outcome Metrics:**
```
memory_write_success_total
outcome_verified_total
episode_created_total
lessons_learned_total
```

**Quality Metrics:**
```
stale_memory_used_total
contradiction_detected_total
tasks_without_context_pack_total  # MUST BE 0
```

---

## 🚦 Success Criteria

### Phase 10.2 Complete When:

1. ✅ 100% of tasks have `context_pack_id`
2. ✅ 100% of completed tasks write outcome memory
3. ✅ Hermes retrieves similar past episodes automatically
4. ✅ Hermes applies user/project constraints without being prompted
5. ✅ Hermes can explain which memories influenced a decision
6. ✅ Stale or unverified memories are marked as such
7. ✅ Failed tasks become reusable lessons
8. ✅ `tasks_without_context_pack_total = 0`

---

## 🎯 Integration with Existing Phases

### Phase 1 (Week 1): Stop the Bleeding
- Focus: Stability
- Memory: Not yet

### Phase 2 (Week 2): Make it Observable
- Focus: Metrics
- Memory: Start collecting raw evidence

### Phase 3 (Week 3+): Make it Maintainable
- Focus: Clean code
- Memory: Not yet

### **Phase 10.2 (Week 4-5): Cognitive Substrate**
- Focus: Always-on memory
- Memory: **CORE FEATURE**

---

## 📚 References

### GraphRAG Approaches

1. **Microsoft GraphRAG**
   - Graph structures + hierarchical communities
   - Community summaries for global questions
   - Dual-level retrieval (local + global)

2. **Neo4j GraphRAG**
   - Vector search + graph traversal
   - `VectorCypherRetriever`: vector → graph expansion

3. **LightRAG**
   - Dual-level retrieval
   - Low-level + high-level knowledge extraction

4. **DRIFT Search**
   - Local entities + community context
   - Combines focused and broad retrieval

---

## ✨ Summary

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

**Если этот цикл появится, Hermes реально начнёт вести себя как система, которая помнит, учится и не просит каждый раз объяснять, что уже было.**

---

**Status:** DESIGN APPROVED  
**Priority:** P1 (after Phase 1 + Phase 2 stable)  
**Estimated:** 2 weeks (10 days)  
**Dependencies:** Phase 1 complete, Phase 2 complete

**Next:** Implement after Week 2 (observability) complete

