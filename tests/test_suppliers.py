# Store/tests/test_suppliers.py
# @ai-rules:
# 1. [Pattern]: Uses SimpleConnectionPool patch around TestClient for DB mocking.
# 2. [Constraint]: TestClient must be inside `with` block, not module-level.
"""Unit tests for supplier CRUD endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client_with_db():
    with patch("app.main.SimpleConnectionPool") as mock_pool_cls:
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        with TestClient(app) as client:
            yield client, mock_cursor


def test_create_supplier(client_with_db):
    client, mock_db = client_with_db
    mock_db.fetchone.return_value = ["2026-02-21T00:00:00"]
    response = client.post("/suppliers", json={
        "name": "Test Supplier",
        "contact_email": "test@example.com",
        "phone": "1234567890"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Supplier"
    assert data["contact_email"] == "test@example.com"
    assert "id" in data


def test_create_supplier_minimal(client_with_db):
    client, mock_db = client_with_db
    mock_db.fetchone.return_value = ["2026-02-21T00:00:00"]
    response = client.post("/suppliers", json={"name": "Min Supplier"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Min Supplier"
    assert data["contact_email"] is None


def test_list_suppliers_with_low_stock(client_with_db):
    client, mock_db = client_with_db
    mock_db.fetchall.return_value = [
        ("id1", "Supplier A", "a@ex.com", "111", "2026-02-21T00:00:00", 2)
    ]
    response = client.get("/suppliers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Supplier A"
    assert data[0]["low_stock_count"] == 2


def test_delete_supplier_no_products(client_with_db):
    client, mock_db = client_with_db
    mock_db.fetchone.return_value = (0,)
    mock_db.rowcount = 1
    response = client.delete("/suppliers/some-id")
    assert response.status_code == 204


def test_delete_supplier_with_products_409(client_with_db):
    client, mock_db = client_with_db
    mock_db.fetchone.return_value = (3,)
    response = client.delete("/suppliers/some-id")
    assert response.status_code == 409
    assert "attached products" in response.json()["detail"]


def test_delete_supplier_not_found(client_with_db):
    client, mock_db = client_with_db
    mock_db.fetchone.return_value = (0,)
    mock_db.rowcount = 0
    response = client.delete("/suppliers/nonexistent")
    assert response.status_code == 404


def test_list_supplier_products(client_with_db):
    client, mock_db = client_with_db
    mock_db.fetchall.return_value = [
        ("pid1", "Widget", 9.99, 5, "SKU-001", None, "", "sid1", 10)
    ]
    response = client.get("/suppliers/sid1/products")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Widget"
