import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_values


def load_rows(path: Path):
    now = datetime.now(timezone.utc)
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            rows.append(
                (
                    item["collection"],
                    item["source"],
                    item["content"],
                    Json(item.get("metadata", {})),
                    now,
                    now,
                )
            )
    return rows


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: obsidian_rag_import.py <main.ndjson> <rules.ndjson>")

    main_path = Path(sys.argv[1])
    rules_path = Path(sys.argv[2])
    main_rows = load_rows(main_path)
    rules_rows = load_rows(rules_path)

    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "rag"),
        user=os.environ.get("PGUSER", "automation"),
        password=os.environ.get("PGPASSWORD", ""),
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "delete from rag_documents where collection in ('obsidian-main','obsidian-rules')"
            )
            execute_values(
                cur,
                "insert into rag_documents (collection, source, content, metadata, created_at, updated_at) values %s",
                main_rows,
                page_size=200,
            )
            execute_values(
                cur,
                "insert into rag_documents (collection, source, content, metadata, created_at, updated_at) values %s",
                rules_rows,
                page_size=200,
            )
            cur.execute(
                """
                select collection, count(*)
                from rag_documents
                where collection in ('obsidian-main','obsidian-rules')
                group by collection
                order by collection
                """
            )
            counts = cur.fetchall()

    print(
        json.dumps(
            {
                "inserted_main": len(main_rows),
                "inserted_rules": len(rules_rows),
                "counts": counts,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
