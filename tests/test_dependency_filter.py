# tests/test_dependency_filter.py
"""
Tests for DarwinClient._discover_topology dependency filtering.

Verifies that credential / config env vars (DB_USER, DB_PASSWORD, DB_NAME,
DB_PORT) are NOT treated as service dependencies, while connection-target
vars (DB_HOST, DATABASE_URL, REDIS_HOST) are correctly discovered.
"""

import sys
import os
from pathlib import Path
from unittest import mock

# Add src to sys.path so the app package is importable.
src_path = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_path))

from app.darwin_client import DarwinClient


def _make_client() -> DarwinClient:
    return DarwinClient(
        service="darwin-store",
        url="http://darwin-blackboard:8000",
        version="1.0.0",
    )


def test_db_user_not_treated_as_dependency():
    """DB_USER=postgres must NOT produce a 'postgres' dependency node."""
    env = {
        "DB_USER": "postgres",
        "DB_HOST": "darwin-store-postgres-svc",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    targets = [d.target for d in deps]
    assert "postgres" not in targets, (
        f"DB_USER value 'postgres' leaked into dependencies: {targets}"
    )


def test_db_password_not_treated_as_dependency():
    """DB_PASSWORD must be filtered out."""
    env = {
        "DB_PASSWORD": "supersecret",
        "DB_HOST": "darwin-store-postgres-svc",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    targets = [d.target for d in deps]
    assert "supersecret" not in targets, (
        f"DB_PASSWORD value leaked into dependencies: {targets}"
    )


def test_db_name_not_treated_as_dependency():
    """DB_NAME should not be treated as a dependency target."""
    env = {
        "DB_NAME": "darwin",
        "DB_HOST": "darwin-store-postgres-svc",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    targets = [d.target for d in deps]
    # "darwin" from DB_NAME should not appear (unless DB_HOST also resolves to "darwin")
    env_vars = [d.env_var for d in deps]
    assert "DB_NAME" not in env_vars, (
        f"DB_NAME should be filtered out, but found in env_vars: {env_vars}"
    )


def test_db_port_not_treated_as_dependency():
    """DB_PORT should not be treated as a dependency target."""
    env = {
        "DB_PORT": "5432",
        "DB_HOST": "darwin-store-postgres-svc",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    env_vars = [d.env_var for d in deps]
    assert "DB_PORT" not in env_vars, (
        f"DB_PORT should be filtered out, but found in env_vars: {env_vars}"
    )


def test_db_host_is_discovered():
    """DB_HOST should still be discovered as a database dependency."""
    env = {
        "DB_HOST": "darwin-store-postgres-svc",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    targets = [d.target for d in deps]
    assert "darwin-store-postgres-svc" in targets, (
        f"DB_HOST should be discovered, but targets are: {targets}"
    )
    db_host_dep = [d for d in deps if d.env_var == "DB_HOST"][0]
    assert db_host_dep.type == "db"


def test_database_url_is_discovered():
    """DATABASE_URL with a full connection string should be discovered."""
    env = {
        "DATABASE_URL": "postgresql://user:pass@my-db-host:5432/mydb",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    targets = [d.target for d in deps]
    assert "my-db-host" in targets, (
        f"DATABASE_URL hostname should be extracted, but targets are: {targets}"
    )


def test_redis_host_is_discovered():
    """REDIS_HOST should be discovered as a database dependency."""
    env = {
        "REDIS_HOST": "redis-master",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    targets = [d.target for d in deps]
    assert "redis-master" in targets, (
        f"REDIS_HOST should be discovered, targets are: {targets}"
    )


def test_http_url_is_discovered():
    """An env var ending in _URL should be discovered as http dependency."""
    env = {
        "DARWIN_URL": "http://darwin-blackboard-brain:8000",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    targets = [d.target for d in deps]
    assert "darwin-blackboard-brain" in targets, (
        f"DARWIN_URL should produce http dep, targets are: {targets}"
    )
    darwin_dep = [d for d in deps if d.env_var == "DARWIN_URL"][0]
    assert darwin_dep.type == "http"


def test_postgres_user_password_all_filtered():
    """
    Integration-style test: with the exact env vars from production,
    the ghost 'postgres' node must not appear.
    """
    env = {
        "DB_HOST": "darwin-store-postgres-svc",
        "DB_PORT": "5432",
        "DB_NAME": "darwin",
        "DB_USER": "postgres",
        "DB_PASSWORD": "darwin",
        "DARWIN_URL": "http://darwin-blackboard-brain:8000",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    targets = [d.target for d in deps]
    env_vars = [d.env_var for d in deps]

    # Only DB_HOST and DARWIN_URL should produce dependencies
    assert "DB_HOST" in env_vars, f"DB_HOST should be present: {env_vars}"
    assert "DARWIN_URL" in env_vars, f"DARWIN_URL should be present: {env_vars}"
    assert "DB_USER" not in env_vars, f"DB_USER should be filtered: {env_vars}"
    assert "DB_PASSWORD" not in env_vars, f"DB_PASSWORD should be filtered: {env_vars}"
    assert "DB_NAME" not in env_vars, f"DB_NAME should be filtered: {env_vars}"
    assert "DB_PORT" not in env_vars, f"DB_PORT should be filtered: {env_vars}"

    # The critical assertion: no ghost 'postgres' node
    assert "postgres" not in targets, (
        f"Ghost 'postgres' node must not appear in targets: {targets}"
    )


def test_postgres_pass_suffix_filtered():
    """POSTGRES_PASS (short form) should also be filtered."""
    env = {
        "POSTGRES_PASS": "secret123",
        "POSTGRES_HOST": "pg-primary",
    }
    client = _make_client()
    with mock.patch.dict(os.environ, env, clear=True):
        deps = client._discover_topology()

    env_vars = [d.env_var for d in deps]
    assert "POSTGRES_PASS" not in env_vars


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
