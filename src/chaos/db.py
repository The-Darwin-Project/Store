# Store/src/chaos/db.py
"""PostgreSQL persistence for chaos controller test reports.

Implements a strict FIFO journal: only reports from the 7 most recent
deployment runs are kept. A deployment run is identified by git_sha;
reports without a git_sha are treated as standalone runs.
Falls back to in-memory storage when the database is unavailable.
"""

import os
import json
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional, List

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

logger = logging.getLogger(__name__)

MAX_REPORTS = 7

# Database configuration
DB_HOST = os.getenv("DB_HOST", "darwin-store-postgres-svc")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "darwin")
DB_NAME = os.getenv("DB_NAME", "postgres")

# Connection pool (initialized on startup)
db_pool: Optional[SimpleConnectionPool] = None

# In-memory fallback (used when DB is unavailable)
_fallback_reports: list = []
_using_fallback = False


def init_db() -> bool:
    """Initialize DB pool and create test_reports table. Returns True on success."""
    global db_pool, _using_fallback

    dsn = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    max_retries = 5
    retry_delay = 2

    for attempt in range(1, max_retries + 1):
        try:
            db_pool = SimpleConnectionPool(1, 5, dsn=dsn)
            logger.info(f"Chaos DB pool established (attempt {attempt})")
            break
        except psycopg2.OperationalError as e:
            if attempt < max_retries:
                logger.warning(f"Chaos DB attempt {attempt}/{max_retries} failed: {e}. Retrying...")
                import time
                time.sleep(retry_delay)
            else:
                logger.error(f"Chaos DB connection failed after {max_retries} attempts: {e}")
                _using_fallback = True
                return False

    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS test_reports (
                    id VARCHAR(12) PRIMARY KEY,
                    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    suite VARCHAR(100) NOT NULL DEFAULT 'post-deploy',
                    total INTEGER NOT NULL DEFAULT 0,
                    passed INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    skipped INTEGER NOT NULL DEFAULT 0,
                    duration_ms REAL NOT NULL DEFAULT 0,
                    tests JSONB NOT NULL DEFAULT '[]',
                    git_sha VARCHAR(255),
                    image_tag VARCHAR(255)
                )
            ''')
        conn.commit()
        logger.info("test_reports table ready")
        _using_fallback = False
        return True
    except Exception as e:
        logger.error(f"Failed to create test_reports table: {e}")
        _using_fallback = True
        return False
    finally:
        if conn and db_pool:
            db_pool.putconn(conn)


def close_db():
    """Close DB pool on shutdown."""
    global db_pool
    if db_pool:
        db_pool.closeall()
        logger.info("Chaos DB pool closed")


def insert_report(report_dict: dict) -> dict:
    """Insert a report and enforce FIFO (keep only MAX_REPORTS most recent).

    Returns the stored report dict.
    """
    global _using_fallback

    if _using_fallback or db_pool is None:
        _fallback_reports.insert(0, report_dict)
        _trim_fallback()
        return report_dict

    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute(
                '''INSERT INTO test_reports
                   (id, received_at, suite, total, passed, failed, skipped,
                    duration_ms, tests, git_sha, image_tag)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (
                    report_dict["id"],
                    report_dict["received_at"],
                    report_dict["suite"],
                    report_dict["total"],
                    report_dict["passed"],
                    report_dict["failed"],
                    report_dict["skipped"],
                    report_dict["duration_ms"],
                    json.dumps([t if isinstance(t, dict) else t for t in report_dict.get("tests", [])]),
                    report_dict.get("git_sha"),
                    report_dict.get("image_tag"),
                )
            )
            # FIFO enforcement: keep only reports from the last MAX_REPORTS deployment runs
            cur.execute(
                '''DELETE FROM test_reports
                   WHERE COALESCE(git_sha, id) NOT IN (
                       SELECT run_key FROM (
                           SELECT COALESCE(git_sha, id) AS run_key,
                                  MAX(received_at) AS latest_at
                           FROM test_reports
                           GROUP BY COALESCE(git_sha, id)
                           ORDER BY latest_at DESC
                           LIMIT %s
                       ) latest_runs
                   )''',
                (MAX_REPORTS,)
            )
        conn.commit()
        return report_dict
    except Exception as e:
        logger.error(f"DB insert failed, using fallback: {e}")
        if conn:
            conn.rollback()
        _using_fallback = True
        _fallback_reports.insert(0, report_dict)
        _trim_fallback()
        return report_dict
    finally:
        if conn and db_pool:
            db_pool.putconn(conn)


def list_reports() -> list:
    """Return all reports from the last MAX_REPORTS deployment runs (newest first)."""
    global _using_fallback

    if _using_fallback or db_pool is None:
        return list(_fallback_reports)

    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                '''SELECT id, received_at, suite, total, passed, failed,
                          skipped, duration_ms, tests, git_sha, image_tag
                   FROM test_reports
                   WHERE COALESCE(git_sha, id) IN (
                       SELECT run_key FROM (
                           SELECT COALESCE(git_sha, id) AS run_key,
                                  MAX(received_at) AS latest_at
                           FROM test_reports
                           GROUP BY COALESCE(git_sha, id)
                           ORDER BY latest_at DESC
                           LIMIT %s
                       ) latest_runs
                   )
                   ORDER BY received_at DESC, suite''',
                (MAX_REPORTS,)
            )
            rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f"DB list failed, using fallback: {e}")
        _using_fallback = True
        return list(_fallback_reports)
    finally:
        if conn and db_pool:
            db_pool.putconn(conn)


def get_latest_report() -> Optional[dict]:
    """Return the most recent report, or None."""
    global _using_fallback

    if _using_fallback or db_pool is None:
        return _fallback_reports[0] if _fallback_reports else None

    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                '''SELECT id, received_at, suite, total, passed, failed,
                          skipped, duration_ms, tests, git_sha, image_tag
                   FROM test_reports
                   ORDER BY received_at DESC
                   LIMIT 1'''
            )
            row = cur.fetchone()
        return _row_to_dict(row) if row else None
    except Exception as e:
        logger.error(f"DB latest failed, using fallback: {e}")
        _using_fallback = True
        return _fallback_reports[0] if _fallback_reports else None
    finally:
        if conn and db_pool:
            db_pool.putconn(conn)


def _row_to_dict(row: dict) -> dict:
    """Convert a DB row to the API response format."""
    return {
        "id": row["id"],
        "received_at": row["received_at"].isoformat() if hasattr(row["received_at"], "isoformat") else str(row["received_at"]),
        "suite": row["suite"],
        "total": row["total"],
        "passed": row["passed"],
        "failed": row["failed"],
        "skipped": row["skipped"],
        "duration_ms": row["duration_ms"],
        "tests": row["tests"] if isinstance(row["tests"], list) else json.loads(row["tests"]) if row["tests"] else [],
        "git_sha": row.get("git_sha"),
        "image_tag": row.get("image_tag"),
    }


def _trim_fallback():
    """Trim fallback storage to keep only reports from the last MAX_REPORTS deployment runs."""
    global _fallback_reports
    if not _fallback_reports:
        return
    seen_keys: list = []
    for r in _fallback_reports:
        key = r.get("git_sha") or r.get("id")
        if key not in seen_keys:
            seen_keys.append(key)
    if len(seen_keys) > MAX_REPORTS:
        keep = set(seen_keys[:MAX_REPORTS])
        _fallback_reports = [r for r in _fallback_reports if (r.get("git_sha") or r.get("id")) in keep]
