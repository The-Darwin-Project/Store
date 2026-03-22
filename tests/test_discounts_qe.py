# @ai-rules:
# 1. [Pattern]: QE integration tests for product-level discounts (evt-840d313d).
# 2. [Constraint]: Uses TestClient + mocked DB pool -- no real DB required.
# 3. [Gotcha]: fetchone side_effect order must match exact query sequence in routes.
# 4. [Gotcha]: Product UPDATE RETURNING now returns 6 columns: id, name, price, stock, sale_price, discount_percent.
"""
QE Integration Tests: Product-Level Discounts (evt-840d313d)

Coverage:
  - Effective price calculation (sale_price, discount_percent, stacking, edge cases)
  - Product API: GET/POST/PUT/PATCH with discount fields
  - Order creation uses effective discounted price
  - Coupon stacking: product discount applied first, coupon on discounted subtotal
  - Admin: clear discounts via PATCH (null values)
  - Frontend helper equivalents: getEffectivePrice, hasDiscount logic
"""

import uuid
import sys
import os
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from app.models import effective_price, Product, ProductCreate, ProductUpdate
from app.main import app

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

PRODUCT_ID = str(uuid.uuid4())
CUSTOMER_ID = str(uuid.uuid4())
COUPON_ID = str(uuid.uuid4())


def _make_pool_mock(mock_pool_cls):
    """Return (mock_pool, mock_conn, mock_cursor) wired up correctly."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    return mock_pool, mock_conn, mock_cursor


def _product_row(
    product_id=None,
    name="Widget",
    price=100.0,
    stock=10,
    sku="W1",
    image_data=None,
    description="A widget",
    supplier_id=None,
    reorder_threshold=10,
    sale_price=None,
    discount_percent=None,
):
    """Build a product row tuple matching SELECT column order in products.py."""
    return (
        product_id or PRODUCT_ID,
        name, price, stock, sku, image_data, description,
        supplier_id, reorder_threshold, sale_price, discount_percent,
    )


def _update_returning_row(
    product_id=None,
    name="Widget",
    price=100.0,
    stock=8,
    sale_price=None,
    discount_percent=None,
):
    """Build UPDATE RETURNING row for order creation (6 columns)."""
    return (product_id or PRODUCT_ID, name, price, stock, sale_price, discount_percent)


def _coupon_row(
    coupon_id=None,
    code="SAVE10",
    discount_type="percentage",
    discount_value=10.0,
    min_order_amount=0.0,
    max_uses=0,
    current_uses=0,
    is_active=True,
    expires_at=None,
    created_at=None,
):
    """Build a coupon row matching _COUPON_COLUMNS in coupons.py."""
    return (
        coupon_id or COUPON_ID,
        code, discount_type, discount_value,
        min_order_amount, max_uses, current_uses,
        is_active, expires_at, created_at,
    )


# ---------------------------------------------------------------------------
# Section 1: Effective price -- additional QE edge cases
# ---------------------------------------------------------------------------

class TestEffectivePriceQE:
    """Additional edge cases not covered by Developer's tests."""

    def test_sale_price_zero_overrides_discount_percent(self):
        """Sale price of 0 takes precedence over discount_percent (free item)."""
        assert effective_price(50.0, 0.0, 50) == 0.0

    def test_discount_percent_boundary_just_below_100(self):
        assert effective_price(100.0, None, 99.9) == round(100.0 * 0.001, 2)

    def test_sale_price_higher_than_original_is_allowed(self):
        """No business rule prevents sale_price > price (markup scenario)."""
        assert effective_price(50.0, 75.0, None) == 75.0

    def test_rounding_half_cent(self):
        """Verify round-half-even doesn't produce unexpected results."""
        result = effective_price(10.0, None, 33.33)
        # 10 * (1 - 0.3333) = 6.667 -> rounds to 6.67
        assert result == round(10.0 * (1 - 33.33 / 100), 2)

    def test_small_price_with_large_percent(self):
        """Floating-point safety on small values."""
        result = effective_price(0.01, None, 50)
        assert result == round(0.01 * 0.5, 2)

    def test_no_discount_returns_exact_price(self):
        """No rounding applied when no discount."""
        assert effective_price(9.99, None, None) == 9.99

    def test_sale_price_exact_match(self):
        """sale_price == price is still valid (0% effective discount)."""
        assert effective_price(99.99, 99.99, None) == 99.99


# ---------------------------------------------------------------------------
# Section 2: Frontend helper logic equivalents (Python)
# ---------------------------------------------------------------------------

class TestFrontendHelperEquivalents:
    """
    Verify the frontend getEffectivePrice / hasDiscount logic matches backend.
    Python equivalents translated from frontend/src/types/index.ts.
    """

    def _get_effective_price(self, product: dict) -> float:
        """Python equivalent of getEffectivePrice() in index.ts."""
        if product.get("sale_price") is not None:
            return product["sale_price"]
        dp = product.get("discount_percent")
        if dp is not None:
            return round(product["price"] * (1 - dp / 100) * 100) / 100
        return product["price"]

    def _has_discount(self, product: dict) -> bool:
        """Python equivalent of hasDiscount() in index.ts."""
        return (
            product.get("sale_price") is not None
            or (product.get("discount_percent") is not None and product["discount_percent"] > 0)
        )

    def test_no_discount_product(self):
        p = {"price": 99.99, "sale_price": None, "discount_percent": None}
        assert not self._has_discount(p)
        assert self._get_effective_price(p) == 99.99

    def test_sale_price_product(self):
        p = {"price": 99.99, "sale_price": 79.99, "discount_percent": None}
        assert self._has_discount(p)
        assert self._get_effective_price(p) == 79.99

    def test_discount_percent_product(self):
        p = {"price": 100.0, "sale_price": None, "discount_percent": 20}
        assert self._has_discount(p)
        assert self._get_effective_price(p) == 80.0

    def test_zero_discount_not_has_discount(self):
        """0% discount_percent = no discount badge shown."""
        p = {"price": 50.0, "sale_price": None, "discount_percent": 0}
        assert not self._has_discount(p)

    def test_frontend_backend_price_agreement(self):
        """Frontend getEffectivePrice must match backend effective_price for all cases."""
        cases = [
            (99.99, None, None),
            (99.99, 79.99, None),
            (100.0, None, 20.0),
            (100.0, 79.99, 20.0),  # sale_price wins
            (50.0, 0.0, None),
        ]
        for price, sale_price, discount_percent in cases:
            backend = effective_price(price, sale_price, discount_percent)
            frontend = self._get_effective_price({
                "price": price, "sale_price": sale_price,
                "discount_percent": discount_percent,
            })
            assert backend == frontend, (
                f"Mismatch for price={price}, sale_price={sale_price}, "
                f"discount_percent={discount_percent}: backend={backend}, frontend={frontend}"
            )


# ---------------------------------------------------------------------------
# Section 3: Product API -- GET includes discount fields
# ---------------------------------------------------------------------------

class TestProductAPIDiscountFields:

    @patch("app.main.SimpleConnectionPool")
    def test_get_product_returns_sale_price(self, mock_pool_cls):
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.return_value = _product_row(sale_price=79.99)

        with TestClient(app) as client:
            resp = client.get(f"/products/{PRODUCT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sale_price"] == 79.99
        assert data["discount_percent"] is None

    @patch("app.main.SimpleConnectionPool")
    def test_get_product_returns_discount_percent(self, mock_pool_cls):
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.return_value = _product_row(discount_percent=25.0)

        with TestClient(app) as client:
            resp = client.get(f"/products/{PRODUCT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sale_price"] is None
        assert data["discount_percent"] == 25.0

    @patch("app.main.SimpleConnectionPool")
    def test_get_product_no_discount_fields_null(self, mock_pool_cls):
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.return_value = _product_row()

        with TestClient(app) as client:
            resp = client.get(f"/products/{PRODUCT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sale_price"] is None
        assert data["discount_percent"] is None

    @patch("app.main.SimpleConnectionPool")
    def test_create_product_with_sale_price(self, mock_pool_cls):
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        # create_product returns the created product row
        mock_cursor.fetchone.return_value = _product_row(
            sale_price=79.99, discount_percent=None
        )

        payload = {
            "name": "Widget", "price": 99.99, "sku": "W1", "stock": 10,
            "sale_price": 79.99,
        }
        with TestClient(app) as client:
            resp = client.post("/products", json=payload)

        assert resp.status_code == 201
        data = resp.json()
        assert data["sale_price"] == 79.99

    @patch("app.main.SimpleConnectionPool")
    def test_create_product_with_discount_percent(self, mock_pool_cls):
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.return_value = _product_row(discount_percent=15.0)

        payload = {
            "name": "Widget", "price": 100.0, "sku": "W2", "stock": 5,
            "discount_percent": 15.0,
        }
        with TestClient(app) as client:
            resp = client.post("/products", json=payload)

        assert resp.status_code == 201
        assert resp.json()["discount_percent"] == 15.0

    @patch("app.main.SimpleConnectionPool")
    def test_patch_product_sets_sale_price(self, mock_pool_cls):
        """PATCH can set sale_price on existing product (admin clears, then sets)."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        # GET existing product, then UPDATE
        mock_cursor.fetchone.side_effect = [
            _product_row(),  # existing product fetch
            _product_row(sale_price=69.99),  # after PATCH
        ]

        with TestClient(app) as client:
            resp = client.patch(f"/products/{PRODUCT_ID}", json={"sale_price": 69.99})

        assert resp.status_code == 200
        assert resp.json()["sale_price"] == 69.99

    @patch("app.main.SimpleConnectionPool")
    def test_patch_product_clears_sale_price(self, mock_pool_cls):
        """Admin can clear sale_price by PATCHing with null."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            _product_row(sale_price=79.99),  # existing product
            _product_row(sale_price=None),   # after clearing
        ]

        with TestClient(app) as client:
            resp = client.patch(f"/products/{PRODUCT_ID}", json={"sale_price": None})

        assert resp.status_code == 200
        assert resp.json()["sale_price"] is None

    @patch("app.main.SimpleConnectionPool")
    def test_patch_product_clears_discount_percent(self, mock_pool_cls):
        """Admin can clear discount_percent by PATCHing with null."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            _product_row(discount_percent=20.0),  # existing product
            _product_row(discount_percent=None),  # after clearing
        ]

        with TestClient(app) as client:
            resp = client.patch(f"/products/{PRODUCT_ID}", json={"discount_percent": None})

        assert resp.status_code == 200
        assert resp.json()["discount_percent"] is None

    @patch("app.main.SimpleConnectionPool")
    def test_create_product_invalid_negative_sale_price(self, mock_pool_cls):
        """API rejects negative sale_price at validation layer."""
        _make_pool_mock(mock_pool_cls)
        payload = {"name": "Widget", "price": 100.0, "sku": "W3", "sale_price": -5.0}
        with TestClient(app) as client:
            resp = client.post("/products", json=payload)
        assert resp.status_code == 422

    @patch("app.main.SimpleConnectionPool")
    def test_create_product_invalid_discount_over_100(self, mock_pool_cls):
        """API rejects discount_percent > 100."""
        _make_pool_mock(mock_pool_cls)
        payload = {"name": "Widget", "price": 100.0, "sku": "W4", "discount_percent": 150.0}
        with TestClient(app) as client:
            resp = client.post("/products", json=payload)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Section 4: Order creation uses effective price
# ---------------------------------------------------------------------------

class TestOrderUsesEffectivePrice:
    """Verify order creation applies product discounts at line-item level."""

    def _order_payload(self, quantity=2):
        return {
            "items": [{"product_id": PRODUCT_ID, "quantity": quantity}],
            "customer_id": CUSTOMER_ID,
        }

    @patch("app.main.SimpleConnectionPool")
    def test_order_with_sale_price_uses_sale_price(self, mock_pool_cls):
        """Order total uses sale_price when set (e.g., $79.99 not $99.99)."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),  # customer check
            _update_returning_row(price=99.99, stock=8, sale_price=79.99, discount_percent=None),
            (datetime.now(),),  # created_at
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_payload(quantity=2))

        assert resp.status_code == 201
        data = resp.json()
        # 2 * 79.99 = 159.98
        assert data["total_amount"] == pytest.approx(159.98, abs=0.01)
        assert data["items"][0]["price_at_purchase"] == pytest.approx(79.99, abs=0.01)

    @patch("app.main.SimpleConnectionPool")
    def test_order_with_discount_percent_applies_discount(self, mock_pool_cls):
        """Order uses price * (1 - discount_percent/100) when discount_percent set."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),
            _update_returning_row(price=50.0, stock=8, sale_price=None, discount_percent=20.0),
            (datetime.now(),),
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_payload(quantity=3))

        assert resp.status_code == 201
        data = resp.json()
        # 50 * 0.8 = 40.0, 3 * 40.0 = 120.0
        assert data["total_amount"] == pytest.approx(120.0, abs=0.01)
        assert data["items"][0]["price_at_purchase"] == pytest.approx(40.0, abs=0.01)

    @patch("app.main.SimpleConnectionPool")
    def test_order_with_both_sale_price_wins(self, mock_pool_cls):
        """When both discount fields set, sale_price wins (order uses sale_price)."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),
            _update_returning_row(price=100.0, stock=5, sale_price=79.99, discount_percent=30.0),
            (datetime.now(),),
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_payload(quantity=1))

        assert resp.status_code == 201
        data = resp.json()
        # sale_price=79.99 wins over 30% off (which would be 70.0)
        assert data["items"][0]["price_at_purchase"] == pytest.approx(79.99, abs=0.01)

    @patch("app.main.SimpleConnectionPool")
    def test_order_without_discount_uses_original_price(self, mock_pool_cls):
        """Products without discounts use original price (backward compat)."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),
            _update_returning_row(price=25.50, stock=9, sale_price=None, discount_percent=None),
            (datetime.now(),),
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_payload(quantity=4))

        assert resp.status_code == 201
        data = resp.json()
        assert data["total_amount"] == pytest.approx(102.0, abs=0.01)
        assert data["items"][0]["price_at_purchase"] == pytest.approx(25.50, abs=0.01)

    @patch("app.main.SimpleConnectionPool")
    def test_order_with_100_percent_discount(self, mock_pool_cls):
        """100% discount yields price_at_purchase=0, total=0."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),
            _update_returning_row(price=50.0, stock=9, sale_price=None, discount_percent=100.0),
            (datetime.now(),),
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_payload(quantity=2))

        assert resp.status_code == 201
        data = resp.json()
        assert data["items"][0]["price_at_purchase"] == pytest.approx(0.0, abs=0.01)
        assert data["total_amount"] == pytest.approx(0.0, abs=0.01)

    @patch("app.main.SimpleConnectionPool")
    def test_order_multiple_items_different_discounts(self, mock_pool_cls):
        """Multi-item order: each item uses its own effective price."""
        product_id_2 = str(uuid.uuid4())
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),  # customer check
            _update_returning_row(price=100.0, stock=8, sale_price=79.99, discount_percent=None),
            _update_returning_row(product_id=product_id_2, price=50.0, stock=7, sale_price=None, discount_percent=20.0),
            (datetime.now(),),
        ]

        payload = {
            "items": [
                {"product_id": PRODUCT_ID, "quantity": 1},
                {"product_id": product_id_2, "quantity": 2},
            ],
            "customer_id": CUSTOMER_ID,
        }
        with TestClient(app) as client:
            resp = client.post("/orders", json=payload)

        assert resp.status_code == 201
        data = resp.json()
        # item1: 1 * 79.99 = 79.99; item2: 2 * 40.0 = 80.0; total = 159.99
        assert data["total_amount"] == pytest.approx(159.99, abs=0.01)


# ---------------------------------------------------------------------------
# Section 5: Coupon stacking -- product discount first, coupon second
# ---------------------------------------------------------------------------

class TestCouponStackingWithProductDiscount:
    """
    Verify: product discounts reduce line-item prices first.
    Coupon applies to the already-discounted subtotal.
    """

    def _order_with_coupon(self, quantity, coupon_code):
        return {
            "items": [{"product_id": PRODUCT_ID, "quantity": quantity}],
            "customer_id": CUSTOMER_ID,
            "coupon_code": coupon_code,
        }

    @patch("app.main.SimpleConnectionPool")
    def test_percentage_coupon_on_discounted_subtotal(self, mock_pool_cls):
        """
        Product: price=100, sale_price=80 → line item = 80 (qty 2) = 160.
        Coupon: 10% off → discount = 16.0, final = 144.0.
        """
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),  # customer check
            _update_returning_row(price=100.0, stock=8, sale_price=80.0, discount_percent=None),
            _coupon_row(discount_type="percentage", discount_value=10.0),  # coupon lookup
            (COUPON_ID,),  # coupon uses update RETURNING id
            (datetime.now(),),  # created_at
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_with_coupon(2, "SAVE10"))

        assert resp.status_code == 201
        data = resp.json()
        assert data["discount_amount"] == pytest.approx(16.0, abs=0.01)
        assert data["total_amount"] == pytest.approx(144.0, abs=0.01)
        assert data["coupon_code"] == "SAVE10"

    @patch("app.main.SimpleConnectionPool")
    def test_fixed_coupon_on_discounted_subtotal(self, mock_pool_cls):
        """
        Product: price=50, discount_percent=20 → line item = 40 (qty 3) = 120.
        Coupon: $15 fixed off → final = 105.0.
        """
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),
            _update_returning_row(price=50.0, stock=8, sale_price=None, discount_percent=20.0),
            _coupon_row(discount_type="fixed", discount_value=15.0),
            (COUPON_ID,),
            (datetime.now(),),
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_with_coupon(3, "FLAT15"))

        assert resp.status_code == 201
        data = resp.json()
        assert data["discount_amount"] == pytest.approx(15.0, abs=0.01)
        assert data["total_amount"] == pytest.approx(105.0, abs=0.01)

    @patch("app.main.SimpleConnectionPool")
    def test_stacking_order_correct_coupon_gets_discounted_base(self, mock_pool_cls):
        """
        Key correctness check: coupon % discount is applied to the DISCOUNTED subtotal,
        not the original price. Verify by comparing expected vs actual.

        Product: price=100, discount_percent=50 → effective=50 (qty 2) → subtotal=100.
        Coupon: 20% → should discount 100 * 0.20 = 20, final = 80.
        (NOT 200 * 0.20 = 40 off original).
        """
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),
            _update_returning_row(price=100.0, stock=8, sale_price=None, discount_percent=50.0),
            _coupon_row(discount_type="percentage", discount_value=20.0),
            (COUPON_ID,),
            (datetime.now(),),
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_with_coupon(2, "BIG20"))

        assert resp.status_code == 201
        data = resp.json()
        # Discounted subtotal: 2 * 50 = 100. Coupon 20% of 100 = 20. Final = 80.
        assert data["discount_amount"] == pytest.approx(20.0, abs=0.01)
        assert data["total_amount"] == pytest.approx(80.0, abs=0.01)

    @patch("app.main.SimpleConnectionPool")
    def test_no_product_discount_coupon_applies_to_full_price(self, mock_pool_cls):
        """Without product discount, coupon applies to full-price subtotal (baseline)."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),
            _update_returning_row(price=100.0, stock=8, sale_price=None, discount_percent=None),
            _coupon_row(discount_type="percentage", discount_value=10.0),
            (COUPON_ID,),
            (datetime.now(),),
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_with_coupon(2, "SAVE10"))

        assert resp.status_code == 201
        data = resp.json()
        # No product discount: subtotal = 200. Coupon 10% = 20. Final = 180.
        assert data["discount_amount"] == pytest.approx(20.0, abs=0.01)
        assert data["total_amount"] == pytest.approx(180.0, abs=0.01)

    @patch("app.main.SimpleConnectionPool")
    def test_coupon_capped_at_order_total(self, mock_pool_cls):
        """Fixed coupon larger than order total: total capped at 0."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            (CUSTOMER_ID,),
            _update_returning_row(price=20.0, stock=8, sale_price=10.0, discount_percent=None),
            _coupon_row(discount_type="fixed", discount_value=100.0),  # $100 off $10
            (COUPON_ID,),
            (datetime.now(),),
        ]

        with TestClient(app) as client:
            resp = client.post("/orders", json=self._order_with_coupon(1, "MEGA"))

        assert resp.status_code == 201
        data = resp.json()
        # Fixed $100 off $10 → capped at 10. Final = 0.
        assert data["total_amount"] == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# Section 6: Admin can set and clear discounts
# ---------------------------------------------------------------------------

class TestAdminDiscountManagement:
    """Verify admin can update and clear product discount fields via PUT/PATCH."""

    @patch("app.main.SimpleConnectionPool")
    def test_put_product_sets_both_discount_fields(self, mock_pool_cls):
        """PUT (full update) can set both sale_price and discount_percent."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.return_value = _product_row(sale_price=49.99, discount_percent=10.0)

        payload = {
            "name": "Widget", "price": 59.99, "sku": "W1", "stock": 20,
            "sale_price": 49.99, "discount_percent": 10.0,
        }
        with TestClient(app) as client:
            resp = client.put(f"/products/{PRODUCT_ID}", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["sale_price"] == 49.99
        assert data["discount_percent"] == 10.0

    @patch("app.main.SimpleConnectionPool")
    def test_put_product_clears_discounts(self, mock_pool_cls):
        """PUT with null discount fields clears them."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.return_value = _product_row(sale_price=None, discount_percent=None)

        payload = {
            "name": "Widget", "price": 59.99, "sku": "W1", "stock": 20,
            "sale_price": None, "discount_percent": None,
        }
        with TestClient(app) as client:
            resp = client.put(f"/products/{PRODUCT_ID}", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["sale_price"] is None
        assert data["discount_percent"] is None

    @patch("app.main.SimpleConnectionPool")
    def test_patch_adds_discount_to_existing_product(self, mock_pool_cls):
        """PATCH only sets discount fields, leaves price unchanged."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            _product_row(price=99.99),  # existing (no discount)
            _product_row(price=99.99, discount_percent=15.0),  # after patch
        ]

        with TestClient(app) as client:
            resp = client.patch(f"/products/{PRODUCT_ID}", json={"discount_percent": 15.0})

        assert resp.status_code == 200
        data = resp.json()
        assert data["price"] == 99.99  # unchanged
        assert data["discount_percent"] == 15.0

    @patch("app.main.SimpleConnectionPool")
    def test_patch_switches_from_sale_price_to_discount_percent(self, mock_pool_cls):
        """Admin can change from sale_price to discount_percent via PATCH."""
        _, mock_conn, mock_cursor = _make_pool_mock(mock_pool_cls)
        mock_cursor.fetchone.side_effect = [
            _product_row(sale_price=79.99),  # existing (has sale_price)
            _product_row(sale_price=None, discount_percent=25.0),  # after patch
        ]

        with TestClient(app) as client:
            resp = client.patch(
                f"/products/{PRODUCT_ID}",
                json={"sale_price": None, "discount_percent": 25.0}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["sale_price"] is None
        assert data["discount_percent"] == 25.0
