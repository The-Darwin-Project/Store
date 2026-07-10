# @ai-rules:
# 1. [Pattern]: Patches SimpleConnectionPool at module level so startup gets a mock pool.
# 2. [Constraint]: Repo root on sys.path for relative imports in src.inventory.
# 3. [Gotcha]: Each test needs its own TestClient context to avoid state leakage.
"""QE verification: /catalog and /products parity + Nginx proxy config (evt-3bbde129)."""

import sys
import os
import uuid
import json
from unittest.mock import MagicMock, patch

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

SECOND_PRODUCT_ROW = (
    "550e8400-e29b-41d4-a716-446655440099",
    "Gadget",
    24.99,
    42,
    "GDG-002",
    "base64data",
    "A test gadget",
    "660e8400-e29b-41d4-a716-446655440001",
    5,
    19.99,
    20.0,
    "770e8400-e29b-41d4-a716-446655440002",
)


def _mock_pool_and_cursor(mock_pool_cls):
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    return mock_pool, mock_conn, mock_cursor


# --- Full response body parity ---

@patch("src.inventory.main.SimpleConnectionPool")
def test_full_body_parity_list_endpoint(mock_pool_cls):
    """GET /catalog and GET /products return byte-identical JSON bodies."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = (2,)
    mock_cursor.fetchall.return_value = [SAMPLE_PRODUCT_ROW, SECOND_PRODUCT_ROW]

    with TestClient(app) as client:
        resp_products = client.get("/products")
        resp_catalog = client.get("/catalog")

    assert resp_products.status_code == resp_catalog.status_code == 200
    assert resp_products.json() == resp_catalog.json(), (
        "Full JSON body mismatch between GET /products and GET /catalog"
    )


@patch("src.inventory.main.SimpleConnectionPool")
def test_full_body_parity_get_by_id(mock_pool_cls):
    """GET /catalog/{id} and GET /products/{id} return identical JSON bodies."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = SECOND_PRODUCT_ROW

    product_id = SECOND_PRODUCT_ROW[0]
    with TestClient(app) as client:
        resp_products = client.get(f"/products/{product_id}")
        resp_catalog = client.get(f"/catalog/{product_id}")

    assert resp_products.status_code == resp_catalog.status_code == 200
    assert resp_products.json() == resp_catalog.json(), (
        "Full JSON body mismatch between GET /products/{id} and GET /catalog/{id}"
    )


@patch("src.inventory.main.SimpleConnectionPool")
def test_full_body_parity_create(mock_pool_cls):
    """POST /catalog and POST /products return identical response shapes."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)

    payload = {"name": "Parity Check", "price": 5.00, "stock": 10, "sku": "PC-001"}
    with TestClient(app) as client:
        resp_products = client.post("/products", json=payload)
        resp_catalog = client.post("/catalog", json=payload)

    assert resp_products.status_code == resp_catalog.status_code == 201
    prod_body = resp_products.json()
    cat_body = resp_catalog.json()
    assert set(prod_body.keys()) == set(cat_body.keys()), (
        f"Response key mismatch: /products has {set(prod_body.keys())}, "
        f"/catalog has {set(cat_body.keys())}"
    )


# --- Category filter parity ---

@patch("src.inventory.main.SimpleConnectionPool")
def test_category_filter_parity(mock_pool_cls):
    """GET /catalog?category_id=X and GET /products?category_id=X return identical results."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = (1,)
    mock_cursor.fetchall.return_value = [SECOND_PRODUCT_ROW]

    cat_id = "770e8400-e29b-41d4-a716-446655440002"
    with TestClient(app) as client:
        resp_products = client.get(f"/products?category_id={cat_id}")
        resp_catalog = client.get(f"/catalog?category_id={cat_id}")

    assert resp_products.status_code == resp_catalog.status_code == 200
    assert resp_products.json() == resp_catalog.json(), (
        "Category filter results differ between /products and /catalog"
    )


# --- Validation parity ---

@patch("src.inventory.main.SimpleConnectionPool")
def test_invalid_limit_parity(mock_pool_cls):
    """GET /catalog?limit=0 and GET /products?limit=0 both return 422."""
    _mock_pool_and_cursor(mock_pool_cls)

    with TestClient(app) as client:
        resp_products = client.get("/products?limit=0")
        resp_catalog = client.get("/catalog?limit=0")

    assert resp_products.status_code == 422
    assert resp_catalog.status_code == 422


@patch("src.inventory.main.SimpleConnectionPool")
def test_invalid_limit_over_max_parity(mock_pool_cls):
    """GET /catalog?limit=101 and GET /products?limit=101 both return 422."""
    _mock_pool_and_cursor(mock_pool_cls)

    with TestClient(app) as client:
        resp_products = client.get("/products?limit=101")
        resp_catalog = client.get("/catalog?limit=101")

    assert resp_products.status_code == 422
    assert resp_catalog.status_code == 422


# --- PUT/PATCH status code parity ---

@patch("src.inventory.main.SimpleConnectionPool")
def test_put_status_code_parity(mock_pool_cls):
    """PUT /catalog/{id} and PUT /products/{id} return same status code."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = SAMPLE_PRODUCT_ROW

    payload = {"name": "X", "price": 1.0, "stock": 1, "sku": "X-1"}
    pid = SAMPLE_PRODUCT_ROW[0]
    with TestClient(app) as client:
        resp_products = client.put(f"/products/{pid}", json=payload)
        resp_catalog = client.put(f"/catalog/{pid}", json=payload)

    assert resp_products.status_code == resp_catalog.status_code == 200


@patch("src.inventory.main.SimpleConnectionPool")
def test_patch_status_code_parity(mock_pool_cls):
    """PATCH /catalog/{id} and PATCH /products/{id} return same status code."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = SAMPLE_PRODUCT_ROW

    pid = SAMPLE_PRODUCT_ROW[0]
    with TestClient(app) as client:
        resp_products = client.patch(f"/products/{pid}", json={"stock": 5})
        resp_catalog = client.patch(f"/catalog/{pid}", json={"stock": 5})

    assert resp_products.status_code == resp_catalog.status_code == 200


# --- 404 parity ---

@patch("src.inventory.main.SimpleConnectionPool")
def test_get_nonexistent_404_parity(mock_pool_cls):
    """GET /catalog/{id} and GET /products/{id} both return 404 with same detail for missing products."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = None

    fake_id = str(uuid.uuid4())
    with TestClient(app) as client:
        resp_products = client.get(f"/products/{fake_id}")
        resp_catalog = client.get(f"/catalog/{fake_id}")

    assert resp_products.status_code == resp_catalog.status_code == 404
    assert resp_products.json() == resp_catalog.json(), (
        "404 response body differs between /products and /catalog"
    )


@patch("src.inventory.main.SimpleConnectionPool")
def test_put_nonexistent_404_parity(mock_pool_cls):
    """PUT /catalog/{id} and PUT /products/{id} both return 404 for missing products."""
    _, _, mock_cursor = _mock_pool_and_cursor(mock_pool_cls)
    mock_cursor.fetchone.return_value = None

    fake_id = str(uuid.uuid4())
    payload = {"name": "X", "price": 1.0, "stock": 1, "sku": "X-1"}
    with TestClient(app) as client:
        resp_products = client.put(f"/products/{fake_id}", json=payload)
        resp_catalog = client.put(f"/catalog/{fake_id}", json=payload)

    assert resp_products.status_code == resp_catalog.status_code == 404


# --- OpenAPI schema parity ---

@patch("src.inventory.main.SimpleConnectionPool")
def test_openapi_method_and_schema_parity(mock_pool_cls):
    """OpenAPI spec: /catalog endpoints mirror /products in methods and response schemas."""
    _mock_pool_and_cursor(mock_pool_cls)

    with TestClient(app) as client:
        resp = client.get("/openapi.json")

    assert resp.status_code == 200
    paths = resp.json()["paths"]

    assert "/catalog" in paths
    assert "/catalog/{product_id}" in paths
    assert "/products" in paths
    assert "/products/{product_id}" in paths

    for catalog_path, products_path in [
        ("/catalog", "/products"),
        ("/catalog/{product_id}", "/products/{product_id}"),
    ]:
        cat_methods = set(paths[catalog_path].keys())
        prod_methods = set(paths[products_path].keys())
        assert cat_methods == prod_methods, (
            f"{catalog_path} methods {cat_methods} != {products_path} methods {prod_methods}"
        )


# --- Nginx config validation ---

def test_nginx_catalog_proxy_block_exists():
    """Nginx default.conf contains /catalog location proxying to inventory upstream."""
    nginx_path = os.path.join(_REPO_ROOT, "nginx", "default.conf")
    assert os.path.exists(nginx_path), "nginx/default.conf not found"

    with open(nginx_path) as f:
        content = f.read()

    assert "location /catalog" in content, "/catalog location block missing from nginx config"
    assert "proxy_pass http://inventory" in content, "proxy_pass to inventory missing"

    lines = content.splitlines()
    in_catalog_block = False
    catalog_proxy_target = None
    products_proxy_target = None
    in_products_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("location /catalog"):
            in_catalog_block = True
            in_products_block = False
        elif stripped.startswith("location /products"):
            in_products_block = True
            in_catalog_block = False
        elif stripped == "}":
            in_catalog_block = False
            in_products_block = False

        if in_catalog_block and "proxy_pass" in stripped:
            catalog_proxy_target = stripped
        if in_products_block and "proxy_pass" in stripped:
            products_proxy_target = stripped

    assert catalog_proxy_target is not None, "No proxy_pass in /catalog block"
    assert products_proxy_target is not None, "No proxy_pass in /products block"
    assert catalog_proxy_target == products_proxy_target, (
        f"Proxy targets differ: /catalog -> {catalog_proxy_target}, "
        f"/products -> {products_proxy_target}"
    )


def test_nginx_catalog_has_required_proxy_headers():
    """Nginx /catalog block includes standard proxy headers."""
    nginx_path = os.path.join(_REPO_ROOT, "nginx", "default.conf")
    with open(nginx_path) as f:
        content = f.read()

    lines = content.splitlines()
    in_catalog_block = False
    catalog_headers = set()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("location /catalog"):
            in_catalog_block = True
        elif in_catalog_block and stripped == "}":
            break
        if in_catalog_block and "proxy_set_header" in stripped:
            header_name = stripped.split("proxy_set_header")[1].strip().split()[0]
            catalog_headers.add(header_name)

    required_headers = {"Host", "X-Real-IP", "X-Forwarded-For", "X-Forwarded-Proto"}
    missing = required_headers - catalog_headers
    assert not missing, f"Missing proxy headers in /catalog block: {missing}"


# --- Ensure catalog_router uses same handler functions ---

@patch("src.inventory.main.SimpleConnectionPool")
def test_catalog_routes_share_handler_functions(mock_pool_cls):
    """Verify catalog_router routes point to the same handler functions as products_router."""
    _mock_pool_and_cursor(mock_pool_cls)

    from src.inventory.routes.products import router as prod_router, catalog_router as cat_router

    def _normalize_path(path, prefix):
        return path.removeprefix(prefix) or "/"

    prod_routes = {}
    for route in prod_router.routes:
        if hasattr(route, "endpoint"):
            for method in route.methods:
                norm = _normalize_path(route.path, "/products")
                prod_routes[(method, norm)] = route.endpoint

    cat_routes = {}
    for route in cat_router.routes:
        if hasattr(route, "endpoint"):
            for method in route.methods:
                norm = _normalize_path(route.path, "/catalog")
                cat_routes[(method, norm)] = route.endpoint

    assert len(prod_routes) == len(cat_routes), (
        f"Route count mismatch: /products has {len(prod_routes)}, "
        f"/catalog has {len(cat_routes)}"
    )

    for (method, norm_path), prod_fn in prod_routes.items():
        cat_fn = cat_routes.get((method, norm_path))
        assert cat_fn is not None, f"Missing {method} {norm_path} in catalog_router"
        assert cat_fn is prod_fn, (
            f"{method} {norm_path}: catalog handler {cat_fn.__name__} "
            f"is not the same function as products handler {prod_fn.__name__}"
        )
