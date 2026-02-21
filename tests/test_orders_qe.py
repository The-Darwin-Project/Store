
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, ANY
import sys
import os
import uuid

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app

client = TestClient(app)

MOCK_PRODUCT_ID = str(uuid.uuid4())
MOCK_ORDER_PAYLOAD = {
    "items": [
        {
            "product_id": MOCK_PRODUCT_ID,
            "quantity": 2
        }
    ],
    "customer_id": str(uuid.uuid4())
}

@patch("app.main.SimpleConnectionPool")
def test_create_order_atomic_update_sql(mock_pool_cls):
    """Verify the exact SQL used for atomic stock update."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Setup successful execution
    mock_cursor.fetchone.side_effect = [
        (MOCK_ORDER_PAYLOAD["customer_id"],),  # SELECT id FROM customers
        (MOCK_PRODUCT_ID, "Test Product", 10.0, 98),  # UPDATE RETURNING
        (None,)  # SELECT created_at
    ]
    
    with TestClient(app) as client:
        response = client.post("/orders", json=MOCK_ORDER_PAYLOAD)
        
        assert response.status_code == 201
        
        # Verify the SQL query
        # We look for the UPDATE call
        update_call = [call for call in mock_cursor.execute.call_args_list if "UPDATE products" in call[0][0]]
        assert len(update_call) == 1
        
        sql = update_call[0][0][0]
        params = update_call[0][0][1]
        
        assert "stock = stock - %s" in sql
        assert "stock >= %s" in sql
        assert params == (2, MOCK_PRODUCT_ID, 2)

@patch("app.main.SimpleConnectionPool")
def test_create_order_insufficient_stock_rollback(mock_pool_cls):
    """Verify rollback on insufficient stock."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Customer validation passes, then UPDATE returns None (row not found due to condition)
    # Then SELECT returns product to confirm it exists but has low stock
    mock_cursor.fetchone.side_effect = [
        (MOCK_ORDER_PAYLOAD["customer_id"],),  # SELECT id FROM customers
        None,
        ("Test Product", 1)
    ]
    
    with TestClient(app) as client:
        response = client.post("/orders", json=MOCK_ORDER_PAYLOAD)
        
        assert response.status_code == 400
        assert "Insufficient stock" in response.json()["detail"]
        
        # Verify rollback was called
        mock_conn.rollback.assert_called()

@patch("app.main.SimpleConnectionPool")
def test_create_order_product_not_found(mock_pool_cls):
    """Verify 404 when product does not exist."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Customer validation passes, UPDATE returns None
    # Then SELECT returns None (product really doesn't exist)
    mock_cursor.fetchone.side_effect = [
        (MOCK_ORDER_PAYLOAD["customer_id"],),  # SELECT id FROM customers
        None,
        None
    ]
    
    with TestClient(app) as client:
        response = client.post("/orders", json=MOCK_ORDER_PAYLOAD)
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

@patch("app.main.SimpleConnectionPool")
def test_create_order_db_error_handling(mock_pool_cls):
    """Verify 500 on generic DB error."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Simulate DB error
    mock_cursor.execute.side_effect = Exception("DB Connection Lost")
    
    with TestClient(app) as client:
        response = client.post("/orders", json=MOCK_ORDER_PAYLOAD)
        
        assert response.status_code == 500
        assert "Order creation failed" in response.json()["detail"]
        mock_conn.rollback.assert_called()
