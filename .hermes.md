# Workspace Context

This workspace is the control plane for the cloud server behind this Hermes instance.

## Operating Mode

- You may use the host machine, installed CLIs, system services, Docker, Postgres, n8n, nginx, and local files when the user asks for real work.
- You may install new tools, packages, skills, scripts, services, and automations when they are needed for the user's request.
- You may extend your own capabilities by creating or updating Hermes skills, scripts, and workspace docs when that helps future tasks.

## Destructive-Change Rule

You must not delete, purge, drop, truncate, uninstall, wipe, revoke, or permanently disable anything unless the user explicitly confirms that destructive action in the current conversation.

Examples that require explicit confirmation:
- removing files or directories
- uninstalling packages or tools
- dropping databases or tables
- deleting Docker containers, images, or volumes
- disabling or deleting systemd services
- rotating or deleting credentials
- overwriting user content in a way that is not reversible

If a destructive action is needed, ask one short confirmation question first.

## Secret Hygiene

Never print secret values back to the user or into durable memory.

Treat these as secrets:
- variables containing `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `PASS`, `PRIVATE`, `ENCRYPTION`, `CREDENTIAL`
- raw `.env` file contents
- database passwords
- bearer tokens and bot tokens

When checking credentials, report only whether a key is present and which service it belongs to. Redact values as `***`.
Do not run broad `env`, `printenv`, or raw `.env` dumps unless the output is filtered and redacted.

## Tool Discipline

Default to the local MCP control plane before raw shell exploration. It is the primary typed interface for host, memory, n8n, model backend, and orchestration work.

Use the `control_plane` MCP server first for agent-facing operations:

**Infrastructure:**
- `mcp_control_plane_infra_readiness` — сервисы + endpoints + кредо + память за один вызов
- `mcp_control_plane_infra_snapshot` — последний снепшот хоста
- `mcp_control_plane_refresh_infra_snapshot` — обновить снепшот
- `mcp_control_plane_service_logs` — логи любого из разрешённых сервисов

**Память:**
- `mcp_control_plane_memory_overview` — счётчики, воркспейсы, коллекции
- `mcp_control_plane_memory_search` — поиск по rag_documents
- `mcp_control_plane_memory_record_observation` — записать наблюдение (additive, non-destructive)

**n8n:**
- `mcp_control_plane_n8n_status` — здоровье + статистика выполнений
- `mcp_control_plane_n8n_workflows` — список workflows
- `mcp_control_plane_n8n_recent_executions` — последние запуски

**Провайдеры:**
- `mcp_control_plane_model_backend_status` — статус ключей OpenRouter/NVIDIA
- `mcp_control_plane_provider_health_check` — ЖИВОЙ тест: пинг к OpenRouter и NVIDIA с замером latency. Вызывай ПЕРВЫМ при APIError или зависании провайдера.
- `mcp_control_plane_notion_status` — присутствие Notion токена

**Оркестрация:**
- `mcp_control_plane_orchestrate_tasks` — запустить fan-out задачи через Hermes sub-agents

Use script checklists only when MCP does not answer the question or when validating MCP output:
- `/home/Bilirubin/workspace/agent_readiness_check.sh`
- `/home/Bilirubin/workspace/host_checklist.sh`
- `/home/Bilirubin/workspace/db_checklist.sh`

Use raw shell only when the curated tool does not answer the question or when debugging a specific failure.
Prefer narrow commands that answer one question. Avoid broad recursive scans and noisy environment dumps.

## Autonomous Capabilities Already Running

These systems run without any user or agent intervention. Do not recreate them.

### Self-Healing Loop (systemd, every 15 min)
- `infra-health-loop.timer` → `/usr/local/bin/health_optimization_loop.py`
- Automatically restarts any inactive service from: hermes-gateway, hermes-dashboard, n8n, automation-gateway, brain-mcp, nginx, node-exporter, prometheus
- Also restarts `automation-postgres` Docker container if unhealthy
- Checks OpenRouter and NVIDIA connectivity; sends Telegram alert if any provider is down
- Writes results to Postgres (`host-optimization` collection) and sends Telegram on warn/critical

### Self-Monitoring Cron Jobs (Hermes gateway, active)
- `self-monitor` (*/15 * * * *) — calls infra_readiness + provider_health_check, records observations to memory
- `provider-watchdog` (*/30 * * * *) — calls provider_health_check, records alert if provider failing

To inspect: `hermes cron list`. Do not add duplicate jobs with the same name.

### n8n Self-Healing Workflow
- Name: "Self-Healing Loop", ID: 998d7d39-2d9b-4952-8326-4f37da5c4374 (currently inactive — activate via n8n UI)
- Runs every 15 min via schedule trigger, calls infra_readiness + provider_health_check, triggers orchestrate_tasks if problems found

### Monitoring Stack
- Prometheus: `http://127.0.0.1:9090` — scrapes node_exporter (9100), n8n (5678/metrics), hermes (8642/metrics)
- node_exporter: `http://127.0.0.1:9100/metrics` — 610+ host metrics
- n8n metrics: `http://127.0.0.1:5678/metrics` — 72+ workflow/execution metrics

### Memory Topology
Canonical layer (SQL): `rag.workspaces`, `rag.projects`, `rag.artifacts`, `rag.insights`
Retrieval layer (rag_documents collections):
- `host-state` — latest host snapshot
- `host-optimization` — health loop reports (latest + history)
- `host-insights` — anomaly events and auto-remediation records
- `obsidian-main` — imported Obsidian vault notes
- `obsidian-rules` — behavioral rules from Obsidian

## Host Truth Source

When a user asks about:
- the server or infrastructure you are running on
- deployed tools like Hermes, n8n, Postgres, nginx, automation-gateway, or Kilo
- available endpoints, ports, paths, or service status

read `/workspace/INFRASTRUCTURE.md` first and treat it as the host-level source of truth.
For server maintenance and optimization work, load and follow the `server-ops` skill first.
For ambiguous prompts like `check`, `study the server`, `what do you have access to`, or `inspect your environment`, run `/home/Bilirubin/workspace/host_checklist.sh` before making claims.
For questions about memory, Postgres, migrations, projects already stored in the database, or long-term storage design, run `/home/Bilirubin/workspace/db_checklist.sh` and read `/home/Bilirubin/workspace/POSTGRES_MEMORY.md` before answering.

When MCP is available, replace those raw checklist starts with the equivalent MCP calls:
- server baseline: `mcp_control_plane_infra_readiness`
- latest snapshot: `mcp_control_plane_infra_snapshot`
- memory baseline: `mcp_control_plane_memory_overview`
- n8n baseline: `mcp_control_plane_n8n_status`
- model/backend baseline: `mcp_control_plane_model_backend_status`

For recent historical state and operational memory, use the Postgres-backed external memory:
- `host-state` for the latest summarized host snapshot
- `host-insights` for notable changes, pressure signals, and anomalies over time
- `host-optimization` for concrete improvement suggestions and health-loop reports

For canonical long-term memory, prefer the normalized Postgres layer in `rag`:
- `workspaces`
- `projects`
- `artifacts`
- `artifact_versions`
- `ingestion_jobs`
- `insights`

## Current Host Facts

Use these as the default factual baseline unless a newer snapshot contradicts them:
- Cloud: Google Cloud Platform (GCP)
- GCP Project: `project-331ea79e-323c-4fbd-b1c`
- GCP Billing account: `0165FC-821098-D42D65`
- Budget alert: Career Odyssey Guardrail 20 (thresholds: 25/50/90/100%)
- VM name in GCP: `career-odyssey-vm` (GCP resource name — cannot be changed without recreating)
- Internal project name: **Hermes Server** (slug: `hermes_server`)
- Zone: `us-central1-a`
- Machine type: `e2-small` (2 vCPU, 2 GB RAM)
- OS: `Debian 12`
- Public IP: `34.133.31.146` (ephemeral — no reserved/static IP)
- Owner email: `the.career.odyssey@gmail.com`
- Public routes: `/`, `/orchestrate`, `/rag-search`
- Core services expected on host: `hermes-gateway`, `hermes-dashboard`, `n8n`, `automation-gateway`, `brain-mcp`, `nginx`, `docker`, `prometheus`, `node-exporter`
- Local MCP control plane: `http://127.0.0.1:8791/mcp/`
- Database expected on host: Postgres with pgvector, local bind `127.0.0.1:5432`
- Canonical memory workspaces expected: `dev_projects_graph`, `agent_ops`, `life_core`, `strategy_hub`, `infra_ops`
- Retrieval collections expected: `host-state`, `host-insights`, `host-optimization`, `obsidian-main`, `obsidian-rules`

## Important Distinctions

If terminal output conflicts with `/workspace/INFRASTRUCTURE.md`, explain the difference clearly instead of assuming the host service is missing. Prefer the snapshot for host-level facts unless it is stale.
Do not conclude that `n8n` is absent just because it does not appear in `docker ps`. On this host, `n8n` is expected to run as a `systemd` service and must be checked with `systemctl` and `http://127.0.0.1:5678/healthz/readiness`.
Do not invent Postgres schemas, users, databases, passwords, or existing tables. Inspect first, then propose additive changes.
Do not confuse canonical SQL table `insights` with retrieval collection `host-insights`.

## Failure Recovery Protocol

### When MCP control plane is unavailable

If any `mcp_control_plane_*` call returns an error or times out:

1. Check brain-mcp service: `sudo systemctl is-active brain-mcp`
2. If inactive, restart: `sudo systemctl start brain-mcp`
3. Verify: `curl -fsS http://127.0.0.1:8791/mcp/` — should return 200
4. While brain-mcp is down, fall back to shell checklists:
   - Host state: `/home/Bilirubin/workspace/host_checklist.sh`
   - Memory: `/home/Bilirubin/workspace/db_checklist.sh`
   - Full readiness: `/home/Bilirubin/workspace/agent_readiness_check.sh`
5. **Never conclude a service is absent** just because MCP is unavailable — the service may still be running.

### When a provider returns APIError or drops the streaming connection

1. Call `mcp_control_plane_provider_health_check` to identify which providers are alive.
2. If the current model provider is failing and another is healthy:
   - Report to user which provider is down and which is available.
   - Ask user to update `~/.hermes/config.yaml` model section, or do it yourself with explicit user confirmation.
3. If all providers are failing:
   - Check network: `curl -fsS https://openrouter.ai/api/v1/models` (presence test only, output truncated).
   - Report outcome to user and wait — do not loop indefinitely on broken providers.
4. Never retry a streaming request that has already failed 3 times without first running `provider_health_check`.

### Self-investigation baseline

When asked to inspect yourself or the server, always run in this order:
1. `mcp_control_plane_infra_readiness` — services + endpoints + memory in one call
2. `mcp_control_plane_infra_snapshot` — last snapshot
3. `mcp_control_plane_memory_overview` — canonical memory counts
4. Only after those: fallback shell scripts if anything is missing or MCP is down.

Do not run broad `ls`, `env`, or `find` scans as first moves. Start with curated MCP tools.

## Answering Style

- Prefer short, clean sections instead of noisy bullet spam.
- Start with the current host summary.
- Then mention service status and any operational caveats.
- If `INFRASTRUCTURE.md` is older than 10 minutes, mention that the snapshot may be stale.
- When asked to optimize the server, look for obvious pressure first: service failures, low memory, high disk usage, broken endpoints, or repeated insight events.
