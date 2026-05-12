# tests/test_categories_evt_2d1b17b0.py
# @ai-rules:
# 1. [Pattern]: Direct app.state.db_pool injection -- no module-level patch needed.
# 2. [Constraint]: Tests target src/inventory/main.py (nginx routes /categories there).
# 3. [Gotcha]: update_category calls fetchone twice: UPDATE RETURNING, then COUNT(*).
"""QE tests for evt-2d1b17b0: product categories CRUD + product category_id integration."""

import sys
import os
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _REPO_ROOT)

CATEGORY_ID = str(uuid.uuid4())
CATEGORY_ID_2 = str(uuid.uuid4())
PRODUCT_ID = str(uuid.uuid4())
CREATED_AT = datetime(2026, 5, 12, 12, 0, 0)


def make_mock_pool(cursor_mock: MagicMock) -> MagicMock:
    conn = MagicMock()
    pool = MagicMock()
    pool.getconn.return_value = conn
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor_mock)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return pool


# ===========================================================================
# GET /categories
# ===========================================================================

class TestCategoriesList:
    def setup_method(self):
        from src.inventory.main import app
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def test_list_categories_empty(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        self._set_pool(cur)

        resp = self.client.get("/categories")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_categories_returns_all_fields(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            (CATEGORY_ID, "Electronics", "Electronic gadgets", CREATED_AT, 5),
        ]
        self._set_pool(cur)

        resp = self.client.get("/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        cat = data[0]
        assert cat["id"] == CATEGORY_ID
        assert cat["name"] == "Electronics"
        assert cat["description"] == "Electronic gadgets"
        assert cat["product_count"] == 5

    def test_list_categories_product_count_zero_for_empty_category(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            (CATEGORY_ID, "Books", "Literature", CREATED_AT, 0),
        ]
        self._set_pool(cur)

        resp = self.client.get("/categories")
        data = resp.json()
        assert data[0]["product_count"] == 0

    def test_list_categories_multiple_sorted(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            (CATEGORY_ID, "Clothing", "Apparel", CREATED_AT, 3),
            (CATEGORY_ID_2, "Electronics", "Gadgets", CREATED_AT, 12),
        ]
        self._set_pool(cur)

        resp = self.client.get("/categories")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Clothing"
        assert data[1]["name"] == "Electronics"


# ===========================================================================
# POST /categories
# ===========================================================================

class TestCategoriesCreate:
    def setup_method(self):
        from src.inventory.main import app
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def test_create_category_success_201(self):
        cur = MagicMock()
        cur.fetchone.return_value = (CATEGORY_ID, "Electronics", "Electronic gadgets", CREATED_AT)
        self._set_pool(cur)

        resp = self.client.post("/categories", json={"name": "Electronics", "description": "Electronic gadgets"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Electronics"
        assert data["description"] == "Electronic gadgets"
        assert data["product_count"] == 0
        assert "id" in data

    def test_create_category_name_only(self):
        """Description is optional -- defaults to empty string."""
        cur = MagicMock()
        cur.fetchone.return_value = (CATEGORY_ID, "Books", "", CREATED_AT)
        self._set_pool(cur)

        resp = self.client.post("/categories", json={"name": "Books"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Books"

    def test_create_category_duplicate_name_returns_409(self):
        cur = MagicMock()
        cur.execute.side_effect = Exception("duplicate key value violates unique constraint")
        self._set_pool(cur)

        resp = self.client.post("/categories", json={"name": "Electronics"})
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_category_empty_name_returns_422(self):
        """min_length=1 on name field."""
        cur = MagicMock()
        self._set_pool(cur)

        resp = self.client.post("/categories", json={"name": ""})
        assert resp.status_code == 422

    def test_create_category_missing_name_returns_422(self):
        cur = MagicMock()
        self._set_pool(cur)

        resp = self.client.post("/categories", json={"description": "No name provided"})
        assert resp.status_code == 422

    def test_create_category_name_stripped_of_whitespace(self):
        """Name is stripped before INSERT."""
        cur = MagicMock()
        cur.fetchone.return_value = (CATEGORY_ID, "Electronics", "", CREATED_AT)
        self._set_pool(cur)

        resp = self.client.post("/categories", json={"name": "  Electronics  "})
        assert resp.status_code == 201
        # Verify INSERT was called with stripped name
        call_args = cur.execute.call_args
        assert "Electronics" in str(call_args)
        assert "  Electronics  " not in str(call_args)


# ===========================================================================
# PATCH /categories/{id}
# ===========================================================================

class TestCategoriesUpdate:
    def setup_method(self):
        from src.inventory.main import app
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def test_update_category_name(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (CATEGORY_ID, "Electronics Pro", "Electronic gadgets", CREATED_AT),
            (3,),
        ]
        self._set_pool(cur)

        resp = self.client.patch(f"/categories/{CATEGORY_ID}", json={"name": "Electronics Pro"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Electronics Pro"
        assert data["product_count"] == 3

    def test_update_category_description(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (CATEGORY_ID, "Electronics", "Updated description", CREATED_AT),
            (0,),
        ]
        self._set_pool(cur)

        resp = self.client.patch(f"/categories/{CATEGORY_ID}", json={"description": "Updated description"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_update_category_both_fields(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (CATEGORY_ID, "New Name", "New description", CREATED_AT),
            (7,),
        ]
        self._set_pool(cur)

        resp = self.client.patch(
            f"/categories/{CATEGORY_ID}",
            json={"name": "New Name", "description": "New description"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["description"] == "New description"
        assert data["product_count"] == 7

    def test_update_category_empty_body_returns_400(self):
        """PATCH with empty body must return 400 (no fields to update)."""
        cur = MagicMock()
        self._set_pool(cur)

        resp = self.client.patch(f"/categories/{CATEGORY_ID}", json={})
        assert resp.status_code == 400
        assert "No fields to update" in resp.json()["detail"]

    def test_update_category_not_found_returns_404(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        self._set_pool(cur)

        resp = self.client.patch(f"/categories/{CATEGORY_ID}", json={"name": "Ghost"})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ===========================================================================
# DELETE /categories/{id}
# ===========================================================================

class TestCategoriesDelete:
    def setup_method(self):
        from src.inventory.main import app
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def test_delete_category_success_204(self):
        cur = MagicMock()
        cur.rowcount = 1
        self._set_pool(cur)

        resp = self.client.delete(f"/categories/{CATEGORY_ID}")
        assert resp.status_code == 204

    def test_delete_category_not_found_returns_404(self):
        cur = MagicMock()
        cur.rowcount = 0
        self._set_pool(cur)

        resp = self.client.delete(f"/categories/nonexistent-id")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_delete_category_commits_before_rowcount_check(self):
        """Delete issues commit -- products become uncategorized via ON DELETE SET NULL (DB-level)."""
        cur = MagicMock()
        cur.rowcount = 1
        self._set_pool(cur)

        resp = self.client.delete(f"/categories/{CATEGORY_ID}")
        assert resp.status_code == 204
        pool = self.app.state.db_pool
        conn = pool.getconn()
        conn.commit.assert_called()


# ===========================================================================
# Product category_id integration
# ===========================================================================

class TestProductsCategoryIntegration:
    def setup_method(self):
        from src.inventory.main import app
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def _product_row(self, category_id=None):
        return (
            PRODUCT_ID, "Widget", 9.99, 10, "SKU-001",
            None, "", None, 10, None, None, category_id,
        )

    def test_list_products_includes_category_id_field(self):
        cur = MagicMock()
        cur.fetchone.return_value = (1,)
        cur.fetchall.return_value = [self._product_row(CATEGORY_ID)]
        self._set_pool(cur)

        resp = self.client.get("/products")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "category_id" in item
        assert item["category_id"] == CATEGORY_ID

    def test_list_products_category_id_null_for_uncategorized(self):
        cur = MagicMock()
        cur.fetchone.return_value = (1,)
        cur.fetchall.return_value = [self._product_row(None)]
        self._set_pool(cur)

        resp = self.client.get("/products")
        assert resp.json()["items"][0]["category_id"] is None

    def test_list_products_filtered_by_category_id(self):
        """?category_id=X triggers a filtered COUNT + filtered SELECT."""
        cur = MagicMock()
        cur.fetchone.return_value = (1,)
        cur.fetchall.return_value = [self._product_row(CATEGORY_ID)]
        self._set_pool(cur)

        resp = self.client.get(f"/products?category_id={CATEGORY_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["category_id"] == CATEGORY_ID

        # Verify WHERE clause was used (category_id param passed to SQL)
        calls = [str(c) for c in cur.execute.call_args_list]
        assert any(CATEGORY_ID in c for c in calls)

    def test_list_products_no_filter_returns_all(self):
        """Without category_id param, all products are returned."""
        cur = MagicMock()
        cur.fetchone.return_value = (2,)
        cur.fetchall.return_value = [
            self._product_row(CATEGORY_ID),
            self._product_row(None),
        ]
        self._set_pool(cur)

        resp = self.client.get("/products")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_create_product_with_category_id(self):
        cur = MagicMock()
        self._set_pool(cur)

        resp = self.client.post("/products", json={
            "name": "Electronics Widget",
            "price": 49.99,
            "stock": 100,
            "sku": "ELEC-001",
            "category_id": CATEGORY_ID,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["category_id"] == CATEGORY_ID
        assert data["name"] == "Electronics Widget"

    def test_create_product_without_category_id_defaults_null(self):
        cur = MagicMock()
        self._set_pool(cur)

        resp = self.client.post("/products", json={
            "name": "Uncategorized Widget",
            "price": 9.99,
            "stock": 50,
            "sku": "UNCAT-001",
        })
        assert resp.status_code == 201
        assert resp.json()["category_id"] is None

    def test_patch_product_updates_category_id(self):
        cur = MagicMock()
        cur.fetchone.return_value = self._product_row(None)
        self._set_pool(cur)

        resp = self.client.patch(f"/products/{PRODUCT_ID}", json={"category_id": CATEGORY_ID})
        assert resp.status_code == 200
        assert resp.json()["category_id"] == CATEGORY_ID

    def test_patch_product_clears_category_id(self):
        """Setting category_id to null removes the category assignment."""
        cur = MagicMock()
        cur.fetchone.return_value = self._product_row(CATEGORY_ID)
        self._set_pool(cur)

        resp = self.client.patch(f"/products/{PRODUCT_ID}", json={"category_id": None})
        assert resp.status_code == 200
        assert resp.json()["category_id"] is None

    def test_get_product_includes_category_id(self):
        cur = MagicMock()
        cur.fetchone.return_value = self._product_row(CATEGORY_ID)
        self._set_pool(cur)

        resp = self.client.get(f"/products/{PRODUCT_ID}")
        assert resp.status_code == 200
        assert resp.json()["category_id"] == CATEGORY_ID
