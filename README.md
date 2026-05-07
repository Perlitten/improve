# 🤖 Hermes — AI Agent Infrastructure

Autonomous infrastructure for AI agents with long-term memory, automatic monitoring, and self-healing capabilities.

## 🏗️ Architecture

### Core Components

- **Hermes Gateway** (port 8642) — Agent API and request handling
- **Hermes Dashboard** (port 9119) — Web UI for monitoring
- **Brain MCP** (port 8791) — Model Context Protocol control plane
- **n8n** (port 5678) — Workflow automation engine
- **PostgreSQL** — Long-term memory (database `rag`)
- **Monitoring** — Automatic health checks and self-healing

### Services

| Service | Port | Purpose |
|---------|------|---------|
| `hermes-gateway` | 8642 | Agent API |
| `hermes-dashboard` | 9119 | Web UI |
| `brain-mcp` | 8791 | MCP control plane |
| `n8n` | 5678 | Workflow automation |
| `automation-gateway` | 8788 | Orchestration webhooks |
| `nginx` | 80/443 | Reverse proxy |

---

## 📁 Project Structure

```
hermes/
├── src/                     # Core source code
│   ├── hermes_core/         # Main Hermes implementation
│   ├── brain_mcp_server.py  # MCP server
│   ├── model_router.py      # Provider routing
│   ├── canonical_memory.py  # Memory management
│   └── *.sh                 # Server-side scripts
│
├── deploy/                  # Deployment tools
│   ├── sync_to_server.ps1   # Direct file sync (recommended)
│   ├── deploy_to_server.ps1 # Git-based deployment
│   ├── quick_fix.ps1        # Quick server commands
│   ├── test_connection.ps1  # Connection testing
│   └── .deploy-config       # Server credentials (not in Git)
│
├── docs/                    # Documentation
│   ├── hermes-recovery/     # Recovery guides
│   ├── architecture/        # Architecture docs
│   └── history/             # Completed phases
│
├── services/                # Systemd service files
│   ├── *.service            # Service definitions
│   ├── *.timer              # Timer definitions
│   └── prometheus.yml       # Monitoring config
│
├── config/                  # Configuration files
│   ├── model_capabilities.json  # Model capabilities
│   └── soul_append.txt          # Agent personality
│
├── scripts/                 # Executable scripts
│   └── run_agent.py         # Agent runner
│
├── tools/                   # Development utilities
│   ├── extract.py           # Code extraction
│   ├── token_usage_analysis.py  # Token analysis
│   └── *.py                 # Other utilities
│
├── reports/                 # Status reports
│   └── *.md                 # Phase completion reports
│
├── nim/                     # NIM orchestrator (experimental)
│   └── nim_orchestrator.py  # Multi-agent orchestration
│
├── temp/                    # Temporary files (not in Git)
│   └── *.json               # Test results, analysis
│
├── hermes_constants.py      # Global constants
├── utils.py                 # Shared utilities
├── .hermes.md               # Agent instructions
└── README.md                # This file
```

---

## 🚀 Quick Start

### 1. Configure Deployment

```powershell
# Edit server connection details
notepad deploy\.deploy-config
```

Update with your server details:
```json
{
    "server_host": "user@your-server-ip",
    "server_path": "/home/user/workspace",
    "server_user": "user"
}
```

### 2. Deploy to Server

```powershell
# Direct file sync (recommended)
.\deploy\sync_to_server.ps1

# Or Git-based deployment
.\deploy\deploy_to_server.ps1 -Message "Initial deployment"
```

### 3. Verify Deployment

```powershell
# Test connection
.\deploy\test_connection.ps1

# Check service status
.\deploy\quick_fix.ps1 -ShowLogs

# Check health
.\deploy\quick_fix.ps1 -Command "/home/Bilirubin/workspace/host_checklist.sh"
```

---

## 🔧 Deployment

### Quick Commands

```powershell
# Deploy changes
.\deploy\sync_to_server.ps1

# View logs
.\deploy\quick_fix.ps1 -ShowLogs

# Restart service
.\deploy\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp"

# Check database
.\deploy\quick_fix.ps1 -Command "/home/Bilirubin/workspace/db_checklist.sh"

# Run diagnostics
.\deploy\quick_fix.ps1 -Command "/home/Bilirubin/workspace/agent_readiness_check.sh"
```

### Deployment Options

**Option 1: Direct File Sync** (Recommended)
- Fast and simple
- No Git conflicts
- Use: `.\deploy\sync_to_server.ps1`

**Option 2: Git Push + Pull**
- Version control
- Commit history
- Use: `.\deploy\deploy_to_server.ps1`

**📚 Full Guide:** [docs/hermes-recovery/DEPLOY_CHEATSHEET.md](docs/hermes-recovery/DEPLOY_CHEATSHEET.md)

---

## 🔍 Hermes Recovery

### Current Issues

1. **Provider fallback loop** — HTTP 400 on rate limit crashes gateway
2. **Session reset** — Requires manual /resume after restart
3. **Message interruption** — New messages interrupt current tasks
4. **MCP reconnect** — Requires gateway restart

### Recovery Steps

**Phase 1: Emergency Patch** (+5 min)
- Disable incompatible NVIDIA llama fallback
- Prevent HTTP 400 crash loop
- **Guide:** [docs/hermes-recovery/HERMES_EMERGENCY_PATCH.md](docs/hermes-recovery/HERMES_EMERGENCY_PATCH.md)

**Phase 2: Provider Capability Router** (+30 min)
- Smart model selection based on capabilities
- Proper fallback handling with rate limit awareness
- **Guide:** [docs/hermes-recovery/HERMES_PHASE_9_9_PROVIDER_ROUTER.md](docs/hermes-recovery/HERMES_PHASE_9_9_PROVIDER_ROUTER.md)

**Phase 3: Reliable Agent Runtime** (+2 hours)
- Persistent message queue
- Auto-resume after restart
- Checkpoint system for long-running tasks
- **Guide:** [docs/hermes-recovery/HERMES_PHASE_10_0_RELIABLE_RUNTIME.md](docs/hermes-recovery/HERMES_PHASE_10_0_RELIABLE_RUNTIME.md)

**📚 Full Recovery Guide:** [docs/hermes-recovery/HERMES_RECOVERY_CHECKLIST.md](docs/hermes-recovery/HERMES_RECOVERY_CHECKLIST.md)

---

## 📊 Monitoring

### Automatic Checks

- **Health Loop** — Hourly service health checks (`infra-health-loop.timer`)
- **Infra Snapshot** — Hourly infrastructure snapshots (`infra-snapshot.timer`)
- **Self Monitor** — System health monitoring (`hermes-self-monitor.timer`)
- **Auto Remediation** — Automatic service restart on failure

### Manual Checks

```bash
# Service status
systemctl status brain-mcp hermes-gateway n8n

# View logs
journalctl -u brain-mcp -n 50 -f
journalctl -u infra-health-loop -f

# Restart services
sudo systemctl restart brain-mcp
sudo systemctl restart hermes-gateway
sudo systemctl daemon-reload
```

### Prometheus Metrics

- Node Exporter: `http://localhost:9100/metrics`
- Prometheus UI: `http://localhost:9090`

---

## 🗄️ Database

### Structure

**Database: `rag`** — Long-term memory
- `workspaces` — Workspace definitions
- `projects` — Project metadata
- `artifacts` — Code artifacts
- `artifact_versions` — Version history
- `rag_documents` — Searchable documents
- `insights` — Generated insights
- `infra_snapshots` — Infrastructure state snapshots

**Database: `n8n`** — Workflow runtime state

### RAG Collections

- `host-state` — Current host state
- `host-insights` — Host analysis and insights
- `host-optimization` — Optimization recommendations
- `obsidian-main` — Obsidian vault content
- `obsidian-rules` — Obsidian rules and guidelines

### Database Operations

```bash
# Check database
/home/Bilirubin/workspace/db_checklist.sh

# Connect to PostgreSQL
docker exec -it automation-postgres psql -U postgres -d rag

# Backup database
docker exec automation-postgres pg_dump -U postgres rag > backup.sql
```

---

## 🧠 Brain MCP Server

Model Context Protocol server providing:

- **Memory Management** — Long-term memory storage and retrieval
- **RAG Search** — Semantic search across collections
- **Workspace Management** — Project and artifact tracking
- **Infrastructure Monitoring** — System health and optimization

### MCP Tools

- `create_workspace` — Create new workspace
- `create_project` — Create project in workspace
- `store_artifact` — Store code artifact
- `search_rag` — Semantic search
- `get_insights` — Retrieve insights
- `snapshot_infra` — Capture infrastructure state

### Configuration

```bash
# Service file
/etc/systemd/system/brain-mcp.service

# Logs
journalctl -u brain-mcp -f

# Restart
sudo systemctl restart brain-mcp
```

---

## 🔐 Security

### Credentials

- **DON'T commit** `deploy/.deploy-config` (contains SSH credentials)
- **DON'T commit** `.env` files
- **USE** SSH keys instead of passwords
- **VERIFY** changes before deploying

### Best Practices

```powershell
# Always dry-run first
.\deploy\deploy_to_server.ps1 -DryRun

# Check changes
git status
git diff

# Make backups
.\deploy\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git branch backup-$(date +%Y%m%d)"
```

---

## 📚 Documentation

### Getting Started

- [READY_START_HERE.md](docs/hermes-recovery/READY_START_HERE.md) — Start here!
- [DEPLOY_NOW.md](docs/hermes-recovery/DEPLOY_NOW.md) — Quick deployment guide
- [DEPLOY_CHEATSHEET.md](docs/hermes-recovery/DEPLOY_CHEATSHEET.md) — Command reference

### Recovery

- [HERMES_RECOVERY_CHECKLIST.md](docs/hermes-recovery/HERMES_RECOVERY_CHECKLIST.md) — Step-by-step recovery
- [HERMES_EMERGENCY_PATCH.md](docs/hermes-recovery/HERMES_EMERGENCY_PATCH.md) — Emergency fix
- [HERMES_PHASE_9_9_PROVIDER_ROUTER.md](docs/hermes-recovery/HERMES_PHASE_9_9_PROVIDER_ROUTER.md) — Provider router
- [HERMES_PHASE_10_0_RELIABLE_RUNTIME.md](docs/hermes-recovery/HERMES_PHASE_10_0_RELIABLE_RUNTIME.md) — Reliable runtime

### Architecture

- [architecture/orchestration_gateway_design.md](docs/architecture/orchestration_gateway_design.md) — Gateway design
- [architecture/SESSION_LOGGING.md](docs/architecture/SESSION_LOGGING.md) — Session logging
- [architecture/infrastructure_improvements.md](docs/architecture/infrastructure_improvements.md) — Infrastructure improvements

### Completed Phases

- [history/PHASE_9_BACKUP_RESTORE_COMPLETE.md](docs/history/PHASE_9_BACKUP_RESTORE_COMPLETE.md)
- [history/PHASE_9.9_PROVIDER_HOTFIX_COMPLETE.md](docs/history/PHASE_9.9_PROVIDER_HOTFIX_COMPLETE.md)
- [history/PHASE_10_OBSERVABILITY_COMPLETE.md](docs/history/PHASE_10_OBSERVABILITY_COMPLETE.md)

---

## 🆘 Troubleshooting

### Services Not Working

```powershell
# Check status
.\deploy\quick_fix.ps1 -ShowLogs

# Restart all services
.\deploy\quick_fix.ps1 -Command "sudo systemctl restart brain-mcp hermes-gateway n8n"

# View logs
.\deploy\quick_fix.ps1 -Command "sudo journalctl -u brain-mcp -n 100"
```

### Database Issues

```powershell
# Check PostgreSQL
.\deploy\quick_fix.ps1 -Command "sudo docker ps | grep postgres"

# View logs
.\deploy\quick_fix.ps1 -Command "sudo docker logs automation-postgres --tail 50"

# Restart database
.\deploy\quick_fix.ps1 -Command "sudo docker restart automation-postgres"
```

### Deployment Issues

```powershell
# Test connection
.\deploy\test_connection.ps1

# Check Git status
.\deploy\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git status"

# Rollback
.\deploy\quick_fix.ps1 -Command "cd /home/Bilirubin/workspace && git reset --hard HEAD~1"
```

### Hermes Gateway Issues

```powershell
# Check gateway logs
.\deploy\quick_fix.ps1 -Command "sudo journalctl -u hermes-gateway -n 100"

# Restart gateway
.\deploy\quick_fix.ps1 -Command "sudo systemctl restart hermes-gateway"

# Check provider status
.\deploy\quick_fix.ps1 -Command "curl http://localhost:8642/health"
```

---

## 🎯 Development

### Running Locally

```powershell
# Run agent
python scripts\run_agent.py

# Test provider router
python src\test_provider_router.py

# Run MCP server
python src\brain_mcp_server.py
```

### Tools

```powershell
# Extract code
python tools\extract.py

# Analyze token usage
python tools\token_usage_analysis.py

# Fix indentation
python tools\fix_indent.py
```

---

## 📞 Links

- **Server:** `Bilirubin@34.133.31.146:/home/Bilirubin/workspace`
- **Dashboard:** `http://34.133.31.146:9119`
- **Gateway API:** `http://34.133.31.146:8642`
- **n8n:** `http://34.133.31.146:5678`

---

## 📄 License

See LICENSE file in repository.

---

**Status:** Production  
**Last Updated:** 2026-05-05  
**Maintainer:** Hermes Infrastructure Team
