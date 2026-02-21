import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import sys
import os
import uuid

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import sys
import os
import uuid

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app

# Mock data
MOCK_CUSTOMER_ID = str(uuid.uuid4())
MOCK_ORDER_ID = str(uuid.uuid4())
MOCK_PRODUCT_ID = str(uuid.uuid4())

@pytest.fixture
def client_with_db():
    with patch("app.main.SimpleConnectionPool") as mock_pool_cls:
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        with TestClient(app) as client:
            # We yield both client and the mock cursor so tests can configure the cursor
            yield client, mock_cursor

def test_create_customer(client_with_db):
    client, mock_db = client_with_db
    # Mock RETURNING created_at
    mock_db.fetchone.return_value = ["2023-01-01T00:00:00"]
    
    payload = {"name": "Test User", "email": "test@example.com"}
    response = client.post("/customers", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "created_at" in data

def test_list_customers(client_with_db):
    client, mock_db = client_with_db
    mock_db.fetchall.return_value = [
        (MOCK_CUSTOMER_ID, "Test User", "test@example.com", "2023-01-01T00:00:00")
    ]
    
    response = client.get("/customers")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == MOCK_CUSTOMER_ID
    assert data[0]["name"] == "Test User"

def test_create_order_with_customer(client_with_db):
    client, mock_db = client_with_db
    # Mock customer check (exists)
    mock_db.fetchone.side_effect = [
        (MOCK_CUSTOMER_ID,), # Customer exists check
        ("some-id", "Test Product", 10.0, 98), # Update stock returning
        ("2023-01-01T00:00:00",) # Select created_at
    ]
    
    payload = {
        "items": [{"product_id": MOCK_PRODUCT_ID, "quantity": 1}],
        "customer_id": MOCK_CUSTOMER_ID
    }
    
    response = client.post("/orders", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["customer_id"] == MOCK_CUSTOMER_ID
    assert data["status"] == "pending"

def test_create_order_invalid_customer(client_with_db):
    client, mock_db = client_with_db
    # Mock customer check (does not exist)
    mock_db.fetchone.return_value = None
    
    payload = {
        "items": [{"product_id": MOCK_PRODUCT_ID, "quantity": 1}],
        "customer_id": "invalid-id"
    }
    
    response = client.post("/orders", json=payload)
    
    assert response.status_code == 400
    assert "Invalid customer_id" in response.json()["detail"]

def test_list_customer_orders(client_with_db):
    client, mock_db = client_with_db
    mock_db.fetchall.return_value = [
        (MOCK_ORDER_ID, "2023-01-01T00:00:00", 100.0, "pending")
    ]
    
    response = client.get(f"/customers/{MOCK_CUSTOMER_ID}/orders")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == MOCK_ORDER_ID
    assert data[0]["customer_id"] == MOCK_CUSTOMER_ID

def test_detach_order(client_with_db):
    client, mock_db = client_with_db
    # Mock rowcount for update
    mock_db.rowcount = 1
    
    response = client.delete(f"/customers/{MOCK_CUSTOMER_ID}/orders/{MOCK_ORDER_ID}")
    
    assert response.status_code == 204

def test_detach_order_not_found(client_with_db):
    client, mock_db = client_with_db
    # Mock rowcount 0 (not found or not owned)
    mock_db.rowcount = 0
    
    response = client.delete(f"/customers/{MOCK_CUSTOMER_ID}/orders/{MOCK_ORDER_ID}")
    
    assert response.status_code == 404
