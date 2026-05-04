import json
from pathlib import Path

import psycopg2

from canonical_memory import (
    classify_rag_row,
    ensure_schema,
    record_insight,
    upsert_artifact_version,
    verify_queryability_from_rag,
)


def read_env(path):
    data = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def main():
    env = read_env("/srv/automation/.env")
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        dbname="rag",
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    imported = 0
    skipped = 0
    with conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                select collection, source, content, metadata
                from rag_documents
                where collection in ('host-state','host-insights','host-optimization','obsidian-main','obsidian-rules')
                order by collection, source
                """
            )
            rows = cur.fetchall()
            for collection, source, content, metadata in rows:
                payload = classify_rag_row(collection, source, content, metadata)
                result = upsert_artifact_version(cur, content=content, **payload)
                if result["ingestion_job_id"]:
                    verify_queryability_from_rag(
                        cur,
                        ingestion_job_id=result["ingestion_job_id"],
                        document_ref=result["document_ref"],
                        artifact_kind=payload["artifact_kind"],
                        source_uri=payload["source_uri"],
                        metadata=payload["metadata"],
                    )
                if collection in {"host-insights", "host-optimization"} and result["created"]:
                    record_insight(
                        cur,
                        workspace_slug=payload["workspace_slug"],
                        workspace_name=payload["workspace_name"],
                        project_slug=payload["project_slug"],
                        project_name=payload["project_name"],
                        kind=payload["artifact_kind"],
                        title=payload["title"],
                        content=content,
                        metadata=payload["metadata"],
                        artifact_id=result["artifact_id"],
                    )
                if result["created"]:
                    imported += 1
                else:
                    skipped += 1
    print(json.dumps({"imported_versions": imported, "skipped_existing": skipped}, ensure_ascii=False))


if __name__ == "__main__":
    main()
