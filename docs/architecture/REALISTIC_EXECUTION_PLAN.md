# 🎯 Realistic Execution Plan: Grounded & Gated

**Date:** 2026-05-06  
**Philosophy:** Execute Phase 1 ONLY. Phase 2 starts ONLY after Phase 1 is verified green.  
**Discipline:** "S1 failed. Do not start S2."

---

## 🚨 Critical Insight

> "Built a chat interface when we needed a task runtime."

This is the root cause. Everything else is symptoms.

---

## 📊 Priority Classification

### P0: Stop the Bleeding (MUST FIX NOW)

1. **Provider routing crashes system** → HTTP 400 loops
2. **Work lost on restart** → No task queue
3. **Disk full** → 80% usage, no cleanup
4. **Config chaos** → 5+ config files, conflicts

### P1: Make it Observable (MUST FIX NEXT)

1. **No cost tracking** → Budget unknown
2. **Monitoring duplication** → 5 systems, confusion
3. **No clear metrics** → Can't measure stability

### P2: Make it Maintainable (FIX LATER)

1. **Monolithic modules** → run_loop.py (233KB)
2. **Dead code** → n8n workflows, NIM, duplicates
3. **Low test coverage** → ~5%
4. **Memory learning** → Not using outcomes

---

## 🎯 Phase 1: Stop the Bleeding (Week 1)

**Goal:** System does not crash and does not lose work.

**Duration:** 5 days  
**Gate:** ALL P0 issues resolved + verified by tests + 7 days uptime

### Day 1: Provider Routing Fix ✅ COMPLETE

**Status:** DONE  
**Deliverables:**
- ✅ Capability-aware routing
- ✅ HTTP 400 handler (no retry loop)
- ✅ Rate limit handler (pause and retry)
- ✅ Safe mode (pause, don't crash)
- ✅ Test framework (14 tests)

### Day 2: Task Queue Foundation

**Goal:** Tasks persist in database, survive restarts

**Tasks:**

1. **Create database schema** (2 hours)
   ```sql
   CREATE TABLE agent_inbox (
     id SERIAL PRIMARY KEY,
     message_text TEXT NOT NULL,
     source VARCHAR(50) NOT NULL,
     priority INT DEFAULT 5,
     status VARCHAR(20) DEFAULT 'pending',
     created_at TIMESTAMPTZ DEFAULT NOW(),
     processed_at TIMESTAMPTZ
   );
   
   CREATE TABLE agent_tasks (
     id SERIAL PRIMARY KEY,
     inbox_id INT REFERENCES agent_inbox(id),
     task_type VARCHAR(50) NOT NULL,
     task_data JSONB NOT NULL,
     status VARCHAR(20) DEFAULT 'queued',
     checkpoint_data JSONB,
     started_at TIMESTAMPTZ,
     completed_at TIMESTAMPTZ,
     error_message TEXT
   );
   
   CREATE INDEX idx_inbox_status ON agent_inbox(status, priority DESC);
   CREATE INDEX idx_tasks_status ON agent_tasks(status);
   ```

2. **Implement TaskOrchestrator** (4 hours)
   ```python
   class TaskOrchestrator:
       def enqueue(self, message, source, priority=5) -> int
       def dequeue(self) -> dict
       def checkpoint(self, task_id, state)
       def resume(self, task_id) -> dict
       def complete(self, task_id, result)
   ```

3. **Write tests** (2 hours)
   - 20+ tests for TaskOrchestrator
   - Test enqueue/dequeue
   - Test checkpoint/resume
   - Test restart recovery

**Success Criteria:**
- ✅ Schema created
- ✅ TaskOrchestrator works
- ✅ Tests pass
- ✅ Task survives restart

### Day 3: Config Consolidation

**Goal:** Single source of truth for config

**Tasks:**

1. **Audit all configs** (1 hour)
   - Document all config locations
   - Identify conflicts
   - Map dependencies

2. **Create unified config** (2 hours)
   ```yaml
   # ~/.hermes/config.yaml
   
   hermes:
     home: /home/Bilirubin/.hermes
     log_level: INFO
     
   providers:
     openrouter:
       api_key: ${OPENROUTER_API_KEY}
     nvidia:
       api_key: ${NVIDIA_API_KEY}
       
   models:
     primary:
       model: anthropic/claude-sonnet-4
       max_cost_per_task: 0.50
     fallback:
       - nvidia/nemotron-3-super-120b-a12b:free
       
   task_queue:
     max_concurrent: 2
     checkpoint_interval: 60
     
   cost_tracking:
     enabled: true
     daily_budget: 10.00
   ```

3. **Migrate configs** (2 hours)
   - Backup old configs
   - Apply new config
   - Validate
   - Test services

4. **Write tests** (1 hour)
   - Config loading tests
   - Validation tests

**Success Criteria:**
- ✅ Single config file
- ✅ All settings migrated
- ✅ Services restart successfully
- ✅ Tests pass

### Day 4: Disk Cleanup

**Goal:** Free space, prevent future issues

**Tasks:**

1. **Analyze disk usage** (30 min)
   ```bash
   du -h /home/Bilirubin/.hermes | sort -rh | head -20
   du -h /var/log | sort -rh | head -20
   ```

2. **Clean up** (1 hour)
   ```bash
   # Remove old logs (> 30 days)
   find /home/Bilirubin/.hermes/logs -name "*.log" -mtime +30 -delete
   
   # Archive old backups (> 7 days)
   find /home/Bilirubin/.hermes/backups -name "*.tar.gz" -mtime +7 \
     -exec mv {} /home/Bilirubin/.hermes/backups/archive/ \;
   ```

3. **Set up automatic cleanup** (1 hour)
   ```bash
   # Logrotate
   cat > /etc/logrotate.d/hermes <<EOF
   /home/Bilirubin/.hermes/logs/*.log {
       daily
       rotate 30
       compress
       missingok
   }
   EOF
   
   # Cron cleanup
   cat > /etc/cron.daily/hermes-cleanup <<EOF
   #!/bin/bash
   find /home/Bilirubin/.hermes/temp -mtime +7 -delete
   EOF
   ```

4. **Verify** (30 min)
   - Check disk usage < 70%
   - Verify logrotate works
   - Verify cron works

**Success Criteria:**
- ✅ Disk usage < 70%
- ✅ Automatic cleanup configured
- ✅ No manual intervention needed

### Day 5: Archive Dead Code

**Goal:** Remove noise, reduce confusion

**Tasks:**

1. **Archive n8n workflows** (30 min)
   ```bash
   mkdir -p hermes/archive/n8n-workflows
   # Export workflows
   psql -U automation -d n8n -c \
     "COPY (SELECT * FROM workflow_entity) TO '/tmp/n8n_backup.csv' CSV HEADER;"
   mv /tmp/n8n_backup.csv hermes/archive/n8n-workflows/
   
   # Create ARCHIVE_REASON.md
   echo "Archived 2026-05-06. Reason: inactive. Will be reintegrated as peripheral nervous system in Phase 10.1." \
     > hermes/archive/n8n-workflows/ARCHIVE_REASON.md
   ```

2. **Archive NIM orchestrator** (15 min)
   ```bash
   mv hermes/nim hermes/archive/nim-orchestrator
   echo "Archived 2026-05-06. Reason: experimental, not production." \
     > hermes/archive/nim-orchestrator/ARCHIVE_REASON.md
   ```

3. **Archive duplicate scripts** (30 min)
   ```bash
   mkdir -p hermes/archive/duplicate-health-checks
   # Move duplicate health check scripts
   ```

4. **Update documentation** (30 min)
   - Update README
   - Update .hermes.md
   - Document what was archived and why

**Success Criteria:**
- ✅ Dead code archived (not deleted)
- ✅ ARCHIVE_REASON.md for each
- ✅ Documentation updated
- ✅ No broken references

---

## 🚦 Phase 1 Gate: Verification

**Phase 2 starts ONLY if ALL criteria met:**

### Automated Checks

```bash
# 1. No HTTP 400 loops in last 7 days
sudo journalctl -u hermes-gateway --since "7 days ago" | \
  grep -i "HTTP 400\|single tool" | wc -l
# Expected: 0

# 2. Task queue works
psql -U automation -d rag -c "SELECT count(*) FROM agent_inbox;"
# Expected: > 0

# 3. Tasks survive restart
sudo systemctl restart hermes-gateway
sleep 10
psql -U automation -d rag -c "SELECT count(*) FROM agent_tasks WHERE status='queued';"
# Expected: tasks still queued

# 4. Disk usage < 70%
df -h | grep -E "/$|/home" | awk '{print $5}' | sed 's/%//'
# Expected: < 70

# 5. Config loads
python3 -c "import yaml; yaml.safe_load(open('/home/Bilirubin/.hermes/config.yaml'))"
# Expected: no errors

# 6. Tests pass
cd hermes && pytest tests/unit -v
# Expected: all pass
```

### Manual Verification

- [ ] Gateway runs for 7 days without manual restart
- [ ] No provider fallback crashes
- [ ] Tasks persist across restarts
- [ ] Config is single source of truth
- [ ] Disk usage stable < 70%
- [ ] Dead code archived with reasons

### Metrics

- **Uptime:** 7 days continuous
- **Failed tasks:** 0 due to provider errors
- **Disk usage:** < 70%
- **Test coverage:** > 60%

---

## 🎯 Phase 2: Make it Observable (Week 2)

**ONLY START IF PHASE 1 GATE PASSED**

**Goal:** Understand what's happening

**Duration:** 5 days  
**Gate:** Metrics dashboard + cost tracking + 14 days uptime

### Day 6: Cost Tracking

**Goal:** Track cost per task

**Tasks:**

1. **Add cost calculation** (2 hours)
   ```python
   def calculate_cost(model: str, tokens: int) -> float:
       # Model pricing table
       # Calculate based on input/output tokens
   ```

2. **Store costs in database** (2 hours)
   ```sql
   ALTER TABLE agent_tasks ADD COLUMN cost_usd DECIMAL(10,4);
   ALTER TABLE agent_tasks ADD COLUMN model_used VARCHAR(100);
   ALTER TABLE agent_tasks ADD COLUMN tokens_used INT;
   ```

3. **Create cost dashboard** (2 hours)
   ```python
   def get_daily_cost() -> float
   def get_cost_by_model() -> dict
   def get_cost_by_task_type() -> dict
   ```

4. **Set up budget alerts** (2 hours)
   ```python
   if daily_cost > budget * 0.80:
       send_alert("Budget warning: 80%")
   ```

**Success Criteria:**
- ✅ Cost tracked per task
- ✅ Daily cost dashboard
- ✅ Budget alerts work

### Day 7: Monitoring Consolidation

**Goal:** Single monitoring system (Prometheus)

**Tasks:**

1. **Add custom metrics** (3 hours)
   ```python
   from prometheus_client import Counter, Histogram, Gauge
   
   tasks_total = Counter('hermes_tasks_total', 'Total tasks', ['status'])
   task_duration = Histogram('hermes_task_duration_seconds', 'Task duration')
   task_cost = Histogram('hermes_task_cost_usd', 'Task cost')
   queue_depth = Gauge('hermes_queue_depth', 'Queue depth')
   daily_cost = Gauge('hermes_daily_cost_usd', 'Daily cost')
   ```

2. **Remove duplicates** (2 hours)
   ```bash
   # Disable duplicate timers
   sudo systemctl disable infra-health-loop.timer
   sudo systemctl disable daily-status-report.timer
   ```

3. **Create dashboard** (3 hours)
   - Service health
   - Task metrics
   - Cost metrics
   - Queue depth

**Success Criteria:**
- ✅ All metrics in Prometheus
- ✅ Duplicates removed
- ✅ Dashboard works

### Day 8-9: Integration Tests

**Goal:** Test critical paths

**Tasks:**

1. **Provider routing tests** (4 hours)
   - Test fallback chain
   - Test safe mode
   - Test rate limit handling

2. **Task queue tests** (4 hours)
   - Test enqueue/dequeue
   - Test checkpoint/resume
   - Test restart recovery

3. **Cost tracking tests** (2 hours)
   - Test cost calculation
   - Test budget alerts

4. **End-to-end tests** (6 hours)
   - Test complete task flow
   - Test task survives restart
   - Test provider failover

**Success Criteria:**
- ✅ 50+ integration tests
- ✅ All tests pass
- ✅ Coverage > 70%

### Day 10: Documentation

**Goal:** Document how it works

**Tasks:**

1. **Architecture docs** (3 hours)
   - Updated architecture diagram
   - Component descriptions
   - Data flow

2. **Runbook** (3 hours)
   - How to deploy
   - How to monitor
   - How to troubleshoot

3. **API docs** (2 hours)
   - Task queue API
   - Cost tracking API
   - Monitoring API

**Success Criteria:**
- ✅ Architecture documented
- ✅ Runbook complete
- ✅ API documented

---

## 🚦 Phase 2 Gate: Verification

**Phase 3 starts ONLY if ALL criteria met:**

### Automated Checks

```bash
# 1. Cost tracking works
psql -U automation -d rag -c \
  "SELECT count(*) FROM agent_tasks WHERE cost_usd IS NOT NULL;"
# Expected: > 0

# 2. Metrics available
curl -s http://localhost:9090/api/v1/query?query=hermes_tasks_total | jq .
# Expected: data returned

# 3. Tests pass
cd hermes && pytest tests/ -v
# Expected: 50+ tests pass

# 4. Coverage > 70%
cd hermes && pytest --cov=src --cov-report=term-missing
# Expected: > 70%
```

### Manual Verification

- [ ] Gateway runs for 14 days without manual restart
- [ ] Cost tracked for all tasks
- [ ] Dashboard shows real-time metrics
- [ ] Budget alerts work
- [ ] Documentation complete

### Metrics

- **Uptime:** 14 days continuous
- **Cost tracking:** 100% of tasks
- **Test coverage:** > 70%
- **Monitoring:** Single system (Prometheus)

---

## 🎯 Phase 3: Make it Maintainable (Week 3)

**ONLY START IF PHASE 2 GATE PASSED**

**Goal:** Clean code, easy to change

**Duration:** 5 days  
**Gate:** Monolith decomposed + tests pass + 14 days uptime

### Day 11-13: Decompose run_loop.py

**Goal:** Break 233KB monolith into modules

**Tasks:**

1. **Extract modules** (8 hours)
   - MessageHandler
   - ToolOrchestrator
   - ProviderManager
   - StreamProcessor
   - CheckpointManager
   - ErrorHandler
   - CostTracker

2. **Write tests** (8 hours)
   - 80+ tests for new modules
   - Test module interactions

3. **Verify** (4 hours)
   - All existing tests still pass
   - No regressions
   - Performance same or better

**Success Criteria:**
- ✅ run_loop.py < 200 lines
- ✅ 7 focused modules
- ✅ All tests pass
- ✅ Coverage > 80%

### Day 14-15: Production Hardening

**Goal:** Make it robust

**Tasks:**

1. **Rate limiting** (3 hours)
2. **Circuit breakers** (3 hours)
3. **Graceful shutdown** (3 hours)
4. **Load tests** (6 hours)
5. **Security audit** (3 hours)

**Success Criteria:**
- ✅ Rate limiting works
- ✅ Circuit breakers prevent cascades
- ✅ Graceful shutdown preserves work
- ✅ Load tests pass
- ✅ Security audit clean

---

## 🚦 Phase 3 Gate: Verification

**Phase 4 starts ONLY if ALL criteria met:**

### Automated Checks

```bash
# 1. No monolithic modules
find hermes/src -name "*.py" -size +100k
# Expected: empty

# 2. Tests pass
cd hermes && pytest tests/ -v
# Expected: 120+ tests pass

# 3. Coverage > 80%
cd hermes && pytest --cov=src --cov-report=term-missing
# Expected: > 80%

# 4. Services stable
sudo systemctl status hermes-gateway
# Expected: active (running)
```

### Manual Verification

- [ ] Gateway runs for 14 days without manual restart
- [ ] No monolithic modules (> 100KB)
- [ ] Load tests pass
- [ ] Security audit clean
- [ ] Documentation complete

### Metrics

- **Uptime:** 14 days continuous
- **Test coverage:** > 80%
- **Average module size:** < 10KB
- **Failed tasks:** < 1%

---

## 🎯 Phase 4: Cognitive Substrate (Week 4-5)

**ONLY START IF PHASE 3 GATE PASSED**

**Goal:** Always-on graph memory — no task starts without context pack

**Duration:** 10 days  
**Gate:** 100% tasks have context_pack + memory learning works + 21 days uptime

**Philosophy:** Memory is not a tool. Memory is middleware.

**See:** [PHASE_10_2_COGNITIVE_SUBSTRATE.md](PHASE_10_2_COGNITIVE_SUBSTRATE.md)

### Day 16-17: Context Pack Foundation

**Goal:** No task can start without context pack

**Tasks:**

1. **Create Context Orchestrator** (6 hours)
   - `context_orchestrator.py`
   - `ContextPack` schema
   - Basic retrieval (constraints + episodes)

2. **Enforce context pack** (4 hours)
   - Modify task runner
   - Add validation
   - Add logging

3. **Write tests** (6 hours)
   - Context pack creation tests
   - Retrieval tests
   - Enforcement tests

**Success Criteria:**
- ✅ 100% of tasks have `context_pack_id`
- ✅ Task fails if context pack missing
- ✅ Logs show retrieved memories

### Day 18-19: Outcome Writer

**Goal:** Every completed task writes episode + lessons

**Tasks:**

1. **Create Outcome Writer** (6 hours)
   - `outcome_writer.py`
   - `Episode` schema
   - Outcome extraction

2. **Implement learning** (6 hours)
   - Extract lessons learned
   - Link to entities/files/tools
   - Save to database

3. **Write tests** (4 hours)
   - Outcome writing tests
   - Episode creation tests
   - Lesson extraction tests

**Success Criteria:**
- ✅ 100% of completed tasks write episode
- ✅ Episodes have lessons
- ✅ Episodes link to entities

### Day 20-22: Graph Memory

**Goal:** Graph traversal on top of vector search

**Tasks:**

1. **Entity extraction** (6 hours)
   - Extract entities from text
   - Store in database
   - Link to evidence

2. **Relation extraction** (6 hours)
   - Extract relations
   - Build graph
   - Store in database

3. **Graph traversal retriever** (8 hours)
   - Implement traversal
   - Combine vector + graph
   - Compress to context pack

4. **Write tests** (6 hours)
   - Entity extraction tests
   - Relation extraction tests
   - Traversal tests

**Success Criteria:**
- ✅ Context pack includes graph-traversed entities
- ✅ Context pack includes related playbooks
- ✅ Context pack includes constraints

### Day 23: Memory Policy Engine

**Goal:** Each task type has mandatory retrieval policy

**Tasks:**

1. **Define task types** (2 hours)
   - code_repair
   - provider_fix
   - n8n_workflow
   - deployment
   - monitoring

2. **Create policies** (3 hours)
   - Define required/optional memories
   - Set max tokens
   - Set freshness

3. **Implement enforcement** (3 hours)
   - Policy validation
   - Policy application
   - Logging

**Success Criteria:**
- ✅ All task types have policy
- ✅ Policy enforced automatically
- ✅ Logs show policy applied

### Day 24-25: n8n Event Intake

**Goal:** n8n events become raw evidence

**Tasks:**

1. **Create webhook** (4 hours)
   - n8n → Hermes event webhook
   - Event normalization
   - Store as raw evidence

2. **Entity extraction from events** (4 hours)
   - Extract entities
   - Update graph
   - Link to episodes

3. **Integration** (4 hours)
   - Telegram inbound workflow
   - Telegram notification workflow
   - Human approval workflow

4. **Write tests** (4 hours)
   - Event intake tests
   - Entity extraction tests
   - Integration tests

**Success Criteria:**
- ✅ n8n executions stored as evidence
- ✅ Entities extracted from n8n events
- ✅ Graph updated from n8n
- ✅ Telegram → Hermes task works

---

## 🚦 Phase 4 Gate: Verification

**Production ready ONLY if ALL criteria met:**

### Automated Checks

```bash
# 1. All tasks have context pack
psql -U automation -d rag -c \
  "SELECT COUNT(*) FROM agent_tasks WHERE context_pack_id IS NULL;"
# Expected: 0

# 2. All completed tasks have episodes
psql -U automation -d rag -c \
  "SELECT COUNT(*) FROM agent_tasks t 
   LEFT JOIN episodes e ON t.id = e.task_id 
   WHERE t.status = 'completed' AND e.episode_id IS NULL;"
# Expected: 0

# 3. Memory retrieval works
python3 -c "
from context_orchestrator import ContextOrchestrator
co = ContextOrchestrator()
ctx = co.build_context_pack({'type': 'code_repair', 'description': 'test'})
assert ctx is not None
assert ctx.confidence > 0.5
print('✅ Context pack works')
"

# 4. Tests pass
cd hermes && pytest tests/ -v
# Expected: 150+ tests pass

# 5. Coverage > 80%
cd hermes && pytest --cov=src --cov-report=term-missing
# Expected: > 80%
```

### Manual Verification

- [ ] Gateway runs for 21 days without manual restart
- [ ] 100% of tasks have context pack
- [ ] 100% of completed tasks write episodes
- [ ] Memory retrieval latency < 200ms
- [ ] Hermes applies constraints automatically
- [ ] Hermes retrieves similar episodes automatically
- [ ] Documentation complete

### Metrics

- **Uptime:** 21 days continuous (99%+)
- **Test coverage:** > 80%
- **Tasks with context pack:** 100%
- **Tasks with episodes:** 100%
- **Memory retrieval latency:** < 200ms
- **Failed tasks:** < 1%

---

## 📊 Success Metrics

### Phase 1 (Week 1)

- ✅ No HTTP 400 loops for 7 days
- ✅ Tasks survive restarts
- ✅ Disk < 70%
- ✅ Config consolidated
- ✅ Dead code archived

### Phase 2 (Week 2)

- ✅ Cost tracked per task
- ✅ Single monitoring system
- ✅ 50+ integration tests
- ✅ Coverage > 70%
- ✅ 14 days uptime

### Phase 3 (Week 3)

- ✅ No monolithic modules
- ✅ 120+ tests
- ✅ Coverage > 80%
- ✅ 14 days uptime

### Phase 4 (Week 4-5): Cognitive Substrate

- ✅ 100% tasks have context pack
- ✅ 100% completed tasks write episodes
- ✅ Memory retrieval < 200ms
- ✅ Hermes applies constraints automatically
- ✅ Hermes retrieves similar episodes automatically
- ✅ 150+ tests
- ✅ Coverage > 80%
- ✅ 21 days uptime (99%+)

---

## 🚨 Discipline Rules

### Rule 1: Gates are Hard

**Phase 2 does NOT start until Phase 1 gate passes.**  
**Phase 3 does NOT start until Phase 2 gate passes.**

No exceptions. No "just one more feature".

### Rule 2: No Feature Creep

**During Phase 1:** Only P0 fixes.  
**During Phase 2:** Only P1 fixes.  
**During Phase 3:** Only P2 fixes.

New features wait until current phase complete.

### Rule 3: Tests are Required

**Every change must have tests.**  
**Every gate requires tests to pass.**

No "we'll add tests later".

### Rule 4: Rollback Plan

**Every change must be reversible.**  
**Archive, don't delete.**

If something breaks, we can roll back.

---

## 📝 What NOT to Do

### ❌ Don't Start Memory Learning Yet (Phase 1-2)

Memory learning is Phase 4, not P0. If system is unstable, learning will learn from garbage.

**Wait until:** Phase 3 complete + 14 days stable uptime

### ❌ Don't Decompose Everything at Once

Decompose run_loop.py ONLY in Phase 3. Other modules wait.

**Wait until:** Phase 1 + Phase 2 complete

### ❌ Don't Add New Features

No new features until stability proven.

**Wait until:** Phase 3 complete

### ❌ Don't Skip Tests

Every change needs tests. No exceptions.

**Always:** Write tests first or alongside code

### ❌ Don't Make Memory Optional

In Phase 4, memory is NOT a tool. Memory is middleware.

**Rule:** No task can start without context pack.

---

## ✅ Execution Command

**START:** Phase 1, Day 2 (Day 1 already complete)  
**STOP:** After Phase 1 gate verification  
**THEN:** Review, verify, decide on Phase 2

**Discipline:** "S1 failed. Do not start S2."

---

**Status:** READY FOR EXECUTION  
**Current Phase:** Phase 1, Day 2  
**Next Gate:** Phase 1 verification (after Day 5)  
**Last Updated:** 2026-05-06
