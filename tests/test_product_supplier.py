# Store/tests/test_product_supplier.py
# @ai-rules:
# 1. [Pattern]: Uses SimpleConnectionPool patch around TestClient for DB mocking.
# 2. [Constraint]: TestClient must be inside `with` block, not module-level.
"""Unit tests for product-supplier link functionality."""

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


def test_create_product_with_supplier(client_with_db):
    client, mock_db = client_with_db
    response = client.post("/products", json={
        "name": "Product 1",
        "price": 10.0,
        "stock": 5,
        "sku": "SKU1",
        "supplier_id": "supp-123",
        "reorder_threshold": 10
    })
    assert response.status_code == 201
    data = response.json()
    assert data["supplier_id"] == "supp-123"
    assert data["reorder_threshold"] == 10


def test_patch_product_with_supplier(client_with_db):
    client, mock_db = client_with_db
    # 12 columns: id, name, price, stock, sku, image_data, description,
    #             supplier_id, reorder_threshold, sale_price, discount_percent, category_id
    mock_db.fetchone.return_value = ("id1", "P1", 10.0, 5, "SKU1", None, "Desc", "supp-1", 10, None, None, None)
    response = client.patch("/products/id1", json={
        "supplier_id": "supp-456",
        "reorder_threshold": 15
    })
    assert response.status_code == 200
    data = response.json()
    assert data["supplier_id"] == "supp-456"
    assert data["reorder_threshold"] == 15


def test_get_products_with_supplier(client_with_db):
    client, mock_db = client_with_db
    # fetchone for COUNT(*), fetchall for rows -- 12 columns now includes category_id
    mock_db.fetchone.return_value = (1,)
    mock_db.fetchall.return_value = [
        ("id1", "P1", 10.0, 5, "SKU1", None, "Desc", "supp-1", 10, None, None, None)
    ]
    response = client.get("/products")
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["supplier_id"] == "supp-1"
    assert data["items"][0]["reorder_threshold"] == 10
