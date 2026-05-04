#!/usr/bin/env bash
set -euo pipefail

echo "== databases =="
sudo docker exec -i automation-postgres psql -U automation -d postgres <<'SQL'
select datname
from pg_database
where datistemplate = false
order by datname;
SQL

echo
echo "== rag tables =="
sudo docker exec -i automation-postgres psql -U automation -d rag <<'SQL'
select tablename
from pg_tables
where schemaname = 'public'
order by tablename;
SQL

echo
echo "== canonical artifact counts =="
sudo docker exec -i automation-postgres psql -U automation -d rag <<'SQL'
select
  (select count(*) from workspaces) as workspaces,
  (select count(*) from projects) as projects,
  (select count(*) from artifacts) as artifacts,
  (select count(*) from artifact_versions) as artifact_versions,
  (select count(*) from ingestion_jobs) as ingestion_jobs,
  (select count(*) from insights) as insights;
SQL

echo
echo "== canonical workspace/project groups =="
sudo docker exec -i automation-postgres psql -U automation -d rag <<'SQL'
select w.slug as workspace, p.slug as project, count(*) as artifacts
from artifacts a
join workspaces w on w.id = a.workspace_id
left join projects p on p.id = a.project_id
group by w.slug, p.slug
order by w.slug, p.slug;
SQL

echo
echo "== queryability status =="
sudo docker exec -i automation-postgres psql -U automation -d rag <<'SQL'
select coalesce(metadata_json->>'queryability_status', 'missing') as queryability_status, count(*)
from ingestion_jobs
group by 1
order by 1;
SQL

echo
echo "== rag collections =="
sudo docker exec -i automation-postgres psql -U automation -d rag <<'SQL'
select collection, count(*)
from rag_documents
group by collection
order by collection;
SQL

echo
echo "== infra snapshots =="
sudo docker exec -i automation-postgres psql -U automation -d rag <<'SQL'
select count(*) as infra_snapshots_count
from infra_snapshots;
SQL

echo
echo "== latest host optimization =="
sudo docker exec -i automation-postgres psql -U automation -d rag <<'SQL'
select source, left(content, 500)
from rag_documents
where collection = 'host-optimization'
order by updated_at desc
limit 2;
SQL

echo
echo "== n8n tables sample =="
sudo docker exec -i automation-postgres psql -U automation -d n8n <<'SQL'
select tablename
from pg_tables
where schemaname = 'public'
order by tablename
limit 40;
SQL

echo
echo "== connection facts =="
echo "container=automation-postgres"
echo "user=automation"
echo "dbs=postgres,n8n,rag"
