import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app

client = TestClient(app)

# Mock data
MOCK_PRODUCT_ID = "123e4567-e89b-12d3-a456-426614174000"
MOCK_ORDER_PAYLOAD = {
    "items": [
        {
            "product_id": MOCK_PRODUCT_ID,
            "quantity": 2
        }
    ],
    "customer_id": str(uuid.uuid4())
}

@pytest.mark.skipif(os.getenv("QE_SKIP_DB", "false") == "true", reason="Skipping DB tests")
def test_create_order_success():
    # We need to mock the DB interaction because we can't rely on the real DB having this product
    # or we can try to create a product first?
    # For now, let's assume the developer implements the DB logic correctly and we mock the DB execution
    # inside the route or we use a real DB if available.
    
    # Given the complexity of mocking the internal pool in integration tests without dependency injection override,
    # we will try to rely on the response structure first.
    # However, if the dev hasn't implemented it, this will 404.
    
    # We need to authorize the request if needed? No auth mentioned.
    
    # We will try to mock the db_pool.getconn context manager
    with patch("app.main.db_pool") as mock_pool:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock verifying stock
        # The code will likely query "SELECT price, stock FROM products WHERE id = ..."
        # We simulate we have enough stock
        mock_cursor.fetchone.return_value = {"price": 10.0, "stock": 100}
        
        # The code will then INSERT into orders and order_items and UPDATE products
        # We don't need to return anything specific for inserts usually, maybe the ID if using RETURNING
        
        response = client.post("/orders", json=MOCK_ORDER_PAYLOAD)
        
        # If the route is not implemented yet, this returns 404
        if response.status_code == 404:
            pytest.fail("Endpoint /orders not implemented yet")
            
        assert response.status_code == 201 or response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending" or data["status"] == "confirmed"

def test_create_order_insufficient_stock():
    with patch("app.main.db_pool") as mock_pool:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock verifying stock - return low stock
        mock_cursor.fetchone.return_value = {"price": 10.0, "stock": 1}
        
        payload = {
            "items": [
                {
                    "product_id": MOCK_PRODUCT_ID,
                    "quantity": 2
                }
            ]
        }
        
        response = client.post("/orders", json=payload)
        
        if response.status_code == 404:
             pytest.fail("Endpoint /orders not implemented yet")

        assert response.status_code == 400
        assert "stock" in response.text.lower()
