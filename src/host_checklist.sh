#!/usr/bin/env bash
set -euo pipefail

echo "== host =="
hostname
uname -a

echo
echo "== infrastructure snapshot =="
if [ -f /home/Bilirubin/workspace/INFRASTRUCTURE.md ]; then
  sed -n '1,80p' /home/Bilirubin/workspace/INFRASTRUCTURE.md
else
  echo "missing /workspace/INFRASTRUCTURE.md"
fi

echo
echo "== systemd services =="
sudo systemctl is-active hermes-gateway hermes-dashboard n8n automation-gateway nginx docker || true

echo
echo "== endpoint health =="
curl -fsS http://127.0.0.1:5678/healthz/readiness || true
echo
curl -fsS http://127.0.0.1:8788/health || true
echo

echo "== docker containers =="
sudo docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}' || true

echo
echo "== memory collections =="
sudo docker exec -i automation-postgres psql -U automation -d rag <<'SQL' || true
select collection, count(*)
from rag_documents
where collection in ('host-state','host-insights','host-optimization','obsidian-main','obsidian-rules')
group by collection
order by collection;
SQL
