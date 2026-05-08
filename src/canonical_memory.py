import hashlib
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json


def slugify(value: str, fallback: str = "item") -> str:
    value = unicodedata.normalize("NFC", value or "")
    value = (value or "").strip().lower().replace("\\", "/")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:160] or fallback


def safe_exception_metadata(exc: Exception) -> dict:
    message = str(exc)
    return {
        "type": type(exc).__name__,
        "hash": hashlib.sha256(message.encode("utf-8", errors="replace")).hexdigest()[:16],
    }


def _read_env(path: str) -> dict:
    data = {}
    env_path = Path(path)
    if not env_path.exists():
        return data
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip("\"'")
    return data


def _get_conn_from_env():
    env = {}
    env.update(_read_env("/srv/automation/n8n.env"))
    env.update(_read_env("/srv/automation/.env"))
    env.update(os.environ)
    return psycopg2.connect(
        host=env.get("POSTGRES_HOST") or env.get("DB_POSTGRESDB_HOST") or "127.0.0.1",
        port=int(env.get("POSTGRES_PORT") or env.get("DB_POSTGRESDB_PORT") or 5432),
        dbname=env.get("POSTGRES_DB") or "rag",
        user=env.get("POSTGRES_USER") or env.get("DB_POSTGRESDB_USER") or os.getenv("USER", "automation"),
        password=env.get("POSTGRES_PASSWORD") or env.get("DB_POSTGRESDB_PASSWORD") or "",
        options="-c search_path=automation,public",
    )


def display_name(value: str, fallback: str = "Item") -> str:
    value = (value or "").strip()
    if not value:
        return fallback
    if re.search(r"[A-Z ]", value):
        return value
    return re.sub(r"\s+", " ", value.replace("-", " ").replace("_", " ")).title()


def summarize_text(text: str, limit: int = 280) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def normalize_source_path(source: str, metadata: dict) -> str:
    raw = (metadata or {}).get("path") or source or ""
    raw = raw.replace("\\", "/")
    raw = re.sub(r"^[A-Za-z]:/Claude/Claude/", "", raw)
    return raw.lstrip("/")


def infer_artifact_kind(collection: str, path: str, title: str) -> str:
    if collection == "obsidian-rules":
        return "policy_rule"

    name = (title or Path(path).stem or "").lower()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", Path(path).stem):
        return "daily_note"
    if "adr" in name or "decision" in name:
        return "decision_log"
    if "risk" in name:
        return "risk_register"
    if "roadmap" in name or "strategic" in name or "vision" in name or "hub" in name:
        return "strategy_note"
    if "index" in name or name == "readme":
        return "project_index"
    if "architecture" in name or "topology" in name or "sequence" in name or "module" in name:
        return "architecture_map"
    if "schema" in name or "contract" in name or "ontology" in name:
        return "data_standards"
    if "audit" in name:
        return "audit_note"
    if "health" in name:
        return "health_check"
    if "safety" in name or "protocol" in name or "privacy" in name or "security" in name or "guardrail" in name:
        return "safety_protocol"
    if "report" in name or "completion" in name or "notes" in name or "changelog" in name:
        return "change_summary"
    if "identity" in name or "preferences" in name:
        return "identity_note"
    if "overview" in name or "current state" in name or "status" in name:
        return "current_state"
    return "knowledge_note"


def resolve_obsidian_taxonomy(path: str):
    parts = [part for part in path.split("/") if part]
    if not parts:
        return {
            "workspace_slug": "strategy_hub",
            "workspace_name": "Strategy Hub",
            "project_slug": "career_odyssey_hq",
            "project_name": "Career Odyssey HQ",
        }

    if parts[0] == "Daily":
        return {
            "workspace_slug": "life_core",
            "workspace_name": "Life Core",
            "project_slug": "daily_journal",
            "project_name": "Daily Journal",
        }

    if parts[0] == "Inbox":
        return {
            "workspace_slug": "life_core",
            "workspace_name": "Life Core",
            "project_slug": "inbox_capture",
            "project_name": "Inbox Capture",
        }

    if len(parts) >= 3 and parts[0] == "Memory" and parts[1] == "projects":
        raw_project = parts[2]
        if raw_project.lower().endswith(".md"):
            stem = Path(raw_project).stem
            raw_project = "projects-hub" if stem.lower() == "readme" else stem
        return {
            "workspace_slug": "dev_projects_graph",
            "workspace_name": "Dev Projects Graph",
            "project_slug": slugify(raw_project, "project"),
            "project_name": display_name(raw_project, "Project"),
        }

    if len(parts) >= 4 and parts[0] == "System" and parts[1] == "Memory" and parts[2] == "projects":
        raw_project = parts[3]
        if raw_project.lower().endswith(".md"):
            stem = Path(raw_project).stem
            raw_project = "projects-hub" if stem.lower() == "readme" else stem
        return {
            "workspace_slug": "dev_projects_graph",
            "workspace_name": "Dev Projects Graph",
            "project_slug": slugify(raw_project, "project"),
            "project_name": display_name(raw_project, "Project"),
        }

    if len(parts) >= 2 and parts[0] == "System" and parts[1] == "Architecture":
        raw_project = parts[2] if len(parts) >= 3 and not parts[2].lower().endswith(".md") else "system-architecture"
        return {
            "workspace_slug": "dev_projects_graph",
            "workspace_name": "Dev Projects Graph",
            "project_slug": slugify(raw_project, "system-architecture"),
            "project_name": display_name(raw_project, "System Architecture"),
        }

    if len(parts) >= 3 and parts[0] == "System" and parts[1] == "Memory" and parts[2] == "Codex":
        return {
            "workspace_slug": "agent_ops",
            "workspace_name": "Agent Ops",
            "project_slug": "codex_operating_system",
            "project_name": "Codex Operating System",
        }

    if len(parts) >= 2 and parts[0] == "System" and parts[1] == "Audit":
        return {
            "workspace_slug": "agent_ops",
            "workspace_name": "Agent Ops",
            "project_slug": "audit_trail",
            "project_name": "Audit Trail",
        }

    if len(parts) >= 2 and parts[0] == "System" and parts[1] == "Health":
        return {
            "workspace_slug": "agent_ops",
            "workspace_name": "Agent Ops",
            "project_slug": "system_health",
            "project_name": "System Health",
        }

    if len(parts) >= 2 and parts[0] == "System" and parts[1] == "Tools":
        return {
            "workspace_slug": "agent_ops",
            "workspace_name": "Agent Ops",
            "project_slug": "tooling_ops",
            "project_name": "Tooling Ops",
        }

    if len(parts) >= 2 and parts[0] == "System" and parts[1] == "Memory":
        return {
            "workspace_slug": "agent_ops",
            "workspace_name": "Agent Ops",
            "project_slug": "personal_model",
            "project_name": "Personal Model",
        }

    return {
        "workspace_slug": "strategy_hub",
        "workspace_name": "Strategy Hub",
        "project_slug": "career_odyssey_hq",
        "project_name": "Career Odyssey HQ",
    }


def derive_rag_locator(*, artifact_kind=None, source_uri=None, metadata=None):
    metadata = metadata or {}
    collection = metadata.get("rag_collection")
    source = metadata.get("rag_source") or source_uri
    if collection and source:
        return collection, source

    if artifact_kind == "host_state_snapshot":
        return "host-state", source_uri or "latest"
    if artifact_kind == "host_insight":
        return "host-insights", source_uri or "latest"
    if artifact_kind == "host_optimization":
        return "host-optimization", source_uri or "latest"
    if artifact_kind == "policy_rule" and source_uri:
        return "obsidian-rules", source_uri
    if source_uri and (
        source_uri.startswith("Daily/")
        or source_uri.startswith("Inbox/")
        or source_uri.startswith("Memory/")
        or source_uri.startswith("System/")
        or source_uri.endswith(".md")
    ):
        return "obsidian-main", source_uri
    return None, None


def ensure_schema(cur):
    # Preflight migration for the legacy production schema. The old shim created
    # narrower tables first; add the new columns before indexes reference them.
    cur.execute(
        """
        alter table if exists workspaces add column if not exists slug text;
        alter table if exists workspaces add column if not exists display_name text;
        alter table if exists workspaces add column if not exists name text;
        alter table if exists workspaces add column if not exists domain text;
        alter table if exists workspaces add column if not exists sensitivity_level text;
        alter table if exists workspaces add column if not exists retention_policy text;
        alter table if exists workspaces add column if not exists metadata_json jsonb;
        alter table if exists workspaces add column if not exists metadata jsonb;
        alter table if exists workspaces add column if not exists updated_at timestamptz;

        alter table if exists projects add column if not exists slug text;
        alter table if exists projects add column if not exists status text;
        alter table if exists projects add column if not exists metadata_json jsonb;
        alter table if exists projects add column if not exists metadata jsonb;
        alter table if exists projects add column if not exists updated_at timestamptz;

        alter table if exists artifacts add column if not exists workspace_id bigint;
        alter table if exists artifacts add column if not exists slug text;
        alter table if exists artifacts add column if not exists title text;
        alter table if exists artifacts add column if not exists artifact_kind text;
        alter table if exists artifacts add column if not exists source_kind text;
        alter table if exists artifacts add column if not exists source_uri text;
        alter table if exists artifacts add column if not exists summary text;
        alter table if exists artifacts add column if not exists tags_json jsonb;
        alter table if exists artifacts add column if not exists metadata_json jsonb;
        alter table if exists artifacts add column if not exists name text;
        alter table if exists artifacts add column if not exists updated_at timestamptz;

        alter table if exists artifact_versions add column if not exists version_index integer;
        alter table if exists artifact_versions add column if not exists version integer;
        alter table if exists artifact_versions add column if not exists checksum text;
        alter table if exists artifact_versions add column if not exists metadata_json jsonb;
        alter table if exists artifact_versions add column if not exists document_ref text;

        alter table if exists ingestion_jobs add column if not exists target text;
        alter table if exists ingestion_jobs add column if not exists action text;
        alter table if exists ingestion_jobs add column if not exists document_ref text;
        alter table if exists ingestion_jobs add column if not exists document_refs jsonb;
        alter table if exists ingestion_jobs add column if not exists provider text;
        alter table if exists ingestion_jobs add column if not exists provider_track_ids jsonb;
        alter table if exists ingestion_jobs add column if not exists provider_statuses jsonb;
        alter table if exists ingestion_jobs add column if not exists metadata_json jsonb;
        alter table if exists ingestion_jobs add column if not exists error_message text;
        alter table if exists ingestion_jobs add column if not exists error text;
        alter table if exists ingestion_jobs add column if not exists updated_at timestamptz;
        alter table if exists ingestion_jobs add column if not exists completed_at timestamptz;

        alter table if exists insights add column if not exists workspace_id bigint;
        alter table if exists insights add column if not exists project_id bigint;
        alter table if exists insights add column if not exists artifact_id bigint;
        alter table if exists insights add column if not exists kind text;
        alter table if exists insights add column if not exists title text;
        alter table if exists insights add column if not exists content text;
        alter table if exists insights add column if not exists metadata_json jsonb;
        alter table if exists insights add column if not exists workspace text;
        alter table if exists insights add column if not exists project text;
        alter table if exists insights add column if not exists insight text;
        alter table if exists insights add column if not exists metadata jsonb;
        """
    )
    cur.execute(
        """
        create table if not exists workspaces (
          id bigserial primary key,
          slug text not null unique,
          display_name text not null,
          domain text,
          sensitivity_level text,
          retention_policy text,
          metadata_json jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        );

        create table if not exists projects (
          id bigserial primary key,
          workspace_id bigint not null references workspaces(id) on delete cascade,
          slug text not null,
          name text not null,
          status text,
          metadata_json jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          unique (workspace_id, slug)
        );

        create table if not exists artifacts (
          id bigserial primary key,
          workspace_id bigint not null references workspaces(id) on delete cascade,
          project_id bigint references projects(id) on delete set null,
          slug text not null,
          title text not null,
          artifact_kind text not null,
          source_kind text,
          source_uri text,
          summary text,
          tags_json jsonb not null default '[]'::jsonb,
          metadata_json jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          unique (workspace_id, slug)
        );

        create table if not exists artifact_versions (
          id bigserial primary key,
          artifact_id bigint not null references artifacts(id) on delete cascade,
          version_index integer not null,
          checksum text not null,
          content text not null,
          metadata_json jsonb not null default '{}'::jsonb,
          document_ref text not null unique,
          created_at timestamptz not null default now(),
          unique (artifact_id, version_index)
        );

        create table if not exists ingestion_jobs (
          id bigserial primary key,
          artifact_version_id bigint references artifact_versions(id) on delete set null,
          target text not null,
          action text not null,
          status text not null,
          document_ref text,
          document_refs jsonb not null default '[]'::jsonb,
          provider text,
          provider_track_ids jsonb not null default '[]'::jsonb,
          provider_statuses jsonb not null default '[]'::jsonb,
          metadata_json jsonb not null default '{}'::jsonb,
          error_message text,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          completed_at timestamptz
        );

        create table if not exists insights (
          id bigserial primary key,
          workspace_id bigint not null references workspaces(id) on delete cascade,
          project_id bigint references projects(id) on delete set null,
          artifact_id bigint references artifacts(id) on delete set null,
          kind text not null,
          title text not null,
          content text not null,
          metadata_json jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now()
        );

        create index if not exists idx_projects_workspace_slug on projects(workspace_id, slug);
        create index if not exists idx_artifacts_workspace_kind on artifacts(workspace_id, artifact_kind);
        create index if not exists idx_artifact_versions_artifact on artifact_versions(artifact_id, version_index desc);
        create index if not exists idx_ingestion_jobs_status on ingestion_jobs(status, target);
        """
    )
    cur.execute(
        """
        alter table workspaces add column if not exists name text;
        alter table workspaces add column if not exists metadata jsonb;
        alter table projects add column if not exists metadata jsonb;
        alter table artifacts add column if not exists name text;
        alter table artifact_versions add column if not exists version integer;
        alter table ingestion_jobs add column if not exists error text;
        alter table ingestion_jobs add column if not exists started_at timestamptz;
        alter table ingestion_jobs add column if not exists finished_at timestamptz;
        alter table insights add column if not exists workspace text;
        alter table insights add column if not exists project text;
        alter table insights add column if not exists insight text;
        alter table insights add column if not exists metadata jsonb;

        update workspaces
        set slug = coalesce(nullif(slug, ''), 'workspace-' || id::text),
            display_name = coalesce(nullif(display_name, ''), nullif(name, ''), 'Workspace ' || id::text),
            name = coalesce(nullif(name, ''), nullif(display_name, ''), 'Workspace ' || id::text),
            metadata_json = coalesce(metadata_json, '{}'::jsonb),
            metadata = coalesce(metadata, '{}'::jsonb),
            updated_at = coalesce(updated_at, created_at, now())
        where slug is null
           or slug = ''
           or display_name is null
           or display_name = ''
           or name is null
           or name = ''
           or metadata_json is null
           or metadata is null
           or updated_at is null;

        update projects
        set slug = coalesce(nullif(slug, ''), 'project-' || id::text),
            status = coalesce(nullif(status, ''), 'active'),
            metadata_json = coalesce(metadata_json, '{}'::jsonb),
            metadata = coalesce(metadata, '{}'::jsonb),
            updated_at = coalesce(updated_at, created_at, now())
        where slug is null
           or slug = ''
           or status is null
           or status = ''
           or metadata_json is null
           or metadata is null
           or updated_at is null;

        update artifacts a
        set workspace_id = coalesce(a.workspace_id, p.workspace_id),
            slug = coalesce(nullif(a.slug, ''), 'artifact-' || a.id::text),
            title = coalesce(nullif(a.title, ''), nullif(a.name, ''), 'Artifact ' || a.id::text),
            name = coalesce(nullif(a.name, ''), nullif(a.title, ''), 'Artifact ' || a.id::text),
            artifact_kind = coalesce(nullif(a.artifact_kind, ''), 'legacy_artifact'),
            tags_json = coalesce(a.tags_json, '[]'::jsonb),
            metadata_json = coalesce(a.metadata_json, '{}'::jsonb),
            updated_at = coalesce(a.updated_at, a.created_at, now())
        from projects p
        where a.project_id = p.id
          and (
            a.workspace_id is null
            or a.slug is null
            or a.slug = ''
            or a.title is null
            or a.title = ''
            or a.name is null
            or a.name = ''
            or a.artifact_kind is null
            or a.artifact_kind = ''
            or a.tags_json is null
            or a.metadata_json is null
            or a.updated_at is null
          );

        update artifacts
        set slug = coalesce(nullif(slug, ''), 'artifact-' || id::text),
            title = coalesce(nullif(title, ''), nullif(name, ''), 'Artifact ' || id::text),
            name = coalesce(nullif(name, ''), nullif(title, ''), 'Artifact ' || id::text),
            artifact_kind = coalesce(nullif(artifact_kind, ''), 'legacy_artifact'),
            tags_json = coalesce(tags_json, '[]'::jsonb),
            metadata_json = coalesce(metadata_json, '{}'::jsonb),
            updated_at = coalesce(updated_at, created_at, now())
        where slug is null
           or slug = ''
           or title is null
           or title = ''
           or name is null
           or name = ''
           or artifact_kind is null
           or artifact_kind = ''
           or tags_json is null
           or metadata_json is null
           or updated_at is null;

        update artifact_versions
        set version_index = coalesce(version_index, version, 1),
            version = coalesce(version, version_index, 1),
            checksum = coalesce(checksum, md5(coalesce(content, ''))),
            metadata_json = coalesce(metadata_json, '{}'::jsonb),
            document_ref = coalesce(document_ref, 'legacy://artifact-version/' || id::text)
        where version_index is null
           or version is null
           or checksum is null
           or checksum = ''
           or metadata_json is null
           or document_ref is null
           or document_ref = '';

        update ingestion_jobs
        set target = coalesce(nullif(target, ''), 'canonical_memory'),
            action = coalesce(nullif(action, ''), 'legacy'),
            document_refs = coalesce(document_refs, '[]'::jsonb),
            provider = coalesce(nullif(provider, ''), 'legacy'),
            provider_track_ids = coalesce(provider_track_ids, '[]'::jsonb),
            provider_statuses = coalesce(provider_statuses, '[]'::jsonb),
            metadata_json = coalesce(metadata_json, '{}'::jsonb),
            error_message = coalesce(error_message, error),
            updated_at = coalesce(updated_at, finished_at, started_at, created_at, now()),
            completed_at = coalesce(completed_at, finished_at)
        where target is null
           or target = ''
           or action is null
           or action = ''
           or document_refs is null
           or provider_track_ids is null
           or provider_statuses is null
           or metadata_json is null
           or updated_at is null;

        update insights
        set kind = coalesce(nullif(kind, ''), 'legacy_insight'),
            title = coalesce(nullif(title, ''), left(coalesce(insight, content, 'Insight ' || id::text), 200)),
            content = coalesce(content, insight, ''),
            metadata_json = coalesce(metadata_json, metadata, '{}'::jsonb),
            metadata = coalesce(metadata, metadata_json, '{}'::jsonb)
        where kind is null
           or kind = ''
           or title is null
           or title = ''
           or content is null
           or metadata_json is null
           or metadata is null;

        alter table workspaces alter column slug set not null;
        alter table workspaces alter column display_name set not null;
        alter table workspaces alter column metadata_json set default '{}'::jsonb;
        alter table workspaces alter column metadata_json set not null;

        alter table projects alter column slug set not null;
        alter table projects alter column status set default 'active';
        alter table projects alter column metadata_json set default '{}'::jsonb;
        alter table projects alter column metadata_json set not null;

        alter table artifacts alter column slug set not null;
        alter table artifacts alter column title set not null;
        alter table artifacts alter column artifact_kind set not null;
        alter table artifacts alter column tags_json set default '[]'::jsonb;
        alter table artifacts alter column tags_json set not null;
        alter table artifacts alter column metadata_json set default '{}'::jsonb;
        alter table artifacts alter column metadata_json set not null;

        alter table artifact_versions alter column version_index set not null;
        alter table artifact_versions alter column checksum set not null;
        alter table artifact_versions alter column metadata_json set default '{}'::jsonb;
        alter table artifact_versions alter column metadata_json set not null;
        alter table artifact_versions alter column document_ref set not null;

        alter table ingestion_jobs alter column target set default 'canonical_memory';
        alter table ingestion_jobs alter column action set default 'upsert';
        alter table ingestion_jobs alter column document_refs set default '[]'::jsonb;
        alter table ingestion_jobs alter column document_refs set not null;
        alter table ingestion_jobs alter column provider_track_ids set default '[]'::jsonb;
        alter table ingestion_jobs alter column provider_track_ids set not null;
        alter table ingestion_jobs alter column provider_statuses set default '[]'::jsonb;
        alter table ingestion_jobs alter column provider_statuses set not null;
        alter table ingestion_jobs alter column metadata_json set default '{}'::jsonb;
        alter table ingestion_jobs alter column metadata_json set not null;

        alter table insights alter column workspace drop not null;
        alter table insights alter column project drop not null;
        alter table insights alter column insight drop not null;
        alter table insights alter column metadata_json set default '{}'::jsonb;

        create unique index if not exists workspaces_slug_unique_full on workspaces(slug);
        create unique index if not exists projects_workspace_slug_unique_full on projects(workspace_id, slug);
        create unique index if not exists artifacts_workspace_slug_unique_full on artifacts(workspace_id, slug);
        create unique index if not exists artifact_versions_artifact_version_index_unique_full
            on artifact_versions(artifact_id, version_index);
        create unique index if not exists artifact_versions_document_ref_unique_full on artifact_versions(document_ref);
        """
    )


def ensure_workspace(
    cur,
    slug,
    display_name,
    domain=None,
    sensitivity="medium",
    retention="long_term",
    metadata=None,
):
    slug = slugify(slug or display_name, "workspace")
    workspace_display_name = display_name or globals()["display_name"](slug, "Workspace")
    metadata = metadata or {}
    cur.execute(
        """
        insert into workspaces (slug, display_name, name, domain, sensitivity_level, retention_policy, metadata_json, metadata)
        values (%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (name) do update
        set slug = excluded.slug,
            display_name = excluded.display_name,
            domain = excluded.domain,
            sensitivity_level = excluded.sensitivity_level,
            retention_policy = excluded.retention_policy,
            metadata_json = workspaces.metadata_json || excluded.metadata_json,
            metadata = coalesce(workspaces.metadata, '{}'::jsonb) || excluded.metadata,
            updated_at = now()
        returning id
        """,
        (slug, workspace_display_name, workspace_display_name, domain, sensitivity, retention, Json(metadata), Json(metadata)),
    )
    return cur.fetchone()[0]


def ensure_project(cur, workspace_id, slug, name, status="active", metadata=None):
    if isinstance(status, dict) and metadata is None:
        metadata = status
        status = "active"
    slug = slugify(slug or name, "project")
    metadata = metadata or {}
    cur.execute(
        """
        insert into projects (workspace_id, slug, name, status, metadata_json, metadata)
        values (%s,%s,%s,%s,%s,%s)
        on conflict (workspace_id, name) do update
        set slug = excluded.slug,
            status = excluded.status,
            metadata_json = projects.metadata_json || excluded.metadata_json,
            metadata = coalesce(projects.metadata, '{}'::jsonb) || excluded.metadata,
            updated_at = now()
        returning id
        """,
        (workspace_id, slug, name, status, Json(metadata), Json(metadata)),
    )
    return cur.fetchone()[0]


def record_insight(
    cur,
    workspace=None,
    project=None,
    insight=None,
    metadata=None,
    *,
    workspace_slug=None,
    workspace_name=None,
    project_slug=None,
    project_name=None,
    kind=None,
    title=None,
    content=None,
    artifact_id=None,
):
    metadata = metadata or {}
    workspace_slug = slugify(workspace_slug or workspace or workspace_name, "workspace")
    workspace_name = workspace_name or globals()["display_name"](workspace or workspace_slug, "Workspace")
    project_slug = slugify(project_slug or project or project_name, "project")
    project_name = project_name or globals()["display_name"](project or project_slug, "Project")
    kind = kind or "legacy_insight"
    content = content if content is not None else (insight or "")
    title = title or summarize_text(insight or content or kind, 180)
    workspace_id = ensure_workspace(cur, workspace_slug, workspace_name, metadata={"origin": "canonical_memory"})
    project_id = ensure_project(cur, workspace_id, project_slug, project_name, metadata={"origin": "canonical_memory"})
    cur.execute(
        """
        insert into insights (
          workspace_id, project_id, artifact_id, kind, title, content, metadata_json,
          workspace, project, insight, metadata
        )
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            workspace_id,
            project_id,
            artifact_id,
            kind,
            title,
            content,
            Json(metadata),
            workspace_slug,
            project_slug,
            content,
            Json(metadata),
        ),
    )


def upsert_artifact_version(cur, **kwargs):
    workspace_slug = slugify(
        kwargs.get("workspace_slug") or kwargs.get("workspace") or kwargs.get("workspace_name"),
        "workspace",
    )
    workspace_name = kwargs.get("workspace_name") or globals()["display_name"](workspace_slug, "Workspace")
    project_slug = slugify(
        kwargs.get("project_slug") or kwargs.get("project") or kwargs.get("project_name"),
        "project",
    )
    project_name = kwargs.get("project_name") or globals()["display_name"](project_slug, "Project")
    artifact_slug = slugify(
        kwargs.get("artifact_slug") or kwargs.get("artifact_name") or kwargs.get("name") or kwargs.get("title"),
        "artifact",
    )
    title = kwargs.get("title") or kwargs.get("artifact_name") or kwargs.get("name") or globals()["display_name"](
        artifact_slug, "Artifact"
    )
    artifact_kind = kwargs.get("artifact_kind") or kwargs.get("kind") or "legacy_artifact"
    source_kind = kwargs.get("source_kind") or kwargs.get("source_type") or "unknown"
    source_uri = kwargs.get("source_uri") or kwargs.get("source") or artifact_slug
    content = kwargs.get("content") or ""
    target = kwargs.get("target", "rag_documents")
    action = kwargs.get("action", "upsert")
    status = kwargs.get("status", "completed")
    requested_version = kwargs.get("version") or kwargs.get("version_index")
    metadata = kwargs.get("metadata") or {}
    tags = kwargs.get("tags") or []
    workspace_id = ensure_workspace(cur, workspace_slug, workspace_name, metadata={"origin": "bootstrap"})
    project_id = ensure_project(cur, workspace_id, project_slug, project_name, metadata={"origin": "bootstrap"})

    cur.execute(
        """
        insert into artifacts (
          workspace_id, project_id, slug, title, name, artifact_kind, source_kind, source_uri, summary,
          tags_json, metadata_json
        )
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (workspace_id, slug) do update
        set project_id = excluded.project_id,
            title = excluded.title,
            name = excluded.name,
            artifact_kind = excluded.artifact_kind,
            source_kind = excluded.source_kind,
            source_uri = excluded.source_uri,
            summary = excluded.summary,
            tags_json = excluded.tags_json,
            metadata_json = artifacts.metadata_json || excluded.metadata_json,
            updated_at = now()
        returning id
        """,
        (
            workspace_id,
            project_id,
            artifact_slug,
            title,
            title,
            artifact_kind,
            source_kind,
            source_uri,
            summarize_text(content),
            Json(tags),
            Json(metadata),
        ),
    )
    artifact_id = cur.fetchone()[0]

    checksum = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
    cur.execute(
        """
        select id, version_index, checksum, document_ref
        from artifact_versions
        where artifact_id = %s
        order by version_index desc
        limit 1
        """,
        (artifact_id,),
    )
    row = cur.fetchone()
    if row and row[2] == checksum:
        cur.execute(
            """
            select id
            from ingestion_jobs
            where artifact_version_id = %s
            order by id desc
            limit 1
            """,
            (row[0],),
        )
        job_row = cur.fetchone()
        return {
            "artifact_id": artifact_id,
            "version_id": row[0],
            "version_index": row[1],
            "document_ref": row[3],
            "ingestion_job_id": job_row[0] if job_row else None,
            "created": False,
        }

    next_version = int(requested_version) if requested_version and not row else (1 if not row else row[1] + 1)
    document_ref = (
        f"brain://workspace/{workspace_slug}/project/{project_slug}/artifact/{artifact_slug}/version/{next_version}"
    )
    now = datetime.now(timezone.utc)
    cur.execute(
        """
        insert into artifact_versions (
          artifact_id, version_index, version, checksum, content, metadata_json, document_ref, created_at
        )
        values (%s,%s,%s,%s,%s,%s,%s,%s)
        returning id
        """,
        (artifact_id, next_version, next_version, checksum, content, Json(metadata), document_ref, now),
    )
    version_id = cur.fetchone()[0]
    cur.execute(
        """
        insert into ingestion_jobs (
          artifact_version_id, target, action, status, document_ref, document_refs, provider, provider_track_ids,
          provider_statuses, metadata_json, error_message, error, started_at, finished_at, created_at, updated_at,
          completed_at
        )
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        returning id
        """,
        (
            version_id,
            target,
            action,
            status,
            document_ref,
            Json([document_ref]),
            "local-bootstrap",
            Json([]),
            Json([status]),
            Json(metadata),
            None,
            None,
            now,
            now if status == "completed" else None,
            now,
            now,
            now if status == "completed" else None,
        ),
    )
    ingestion_job_id = cur.fetchone()[0]
    return {
        "artifact_id": artifact_id,
        "version_id": version_id,
        "version_index": next_version,
        "document_ref": document_ref,
        "ingestion_job_id": ingestion_job_id,
        "created": True,
    }


def verify_queryability_from_rag(
    cur,
    *,
    ingestion_job_id,
    document_ref,
    rag_collection=None,
    rag_source=None,
    artifact_kind=None,
    source_uri=None,
    metadata=None,
):
    metadata = metadata or {}
    rag_collection = rag_collection or metadata.get("rag_collection")
    rag_source = rag_source or metadata.get("rag_source")
    if not rag_collection or not rag_source:
        rag_collection, rag_source = derive_rag_locator(
            artifact_kind=artifact_kind,
            source_uri=source_uri,
            metadata=metadata,
        )

    checked_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "queryability_checked_at": checked_at,
        "queryability_expected_refs": [document_ref] if document_ref else [],
        "queryability_matched_refs": [],
        "queryability_result_count": 0,
        "queryability_error": None,
        "derived_collection": rag_collection,
        "derived_source": rag_source,
    }

    if not rag_collection or not rag_source:
        payload["queryability_status"] = "skipped"
        payload["queryability_probe_kind"] = "missing_locator"
    else:
        cur.execute("savepoint canonical_queryability_probe")
        try:
            cur.execute(
                """
                select count(*)
                from rag_documents
                where collection = %s and source = %s
                """,
                (rag_collection, rag_source),
            )
            count = int(cur.fetchone()[0])
            payload["queryability_result_count"] = count
            payload["queryability_probe_kind"] = "derived_source_match"
            if count > 0:
                payload["queryability_status"] = "passed"
                payload["queryability_matched_refs"] = [document_ref] if document_ref else []
            else:
                payload["queryability_status"] = "failed"
                payload["queryability_error"] = "No matching rag_documents row found for derived locator."
        except Exception as exc:  # pragma: no cover
            cur.execute("rollback to savepoint canonical_queryability_probe")
            payload["queryability_status"] = "error"
            payload["queryability_probe_kind"] = "derived_source_match"
            payload["queryability_error"] = safe_exception_metadata(exc)
        finally:
            cur.execute("release savepoint canonical_queryability_probe")

    cur.execute(
        """
        update ingestion_jobs
        set metadata_json = coalesce(metadata_json, '{}'::jsonb) || %s,
            updated_at = now()
        where id = %s
        """,
        (Json(payload), ingestion_job_id),
    )
    return payload


def classify_obsidian_row(collection, source, metadata):
    metadata = metadata or {}
    path = normalize_source_path(source, metadata)
    title = metadata.get("title") or Path(path).stem or ("Obsidian Rule" if collection == "obsidian-rules" else "Obsidian Note")
    taxonomy = resolve_obsidian_taxonomy(path)
    artifact_kind = infer_artifact_kind(collection, path, title)
    tags = ["obsidian", collection, taxonomy["workspace_slug"], taxonomy["project_slug"]]
    if collection == "obsidian-rules":
        tags.append("rule")
    parts = [part for part in path.split("/") if part]
    if parts:
        tags.append(slugify(parts[0], "obsidian-root"))
    return {
        **taxonomy,
        "artifact_slug": slugify(path or source, "obsidian-item"),
        "title": title,
        "artifact_kind": artifact_kind,
        "source_kind": "obsidian",
        "source_uri": path or source,
        "tags": tags,
        "metadata": {
            "rag_collection": collection,
            "rag_source": source,
            "obsidian_path": path,
            "classification_version": 2,
            **metadata,
        },
    }


def classify_rag_row(collection, source, content, metadata):
    metadata = metadata or {}
    source = source or "unknown"
    if collection in {"obsidian-main", "obsidian-rules"}:
        return classify_obsidian_row(collection, source, metadata)

    if collection in {"host-state", "host-insights", "host-optimization"}:
        artifact_kind_map = {
            "host-state": "host_state_snapshot",
            "host-insights": "host_insight",
            "host-optimization": "host_optimization",
        }
        return {
            "workspace_slug": "infra_ops",
            "workspace_name": "Infrastructure Ops",
            "project_slug": "career_odyssey_vm",
            "project_name": "Career Odyssey VM",
            "artifact_slug": slugify(f"{collection}-{source}", collection),
            "title": source if source != "latest" else collection,
            "artifact_kind": artifact_kind_map[collection],
            "source_kind": "system",
            "source_uri": source,
            "tags": ["infra", collection],
            "metadata": {"rag_collection": collection, "rag_source": source, **metadata},
        }

    return {
        "workspace_slug": "legacy_memory",
        "workspace_name": "Legacy Memory",
        "project_slug": "legacy_rag",
        "project_name": "Legacy RAG Imports",
        "artifact_slug": slugify(f"{collection}-{source}", "legacy-item"),
        "title": source or collection,
        "artifact_kind": "legacy_import",
        "source_kind": "rag",
        "source_uri": source,
        "tags": ["legacy", collection],
        "metadata": {"rag_collection": collection, "rag_source": source, **metadata},
    }
