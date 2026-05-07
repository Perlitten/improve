# 🔍 Hermes Architecture Audit

**Date:** 2026-05-05  
**Auditor:** Kiro AI  
**Scope:** Complete system architecture review

---

## 🎯 Executive Summary

**Current State:** Frankenstein's monster — functional but fragile  
**Core Problem:** Reactive patching without architectural vision  
**Risk Level:** HIGH — system complexity growing faster than stability

### Key Findings

1. ✅ **What Works:** MCP control plane, PostgreSQL memory, basic monitoring
2. ⚠️ **What's Fragile:** Provider fallback, runtime stability, config management
3. ❌ **What's Broken:** No task queue, no cost optimization, memory underutilized
4. 🗑️ **What's Dead:** n8n workflows (inactive), duplicate monitoring, scattered configs

---

## 📊 Architecture Overview

### Current Components

```
┌─────────────────────────────────────────────────────────────┐
│                      USER / TELEGRAM                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  HERMES GATEWAY (8642)                       │
│  • Chat interface                                            │
│  • Provider routing (fragile)                                │
│  • No task queue                                             │
│  • No cost tracking                                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐
│  OpenRouter  │ │  NVIDIA  │ │ Omniroute  │
│  (primary)   │ │(fallback)│ │ (backup)   │
│  • Expensive │ │ • Broken │ │ • Unstable │
│  • Rate lim  │ │ • Single │ │            │
└──────────────┘ └──────────┘ └────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  BRAIN MCP (8791)                            │
│  • Memory operations                                         │
│  • Infrastructure monitoring                                 │
│  • Provider health checks                                    │
│  ✅ WORKS WELL                                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              POSTGRESQL (rag + n8n)                          │
│  • Canonical memory (workspaces, projects, artifacts)        │
│  • RAG collections (host-state, host-insights, etc.)         │
│  • n8n workflows (inactive)                                  │
│  ⚠️ UNDERUTILIZED                                            │
└──────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  MONITORING STACK                            │
│  • Prometheus (9090)                                         │
│  • node_exporter (9100)                                      │
│  • infra-health-loop (systemd timer)                         │
│  • Daily status reports                                      │
│  ⚠️ DUPLICATE SYSTEMS                                        │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔴 Critical Problems

### 1. Provider Fallback Hell

**Problem:**
- Primary model (Claude) rate limits → fallback to NVIDIA llama
- NVIDIA llama doesn't support parallel tools → HTTP 400
- HTTP 400 → retry loop → crash
- Manual restart required

**Root Cause:**
- No capability-aware routing
- No graceful degradation
- No task queue to pause/resume

**Impact:**
- Hermes crashes multiple times per day
- Tasks lost
- Manual intervention required

**Solution Attempted:**
- Phase 9.9: Provider Capability Router (INCOMPLETE)
- Emergency patch (BAND-AID)

**Real Solution Needed:**
- Task queue with pause/resume
- Capability-aware routing (finish Phase 9.9)
- Cost-aware model selection
- Graceful degradation to "safe mode"

### 2. No Task Queue

**Problem:**
- Hermes is a chat interface, not a task runtime
- New message interrupts current task
- No persistence across restarts
- No priority management
- No cost tracking per task

**Impact:**
- Tasks interrupted
- Work lost on restart
- No way to batch/schedule work
- No cost optimization

**Solution Attempted:**
- Phase 10.0: Reliable Agent Runtime (NOT STARTED)

**Real Solution Needed:**
- Persistent task queue (PostgreSQL)
- Task orchestrator
- Checkpoint/resume system
- Priority management
- Cost tracking

### 3. Memory Underutilized

**Problem:**
- PostgreSQL with pgvector exists
- RAG collections exist
- But NOT used for:
  - Learning from past tasks
  - Cost optimization
  - Pattern recognition
  - Proactive suggestions

**Impact:**
- Repeating same mistakes
- No learning curve
- No cost optimization
- Wasted infrastructure

**Andrey Karpathy Principle Violated:**
> "The best models learn from their own outputs and improve over time."

**Real Solution Needed:**
- Task outcome tracking
- Cost per task type analysis
- Pattern recognition
- Proactive optimization suggestions
- Self-improvement loop

### 4. Config Chaos

**Problem:**
- Configs scattered across:
  - `/home/Bilirubin/.hermes/config.yaml`
  - `/home/Bilirubin/.hermes/model_capabilities.json`
  - `/srv/automation/.env`
  - `/home/Bilirubin/.hermes/.env`
  - `/srv/automation/n8n.env`
  - Hardcoded in scripts

**Impact:**
- Hard to change settings
- Easy to create conflicts
- No single source of truth
- Deployment fragility

**Real Solution Needed:**
- Single config file
- Environment-specific overrides
- Config validation
- Migration system

### 5. Monitoring Duplication

**Problem:**
- Multiple monitoring systems:
  - Prometheus + node_exporter
  - infra-health-loop (systemd)
  - Daily status reports
  - Hermes cron jobs
  - n8n workflows (inactive)

**Impact:**
- Confusion about which system is authoritative
- Duplicate alerts
- Wasted resources
- Maintenance burden

**Real Solution Needed:**
- Single monitoring system
- Clear responsibilities
- Unified alerting
- Remove duplicates

---

## 🗑️ Dead Code / Unused Features

### 1. n8n Workflows (INACTIVE)

**Status:** Created but never activated  
**Reason:** Credential setup too complex  
**Alternative:** Hermes cron jobs (active)

**Recommendation:** DELETE n8n workflows, keep only cron jobs

### 2. NIM Orchestrator (EXPERIMENTAL)

**Location:** `hermes/nim/`  
**Status:** Experimental, not used in production  
**Purpose:** Multi-agent orchestration

**Recommendation:** ARCHIVE until needed

### 3. Multiple Backup Scripts

**Problem:** Backup logic scattered across:
- systemd timers
- Hermes cron jobs
- Manual scripts

**Recommendation:** CONSOLIDATE into single backup system

### 4. Duplicate Health Checks

**Problem:**
- `host_checklist.sh`
- `db_checklist.sh`
- `agent_readiness_check.sh`
- MCP `infra_readiness`
- Prometheus metrics

**Recommendation:** Use MCP as primary, remove shell scripts

---

## ⚠️ Fragile Components

### 1. Provider Routing

**Current:** Hardcoded fallback chain  
**Problem:** No capability awareness, no cost awareness  
**Risk:** HTTP 400 loop, cost explosion

**Fix Priority:** CRITICAL

### 2. Session Management

**Current:** Manual /resume after restart  
**Problem:** No persistence, no auto-recovery  
**Risk:** Work lost on crash

**Fix Priority:** HIGH

### 3. Disk Space

**Current:** 80% full  
**Problem:** No automatic cleanup  
**Risk:** Out of space → system crash

**Fix Priority:** HIGH

### 4. Single Point of Failure

**Current:** All services on one VM  
**Problem:** VM crash = total outage  
**Risk:** No redundancy

**Fix Priority:** MEDIUM (after stability)

---

## ✅ What Works Well

### 1. Brain MCP Server

**Status:** PRODUCTION READY  
**Quality:** Clean, well-documented, non-destructive  
**Coverage:** Infrastructure, memory, n8n, providers

**Keep:** YES

### 2. PostgreSQL Memory

**Status:** STABLE  
**Quality:** Proper schema, migrations, pgvector  
**Coverage:** Canonical memory + RAG collections

**Keep:** YES  
**Improve:** Utilize more for learning

### 3. Systemd Services

**Status:** RELIABLE  
**Quality:** Proper service definitions, auto-restart  
**Coverage:** All core services

**Keep:** YES

### 4. Prometheus Monitoring

**Status:** WORKING  
**Quality:** 610+ host metrics, 72+ n8n metrics  
**Coverage:** System health

**Keep:** YES  
**Improve:** Add cost metrics, task metrics

---

## 🎯 Recommended Architecture

### Phase 1: Stabilize (Week 1)

**Goal:** Stop the bleeding

1. **Finish Phase 9.9: Provider Capability Router**
   - Capability-aware routing
   - Cost-aware model selection
   - Graceful degradation
   - No HTTP 400 loops

2. **Implement Phase 10.0: Task Queue**
   - Persistent inbox (PostgreSQL)
   - Task orchestrator
   - Checkpoint/resume
   - Priority management

3. **Config Consolidation**
   - Single config file
   - Environment overrides
   - Validation

4. **Disk Cleanup**
   - Remove old logs
   - Archive old backups
   - Set up auto-cleanup

**Success Criteria:**
- ✅ No HTTP 400 loops
- ✅ No manual /resume required
- ✅ Tasks survive restarts
- ✅ Disk < 70%

### Phase 2: Optimize (Week 2)

**Goal:** Make it smart

1. **Cost Tracking**
   - Track cost per task
   - Track cost per model
   - Daily cost reports
   - Budget alerts

2. **Memory Learning**
   - Store task outcomes
   - Analyze patterns
   - Suggest optimizations
   - Learn from mistakes

3. **Model Selection Intelligence**
   - Task type → model mapping
   - Cost vs quality tradeoffs
   - Automatic model selection
   - A/B testing

4. **Monitoring Consolidation**
   - Remove duplicates
   - Unified dashboard
   - Clear alerting rules

**Success Criteria:**
- ✅ Cost per task tracked
- ✅ Automatic model selection
- ✅ Learning from past tasks
- ✅ Single monitoring system

### Phase 3: Scale (Week 3+)

**Goal:** Make it robust

1. **Redundancy**
   - Multi-region providers
   - Backup VM
   - Database replication

2. **Advanced Features**
   - Batch processing
   - Scheduled tasks
   - Multi-agent orchestration
   - Self-improvement loop

3. **Production Hardening**
   - Rate limiting
   - Circuit breakers
   - Graceful shutdown
   - Zero-downtime deploys

**Success Criteria:**
- ✅ 99.9% uptime
- ✅ No single point of failure
- ✅ Self-healing
- ✅ Continuous improvement

---

## 📋 Immediate Action Items

### This Week (Priority 1)

1. **Finish Phase 9.9** (4 hours)
   - Complete provider capability router
   - Test with all models
   - Verify no HTTP 400 loops

2. **Start Phase 10.0** (8 hours)
   - Implement task queue
   - Implement checkpoint/resume
   - Test restart recovery

3. **Disk Cleanup** (1 hour)
   - Remove old logs (> 30 days)
   - Archive old backups (> 7 days)
   - Set up logrotate

4. **Config Audit** (2 hours)
   - Document all config locations
   - Identify conflicts
   - Plan consolidation

### Next Week (Priority 2)

1. **Cost Tracking** (4 hours)
   - Add cost tracking to task queue
   - Create cost dashboard
   - Set up budget alerts

2. **Memory Learning** (6 hours)
   - Store task outcomes
   - Analyze patterns
   - Create learning loop

3. **Monitoring Cleanup** (3 hours)
   - Remove duplicate systems
   - Consolidate alerts
   - Create unified dashboard

4. **Dead Code Removal** (2 hours)
   - Archive n8n workflows
   - Archive NIM orchestrator
   - Remove unused scripts

---

## 🎓 Andrey Karpathy Principles Applied

### 1. "Start Simple, Add Complexity Only When Needed"

**Current:** Too complex too early  
**Fix:** Remove unused features, focus on core

### 2. "The Best Models Learn from Their Own Outputs"

**Current:** No learning loop  
**Fix:** Store outcomes, analyze patterns, improve

### 3. "Optimize for Iteration Speed"

**Current:** Slow to change, fragile  
**Fix:** Better config management, faster deploys

### 4. "Measure Everything"

**Current:** No cost tracking, no task metrics  
**Fix:** Track costs, track outcomes, track patterns

### 5. "Automate the Boring Stuff"

**Current:** Manual restarts, manual /resume  
**Fix:** Auto-recovery, auto-resume, auto-cleanup

---

## 📊 Metrics to Track

### System Health

- ✅ Service uptime (already tracked)
- ✅ Disk usage (already tracked)
- ✅ Memory usage (already tracked)
- ❌ Task queue depth (NOT tracked)
- ❌ Task completion rate (NOT tracked)
- ❌ Task failure rate (NOT tracked)

### Cost Metrics

- ❌ Cost per task (NOT tracked)
- ❌ Cost per model (NOT tracked)
- ❌ Daily cost (NOT tracked)
- ❌ Budget vs actual (NOT tracked)

### Quality Metrics

- ❌ Task success rate (NOT tracked)
- ❌ Average task duration (NOT tracked)
- ❌ Retry rate (NOT tracked)
- ❌ User satisfaction (NOT tracked)

### Learning Metrics

- ❌ Patterns recognized (NOT tracked)
- ❌ Optimizations applied (NOT tracked)
- ❌ Cost savings (NOT tracked)
- ❌ Quality improvements (NOT tracked)

---

## 🎯 Success Criteria

### Short Term (1 week)

- ✅ No HTTP 400 loops
- ✅ No manual /resume required
- ✅ Tasks survive restarts
- ✅ Disk < 70%
- ✅ Config consolidated

### Medium Term (1 month)

- ✅ Cost per task tracked
- ✅ Automatic model selection
- ✅ Learning from past tasks
- ✅ Single monitoring system
- ✅ 99% uptime

### Long Term (3 months)

- ✅ Self-improving system
- ✅ Cost optimized
- ✅ Production hardened
- ✅ No manual intervention needed
- ✅ 99.9% uptime

---

## 📝 Conclusion

**Current State:** Functional but fragile Frankenstein  
**Root Cause:** Reactive patching without architectural vision  
**Path Forward:** Stabilize → Optimize → Scale

**Key Insight:**  
> "We built a chat interface when we needed a task runtime.  
> We added monitoring when we needed learning.  
> We patched problems when we needed architecture."

**Recommendation:**  
Stop adding features. Finish what we started. Make it stable, then make it smart.

---

**Next Steps:**
1. Read this audit
2. Prioritize action items
3. Execute Phase 1 (Stabilize)
4. Review progress weekly

**Status:** READY FOR EXECUTION  
**Owner:** Hermes Team  
**Deadline:** Phase 1 complete by 2026-05-12
