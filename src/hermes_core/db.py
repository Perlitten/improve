"""Shared PostgreSQL connection pool for all hermes/src services.

Usage:
    from hermes_core.db import get_conn, put_conn

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(...)
        conn.commit()
    finally:
        put_conn(conn)

Or use the context manager:
    with db_conn() as conn:
        ...

The pool is lazy-initialised on first use and reuses credentials from
/srv/automation/.env (POSTGRES_USER, POSTGRES_PASSWORD).
"""
import contextlib
import os
import threading
from pathlib import Path

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

_ENV_PATH = Path("/srv/automation/.env")
_MIN_CONN = 2
_MAX_CONN = 20


def _load_pg_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("\"'")
    env.setdefault("POSTGRES_USER", os.getenv("POSTGRES_USER", ""))
    env.setdefault("POSTGRES_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
    return env


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        pg = _load_pg_env()
        _pool = ThreadedConnectionPool(
            _MIN_CONN,
            _MAX_CONN,
            host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB", "rag"),
            user=pg["POSTGRES_USER"],
            password=pg["POSTGRES_PASSWORD"],
        )
    return _pool


def get_conn() -> psycopg2.extensions.connection:
    """Borrow a connection from the pool. Must be returned with put_conn()."""
    return _get_pool().getconn()


def put_conn(conn: psycopg2.extensions.connection, close: bool = False) -> None:
    """Return a connection to the pool."""
    _get_pool().putconn(conn, close=close)


@contextlib.contextmanager
def db_conn():
    """Context manager that borrows and auto-returns a pool connection."""
    conn = get_conn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


def close_pool() -> None:
    """Close all connections in the pool. Call at process exit."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None
