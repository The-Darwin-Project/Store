# tests/test_coupon_redemption.py
# @ai-rules:
# 1. [Scope]: Tests for POST /coupons/redeem on the inventory service (feat/coupon-redemption-tracking).
# 2. [Pattern]: Mock request.app.state.db_pool -- NOT module-level globals. See test_split_services_evt_fb71d51d.py.
# 3. [Gotcha]: A single mocked cursor backs every `with conn.cursor()` in the request; fetchone()
#    side_effect must be ordered to match: order lookup, coupon lookup, redemption insert, atomic increment.
"""Tests for POST /coupons/redeem: idempotency, max_uses race guard, order validity, error handling."""

import os
import sys
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _REPO_ROOT)

from src.inventory.main import app  # noqa: E402

ORDER_ID = str(uuid.uuid4())
COUPON_ID = str(uuid.uuid4())


def make_mock_pool(cursor_mock: MagicMock) -> MagicMock:
    """Build a mock psycopg2 connection pool that yields the given cursor mock."""
    conn = MagicMock()
    pool = MagicMock()
    pool.getconn.return_value = conn
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor_mock)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return pool


def coupon_row(max_uses=5, current_uses=2, is_active=True, min_order_amount=0.0):
    """A coupons row matching _row_to_coupon's column order."""
    return (COUPON_ID, "SAVE10", "fixed", 10.0, min_order_amount, max_uses, current_uses, is_active, None, None)


class TestCouponRedeem:
    def setup_method(self):
        from src.inventory.main import app as inv_app
        self.app = inv_app
        self.client = TestClient(inv_app, raise_server_exceptions=False)

    def _set_pool(self, cursor_mock):
        self.app.state.db_pool = make_mock_pool(cursor_mock)

    def _redeem(self, **overrides):
        payload = {"code": "SAVE10", "cart_total": 100.0, "order_id": ORDER_ID}
        payload.update(overrides)
        return self.client.post("/coupons/redeem", json=payload)

    def test_redeem_success_increments_usage_atomically(self):
        """Happy path: order valid, coupon valid, insert + atomic increment both succeed."""
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("pending",),                 # order status lookup
            coupon_row(),                  # coupon lookup (validate_coupon_for_cart)
            (str(uuid.uuid4()),),          # coupon_redemptions INSERT ... RETURNING id
            (3,),                           # atomic UPDATE ... RETURNING current_uses
        ]
        self._set_pool(cur)

        resp = self._redeem()
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["redeemed"] is True
        assert data["coupon"]["current_uses"] == 3
        assert data["discount_amount"] == 10.0
        assert data["final_total"] == 90.0

        insert_call = cur.execute.call_args_list[-2]
        assert "ON CONFLICT (coupon_id, order_id) DO NOTHING" in insert_call.args[0]
        update_call = cur.execute.call_args_list[-1]
        assert "current_uses < max_uses" in update_call.args[0]

    def test_redeem_rejects_fabricated_order_id(self):
        """order_id with no matching order is rejected before touching the coupon."""
        cur = MagicMock()
        cur.fetchone.side_effect = [None]  # order lookup finds nothing
        self._set_pool(cur)

        resp = self._redeem(order_id=str(uuid.uuid4()))
        assert resp.status_code == 200
        data = resp.json()
        assert data["redeemed"] is False
        assert "not found" in data["error"].lower()

    def test_redeem_rejects_cancelled_order(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [("cancelled",)]
        self._set_pool(cur)

        resp = self._redeem()
        data = resp.json()
        assert data["redeemed"] is False
        assert "cancelled" in data["error"].lower()

    def test_redeem_is_idempotent_for_same_order(self):
        """A retried redemption for an order already recorded is rejected, not double-counted."""
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("pending",),
            coupon_row(),
            None,  # INSERT ... ON CONFLICT DO NOTHING found an existing row -> no insert
        ]
        self._set_pool(cur)

        resp = self._redeem()
        data = resp.json()
        assert data["redeemed"] is False
        assert "already redeemed" in data["error"].lower()

        # Usage must not be touched once idempotency blocks the request.
        for call in cur.execute.call_args_list:
            assert "UPDATE coupons SET current_uses" not in call.args[0]

    def test_redeem_enforces_max_uses_even_if_precheck_passed(self):
        """Guarded atomic UPDATE is the source of truth even when the coupon read looked fine."""
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("pending",),
            coupon_row(max_uses=5, current_uses=4),   # looks fine at read time
            (str(uuid.uuid4()),),                       # redemption insert succeeds
            None,                                        # but atomic UPDATE finds the limit was hit
        ]
        self._set_pool(cur)

        resp = self._redeem()
        data = resp.json()
        assert data["redeemed"] is False
        assert "limit reached" in data["error"].lower()

    def test_redeem_unexpected_db_error_rolls_back_and_returns_500(self):
        """A non-HTTPException failure is caught, rolls back, and doesn't poison the pool."""
        cur = MagicMock()
        cur.execute.side_effect = Exception("connection reset by peer")
        pool = make_mock_pool(cur)
        self.app.state.db_pool = pool

        resp = self._redeem()
        assert resp.status_code == 500
        assert "Coupon redemption failed" in resp.json()["detail"]
        pool.getconn.return_value.rollback.assert_called_once()
        pool.getconn.return_value.commit.assert_not_called()
