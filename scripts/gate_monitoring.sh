#!/bin/bash
# Daily Phase 1 Gate Monitoring
# Run this script every day during the 7-day gate period

DATE=$(date +%Y-%m-%d)
LOG_DIR="/home/Bilirubin/.hermes/logs"
LOG_FILE="$LOG_DIR/gate_monitoring_${DATE}.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

echo "=== Phase 1 Gate Monitoring - $DATE ===" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Track pass/fail
PASSED=0
FAILED=0

# 1. Check HTTP 400 loops
echo "1. Checking HTTP 400 loops..." | tee -a "$LOG_FILE"
HTTP_400_COUNT=$(sudo journalctl -u hermes-gateway --since "24 hours ago" 2>/dev/null | \
  grep -i "HTTP 400\|single tool" | wc -l)
echo "   HTTP 400 count: $HTTP_400_COUNT (expected: 0)" | tee -a "$LOG_FILE"
if [ "$HTTP_400_COUNT" -eq 0 ]; then
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
    ((PASSED++))
else
    echo "   ❌ FAILED: HTTP 400 loops detected" | tee -a "$LOG_FILE"
    ((FAILED++))
fi
echo "" | tee -a "$LOG_FILE"

# 2. Check task queue
echo "2. Checking task queue..." | tee -a "$LOG_FILE"
TASK_COUNT=$(psql -U automation -d rag -t -c "SELECT count(*) FROM agent_inbox;" 2>/dev/null | tr -d ' ' || echo "0")
echo "   Task count: $TASK_COUNT (expected: > 0)" | tee -a "$LOG_FILE"
if [ "$TASK_COUNT" -gt 0 ]; then
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
    ((PASSED++))
else
    echo "   ⚠️  WARNING: No tasks in queue (may be normal)" | tee -a "$LOG_FILE"
    ((PASSED++))
fi
echo "" | tee -a "$LOG_FILE"

# 3. Check disk usage
echo "3. Checking disk usage..." | tee -a "$LOG_FILE"
DISK_USAGE=$(df -h / 2>/dev/null | grep -E "/$" | awk '{print $5}' | sed 's/%//' || echo "100")
echo "   Disk usage: ${DISK_USAGE}% (expected: < 70)" | tee -a "$LOG_FILE"
if [ "$DISK_USAGE" -lt 70 ]; then
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
    ((PASSED++))
else
    echo "   ❌ FAILED: Disk usage too high" | tee -a "$LOG_FILE"
    ((FAILED++))
fi
echo "" | tee -a "$LOG_FILE"

# 4. Check config loads
echo "4. Checking config loads..." | tee -a "$LOG_FILE"
if python3 -c "import yaml; yaml.safe_load(open('/home/Bilirubin/.hermes/config.yaml'))" 2>&1 >> "$LOG_FILE"; then
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
    ((PASSED++))
else
    echo "   ❌ FAILED: Config load error" | tee -a "$LOG_FILE"
    ((FAILED++))
fi
echo "" | tee -a "$LOG_FILE"

# 5. Check tests pass
echo "5. Checking tests..." | tee -a "$LOG_FILE"
cd /home/Bilirubin/workspace/hermes
TEST_OUTPUT=$(pytest tests/unit -v --tb=short 2>&1)
TEST_RESULT=$?
echo "$TEST_OUTPUT" >> "$LOG_FILE"
if [ $TEST_RESULT -eq 0 ]; then
    TEST_COUNT=$(echo "$TEST_OUTPUT" | grep -oP '\d+ passed' | grep -oP '\d+')
    echo "   ✅ PASSED ($TEST_COUNT tests)" | tee -a "$LOG_FILE"
    ((PASSED++))
else
    echo "   ❌ FAILED: Tests failed" | tee -a "$LOG_FILE"
    ((FAILED++))
fi
echo "" | tee -a "$LOG_FILE"

# 6. Check gateway uptime
echo "6. Checking gateway uptime..." | tee -a "$LOG_FILE"
GATEWAY_STATUS=$(sudo systemctl is-active hermes-gateway 2>/dev/null || echo "unknown")
echo "   Gateway status: $GATEWAY_STATUS (expected: active)" | tee -a "$LOG_FILE"
if [ "$GATEWAY_STATUS" = "active" ]; then
    # Get uptime
    GATEWAY_UPTIME=$(sudo systemctl show hermes-gateway --property=ActiveEnterTimestamp 2>/dev/null | cut -d= -f2)
    echo "   Gateway started: $GATEWAY_UPTIME" | tee -a "$LOG_FILE"
    echo "   ✅ PASSED" | tee -a "$LOG_FILE"
    ((PASSED++))
else
    echo "   ❌ FAILED: Gateway not active" | tee -a "$LOG_FILE"
    ((FAILED++))
fi
echo "" | tee -a "$LOG_FILE"

# 7. Check Hermes directory size
echo "7. Checking Hermes directory size..." | tee -a "$LOG_FILE"
HERMES_SIZE=$(du -sh /home/Bilirubin/.hermes 2>/dev/null | awk '{print $1}')
echo "   Hermes size: $HERMES_SIZE" | tee -a "$LOG_FILE"
echo "   ℹ️  INFO (tracking only)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Summary
echo "=== Summary ===" | tee -a "$LOG_FILE"
echo "Date: $DATE" | tee -a "$LOG_FILE"
echo "Passed: $PASSED" | tee -a "$LOG_FILE"
echo "Failed: $FAILED" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

if [ $FAILED -eq 0 ]; then
    echo "✅ All checks passed!" | tee -a "$LOG_FILE"
    exit 0
else
    echo "❌ $FAILED check(s) failed. Review the log and take action immediately." | tee -a "$LOG_FILE"
    exit 1
fi
