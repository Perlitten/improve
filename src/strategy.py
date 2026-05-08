#!/usr/bin/env python3
"""
strategy.py — Learning strategy database CLI for Hermes Agent.

The agent uses this to:
  1. Look up known solutions before attempting anything new  (find)
  2. Record what worked and what didn't                      (record)
  3. Add newly discovered solutions                          (add)
  4. Evolve: promote winners, disable losers                 (evolve)
  5. Curate: merge duplicates, purge contradictions          (curate)
  6. Reflect: pack a completed task into a reusable strategy (reflect)
  7. Stats and listing                                       (stats / list)

Problem type conventions:
  nvidia_embedding_api   embedding endpoint / model failures
  nvidia_llm_tools       LLM refuses parallel tool calls
  provider_402           out of credits
  provider_429           rate-limited
  provider_stream_hang   streaming hangs > 90s
  db_vector_type         pgvector type not found (wrong schema/db)
  db_vector_dim          vector column has wrong dimension
  service_down           systemd service inactive

Action JSON schema (flexible — anything Hermes can execute):
  {"type": "use_model",        "model": "...", "endpoint": "...", "dim": N}
  {"type": "switch_model",     "model": "...", "provider": "openrouter|nvidia"}
  {"type": "run_script",       "script": "...", "args": [...]}
  {"type": "exec_sql",         "sql": "..."}
  {"type": "restart_service",  "service": "..."}
  {"type": "custom",           "steps": ["step1 description", ...]}
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor


# ── DB helpers ────────────────────────────────────────────────────────────────

def load_env():
    for path in ["/srv/automation/.env", "/home/Bilirubin/.hermes/.env"]:
        if not os.path.exists(path):
            continue
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip("\"'"))


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        options="-c search_path=automation,public",
    )


class EmbeddingUnavailable(RuntimeError):
    """Raised when the embedding API is unreachable or unconfigured.

    Callers must NOT fall back to zero vectors — zero vectors corrupt the HNSW index.
    Either skip the embed-dependent operation or propagate this exception.
    """


_EMBED_MODEL = "nvidia/nv-embedqa-e5-v5"
_EMBED_MODEL_VERSION = "1"


def _embed(text: str) -> list[float]:
    """Generate 1024-dim embedding via NVIDIA API.

    Raises EmbeddingUnavailable instead of returning zero vectors to prevent
    HNSW index poisoning.
    """
    key = os.getenv("NVIDIA_API_KEY")
    if not key:
        raise EmbeddingUnavailable("NVIDIA_API_KEY not set — cannot generate embedding")
    try:
        import requests
        r = requests.post(
            "https://integrate.api.nvidia.com/v1/embeddings",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": _EMBED_MODEL, "input": [text], "input_type": "passage"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception as exc:
        raise EmbeddingUnavailable(f"embedding API failed: {exc}") from exc


def _save_to_kb(title, content, source="strategy_system", category="meta"):
    """Persist a learning event to knowledge_base for semantic recall."""
    try:
        emb = _embed(f"{title}\n{content}")
    except EmbeddingUnavailable:
        return  # skip rather than poison the index with zero vectors
    conn = get_conn()
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO knowledge_base (title, content, embedding, source, category)"
            " VALUES (%s, %s, %s::vector, %s, %s)",
            (title, content, emb, source, category),
        )
        conn.commit()
    conn.close()


# ── find ──────────────────────────────────────────────────────────────────────

def cmd_find(args):
    """Return enabled strategies for a problem type, best-first."""
    conn = get_conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, name, description, action, priority,
                   success_count, failure_count,
                   CASE WHEN (success_count + failure_count) > 0
                        THEN round(success_count::numeric
                                   / (success_count + failure_count) * 100, 1)
                        ELSE NULL END AS success_rate
            FROM strategies
            WHERE problem_type = %s AND enabled = TRUE
            ORDER BY
                -- untried first (give every strategy at least one chance)
                CASE WHEN success_count + failure_count = 0 THEN 0 ELSE 1 END,
                priority ASC,
                success_count DESC,
                failure_count ASC
            """,
            (args.problem_type,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    if not rows:
        out = {
            "ok": False,
            "strategies": [],
            "hint": (
                f"No strategies for '{args.problem_type}'. "
                f"Discover with probe_api.py then add with: "
                f"strategy.py add {args.problem_type} <name> '<action_json>'"
            ),
        }
        print(json.dumps(out)); sys.exit(1)
    print(json.dumps({"ok": True, "count": len(rows), "strategies": rows}, default=str))


# ── record ────────────────────────────────────────────────────────────────────

def cmd_record(args):
    """Record the outcome of a strategy attempt."""
    conn = get_conn()
    now = datetime.now(timezone.utc)
    context = json.loads(args.context) if args.context else None
    result  = json.loads(args.result)  if args.result  else None

    with conn.cursor() as cur:
        cur.execute("SELECT problem_type, name FROM strategies WHERE id = %s",
                    (args.strategy_id,))
        row = cur.fetchone()
        if not row:
            print(json.dumps({"ok": False,
                               "error": f"Strategy {args.strategy_id} not found"}))
            sys.exit(1)
        problem_type, name = row

        cur.execute(
            """INSERT INTO strategy_attempts
               (strategy_id, problem_type, context, outcome, result, error_msg, duration_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (args.strategy_id, problem_type,
             json.dumps(context) if context else None,
             args.outcome,
             json.dumps(result) if result else None,
             args.error, args.ms),
        )
        if args.outcome == "success":
            cur.execute(
                "UPDATE strategies SET success_count=success_count+1,"
                " last_success=%s, updated_at=%s WHERE id=%s",
                (now, now, args.strategy_id),
            )
        elif args.outcome == "failure":
            cur.execute(
                "UPDATE strategies SET failure_count=failure_count+1,"
                " last_failure=%s, updated_at=%s WHERE id=%s",
                (now, now, args.strategy_id),
            )
        conn.commit()
    conn.close()
    print(json.dumps({"ok": True, "strategy_id": args.strategy_id,
                      "outcome": args.outcome, "problem_type": problem_type,
                      "strategy_name": name}))


# ── add ───────────────────────────────────────────────────────────────────────

def cmd_add(args):
    """Add or upsert a strategy."""
    try:
        action = json.loads(args.action_json)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"Invalid JSON: {e}"})); sys.exit(1)

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO strategies (problem_type, name, description, action, priority)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (problem_type, name) DO UPDATE
               SET action      = EXCLUDED.action,
                   description = COALESCE(EXCLUDED.description, strategies.description),
                   priority    = EXCLUDED.priority,
                   enabled     = TRUE,
                   updated_at  = NOW()
            RETURNING id
            """,
            (args.problem_type, args.name,
             getattr(args, "desc", None),
             json.dumps(action),
             getattr(args, "priority", 100)),
        )
        sid = cur.fetchone()[0]
        conn.commit()
    conn.close()
    print(json.dumps({"ok": True, "id": sid,
                      "problem_type": args.problem_type, "name": args.name}))


# ── disable ───────────────────────────────────────────────────────────────────

def cmd_disable(args):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE strategies SET enabled=FALSE, updated_at=NOW()"
            " WHERE id=%s RETURNING name, problem_type",
            (args.strategy_id,),
        )
        row = cur.fetchone()
        conn.commit()
    conn.close()
    if not row:
        print(json.dumps({"ok": False, "error": "Not found"})); sys.exit(1)
    print(json.dumps({"ok": True,
                      "disabled": {"id": args.strategy_id,
                                   "name": row[0], "problem_type": row[1]}}))


# ── evolve ────────────────────────────────────────────────────────────────────

def cmd_evolve(args):
    """
    Automatic strategy evolution:
    - Disable strategies with success_rate < 15% and failure_count >= 5
    - Promote strategies with success_rate > 85% (lower priority by 10)
    - Write evolution report to knowledge_base
    """
    dry = getattr(args, "dry_run", False)
    conn = get_conn()
    disabled = []
    promoted = []

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, problem_type, name, priority,
                   success_count, failure_count,
                   CASE WHEN (success_count + failure_count) >= 5
                        THEN round(success_count::numeric
                                   / (success_count + failure_count) * 100, 1)
                        ELSE NULL END AS success_rate
            FROM strategies
            WHERE enabled = TRUE AND (success_count + failure_count) >= 5
            """
        )
        rows = cur.fetchall()
        now = datetime.now(timezone.utc)

        for r in rows:
            sr = r["success_rate"]
            if sr is None:
                continue
            if sr < 15.0 and r["failure_count"] >= 5:
                if not dry:
                    cur.execute(
                        "UPDATE strategies SET enabled=FALSE, updated_at=%s WHERE id=%s",
                        (now, r["id"]),
                    )
                disabled.append({"id": r["id"], "name": r["name"],
                                  "problem_type": r["problem_type"],
                                  "success_rate": float(sr)})
            elif sr > 85.0 and r["priority"] > 10:
                new_p = max(10, r["priority"] - 10)
                if not dry:
                    cur.execute(
                        "UPDATE strategies SET priority=%s, updated_at=%s WHERE id=%s",
                        (new_p, now, r["id"]),
                    )
                promoted.append({"id": r["id"], "name": r["name"],
                                  "problem_type": r["problem_type"],
                                  "old_priority": r["priority"],
                                  "new_priority": new_p,
                                  "success_rate": float(sr)})

        if not dry:
            conn.commit()
    conn.close()

    result = {
        "ok": True, "dry_run": dry,
        "disabled": disabled, "promoted": promoted,
        "summary": f"Disabled {len(disabled)}, promoted {len(promoted)} strategies",
    }
    print(json.dumps(result, default=str))

    if not dry and (disabled or promoted):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        content = (
            f"Strategy evolution {today}. "
            f"Disabled (success_rate<15%): "
            f"{[d['name'] for d in disabled] or 'none'}. "
            f"Promoted (success_rate>85%): "
            f"{[p['name']+' priority→'+str(p['new_priority']) for p in promoted] or 'none'}."
        )
        try:
            _save_to_kb(f"Strategy evolution {today}", content,
                        "strategy_evolve", "meta")
        except Exception:
            pass


# ── curate ────────────────────────────────────────────────────────────────────

def cmd_curate(args):
    """
    Cognitive hygiene: find redundant/contradictory strategies and report them.
    Does NOT auto-delete — prints a JSON report for the agent to review.
    The agent should then disable duplicates or merge actions manually.
    """
    conn = get_conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Find problem types with many disabled strategies (sign of churn)
        cur.execute(
            """
            SELECT problem_type,
                   count(*) FILTER (WHERE enabled)  AS active,
                   count(*) FILTER (WHERE NOT enabled) AS disabled_count,
                   sum(success_count) AS total_successes,
                   sum(failure_count) AS total_failures
            FROM strategies
            GROUP BY problem_type
            ORDER BY disabled_count DESC, total_failures DESC
            """
        )
        by_type = [dict(r) for r in cur.fetchall()]

        # Strategies with 0 attempts (never tried) and old creation date
        cur.execute(
            """
            SELECT id, problem_type, name, priority, created_at
            FROM strategies
            WHERE enabled = TRUE
              AND success_count = 0 AND failure_count = 0
              AND created_at < NOW() - INTERVAL '14 days'
            ORDER BY created_at
            """
        )
        stale_untried = [dict(r) for r in cur.fetchall()]
    conn.close()

    report = {
        "ok": True,
        "by_problem_type": by_type,
        "stale_untried": stale_untried,
        "recommendation": (
            "Review stale_untried strategies — if still relevant, try them. "
            "If not, disable with: strategy.py disable <id>. "
            "For problem types with many disabled strategies, consider whether "
            "the remaining active strategies cover all cases."
        ),
    }
    print(json.dumps(report, default=str))


# ── reflect ───────────────────────────────────────────────────────────────────

def cmd_reflect(args):
    """
    Pack a just-completed task into a reusable strategy.
    Call this AFTER successfully solving a problem.
    This is how the system grows: each solved problem seeds new strategies.
    """
    try:
        action = json.loads(args.action_json)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"Invalid JSON: {e}"})); sys.exit(1)

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO strategies (problem_type, name, description, action, priority,
                                    success_count, last_success)
            VALUES (%s, %s, %s, %s, %s, 1, NOW())
            ON CONFLICT (problem_type, name) DO UPDATE
               SET action        = EXCLUDED.action,
                   description   = COALESCE(EXCLUDED.description, strategies.description),
                   success_count = strategies.success_count + 1,
                   last_success  = NOW(),
                   enabled       = TRUE,
                   updated_at    = NOW()
            RETURNING id
            """,
            (args.problem_type, args.name,
             getattr(args, "desc", None),
             json.dumps(action),
             getattr(args, "priority", 50)),   # reflect starts at priority 50 (higher trust)
        )
        sid = cur.fetchone()[0]
        conn.commit()
    conn.close()

    # Also save to knowledge_base for semantic search
    content = (
        f"Problem type: {args.problem_type}. "
        f"Strategy: {args.name}. "
        f"Description: {getattr(args, 'desc', 'N/A')}. "
        f"Action: {json.dumps(action)}."
    )
    try:
        _save_to_kb(
            f"Solved: {args.problem_type} via {args.name}",
            content, "strategy_reflect", "infra",
        )
    except Exception:
        pass

    print(json.dumps({"ok": True, "id": sid,
                      "problem_type": args.problem_type, "name": args.name,
                      "note": "Strategy seeded with 1 success. "
                              "Will be promoted automatically after more successes."}))


# ── stats ─────────────────────────────────────────────────────────────────────

def cmd_stats(args):
    conn = get_conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        where = "WHERE s.problem_type = %s" if getattr(args, "problem_type", None) else ""
        params = [args.problem_type] if getattr(args, "problem_type", None) else []
        cur.execute(
            f"""
            SELECT s.problem_type,
                   count(*)                                   AS total,
                   count(*) FILTER (WHERE s.enabled)          AS enabled,
                   sum(s.success_count)                       AS successes,
                   sum(s.failure_count)                       AS failures,
                   round(sum(s.success_count)::numeric /
                         NULLIF(sum(s.success_count + s.failure_count), 0) * 100, 1
                   )                                          AS success_rate
            FROM strategies s
            {where}
            GROUP BY s.problem_type
            ORDER BY s.problem_type
            """,
            params,
        )
        by_type = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT count(*) AS n FROM strategy_attempts WHERE outcome='success'")
        ok = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM strategy_attempts WHERE outcome='failure'")
        fail = cur.fetchone()["n"]
    conn.close()
    print(json.dumps({"total_attempts": ok + fail, "total_successes": ok,
                      "total_failures": fail, "by_problem_type": by_type}, default=str))


# ── list ──────────────────────────────────────────────────────────────────────

def cmd_list(args):
    conn = get_conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        where = "WHERE problem_type = %s" if getattr(args, "problem_type", None) else ""
        params = [args.problem_type] if getattr(args, "problem_type", None) else []
        cur.execute(
            f"""
            SELECT id, problem_type, name, description, priority, enabled,
                   success_count, failure_count,
                   CASE WHEN (success_count + failure_count) > 0
                        THEN round(success_count::numeric
                                   / (success_count + failure_count) * 100, 1)
                        ELSE NULL END AS success_rate,
                   action
            FROM strategies
            {where}
            ORDER BY problem_type, priority, id
            """,
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    print(json.dumps({"count": len(rows), "strategies": rows}, default=str))


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    load_env()
    p = argparse.ArgumentParser(description="Hermes strategy learning DB")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("find", help="List strategies to try for a problem type")
    s.add_argument("problem_type")
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("record", help="Record outcome of an attempt")
    s.add_argument("strategy_id", type=int)
    s.add_argument("outcome", choices=["success", "failure", "partial"])
    s.add_argument("--error",   default=None)
    s.add_argument("--result",  default=None)
    s.add_argument("--context", default=None)
    s.add_argument("--ms",      type=int, default=None)
    s.set_defaults(func=cmd_record)

    s = sub.add_parser("add", help="Add or update a strategy")
    s.add_argument("problem_type")
    s.add_argument("name")
    s.add_argument("action_json")
    s.add_argument("--desc",     default=None)
    s.add_argument("--priority", type=int, default=100)
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("disable", help="Blacklist a strategy permanently")
    s.add_argument("strategy_id", type=int)
    s.set_defaults(func=cmd_disable)

    s = sub.add_parser("evolve",
                       help="Promote winners, disable losers, write report")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_evolve)

    s = sub.add_parser("curate",
                       help="Cognitive hygiene: find redundant/stale strategies")
    s.set_defaults(func=cmd_curate)

    s = sub.add_parser("reflect",
                       help="Pack a just-solved problem into a reusable strategy")
    s.add_argument("problem_type")
    s.add_argument("name")
    s.add_argument("action_json")
    s.add_argument("--desc",     default=None)
    s.add_argument("--priority", type=int, default=50)
    s.set_defaults(func=cmd_reflect)

    s = sub.add_parser("stats", help="Learning summary")
    s.add_argument("problem_type", nargs="?", default=None)
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("list", help="List all strategies with stats")
    s.add_argument("problem_type", nargs="?", default=None)
    s.set_defaults(func=cmd_list)

    args = p.parse_args()
    if not args.cmd:
        p.print_help(); sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
