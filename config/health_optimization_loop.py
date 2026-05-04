import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

import psycopg2
from psycopg2.extras import Json

from canonical_memory import ensure_schema, record_insight, upsert_artifact_version, verify_queryability_from_rag


SNAPSHOT_PATH = Path("/home/Bilirubin/workspace/.agent-state/infra_snapshot.json")
AUTOMATION_ENV = Path("/srv/automation/.env")
HERMES_ENV = Path("/home/Bilirubin/.hermes/.env")
HERMES_CONFIG = Path("/home/Bilirubin/.hermes/config.yaml")
SERVICES = ["hermes-gateway", "hermes-dashboard", "n8n", "automation-gateway", "brain-mcp", "nginx", "docker"]

# Model tiers — ordered best-to-worst.
# provider: "openrouter" = paid credits required; "nvidia" = free NVIDIA NIM.
MODEL_TIERS = [
    # ── Paid (OpenRouter) ───────────────────────────────────────────────────
    {"label": "claude-sonnet-4.6",  "model": "anthropic/claude-sonnet-4-6",                "provider": "openrouter_paid", "min_credits": 1.5},
    {"label": "claude-3.5-sonnet",  "model": "anthropic/claude-3.5-sonnet",                "provider": "openrouter_paid", "min_credits": 0.5},
    # ── Free via OpenRouter (no credits needed, separate rate-limit pools) ──
    # Confirmed tool-call support:
    {"label": "nemotron-or-free",   "model": "nvidia/nemotron-3-super-120b-a12b:free",     "provider": "openrouter_free", "min_credits": 0},
    {"label": "gemma4-26b-free",    "model": "google/gemma-4-26b-a4b-it:free",             "provider": "openrouter_free", "min_credits": 0},
    # Larger free models (popular — may hit 429, retry handles it):
    {"label": "gemma4-31b-free",    "model": "google/gemma-4-31b-it:free",                 "provider": "openrouter_free", "min_credits": 0},
    {"label": "qwen3-80b-free",     "model": "qwen/qwen3-next-80b-a3b-instruct:free",      "provider": "openrouter_free", "min_credits": 0},
    {"label": "llama3.3-70b-free",  "model": "meta-llama/llama-3.3-70b-instruct:free",     "provider": "openrouter_free", "min_credits": 0},
    # ── Free via NVIDIA direct (different API, different rate limits) ───────
    {"label": "nemotron-120b",      "model": "nvidia/nemotron-3-super-120b-a12b",          "provider": "nvidia",          "min_credits": 0},
    {"label": "llama3.1-405b",      "model": "meta/llama-3.1-405b-instruct",               "provider": "nvidia",          "min_credits": 0},
    # ── Last resort ─────────────────────────────────────────────────────────
    {"label": "llama3.1-70b",       "model": "meta/llama-3.1-70b-instruct",                "provider": "nvidia",          "min_credits": 0},
]


def run(*args):
    proc = subprocess.run(list(args), check=False, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def check_provider(name: str, url: str, api_key: str, payload: dict | None = None) -> dict:
    import time
    t0 = time.monotonic()
    try:
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            req_obj = request.Request(
                url, data=body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST",
            )
        else:
            req_obj = request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
        with request.urlopen(req_obj, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            count = len(data.get("data", []))
            return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000), "models": count}
    except Exception as exc:
        return {"ok": False, "latency_ms": round((time.monotonic() - t0) * 1000), "error": str(exc)[:200]}


def _check_openrouter_account(api_key: str) -> dict:
    """Read account stats from OpenRouter — no tokens spent."""
    try:
        req_obj = request.Request(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with request.urlopen(req_obj, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            usage = data.get("data", {}).get("usage", 0) or 0
            limit = data.get("data", {}).get("limit")
            remaining = round(limit - usage, 4) if limit else None
            return {"ok": True, "usage_usd": round(usage, 4), "limit_usd": limit, "remaining_usd": remaining}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _gateway_has_recent_402(minutes: int = 20) -> bool:
    """Scan recent hermes-gateway journal for OpenRouter 402 (out-of-credits) errors."""
    _, output, _ = run(
        "journalctl", "-u", "hermes-gateway",
        f"--since={minutes} minutes ago", "--no-pager", "--output=short",
    )
    low = output.lower()
    return "402" in low and ("openrouter" in low or "credit" in low)


def collect_provider_health(hermes_env: dict) -> dict:
    results = {}
    if hermes_env.get("OPENROUTER_API_KEY"):
        key = hermes_env["OPENROUTER_API_KEY"]
        info = _check_openrouter_account(key)
        # 402 in recent logs means we burned through credits — mark as unaffordable immediately
        has_402 = _gateway_has_recent_402()
        remaining = info.get("remaining_usd")
        # If limit=None (no hard cap set), only mark unaffordable when we see a real 402
        affordable = info.get("ok") and not has_402 and (remaining is None or remaining >= 0.5)
        results["openrouter"] = {**info, "affordable": affordable, "recent_402": has_402}
    if hermes_env.get("NVIDIA_API_KEY"):
        results["nvidia"] = check_provider(
            "nvidia",
            "https://integrate.api.nvidia.com/v1/models",
            hermes_env["NVIDIA_API_KEY"],
        )
    return results


# ── Model auto-selection ────────────────────────────────────────────────────

def _get_current_model() -> str:
    try:
        for line in HERMES_CONFIG.read_text(encoding="utf-8").splitlines():
            if not line.startswith((" ", "\t")) and line.startswith("model:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def _write_model_to_config(new_model: str) -> bool:
    try:
        text = HERMES_CONFIG.read_text(encoding="utf-8")
        lines = text.splitlines()
        new_lines = [
            f"model: {new_model}" if (not ln.startswith((" ", "\t")) and ln.startswith("model:")) else ln
            for ln in lines
        ]
        HERMES_CONFIG.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
    except Exception as exc:
        print(f"[model-select] config write failed: {exc}")
        return False


def select_optimal_model(providers: dict) -> dict:
    """Return the best tier dict given current provider state."""
    or_info = providers.get("openrouter", {})
    or_ok = or_info.get("ok", False)          # key is valid (free models usable)
    or_affordable = or_info.get("affordable", False)  # paid credits available
    or_remaining = or_info.get("remaining_usd")
    nvidia_ok = providers.get("nvidia", {}).get("ok", False)

    for tier in MODEL_TIERS:
        p = tier["provider"]
        if p == "openrouter_paid":
            if not or_affordable:
                continue
            if or_remaining is not None and or_remaining < tier["min_credits"]:
                continue
            return tier
        if p == "openrouter_free":
            # Free models need only a valid OR key — no credits required
            if or_ok:
                return tier
        if p == "nvidia" and nvidia_ok:
            return tier

    return MODEL_TIERS[-1]  # last-resort fallback


def apply_model_selection(providers: dict, pg_env: dict) -> dict:
    """Pick best model, update config if changed, restart gateway if degrading."""
    best = select_optimal_model(providers)
    current = _get_current_model()
    result = {"tier": best["label"], "model": best["model"], "previous": current, "changed": False}

    if best["model"] == current:
        return result

    if not _write_model_to_config(best["model"]):
        result["error"] = "config write failed"
        return result

    result["changed"] = True

    # Determine if this is a downgrade (from paid → free) or upgrade (free → paid)
    current_tier_idx = next((i for i, t in enumerate(MODEL_TIERS) if t["model"] == current), 999)
    new_tier_idx = next((i for i, t in enumerate(MODEL_TIERS) if t["model"] == best["model"]), 999)
    is_downgrade = new_tier_idx > current_tier_idx

    # Restart gateway on downgrade — the current model is broken (402/unavailable)
    # On upgrade — just write config; next natural restart picks it up (avoids interrupting sessions)
    if is_downgrade:
        run("sudo", "systemctl", "restart", "hermes-gateway")
        result["restarted"] = True

    # Persist switch event
    now = datetime.now(timezone.utc)
    direction = "↓ downgrade" if is_downgrade else "↑ upgrade"
    or_info = providers.get("openrouter", {})
    reason = (
        f"OpenRouter 402 detected" if or_info.get("recent_402") else
        f"OpenRouter credits low (${or_info.get('remaining_usd', '?')})" if or_info.get("remaining_usd") is not None else
        f"OpenRouter unavailable" if not or_info.get("ok") else
        "Upgrading to better model"
    )
    msg = f"Model {direction}: {current} → {best['model']} | reason: {reason}"
    try:
        conn = psycopg2.connect(
            host="127.0.0.1", port=5432, dbname="rag",
            user=pg_env["POSTGRES_USER"], password=pg_env["POSTGRES_PASSWORD"],
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO rag_documents (collection, source, content, metadata, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    ("host-insights", f"model-switch:{now.isoformat()}", msg,
                     Json({**result, "reason": reason, "direction": direction}), now, now),
                )
    except Exception:
        pass

    result["reason"] = reason
    result["direction"] = direction
    return result


def read_env(path: Path):
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def http_get(url: str):
    try:
        with request.urlopen(url, timeout=10) as resp:
            return {"ok": True, "status": resp.status, "body": resp.read().decode("utf-8", errors="replace")[:500]}
    except Exception as exc:
        return {"ok": False, "status": None, "error": str(exc)}


def load_snapshot():
    if not SNAPSHOT_PATH.exists():
        return {}
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def parse_mem_value(text):
    number = float(text.split()[0])
    if "GiB" in text:
        return number * 1024
    if "MiB" in text:
        return number
    return number


def collect_status(snapshot):
    status = {
        "snapshot_updated": snapshot.get("updated_at_utc"),
        "services": {},
        "endpoints": {},
        "db": {},
        "snapshot": snapshot,
    }

    for svc in SERVICES:
        _, active_out, _ = run("systemctl", "is-active", svc)
        _, restart_out, _ = run("systemctl", "show", svc, "-p", "NRestarts", "--value")
        status["services"][svc] = {
            "active": active_out.strip() == "active",
            "status": active_out.strip() or "unknown",
            "restarts": int(restart_out.strip() or "0"),
        }

    status["endpoints"]["n8n"] = http_get("http://127.0.0.1:5678/healthz/readiness")
    status["endpoints"]["automation_gateway"] = http_get("http://127.0.0.1:8788/health")
    status["endpoints"]["hermes_api_ping"] = http_get("http://127.0.0.1:8642/health")
    status["endpoints"]["dashboard"] = http_get("http://127.0.0.1:9119")

    pg = read_env(AUTOMATION_ENV)
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        dbname="rag",
        user=pg["POSTGRES_USER"],
        password=pg["POSTGRES_PASSWORD"],
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute("select pg_database_size('rag'), pg_database_size('n8n')")
            rag_size, n8n_size = cur.fetchone()
            cur.execute(
                """
                select collection, count(*)
                from rag_documents
                where collection in ('host-state','host-insights','host-optimization','obsidian-main','obsidian-rules')
                group by collection
                """
            )
            counts = dict(cur.fetchall())
    status["db"] = {
        "rag_size_bytes": rag_size,
        "n8n_size_bytes": n8n_size,
        "counts": counts,
    }
    hermes_env = read_env(HERMES_ENV)
    status["providers"] = collect_provider_health(hermes_env)
    return status, pg


def build_recommendations(status):
    snapshot = status["snapshot"]
    recs = []
    sev = "info"

    disk = snapshot.get("disk_root", {})
    used_pct = float(disk.get("used_percent", 0))
    free_gb = float(disk.get("free_gb", 0))
    mem_available = parse_mem_value(snapshot.get("memory", {}).get("available", "0 MiB"))
    swap_free = parse_mem_value(snapshot.get("memory", {}).get("swap_free", "0 MiB"))
    swap_total = parse_mem_value(snapshot.get("memory", {}).get("swap_total", "0 MiB"))
    swap_used = max(swap_total - swap_free, 0)

    if used_pct >= 80 or free_gb <= 3:
        sev = "warn"
        recs.append("Root disk is getting tight. Clean up old artifacts or expand the boot disk before write failures start.")
    elif used_pct >= 65:
        recs.append("Disk usage is already above 65%. Keep watching growth from logs, npm cache, and future tool installs.")

    if mem_available < 700:
        sev = "warn"
        recs.append("Available RAM is low. Watch Hermes and n8n memory growth and consider another RAM step if swap starts climbing.")
    elif swap_used > 256:
        recs.append("Swap is in active use. This is acceptable for now, but it is an early sign of pressure on a 2 GiB host.")

    failing = [name for name, info in status["services"].items() if not info["active"]]
    if failing:
        sev = "critical"
        recs.append("Some core services are not active: " + ", ".join(failing) + ".")

    if not status["endpoints"]["n8n"]["ok"]:
        sev = "critical"
        recs.append("n8n health endpoint is failing. Inspect n8n logs before relying on workflows.")

    if not status["endpoints"]["automation_gateway"]["ok"]:
        sev = "critical"
        recs.append("automation-gateway health endpoint is failing. Orchestration webhooks may be broken.")

    if status["db"]["counts"].get("host-state", 0) == 0:
        sev = "warn"
        recs.append("External memory has no host-state row. Snapshot persistence should be checked.")

    if status["db"]["counts"].get("obsidian-rules", 0) == 0:
        recs.append("Rules memory is empty. Re-import Obsidian rules before expecting policy-aware retrieval.")

    recs.append("If you do not need a permanent public IP, replacing the static external IPv4 with an ephemeral IP or tunnel would reduce baseline cost.")

    failing_providers = [name for name, r in status.get("providers", {}).items() if not r.get("ok")]
    if failing_providers:
        sev = "warn" if sev == "info" else sev
        recs.append(f"LLM provider(s) unreachable: {', '.join(failing_providers)}. Hermes may stall on long tasks.")

    openrouter = status.get("providers", {}).get("openrouter", {})
    if openrouter.get("recent_402"):
        sev = "warn" if sev == "info" else sev
        recs.append(f"OpenRouter 402 detected — out of credits (used ${openrouter.get('usage_usd', 0):.2f}). Top up: https://openrouter.ai/settings/credits")
    elif openrouter.get("remaining_usd") is not None and openrouter["remaining_usd"] < 2.0:
        sev = "warn" if sev == "info" else sev
        recs.append(f"OpenRouter credits low: ${openrouter['remaining_usd']:.2f} remaining. Top up before switching back to Claude.")
    elif openrouter.get("usage_usd") and openrouter.get("limit_usd") is None:
        recs.append(f"OpenRouter usage: ${openrouter['usage_usd']:.2f} (no hard cap — 402 auto-detected from logs).")

    return sev, recs


def format_bytes(num):
    gb = 1024 ** 3
    mb = 1024 ** 2
    if num >= gb:
        return f"{num / gb:.2f} GB"
    return f"{num / mb:.2f} MB"


def build_report(status, severity, recommendations):
    snapshot = status["snapshot"]
    provider_summary = ", ".join(
        f"{name}={'ok' if r.get('ok') else 'FAIL'}"
        for name, r in status.get("providers", {}).items()
    ) or "none configured"
    lines = [
        f"Host: {snapshot.get('host', {}).get('instance_name', 'unknown')} ({snapshot.get('host', {}).get('machine_type', 'unknown')}, {snapshot.get('host', {}).get('zone', 'unknown')})",
        "Service status: " + ", ".join(f"{name}={info['status']}" for name, info in status["services"].items()),
        "n8n health: " + ("ok" if status["endpoints"]["n8n"]["ok"] else "failed"),
        "automation-gateway health: " + ("ok" if status["endpoints"]["automation_gateway"]["ok"] else "failed"),
        f"LLM providers: {provider_summary}",
        f"RAG DB size: {format_bytes(status['db']['rag_size_bytes'])}; n8n DB size: {format_bytes(status['db']['n8n_size_bytes'])}",
        "Recommendations:",
    ]
    lines.extend(f"- {item}" for item in recommendations)
    return "\n".join(lines)


def _alert_fingerprint(severity: str, down_services: list, failing_providers: list) -> str:
    import hashlib
    key = f"{severity}|{','.join(sorted(down_services))}|{','.join(sorted(failing_providers))}"
    return hashlib.md5(key.encode()).hexdigest()


def _last_alert_fingerprint(pg_env: dict) -> str:
    try:
        conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="rag",
                                user=pg_env["POSTGRES_USER"], password=pg_env["POSTGRES_PASSWORD"])
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT content FROM rag_documents WHERE collection='alert-state' AND source='fingerprint' LIMIT 1"
                )
                row = cur.fetchone()
                return row[0] if row else ""
    except Exception:
        return ""


def _save_alert_fingerprint(fp: str, pg_env: dict):
    now = datetime.now(timezone.utc)
    try:
        conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="rag",
                                user=pg_env["POSTGRES_USER"], password=pg_env["POSTGRES_PASSWORD"])
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rag_documents WHERE collection='alert-state' AND source='fingerprint'")
                cur.execute(
                    "INSERT INTO rag_documents (collection, source, content, metadata, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    ("alert-state", "fingerprint", fp, Json({"updated_at": now.isoformat()}), now, now),
                )
    except Exception:
        pass


def send_telegram(summary: str, severity: str, pg_env: dict | None = None,
                  down_services: list | None = None, failing_providers: list | None = None):
    env = read_env(HERMES_ENV)
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id or severity not in {"warn", "critical"}:
        return

    # Дедупликация: не шлём если статус не изменился
    if pg_env is not None:
        fp = _alert_fingerprint(severity, down_services or [], failing_providers or [])
        last_fp = _last_alert_fingerprint(pg_env)
        if fp == last_fp:
            return  # то же самое — молчим
        _save_alert_fingerprint(fp, pg_env)

    body = json.dumps({"chat_id": chat_id, "text": f"[server-loop:{severity}]\n{summary}"}, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        request.urlopen(req, timeout=15).read()
    except Exception:
        pass


def persist_report(status, severity, recommendations, summary, pg_env):
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        dbname="rag",
        user=pg_env["POSTGRES_USER"],
        password=pg_env["POSTGRES_PASSWORD"],
    )
    now = datetime.now(timezone.utc)
    metadata = {
        "severity": severity,
        "recommendation_count": len(recommendations),
        "snapshot_updated": status["snapshot_updated"],
        "services": status["services"],
        "endpoints": {
            name: {"ok": info["ok"], "status": info.get("status")}
            for name, info in status["endpoints"].items()
        },
    }
    with conn:
        with conn.cursor() as cur:
            cur.execute("delete from rag_documents where collection='host-optimization' and source='latest'")
            cur.execute(
                """
                insert into rag_documents (collection, source, content, metadata, created_at, updated_at)
                values (%s,%s,%s,%s,%s,%s)
                """,
                ("host-optimization", "latest", summary, Json(metadata), now, now),
            )
            cur.execute(
                """
                insert into rag_documents (collection, source, content, metadata, created_at, updated_at)
                values (%s,%s,%s,%s,%s,%s)
                """,
                ("host-optimization", f"loop:{now.isoformat()}", summary, Json(metadata), now, now),
            )
            ensure_schema(cur)
            latest_result = upsert_artifact_version(
                cur,
                workspace_slug="infra_ops",
                workspace_name="Infrastructure Ops",
                project_slug="hermes_server",
                project_name="Hermes Server",
                artifact_slug="host-optimization-latest",
                title="host-optimization",
                artifact_kind="host_optimization",
                source_kind="system",
                source_uri="latest",
                content=summary,
                metadata={"origin": "health_optimization_loop", "rag_collection": "host-optimization", "rag_source": "latest", **metadata},
                tags=["infra", "host-optimization", severity],
                target="rag_documents",
                action="upsert",
                status="completed",
            )
            if latest_result["ingestion_job_id"]:
                verify_queryability_from_rag(
                    cur,
                    ingestion_job_id=latest_result["ingestion_job_id"],
                    document_ref=latest_result["document_ref"],
                    artifact_kind="host_optimization",
                    source_uri="latest",
                    metadata={"rag_collection": "host-optimization", "rag_source": "latest"},
                )
            record_insight(
                cur,
                workspace_slug="infra_ops",
                workspace_name="Infrastructure Ops",
                project_slug="hermes_server",
                project_name="Hermes Server",
                kind="host_optimization",
                title="host-optimization",
                content=summary,
                metadata={"origin": "health_optimization_loop", **metadata},
            )


AUTO_RESTART_SAFE = {
    "hermes-gateway", "hermes-dashboard", "n8n",
    "automation-gateway", "brain-mcp", "nginx",
    "node-exporter", "prometheus",
}


def auto_remediate(status: dict, pg_env: dict) -> list[dict]:
    """Restart inactive services that are safe to auto-restart. Returns list of actions taken."""
    actions = []
    for name, info in status["services"].items():
        if info["active"] or name not in AUTO_RESTART_SAFE:
            continue
        rc, stdout, stderr = run("sudo", "systemctl", "restart", name)
        import time; time.sleep(2)
        _, active_out, _ = run("systemctl", "is-active", name)
        recovered = active_out.strip() == "active"
        actions.append({
            "service": name,
            "action": "restart",
            "rc": rc,
            "recovered": recovered,
            "detail": stderr[:200] if stderr else stdout[:200],
        })

    # Restart postgres container if unhealthy
    _, docker_health, _ = run(
        "sudo", "docker", "inspect", "--format", "{{.State.Health.Status}}", "automation-postgres"
    )
    if docker_health.strip() not in ("healthy", ""):
        rc, stdout, stderr = run("sudo", "docker", "restart", "automation-postgres")
        actions.append({"service": "automation-postgres", "action": "docker_restart", "rc": rc})

    if actions:
        now = datetime.now(timezone.utc)
        conn = psycopg2.connect(
            host="127.0.0.1", port=5432, dbname="rag",
            user=pg_env["POSTGRES_USER"], password=pg_env["POSTGRES_PASSWORD"],
        )
        recovered = [a["service"] for a in actions if a.get("recovered")]
        failed = [a["service"] for a in actions if not a.get("recovered")]
        content = f"Auto-remediation at {now.isoformat()}. Restarted: {[a['service'] for a in actions]}. Recovered: {recovered}. Still down: {failed}."
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into rag_documents (collection, source, content, metadata, created_at, updated_at) values (%s,%s,%s,%s,%s,%s)",
                    ("host-insights", f"remediation:{now.isoformat()}", content, Json({"actions": actions}), now, now),
                )
    return actions


def main():
    snapshot = load_snapshot()
    status, pg_env = collect_status(snapshot)
    severity, recommendations = build_recommendations(status)

    # Self-heal: restart failed services
    actions = auto_remediate(status, pg_env)
    if actions:
        status, _ = collect_status(snapshot)
        severity, recommendations = build_recommendations(status)
        recovered = [a["service"] for a in actions if a.get("recovered")]
        still_broken = [a["service"] for a in actions if not a.get("recovered")]
        recommendations.insert(0, f"Auto-remediation ran: restarted {[a['service'] for a in actions]}. Recovered: {recovered}. Still down: {still_broken}.")

    # Intelligent model selection — auto-switch based on available credits/providers
    model_switch = apply_model_selection(status["providers"], pg_env)
    if model_switch.get("changed"):
        msg = f"Model {model_switch['direction']}: {model_switch['previous']} → {model_switch['model']} ({model_switch.get('reason', '')})"
        recommendations.insert(0, msg)
        if model_switch.get("direction", "").startswith("↓"):
            severity = "warn" if severity == "info" else severity

    down_services = [name for name, info in status["services"].items() if not info["active"]]
    failing_providers = [name for name, r in status.get("providers", {}).items() if not r.get("ok")]

    summary = build_report(status, severity, recommendations)
    persist_report(status, severity, recommendations, summary, pg_env)
    send_telegram(summary, severity, pg_env=pg_env, down_services=down_services, failing_providers=failing_providers)
    print(json.dumps({
        "severity": severity,
        "model": model_switch.get("model"),
        "model_changed": model_switch.get("changed"),
        "actions": actions,
        "recommendations": recommendations,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
