import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

from app.main import app
from app.models import DiscountType


@pytest.fixture
def mock_db():
    with patch("app.main.SimpleConnectionPool") as mock_pool:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool_inst = MagicMock()
        mock_pool.return_value = mock_pool_inst
        mock_pool_inst.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        yield mock_pool, mock_conn, mock_cur


@pytest.fixture
def client(mock_db):
    with TestClient(app) as client:
        yield client


def test_create_coupon(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = (datetime.now(),)

    response = client.post("/coupons", json={
        "code": "TEST50",
        "discount_type": "percentage",
        "discount_value": 50,
        "min_order_amount": 100,
        "max_uses": 5
    })

    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "TEST50"
    assert data["discount_value"] == 50.0


def test_list_coupons(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchall.return_value = [
        ("123", "SAVE10", "fixed", 10.0, 0.0, 0, 0, True, None, None)
    ]

    response = client.get("/coupons")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["code"] == "SAVE10"


def test_validate_coupon_percentage(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = ("123", "SAVE20", "percentage", 20.0, 50.0, 10, 2, True, None, None)

    response = client.post("/coupons/validate", json={
        "code": "SAVE20",
        "cart_total": 100.0
    })

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["discount_amount"] == 20.0
    assert data["final_total"] == 80.0


def test_validate_coupon_fixed(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = ("123", "MINUS15", "fixed", 15.0, 0.0, 0, 0, True, None, None)

    response = client.post("/coupons/validate", json={
        "code": "MINUS15",
        "cart_total": 50.0
    })

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["discount_amount"] == 15.0
    assert data["final_total"] == 35.0


def test_validate_coupon_expired(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    past_date = datetime.now(timezone.utc) - timedelta(days=1)
    mock_cur.fetchone.return_value = ("123", "OLDCODE", "fixed", 10.0, 0.0, 0, 0, True, past_date, None)

    response = client.post("/coupons/validate", json={
        "code": "OLDCODE",
        "cart_total": 100.0
    })

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "expired" in data["error"].lower()


def test_validate_coupon_min_amount(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = ("123", "BIGSPEND", "fixed", 20.0, 100.0, 0, 0, True, None, None)

    response = client.post("/coupons/validate", json={
        "code": "BIGSPEND",
        "cart_total": 50.0
    })

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "minimum" in data["error"].lower()


def test_validate_coupon_usage_limit(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = ("123", "LIMIT5", "fixed", 10.0, 0.0, 5, 5, True, None, None)

    response = client.post("/coupons/validate", json={
        "code": "LIMIT5",
        "cart_total": 100.0
    })

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "limit" in data["error"].lower()


def test_validate_coupon_inactive(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = ("123", "INACTIVE", "fixed", 10.0, 0.0, 0, 0, False, None, None)

    response = client.post("/coupons/validate", json={
        "code": "INACTIVE",
        "cart_total": 100.0
    })

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "active" in data["error"].lower()


def test_validate_coupon_not_found(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = None

    response = client.post("/coupons/validate", json={
        "code": "NOTEXIST",
        "cart_total": 100.0
    })

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "not found" in data["error"].lower()


def test_delete_coupon(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = ("123",)

    response = client.delete("/coupons/123")
    assert response.status_code == 204


def test_delete_coupon_not_found(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = None

    response = client.delete("/coupons/999")
    assert response.status_code == 404


def test_order_creation_without_coupon(client, mock_db):
    """Backwards compatibility: orders without coupons still work."""
    _, mock_conn, mock_cur = mock_db

    # Mock: customer exists, product stock deduction succeeds, order insert
    mock_cur.fetchone.side_effect = [
        ("cust1",),                           # customer check
        ("prod1", "Widget", 50.0, 8),         # stock deduction RETURNING
        (datetime.now(),),                     # order created_at
    ]

    response = client.post("/orders", json={
        "items": [{"product_id": "prod1", "quantity": 2}],
        "customer_id": "cust1"
    })

    assert response.status_code == 201
    data = response.json()
    assert data["coupon_code"] is None
    assert data["discount_amount"] == 0.0
