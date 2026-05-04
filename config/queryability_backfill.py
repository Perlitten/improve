import json
from pathlib import Path

import psycopg2

from canonical_memory import ensure_schema, verify_queryability_from_rag


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
    summary = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    with conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                select
                  ij.id,
                  ij.document_ref,
                  ij.metadata_json,
                  a.artifact_kind,
                  a.source_uri
                from ingestion_jobs ij
                join artifact_versions av on av.id = ij.artifact_version_id
                join artifacts a on a.id = av.artifact_id
                order by ij.id
                """
            )
            rows = cur.fetchall()
            for ingestion_job_id, document_ref, metadata, artifact_kind, source_uri in rows:
                result = verify_queryability_from_rag(
                    cur,
                    ingestion_job_id=ingestion_job_id,
                    document_ref=document_ref,
                    artifact_kind=artifact_kind,
                    source_uri=source_uri,
                    metadata=metadata or {},
                )
                summary[result["queryability_status"]] = summary.get(result["queryability_status"], 0) + 1
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
