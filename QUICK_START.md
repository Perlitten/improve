# 🚀 Hermes Quick Start Guide

Quick reference for deploying and testing Hermes changes.

---

## 📋 Prerequisites

- Windows machine with PowerShell
- SSH access to server: `Bilirubin@192.168.1.100`
- Server workspace: `/home/Bilirubin/workspace/hermes`

---

## 🎯 Common Tasks

### 1. Deploy Schema Changes

```powershell
# From Windows
cd hermes/deploy

# Preview
.\apply_schema.ps1 -DryRun

# Apply
.\apply_schema.ps1
```

### 2. Deploy Code Changes

```powershell
# From Windows
cd hermes/deploy

# Preview
.\deploy_to_server.ps1 -DryRun

# Deploy
.\deploy_to_server.ps1
```

### 3. Quick Fix (Emergency)

```powershell
# From Windows
cd hermes/deploy

# Deploy single file
.\quick_fix.ps1 -File "src/model_router.py" -Service "hermes-gateway" -Verify
```

### 4. Run Tests

```bash
# On server
cd /home/Bilirubin/workspace/hermes

# All tests
pytest tests/ -v

# Specific module
pytest tests/unit/test_model_router.py -v
pytest tests/unit/test_task_orchestrator.py -v

# With coverage
pytest --cov=src --cov-report=html
```

### 5. Check Service Status

```bash
# Status
sudo systemctl status hermes-gateway

# Logs (real-time)
sudo journalctl -u hermes-gateway -f

# Logs (last 100 lines)
sudo journalctl -u hermes-gateway -n 100

# Restart
sudo systemctl restart hermes-gateway
```

### 6. Check Task Queue

```bash
# On server
cd /home/Bilirubin/workspace/hermes

# Queue depth
python3 -c "from src.task_orchestrator import TaskOrchestrator; print(f'Queue depth: {TaskOrchestrator().get_queue_depth()}')"

# View inbox
source ~/.hermes/automation.env
PGPASSWORD=$POSTGRES_PASSWORD psql -h 127.0.0.1 -U $POSTGRES_USER -d rag -c \
  "SELECT id, source, priority, status, created_at FROM agent_inbox ORDER BY id DESC LIMIT 10;"

# View tasks
PGPASSWORD=$POSTGRES_PASSWORD psql -h 127.0.0.1 -U $POSTGRES_USER -d rag -c \
  "SELECT id, task_type, status, retry_count, started_at FROM agent_tasks ORDER BY id DESC LIMIT 10;"
```

### 7. Test Task Persistence

```bash
# On server
cd /home/Bilirubin/workspace/hermes

# Create test task
python3 src/task_orchestrator.py

# Verify in database
source ~/.hermes/automation.env
PGPASSWORD=$POSTGRES_PASSWORD psql -h 127.0.0.1 -U $POSTGRES_USER -d rag -c \
  "SELECT COUNT(*) FROM agent_tasks;"
```

---

## 🔍 Troubleshooting

### Connection Issues

```powershell
# Test connection
cd hermes/deploy
.\test_connection.ps1
```

### Service Won't Start

```bash
# Check status
sudo systemctl status hermes-gateway

# Check logs
sudo journalctl -u hermes-gateway -n 50

# Check config
cat ~/.hermes/automation.env
```

### Tests Failing

```bash
# Install dependencies
pip install -r requirements-test.txt

# Run with verbose output
pytest tests/ -v -s

# Run specific test
pytest tests/unit/test_model_router.py::TestModelRouter::test_select_model_primary_available -v
```

### Database Issues

```bash
# Check connection
source ~/.hermes/automation.env
PGPASSWORD=$POSTGRES_PASSWORD psql -h 127.0.0.1 -U $POSTGRES_USER -d rag -c '\dt'

# Check tables
PGPASSWORD=$POSTGRES_PASSWORD psql -h 127.0.0.1 -U $POSTGRES_USER -d rag -c '\dt agent_*'

# Check data
PGPASSWORD=$POSTGRES_PASSWORD psql -h 127.0.0.1 -U $POSTGRES_USER -d rag -c \
  "SELECT COUNT(*) FROM agent_inbox;"
```

---

## 📚 Documentation

- **Phase 1 Progress:** [PHASE1_PROGRESS_SUMMARY.md](PHASE1_PROGRESS_SUMMARY.md)
- **Day 1 Details:** [WEEK1_DAY1_PROGRESS.md](WEEK1_DAY1_PROGRESS.md)
- **Day 2 Details:** [WEEK1_DAY2_PROGRESS.md](WEEK1_DAY2_PROGRESS.md)
- **Deployment Guide:** [deploy/README.md](deploy/README.md)
- **Architecture:** [docs/architecture/REALISTIC_EXECUTION_PLAN.md](docs/architecture/REALISTIC_EXECUTION_PLAN.md)

---

## ✅ Verification Checklist

After deployment:

- [ ] Tests pass: `pytest tests/ -v`
- [ ] Service running: `sudo systemctl status hermes-gateway`
- [ ] No errors in logs: `sudo journalctl -u hermes-gateway -n 50`
- [ ] Task queue works: Check queue depth
- [ ] Database accessible: Check tables exist

---

**Last Updated:** 2026-05-05

