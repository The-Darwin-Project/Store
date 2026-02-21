
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import sys
import os
import uuid

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app

# Mocks
MOCK_CUSTOMER_ID = str(uuid.uuid4())
MOCK_ORDER_ID = str(uuid.uuid4())
MOCK_PRODUCT_ID = str(uuid.uuid4())

@pytest.fixture
def mock_db_and_client():
    with patch("app.main.SimpleConnectionPool") as mock_pool_cls:
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Start client (triggers startup)
        with TestClient(app) as client:
            yield mock_cursor, client

def test_create_customer_success(mock_db_and_client):
    mock_db, client = mock_db_and_client
    mock_db.fetchone.return_value = ("2023-01-01T00:00:00",)
    
    response = client.post("/customers", json={"name": "John Doe", "email": "john@example.com"})
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "John Doe"
    assert data["email"] == "john@example.com"
    assert "id" in data

def test_list_customers_success(mock_db_and_client):
    mock_db, client = mock_db_and_client
    mock_db.fetchall.return_value = [
        (MOCK_CUSTOMER_ID, "John Doe", "john@example.com", "2023-01-01T00:00:00")
    ]
    
    response = client.get("/customers")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == MOCK_CUSTOMER_ID
    assert data[0]["name"] == "John Doe"

def test_create_order_requires_customer_id(mock_db_and_client):
    mock_db, client = mock_db_and_client
    # Payload missing customer_id
    payload = {
        "items": [{"product_id": MOCK_PRODUCT_ID, "quantity": 1}]
    }
    
    response = client.post("/orders", json=payload)
    
    # Should be 422 Unprocessable Entity (Pydantic validation)
    assert response.status_code == 422

def test_create_order_invalid_customer_id(mock_db_and_client):
    mock_db, client = mock_db_and_client
    # Mock customer check returning None (customer not found)
    mock_db.fetchone.return_value = None
    
    payload = {
        "items": [{"product_id": MOCK_PRODUCT_ID, "quantity": 1}],
        "customer_id": MOCK_CUSTOMER_ID
    }
    
    response = client.post("/orders", json=payload)
    
    assert response.status_code == 400
    assert "Invalid customer_id" in response.json()["detail"]

def test_create_order_success_with_customer(mock_db_and_client):
    mock_db, client = mock_db_and_client
    # 1. Check customer exists (returns ID)
    # 2. Update stock (returns product info)
    # 3. Get created_at (returns timestamp)
    mock_db.fetchone.side_effect = [
        (MOCK_CUSTOMER_ID,), # Customer exists
        (MOCK_PRODUCT_ID, "Test Product", 10.0, 99), # Stock update
        ("2023-01-01T00:00:00",) # Created at
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

def test_detach_order(mock_db_and_client):
    mock_db, client = mock_db_and_client
    # Mock rowcount to simulate successful update
    mock_db.rowcount = 1
    
    response = client.delete(f"/customers/{MOCK_CUSTOMER_ID}/orders/{MOCK_ORDER_ID}")
    
    assert response.status_code == 204

def test_detach_order_not_found(mock_db_and_client):
    mock_db, client = mock_db_and_client
    # Mock rowcount to simulate no rows updated
    mock_db.rowcount = 0
    
    response = client.delete(f"/customers/{MOCK_CUSTOMER_ID}/orders/{MOCK_ORDER_ID}")
    
    assert response.status_code == 404
