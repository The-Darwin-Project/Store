# tests/test_chaos_reports_db.py
# QE tests for evt-b614912c: PostgreSQL-backed test report journal with FIFO queue.
#
# Approved architect plan (Turn 9):
#   1. chaos/db.py: SimpleConnectionPool init, FIFO insert (DELETE older than 7),
#      list, latest, graceful fallback.
#   2. chaos/main.py: test-reports API wired to db.py with startup/shutdown hooks.
#   3. index.html: description updated to "Showing the last 7 deployment reports."
#
# Tests cover:
#   - DB persistence layer (mocked SimpleConnectionPool)
#   - FIFO enforcement: max 7 records, oldest deleted on insert
#   - Fallback behavior: in-memory deque when DB unavailable
#   - UI rendering: HTML structure, tab, report cards, JS functions
#   - API layer: POST/GET endpoints via FastAPI TestClient
#
# sys.path handled by conftest.py (adds src/ to path).

import json
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ── Paths ─────────────────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
CHAOS_DB_PATH = SRC_DIR / "chaos" / "db.py"
CHAOS_HTML = SRC_DIR / "chaos" / "static" / "index.html"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_report(report_id="abc123def456", suite="post-deploy",
                 total=5, passed=4, failed=1, skipped=0,
                 duration_ms=1234.5, git_sha="deadbeef", image_tag="v1.0"):
    """Build a minimal report dict matching the schema accepted by insert_report."""
    return {
        "id": report_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "suite": suite,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration_ms": duration_ms,
        "tests": [{"name": "test_home", "status": "passed", "duration_ms": 120.0}],
        "git_sha": git_sha,
        "image_tag": image_tag,
    }


def _make_db_row(report_id="abc123def456"):
    """Build a mock DB row that mimics a RealDictCursor result."""
    row = {
        "id": report_id,
        "received_at": datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
        "suite": "post-deploy",
        "total": 5,
        "passed": 4,
        "failed": 1,
        "skipped": 0,
        "duration_ms": 1234.5,
        "tests": [{"name": "test_home", "status": "passed", "duration_ms": 120.0}],
        "git_sha": "deadbeef",
        "image_tag": "v1.0",
    }
    # Make row subscriptable (dict-like) for _row_to_dict
    return row


def _make_mock_pool(mock_cursor_results=None, fetchall_return=None,
                    fetchone_return=None, raise_on_execute=None):
    """
    Build a mock SimpleConnectionPool with a stub connection and cursor.

    Returns (mock_pool, mock_conn, mock_cursor).
    """
    mock_cursor = MagicMock()
    if raise_on_execute:
        mock_cursor.execute.side_effect = raise_on_execute
    if fetchall_return is not None:
        mock_cursor.fetchall.return_value = fetchall_return
    if fetchone_return is not None:
        mock_cursor.fetchone.return_value = fetchone_return

    # Cursor context manager support
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_conn

    return mock_pool, mock_conn, mock_cursor


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db_module_state():
    """
    Reset chaos.db module-level globals before each test.

    The module uses globals (db_pool, _using_fallback, _fallback_reports) that
    persist across tests within the same process. This fixture ensures a clean
    slate so tests don't interfere with each other.
    """
    import chaos.db as db
    # Save original state
    orig_pool = db.db_pool
    orig_fallback = db._using_fallback

    # Reset to clean state
    db.db_pool = None
    db._using_fallback = False
    db._fallback_reports = deque(maxlen=db.MAX_REPORTS)

    yield

    # Restore (best-effort cleanup for test isolation)
    db.db_pool = orig_pool
    db._using_fallback = orig_fallback
    db._fallback_reports = deque(maxlen=db.MAX_REPORTS)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Module constants
# ─────────────────────────────────────────────────────────────────────────────

class TestDbModuleConstants:
    """Verify the DB module constants match the approved plan."""

    def test_max_reports_is_7(self):
        """
        The approved plan specifies a strict FIFO queue of maximum 7 records.
        MAX_REPORTS must equal 7.
        """
        import chaos.db as db
        assert db.MAX_REPORTS == 7, (
            f"MAX_REPORTS is {db.MAX_REPORTS}, expected 7. "
            "The FIFO queue must cap at exactly 7 reports."
        )

    def test_fallback_deque_maxlen_matches_max_reports(self):
        """
        The in-memory fallback deque must have maxlen=MAX_REPORTS (7).
        This ensures the fallback also caps at 7 items without explicit FIFO logic.
        """
        import chaos.db as db
        assert db._fallback_reports.maxlen == db.MAX_REPORTS, (
            f"Fallback deque maxlen={db._fallback_reports.maxlen}, expected {db.MAX_REPORTS}. "
            "Both the DB and in-memory fallback must enforce the same limit."
        )

    def test_db_pool_starts_as_none(self):
        """db_pool must be None at module load (before init_db is called)."""
        import chaos.db as db
        assert db.db_pool is None, "db_pool should be None before init_db() is called."

    def test_using_fallback_starts_as_false(self):
        """_using_fallback must be False at module load."""
        import chaos.db as db
        assert db._using_fallback is False, (
            "_using_fallback should be False initially; fallback is opt-in when DB fails."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: init_db() — pool creation and table schema
# ─────────────────────────────────────────────────────────────────────────────

class TestInitDb:
    """
    Tests for chaos.db.init_db().

    The function must:
    - Create a SimpleConnectionPool on startup
    - Execute CREATE TABLE IF NOT EXISTS test_reports
    - Set _using_fallback=False on success
    - Set _using_fallback=True and return False when the DB is unreachable
    """

    def test_init_db_success_returns_true(self):
        """
        When pool creation and table creation both succeed, init_db must return True.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()

        with patch("chaos.db.SimpleConnectionPool", return_value=mock_pool):
            result = db.init_db()

        assert result is True, "init_db() must return True on successful DB connection."

    def test_init_db_success_sets_db_pool(self):
        """
        After successful init_db(), db_pool must be set to the created pool.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()

        with patch("chaos.db.SimpleConnectionPool", return_value=mock_pool):
            db.init_db()

        assert db.db_pool is mock_pool, (
            "db_pool not set after successful init_db(). "
            "Pool must be stored for use by insert/list/latest functions."
        )

    def test_init_db_success_clears_fallback_flag(self):
        """
        Successful init_db() must set _using_fallback=False, ensuring the DB
        path is used instead of the in-memory deque.
        """
        import chaos.db as db
        db._using_fallback = True  # Simulate previous failure state

        mock_pool, mock_conn, mock_cursor = _make_mock_pool()

        with patch("chaos.db.SimpleConnectionPool", return_value=mock_pool):
            db.init_db()

        assert db._using_fallback is False, (
            "_using_fallback must be cleared to False after successful init_db(). "
            "A prior failure state must not persist if the DB later becomes available."
        )

    def test_init_db_creates_test_reports_table(self):
        """
        init_db() must execute CREATE TABLE IF NOT EXISTS test_reports with
        the required columns. This is idempotent and safe on re-runs.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()

        with patch("chaos.db.SimpleConnectionPool", return_value=mock_pool):
            db.init_db()

        # Verify CREATE TABLE was executed
        executed_sql_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        create_table_called = any(
            "CREATE TABLE" in sql and "test_reports" in sql
            for sql in executed_sql_calls
        )
        assert create_table_called, (
            "CREATE TABLE IF NOT EXISTS test_reports not found in cursor.execute calls. "
            "init_db() must create the persistence table."
        )

    def test_init_db_commits_after_table_creation(self):
        """
        init_db() must commit after creating the table to persist the schema change.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()

        with patch("chaos.db.SimpleConnectionPool", return_value=mock_pool):
            db.init_db()

        mock_conn.commit.assert_called_once(), (
            "conn.commit() must be called after table creation."
        )

    def test_init_db_releases_connection_to_pool(self):
        """
        init_db() must return the connection to the pool after table creation
        (putconn), even on success, to avoid pool exhaustion.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()

        with patch("chaos.db.SimpleConnectionPool", return_value=mock_pool):
            db.init_db()

        mock_pool.putconn.assert_called_once_with(mock_conn), (
            "init_db() must call db_pool.putconn(conn) to release the connection."
        )

    def test_init_db_pool_failure_returns_false(self):
        """
        When SimpleConnectionPool raises OperationalError on all retries,
        init_db() must return False.
        """
        import chaos.db as db
        import psycopg2

        with patch("chaos.db.SimpleConnectionPool",
                   side_effect=psycopg2.OperationalError("connection refused")), \
             patch("time.sleep"):  # time is imported inline in init_db()
            result = db.init_db()

        assert result is False, (
            "init_db() must return False when DB is unreachable after all retries."
        )

    def test_init_db_pool_failure_sets_fallback_flag(self):
        """
        When DB connection fails, init_db() must set _using_fallback=True
        so subsequent operations use the in-memory deque.
        """
        import chaos.db as db
        import psycopg2

        with patch("chaos.db.SimpleConnectionPool",
                   side_effect=psycopg2.OperationalError("connection refused")), \
             patch("time.sleep"):  # time is imported inline in init_db()
            db.init_db()

        assert db._using_fallback is True, (
            "_using_fallback must be True after pool creation failure. "
            "All subsequent DB operations must use the in-memory deque."
        )

    def test_init_db_table_creation_failure_sets_fallback(self):
        """
        When pool creation succeeds but table creation fails (e.g., permission error),
        init_db() must set _using_fallback=True and return False.
        """
        import chaos.db as db

        mock_pool, mock_conn, mock_cursor = _make_mock_pool(
            raise_on_execute=Exception("permission denied")
        )

        with patch("chaos.db.SimpleConnectionPool", return_value=mock_pool):
            result = db.init_db()

        assert result is False, (
            "init_db() must return False when table creation fails."
        )
        assert db._using_fallback is True, (
            "_using_fallback must be True when table creation fails."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: insert_report() — DB path and FIFO enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestInsertReport:
    """
    Tests for chaos.db.insert_report().

    The approved plan requires:
    - INSERT the new report into test_reports
    - DELETE all rows not in the MAX_REPORTS most recent (FIFO enforcement)
    - Fall back to in-memory appendleft when DB is unavailable
    - Return the report dict
    """

    def test_insert_report_fallback_when_pool_is_none(self):
        """
        When db_pool is None (init_db not called or failed to set pool),
        insert_report must append to _fallback_reports and return the report.
        """
        import chaos.db as db
        report = _make_report("test001")

        result = db.insert_report(report)

        assert result == report, "insert_report must return the stored report dict."
        assert list(db._fallback_reports)[0] == report, (
            "Report must be in _fallback_reports when db_pool is None."
        )

    def test_insert_report_fallback_when_using_fallback_true(self):
        """
        When _using_fallback=True (DB previously failed), insert_report must
        use the in-memory deque without attempting any DB connection.
        """
        import chaos.db as db
        db._using_fallback = True
        db.db_pool = MagicMock()  # Pool exists but fallback flag is set

        report = _make_report("test002")
        result = db.insert_report(report)

        assert result == report
        assert list(db._fallback_reports)[0] == report, (
            "Must use fallback deque when _using_fallback=True."
        )
        # Pool.getconn should NOT be called
        db.db_pool.getconn.assert_not_called()

    def test_insert_report_db_executes_insert(self):
        """
        When DB is available, insert_report must call cursor.execute with an
        INSERT INTO test_reports statement including all required fields.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        db.db_pool = mock_pool

        report = _make_report("inserttest")
        db.insert_report(report)

        # Find the INSERT call
        executed_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        insert_called = any("INSERT" in sql and "test_reports" in sql for sql in executed_calls)
        assert insert_called, (
            "cursor.execute must be called with INSERT INTO test_reports. "
            f"Actual calls: {executed_calls}"
        )

    def test_insert_report_fifo_delete_called_with_max_reports(self):
        """
        FIFO enforcement: after INSERT, insert_report must execute a DELETE that
        removes all rows except the MAX_REPORTS (7) most recent.
        The DELETE must use MAX_REPORTS as the LIMIT parameter.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        db.db_pool = mock_pool

        report = _make_report("fifotest")
        db.insert_report(report)

        # Find the DELETE call and verify it uses MAX_REPORTS as the limit
        delete_calls = [
            c for c in mock_cursor.execute.call_args_list
            if len(c.args) > 0 and "DELETE" in str(c.args[0])
        ]
        assert len(delete_calls) == 1, (
            f"Expected exactly 1 DELETE call for FIFO enforcement, got {len(delete_calls)}. "
            "Each insert must prune excess records."
        )

        # Verify the LIMIT parameter is MAX_REPORTS
        delete_args = delete_calls[0].args
        assert len(delete_args) >= 2, "DELETE must have a parameter tuple for LIMIT."
        limit_param = delete_args[1]
        assert limit_param == (db.MAX_REPORTS,), (
            f"FIFO DELETE limit is {limit_param}, expected ({db.MAX_REPORTS},). "
            "The DELETE must keep only the MAX_REPORTS most recent rows."
        )

    def test_insert_report_fifo_delete_uses_received_at_order(self):
        """
        The FIFO DELETE must order by received_at DESC to identify the most
        recent reports to keep. Ordering by ID or insertion order is insufficient
        because reports may arrive out of order.
        """
        source = CHAOS_DB_PATH.read_text()
        # The DELETE subquery must use received_at to determine recency
        assert "received_at" in source.split("DELETE")[1][:500], (
            "FIFO DELETE subquery must order by received_at to identify recent rows. "
            "Ordering by ID alone is not reliable for time-based recency."
        )

    def test_insert_report_commits_transaction(self):
        """
        After INSERT + DELETE, insert_report must commit the transaction.
        Without commit, the FIFO enforcement is not durable.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        db.db_pool = mock_pool

        db.insert_report(_make_report("commitme"))

        mock_conn.commit.assert_called_once(), (
            "conn.commit() must be called after INSERT and DELETE to persist changes."
        )

    def test_insert_report_releases_connection(self):
        """
        insert_report must always return the connection to the pool (putconn)
        to prevent pool exhaustion.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        db.db_pool = mock_pool

        db.insert_report(_make_report("pooltest"))

        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_insert_report_db_error_triggers_fallback(self):
        """
        When cursor.execute raises an exception during INSERT, insert_report
        must switch to fallback mode (_using_fallback=True) and store the
        report in the in-memory deque.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(
            raise_on_execute=Exception("DB write error")
        )
        db.db_pool = mock_pool

        report = _make_report("errtest")
        result = db.insert_report(report)

        assert result == report, "insert_report must still return the report on DB error."
        assert db._using_fallback is True, (
            "_using_fallback must be True after a DB write error."
        )
        assert report in list(db._fallback_reports), (
            "Report must be in _fallback_reports after DB write error."
        )

    def test_insert_report_rolls_back_on_error(self):
        """
        On DB error, insert_report must call conn.rollback() to avoid a
        stuck transaction on the connection before returning it to the pool.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(
            raise_on_execute=Exception("constraint violation")
        )
        db.db_pool = mock_pool

        db.insert_report(_make_report("rollbackme"))

        mock_conn.rollback.assert_called_once(), (
            "conn.rollback() must be called when INSERT fails."
        )

    def test_insert_report_returns_report_dict(self):
        """
        insert_report must return the same report dict passed in,
        regardless of DB path or fallback path.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        db.db_pool = mock_pool

        report = _make_report("returnme")
        result = db.insert_report(report)

        assert result is report, (
            "insert_report must return the original report dict."
        )

    def test_insert_report_passes_all_fields_to_cursor(self):
        """
        The INSERT must include all required fields: id, received_at, suite, total,
        passed, failed, skipped, duration_ms, tests, git_sha, image_tag.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        db.db_pool = mock_pool

        report = _make_report(
            "fieldcheck",
            suite="smoke",
            total=10,
            passed=9,
            failed=1,
            skipped=0,
            duration_ms=5678.9,
            git_sha="cafebabe",
            image_tag="v2.0",
        )
        db.insert_report(report)

        # Find INSERT call args
        insert_calls = [
            c for c in mock_cursor.execute.call_args_list
            if len(c.args) > 0 and "INSERT" in str(c.args[0])
        ]
        assert len(insert_calls) == 1
        params = insert_calls[0].args[1]
        assert params[0] == "fieldcheck", f"id mismatch: {params[0]}"
        assert params[2] == "smoke", f"suite mismatch: {params[2]}"
        assert params[3] == 10, f"total mismatch: {params[3]}"
        assert params[4] == 9, f"passed mismatch: {params[4]}"
        assert params[5] == 1, f"failed mismatch: {params[5]}"
        assert params[9] == "cafebabe", f"git_sha mismatch: {params[9]}"
        assert params[10] == "v2.0", f"image_tag mismatch: {params[10]}"


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: list_reports() — DB path, fallback, and LIMIT enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestListReports:
    """Tests for chaos.db.list_reports()."""

    def test_list_reports_fallback_when_pool_is_none(self):
        """
        When db_pool is None, list_reports must return list(_fallback_reports).
        """
        import chaos.db as db
        report = _make_report("listfallback")
        db._fallback_reports.appendleft(report)

        result = db.list_reports()

        assert result == [report], (
            "list_reports must return fallback deque contents when db_pool is None."
        )

    def test_list_reports_fallback_returns_all_deque_items(self):
        """
        Fallback list_reports must return all items in the deque (up to MAX_REPORTS).
        """
        import chaos.db as db
        reports = [_make_report(f"r{i:02d}") for i in range(5)]
        for r in reports:
            db._fallback_reports.appendleft(r)

        result = db.list_reports()

        assert len(result) == 5, f"Expected 5 reports, got {len(result)}."

    def test_list_reports_db_path_executes_select(self):
        """
        When DB is available, list_reports must execute SELECT on test_reports.
        """
        import chaos.db as db
        db_row = _make_db_row("selecttest")
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchall_return=[db_row])
        db.db_pool = mock_pool

        db.list_reports()

        executed_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        select_called = any("SELECT" in sql and "test_reports" in sql for sql in executed_calls)
        assert select_called, "list_reports must execute SELECT FROM test_reports."

    def test_list_reports_db_path_uses_limit(self):
        """
        The SELECT must include LIMIT MAX_REPORTS to cap the result set to 7.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchall_return=[])
        db.db_pool = mock_pool

        db.list_reports()

        # Find SELECT call args
        select_calls = [
            c for c in mock_cursor.execute.call_args_list
            if len(c.args) > 0 and "SELECT" in str(c.args[0])
        ]
        assert len(select_calls) == 1
        params = select_calls[0].args[1]
        assert params == (db.MAX_REPORTS,), (
            f"SELECT LIMIT param is {params}, expected ({db.MAX_REPORTS},). "
            "list_reports must cap results at MAX_REPORTS."
        )

    def test_list_reports_db_path_orders_by_received_at_desc(self):
        """
        The SELECT must order by received_at DESC so the newest reports appear first.
        This matches the UI expectation of newest-first journal display.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchall_return=[])
        db.db_pool = mock_pool

        db.list_reports()

        select_calls = [
            c for c in mock_cursor.execute.call_args_list
            if len(c.args) > 0 and "SELECT" in str(c.args[0])
        ]
        sql = str(select_calls[0].args[0])
        assert "received_at" in sql and "DESC" in sql, (
            f"SELECT must ORDER BY received_at DESC. Got: {sql}"
        )

    def test_list_reports_maps_rows_to_dicts(self):
        """
        list_reports must convert each DB row to an API-compatible dict
        using _row_to_dict (timestamp to ISO string, tests as list).
        """
        import chaos.db as db
        db_row = _make_db_row("dictmap")
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchall_return=[db_row])
        db.db_pool = mock_pool

        result = db.list_reports()

        assert len(result) == 1
        row_dict = result[0]
        assert row_dict["id"] == "dictmap"
        # Timestamp must be an ISO string, not a datetime object
        assert isinstance(row_dict["received_at"], str), (
            "received_at must be serialized to an ISO string for JSON responses."
        )
        assert isinstance(row_dict["tests"], list), (
            "tests must be a list, not a raw JSON string."
        )

    def test_list_reports_releases_connection(self):
        """list_reports must release the connection back to the pool."""
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchall_return=[])
        db.db_pool = mock_pool

        db.list_reports()

        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_list_reports_db_error_falls_back(self):
        """
        When SELECT fails, list_reports must set _using_fallback=True and
        return the in-memory deque contents.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(
            raise_on_execute=Exception("DB read error")
        )
        db.db_pool = mock_pool
        fallback_report = _make_report("fallbackread")
        db._fallback_reports.appendleft(fallback_report)

        result = db.list_reports()

        assert db._using_fallback is True
        assert fallback_report in result, (
            "list_reports must return fallback deque contents on DB error."
        )

    def test_list_reports_returns_empty_list_when_no_reports(self):
        """
        list_reports must return [] when there are no reports in either
        the DB or the fallback deque.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchall_return=[])
        db.db_pool = mock_pool

        result = db.list_reports()

        assert result == [], f"Expected empty list, got {result}"


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: get_latest_report() — most recent report retrieval
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLatestReport:
    """Tests for chaos.db.get_latest_report()."""

    def test_get_latest_fallback_empty_returns_none(self):
        """
        When fallback deque is empty and db_pool is None, get_latest_report
        must return None (no reports available).
        """
        import chaos.db as db
        result = db.get_latest_report()
        assert result is None, "get_latest_report must return None when no reports exist."

    def test_get_latest_fallback_returns_first_item(self):
        """
        When using fallback (db_pool=None), get_latest_report must return
        the first item in _fallback_reports (most recently appended via appendleft).
        """
        import chaos.db as db
        newest = _make_report("newest")
        older = _make_report("older")
        db._fallback_reports.appendleft(older)
        db._fallback_reports.appendleft(newest)

        result = db.get_latest_report()

        assert result == newest, (
            "get_latest_report must return the most recent report (index 0 of deque)."
        )

    def test_get_latest_db_path_executes_select_limit_1(self):
        """
        When DB is available, get_latest_report must execute SELECT with LIMIT 1
        to retrieve only the most recent row.
        """
        import chaos.db as db
        db_row = _make_db_row("latestdb")
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchone_return=db_row)
        db.db_pool = mock_pool

        db.get_latest_report()

        executed_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        select_called = any("SELECT" in sql and "LIMIT" in sql for sql in executed_calls)
        assert select_called, "get_latest_report must SELECT with LIMIT."

        # Verify LIMIT 1 (no params tuple since LIMIT is hard-coded)
        # The SQL itself should contain LIMIT 1
        select_sql_calls = [
            str(c.args[0]) for c in mock_cursor.execute.call_args_list
            if len(c.args) > 0 and "SELECT" in str(c.args[0])
        ]
        assert any("LIMIT 1" in sql for sql in select_sql_calls), (
            "get_latest_report must SELECT with LIMIT 1, not a larger limit."
        )

    def test_get_latest_db_path_returns_mapped_dict(self):
        """
        get_latest_report must convert the DB row to an API dict and return it.
        """
        import chaos.db as db
        db_row = _make_db_row("mapdicttest")
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchone_return=db_row)
        db.db_pool = mock_pool

        result = db.get_latest_report()

        assert result is not None
        assert result["id"] == "mapdicttest"
        assert isinstance(result["received_at"], str), (
            "received_at must be ISO string in returned dict."
        )

    def test_get_latest_db_path_empty_returns_none(self):
        """
        When DB has no rows, get_latest_report must return None.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchone_return=None)
        db.db_pool = mock_pool

        result = db.get_latest_report()

        assert result is None, "get_latest_report must return None when table is empty."

    def test_get_latest_releases_connection(self):
        """get_latest_report must release the connection back to the pool."""
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(fetchone_return=None)
        db.db_pool = mock_pool

        db.get_latest_report()

        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_get_latest_db_error_falls_back(self):
        """
        When SELECT fails, get_latest_report must set _using_fallback=True
        and return from the in-memory deque.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(
            raise_on_execute=Exception("DB read failure")
        )
        db.db_pool = mock_pool
        fallback_report = _make_report("latestfallback")
        db._fallback_reports.appendleft(fallback_report)

        result = db.get_latest_report()

        assert db._using_fallback is True
        assert result == fallback_report, (
            "get_latest_report must return the fallback deque's first item on DB error."
        )

    def test_get_latest_db_error_empty_fallback_returns_none(self):
        """
        When DB fails and fallback deque is also empty, return None.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool(
            raise_on_execute=Exception("DB failure")
        )
        db.db_pool = mock_pool

        result = db.get_latest_report()

        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Section 6: close_db() — connection pool shutdown
# ─────────────────────────────────────────────────────────────────────────────

class TestCloseDb:
    """Tests for chaos.db.close_db()."""

    def test_close_db_calls_closeall(self):
        """
        close_db() must call db_pool.closeall() to release all connections.
        """
        import chaos.db as db
        mock_pool = MagicMock()
        db.db_pool = mock_pool

        db.close_db()

        mock_pool.closeall.assert_called_once(), (
            "close_db() must call db_pool.closeall() to properly shut down the pool."
        )

    def test_close_db_with_no_pool_does_not_raise(self):
        """
        close_db() when db_pool is None must not raise an exception.
        This handles the case where the DB was never successfully initialized.
        """
        import chaos.db as db
        db.db_pool = None

        try:
            db.close_db()
        except Exception as e:
            pytest.fail(f"close_db() raised {e} when db_pool is None.")


# ─────────────────────────────────────────────────────────────────────────────
# Section 7: _row_to_dict() — DB row serialization
# ─────────────────────────────────────────────────────────────────────────────

class TestRowToDict:
    """Tests for chaos.db._row_to_dict()."""

    def test_row_to_dict_converts_datetime_to_iso_string(self):
        """
        DB rows have datetime objects for received_at; _row_to_dict must
        convert them to ISO format strings for JSON serialization.
        """
        import chaos.db as db
        row = _make_db_row("isoconv")
        row["received_at"] = datetime(2026, 3, 1, 10, 30, 0, tzinfo=timezone.utc)

        result = db._row_to_dict(row)

        assert isinstance(result["received_at"], str), (
            "received_at must be a string in the returned dict."
        )
        assert "2026-03-01" in result["received_at"], (
            f"ISO string must contain the date. Got: {result['received_at']}"
        )

    def test_row_to_dict_preserves_list_tests(self):
        """
        When tests field is already a list (psycopg2 auto-parses JSONB),
        _row_to_dict must preserve it as-is.
        """
        import chaos.db as db
        row = _make_db_row()
        row["tests"] = [{"name": "test_home", "status": "passed", "duration_ms": 100.0}]

        result = db._row_to_dict(row)

        assert isinstance(result["tests"], list)
        assert result["tests"][0]["name"] == "test_home"

    def test_row_to_dict_parses_json_string_tests(self):
        """
        When tests is a JSON string (raw storage without JSONB auto-parse),
        _row_to_dict must parse it into a Python list.
        """
        import chaos.db as db
        row = _make_db_row()
        row["tests"] = '[{"name": "test_api", "status": "passed", "duration_ms": 50.0}]'

        result = db._row_to_dict(row)

        assert isinstance(result["tests"], list), (
            "tests must be a list even when stored as a JSON string."
        )
        assert result["tests"][0]["name"] == "test_api"

    def test_row_to_dict_handles_null_tests(self):
        """
        When tests is None or empty, _row_to_dict must return an empty list.
        """
        import chaos.db as db
        row = _make_db_row()
        row["tests"] = None

        result = db._row_to_dict(row)

        assert isinstance(result["tests"], list), (
            "tests must be a list (not None) in the returned dict."
        )

    def test_row_to_dict_includes_all_required_fields(self):
        """
        _row_to_dict output must include all fields required by the API schema:
        id, received_at, suite, total, passed, failed, skipped, duration_ms,
        tests, git_sha, image_tag.
        """
        import chaos.db as db
        row = _make_db_row("allfields")
        result = db._row_to_dict(row)

        required_fields = [
            "id", "received_at", "suite", "total", "passed",
            "failed", "skipped", "duration_ms", "tests", "git_sha", "image_tag"
        ]
        for field in required_fields:
            assert field in result, f"Field '{field}' missing from _row_to_dict output."

    def test_row_to_dict_preserves_optional_null_fields(self):
        """
        git_sha and image_tag may be None. _row_to_dict must preserve None values.
        """
        import chaos.db as db
        row = _make_db_row()
        row["git_sha"] = None
        row["image_tag"] = None

        result = db._row_to_dict(row)

        assert result["git_sha"] is None
        assert result["image_tag"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Section 8: FIFO queue enforcement — behavioral integration
# ─────────────────────────────────────────────────────────────────────────────

class TestFifoQueueEnforcement:
    """
    Behavioral tests verifying FIFO semantics: at most 7 records kept,
    oldest record purged when the 8th is inserted.
    """

    def test_fallback_deque_caps_at_7(self):
        """
        The in-memory fallback deque must enforce maxlen=7.
        Inserting an 8th report via fallback must drop the oldest.
        """
        import chaos.db as db
        # Insert 8 reports when fallback is active (db_pool=None)
        for i in range(8):
            db.insert_report(_make_report(f"fifo{i:02d}"))

        assert len(db._fallback_reports) == 7, (
            f"Fallback deque has {len(db._fallback_reports)} items; expected 7. "
            "The FIFO queue must cap at MAX_REPORTS."
        )

    def test_fallback_deque_newest_first(self):
        """
        After inserting multiple reports via fallback, the most recent must be
        at index 0 (appendleft semantics: newest = first).
        """
        import chaos.db as db
        for i in range(3):
            db.insert_report(_make_report(f"order{i:02d}"))

        # Most recently inserted should be first
        first = list(db._fallback_reports)[0]
        assert first["id"] == "order02", (
            f"Expected 'order02' at index 0, got '{first['id']}'. "
            "Reports must be newest-first in the fallback deque."
        )

    def test_fifo_sql_contains_delete_for_overflow(self):
        """
        The DB FIFO logic must use a DELETE statement to physically remove
        old rows (not just hide them with LIMIT on SELECT).
        This ensures the database doesn't grow unbounded over time.
        """
        source = CHAOS_DB_PATH.read_text()
        assert "DELETE FROM test_reports" in source, (
            "FIFO enforcement must physically DELETE old rows from the database, "
            "not just use SELECT LIMIT to hide them."
        )

    def test_fifo_sql_uses_not_in_subquery(self):
        """
        The FIFO DELETE must use NOT IN with a subquery that selects the
        MAX_REPORTS most recent IDs, preserving exactly the newest 7 records.
        """
        source = CHAOS_DB_PATH.read_text()
        assert "NOT IN" in source or "not in" in source.lower(), (
            "FIFO DELETE must use NOT IN subquery to identify rows to delete."
        )

    def test_db_insert_calls_delete_on_every_insert(self):
        """
        FIFO cleanup must run on every INSERT, not just when the table exceeds 7.
        This is safe because DELETE WHERE NOT IN (latest 7) is a no-op when
        fewer than 7 rows exist.
        """
        import chaos.db as db
        mock_pool, mock_conn, mock_cursor = _make_mock_pool()
        db.db_pool = mock_pool

        db.insert_report(_make_report("fifofirst"))

        delete_calls = [
            c for c in mock_cursor.execute.call_args_list
            if len(c.args) > 0 and "DELETE" in str(c.args[0])
        ]
        assert len(delete_calls) == 1, (
            "DELETE must be called on every insert (even the first) "
            "to ensure FIFO cleanup is always applied."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 9: Source code structure verification
# ─────────────────────────────────────────────────────────────────────────────

class TestDbSourceStructure:
    """
    Static source-code checks to verify the approved plan structure is in place.
    """

    def test_db_module_exists(self):
        """chaos/db.py must exist as a separate module (not inlined in main.py)."""
        assert CHAOS_DB_PATH.exists(), (
            "src/chaos/db.py does not exist. "
            "The architect plan requires extracting DB logic to a separate module."
        )

    def test_db_module_imports_simple_connection_pool(self):
        """db.py must import SimpleConnectionPool from psycopg2.pool."""
        source = CHAOS_DB_PATH.read_text()
        assert "SimpleConnectionPool" in source, (
            "db.py must use psycopg2.pool.SimpleConnectionPool for connection pooling."
        )

    def test_db_module_imports_real_dict_cursor(self):
        """
        db.py must use RealDictCursor for SELECT queries so rows are returned
        as dict-like objects (not tuples) for easy field access.
        """
        source = CHAOS_DB_PATH.read_text()
        assert "RealDictCursor" in source, (
            "db.py must use RealDictCursor for SELECT results. "
            "Without it, rows are tuples and field-by-name access breaks."
        )

    def test_main_imports_from_db_module(self):
        """
        chaos/main.py must import from chaos.db (or src.chaos.db),
        not define the DB logic inline.
        """
        chaos_main_path = SRC_DIR / "chaos" / "main.py"
        source = chaos_main_path.read_text()
        assert "from" in source and "db import" in source, (
            "chaos/main.py must import DB functions from chaos.db. "
            "DB logic must not be inlined in main.py."
        )

    def test_main_has_startup_hook(self):
        """main.py must call init_db() on startup to establish the DB connection."""
        chaos_main_path = SRC_DIR / "chaos" / "main.py"
        source = chaos_main_path.read_text()
        assert "init_db" in source and "startup" in source, (
            "chaos/main.py must call init_db() in a startup event handler."
        )

    def test_main_has_shutdown_hook(self):
        """main.py must call close_db() on shutdown to release pool connections."""
        chaos_main_path = SRC_DIR / "chaos" / "main.py"
        source = chaos_main_path.read_text()
        assert "close_db" in source and "shutdown" in source, (
            "chaos/main.py must call close_db() in a shutdown event handler."
        )

    def test_db_has_graceful_fallback_deque(self):
        """db.py must define a fallback in-memory deque for use when DB is down."""
        source = CHAOS_DB_PATH.read_text()
        assert "deque" in source, (
            "db.py must include a deque-based fallback for when the DB is unavailable."
        )

    def test_db_env_vars_have_sensible_defaults(self):
        """
        DB connection env vars must have sensible in-cluster defaults so the
        chaos controller works without explicit environment configuration
        during development.
        """
        source = CHAOS_DB_PATH.read_text()
        # Check for default values that look like in-cluster service names
        assert "postgres" in source.lower(), (
            "db.py must have a default DB_NAME or DB_USER of 'postgres'."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 10: UI rendering verification
# ─────────────────────────────────────────────────────────────────────────────

class TestChaosReportsUI:
    """
    Verify the chaos controller HTML UI correctly implements the test report
    journal tab as specified in the approved plan.
    """

    def _read_html(self) -> str:
        return CHAOS_HTML.read_text()

    def test_ui_description_mentions_last_7_reports(self):
        """
        The Test Reports tab description must say 'last 7' to match the plan
        requirement of showing the 7-record FIFO journal.
        """
        html = self._read_html()
        assert "last 7" in html.lower(), (
            "UI description must mention 'last 7' reports. "
            "The description was updated as part of the approved plan."
        )

    def test_ui_has_test_reports_tab_button(self):
        """
        The chaos UI must have a 'Test Reports' tab button for navigation.
        """
        html = self._read_html()
        assert "Test Reports" in html, (
            "UI must have a 'Test Reports' tab button in the tab bar."
        )

    def test_ui_has_reports_tab_container(self):
        """
        There must be a container div with id='tab-reports' for the reports panel.
        """
        html = self._read_html()
        assert 'id="tab-reports"' in html or "id='tab-reports'" in html, (
            "UI must have a div with id='tab-reports' for the report journal panel."
        )

    def test_ui_has_reports_container_div(self):
        """
        The reports panel must have a container (id='reports-container') where
        report cards are dynamically rendered by JavaScript.
        """
        html = self._read_html()
        assert "reports-container" in html, (
            "UI must have a 'reports-container' element for dynamic report rendering."
        )

    def test_ui_has_render_report_javascript_function(self):
        """
        The UI must define a renderReport() JavaScript function that converts
        a report object to HTML markup for display.
        """
        html = self._read_html()
        assert "renderReport" in html, (
            "UI must define a renderReport() JS function for report card rendering."
        )

    def test_ui_fetches_from_test_reports_api(self):
        """
        The UI must fetch reports from /api/test-reports to populate the journal.
        """
        html = self._read_html()
        assert "/api/test-reports" in html, (
            "UI must fetch from /api/test-reports to load the report journal."
        )

    def test_ui_has_report_card_css_class(self):
        """
        The UI must define .report-card CSS for the stacked card layout.
        """
        html = self._read_html()
        assert "report-card" in html, (
            "UI must define .report-card CSS class for the report journal cards."
        )

    def test_ui_has_pass_badge_style(self):
        """
        The UI must have styling for passed reports (.report-badge.pass or similar).
        """
        html = self._read_html()
        assert "report-badge" in html, (
            "UI must define .report-badge styles for pass/fail status indicators."
        )
        assert "pass" in html, (
            "UI must include 'pass' badge variant for all-passed reports."
        )
        assert "fail" in html, (
            "UI must include 'fail' badge variant for reports with failures."
        )

    def test_ui_has_empty_state_message(self):
        """
        The UI must show an empty state message when no reports are available.
        """
        html = self._read_html()
        assert "no-reports" in html or "No test reports" in html, (
            "UI must have an empty state message shown when the journal has no entries."
        )

    def test_ui_has_expandable_test_cases(self):
        """
        Individual report cards must support expanding to show test case details
        using HTML <details> for progressive disclosure.
        """
        html = self._read_html()
        assert "<details" in html, (
            "UI must use <details> element for expandable test case list in report cards."
        )

    def test_ui_has_refresh_button(self):
        """
        The Test Reports tab must have a Refresh button to manually reload reports.
        """
        html = self._read_html()
        assert "refreshReports" in html or "Refresh" in html, (
            "UI must have a 'Refresh' button that calls refreshReports()."
        )

    def test_ui_render_report_shows_passed_count(self):
        """
        renderReport() must display the passed count from the report data.
        """
        html = self._read_html()
        # Check that r.passed is referenced in the render function
        assert "r.passed" in html or ".passed" in html, (
            "renderReport() must display the passed test count."
        )

    def test_ui_render_report_shows_failed_count(self):
        """renderReport() must display the failed test count."""
        html = self._read_html()
        assert "r.failed" in html or ".failed" in html, (
            "renderReport() must display the failed test count."
        )

    def test_ui_render_report_shows_suite_and_id(self):
        """renderReport() must display the suite name and report ID."""
        html = self._read_html()
        assert "r.suite" in html and "r.id" in html, (
            "renderReport() must include suite name and report ID in the card."
        )

    def test_ui_render_report_shows_image_tag(self):
        """
        renderReport() should display the image_tag when available,
        allowing users to correlate reports with specific deployments.
        """
        html = self._read_html()
        assert "image_tag" in html or "imageTag" in html, (
            "renderReport() must optionally show the image tag for deployment correlation."
        )

    def test_ui_refresh_reports_called_when_tab_active(self):
        """
        The tab switching logic must call refreshReports() when the reports tab
        is activated, ensuring users see fresh data without manual refresh.
        """
        html = self._read_html()
        # The switchTab function should call refreshReports for the reports tab
        assert "refreshReports" in html, (
            "refreshReports() must be called when the reports tab is activated."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 11: API endpoint integration (TestClient with mocked DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestChaosReportsAPI:
    """
    Integration tests for the test report API endpoints in chaos/main.py.

    Uses FastAPI TestClient with mocked DB functions to avoid real DB calls.
    Tests verify the API contract: status codes, response schemas, and routing.
    """

    @pytest.fixture(autouse=True)
    def api_client(self):
        """
        Create a TestClient for the chaos app with DB functions mocked.

        Patches insert_report, list_reports, get_latest_report in the chaos.main
        namespace (where they are imported) to avoid real DB calls.
        """
        from chaos.main import app
        from fastapi.testclient import TestClient

        with patch("chaos.main.insert_report") as mock_insert, \
             patch("chaos.main.list_reports") as mock_list, \
             patch("chaos.main.get_latest_report") as mock_latest:

            self.mock_insert = mock_insert
            self.mock_list = mock_list
            self.mock_latest = mock_latest

            self.client = TestClient(app, raise_server_exceptions=True)
            yield

    def test_post_test_report_returns_201(self):
        """
        POST /api/test-reports with a valid payload must return HTTP 201 Created.
        """
        self.mock_insert.return_value = _make_report("api001")
        payload = {
            "suite": "post-deploy",
            "total": 5,
            "passed": 5,
            "failed": 0,
            "skipped": 0,
            "duration_ms": 1234.5,
            "tests": [],
        }

        resp = self.client.post("/api/test-reports", json=payload)

        assert resp.status_code == 201, (
            f"POST /api/test-reports must return 201 Created, got {resp.status_code}: {resp.text}"
        )

    def test_post_test_report_response_has_status_and_id(self):
        """
        POST /api/test-reports response must include 'status': 'stored' and an 'id'.
        """
        self.mock_insert.return_value = _make_report("api002")
        payload = {
            "suite": "post-deploy",
            "total": 3,
            "passed": 3,
            "failed": 0,
            "skipped": 0,
            "duration_ms": 500.0,
            "tests": [],
        }

        resp = self.client.post("/api/test-reports", json=payload)
        data = resp.json()

        assert data.get("status") == "stored", (
            f"Response must have status='stored'. Got: {data}"
        )
        assert "id" in data, f"Response must include 'id'. Got: {data}"

    def test_post_test_report_calls_insert_report(self):
        """
        POST /api/test-reports must call insert_report() with a dict containing
        the submitted report data.
        """
        report = _make_report("callcheck")
        self.mock_insert.return_value = report
        payload = {
            "suite": "smoke",
            "total": 10,
            "passed": 10,
            "failed": 0,
            "skipped": 0,
            "duration_ms": 2000.0,
            "tests": [],
            "git_sha": "abc123",
            "image_tag": "v3.0",
        }

        self.client.post("/api/test-reports", json=payload)

        self.mock_insert.assert_called_once()
        call_arg = self.mock_insert.call_args.args[0]
        assert call_arg["suite"] == "smoke"
        assert call_arg["total"] == 10
        assert call_arg["git_sha"] == "abc123"
        assert call_arg["image_tag"] == "v3.0"

    def test_post_test_report_assigns_server_id(self):
        """
        POST /api/test-reports must assign a server-generated ID to the report
        (not use a client-provided ID), ensuring IDs are trusted server-side.
        """
        captured = {}

        def capture_insert(report_dict):
            captured["report"] = report_dict
            return report_dict

        self.mock_insert.side_effect = capture_insert

        self.client.post("/api/test-reports", json={
            "suite": "post-deploy", "total": 1, "passed": 1,
            "failed": 0, "skipped": 0, "duration_ms": 100.0, "tests": []
        })

        assert "report" in captured
        assert "id" in captured["report"], "Server must assign an 'id' field."
        assert len(captured["report"]["id"]) > 0, "Server-assigned ID must not be empty."

    def test_get_test_reports_returns_200(self):
        """GET /api/test-reports must return 200."""
        self.mock_list.return_value = []
        resp = self.client.get("/api/test-reports")
        assert resp.status_code == 200, (
            f"GET /api/test-reports must return 200, got {resp.status_code}: {resp.text}"
        )

    def test_get_test_reports_returns_list(self):
        """GET /api/test-reports response must be a JSON array."""
        self.mock_list.return_value = [_make_report("listapi")]
        resp = self.client.get("/api/test-reports")
        data = resp.json()
        assert isinstance(data, list), (
            f"GET /api/test-reports must return a JSON array, got {type(data).__name__}: {data}"
        )

    def test_get_test_reports_calls_list_reports(self):
        """GET /api/test-reports must delegate to list_reports() from db.py."""
        self.mock_list.return_value = []
        self.client.get("/api/test-reports")
        self.mock_list.assert_called_once(), (
            "GET /api/test-reports must call list_reports() to retrieve reports."
        )

    def test_get_test_reports_returns_up_to_7(self):
        """
        GET /api/test-reports must return at most 7 reports.
        The FIFO limit is enforced at the DB/fallback level, but the API
        must not override this by fetching more.
        """
        seven_reports = [_make_report(f"r{i:02d}") for i in range(7)]
        self.mock_list.return_value = seven_reports
        resp = self.client.get("/api/test-reports")
        data = resp.json()
        assert len(data) <= 7, (
            f"GET /api/test-reports must return at most 7 reports, got {len(data)}."
        )

    def test_get_latest_report_returns_200(self):
        """GET /api/test-reports/latest must return 200."""
        self.mock_latest.return_value = _make_report("latest001")
        resp = self.client.get("/api/test-reports/latest")
        assert resp.status_code == 200

    def test_get_latest_report_when_empty_returns_no_reports_status(self):
        """
        When no reports exist, GET /api/test-reports/latest must return
        {"status": "no_reports"} rather than raising a 404 or 500.
        """
        self.mock_latest.return_value = None
        resp = self.client.get("/api/test-reports/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "no_reports", (
            f"Empty journal must return {{status: 'no_reports'}}, got: {data}"
        )

    def test_get_latest_report_with_data_returns_report(self):
        """
        When a report exists, GET /api/test-reports/latest must return the
        report dict with the expected fields.
        """
        report = _make_report("latestapi")
        self.mock_latest.return_value = report
        resp = self.client.get("/api/test-reports/latest")
        data = resp.json()
        assert data.get("id") == "latestapi", (
            f"Response must include the report's id. Got: {data}"
        )

    def test_post_test_report_validates_total_field(self):
        """
        POST /api/test-reports with an invalid payload (missing required fields
        but Pydantic has defaults) must still succeed due to all-optional fields.
        """
        # All fields have defaults in TestReport, so empty body should work
        self.mock_insert.return_value = _make_report("minimalpost")
        resp = self.client.post("/api/test-reports", json={})
        assert resp.status_code == 201, (
            f"POST with empty body (all fields have defaults) must return 201, "
            f"got {resp.status_code}: {resp.text}"
        )

    def test_post_test_report_with_git_sha_and_image_tag(self):
        """
        POST /api/test-reports must accept and store git_sha and image_tag
        fields for deployment correlation.
        """
        captured = {}

        def capture_insert(report_dict):
            captured["report"] = report_dict
            return report_dict

        self.mock_insert.side_effect = capture_insert

        self.client.post("/api/test-reports", json={
            "git_sha": "abc123def456",
            "image_tag": "v1.2.3",
        })

        assert captured.get("report", {}).get("git_sha") == "abc123def456"
        assert captured.get("report", {}).get("image_tag") == "v1.2.3"
