import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import sys
import os
import uuid
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app

# Mocks
MOCK_ORDER_ID_1 = str(uuid.uuid4())
MOCK_ORDER_ID_2 = str(uuid.uuid4())
MOCK_CUSTOMER_ID = str(uuid.uuid4())

@pytest.fixture
def client():
    with patch("app.main.SimpleConnectionPool") as mock_pool_cls:
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        
        # Make the cursor context manager work
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        with TestClient(app) as client:
            # Startup has completed. Reset mock to clear DDL calls.
            mock_cursor.reset_mock()
            client.mock_cursor = mock_cursor # Attach for easy access in tests
            yield client

def test_list_unassigned_orders(client):
    # Setup mock return values
    mock_cursor = client.mock_cursor
    
    # Mock orders query
    mock_cursor.fetchall.side_effect = [
        # 1. Orders
        [
            (MOCK_ORDER_ID_1, datetime.now(), 100.0, "pending"),
            (MOCK_ORDER_ID_2, datetime.now(), 50.0, "pending")
        ],
        # 2. Order items
        []
    ]
    
    response = client.get("/orders/unassigned")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == MOCK_ORDER_ID_1
    assert data[0]["customer_id"] is None
    
    # Verify the SQL query was correct
    call_args = mock_cursor.execute.call_args_list[0]
    assert "WHERE customer_id IS NULL" in call_args[0][0]

def test_attach_order_to_customer(client):
    mock_cursor = client.mock_cursor
    
    # attach_order_to_customer calls:
    # 1. SELECT id FROM customers ... (check customer exists)
    # 2. UPDATE orders ... RETURNING ...
    
    mock_cursor.fetchone.side_effect = [
        (MOCK_CUSTOMER_ID,), # Customer exists
        (MOCK_ORDER_ID_1, datetime.now(), 100.0, "pending"),  # Update returns 4 cols
    ]
    
    response = client.put(f"/orders/{MOCK_ORDER_ID_1}/customer/{MOCK_CUSTOMER_ID}")
    
    if response.status_code != 200:
        print(f"Error response: {response.json()}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == MOCK_ORDER_ID_1
    assert data["customer_id"] == MOCK_CUSTOMER_ID
    
    # Verify update
    assert mock_cursor.execute.call_count == 2
    assert "UPDATE orders SET customer_id = %s" in mock_cursor.execute.call_args_list[1][0][0]

def test_delete_order(client):
    mock_cursor = client.mock_cursor
    
    # delete_order calls:
    # 1. SELECT id FROM orders ... (check order exists)
    # 2. DELETE FROM order_items ...
    # 3. DELETE FROM orders ...
    
    mock_cursor.fetchone.side_effect = [
        (MOCK_ORDER_ID_1,), # Order exists
    ]
    
    response = client.delete(f"/orders/{MOCK_ORDER_ID_1}")
    
    assert response.status_code == 204
    
    # Verify deletes
    assert mock_cursor.execute.call_count == 3
    assert "DELETE FROM order_items" in mock_cursor.execute.call_args_list[1][0][0]
    assert "DELETE FROM orders" in mock_cursor.execute.call_args_list[2][0][0]
