# 🚦 Phase 1 Gate: Verification Guide

**Date:** 2026-05-06  
**Status:** READY TO START  
**Duration:** 7 days

---

## 🎯 Gate Purpose

**Goal:** Verify that Phase 1 changes are stable and effective before proceeding to Phase 2.

**Principle:** "S1 failed. Do not start S2."

**Phase 2 starts ONLY if ALL gate criteria are met.**

---

## ✅ Gate Criteria

### Automated Checks (Run Daily)

#### 1. No HTTP 400 Loops

```bash
# Check for HTTP 400 loops in last 24 hours
sudo journalctl -u hermes-gateway --since "24 hours ago" | \
  grep -i "HTTP 400\|single tool" | wc -l
```

**Expected:** 0  
**Frequency:** Daily  
**Action if failed:** Investigate immediately, fix before continuing

#### 2. Task Queue Works

```bash
# Check task queue has entries
psql -U automation -d rag -c "SELECT count(*) FROM agent_inbox;"
```

**Expected:** > 0  
**Frequency:** Daily  
**Action if failed:** Check database connection, verify schema

#### 3. Tasks Survive Restart

```bash
# Restart gateway
sudo systemctl restart hermes-gateway
sleep 10

# Check tasks still queued
psql -U automation -d rag -c "SELECT count(*) FROM agent_tasks WHERE status='queued';"
```

**Expected:** Tasks still present  
**Frequency:** Every 2 days  
**Action if failed:** Check task persistence, verify database

#### 4. Disk Usage < 70%

```bash
# Check disk usage
df -h / | grep -E "/$" | awk '{print $5}' | sed 's/%//'
```

**Expected:** < 70  
**Frequency:** Daily  
**Action if failed:** Run manual cleanup, check automatic cleanup

#### 5. Config Loads

```bash
# Test config loading
python3 -c "import yaml; yaml.safe_load(open('/home/Bilirubin/.hermes/config.yaml'))"
```

**Expected:** No errors  
**Frequency:** Daily  
**Action if failed:** Check config syntax, verify file exists

#### 6. Tests Pass

```bash
# Run unit tests
cd /home/Bilirubin/workspace/hermes
pytest tests/unit -v
```

**Expected:** All pass (58 tests)  
**Frequency:** Daily  
**Action if failed:** Fix failing tests immediately

---

### Manual Verification (Check Daily)

#### 1. Gateway Uptime

```bash
# Check gateway status
sudo systemctl status hermes-gateway

# Check uptime
sudo journalctl -u hermes-gateway | grep "Started" | tail -1
```

**Expected:** Running continuously, no manual restarts  
**Frequency:** Daily  
**Action if failed:** Investigate why restart was needed

#### 2. No Provider Crashes

```bash
# Check for provider errors
sudo journalctl -u hermes-gateway --since "24 hours ago" | \
  grep -i "error\|crash\|exception" | grep -i "provider"
```

**Expected:** No crashes  
**Frequency:** Daily  
**Action if failed:** Investigate provider issues

#### 3. Task Persistence

```bash
# Check task history
psql -U automation -d rag -c "SELECT status, count(*) FROM agent_tasks GROUP BY status;"
```

**Expected:** Tasks in various states (queued, running, completed)  
**Frequency:** Daily  
**Action if failed:** Check task orchestrator

#### 4. Config is Single Source

```bash
# Check for old config files
find /home/Bilirubin/.hermes -name "*.env" -o -name "config*.yaml" | grep -v config.yaml
```

**Expected:** Only config.yaml exists  
**Frequency:** Once  
**Action if failed:** Remove old config files

#### 5. Disk Usage Stable

```bash
# Check disk usage trend
du -sh /home/Bilirubin/.hermes
```

**Expected:** Stable or decreasing  
**Frequency:** Daily  
**Action if failed:** Check automatic cleanup

#### 6. Dead Code Archived

```bash
# Check archive exists
ls -la /home/Bilirubin/workspace/hermes/archive/2026-05-06-day5/
```

**Expected:** Archive directory with 5 subdirectories  
**Frequency:** Once  
**Action if failed:** Run archive script

---

## 📊 Daily Monitoring Checklist

### Day 1 (2026-05-06)

- [ ] Deploy Day 4 & 5 changes
- [ ] Run automated checks
- [ ] Verify manual checks
- [ ] Document baseline metrics
- [ ] Start monitoring

### Day 2-6 (2026-05-07 to 2026-05-11)

**Daily tasks:**
- [ ] Run automated checks
- [ ] Check gateway uptime
- [ ] Check disk usage
- [ ] Check task queue
- [ ] Document any issues

### Day 7 (2026-05-12)

- [ ] Run all automated checks
- [ ] Verify all manual checks
- [ ] Review 7-day metrics
- [ ] Document gate results
- [ ] Decide: Pass or Fail

---

## 📝 Monitoring Script

Create a daily monitoring script:

```bash
#!/bin/bash
# Daily Phase 1 Gate Monitoring
# Run this script every day during the 7-day gate period

DATE=$(date +%Y-%m-%d)
LOG_FILE="/home/Bilirubin/.hermes/logs/gate_monitoring_${DATE}.log"

echo "=== Phase 1 Gate Monitoring - $DATE ===" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# 1. Check HTTP 400 loops
echo "1. Checking HTTP 400 loops..." | tee -a "$LOG_FILE"
HTTP_400_COUNT=$(sudo journalctl -u hermes-gateway --since "24 hours ago" | \
  grep -i "HTTP 400\|single tool" | wc -l)
echo "   HTTP 400 count: $HTTP_400_COUNT (expected: 0)" | tee -a "$LOG_FILE"
if [ "$HTTP_400_COUNT" -gt 0 ]; then
    echo "   ❌ FAILED: HTTP 400 loops detected" | tee -a "$LOG_FILE"
else
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# 2. Check task queue
echo "2. Checking task queue..." | tee -a "$LOG_FILE"
TASK_COUNT=$(psql -U automation -d rag -t -c "SELECT count(*) FROM agent_inbox;" | tr -d ' ')
echo "   Task count: $TASK_COUNT (expected: > 0)" | tee -a "$LOG_FILE"
if [ "$TASK_COUNT" -gt 0 ]; then
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
else
    echo "   ❌ FAILED: No tasks in queue" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# 3. Check disk usage
echo "3. Checking disk usage..." | tee -a "$LOG_FILE"
DISK_USAGE=$(df -h / | grep -E "/$" | awk '{print $5}' | sed 's/%//')
echo "   Disk usage: ${DISK_USAGE}% (expected: < 70)" | tee -a "$LOG_FILE"
if [ "$DISK_USAGE" -lt 70 ]; then
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
else
    echo "   ❌ FAILED: Disk usage too high" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# 4. Check config loads
echo "4. Checking config loads..." | tee -a "$LOG_FILE"
if python3 -c "import yaml; yaml.safe_load(open('/home/Bilirubin/.hermes/config.yaml'))" 2>&1 | tee -a "$LOG_FILE"; then
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
else
    echo "   ❌ FAILED: Config load error" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# 5. Check tests pass
echo "5. Checking tests..." | tee -a "$LOG_FILE"
cd /home/Bilirubin/workspace/hermes
if pytest tests/unit -v --tb=short 2>&1 | tee -a "$LOG_FILE"; then
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
else
    echo "   ❌ FAILED: Tests failed" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# 6. Check gateway uptime
echo "6. Checking gateway uptime..." | tee -a "$LOG_FILE"
GATEWAY_STATUS=$(sudo systemctl is-active hermes-gateway)
echo "   Gateway status: $GATEWAY_STATUS (expected: active)" | tee -a "$LOG_FILE"
if [ "$GATEWAY_STATUS" = "active" ]; then
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
else
    echo "   ❌ FAILED: Gateway not active" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Summary
echo "=== Summary ===" | tee -a "$LOG_FILE"
echo "Date: $DATE" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Review the log for any failures and take action immediately." | tee -a "$LOG_FILE"
```

**Save as:** `/home/Bilirubin/workspace/hermes/scripts/gate_monitoring.sh`

**Make executable:**
```bash
chmod +x /home/Bilirubin/workspace/hermes/scripts/gate_monitoring.sh
```

**Run daily:**
```bash
bash /home/Bilirubin/workspace/hermes/scripts/gate_monitoring.sh
```

---

## 📈 Metrics to Track

### System Metrics

| Metric | Day 1 | Day 2 | Day 3 | Day 4 | Day 5 | Day 6 | Day 7 |
|--------|-------|-------|-------|-------|-------|-------|-------|
| HTTP 400 count | | | | | | | |
| Task count | | | | | | | |
| Disk usage (%) | | | | | | | |
| Gateway uptime | | | | | | | |
| Tests passing | | | | | | | |

### Issue Tracking

| Date | Issue | Severity | Action Taken | Resolved |
|------|-------|----------|--------------|----------|
| | | | | |

---

## 🚨 Failure Scenarios

### Scenario 1: HTTP 400 Loops Detected

**Symptoms:**
- HTTP 400 count > 0
- Gateway logs show retry loops

**Actions:**
1. Check provider status
2. Review model_router.py logs
3. Verify safe mode is working
4. Fix immediately before continuing

**Gate Decision:** FAIL - Fix and restart 7-day period

### Scenario 2: Tasks Lost on Restart

**Symptoms:**
- Task count drops to 0 after restart
- Tasks not persisting in database

**Actions:**
1. Check database connection
2. Verify schema is applied
3. Check task_orchestrator.py logs
4. Fix immediately before continuing

**Gate Decision:** FAIL - Fix and restart 7-day period

### Scenario 3: Disk Usage > 70%

**Symptoms:**
- Disk usage exceeds 70%
- Automatic cleanup not working

**Actions:**
1. Run manual cleanup
2. Check logrotate config
3. Check cron jobs
4. Verify automatic cleanup is running

**Gate Decision:** WARN - Fix and continue monitoring

### Scenario 4: Tests Failing

**Symptoms:**
- One or more tests failing
- Test coverage drops

**Actions:**
1. Review test logs
2. Fix failing tests
3. Verify all tests pass
4. Continue monitoring

**Gate Decision:** FAIL - Fix and restart 7-day period

### Scenario 5: Gateway Manual Restart

**Symptoms:**
- Gateway required manual restart
- Uptime < 7 days

**Actions:**
1. Investigate why restart was needed
2. Fix root cause
3. Restart 7-day period

**Gate Decision:** FAIL - Fix and restart 7-day period

---

## ✅ Gate Pass Criteria

**ALL of the following must be true:**

1. ✅ No HTTP 400 loops for 7 days
2. ✅ Task queue works every day
3. ✅ Tasks survive restarts (tested 3+ times)
4. ✅ Disk usage < 70% every day
5. ✅ Config loads every day
6. ✅ Tests pass every day (58 tests)
7. ✅ Gateway runs 7 days without manual restart
8. ✅ No provider crashes
9. ✅ Tasks persist across restarts
10. ✅ Config is single source of truth
11. ✅ Disk usage stable or decreasing
12. ✅ Dead code archived

**If ANY criterion fails:** Gate FAILS, fix issue, restart 7-day period

---

## 📝 Gate Report Template

```markdown
# Phase 1 Gate Report

**Date:** [End date]  
**Duration:** 7 days  
**Status:** [PASS / FAIL]

## Automated Checks

| Check | Day 1 | Day 2 | Day 3 | Day 4 | Day 5 | Day 6 | Day 7 | Result |
|-------|-------|-------|-------|-------|-------|-------|-------|--------|
| HTTP 400 loops | | | | | | | | |
| Task queue | | | | | | | | |
| Disk usage | | | | | | | | |
| Config loads | | | | | | | | |
| Tests pass | | | | | | | | |
| Gateway uptime | | | | | | | | |

## Manual Verification

- [ ] Gateway ran 7 days without manual restart
- [ ] No provider crashes
- [ ] Tasks persisted across restarts
- [ ] Config is single source of truth
- [ ] Disk usage stable < 70%
- [ ] Dead code archived

## Issues Encountered

[List any issues and how they were resolved]

## Metrics

- **Total uptime:** [X days]
- **HTTP 400 count:** [X]
- **Tasks processed:** [X]
- **Disk usage range:** [X% - Y%]
- **Tests passing:** [X/58]

## Decision

[PASS / FAIL]

**Reason:** [Explanation]

**Next Steps:** [Proceed to Phase 2 / Fix issues and restart gate]
```

---

## 🚀 Next Steps After Gate Pass

### 1. Document Results

- Create gate report
- Document metrics
- Archive logs

### 2. Celebrate

- Phase 1 complete and verified! 🎉
- System is stable and reliable
- Ready for Phase 2

### 3. Proceed to Phase 2

- Review Phase 2 plan
- Prepare Phase 2 environment
- Start Phase 2: Make it Observable

---

## 📚 Related Documentation

- [PHASE1_COMPLETE.md](../PHASE1_COMPLETE.md) - Phase 1 completion
- [PHASE1_PROGRESS_SUMMARY.md](PHASE1_PROGRESS_SUMMARY.md) - Phase 1 progress
- [docs/architecture/REALISTIC_EXECUTION_PLAN.md](docs/architecture/REALISTIC_EXECUTION_PLAN.md) - Full execution plan

---

**Last Updated:** 2026-05-06  
**Status:** Ready to start  
**Duration:** 7 days
