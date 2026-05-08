#!/usr/bin/env python3
import json
import os
import base64
import re
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import Json, RealDictCursor
from fastmcp import FastMCP

import sys

sys.path.insert(0, "/usr/local/bin")
from canonical_memory import ensure_project, ensure_schema, ensure_workspace, record_insight  # noqa: E402


WORKSPACE = Path("/home/Bilirubin/workspace")
AUTOMATION_ENV = Path("/srv/automation/.env")
HERMES_ENV = Path("/home/Bilirubin/.hermes/.env")
N8N_ENV = Path("/srv/automation/n8n.env")
SNAPSHOT_JSON = WORKSPACE / ".agent-state" / "infra_snapshot.json"

ALLOWED_SERVICES = {
    "hermes-gateway",
    "hermes-dashboard",
    "n8n",
    "automation-gateway",
    "brain-mcp",
    "nginx",
    "docker",
    "infra-snapshot",
    "infra-health-loop",
    "prometheus",
    "node-exporter",
    "ralph",
}

SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS", "PRIVATE", "ENCRYPTION", "CREDENTIAL")
_PG_POOLS: dict[tuple[str, str, int, str, str], ThreadedConnectionPool] = {}


mcp = FastMCP(
    "career-odyssey-control-plane",
    instructions=(
        "Curated control-plane tools for the Career Odyssey VM. "
        "Tools are intentionally narrow, redacted, and non-destructive."
    ),
)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def redact_text(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"sk-or-v1-[A-Za-z0-9_-]{12,}", "sk-or-v1-***", text)
    text = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-***", text)
    text = re.sub(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b", "***telegram-token***", text)
    text = re.sub(r"(?i)\b(postgres(?:ql)?|mysql|redis)://[^\s'\"]+", r"\1://***", text)
    text = re.sub(r"(?i)(password|token|secret|api[_-]?key|encryption[_-]?key|client[_-]?secret|refresh[_-]?token)=([^\\s]+)", r"\1=***", text)
    text = re.sub(r"(?i)(password|token|secret|api[_-]?key|encryption[_-]?key)=([^\\s]+)", r"\1=***", text)
    return text


def redacted_env_presence(path: Path) -> dict[str, Any]:
    values = read_env(path)
    keys = sorted(k for k in values if any(marker in k.upper() for marker in SECRET_MARKERS))
    return {"path": str(path), "exists": path.exists(), "secret_like_keys": keys}


def run_cmd(args: list[str], timeout: int = 20) -> dict[str, Any]:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": redact_text((proc.stdout or "").strip()),
        "stderr": redact_text((proc.stderr or "").strip()),
    }


def run_json_script(script: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    result = run_cmd(["python3", script, encoded], timeout=timeout)
    if not result["ok"]:
        return {"ok": False, "error": "script_failed", "detail": result}
    try:
        return json.loads(result["stdout"] or "{}")
    except Exception as exc:
        return {"ok": False, "error": "invalid_script_json", "detail": redact_text(str(exc)), "stdout": result["stdout"]}


def _get_pg_pool(dbname: str = "rag") -> ThreadedConnectionPool:
    env = read_env(AUTOMATION_ENV)
    key = (
        env.get("POSTGRES_HOST", "127.0.0.1"),
        env.get("POSTGRES_USER", ""),
        int(env.get("POSTGRES_PORT", 5432)),
        dbname,
        env.get("POSTGRES_PASSWORD", ""),
    )
    pool = _PG_POOLS.get(key)
    if pool is None:
        pool = ThreadedConnectionPool(
            minconn=2,
            maxconn=int(os.getenv("HERMES_PG_POOL_MAXCONN", "20")),
            host=key[0],
            port=key[2],
            dbname=dbname,
            user=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"],
        )
        _PG_POOLS[key] = pool
    return pool


@contextmanager
def pg_conn(dbname: str = "rag"):
    pool = _get_pg_pool(dbname)
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def http_get(url: str, timeout: int = 10) -> dict[str, Any]:
    try:
        with request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": resp.status, "body": redact_text(body[:1000])}
    except Exception as exc:
        return {"ok": False, "error": redact_text(str(exc))}


def json_safe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return json.loads(json.dumps(rows, ensure_ascii=False, default=str))


@mcp.tool
def infra_readiness() -> dict[str, Any]:
    """Return high-signal health for core services, endpoints, memory, and credential presence."""
    services = {}
    for name in sorted(ALLOWED_SERVICES):
        if name in {"infra-snapshot", "infra-health-loop"}:
            unit = f"{name}.service"
        else:
            unit = name
        services[name] = run_cmd(["systemctl", "is-active", unit], timeout=10)["stdout"] or "unknown"

    endpoints = {
        "hermes_api": http_get("http://127.0.0.1:8642/health"),
        "n8n": http_get("http://127.0.0.1:5678/healthz/readiness"),
        "automation_gateway": http_get("http://127.0.0.1:8788/health"),
    }

    memory = memory_overview()
    return {
        "ok": all(v in {"active", "inactive"} for v in services.values()) and endpoints["hermes_api"]["ok"],
        "services": services,
        "endpoints": endpoints,
        "memory": memory,
        "credentials": [
            redacted_env_presence(HERMES_ENV),
            redacted_env_presence(N8N_ENV),
            redacted_env_presence(AUTOMATION_ENV),
        ],
    }


@mcp.tool
def infra_snapshot() -> dict[str, Any]:
    """Return the latest host snapshot generated by infra-snapshot.service."""
    if not SNAPSHOT_JSON.exists():
        return {"ok": False, "error": "snapshot_missing", "path": str(SNAPSHOT_JSON)}
    data = json.loads(SNAPSHOT_JSON.read_text(encoding="utf-8"))
    return {"ok": True, "snapshot": data}


@mcp.tool
def refresh_infra_snapshot() -> dict[str, Any]:
    """Refresh host and memory snapshots without changing deployed services."""
    result = run_cmd(["sudo", "-n", "systemctl", "start", "infra-snapshot.service"], timeout=30)
    if not result["ok"]:
        return {"ok": False, "error": "refresh_failed", "detail": result}
    return infra_snapshot()


@mcp.tool
def service_logs(service: str, lines: int = 80) -> dict[str, Any]:
    """Read recent logs for an allowlisted service with secrets redacted."""
    if service not in ALLOWED_SERVICES:
        return {"ok": False, "error": "service_not_allowed", "allowed_services": sorted(ALLOWED_SERVICES)}
    safe_lines = max(1, min(int(lines), 200))
    unit = service if service not in {"infra-snapshot", "infra-health-loop"} else f"{service}.service"
    result = run_cmd(["sudo", "-n", "journalctl", "-u", unit, "-n", str(safe_lines), "--no-pager"], timeout=30)
    return {"ok": result["ok"], "service": service, "logs": result["stdout"], "stderr": result["stderr"]}


@mcp.tool
def memory_overview() -> dict[str, Any]:
    """Inspect canonical Postgres memory counts, workspace/project groups, and queryability status."""
    with pg_conn("rag") as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                select
                  (select count(*) from workspaces) as workspaces,
                  (select count(*) from projects) as projects,
                  (select count(*) from artifacts) as artifacts,
                  (select count(*) from artifact_versions) as artifact_versions,
                  (select count(*) from ingestion_jobs) as ingestion_jobs,
                  (select count(*) from insights) as insights,
                  (select count(*) from workspaces where slug = 'obsidian_vault') as legacy_obsidian_workspaces
                """
            )
            counts = dict(cur.fetchone())
            cur.execute(
                """
                select w.slug as workspace, p.slug as project, count(*) as artifacts
                from artifacts a
                join workspaces w on w.id = a.workspace_id
                left join projects p on p.id = a.project_id
                group by w.slug, p.slug
                order by w.slug, p.slug
                """
            )
            groups = json_safe_rows(cur.fetchall())
            cur.execute(
                """
                select coalesce(metadata_json->>'queryability_status', 'missing') as status, count(*) as count
                from ingestion_jobs
                group by 1
                order by 1
                """
            )
            queryability = json_safe_rows(cur.fetchall())
            cur.execute(
                """
                select collection, count(*) as count
                from rag_documents
                group by collection
                order by collection
                """
            )
            collections = json_safe_rows(cur.fetchall())
    return {"ok": True, "counts": counts, "groups": groups, "queryability": queryability, "collections": collections}


@mcp.tool
def memory_search(collection: str, query: str = "", limit: int = 5) -> dict[str, Any]:
    """Search a retrieval collection in rag_documents using lexical and FTS matching."""
    safe_limit = max(1, min(int(limit), 20))
    safe_collection = str(collection or "").strip()
    safe_query = str(query or "").strip()
    if not safe_collection:
        return {"ok": False, "error": "collection_required"}
    with pg_conn("rag") as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if safe_query:
                cur.execute(
                    """
                    select id, collection, source, left(content, 2000) as content_preview, metadata, updated_at,
                           ts_rank_cd(to_tsvector('simple', coalesce(content,'')), websearch_to_tsquery('simple', %s)) as rank
                    from rag_documents
                    where collection = %s
                      and (
                        to_tsvector('simple', coalesce(content,'')) @@ websearch_to_tsquery('simple', %s)
                        or content ilike %s
                        or source ilike %s
                      )
                    order by rank desc nulls last, id desc
                    limit %s
                    """,
                    (safe_query, safe_collection, safe_query, f"%{safe_query}%", f"%{safe_query}%", safe_limit),
                )
            else:
                cur.execute(
                    """
                    select id, collection, source, left(content, 2000) as content_preview, metadata, updated_at, 0::float as rank
                    from rag_documents
                    where collection = %s
                    order by id desc
                    limit %s
                    """,
                    (safe_collection, safe_limit),
                )
            rows = json_safe_rows(cur.fetchall())
    return {"ok": True, "collection": safe_collection, "query": safe_query, "count": len(rows), "items": rows}


@mcp.tool
def memory_record_observation(title: str, content: str, kind: str = "agent_observation", severity: str = "info") -> dict[str, Any]:
    """Append a non-destructive operational observation to canonical memory and retrieval memory."""
    clean_title = str(title or "").strip()[:200]
    clean_content = str(content or "").strip()
    clean_kind = re.sub(r"[^a-z0-9_:-]+", "_", str(kind or "agent_observation").lower())[:80]
    clean_severity = re.sub(r"[^a-z0-9_:-]+", "_", str(severity or "info").lower())[:40]
    if not clean_title or not clean_content:
        return {"ok": False, "error": "title_and_content_required"}
    now = datetime.now(timezone.utc)
    metadata = {"origin": "mcp_memory_record_observation", "severity": clean_severity, "created_at": now.isoformat()}
    with pg_conn("rag") as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            workspace_id = ensure_workspace(cur, "agent_ops", "Agent Ops", metadata={"origin": "mcp"})
            project_id = ensure_project(cur, workspace_id, "operator_observations", "Operator Observations", metadata={"origin": "mcp"})
            record_insight(
                cur,
                workspace_slug="agent_ops",
                workspace_name="Agent Ops",
                project_slug="operator_observations",
                project_name="Operator Observations",
                kind=clean_kind,
                title=clean_title,
                content=clean_content,
                metadata=metadata,
            )
            cur.execute(
                """
                insert into rag_documents (collection, source, content, metadata, created_at, updated_at)
                values (%s,%s,%s,%s,%s,%s)
                returning id
                """,
                ("agent-observations", f"mcp:{now.isoformat()}", clean_content, Json({"title": clean_title, **metadata}), now, now),
            )
            row_id = cur.fetchone()[0]
    return {"ok": True, "collection": "agent-observations", "rag_document_id": row_id, "title": clean_title}


@mcp.tool
def orchestrate_tasks(
    objective: str,
    tasks: list[str],
    collection: str = "mcp-orchestration",
    store_to_rag: bool = True,
    max_concurrency: int = 2,
) -> dict[str, Any]:
    """Run a bounded Hermes fan-out orchestration and optionally store results in RAG."""
    clean_objective = str(objective or "").strip()
    clean_tasks = [str(item).strip() for item in (tasks or []) if str(item).strip()]
    if not clean_objective and not clean_tasks:
        return {"ok": False, "error": "objective_or_tasks_required"}
    if len(clean_tasks) > 8:
        return {"ok": False, "error": "too_many_tasks", "max_tasks": 8}
    payload = {
        "objective": clean_objective,
        "tasks": clean_tasks,
        "collection": str(collection or "mcp-orchestration").strip() or "mcp-orchestration",
        "store_to_rag": bool(store_to_rag),
        "max_concurrency": max(1, min(int(max_concurrency), 4)),
    }
    return run_json_script("/srv/automation/bin/hermes_fanout.py", payload, timeout=900)


@mcp.tool
def n8n_status() -> dict[str, Any]:
    """Return n8n health plus workflow, execution, and credential counts without credential data."""
    health = http_get("http://127.0.0.1:5678/healthz")
    with pg_conn("n8n") as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                select
                  (select count(*) from workflow_entity) as workflows,
                  (select count(*) from workflow_entity where active = true) as active_workflows,
                  (select count(*) from execution_entity) as executions,
                  (select count(*) from credentials_entity) as credentials
                """
            )
            counts = dict(cur.fetchone())
            cur.execute(
                """
                select status, count(*) as count
                from execution_entity
                group by status
                order by status
                """
            )
            execution_status = json_safe_rows(cur.fetchall())
    return {"ok": bool(health.get("ok")), "health": health, "counts": counts, "execution_status": execution_status}


@mcp.tool
def n8n_workflows(limit: int = 20, active_only: bool = False) -> dict[str, Any]:
    """List n8n workflows with IDs, names, active flags, and update timestamps."""
    safe_limit = max(1, min(int(limit), 100))
    with pg_conn("n8n") as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if active_only:
                cur.execute(
                    """
                    select id, name, active, "createdAt", "updatedAt", "isArchived", "triggerCount"
                    from workflow_entity
                    where active = true
                    order by "updatedAt" desc
                    limit %s
                    """,
                    (safe_limit,),
                )
            else:
                cur.execute(
                    """
                    select id, name, active, "createdAt", "updatedAt", "isArchived", "triggerCount"
                    from workflow_entity
                    order by "updatedAt" desc
                    limit %s
                    """,
                    (safe_limit,),
                )
            rows = json_safe_rows(cur.fetchall())
    return {"ok": True, "count": len(rows), "workflows": rows}


@mcp.tool
def n8n_recent_executions(limit: int = 20) -> dict[str, Any]:
    """List recent n8n executions without node data or credential content."""
    safe_limit = max(1, min(int(limit), 100))
    with pg_conn("n8n") as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                select e.id, e.status, e.finished, e.mode, e."workflowId", w.name as workflow_name,
                       e."startedAt", e."stoppedAt", e."createdAt"
                from execution_entity e
                left join workflow_entity w on w.id = e."workflowId"
                order by e.id desc
                limit %s
                """,
                (safe_limit,),
            )
            rows = json_safe_rows(cur.fetchall())
    return {"ok": True, "count": len(rows), "executions": rows}


@mcp.tool
def model_backend_status() -> dict[str, Any]:
    """Report configured model backends and redacted credential presence."""
    hermes_env = read_env(HERMES_ENV)
    has_nvidia = bool(hermes_env.get("NVIDIA_API_KEY"))
    has_openrouter = bool(hermes_env.get("OPENROUTER_API_KEY"))
    nvidia_models = None
    if has_nvidia:
        try:
            req = request.Request(
                "https://integrate.api.nvidia.com/v1/models",
                headers={"Authorization": f"Bearer {hermes_env['NVIDIA_API_KEY']}"},
            )
            with request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                nvidia_models = {"ok": True, "count": len(data.get("data", []))}
        except Exception as exc:
            nvidia_models = {"ok": False, "error": redact_text(str(exc))}
    return {
        "ok": True,
        "credentials": {"nvidia": has_nvidia, "openrouter": has_openrouter},
        "active_route_note": "Hermes main model is configured separately in ~/.hermes/config.yaml; this tool does not expose secrets.",
        "nvidia_models": nvidia_models,
    }


@mcp.tool
def provider_health_check() -> dict[str, Any]:
    """Test live connectivity to configured LLM providers with a minimal non-streaming request."""
    import time

    hermes_env = read_env(HERMES_ENV)
    results: dict[str, Any] = {}

    def _test_openrouter(key: str) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            data = json.dumps({
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "stream": False,
            }).encode()
            req = request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=data,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://hermes-agent",
                },
                method="POST",
            )
            with request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
                return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000), "model": body.get("model")}
        except Exception as exc:
            return {"ok": False, "latency_ms": round((time.monotonic() - t0) * 1000), "error": redact_text(str(exc))}

    def _test_nvidia(key: str) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            data = json.dumps({
                "model": "meta/llama-3.1-8b-instruct",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "stream": False,
            }).encode()
            req = request.Request(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                data=data,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
                return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000), "model": body.get("model")}
        except Exception as exc:
            return {"ok": False, "latency_ms": round((time.monotonic() - t0) * 1000), "error": redact_text(str(exc))}

    if hermes_env.get("OPENROUTER_API_KEY"):
        results["openrouter"] = _test_openrouter(hermes_env["OPENROUTER_API_KEY"])
    else:
        results["openrouter"] = {"ok": False, "error": "no_key_configured"}

    if hermes_env.get("NVIDIA_API_KEY"):
        results["nvidia"] = _test_nvidia(hermes_env["NVIDIA_API_KEY"])
    else:
        results["nvidia"] = {"ok": False, "error": "no_key_configured"}

    working = [name for name, r in results.items() if r.get("ok")]
    failing = [name for name, r in results.items() if not r.get("ok")]

    return {
        "ok": bool(working),
        "working_providers": working,
        "failing_providers": failing,
        "providers": results,
        "recommendation": (
            "All providers healthy." if not failing
            else f"Switch Hermes model config away from {', '.join(failing)}."
            if working
            else "All providers unreachable — check HERMES_ENV keys and network connectivity."
        ),
    }


@mcp.tool
def notion_status() -> dict[str, Any]:
    """Report whether a Notion integration token is present without exposing it."""
    envs = [read_env(HERMES_ENV), read_env(N8N_ENV), read_env(AUTOMATION_ENV)]
    keys = ["NOTION_API_KEY", "NOTION_TOKEN", "NOTION_INTERNAL_INTEGRATION_TOKEN"]
    present = sorted({key for env in envs for key in keys if env.get(key)})
    return {
        "ok": True,
        "configured": bool(present),
        "present_keys": present,
        "note": "Use a Notion internal integration token for headless automation; token values are never returned.",
    }


@mcp.tool
def inbox_enqueue(
    message: str,
    source: str = "mcp",
    priority: str = "normal",
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Submit a task to the Ralph autonomous runner via SourceRouter.

    Returns the inbox task id, or null if the message was a duplicate.
    """
    import sys as _sys
    _sys.path.insert(0, str(WORKSPACE / "hermes" / "src"))
    try:
        from task_orchestrator_v2 import TaskOrchestrator  # type: ignore
        from s5.source_router import SourceRouter  # type: ignore

        db_url = read_env(HERMES_ENV).get("DATABASE_URL", "")
        # Parse db_url → dbname for orchestrator
        import re as _re
        m = _re.search(r"/([^/?]+)(\?|$)", db_url)
        dbname = m.group(1) if m else "rag"

        orch = TaskOrchestrator(dbname=dbname)
        router = SourceRouter(orch)
        task_id = router.submit(message, source=source, priority=priority, metadata=metadata or {})
        return {"ok": True, "task_id": task_id, "queued": task_id is not None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool
def inbox_status(task_id: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Query status of Ralph task(s).

    Pass task_id to look up a specific task, or omit to list the latest `limit` tasks.
    """
    import sys as _sys
    _sys.path.insert(0, str(WORKSPACE / "hermes" / "src"))
    try:
        from task_orchestrator_v2 import get_db_connection  # type: ignore

        with get_db_connection() as conn:
            cur = conn.cursor()
            if task_id:
                cur.execute(
                    """SELECT t.id, i.raw_text, t.status, t.priority,
                              t.result_text, t.error_text, t.created_at, t.updated_at
                       FROM agent_tasks t
                       LEFT JOIN agent_inbox i ON i.id = t.id
                       WHERE t.id = %s""",
                    (task_id,),
                )
            else:
                cur.execute(
                    """SELECT t.id, i.raw_text, t.status, t.priority,
                              t.result_text, t.error_text, t.created_at, t.updated_at
                       FROM agent_tasks t
                       LEFT JOIN agent_inbox i ON i.id = t.id
                       ORDER BY t.created_at DESC LIMIT %s""",
                    (limit,),
                )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            for k in ("created_at", "updated_at"):
                if r.get(k):
                    r[k] = r[k].isoformat()
        return {"ok": True, "tasks": rows, "count": len(rows)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool
def ralph_status() -> dict[str, Any]:
    """Report Ralph runner status: systemd state, queue depth, task counts by status."""
    import subprocess as _sp
    import sys as _sys
    _sys.path.insert(0, str(WORKSPACE / "hermes" / "src"))

    # systemd state
    try:
        active = _sp.check_output(
            ["systemctl", "is-active", "ralph"], text=True, stderr=_sp.DEVNULL
        ).strip()
    except Exception:
        active = "unknown"

    # queue metrics
    try:
        from task_orchestrator_v2 import get_db_connection  # type: ignore

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) FROM agent_tasks GROUP BY status")
            by_status = {row[0]: row[1] for row in cur.fetchall()}
            cur.execute(
                "SELECT COUNT(*) FROM agent_tasks WHERE status IN ('pending','retry')"
            )
            queue_depth = cur.fetchone()[0]
    except Exception as exc:
        by_status = {}
        queue_depth = -1
        active = f"{active} (db_error: {exc})"

    return {
        "ok": True,
        "service_state": active,
        "running": active == "active",
        "queue_depth": queue_depth,
        "tasks_by_status": by_status,
    }


if __name__ == "__main__":
    mcp.run()
