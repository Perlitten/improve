#!/usr/bin/env python3
"""
memory_maintenance.py — knowledge_base management cron job.

Subcommands:
  reembed  — re-compute NVIDIA embeddings for all knowledge_base rows.
             Chunked (batch_size rows at a time), checkpoint-resumable,
             ResourceGuard-aware.
  archive  — move rows older than N days to GCS or Postgres archive table.
  score    — LLM-based importance scoring via Ralph inbox (Phase 2 / Karpathy).
             Submits batch tasks; Ralph calls the gateway to rank memories.

Usage:
  python memory_maintenance.py reembed [--batch-size 20] [--rate-limit 0.3]
  python memory_maintenance.py archive [--days 180]
  python memory_maintenance.py score   [--dry-run]

Environment (from /srv/automation/.env):
  NVIDIA_API_KEY, POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD,
  TELEGRAM_BOT_TOKEN, TELEGRAM_HOME_CHANNEL, GCS_ARCHIVE_BUCKET (optional)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from urllib import request as _urllib_request

import psycopg2
from psycopg2.extras import RealDictCursor

# Optional GCS
try:
    from google.cloud import storage as _gcs
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False

EMBED_MODEL = "nvidia/nv-embedqa-e5-v5"
EMBED_URL   = "https://integrate.api.nvidia.com/v1/embeddings"
EMBED_DIM   = 1024

CHECKPOINT_FILE = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes")) / "reembed_checkpoint.json"
LOG_FILE        = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes")) / "memory_maintenance.log"


# ── Environment ──────────────────────────────────────────────────────────────

def _load_env() -> None:
    """Load /srv/automation/.env into os.environ (idempotent)."""
    env_path = Path("/srv/automation/.env")
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


_load_env()


# ── Logging ──────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Telegram ─────────────────────────────────────────────────────────────────

def _notify(text: str) -> None:
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_HOME_CHANNEL", "")
    if not token or not chat_id:
        return
    body = json.dumps({"chat_id": chat_id, "text": text[:4096]}).encode()
    req  = _urllib_request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        _urllib_request.urlopen(req, timeout=10)
    except Exception:
        pass


# ── ResourceGuard ─────────────────────────────────────────────────────────────

def _check_resources() -> tuple[bool, str]:
    """
    Return (allowed, reason).
    Tries ResourceGuard; falls back to a simple free-RAM check.
    """
    try:
        sys.path.insert(0, "/home/Bilirubin/workspace/hermes/src")
        from resource_guard.resource_guard import collect_snapshot, assess_resources  # type: ignore
        snapshot = collect_snapshot()
        decision = assess_resources(snapshot, operation="targeted_tests")
        if not decision.allowed:
            return False, "; ".join(decision.blocked_reasons)
        return True, ""
    except ImportError:
        pass

    # Fallback: read /proc/meminfo
    try:
        meminfo = Path("/proc/meminfo").read_text()
        avail_line = next(l for l in meminfo.splitlines() if l.startswith("MemAvailable"))
        avail_kb = int(avail_line.split()[1])
        avail_mb = avail_kb // 1024
        if avail_mb < 350:
            return False, f"MemAvailable {avail_mb} MB < 350 MB threshold"
        return True, ""
    except Exception:
        return True, ""  # If we can't check, proceed


# ── Database ──────────────────────────────────────────────────────────────────

def _get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        options="-c search_path=automation,public",
        connect_timeout=15,
    )


# ── NVIDIA Embedding ──────────────────────────────────────────────────────────

def _embed(text: str) -> list[float]:
    api_key = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        _log("WARNING: NVIDIA_API_KEY not set — returning zero vector")
        return [0.0] * EMBED_DIM
    try:
        import requests as _req  # type: ignore
        resp = _req.post(
            EMBED_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": EMBED_MODEL, "input": [text[:8000]], "input_type": "passage"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except Exception as exc:
        _log(f"WARNING: embed failed ({exc}) — zero vector")
        return [0.0] * EMBED_DIM


def _is_zero_vector(v: list[float]) -> bool:
    return all(x == 0.0 for x in v[:10])


# ── Checkpoint ────────────────────────────────────────────────────────────────

def _load_checkpoint() -> dict:
    try:
        return json.loads(CHECKPOINT_FILE.read_text())
    except Exception:
        return {}


def _save_checkpoint(data: dict) -> None:
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(json.dumps(data))


def _clear_checkpoint() -> None:
    CHECKPOINT_FILE.unlink(missing_ok=True)


# ── reembed ───────────────────────────────────────────────────────────────────

def reembed_all(batch_size: int = 20, rate_limit: float = 0.3, force: bool = False) -> None:
    """
    Re-compute embeddings for all knowledge_base rows.

    Design (Karpathy-inspired batch consolidation):
    - ResourceGuard check before starting and before each batch
    - Processes `batch_size` rows at a time, commits after each batch
    - Checkpoint file records last processed id → resume safely on failure
    - Rate-limited to avoid hammering the NVIDIA API
    - Skips rows that already have a non-zero embedding (unless --force)
    - Sends Telegram notification on completion or failure
    """
    _log("=== reembed started ===")

    # 1. ResourceGuard
    allowed, reason = _check_resources()
    if not allowed:
        msg = f"❌ memory reembed BLOCKED by ResourceGuard: {reason}"
        _log(msg)
        _notify(msg)
        sys.exit(1)

    # 2. Resume from checkpoint
    cp = _load_checkpoint()
    last_id = cp.get("last_id", 0) if not force else 0
    processed = cp.get("processed", 0) if not force else 0
    skipped   = cp.get("skipped", 0) if not force else 0
    if last_id:
        _log(f"Resuming from checkpoint: last_id={last_id}, processed so far={processed}")

    conn = _get_conn()
    start_ts = time.monotonic()

    try:
        while True:
            # ResourceGuard before each batch
            allowed, reason = _check_resources()
            if not allowed:
                msg = f"⚠️ reembed paused (ResourceGuard): {reason}. Will retry next run (checkpoint saved)."
                _log(msg)
                _notify(msg)
                _save_checkpoint({"last_id": last_id, "processed": processed, "skipped": skipped,
                                   "ts": datetime.datetime.utcnow().isoformat()})
                conn.close()
                sys.exit(2)

            # Fetch next batch (cursor-based pagination by id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, coalesce(title, '') || ' ' || coalesce(content, '') AS text,
                           embedding
                    FROM knowledge_base
                    WHERE id > %s
                    ORDER BY id
                    LIMIT %s
                    """,
                    (last_id, batch_size),
                )
                batch = cur.fetchall()

            if not batch:
                break  # Done

            _log(f"Processing batch of {len(batch)} rows (id > {last_id})")

            with conn.cursor() as cur:
                for rid, text, existing_emb in batch:
                    # Skip if already has a valid embedding and not forced
                    if not force and existing_emb is not None:
                        try:
                            existing = existing_emb if isinstance(existing_emb, list) else json.loads(existing_emb)
                            if not _is_zero_vector(existing):
                                skipped += 1
                                last_id = rid
                                continue
                        except Exception:
                            pass

                    emb = _embed(text.strip()[:8000])
                    if _is_zero_vector(emb):
                        _log(f"  row {rid}: zero vector (API key missing or failed)")
                    else:
                        cur.execute(
                            "UPDATE knowledge_base SET embedding = %s::vector, updated_at = NOW() WHERE id = %s",
                            (emb, rid),
                        )
                        processed += 1

                    last_id = rid
                    time.sleep(rate_limit)  # rate-limit API calls

                conn.commit()

            # Save checkpoint after each committed batch
            _save_checkpoint({
                "last_id": last_id,
                "processed": processed,
                "skipped": skipped,
                "ts": datetime.datetime.utcnow().isoformat(),
            })

    except Exception as exc:
        conn.rollback()
        msg = f"❌ reembed failed at id={last_id}: {exc}"
        _log(msg)
        _notify(msg)
        _save_checkpoint({"last_id": last_id, "processed": processed, "skipped": skipped,
                           "error": str(exc), "ts": datetime.datetime.utcnow().isoformat()})
        conn.close()
        raise

    conn.close()
    _clear_checkpoint()

    elapsed = round(time.monotonic() - start_ts)
    msg = (
        f"✅ reembed complete: {processed} embedded, {skipped} skipped (already valid). "
        f"Elapsed: {elapsed}s."
    )
    _log(msg)
    _notify(msg)


# ── archive ───────────────────────────────────────────────────────────────────

def archive_old(days: int = 180) -> None:
    """
    Archive rows older than `days` days to GCS (if configured) or Postgres table.
    Streams rows in batches to avoid loading everything into RAM at once.
    """
    _log(f"=== archive started (days={days}) ===")

    allowed, reason = _check_resources()
    if not allowed:
        msg = f"❌ archive BLOCKED by ResourceGuard: {reason}"
        _log(msg)
        _notify(msg)
        sys.exit(1)

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    conn   = _get_conn()
    bucket = _get_gcs_bucket() if GCS_AVAILABLE else None
    total_archived = 0

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT COUNT(*) FROM knowledge_base WHERE updated_at < %s", (cutoff,)
            )
            total_old = cur.fetchone()["count"]

        if total_old == 0:
            _log(f"Nothing to archive (no rows older than {days} days).")
            conn.close()
            return

        _log(f"Found {total_old} rows to archive (older than {cutoff.date()}).")

        # Batch-stream rows to avoid RAM spikes
        BATCH = 100
        last_id = 0
        while True:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, title, content, source, category, created_at, updated_at
                    FROM knowledge_base
                    WHERE updated_at < %s AND id > %s
                    ORDER BY id
                    LIMIT %s
                    """,
                    (cutoff, last_id, BATCH),
                )
                rows = cur.fetchall()

            if not rows:
                break

            if bucket is not None:
                ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                blob_name = f"knowledge_base_archive/{ts}_{len(rows)}_records.jsonl"
                jsonl = "\n".join(
                    json.dumps({
                        **{k: (v.isoformat() if isinstance(v, datetime.datetime) else v)
                           for k, v in row.items()}
                    })
                    for row in rows
                )
                blob = bucket.blob(blob_name)
                blob.upload_from_string(jsonl, content_type="application/jsonl")
                _log(f"GCS: uploaded {len(rows)} rows to {blob_name}")
            else:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS knowledge_base_archive (
                            LIKE knowledge_base INCLUDING ALL
                        )
                        """
                    )
                    ids = [r["id"] for r in rows]
                    cur.execute(
                        "INSERT INTO knowledge_base_archive SELECT * FROM knowledge_base WHERE id = ANY(%s)",
                        (ids,),
                    )

            # Delete archived rows
            ids = [r["id"] for r in rows]
            with conn.cursor() as cur:
                cur.execute("DELETE FROM knowledge_base WHERE id = ANY(%s)", (ids,))
            conn.commit()

            total_archived += len(rows)
            last_id = rows[-1]["id"]
            _log(f"Archived batch of {len(rows)}, total so far: {total_archived}")

    except Exception as exc:
        conn.rollback()
        msg = f"❌ archive failed: {exc}"
        _log(msg)
        _notify(msg)
        conn.close()
        raise

    conn.close()
    msg = f"✅ archive complete: {total_archived} rows archived ({days}-day cutoff)."
    _log(msg)
    _notify(msg)


# ── score (Phase 2 — Ralph / Karpathy) ───────────────────────────────────────

def score_importance(dry_run: bool = False) -> None:
    """
    LLM-based memory importance scoring via Ralph (Phase 2).

    For each knowledge_base row, submits a task to Ralph:
      "Rate the importance of this memory (1-5) and reason why."
    Ralph runs it through the gateway (free NVIDIA models), returns a score.
    Low-scoring rows are flagged for archival.

    This is the true Karpathy-inspired step: selective memory consolidation
    using a language model as the judge of what's worth keeping.
    """
    _log("=== score (importance) started ===")

    allowed, reason = _check_resources()
    if not allowed:
        _log(f"BLOCKED: {reason}")
        return

    try:
        sys.path.insert(0, "/home/Bilirubin/workspace/hermes/src")
        from task_orchestrator_v2 import TaskOrchestrator  # type: ignore
        from s5.source_router import SourceRouter          # type: ignore
    except ImportError as exc:
        _log(f"Ralph not available ({exc}) — skip importance scoring")
        return

    conn = _get_conn()
    orch   = TaskOrchestrator()
    router = SourceRouter(orch)
    submitted = 0
    skipped   = 0

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, title, left(content, 400) AS excerpt FROM knowledge_base ORDER BY id"
        )
        rows = cur.fetchall()

    conn.close()

    for row in rows:
        task_text = (
            f"Memory importance evaluation task:\n\n"
            f"Title: {row['title']}\n"
            f"Excerpt: {row['excerpt']}\n\n"
            f"Rate the long-term importance of this memory on a scale 1-5 "
            f"(1=ephemeral/redundant, 5=critical/irreplaceable). "
            f"Reply with: SCORE:<n> REASON:<brief reason>. "
            f"Then suggest: KEEP or ARCHIVE."
        )
        if dry_run:
            _log(f"[dry-run] Would submit task for row id={row['id']}: {row['title'][:60]}")
            submitted += 1
            continue

        task_id = router.submit(
            task_text,
            source="memory_score",
            priority="low",
            metadata={"memory_row_id": row["id"], "task_type": "memory_importance_score"},
        )
        if task_id:
            submitted += 1
        else:
            skipped += 1
        time.sleep(0.1)  # don't flood the inbox

    msg = (
        f"{'[dry-run] ' if dry_run else ''}score: submitted {submitted} tasks to Ralph, "
        f"{skipped} duplicates skipped."
    )
    _log(msg)
    _notify(msg)


# ── GCS helper ────────────────────────────────────────────────────────────────

def _get_gcs_bucket():
    if not GCS_AVAILABLE:
        return None
    bucket_name = os.getenv("GCS_ARCHIVE_BUCKET", "")
    if not bucket_name:
        return None
    try:
        client = _gcs.Client()
        bucket = client.bucket(bucket_name)
        if not bucket.exists():
            return None
        return bucket
    except Exception:
        return None


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser(description="Hermes memory maintenance")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_reembed = sub.add_parser("reembed", help="Re-compute embeddings")
    p_reembed.add_argument("--batch-size", type=int, default=20)
    p_reembed.add_argument("--rate-limit", type=float, default=0.3,
                           help="Seconds between embedding API calls")
    p_reembed.add_argument("--force", action="store_true",
                           help="Re-embed even rows that already have valid embeddings")

    p_archive = sub.add_parser("archive", help="Archive old rows")
    p_archive.add_argument("--days", type=int, default=180)

    p_score = sub.add_parser("score", help="LLM importance scoring via Ralph")
    p_score.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.cmd == "reembed":
        reembed_all(batch_size=args.batch_size, rate_limit=args.rate_limit, force=args.force)
    elif args.cmd == "archive":
        archive_old(days=args.days)
    elif args.cmd == "score":
        score_importance(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
