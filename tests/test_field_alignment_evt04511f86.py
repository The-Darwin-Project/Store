# Store/tests/test_field_alignment_evt04511f86.py
# @ai-rules:
# 1. [Pattern]: Uses mock_db fixture with patched SimpleConnectionPool (no real DB needed).
# 2. [Constraint]: Uses `with TestClient(app) as client:` inside test functions.
# 3. [Gotcha]: Tests verify 7 frontend-backend field mismatches fixed in PR #82 (evt-04511f86).
"""QE tests verifying PR #82 field alignment fixes for evt-04511f86.

Covers all 7 bugs: total_amount, price_at_purchase, shipping_* fields,
customer_id in reviews, invoice order_id filter, dashboard field names,
and CouponValidationResult error field.
"""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    CouponValidationResult,
    Customer,
    Order,
    OrderItem,
    Review,
    ReviewCreate,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    with patch("app.main.SimpleConnectionPool") as mock_pool_cls:
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_conn.cursor.return_value.__exit__.return_value = None
        app.state.db_pool = mock_pool
        yield mock_pool, mock_conn, mock_cur


PRODUCT_ID = str(uuid.uuid4())
CUSTOMER_ID = str(uuid.uuid4())
ORDER_ID = str(uuid.uuid4())
INVOICE_ID = str(uuid.uuid4())


# ── Fix 1: Order.total → total_amount ─────────────────────────────────────────

class TestFix1OrderTotalAmount:
    """Backend Order model uses total_amount (not total)."""

    def test_order_model_has_total_amount_field(self):
        """Order Pydantic model must have total_amount, not total."""
        order = Order(
            id=str(uuid.uuid4()),
            items=[],
            total_amount=99.99,
            status="pending",
            created_at=datetime.now().isoformat(),
        )
        assert order.total_amount == 99.99
        assert not hasattr(order, "total"), "Order must NOT have a deprecated 'total' field"

    def test_order_api_returns_total_amount(self, mock_db):
        """GET /orders response includes total_amount key."""
        _, _, mock_cur = mock_db
        # Row format: id, created_at, total_amount, status, customer_id,
        #             coupon_code, discount_amount, customer_name, invoice_id
        mock_cur.fetchall.side_effect = [
            [(ORDER_ID, datetime.now(), 150.0, "delivered", CUSTOMER_ID, None, 0.0, "Alice", None)],
            [],  # order items
        ]
        mock_cur.fetchone.return_value = (1,)  # COUNT(*)
        with TestClient(app) as client:
            resp = client.get("/orders")
        assert resp.status_code == 200
        data = resp.json()
        # Paginated response wraps in {"items": [...], "total": ...}
        orders = data.get("items", data) if isinstance(data, dict) else data
        assert len(orders) == 1
        assert "total_amount" in orders[0], "Response must contain total_amount"
        assert orders[0]["total_amount"] == 150.0
        assert "total" not in orders[0], "Response must NOT contain deprecated 'total' field"


# ── Fix 2: OrderItem.unit_price → price_at_purchase ───────────────────────────

class TestFix2PriceAtPurchase:
    """Backend OrderItem model uses price_at_purchase (not unit_price)."""

    def test_order_item_model_has_price_at_purchase(self):
        """OrderItem Pydantic model must have price_at_purchase."""
        item = OrderItem(
            id=str(uuid.uuid4()),
            order_id=ORDER_ID,
            product_id=PRODUCT_ID,
            product_name="Widget",
            quantity=2,
            price_at_purchase=24.99,
        )
        assert item.price_at_purchase == 24.99
        assert not hasattr(item, "unit_price"), "OrderItem must NOT have deprecated 'unit_price' field"


# ── Fix 3: Customer flat shipping_* fields ─────────────────────────────────────

class TestFix3CustomerShippingFields:
    """Customer model uses flat shipping_* fields (not nested Address)."""

    def test_customer_model_has_flat_shipping_fields(self):
        """Customer must have flat shipping_street etc., not nested address."""
        c = Customer(
            id=str(uuid.uuid4()),
            name="Jane Doe",
            email="jane@example.com",
            shipping_street="10 Elm St",
            shipping_city="Springfield",
            shipping_state="IL",
            shipping_zip="62701",
            shipping_country="USA",
        )
        assert c.shipping_street == "10 Elm St"
        assert c.shipping_city == "Springfield"
        assert not hasattr(c, "address"), "Customer must NOT have nested 'address' field"

    def test_create_customer_with_shipping_fields(self, mock_db):
        """POST /customers accepts flat shipping_* fields."""
        _, _, mock_cur = mock_db
        mock_cur.fetchone.return_value = (datetime.now(),)
        payload = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "shipping_street": "10 Elm St",
            "shipping_city": "Springfield",
            "shipping_state": "IL",
            "shipping_zip": "62701",
            "shipping_country": "USA",
        }
        with TestClient(app) as client:
            resp = client.post("/customers", json=payload)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["shipping_street"] == "10 Elm St"
        assert data["shipping_city"] == "Springfield"
        assert "address" not in data, "Response must NOT contain nested 'address' key"


# ── Fix 4: Review uses customer_id (not reviewer_name) ─────────────────────────

class TestFix4ReviewCustomerId:
    """Reviews use customer_id instead of reviewer_name."""

    def test_review_create_model_has_customer_id(self):
        """ReviewCreate must require customer_id, not reviewer_name."""
        rc = ReviewCreate(customer_id=CUSTOMER_ID, rating=4)
        assert rc.customer_id == CUSTOMER_ID
        assert not hasattr(rc, "reviewer_name"), "ReviewCreate must NOT have 'reviewer_name'"

    def test_review_model_has_customer_id_and_customer_name(self):
        """Review response model must have customer_id and customer_name."""
        r = Review(
            id=str(uuid.uuid4()),
            product_id=PRODUCT_ID,
            customer_id=CUSTOMER_ID,
            customer_name="Alice",
            rating=5,
            created_at=datetime.now().isoformat(),
        )
        assert r.customer_id == CUSTOMER_ID
        assert r.customer_name == "Alice"
        assert not hasattr(r, "reviewer_name"), "Review must NOT have deprecated 'reviewer_name'"

    def test_create_review_api_accepts_customer_id(self, mock_db):
        """POST /products/{id}/reviews accepts customer_id field."""
        _, _, mock_cur = mock_db
        mock_cur.fetchone.side_effect = [
            (PRODUCT_ID,),       # product exists
            ("Alice",),          # customer name lookup
            (datetime.now(),),   # RETURNING created_at
        ]
        with TestClient(app) as client:
            resp = client.post(
                f"/products/{PRODUCT_ID}/reviews",
                json={"customer_id": CUSTOMER_ID, "rating": 5, "comment": "Great!"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["customer_id"] == CUSTOMER_ID
        assert "reviewer_name" not in data, "Response must NOT contain deprecated 'reviewer_name'"


# ── Fix 5: Invoice list supports order_id query param ─────────────────────────

class TestFix5InvoiceOrderIdFilter:
    """GET /invoices?order_id=... filters by order_id (Fix 5)."""

    def _mock_invoice_row(self):
        return (
            INVOICE_ID, 101, ORDER_ID,
            '{"name": "Alice", "email": "a@b.com"}',
            '[]',
            100.0, None, 0.0, 100.0, datetime.now(),
        )

    def test_list_invoices_filter_by_order_id(self, mock_db):
        """GET /invoices?order_id=... should filter and return matching invoice."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = [self._mock_invoice_row()]

        with TestClient(app) as client:
            resp = client.get(f"/invoices?order_id={ORDER_ID}")

        assert resp.status_code == 200
        invoices = resp.json()
        assert len(invoices) == 1
        assert invoices[0]["order_id"] == ORDER_ID

        # Verify SQL includes order_id filter
        call_args = mock_cur.execute.call_args
        sql = call_args[0][0].lower()
        assert "order_id" in sql, "SQL query must filter by order_id"
        params = call_args[0][1]
        assert ORDER_ID in params, "order_id value must be in SQL params"

    def test_list_invoices_filter_by_customer_id_still_works(self, mock_db):
        """GET /invoices?customer_id=... continues to work (backward compat)."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = [self._mock_invoice_row()]

        with TestClient(app) as client:
            resp = client.get(f"/invoices?customer_id={CUSTOMER_ID}")

        assert resp.status_code == 200
        call_args = mock_cur.execute.call_args
        sql = call_args[0][0].lower()
        assert "customer_id" in sql

    def test_list_invoices_no_filter_returns_all(self, mock_db):
        """GET /invoices with no params still returns all invoices."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = [self._mock_invoice_row()]

        with TestClient(app) as client:
            resp = client.get("/invoices")

        assert resp.status_code == 200
        call_args = mock_cur.execute.call_args
        sql = call_args[0][0].lower()
        assert "where" not in sql, "No WHERE clause when no filters provided"

    def test_list_invoices_combined_filters(self, mock_db):
        """GET /invoices?customer_id=...&order_id=... applies both filters."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = []

        with TestClient(app) as client:
            resp = client.get(f"/invoices?customer_id={CUSTOMER_ID}&order_id={ORDER_ID}")

        assert resp.status_code == 200
        call_args = mock_cur.execute.call_args
        sql = call_args[0][0].lower()
        assert "customer_id" in sql
        assert "order_id" in sql


# ── Fix 6: Dashboard endpoint returns total_sold and low_stock_alerts ─────────

class TestFix6DashboardFieldNames:
    """GET /dashboard returns total_sold and low_stock_alerts (not units_sold / low_stock)."""

    def test_dashboard_api_returns_total_sold(self, mock_db):
        """GET /dashboard top_products must use total_sold, not units_sold."""
        _, _, mock_cur = mock_db
        # Mock: revenue, orders_by_status, top_products, low_stock_alerts
        mock_cur.fetchone.return_value = (5000.0,)
        mock_cur.fetchall.side_effect = [
            [("pending", 3), ("delivered", 10)],   # orders_by_status
            [(str(uuid.uuid4()), "Widget", 42)],    # top_products
            [],                                     # low_stock_alerts
        ]
        with TestClient(app) as client:
            resp = client.get("/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "top_products" in data
        assert len(data["top_products"]) == 1
        assert "total_sold" in data["top_products"][0], "Must use 'total_sold', not 'units_sold'"
        assert data["top_products"][0]["total_sold"] == 42
        assert "units_sold" not in data["top_products"][0], "Must NOT use deprecated 'units_sold'"

    def test_dashboard_api_returns_low_stock_alerts(self, mock_db):
        """GET /dashboard must return low_stock_alerts key, not low_stock."""
        _, _, mock_cur = mock_db
        mock_cur.fetchone.return_value = (0.0,)
        mock_cur.fetchall.side_effect = [
            [],   # orders_by_status
            [],   # top_products
            [(str(uuid.uuid4()), "Gadget", 2, 5, str(uuid.uuid4()), "Supplier Co", "s@co.com")],  # low_stock
        ]
        with TestClient(app) as client:
            resp = client.get("/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "low_stock_alerts" in data, "Must use 'low_stock_alerts', not 'low_stock'"
        assert "low_stock" not in data, "Must NOT use deprecated 'low_stock' key"


# ── Fix 7: CouponValidationResult uses error (not message) ────────────────────

class TestFix7CouponErrorField:
    """CouponValidationResult uses error and final_total (not message)."""

    def test_coupon_result_has_error_field(self):
        """CouponValidationResult must have 'error', not 'message'."""
        result = CouponValidationResult(
            valid=False,
            error="Coupon has expired",
        )
        assert result.error == "Coupon has expired"
        assert not hasattr(result, "message"), "CouponValidationResult must NOT have deprecated 'message' field"

    def test_coupon_result_has_final_total_field(self):
        """CouponValidationResult must include final_total."""
        result = CouponValidationResult(
            valid=True,
            discount_amount=10.0,
            final_total=90.0,
        )
        assert result.final_total == 90.0
