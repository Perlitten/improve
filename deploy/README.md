# 🚀 Hermes Deployment Scripts

Deployment scripts for pushing changes from Windows development machine to Linux production server.

---

## 📋 Prerequisites

### Windows Machine

- PowerShell 5.1 or later
- SSH client (OpenSSH)
- SCP client
- Git (optional, for git-based deployment)

### Linux Server

- SSH access configured
- Server: `Bilirubin@192.168.1.100`
- Workspace: `/home/Bilirubin/workspace/hermes`
- PostgreSQL running
- Environment file: `~/.hermes/automation.env`

---

## 🛠️ Available Scripts

### 1. `test_connection.ps1`

Test SSH connection to server.

```powershell
.\test_connection.ps1
```

**Output:**
- ✅ Connection successful
- Server info (hostname, uptime, disk usage)

---

### 2. `apply_schema.ps1`

Apply database schema changes.

```powershell
# Preview changes (dry run)
.\apply_schema.ps1 -DryRun

# Apply schema
.\apply_schema.ps1
```

**What it does:**
1. Copies SQL file to server
2. Runs `scripts/apply_schema.sh` on server
3. Verifies tables created
4. Shows table list

**Files deployed:**
- `sql/001_create_task_queue.sql`

---

### 3. `deploy_to_server.ps1`

Deploy code changes via Git.

```powershell
# Preview changes (dry run)
.\deploy_to_server.ps1 -DryRun

# Deploy
.\deploy_to_server.ps1
```

**What it does:**
1. Commits local changes
2. Pushes to remote repository
3. Pulls on server
4. Restarts services (optional)

**Best for:**
- Code changes
- Multiple file updates
- Version-controlled deployments

---

### 4. `sync_to_server.ps1`

Direct file sync via SCP (no Git).

```powershell
# Preview changes (dry run)
.\sync_to_server.ps1 -DryRun

# Sync specific file
.\sync_to_server.ps1 -File "src/task_orchestrator.py"

# Sync entire directory
.\sync_to_server.ps1 -Directory "src"

# Sync and restart service
.\sync_to_server.ps1 -File "src/model_router.py" -RestartService "hermes-gateway"
```

**What it does:**
1. Copies files directly via SCP
2. Optionally restarts service
3. Verifies deployment

**Best for:**
- Quick fixes
- Single file updates
- Testing changes

---

### 5. `quick_fix.ps1`

Quick deployment for emergency fixes.

```powershell
# Deploy single file
.\quick_fix.ps1 -File "src/model_router.py" -Service "hermes-gateway"

# Deploy and verify
.\quick_fix.ps1 -File "src/task_orchestrator.py" -Service "hermes-gateway" -Verify
```

**What it does:**
1. Backs up current file on server
2. Deploys new file
3. Restarts service
4. Verifies service health
5. Rolls back if verification fails

**Best for:**
- Emergency fixes
- Production hotfixes
- Critical bugs

---

### 6. `setup_deploy.ps1`

Initial deployment setup.

```powershell
.\setup_deploy.ps1
```

**What it does:**
1. Tests SSH connection
2. Verifies server paths
3. Checks Git repository
4. Verifies environment file
5. Tests database connection

**Run once before first deployment.**

---

## 📊 Deployment Workflow

### Standard Workflow (Git-based)

```powershell
# 1. Test connection
.\test_connection.ps1

# 2. Preview deployment
.\deploy_to_server.ps1 -DryRun

# 3. Deploy
.\deploy_to_server.ps1

# 4. Verify
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && pytest tests/ -v"
```

### Quick Fix Workflow

```powershell
# 1. Deploy fix
.\quick_fix.ps1 -File "src/model_router.py" -Service "hermes-gateway" -Verify

# 2. Monitor logs
ssh Bilirubin@192.168.1.100 "sudo journalctl -u hermes-gateway -f"
```

### Schema Update Workflow

```powershell
# 1. Preview schema
.\apply_schema.ps1 -DryRun

# 2. Apply schema
.\apply_schema.ps1

# 3. Deploy code that uses new schema
.\deploy_to_server.ps1

# 4. Run tests
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && pytest tests/unit/test_task_orchestrator.py -v"
```

---

## 🔒 Safety Features

### Dry Run Mode

All scripts support `-DryRun` flag:
- Shows what would be done
- No changes made
- Safe to run anytime

```powershell
.\deploy_to_server.ps1 -DryRun
.\sync_to_server.ps1 -DryRun
.\apply_schema.ps1 -DryRun
```

### Confirmation Prompts

Scripts prompt before:
- Applying schema changes
- Restarting services
- Deploying to production

### Backup

`quick_fix.ps1` automatically backs up files before deployment:
- Backup location: `/home/Bilirubin/workspace/hermes/backups/`
- Timestamped: `model_router.py.backup.20260505_103000`

### Rollback

If deployment fails:

```powershell
# Rollback via Git
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && git reset --hard HEAD~1"

# Restore from backup
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && cp backups/model_router.py.backup.20260505_103000 src/model_router.py"
```

---

## 🧪 Testing After Deployment

### Run All Tests

```bash
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && pytest tests/ -v"
```

### Run Specific Tests

```bash
# Model router tests
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && pytest tests/unit/test_model_router.py -v"

# Task orchestrator tests
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && pytest tests/unit/test_task_orchestrator.py -v"
```

### Check Service Status

```bash
ssh Bilirubin@192.168.1.100 "sudo systemctl status hermes-gateway"
```

### View Logs

```bash
# Real-time logs
ssh Bilirubin@192.168.1.100 "sudo journalctl -u hermes-gateway -f"

# Last 100 lines
ssh Bilirubin@192.168.1.100 "sudo journalctl -u hermes-gateway -n 100"
```

---

## 📝 Configuration

### Server Configuration

Edit scripts to change server settings:

```powershell
# In each script
$SERVER = "Bilirubin@192.168.1.100"
$REMOTE_PATH = "/home/Bilirubin/workspace/hermes"
```

### SSH Key Authentication

For passwordless deployment:

```powershell
# Generate SSH key (if not exists)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Copy to server
ssh-copy-id Bilirubin@192.168.1.100
```

---

## 🚨 Troubleshooting

### Connection Failed

```powershell
# Test connection
.\test_connection.ps1

# Check SSH config
ssh -v Bilirubin@192.168.1.100
```

### Permission Denied

```bash
# On server, check file permissions
ls -la /home/Bilirubin/workspace/hermes/

# Fix permissions
chmod +x /home/Bilirubin/workspace/hermes/scripts/*.sh
```

### Service Won't Start

```bash
# Check service status
sudo systemctl status hermes-gateway

# Check logs
sudo journalctl -u hermes-gateway -n 50

# Check config
cat ~/.hermes/automation.env
```

### Schema Apply Failed

```bash
# Check database connection
source ~/.hermes/automation.env
PGPASSWORD=$POSTGRES_PASSWORD psql -h 127.0.0.1 -U $POSTGRES_USER -d rag -c '\dt'

# Check SQL syntax
cat sql/001_create_task_queue.sql
```

---

## 📚 Examples

### Example 1: Deploy Provider Routing Fix

```powershell
# 1. Test locally
cd hermes
pytest tests/unit/test_model_router.py -v

# 2. Deploy
cd deploy
.\deploy_to_server.ps1

# 3. Verify on server
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && pytest tests/unit/test_model_router.py -v"

# 4. Restart service
ssh Bilirubin@192.168.1.100 "sudo systemctl restart hermes-gateway"

# 5. Monitor
ssh Bilirubin@192.168.1.100 "sudo journalctl -u hermes-gateway -f"
```

### Example 2: Deploy Task Queue

```powershell
# 1. Apply schema
cd deploy
.\apply_schema.ps1

# 2. Deploy code
.\deploy_to_server.ps1

# 3. Run tests
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && pytest tests/unit/test_task_orchestrator.py -v"

# 4. Verify queue works
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && python3 src/task_orchestrator.py"
```

### Example 3: Emergency Hotfix

```powershell
# 1. Quick fix
cd deploy
.\quick_fix.ps1 -File "src/model_router.py" -Service "hermes-gateway" -Verify

# 2. If failed, rollback
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && ls -lt backups/ | head -5"
ssh Bilirubin@192.168.1.100 "cd /home/Bilirubin/workspace/hermes && cp backups/model_router.py.backup.TIMESTAMP src/model_router.py"
ssh Bilirubin@192.168.1.100 "sudo systemctl restart hermes-gateway"
```

---

## ✅ Best Practices

1. **Always test locally first**
   ```powershell
   pytest tests/ -v
   ```

2. **Use dry run before deployment**
   ```powershell
   .\deploy_to_server.ps1 -DryRun
   ```

3. **Deploy during low-traffic periods**
   - Avoid peak hours
   - Schedule maintenance windows

4. **Monitor after deployment**
   ```bash
   sudo journalctl -u hermes-gateway -f
   ```

5. **Keep backups**
   - Automatic backups in `backups/`
   - Manual backups before major changes

6. **Test after deployment**
   ```bash
   pytest tests/ -v
   ```

7. **Document changes**
   - Update CHANGELOG.md
   - Update progress reports

---

## 📞 Support

If deployment fails:

1. Check logs: `sudo journalctl -u hermes-gateway -n 100`
2. Check service: `sudo systemctl status hermes-gateway`
3. Rollback if needed
4. Review deployment scripts
5. Test connection: `.\test_connection.ps1`

---

**Last Updated:** 2026-05-05  
**Version:** 1.0.0

