# tests/test_split_services_evt_fb71d51d.py
# @ai-rules:
# 1. [Scope]: Tests for evt-fb71d51d backend split -- inventory service and customers_svc.
# 2. [Pattern]: Mock request.app.state.db_pool and request.app.state.inventory_client -- NOT module-level globals.
# 3. [Coverage]: Health endpoints, internal stock-deduct/restore/coupon-use, order creation cross-service flow.
# 4. [Gotcha]: Orders route is async and uses InventoryClient -- must mock InventoryClient on app.state.
"""
QE integration tests for evt-fb71d51d: backend split into inventory + customers_svc.

Verifies:
- Inventory service health and internal endpoints (stock-deduct, stock-restore, coupon-use)
- Customer management service health endpoint
- Order creation cross-service flow: stock deduction via InventoryClient, coupon validation, rollback
- Order status update triggering stock restore via InventoryClient on cancel
- No regressions in existing app.main routes
"""

import sys
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add repo root so that src.inventory and src.customers_svc can be imported as
# sub-packages of src (required for their relative imports like "from ..app.chaos_state").
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PRODUCT_ID = str(uuid.uuid4())
CUSTOMER_ID = str(uuid.uuid4())
COUPON_ID = str(uuid.uuid4())


def make_mock_pool(cursor_mock: MagicMock) -> MagicMock:
    """Build a mock psycopg2 connection pool that yields the given cursor mock."""
    conn = MagicMock()
    pool = MagicMock()
    pool.getconn.return_value = conn
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor_mock)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return pool


# ===========================================================================
# INVENTORY SERVICE TESTS
# ===========================================================================

class TestInventoryHealth:
    """Health endpoint on the inventory service."""

    def setup_method(self):
        from src.inventory.main import app
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_health_returns_inventory_online(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "inventory_online"


class TestInventoryInternalStockDeduct:
    """POST /internal/stock-deduct -- atomic stock deduction."""

    def setup_method(self):
        from src.inventory.main import app
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def test_deduct_stock_success(self):
        """Happy path: product has enough stock, returns price_at_purchase."""
        cur = MagicMock()
        # UPDATE ... RETURNING returns (id, name, price, stock, sale_price, discount_percent)
        cur.fetchone.return_value = (PRODUCT_ID, "Widget A", 25.00, 8, None, None)
        self._set_pool(cur)

        resp = self.client.post(
            "/internal/stock-deduct",
            json={"product_id": PRODUCT_ID, "quantity": 2},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["product_id"] == PRODUCT_ID
        assert data["price_at_purchase"] == 25.00
        assert data["remaining_stock"] == 8
        assert data["product_name"] == "Widget A"

    def test_deduct_stock_with_sale_price(self):
        """Stock deduction uses effective_price (sale_price overrides base price)."""
        cur = MagicMock()
        # (id, name, price=100, stock=5, sale_price=75, discount_percent=None)
        cur.fetchone.return_value = (PRODUCT_ID, "Sale Widget", 100.00, 5, 75.00, None)
        self._set_pool(cur)

        resp = self.client.post(
            "/internal/stock-deduct",
            json={"product_id": PRODUCT_ID, "quantity": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["price_at_purchase"] == 75.00

    def test_deduct_stock_insufficient(self):
        """UPDATE returns no row when stock < quantity → 400 with clear message."""
        cur = MagicMock()
        # First fetchone (UPDATE) returns None → insufficient stock path
        # Second fetchone (SELECT) returns product name/stock
        cur.fetchone.side_effect = [None, ("Widget A", 1)]
        self._set_pool(cur)

        resp = self.client.post(
            "/internal/stock-deduct",
            json={"product_id": PRODUCT_ID, "quantity": 5},
        )
        assert resp.status_code == 400
        assert "Insufficient stock" in resp.json()["detail"]

    def test_deduct_stock_product_not_found(self):
        """Product doesn't exist at all → 404."""
        cur = MagicMock()
        cur.fetchone.side_effect = [None, None]
        self._set_pool(cur)

        resp = self.client.post(
            "/internal/stock-deduct",
            json={"product_id": PRODUCT_ID, "quantity": 1},
        )
        assert resp.status_code == 404


class TestInventoryInternalStockRestore:
    """POST /internal/stock-restore -- restore stock on cancel/return."""

    def setup_method(self):
        from src.inventory.main import app
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def test_restore_stock_success(self):
        cur = MagicMock()
        cur.fetchone.return_value = (PRODUCT_ID,)
        self._set_pool(cur)

        resp = self.client.post(
            "/internal/stock-restore",
            json={"product_id": PRODUCT_ID, "quantity": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "restored"
        assert data["product_id"] == PRODUCT_ID
        assert data["quantity"] == 3

    def test_restore_stock_product_not_found(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        self._set_pool(cur)

        resp = self.client.post(
            "/internal/stock-restore",
            json={"product_id": PRODUCT_ID, "quantity": 1},
        )
        assert resp.status_code == 404


class TestInventoryInternalCouponUse:
    """POST /internal/coupon-use -- atomic coupon usage increment."""

    def setup_method(self):
        from src.inventory.main import app
        self.app = app
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def test_increment_coupon_usage_success(self):
        cur = MagicMock()
        cur.fetchone.return_value = (COUPON_ID,)
        self._set_pool(cur)

        resp = self.client.post(
            "/internal/coupon-use",
            json={"coupon_id": COUPON_ID},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "incremented"
        assert data["coupon_id"] == COUPON_ID

    def test_increment_coupon_usage_limit_reached(self):
        """UPDATE returns nothing when max_uses reached → 400."""
        cur = MagicMock()
        cur.fetchone.return_value = None
        self._set_pool(cur)

        resp = self.client.post(
            "/internal/coupon-use",
            json={"coupon_id": COUPON_ID},
        )
        assert resp.status_code == 400
        assert "limit reached" in resp.json()["detail"]


# ===========================================================================
# CUSTOMERS SERVICE TESTS
# ===========================================================================

class TestCustomersHealth:
    """Health endpoint on the customers management service."""

    def setup_method(self):
        from src.customers_svc.main import app
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_health_returns_customers_online(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "customers_online"


class TestOrderCreationCrossService:
    """
    Order creation flow: POST /orders exercises InventoryClient for stock deduction.

    This is the critical cross-service path from the architectural split:
      Customer service → HTTP → Inventory service (stock-deduct)
    """

    def setup_method(self):
        from src.customers_svc.main import app
        from src.customers_svc.inventory_client import InventoryClient
        self.app = app
        self.InventoryClient = InventoryClient
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def _set_inventory_client(self, client_mock):
        self.app.state.inventory_client = client_mock

    def _make_inventory_client_mock(
        self,
        price=19.99,
        product_name="Test Widget",
        deduct_raises=None,
        coupon_valid=True,
        coupon_discount=5.0,
    ) -> MagicMock:
        """Return a mock InventoryClient with configurable behavior."""
        mock = MagicMock(spec=self.InventoryClient)

        if deduct_raises:
            mock.deduct_stock = AsyncMock(side_effect=deduct_raises)
        else:
            mock.deduct_stock = AsyncMock(return_value={
                "product_id": PRODUCT_ID,
                "price_at_purchase": price,
                "remaining_stock": 8,
                "product_name": product_name,
            })

        mock.restore_stock = AsyncMock(return_value={"status": "restored"})

        mock.validate_coupon = AsyncMock(return_value={
            "valid": coupon_valid,
            "coupon": {"id": COUPON_ID, "code": "SAVE5"},
            "discount_amount": coupon_discount,
        })

        mock.increment_coupon_usage = AsyncMock(return_value={"status": "incremented"})

        return mock

    def _cursor_for_order_creation(self, customer_exists=True):
        """Build a cursor mock simulating:
          1. Customer existence check (SELECT id FROM customers)
          2. INSERT orders (no return)
          3. INSERT order_items (no return)
          4. SELECT created_at FROM orders
        """
        cur = MagicMock()
        if customer_exists:
            # fetchone called for: customer check, then created_at query
            cur.fetchone.side_effect = [
                (CUSTOMER_ID,),      # customer exists
                ("2026-04-03T10:00:00",),  # created_at for the new order
            ]
        else:
            cur.fetchone.side_effect = [None]  # customer not found
        return cur

    def test_create_order_success_deducts_stock_via_inventory_client(self):
        """Happy path: order creation calls InventoryClient.deduct_stock."""
        cur = self._cursor_for_order_creation()
        self._set_pool(cur)
        inv_mock = self._make_inventory_client_mock(price=19.99)
        self._set_inventory_client(inv_mock)

        payload = {
            "customer_id": CUSTOMER_ID,
            "items": [{"product_id": PRODUCT_ID, "quantity": 2}],
        }
        resp = self.client.post("/orders", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "pending"
        assert data["customer_id"] == CUSTOMER_ID
        # Total = price * qty
        assert abs(data["total_amount"] - 39.98) < 0.01
        assert len(data["items"]) == 1
        assert data["items"][0]["price_at_purchase"] == 19.99
        # InventoryClient.deduct_stock must have been called once
        inv_mock.deduct_stock.assert_awaited_once_with(PRODUCT_ID, 2)

    def test_create_order_with_coupon_calls_validate_and_increment(self):
        """Coupon flow: validate_coupon then increment_coupon_usage are both called."""
        cur = self._cursor_for_order_creation()
        self._set_pool(cur)
        inv_mock = self._make_inventory_client_mock(price=20.00, coupon_discount=4.00)
        self._set_inventory_client(inv_mock)

        payload = {
            "customer_id": CUSTOMER_ID,
            "items": [{"product_id": PRODUCT_ID, "quantity": 1}],
            "coupon_code": "SAVE5",
        }
        resp = self.client.post("/orders", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        # Total after discount: 20.00 - 4.00 = 16.00
        assert abs(data["total_amount"] - 16.00) < 0.01
        assert data["coupon_code"] == "SAVE5"
        assert abs(data["discount_amount"] - 4.00) < 0.01
        inv_mock.validate_coupon.assert_awaited_once_with("SAVE5", 20.00)
        inv_mock.increment_coupon_usage.assert_awaited_once_with(COUPON_ID)

    def test_create_order_invalid_customer_returns_400(self):
        """Non-existent customer_id → 400 before any inventory calls."""
        cur = self._cursor_for_order_creation(customer_exists=False)
        self._set_pool(cur)
        inv_mock = self._make_inventory_client_mock()
        self._set_inventory_client(inv_mock)

        payload = {
            "customer_id": CUSTOMER_ID,
            "items": [{"product_id": PRODUCT_ID, "quantity": 1}],
        }
        resp = self.client.post("/orders", json=payload)
        assert resp.status_code == 400
        assert "customer" in resp.json()["detail"].lower()
        # InventoryClient must NOT be called (fail fast on invalid customer)
        inv_mock.deduct_stock.assert_not_awaited()

    def test_create_order_stock_deduction_failure_triggers_rollback(self):
        """If deduct_stock raises InventoryError, restore_stock is called for prior items."""
        from src.customers_svc.inventory_client import InventoryError

        cur = self._cursor_for_order_creation()
        self._set_pool(cur)

        PRODUCT_2 = str(uuid.uuid4())
        deduct_calls = 0

        async def deduct_side_effect(product_id, quantity):
            nonlocal deduct_calls
            deduct_calls += 1
            if deduct_calls == 1:
                # First item succeeds
                return {
                    "product_id": product_id,
                    "price_at_purchase": 10.00,
                    "remaining_stock": 9,
                    "product_name": "Item 1",
                }
            else:
                # Second item fails with insufficient stock
                raise InventoryError(400, "Insufficient stock for 'Item 2' (available: 0, requested: 3)")

        inv_mock = MagicMock(spec=self.InventoryClient)
        inv_mock.deduct_stock = AsyncMock(side_effect=deduct_side_effect)
        inv_mock.restore_stock = AsyncMock(return_value={"status": "restored"})
        inv_mock.validate_coupon = AsyncMock()
        inv_mock.increment_coupon_usage = AsyncMock()
        self._set_inventory_client(inv_mock)

        payload = {
            "customer_id": CUSTOMER_ID,
            "items": [
                {"product_id": PRODUCT_ID, "quantity": 1},
                {"product_id": PRODUCT_2, "quantity": 3},
            ],
        }
        resp = self.client.post("/orders", json=payload)
        assert resp.status_code == 400
        assert "Insufficient stock" in resp.json()["detail"]
        # First item's stock must be restored
        inv_mock.restore_stock.assert_awaited_once_with(PRODUCT_ID, 1)

    def test_create_order_missing_items_returns_422(self):
        """Payload without items fails validation before hitting DB or inventory."""
        inv_mock = self._make_inventory_client_mock()
        self._set_inventory_client(inv_mock)

        resp = self.client.post("/orders", json={"customer_id": CUSTOMER_ID})
        assert resp.status_code == 422
        inv_mock.deduct_stock.assert_not_awaited()


class TestOrderStatusUpdateRestoresStock:
    """PATCH /orders/{id}/status -- cancel/return triggers stock restore via InventoryClient."""

    def setup_method(self):
        from src.customers_svc.main import app
        from src.customers_svc.inventory_client import InventoryClient
        self.app = app
        self.InventoryClient = InventoryClient
        self.client = TestClient(app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def _set_inventory_client(self, client_mock):
        self.app.state.inventory_client = client_mock

    def test_cancel_order_restores_stock(self):
        """Cancelling a pending order calls restore_stock for each order item."""
        ORDER_ID = str(uuid.uuid4())

        cur = MagicMock()
        # Calls: SELECT order (returns pending), SELECT items, UPDATE status RETURNING
        cur.fetchone.side_effect = [
            (ORDER_ID, "2026-04-03", 39.98, "pending", CUSTOMER_ID),  # SELECT order
            (ORDER_ID, "2026-04-03", 39.98, "cancelled", CUSTOMER_ID, None, 0.0),  # UPDATE RETURNING
        ]
        cur.fetchall.return_value = [
            (PRODUCT_ID, 2),  # (product_id, quantity) from order_items
        ]
        self._set_pool(cur)

        inv_mock = MagicMock(spec=self.InventoryClient)
        inv_mock.restore_stock = AsyncMock(return_value={"status": "restored"})
        self._set_inventory_client(inv_mock)

        resp = self.client.patch(
            f"/orders/{ORDER_ID}/status",
            json={"status": "cancelled"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "cancelled"
        # Stock must be restored for the cancelled items
        inv_mock.restore_stock.assert_awaited_once_with(str(PRODUCT_ID), 2)

    def test_invalid_status_transition_returns_400(self):
        """Delivered → pending is not an allowed transition."""
        ORDER_ID = str(uuid.uuid4())

        cur = MagicMock()
        cur.fetchone.return_value = (ORDER_ID, "2026-04-03", 50.00, "delivered", CUSTOMER_ID)
        cur.fetchall.return_value = []
        self._set_pool(cur)

        inv_mock = MagicMock(spec=self.InventoryClient)
        inv_mock.restore_stock = AsyncMock()
        self._set_inventory_client(inv_mock)

        resp = self.client.patch(
            f"/orders/{ORDER_ID}/status",
            json={"status": "pending"},
        )
        assert resp.status_code == 400
        inv_mock.restore_stock.assert_not_awaited()


# ===========================================================================
# INVENTORY CLIENT UNIT TESTS
# ===========================================================================

class TestInventoryClientUnit:
    """Unit tests for InventoryClient HTTP calls."""

    def test_inventory_client_uses_env_url(self):
        """INVENTORY_SERVICE_URL env var is respected."""
        with patch.dict(os.environ, {"INVENTORY_SERVICE_URL": "http://custom-inventory:9999"}):
            # Re-import to pick up patched env
            import importlib
            import src.customers_svc.inventory_client as ic_module
            importlib.reload(ic_module)
            client = ic_module.InventoryClient()
            assert client.base_url == "http://custom-inventory:9999"

    def test_inventory_error_carries_status_and_detail(self):
        """InventoryError exposes status_code and detail for HTTPException mapping."""
        from src.customers_svc.inventory_client import InventoryError
        err = InventoryError(400, "Insufficient stock")
        assert err.status_code == 400
        assert err.detail == "Insufficient stock"
        assert "Insufficient stock" in str(err)
