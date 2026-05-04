import json
import os
import platform
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import Json
except Exception:  # pragma: no cover
    psycopg2 = None
    Json = None

from canonical_memory import ensure_schema, record_insight, upsert_artifact_version, verify_queryability_from_rag


WORKSPACE = Path("/home/Bilirubin/workspace")
STATE_DIR = WORKSPACE / ".agent-state"
SNAPSHOT_JSON = STATE_DIR / "infra_snapshot.json"
SNAPSHOT_MD = WORKSPACE / "INFRASTRUCTURE.md"

SERVICES = [
    "hermes-gateway",
    "hermes-dashboard",
    "n8n",
    "automation-gateway",
    "brain-mcp",
    "nginx",
    "docker",
]

LOCAL_ENDPOINTS = {
    "Hermes API": "http://127.0.0.1:8642/v1",
    "Hermes dashboard": "http://127.0.0.1:9119",
    "n8n editor": "http://127.0.0.1:5678",
    "Automation gateway": "http://127.0.0.1:8788",
    "MCP control plane": "http://127.0.0.1:8791/mcp/",
    "Postgres": "127.0.0.1:5432",
}


def run(*args):
    try:
        proc = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}


def load_env_file(path):
    data = {}
    env_path = Path(path)
    if not env_path.exists():
        return data
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def read_metadata(path):
    req = urllib.request.Request(
        f"http://metadata.google.internal/computeMetadata/v1/{path}",
        headers={"Metadata-Flavor": "Google"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception:
        return ""


def get_services():
    items = []
    for name in SERVICES:
        status = run("systemctl", "is-active", name)
        items.append(
            {
                "name": name,
                "status": status["stdout"] or "unknown",
                "ok": status["ok"],
            }
        )
    return items


def get_memory():
    mem = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        mem[key] = value.strip()
    return mem


def human_kib(value):
    kib = int(value.split()[0])
    gib = kib / 1024 / 1024
    if gib >= 1:
        return f"{gib:.2f} GiB"
    mib = kib / 1024
    return f"{mib:.0f} MiB"


def get_disk():
    usage = shutil.disk_usage("/")
    gb = 1024 ** 3
    return {
        "total_gb": round(usage.total / gb, 2),
        "used_gb": round(usage.used / gb, 2),
        "free_gb": round(usage.free / gb, 2),
        "used_percent": round((usage.used / usage.total) * 100, 1),
    }


def get_ports():
    result = run("ss", "-tulpn")
    return result["stdout"].splitlines() if result["ok"] else []


def get_containers():
    fmt = "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"
    result = run("docker", "ps", "--format", fmt)
    rows = []
    if result["ok"] and result["stdout"]:
        for line in result["stdout"].splitlines():
            name, image, status, ports = (line.split("|", 3) + ["", "", "", ""])[:4]
            rows.append(
                {
                    "name": name,
                    "image": image,
                    "status": status,
                    "ports": ports,
                }
            )
    return rows


def sanitize_env_file(path_str):
    path = Path(path_str)
    if not path.exists():
        return {}
    allowed = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, _ = line.split("=", 1)
        if re.match(r"^(N8N_|WEBHOOK_URL|DB_|POSTGRES_)", key):
            allowed[key] = "***"
    return allowed


def parse_nginx_short_routes():
    path = Path("/etc/nginx/sites-available/n8n.conf")
    routes = {}
    if not path.exists():
        return routes
    text = path.read_text(encoding="utf-8")
    for route in ("orchestrate", "rag-search"):
        if f"location = /{route}" in text:
            routes[f"/{route}"] = "enabled"
    return routes


def get_ufw_rules():
    result = run("ufw", "status")
    return result["stdout"].splitlines() if result["ok"] else []


def build_snapshot():
    zone = read_metadata("instance/zone")
    machine_type = read_metadata("instance/machine-type")
    snapshot = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": {
            "hostname": platform.node(),
            "kernel": platform.platform(),
            "project_id": read_metadata("project/project-id"),
            "instance_name": read_metadata("instance/name"),
            "zone": zone.rsplit("/", 1)[-1] if zone else "",
            "machine_type": machine_type.rsplit("/", 1)[-1] if machine_type else "",
            "external_ip": read_metadata(
                "instance/network-interfaces/0/access-configs/0/external-ip"
            ),
            "internal_ip": read_metadata("instance/network-interfaces/0/ip"),
        },
        "agent_runtime": {
            "terminal_backend": "local",
            "working_dir": "/home/Bilirubin/workspace",
            "note": (
                "Hermes is configured for local host terminal access. "
                "Workspace docs and Postgres memory are the preferred host context sources."
            ),
        },
        "services": get_services(),
        "containers": get_containers(),
        "memory": {
            "total": human_kib(get_memory().get("MemTotal", "0 kB")),
            "available": human_kib(get_memory().get("MemAvailable", "0 kB")),
            "swap_total": human_kib(get_memory().get("SwapTotal", "0 kB")),
            "swap_free": human_kib(get_memory().get("SwapFree", "0 kB")),
        },
        "disk_root": get_disk(),
        "local_endpoints": LOCAL_ENDPOINTS,
        "public_endpoints": {
            "n8n": "http://34.56.124.235/",
            "orchestrate": "http://34.56.124.235/orchestrate",
            "rag_search": "http://34.56.124.235/rag-search",
        },
        "paths": {
            "workspace": "/home/Bilirubin/workspace",
            "hermes_home": "/home/Bilirubin/.hermes",
            "automation_root": "/srv/automation",
            "n8n_env": "/srv/automation/n8n.env",
            "nginx_site": "/etc/nginx/sites-available/n8n.conf",
        },
        "n8n_env_keys": sanitize_env_file("/srv/automation/n8n.env"),
        "nginx_short_routes": parse_nginx_short_routes(),
        "ufw_status": get_ufw_rules(),
        "ports_raw": get_ports(),
    }
    return snapshot


def memory_to_mib(value):
    if value.endswith("GiB"):
        return float(value.split()[0]) * 1024
    if value.endswith("MiB"):
        return float(value.split()[0])
    return 0.0


def summarize_snapshot(snapshot, previous):
    active = [svc["name"] for svc in snapshot["services"] if svc["status"] == "active"]
    failed = [svc["name"] for svc in snapshot["services"] if svc["status"] != "active"]
    insights = []

    if failed:
        insights.append("non-active services: " + ", ".join(failed))

    disk = snapshot["disk_root"]
    if disk["used_percent"] >= 80:
        insights.append(f"disk pressure: root usage {disk['used_percent']}%")
    elif disk["free_gb"] <= 3:
        insights.append(f"low free disk: {disk['free_gb']} GB remaining")

    mem_available_mib = memory_to_mib(snapshot["memory"]["available"])
    if mem_available_mib and mem_available_mib < 512:
        insights.append(f"low available memory: {snapshot['memory']['available']}")

    if previous:
        prev_services = {svc["name"]: svc["status"] for svc in previous.get("services", [])}
        changes = []
        for svc in snapshot["services"]:
            before = prev_services.get(svc["name"])
            after = svc["status"]
            if before and before != after:
                changes.append(f"{svc['name']}: {before} -> {after}")
        if changes:
            insights.append("service state changes: " + "; ".join(changes))

    summary_lines = [
        f"Host {snapshot['host']['instance_name']} in {snapshot['host']['zone']} on {snapshot['host']['machine_type']}.",
        f"Active services: {', '.join(active) if active else 'none'}.",
        f"Disk usage: {disk['used_gb']} GB / {disk['total_gb']} GB ({disk['used_percent']}%).",
        f"Available memory: {snapshot['memory']['available']} (swap free {snapshot['memory']['swap_free']}).",
        "Public endpoints: "
        + ", ".join(
            f"{name}={url}"
            for name, url in snapshot["public_endpoints"].items()
        )
        + ".",
    ]
    if insights:
        summary_lines.append("Insights: " + " | ".join(insights) + ".")
    else:
        summary_lines.append("Insights: no immediate pressure or service anomalies detected.")

    return "\n".join(summary_lines), insights


def persist_memory(snapshot):
    if psycopg2 is None:
        return

    env = load_env_file("/srv/automation/.env")
    user = env.get("POSTGRES_USER")
    password = env.get("POSTGRES_PASSWORD")
    if not user or not password:
        return

    conn = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        dbname="rag",
        user=user,
        password=password,
    )
    now = datetime.now(timezone.utc)
    with conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                create table if not exists infra_snapshots (
                  id bigserial primary key,
                  captured_at timestamptz not null default now(),
                  summary text not null,
                  insights jsonb not null default '[]'::jsonb,
                  snapshot jsonb not null
                )
                """
            )
            cur.execute(
                """
                select snapshot
                from infra_snapshots
                order by captured_at desc
                limit 1
                """
            )
            row = cur.fetchone()
            previous = row[0] if row else None
            summary, insights = summarize_snapshot(snapshot, previous)
            cur.execute(
                """
                insert into infra_snapshots (captured_at, summary, insights, snapshot)
                values (%s, %s, %s, %s)
                """,
                (now, summary, Json(insights), Json(snapshot)),
            )
            cur.execute(
                """
                delete from rag_documents
                where collection = 'host-state' and source = 'latest'
                """
            )
            cur.execute(
                """
                insert into rag_documents (collection, source, content, metadata, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (
                    "host-state",
                    "latest",
                    summary,
                    Json(
                        {
                            "captured_at": now.isoformat(),
                            "host": snapshot["host"],
                            "insights": insights,
                        }
                    ),
                    now,
                    now,
                ),
            )
            latest_result = upsert_artifact_version(
                cur,
                workspace_slug="infra_ops",
                workspace_name="Infrastructure Ops",
                project_slug="career_odyssey_vm",
                project_name="Career Odyssey VM",
                artifact_slug="host-state-latest",
                title="host-state",
                artifact_kind="host_state_snapshot",
                source_kind="system",
                source_uri="latest",
                content=summary,
                metadata={
                    "captured_at": now.isoformat(),
                    "host": snapshot["host"],
                    "insights": insights,
                    "origin": "infra_snapshot",
                    "rag_collection": "host-state",
                    "rag_source": "latest",
                },
                tags=["infra", "host-state"],
                target="rag_documents",
                action="upsert",
                status="completed",
            )
            if latest_result["ingestion_job_id"]:
                verify_queryability_from_rag(
                    cur,
                    ingestion_job_id=latest_result["ingestion_job_id"],
                    document_ref=latest_result["document_ref"],
                    artifact_kind="host_state_snapshot",
                    source_uri="latest",
                    metadata={"rag_collection": "host-state", "rag_source": "latest"},
                )
            if insights:
                cur.execute(
                    """
                    insert into rag_documents (collection, source, content, metadata, created_at, updated_at)
                    values (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        "host-insights",
                        f"infra:{now.isoformat()}",
                        summary,
                        Json(
                            {
                                "captured_at": now.isoformat(),
                                "host": snapshot["host"],
                                "insights": insights,
                            }
                        ),
                        now,
                        now,
                    ),
                )
                insight_result = upsert_artifact_version(
                    cur,
                    workspace_slug="infra_ops",
                    workspace_name="Infrastructure Ops",
                    project_slug="career_odyssey_vm",
                    project_name="Career Odyssey VM",
                    artifact_slug=f"host-insights-{now.strftime('%Y%m%d%H%M%S')}",
                    title="host-insights",
                    artifact_kind="host_insight",
                    source_kind="system",
                    source_uri=f"infra:{now.isoformat()}",
                    content=summary,
                    metadata={
                        "captured_at": now.isoformat(),
                        "host": snapshot["host"],
                        "insights": insights,
                        "origin": "infra_snapshot",
                        "rag_collection": "host-insights",
                        "rag_source": f"infra:{now.isoformat()}",
                    },
                    tags=["infra", "host-insight"],
                    target="rag_documents",
                    action="upsert",
                    status="completed",
                )
                if insight_result["ingestion_job_id"]:
                    verify_queryability_from_rag(
                        cur,
                        ingestion_job_id=insight_result["ingestion_job_id"],
                        document_ref=insight_result["document_ref"],
                        artifact_kind="host_insight",
                        source_uri=f"infra:{now.isoformat()}",
                        metadata={"rag_collection": "host-insights", "rag_source": f"infra:{now.isoformat()}"},
                    )
                record_insight(
                    cur,
                    workspace_slug="infra_ops",
                    workspace_name="Infrastructure Ops",
                    project_slug="career_odyssey_vm",
                    project_name="Career Odyssey VM",
                    kind="host_insight",
                    title="host-insights",
                    content=summary,
                    metadata={
                        "captured_at": now.isoformat(),
                        "host": snapshot["host"],
                        "insights": insights,
                        "origin": "infra_snapshot",
                    },
                    artifact_id=None,
                )


def render_markdown(snapshot):
    services = "\n".join(
        f"| {item['name']} | {item['status']} |"
        for item in snapshot["services"]
    )
    containers = (
        "\n".join(
            f"| {item['name']} | {item['image']} | {item['status']} | {item['ports']} |"
            for item in snapshot["containers"]
        )
        or "| none | - | - | - |"
    )
    ufw_lines = "\n".join(f"- `{line}`" for line in snapshot["ufw_status"][:12]) or "- unavailable"

    return f"""# Infrastructure Snapshot

Last updated (UTC): `{snapshot['updated_at_utc']}`

## Read This First

- This file is the host-level source of truth for the server behind the agent.
- Hermes terminal commands run against the host with `terminal.backend=local`.
- When asked about deployed infrastructure, use this file before claiming a service is missing.

## Host

- Project: `{snapshot['host']['project_id']}`
- Instance: `{snapshot['host']['instance_name']}`
- Zone: `{snapshot['host']['zone']}`
- Machine type: `{snapshot['host']['machine_type']}`
- External IP: `{snapshot['host']['external_ip']}`
- Internal IP: `{snapshot['host']['internal_ip']}`
- Hostname: `{snapshot['host']['hostname']}`
- Kernel: `{snapshot['host']['kernel']}`

## Services

| Service | Status |
| --- | --- |
{services}

## Containers

| Name | Image | Status | Ports |
| --- | --- | --- | --- |
{containers}

## Endpoints

- Public n8n: `{snapshot['public_endpoints']['n8n']}`
- Public orchestrate: `{snapshot['public_endpoints']['orchestrate']}`
- Public rag-search: `{snapshot['public_endpoints']['rag_search']}`
- Local Hermes API: `{snapshot['local_endpoints']['Hermes API']}`
- Local Hermes dashboard: `{snapshot['local_endpoints']['Hermes dashboard']}`
- Local MCP control plane: `{snapshot['local_endpoints']['MCP control plane']}`
- Local Postgres: `{snapshot['local_endpoints']['Postgres']}`

## Resources

- Memory total: `{snapshot['memory']['total']}`
- Memory available: `{snapshot['memory']['available']}`
- Swap total: `{snapshot['memory']['swap_total']}`
- Swap free: `{snapshot['memory']['swap_free']}`
- Root disk total: `{snapshot['disk_root']['total_gb']} GB`
- Root disk used: `{snapshot['disk_root']['used_gb']} GB`
- Root disk free: `{snapshot['disk_root']['free_gb']} GB`
- Root disk used percent: `{snapshot['disk_root']['used_percent']}%`

## Key Paths

- Workspace: `{snapshot['paths']['workspace']}`
- Hermes home: `{snapshot['paths']['hermes_home']}`
- Automation root: `{snapshot['paths']['automation_root']}`
- n8n env: `{snapshot['paths']['n8n_env']}`
- nginx site: `{snapshot['paths']['nginx_site']}`

## Firewall

{ufw_lines}
"""


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = build_snapshot()
    SNAPSHOT_JSON.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    SNAPSHOT_MD.write_text(render_markdown(snapshot), encoding="utf-8")
    os.chmod(SNAPSHOT_JSON, 0o644)
    os.chmod(SNAPSHOT_MD, 0o644)
    persist_memory(snapshot)
    print(json.dumps({"json": str(SNAPSHOT_JSON), "markdown": str(SNAPSHOT_MD)}))


if __name__ == "__main__":
    main()
