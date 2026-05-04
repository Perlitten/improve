# MCP Control Plane

## Endpoint

The local control plane is exposed only on the VM loopback interface:

```text
http://127.0.0.1:8791/mcp/
```

It is registered in Hermes as `control_plane`.

## Purpose

Use this MCP server as the default interface for host operations. It provides typed, redacted, non-destructive tools so the agent does not need to start with raw shell, broad env dumps, or ad-hoc SQL.

## Tools

- `infra_readiness`: core service status, local health endpoints, credential presence, and memory overview
- `infra_snapshot`: latest generated infrastructure snapshot
- `refresh_infra_snapshot`: refresh host snapshot through `infra-snapshot.service`
- `service_logs`: recent logs for allowlisted services with redaction
- `memory_overview`: canonical memory counts, workspace/project groups, retrieval collections, and queryability
- `memory_search`: lexical/FTS search over `rag_documents`
- `memory_record_observation`: append-only operational memory write
- `orchestrate_tasks`: bounded Hermes fan-out orchestration with optional RAG persistence
- `n8n_status`: n8n health and aggregate DB counts without credential values
- `n8n_workflows`: read-only workflow inventory
- `n8n_recent_executions`: recent execution status without node payloads or credentials
- `model_backend_status`: OpenRouter/NVIDIA presence and NVIDIA model availability without keys
- `notion_status`: Notion token presence only

## Safety Contract

- No destructive operations are exposed.
- Secrets are redacted and only presence is reported.
- Service logs are limited to allowlisted services.
- `orchestrate_tasks` is bounded by task count and concurrency because it may spend LLM tokens.
- Public nginx should not proxy this endpoint. Keep it localhost-only unless an authenticated transport is added.

## Verification

```bash
/home/Bilirubin/.hermes/venv/bin/hermes mcp list
/home/Bilirubin/.hermes/venv/bin/hermes mcp test control_plane
/home/Bilirubin/.hermes/venv/bin/fastmcp list http://127.0.0.1:8791/mcp/ --transport http --json
```
