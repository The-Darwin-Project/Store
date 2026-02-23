import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import sys
import os
import uuid

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app
from app.routes.alerts import check_and_create_alert, EmailNotifier
from app.models import AlertStatus, AlertType

MOCK_PRODUCT_ID = str(uuid.uuid4())
MOCK_SUPPLIER_ID = str(uuid.uuid4())
MOCK_ALERT_ID = str(uuid.uuid4())

@pytest.fixture
def client_with_db():
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
        yield {
            "client": TestClient(app),
            "pool": mock_pool,
            "conn": mock_conn,
            "cursor": mock_cursor
        }

def test_alerts_table_schema(client_with_db):
    """1. Verify 'alerts' table schema."""
    cursor = client_with_db["cursor"]
    # Initialize the app which runs startup events (table creation)
    with TestClient(app):
        pass
    
    # Check if create table is called in startup event
    sql_calls = [call[0][0] for call in cursor.execute.call_args_list]
    alerts_schema_found = any("CREATE TABLE IF NOT EXISTS alerts" in call for call in sql_calls)
    assert alerts_schema_found, "alerts table schema not found in startup SQL"

def test_check_and_create_alert(client_with_db):
    """2. Test 'AlertsHelper' (check_and_create_alert) for alert creation.
    4. Verify 'EmailNotifier' stub is called."""
    cursor = client_with_db["cursor"]
    conn = client_with_db["conn"]
    
    # Mock return values for check_and_create_alert:
    # 1. Product select
    # 2. Alert select (no existing active)
    # 3. Supplier select
    cursor.fetchone.side_effect = [
        ("Test Product", 5, 10, MOCK_SUPPLIER_ID),
        None,
        ("Test Supplier", "supplier@test.com"),
    ]
    
    with patch.object(EmailNotifier, 'send') as mock_send:
        check_and_create_alert(conn, MOCK_PRODUCT_ID)
        
        # Verify INSERT was called
        insert_calls = [call[0][0] for call in cursor.execute.call_args_list if "INSERT INTO alerts" in call[0][0]]
        assert len(insert_calls) == 1
        
        # Verify EmailNotifier stub is called
        mock_send.assert_called_once_with(
            to="supplier@test.com",
            subject="Restock Alert: Test Product",
            body="Restock needed: 'Test Product' stock is 5, below threshold of 10. Supplier: Test Supplier."
        )

def test_crud_endpoints(client_with_db):
    """3. Test CRUD endpoints (GET, POST, PATCH)."""
    client = client_with_db["client"]
    cursor = client_with_db["cursor"]
    
    # We need to reset the cursor mock side_effects because startup event might have consumed them
    cursor.fetchone.side_effect = None
    
    # POST
    cursor.fetchone.return_value = ("2026-01-01T00:00:00",)
    response = client.post("/alerts", json={
        "type": "restock",
        "message": "Manual alert",
        "product_id": MOCK_PRODUCT_ID,
        "supplier_id": MOCK_SUPPLIER_ID,
        "current_stock": 2,
        "reorder_threshold": 10
    })
    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Manual alert"
    assert data["status"] == "active"
    
    # GET
    cursor.fetchall.return_value = [
        (MOCK_ALERT_ID, "restock", "Low stock!", "active", MOCK_PRODUCT_ID, MOCK_SUPPLIER_ID, 2, 10, "2026-01-01T00:00:00")
    ]
    response = client.get("/alerts")
    assert response.status_code == 200
    print(response.json())
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == MOCK_ALERT_ID
    
    # PATCH
    cursor.fetchone.return_value = (MOCK_ALERT_ID, "restock", "Low stock!", "ordered", MOCK_PRODUCT_ID, MOCK_SUPPLIER_ID, 2, 10, "2026-01-01T00:00:00")
    response = client.patch(f"/alerts/{MOCK_ALERT_ID}", json={
        "status": "ordered"
    })
    assert response.status_code == 200
    assert response.json()["status"] == "ordered"
