# 🧹 Hermes Cleanup & Stabilization Plan

**Date:** 2026-05-05  
**Goal:** Transform Frankenstein into a stable, maintainable system  
**Timeline:** 3 weeks

---

## 🎯 Overview

### Current Problems

1. **Provider fallback hell** → HTTP 400 loops, crashes
2. **No task queue** → work lost on restart
3. **Memory underutilized** → no learning
4. **Config chaos** → scattered across 5+ files
5. **Monitoring duplication** → 5 different systems
6. **Dead code** → n8n workflows, NIM, duplicate scripts
7. **Disk space** → 80% full, no cleanup

### Solution Approach

**Week 1:** Stabilize (stop the bleeding)  
**Week 2:** Optimize (make it smart)  
**Week 3:** Harden (make it robust)

---

## 📅 Week 1: Stabilize

### Day 1: Provider Routing Fix

**Goal:** No more HTTP 400 loops

**Tasks:**

1. **Finish Phase 9.9: Provider Capability Router**
   ```bash
   # Location: hermes/src/model_router.py (already exists)
   # Status: Incomplete
   
   # What to add:
   - Cost-aware model selection
   - Graceful degradation to "safe mode"
   - HTTP 400 handler (no retry loop)
   - Rate limit handler (pause, don't crash)
   ```

2. **Test all provider combinations**
   ```bash
   # Test script
   python3 hermes/src/test_provider_router.py
   
   # Expected: All tests pass
   ```

3. **Update config**
   ```yaml
   # ~/.hermes/config.yaml
   
   provider_routing:
     strategy: capability_aware  # NEW
     cost_optimization: true     # NEW
     safe_mode_on_error: true    # NEW
     
   fallback_chain:
     - model: anthropic/claude-sonnet-4
       provider: openrouter
       max_cost_per_task: 0.50
       
     - model: nvidia/nemotron-3-super-120b-a12b:free
       provider: openrouter
       requires: [supports_parallel_tool_calls]
       
     - model: SAFE_MODE
       action: pause_and_notify
   ```

**Success Criteria:**
- ✅ No HTTP 400 in logs for 24 hours
- ✅ All provider tests pass
- ✅ Graceful degradation works

**Time:** 4 hours

---

### Day 2: Task Queue Implementation

**Goal:** Tasks survive restarts

**Tasks:**

1. **Create task queue schema**
   ```sql
   -- Location: hermes/src/migrations/001_task_queue.sql
   
   CREATE TABLE agent_inbox (
     id SERIAL PRIMARY KEY,
     message_text TEXT NOT NULL,
     source VARCHAR(50) NOT NULL,  -- telegram, api, cron
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
     cost_usd DECIMAL(10,4),
     model_used VARCHAR(100),
     started_at TIMESTAMPTZ,
     completed_at TIMESTAMPTZ,
     error_message TEXT
   );
   
   CREATE INDEX idx_inbox_status ON agent_inbox(status, priority DESC);
   CREATE INDEX idx_tasks_status ON agent_tasks(status, started_at);
   ```

2. **Implement task orchestrator**
   ```python
   # Location: hermes/src/task_orchestrator.py
   
   class TaskOrchestrator:
       def __init__(self):
           self.db = get_db_connection()
           
       def enqueue(self, message, source, priority=5):
           """Add message to inbox"""
           
       def dequeue(self):
           """Get next task from queue"""
           
       def checkpoint(self, task_id, state):
           """Save task state for resume"""
           
       def resume(self, task_id):
           """Resume from checkpoint"""
           
       def complete(self, task_id, result, cost):
           """Mark task complete, track cost"""
   ```

3. **Update hermes-gateway to use queue**
   ```python
   # Location: hermes/src/hermes_core/gateway.py
   
   # OLD: Process message immediately
   # NEW: Enqueue message, process from queue
   
   @app.post("/message")
   async def handle_message(msg: Message):
       task_id = orchestrator.enqueue(
           message=msg.text,
           source="telegram",
           priority=msg.priority or 5
       )
       return {"task_id": task_id, "status": "queued"}
   ```

**Success Criteria:**
- ✅ Messages go to queue
- ✅ Tasks processed from queue
- ✅ Restart doesn't lose work
- ✅ Checkpoint/resume works

**Time:** 8 hours

---

### Day 3: Config Consolidation

**Goal:** Single source of truth

**Tasks:**

1. **Audit all configs**
   ```bash
   # Find all config files
   find /home/Bilirubin/.hermes -name "*.yaml" -o -name "*.json" -o -name ".env"
   find /srv/automation -name "*.env"
   
   # Document locations
   # - ~/.hermes/config.yaml
   # - ~/.hermes/model_capabilities.json
   # - ~/.hermes/.env
   # - /srv/automation/.env
   # - /srv/automation/n8n.env
   ```

2. **Create unified config**
   ```yaml
   # Location: ~/.hermes/config.yaml
   
   # Core settings
   hermes:
     home: /home/Bilirubin/.hermes
     log_level: INFO
     
   # Provider settings
   providers:
     openrouter:
       api_key: ${OPENROUTER_API_KEY}
       base_url: https://openrouter.ai/api/v1
       
     nvidia:
       api_key: ${NVIDIA_API_KEY}
       base_url: https://integrate.api.nvidia.com/v1
       
   # Model settings
   models:
     primary:
       model: anthropic/claude-sonnet-4
       provider: openrouter
       max_cost_per_task: 0.50
       
     fallback:
       - model: nvidia/nemotron-3-super-120b-a12b:free
         provider: openrouter
         requires: [supports_parallel_tool_calls]
         
   # Task queue settings
   task_queue:
     max_concurrent: 2
     checkpoint_interval: 60  # seconds
     retry_limit: 3
     
   # Cost settings
   cost_tracking:
     enabled: true
     daily_budget: 10.00  # USD
     alert_threshold: 0.80  # 80%
     
   # Monitoring settings
   monitoring:
     prometheus_port: 9090
     health_check_interval: 300  # seconds
     alert_telegram: true
   ```

3. **Migrate existing configs**
   ```bash
   # Backup old configs
   cp ~/.hermes/config.yaml ~/.hermes/config.yaml.backup
   cp ~/.hermes/model_capabilities.json ~/.hermes/model_capabilities.json.backup
   
   # Apply new config
   cp hermes/config/unified_config.yaml ~/.hermes/config.yaml
   
   # Validate
   python3 hermes/tools/validate_config.py
   ```

**Success Criteria:**
- ✅ Single config file
- ✅ All settings migrated
- ✅ Validation passes
- ✅ Services restart successfully

**Time:** 2 hours

---

### Day 4: Disk Cleanup

**Goal:** Free up space, prevent future issues

**Tasks:**

1. **Analyze disk usage**
   ```bash
   # Find large files
   du -h /home/Bilirubin/.hermes | sort -rh | head -20
   du -h /srv/automation | sort -rh | head -20
   du -h /var/log | sort -rh | head -20
   
   # Find old logs
   find /home/Bilirubin/.hermes/logs -name "*.log" -mtime +30
   find /var/log -name "*.log" -mtime +30
   ```

2. **Clean up old files**
   ```bash
   # Remove old logs (> 30 days)
   find /home/Bilirubin/.hermes/logs -name "*.log" -mtime +30 -delete
   find /var/log -name "*.log" -mtime +30 -delete
   
   # Archive old backups (> 7 days)
   find /home/Bilirubin/.hermes/backups -name "*.tar.gz" -mtime +7 \
     -exec mv {} /home/Bilirubin/.hermes/backups/archive/ \;
   
   # Remove old temp files
   rm -rf /home/Bilirubin/.hermes/temp/*
   rm -rf /tmp/hermes-*
   ```

3. **Set up automatic cleanup**
   ```bash
   # Create logrotate config
   cat > /etc/logrotate.d/hermes <<EOF
   /home/Bilirubin/.hermes/logs/*.log {
       daily
       rotate 30
       compress
       delaycompress
       missingok
       notifempty
   }
   EOF
   
   # Create cleanup cron job
   cat > /etc/cron.daily/hermes-cleanup <<EOF
   #!/bin/bash
   # Clean up old temp files
   find /home/Bilirubin/.hermes/temp -mtime +7 -delete
   
   # Archive old backups
   find /home/Bilirubin/.hermes/backups -name "*.tar.gz" -mtime +7 \
     -exec mv {} /home/Bilirubin/.hermes/backups/archive/ \;
   EOF
   
   chmod +x /etc/cron.daily/hermes-cleanup
   ```

**Success Criteria:**
- ✅ Disk usage < 70%
- ✅ Old logs removed
- ✅ Automatic cleanup configured
- ✅ No manual intervention needed

**Time:** 1 hour

---

### Day 5: Dead Code Removal

**Goal:** Remove unused features

**Tasks:**

1. **Archive n8n workflows**
   ```bash
   # n8n workflows are inactive, Hermes cron jobs are active
   
   # Export workflows for archive
   psql -U automation -d n8n -c \
     "COPY (SELECT * FROM workflow_entity) TO '/tmp/n8n_workflows_backup.csv' CSV HEADER;"
   
   # Move to archive
   mkdir -p hermes/archive/n8n-workflows
   mv /tmp/n8n_workflows_backup.csv hermes/archive/n8n-workflows/
   
   # Document decision
   echo "n8n workflows archived 2026-05-05. Use Hermes cron jobs instead." \
     > hermes/archive/n8n-workflows/README.md
   ```

2. **Archive NIM orchestrator**
   ```bash
   # NIM is experimental, not used in production
   
   mv hermes/nim hermes/archive/nim-orchestrator
   
   echo "NIM orchestrator archived 2026-05-05. Experimental, not production ready." \
     > hermes/archive/nim-orchestrator/README.md
   ```

3. **Remove duplicate health checks**
   ```bash
   # Keep MCP as primary, remove shell scripts
   
   # Archive shell scripts
   mkdir -p hermes/archive/shell-health-checks
   mv hermes/src/host_checklist.sh hermes/archive/shell-health-checks/
   mv hermes/src/db_checklist.sh hermes/archive/shell-health-checks/
   mv hermes/src/agent_readiness_check.sh hermes/archive/shell-health-checks/
   
   # Update .hermes.md to use MCP only
   sed -i 's|/home/Bilirubin/workspace/host_checklist.sh|mcp_control_plane_infra_readiness|g' \
     hermes/.hermes.md
   ```

4. **Remove duplicate backup scripts**
   ```bash
   # Consolidate into single backup system
   
   # Archive old scripts
   mkdir -p hermes/archive/backup-scripts
   find hermes/scripts -name "*backup*" -exec mv {} hermes/archive/backup-scripts/ \;
   
   # Keep only systemd timer
   # (already exists: infra-snapshot.service + infra-snapshot.timer)
   ```

**Success Criteria:**
- ✅ n8n workflows archived
- ✅ NIM archived
- ✅ Duplicate scripts removed
- ✅ Documentation updated

**Time:** 2 hours

---

## 📅 Week 2: Optimize

### Day 6-7: Cost Tracking

**Goal:** Track and optimize costs

**Tasks:**

1. **Add cost tracking to task queue**
   ```python
   # Location: hermes/src/task_orchestrator.py
   
   def complete(self, task_id, result, model_used):
       # Calculate cost based on model and tokens
       cost = self.calculate_cost(model_used, result.tokens)
       
       # Store in database
       self.db.execute("""
           UPDATE agent_tasks
           SET status = 'completed',
               cost_usd = %s,
               model_used = %s,
               completed_at = NOW()
           WHERE id = %s
       """, (cost, model_used, task_id))
       
       # Check daily budget
       daily_cost = self.get_daily_cost()
       if daily_cost > self.config.daily_budget * 0.80:
           self.send_alert(f"Daily cost: ${daily_cost:.2f} (80% of budget)")
   ```

2. **Create cost dashboard**
   ```python
   # Location: hermes/src/cost_dashboard.py
   
   def generate_cost_report():
       # Daily cost
       # Cost per model
       # Cost per task type
       # Budget vs actual
       # Trends
   ```

3. **Set up budget alerts**
   ```python
   # Location: hermes/src/cost_alerts.py
   
   def check_budget():
       daily_cost = get_daily_cost()
       budget = get_daily_budget()
       
       if daily_cost > budget * 0.80:
           send_telegram_alert(f"⚠️ Daily cost: ${daily_cost:.2f} (80% of ${budget:.2f})")
       
       if daily_cost > budget:
           send_telegram_alert(f"🚨 Budget exceeded: ${daily_cost:.2f} > ${budget:.2f}")
           enable_safe_mode()
   ```

**Success Criteria:**
- ✅ Cost tracked per task
- ✅ Daily cost dashboard
- ✅ Budget alerts working
- ✅ Cost optimization suggestions

**Time:** 8 hours

---

### Day 8-9: Memory Learning

**Goal:** Learn from past tasks

**Tasks:**

1. **Store task outcomes**
   ```python
   # Location: hermes/src/task_learning.py
   
   def store_outcome(task_id, outcome):
       # Store in rag_documents
       self.db.execute("""
           INSERT INTO rag_documents (collection, source, content, metadata)
           VALUES ('task-outcomes', %s, %s, %s)
       """, (
           f"task-{task_id}",
           json.dumps(outcome),
           {
               'task_type': outcome.task_type,
               'model_used': outcome.model,
               'cost': outcome.cost,
               'success': outcome.success,
               'duration': outcome.duration
           }
       ))
   ```

2. **Analyze patterns**
   ```python
   # Location: hermes/src/pattern_analyzer.py
   
   def analyze_patterns():
       # Which models work best for which tasks?
       # Which tasks are most expensive?
       # Which tasks fail most often?
       # What are common error patterns?
       
       patterns = {
           'best_model_for_task': {},
           'expensive_tasks': [],
           'failure_patterns': [],
           'optimization_suggestions': []
       }
       
       return patterns
   ```

3. **Generate suggestions**
   ```python
   # Location: hermes/src/optimization_suggestions.py
   
   def generate_suggestions():
       patterns = analyze_patterns()
       
       suggestions = []
       
       # Model selection suggestions
       if patterns['best_model_for_task']:
           suggestions.append({
               'type': 'model_selection',
               'suggestion': 'Use cheaper model for simple tasks',
               'potential_savings': calculate_savings()
           })
       
       # Task batching suggestions
       if patterns['expensive_tasks']:
           suggestions.append({
               'type': 'task_batching',
               'suggestion': 'Batch similar tasks together',
               'potential_savings': calculate_batching_savings()
           })
       
       return suggestions
   ```

**Success Criteria:**
- ✅ Task outcomes stored
- ✅ Patterns analyzed
- ✅ Suggestions generated
- ✅ Learning loop active

**Time:** 8 hours

---

### Day 10: Monitoring Consolidation

**Goal:** Single monitoring system

**Tasks:**

1. **Choose primary system: Prometheus**
   ```yaml
   # Keep: Prometheus + node_exporter
   # Remove: Duplicate health checks
   # Consolidate: All metrics in Prometheus
   ```

2. **Add custom metrics**
   ```python
   # Location: hermes/src/metrics.py
   
   from prometheus_client import Counter, Histogram, Gauge
   
   # Task metrics
   tasks_total = Counter('hermes_tasks_total', 'Total tasks', ['status', 'type'])
   task_duration = Histogram('hermes_task_duration_seconds', 'Task duration')
   task_cost = Histogram('hermes_task_cost_usd', 'Task cost in USD')
   
   # Queue metrics
   queue_depth = Gauge('hermes_queue_depth', 'Tasks in queue')
   
   # Cost metrics
   daily_cost = Gauge('hermes_daily_cost_usd', 'Daily cost in USD')
   budget_usage = Gauge('hermes_budget_usage_percent', 'Budget usage %')
   ```

3. **Create unified dashboard**
   ```yaml
   # Location: hermes/config/grafana_dashboard.json
   
   # Panels:
   # - Service health
   # - Task queue depth
   # - Task completion rate
   # - Cost per hour
   # - Budget usage
   # - Model usage
   # - Error rate
   ```

4. **Remove duplicates**
   ```bash
   # Disable duplicate timers
   sudo systemctl disable infra-health-loop.timer
   sudo systemctl disable daily-status-report.timer
   
   # Keep only Prometheus
   # (already running, just add custom metrics)
   ```

**Success Criteria:**
- ✅ Single monitoring system
- ✅ All metrics in Prometheus
- ✅ Unified dashboard
- ✅ No duplicates

**Time:** 4 hours

---

## 📅 Week 3: Harden

### Day 11-12: Production Hardening

**Goal:** Make it robust

**Tasks:**

1. **Add rate limiting**
   ```python
   # Location: hermes/src/rate_limiter.py
   
   from redis import Redis
   from datetime import datetime, timedelta
   
   class RateLimiter:
       def __init__(self):
           self.redis = Redis()
           
       def check_limit(self, user_id, limit=10, window=60):
           key = f"rate_limit:{user_id}"
           count = self.redis.incr(key)
           
           if count == 1:
               self.redis.expire(key, window)
           
           return count <= limit
   ```

2. **Add circuit breakers**
   ```python
   # Location: hermes/src/circuit_breaker.py
   
   class CircuitBreaker:
       def __init__(self, failure_threshold=5, timeout=60):
           self.failure_count = 0
           self.failure_threshold = failure_threshold
           self.timeout = timeout
           self.last_failure = None
           self.state = 'closed'  # closed, open, half_open
           
       def call(self, func, *args, **kwargs):
           if self.state == 'open':
               if datetime.now() - self.last_failure > timedelta(seconds=self.timeout):
                   self.state = 'half_open'
               else:
                   raise Exception("Circuit breaker is open")
           
           try:
               result = func(*args, **kwargs)
               if self.state == 'half_open':
                   self.state = 'closed'
                   self.failure_count = 0
               return result
           except Exception as e:
               self.failure_count += 1
               self.last_failure = datetime.now()
               
               if self.failure_count >= self.failure_threshold:
                   self.state = 'open'
               
               raise e
   ```

3. **Add graceful shutdown**
   ```python
   # Location: hermes/src/graceful_shutdown.py
   
   import signal
   import sys
   
   class GracefulShutdown:
       def __init__(self, orchestrator):
           self.orchestrator = orchestrator
           signal.signal(signal.SIGTERM, self.handle_signal)
           signal.signal(signal.SIGINT, self.handle_signal)
           
       def handle_signal(self, signum, frame):
           print("Shutting down gracefully...")
           
           # Checkpoint current tasks
           self.orchestrator.checkpoint_all()
           
           # Stop accepting new tasks
           self.orchestrator.stop()
           
           # Wait for current tasks to finish (max 30s)
           self.orchestrator.wait_for_completion(timeout=30)
           
           sys.exit(0)
   ```

**Success Criteria:**
- ✅ Rate limiting works
- ✅ Circuit breakers prevent cascading failures
- ✅ Graceful shutdown preserves work
- ✅ No data loss on restart

**Time:** 8 hours

---

### Day 13-14: Testing & Documentation

**Goal:** Verify everything works

**Tasks:**

1. **Integration tests**
   ```python
   # Location: hermes/tests/test_integration.py
   
   def test_task_queue():
       # Enqueue task
       # Process task
       # Verify completion
       # Verify cost tracking
       
   def test_provider_routing():
       # Test all provider combinations
       # Test fallback chain
       # Test graceful degradation
       
   def test_checkpoint_resume():
       # Start task
       # Checkpoint
       # Restart
       # Resume
       # Verify completion
   ```

2. **Load tests**
   ```python
   # Location: hermes/tests/test_load.py
   
   def test_concurrent_tasks():
       # Enqueue 100 tasks
       # Process concurrently
       # Verify all complete
       # Verify no errors
       
   def test_high_load():
       # Enqueue 1000 tasks
       # Monitor system resources
       # Verify stability
   ```

3. **Update documentation**
   ```markdown
   # Location: hermes/docs/ARCHITECTURE.md
   
   # Updated architecture diagram
   # Component descriptions
   # Data flow
   # Configuration guide
   # Troubleshooting guide
   ```

**Success Criteria:**
- ✅ All tests pass
- ✅ Load tests pass
- ✅ Documentation updated
- ✅ Ready for production

**Time:** 8 hours

---

## 📊 Success Metrics

### Week 1 (Stabilize)

- ✅ No HTTP 400 loops for 7 days
- ✅ No manual /resume required
- ✅ Tasks survive restarts
- ✅ Disk < 70%
- ✅ Config consolidated

### Week 2 (Optimize)

- ✅ Cost per task tracked
- ✅ Daily cost < $10
- ✅ Learning loop active
- ✅ Single monitoring system

### Week 3 (Harden)

- ✅ 99% uptime
- ✅ All tests pass
- ✅ Documentation complete
- ✅ Production ready

---

## 🎯 Final State

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      USER / TELEGRAM                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  HERMES GATEWAY (8642)                       │
│  • Task queue (PostgreSQL)                                   │
│  • Capability-aware routing                                  │
│  • Cost tracking                                             │
│  • Checkpoint/resume                                         │
│  ✅ STABLE                                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐
│  OpenRouter  │ │  NVIDIA  │ │ SAFE MODE  │
│  (primary)   │ │(fallback)│ │  (pause)   │
│  • Smart     │ │ • Capable│ │            │
│  • Tracked   │ │ • Tested │ │            │
└──────────────┘ └──────────┘ └────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  BRAIN MCP (8791)                            │
│  • Memory operations                                         │
│  • Infrastructure monitoring                                 │
│  • Provider health checks                                    │
│  ✅ STABLE                                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              POSTGRESQL (rag + n8n)                          │
│  • Task queue (agent_inbox, agent_tasks)                     │
│  • Task outcomes (rag_documents)                             │
│  • Cost tracking                                             │
│  • Learning data                                             │
│  ✅ UTILIZED                                                 │
└──────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  PROMETHEUS (9090)                           │
│  • System metrics                                            │
│  • Task metrics                                              │
│  • Cost metrics                                              │
│  • Unified dashboard                                         │
│  ✅ CONSOLIDATED                                             │
└──────────────────────────────────────────────────────────────┘
```

### Key Improvements

1. ✅ **Stable** — No crashes, no manual intervention
2. ✅ **Smart** — Cost tracking, learning, optimization
3. ✅ **Robust** — Rate limiting, circuit breakers, graceful shutdown
4. ✅ **Maintainable** — Single config, unified monitoring, clean code
5. ✅ **Production Ready** — Tests pass, documentation complete

---

## 📝 Next Steps

1. **Review this plan** with team
2. **Prioritize** action items
3. **Execute** Week 1 (Stabilize)
4. **Review** progress after Week 1
5. **Continue** with Week 2 & 3

**Status:** READY FOR EXECUTION  
**Owner:** Hermes Team  
**Start Date:** 2026-05-06  
**Target Completion:** 2026-05-26
