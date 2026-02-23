import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

MOCK_ORDER_ID = "00000000-0000-0000-0000-000000000001"
MOCK_CUSTOMER_ID = "11111111-1111-1111-1111-111111111111"

@patch("app.main.SimpleConnectionPool")
def test_update_order_status_valid(mock_pool_cls):
    """Test valid transitions like pending -> processing -> shipped -> delivered."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Current status: pending
    mock_cursor.fetchone.side_effect = [
        (MOCK_ORDER_ID, "2023-01-01", 100.0, "pending", MOCK_CUSTOMER_ID),
        (MOCK_ORDER_ID, "2023-01-01", 100.0, "processing", MOCK_CUSTOMER_ID, None, 0.0),
    ]

    with TestClient(app) as client:
        response = client.patch(f"/orders/{MOCK_ORDER_ID}/status", json={"status": "processing"})
        assert response.status_code == 200
        assert response.json()["status"] == "processing"


@patch("app.main.SimpleConnectionPool")
def test_update_order_status_invalid(mock_pool_cls):
    """Test invalid transitions like delivered -> pending."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Current status: delivered
    mock_cursor.fetchone.side_effect = [
        (MOCK_ORDER_ID, "2023-01-01", 100.0, "delivered", MOCK_CUSTOMER_ID),
    ]

    with TestClient(app) as client:
        response = client.patch(f"/orders/{MOCK_ORDER_ID}/status", json={"status": "pending"})
        assert response.status_code == 400
        assert "Cannot transition from 'delivered' to 'pending'" in response.json()["detail"]


@patch("app.main.SimpleConnectionPool")
def test_update_order_status_cancel(mock_pool_cls):
    """Test cancelling an order restores stock for each order item."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    product_a = "aaaa-aaaa"
    product_b = "bbbb-bbbb"

    # fetchone #1: current order row (processing)
    # fetchall: order_items for stock restoration
    # fetchone #2: RETURNING row after status UPDATE
    mock_cursor.fetchone.side_effect = [
        (MOCK_ORDER_ID, "2023-01-01", 100.0, "processing", MOCK_CUSTOMER_ID, None, 0.0),
        (MOCK_ORDER_ID, "2023-01-01", 100.0, "cancelled", MOCK_CUSTOMER_ID, None, 0.0),
    ]
    mock_cursor.fetchall.return_value = [
        (product_a, 2),
        (product_b, 5),
    ]

    with TestClient(app) as client:
        response = client.patch(f"/orders/{MOCK_ORDER_ID}/status", json={"status": "cancelled"})
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    # Verify stock restoration queries were executed
    executed_queries = [call[0][0] for call in mock_cursor.execute.call_args_list]
    stock_updates = [q for q in executed_queries if "stock = stock +" in q]
    assert len(stock_updates) == 2, f"Expected 2 stock restoration queries, got {len(stock_updates)}"


@patch("app.main.SimpleConnectionPool")
def test_update_order_status_returned(mock_pool_cls):
    """Test delivered -> returned restores stock for each order item."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    product_a = "aaaa-aaaa"
    product_b = "bbbb-bbbb"

    mock_cursor.fetchone.side_effect = [
        (MOCK_ORDER_ID, "2023-01-01", 100.0, "delivered", MOCK_CUSTOMER_ID),
        (MOCK_ORDER_ID, "2023-01-01", 100.0, "returned", MOCK_CUSTOMER_ID, None, 0.0),
    ]
    mock_cursor.fetchall.return_value = [
        (product_a, 3),
        (product_b, 1),
    ]

    with TestClient(app) as client:
        response = client.patch(f"/orders/{MOCK_ORDER_ID}/status", json={"status": "returned"})
        assert response.status_code == 200
        assert response.json()["status"] == "returned"

    # Verify stock restoration queries were executed
    executed_queries = [call[0][0] for call in mock_cursor.execute.call_args_list]
    stock_updates = [q for q in executed_queries if "stock = stock +" in q]
    assert len(stock_updates) == 2, f"Expected 2 stock restoration queries, got {len(stock_updates)}"


@patch("app.main.SimpleConnectionPool")
def test_update_order_status_returned_terminal(mock_pool_cls):
    """Test that returned is a terminal state — cannot transition further."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchone.side_effect = [
        (MOCK_ORDER_ID, "2023-01-01", 100.0, "returned", MOCK_CUSTOMER_ID, None, 0.0),
    ]

    with TestClient(app) as client:
        response = client.patch(f"/orders/{MOCK_ORDER_ID}/status", json={"status": "pending"})
        assert response.status_code == 400
        assert "Cannot transition from 'returned' to 'pending'" in response.json()["detail"]


@patch("app.main.SimpleConnectionPool")
def test_update_order_status_not_found(mock_pool_cls):
    """Test 404 on unknown order."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchone.return_value = None

    with TestClient(app) as client:
        response = client.patch(f"/orders/{MOCK_ORDER_ID}/status", json={"status": "processing"})
        assert response.status_code == 404
        assert response.json()["detail"] == "Order not found"


@patch("app.main.SimpleConnectionPool")
def test_update_order_status_invalid_value(mock_pool_cls):
    """Test validation error for invalid status value."""
    with TestClient(app) as client:
        response = client.patch(f"/orders/{MOCK_ORDER_ID}/status", json={"status": "bogus"})
        assert response.status_code == 422
