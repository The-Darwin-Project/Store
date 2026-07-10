# @ai-rules:
# 1. [Pattern]: Patches SimpleConnectionPool at module level so startup gets a mock pool.
# 2. [Constraint]: Repo root on sys.path for relative imports in src.inventory.
# 3. [Gotcha]: Each test needs its own TestClient context to avoid state leakage.
"""Tests verifying /catalog endpoints are identical aliases for /products (PR #93)."""

import sys
import os
import uuid
from unittest.mock import MagicMock, patch, call

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _REPO_ROOT)

from fastapi.testclient import TestClient

from src.inventory.main import app


SAMPLE_PRODUCT_ROW = (
    "550e8400-e29b-41d4-a716-446655440000",
    "Widget",
    9.99,
    100,
    "WDG-001",
    None,
    "A test widget",
    "660e8400-e29b-41d4-a716-446655440001",
    10,
    None,
    None,
    None,
)


def _mock_pool_and_cursor(mock_pool_cls):
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    return mock_pool, mock_conn, mock_cursor


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_list_returns_same_as_products_list(mock_pool_cls):
    """GET /catalog returns identical paginated response as GET /products."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = (1,)
    mock_cursor.fetchall.return_value = [SAMPLE_PRODUCT_ROW]

    with TestClient(app) as client:
        resp_products = client.get("/products")
        resp_catalog = client.get("/catalog")

    assert resp_products.status_code == 200
    assert resp_catalog.status_code == 200
    assert resp_products.json()["total"] == resp_catalog.json()["total"]
    assert resp_products.json()["page"] == resp_catalog.json()["page"]
    assert resp_products.json()["limit"] == resp_catalog.json()["limit"]


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_list_pagination(mock_pool_cls):
    """GET /catalog?page=2&limit=5 returns paginated response."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = (10,)
    mock_cursor.fetchall.return_value = []

    with TestClient(app) as client:
        resp = client.get("/catalog?page=2&limit=5")

    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 2
    assert data["limit"] == 5
    assert data["total"] == 10


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_list_invalid_page_returns_422(mock_pool_cls):
    """GET /catalog?page=0 returns 422 (same validation as /products)."""
    _, _, _ = _mock_pool_and_cursor(mock_pool_cls)

    with TestClient(app) as client:
        resp_catalog = client.get("/catalog?page=0")
        resp_products = client.get("/products?page=0")

    assert resp_catalog.status_code == 422
    assert resp_products.status_code == 422


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_get_by_id(mock_pool_cls):
    """GET /catalog/{id} returns same product as GET /products/{id}."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = SAMPLE_PRODUCT_ROW

    product_id = SAMPLE_PRODUCT_ROW[0]
    with TestClient(app) as client:
        resp_catalog = client.get(f"/catalog/{product_id}")
        resp_products = client.get(f"/products/{product_id}")

    assert resp_catalog.status_code == 200
    assert resp_products.status_code == 200
    assert resp_catalog.json()["id"] == product_id
    assert resp_catalog.json()["name"] == resp_products.json()["name"]
    assert resp_catalog.json()["price"] == resp_products.json()["price"]


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_get_nonexistent_returns_404(mock_pool_cls):
    """GET /catalog/{id} returns 404 for non-existent product."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = None

    with TestClient(app) as client:
        resp = client.get(f"/catalog/{uuid.uuid4()}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Product not found"


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_create_product(mock_pool_cls):
    """POST /catalog creates a product (same as POST /products)."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)

    payload = {
        "name": "New Widget",
        "price": 19.99,
        "stock": 50,
        "sku": "NW-001",
    }
    with TestClient(app) as client:
        resp = client.post("/catalog", json=payload)

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "New Widget"
    assert data["price"] == 19.99
    assert data["stock"] == 50


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_update_product(mock_pool_cls):
    """PUT /catalog/{id} full-updates a product."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    updated_row = (
        SAMPLE_PRODUCT_ROW[0], "Updated Widget", 29.99, 200,
        "UW-001", None, "Updated", None, 10, None, None, None,
    )
    mock_cursor.fetchone.return_value = updated_row

    payload = {
        "name": "Updated Widget",
        "price": 29.99,
        "stock": 200,
        "sku": "UW-001",
        "description": "Updated",
    }
    with TestClient(app) as client:
        resp = client.put(f"/catalog/{SAMPLE_PRODUCT_ROW[0]}", json=payload)

    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Widget"


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_patch_product(mock_pool_cls):
    """PATCH /catalog/{id} partially updates a product."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = SAMPLE_PRODUCT_ROW

    with TestClient(app) as client:
        resp = client.patch(
            f"/catalog/{SAMPLE_PRODUCT_ROW[0]}",
            json={"price": 14.99},
        )

    assert resp.status_code == 200
    assert resp.json()["price"] == 14.99


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_delete_product(mock_pool_cls):
    """DELETE /catalog/{id} deletes a product."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.rowcount = 1

    with TestClient(app) as client:
        resp = client.delete(f"/catalog/{SAMPLE_PRODUCT_ROW[0]}")

    assert resp.status_code == 204


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_delete_nonexistent_returns_404(mock_pool_cls):
    """DELETE /catalog/{id} returns 404 for non-existent product."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.rowcount = 0

    with TestClient(app) as client:
        resp = client.delete(f"/catalog/{uuid.uuid4()}")

    assert resp.status_code == 404


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_router_registered_in_app(mock_pool_cls):
    """Verify catalog_router is included in the FastAPI app."""
    _mock_pool_and_cursor(mock_pool_cls)

    with TestClient(app) as client:
        resp = client.get("/openapi.json")

    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/catalog" in paths, "/catalog not found in OpenAPI paths"
    assert "/catalog/{product_id}" in paths, "/catalog/{product_id} not in OpenAPI"

    catalog_methods = set(paths["/catalog"].keys())
    products_methods = set(paths["/products"].keys())
    assert catalog_methods == products_methods, (
        f"Method mismatch: /catalog has {catalog_methods}, /products has {products_methods}"
    )


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_create_status_code_matches_products(mock_pool_cls):
    """BUG: POST /catalog should return 201 like POST /products, not 200."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)

    payload = {"name": "Test", "price": 9.99, "stock": 10, "sku": "T-001"}
    with TestClient(app) as client:
        resp_products = client.post("/products", json=payload)
        resp_catalog = client.post("/catalog", json=payload)

    assert resp_products.status_code == 201, "POST /products should return 201"
    assert resp_catalog.status_code == resp_products.status_code, (
        f"POST /catalog returns {resp_catalog.status_code}, expected {resp_products.status_code}. "
        "Fix: add status_code=201 to catalog_router.add_api_route for POST"
    )


@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_delete_status_code_matches_products(mock_pool_cls):
    """BUG: DELETE /catalog should return 204 like DELETE /products, not 200."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.rowcount = 1

    product_id = SAMPLE_PRODUCT_ROW[0]
    with TestClient(app) as client:
        resp_products = client.delete(f"/products/{product_id}")
        resp_catalog = client.delete(f"/catalog/{product_id}")

    assert resp_products.status_code == 204, "DELETE /products should return 204"
    assert resp_catalog.status_code == resp_products.status_code, (
        f"DELETE /catalog returns {resp_catalog.status_code}, expected {resp_products.status_code}. "
        "Fix: add status_code=204 to catalog_router.add_api_route for DELETE"
    )


@patch("src.inventory.main.SimpleConnectionPool")
def test_products_endpoints_still_work(mock_pool_cls):
    """Regression: existing /products routes still respond correctly."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = (0,)
    mock_cursor.fetchall.return_value = []

    with TestClient(app) as client:
        resp = client.get("/products")

    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []
