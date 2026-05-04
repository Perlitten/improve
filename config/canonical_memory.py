import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from psycopg2.extras import Json


def slugify(value: str, fallback: str = "item") -> str:
    value = (value or "").strip().lower().replace("\\", "/")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:160] or fallback


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


def ensure_workspace(
    cur,
    slug,
    display_name,
    domain=None,
    sensitivity="medium",
    retention="long_term",
    metadata=None,
):
    metadata = metadata or {}
    cur.execute(
        """
        insert into workspaces (slug, display_name, domain, sensitivity_level, retention_policy, metadata_json)
        values (%s,%s,%s,%s,%s,%s)
        on conflict (slug) do update
        set display_name = excluded.display_name,
            domain = excluded.domain,
            sensitivity_level = excluded.sensitivity_level,
            retention_policy = excluded.retention_policy,
            metadata_json = workspaces.metadata_json || excluded.metadata_json,
            updated_at = now()
        returning id
        """,
        (slug, display_name, domain, sensitivity, retention, Json(metadata)),
    )
    return cur.fetchone()[0]


def ensure_project(cur, workspace_id, slug, name, status="active", metadata=None):
    metadata = metadata or {}
    cur.execute(
        """
        insert into projects (workspace_id, slug, name, status, metadata_json)
        values (%s,%s,%s,%s,%s)
        on conflict (workspace_id, slug) do update
        set name = excluded.name,
            status = excluded.status,
            metadata_json = projects.metadata_json || excluded.metadata_json,
            updated_at = now()
        returning id
        """,
        (workspace_id, slug, name, status, Json(metadata)),
    )
    return cur.fetchone()[0]


def record_insight(
    cur,
    *,
    workspace_slug,
    workspace_name,
    project_slug,
    project_name,
    kind,
    title,
    content,
    metadata=None,
    artifact_id=None,
):
    metadata = metadata or {}
    workspace_id = ensure_workspace(cur, workspace_slug, workspace_name, metadata={"origin": "canonical_memory"})
    project_id = ensure_project(cur, workspace_id, project_slug, project_name, metadata={"origin": "canonical_memory"})
    cur.execute(
        """
        insert into insights (workspace_id, project_id, artifact_id, kind, title, content, metadata_json)
        values (%s,%s,%s,%s,%s,%s,%s)
        """,
        (workspace_id, project_id, artifact_id, kind, title, content, Json(metadata)),
    )


def upsert_artifact_version(
    cur,
    *,
    workspace_slug,
    workspace_name,
    project_slug,
    project_name,
    artifact_slug,
    title,
    artifact_kind,
    source_kind,
    source_uri,
    content,
    metadata=None,
    tags=None,
    target="rag_documents",
    action="upsert",
    status="completed",
):
    metadata = metadata or {}
    tags = tags or []
    workspace_id = ensure_workspace(cur, workspace_slug, workspace_name, metadata={"origin": "bootstrap"})
    project_id = ensure_project(cur, workspace_id, project_slug, project_name, metadata={"origin": "bootstrap"})

    cur.execute(
        """
        insert into artifacts (
          workspace_id, project_id, slug, title, artifact_kind, source_kind, source_uri, summary, tags_json, metadata_json
        )
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (workspace_id, slug) do update
        set project_id = excluded.project_id,
            title = excluded.title,
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

    next_version = 1 if not row else row[1] + 1
    document_ref = (
        f"brain://workspace/{workspace_slug}/project/{project_slug}/artifact/{artifact_slug}/version/{next_version}"
    )
    now = datetime.now(timezone.utc)
    cur.execute(
        """
        insert into artifact_versions (artifact_id, version_index, checksum, content, metadata_json, document_ref, created_at)
        values (%s,%s,%s,%s,%s,%s,%s)
        returning id
        """,
        (artifact_id, next_version, checksum, content, Json(metadata), document_ref, now),
    )
    version_id = cur.fetchone()[0]
    cur.execute(
        """
        insert into ingestion_jobs (
          artifact_version_id, target, action, status, document_ref, document_refs, provider, provider_track_ids,
          provider_statuses, metadata_json, created_at, updated_at, completed_at
        )
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
            payload["queryability_status"] = "error"
            payload["queryability_probe_kind"] = "derived_source_match"
            payload["queryability_error"] = str(exc)

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
