#!/usr/bin/env bash
set -euo pipefail

echo "== core services =="
systemctl is-active hermes-gateway hermes-dashboard n8n automation-gateway brain-mcp nginx docker

echo
echo "== local health endpoints =="
printf "hermes_api="
curl -fsS http://127.0.0.1:8642/health
printf "\nn8n="
curl -fsS http://127.0.0.1:5678/healthz/readiness
printf "\nautomation_gateway="
curl -fsS http://127.0.0.1:8788/health
printf "\n"

echo
echo "== canonical memory health =="
sudo docker exec -i automation-postgres psql -U automation -d rag <<'SQL'
select
  (select count(*) from workspaces) as workspaces,
  (select count(*) from projects) as projects,
  (select count(*) from artifacts) as artifacts,
  (select count(*) from artifact_versions) as artifact_versions,
  (select count(*) from ingestion_jobs) as ingestion_jobs,
  (select count(*) from insights) as insights,
  (select count(*) from workspaces where slug = 'obsidian_vault') as legacy_obsidian_workspaces;

select coalesce(metadata_json->>'queryability_status', 'missing') as queryability_status, count(*)
from ingestion_jobs
group by 1
order by 1;

select w.slug as workspace, p.slug as project, count(*) as artifacts
from artifacts a
join workspaces w on w.id = a.workspace_id
left join projects p on p.id = a.project_id
group by w.slug, p.slug
order by w.slug, p.slug;
SQL

echo
echo "== credential presence redacted =="
python3 - <<'PY'
from pathlib import Path

paths = [Path("/home/Bilirubin/.hermes/.env"), Path("/srv/automation/n8n.env"), Path("/srv/automation/.env")]
secret_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS", "PRIVATE", "ENCRYPTION", "CREDENTIAL")
for path in paths:
    if not path.exists():
        continue
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key = line.split("=", 1)[0].strip()
        if any(marker in key.upper() for marker in secret_markers):
            names.append(key)
    print(f"{path}: " + (", ".join(sorted(names)) if names else "no secret-like keys detected"))
PY
