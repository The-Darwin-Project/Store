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
from app.models import OrderStatus

# Test data
MOCK_CUSTOMER_ID = str(uuid.uuid4())
MOCK_PRODUCT_ID = str(uuid.uuid4())
MOCK_ORDER_ID = str(uuid.uuid4())
MOCK_INVOICE_ID = str(uuid.uuid4())

@pytest.fixture
def client_with_mock_db():
    with patch("app.main.SimpleConnectionPool") as mock_pool_cls:
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_conn.cursor.return_value = mock_cursor
        
        app.state.db_pool = mock_pool
        
        with TestClient(app) as client:
            yield {
                "client": client,
                "pool": mock_pool,
                "conn": mock_conn,
                "cursor": mock_cursor
            }

def test_customers_new_fields_implemented(client_with_mock_db):
    """1. Verify that POST /customers handles new fields."""
    client = client_with_mock_db["client"]
    cursor = client_with_mock_db["cursor"]
    
    # Mock for POST /customers
    cursor.fetchone.return_value = (datetime.now(),)
    
    customer_data = {
        "name": "Acme Corp",
        "email": "acme@example.com",
        "company": "Acme Corporation",
        "phone": "555-0123",
        "shipping_street": "123 Main St",
        "shipping_city": "Metropolis",
        "shipping_state": "NY",
        "shipping_zip": "10001",
        "shipping_country": "USA"
    }
    
    response = client.post("/customers", json=customer_data)
    
    # If it returns 422, the model hasn't been updated
    if response.status_code == 422:
        pytest.fail("CustomerCreate model does not support new fields")
        
    assert response.status_code == 201
    
    # Verify SQL includes new columns
    last_query = cursor.execute.call_args[0][0].lower()
    assert "company" in last_query
    assert "shipping_street" in last_query

def test_patch_customer_implemented(client_with_mock_db):
    """1. Verify that PATCH /customers/{id} is implemented."""
    client = client_with_mock_db["client"]
    cursor = client_with_mock_db["cursor"]
    
    # Mock for SELECT customer and RETURNING updated customer
    cursor.fetchone.return_value = (MOCK_CUSTOMER_ID, "Updated Name", "test@example.com", "Acme", "555", "St", "City", "ST", "123", "USA", datetime.now())
    
    patch_data = {"company": "Updated Acme"}
    response = client.patch(f"/customers/{MOCK_CUSTOMER_ID}", json=patch_data)
    
    if response.status_code == 404:
        pytest.fail("PATCH /customers/{customer_id} not implemented")
    
    assert response.status_code == 200
    assert response.json()["company"] == "Acme" # Based on our mock return

def test_invoice_generation_logic(client_with_mock_db):
    """2. Verify POST /orders/{id}/invoice logic."""
    client = client_with_mock_db["client"]
    cursor = client_with_mock_db["cursor"]
    
    # Mock sequence:
    # 1. Fetch order
    # 2. Check existing invoice
    # 3. Fetch customer
    # 4. Fetch order items with products
    # 5. Insert invoice
    
    cursor.fetchone.side_effect = [
        (MOCK_ORDER_ID, datetime.now(), 150.0, "delivered", MOCK_CUSTOMER_ID, "SAVE20", 30.0), # Order
        None, # No existing invoice
        (MOCK_CUSTOMER_ID, "John Doe", "john@example.com", "Acme", "555", "Street", "City", "ST", "123", "USA", datetime.now()), # Customer
        (MOCK_INVOICE_ID, 101, MOCK_ORDER_ID, "{}", "[]", 180.0, "SAVE20", 30.0, 150.0, datetime.now()) # Inserted invoice RETURNING
    ]
    
    cursor.fetchall.return_value = [
        (str(uuid.uuid4()), MOCK_ORDER_ID, MOCK_PRODUCT_ID, 2, 90.0, "Product A", "SKU-A")
    ]
    
    response = client.post(f"/orders/{MOCK_ORDER_ID}/invoice")
    
    if response.status_code == 404:
        pytest.fail("POST /orders/{order_id}/invoice not implemented")
        
    assert response.status_code == 201
    data = response.json()
    assert data["invoice_number"] == 101
    assert data["grand_total"] == 150.0
    assert data["customer_snapshot"]["name"] == "John Doe"
    assert len(data["line_items"]) == 1
    assert data["line_items"][0]["product_name"] == "Product A"

def test_list_invoices(client_with_mock_db):
    """3. Verify GET /invoices."""
    client = client_with_mock_db["client"]
    cursor = client_with_mock_db["cursor"]
    
    cursor.fetchall.return_value = [
        (MOCK_INVOICE_ID, 101, MOCK_ORDER_ID, MOCK_CUSTOMER_ID, '{"name": "John"}', '[]', 100.0, None, 0.0, 100.0, datetime.now())
    ]
    
    response = client.get("/invoices")
    assert response.status_code == 200
    invoices = response.json()
    assert len(invoices) == 1
    assert invoices[0]["invoice_number"] == 101

def test_order_model_includes_invoice_id(client_with_mock_db):
    """4. Verify Order model includes invoice_id."""
    client = client_with_mock_db["client"]
    cursor = client_with_mock_db["cursor"]
    
    # Mock GET /orders response from DB
    cursor.fetchall.side_effect = [
        [(MOCK_ORDER_ID, datetime.now(), 100.0, "delivered", MOCK_CUSTOMER_ID, None, 0.0, "John", MOCK_INVOICE_ID)], # Orders
        [] # Order items
    ]
    
    response = client.get("/orders")
    assert response.status_code == 200
    orders = response.json()
    if orders:
        assert "invoice_id" in orders[0], "invoice_id field missing from Order response"
