# Store/tests/test_pagination.py
# @ai-rules:
# 1. [Pattern]: Patches SimpleConnectionPool at module level so the startup event gets a mock pool.
# 2. [Constraint]: sys.path handled by conftest.py -- do NOT add manual path hacks.
# 3. [Gotcha]: fetchone must be set for the COUNT(*) query, fetchall for the SELECT.
"""Tests for pagination on products and orders endpoints."""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app


@patch("app.main.SimpleConnectionPool")
def test_products_pagination_defaults(mock_pool_cls):
    """GET /products with no params returns paginated response with defaults."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchone.return_value = (2,)  # COUNT(*) total
    mock_cursor.fetchall.return_value = []    # empty page of items

    with TestClient(app) as client:
        response = client.get("/products")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["limit"] == 20
    assert data["total"] == 2
    assert data["items"] == []


@patch("app.main.SimpleConnectionPool")
def test_pagination_invalid_page(mock_pool_cls):
    """GET /products?page=0 returns 422 (FastAPI validates ge=1)."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_pool.getconn.return_value = MagicMock()

    with TestClient(app) as client:
        response = client.get("/products?page=0")

    assert response.status_code == 422
