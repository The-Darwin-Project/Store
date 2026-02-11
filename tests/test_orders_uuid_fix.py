import pytest
import uuid
from unittest.mock import MagicMock, patch, call
from fastapi.testclient import TestClient
from fastapi import Request
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app
from app.routes.orders import list_orders

@patch("app.main.SimpleConnectionPool")
def test_list_orders_uses_uuid_objects_for_array_query(mock_pool_cls):
    """
    Verify that list_orders converts order IDs to uuid.UUID objects 
    before passing them to the ANY(%s) query.
    """
    # Setup Mock DB
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # Mock data
    oid1_str = "550e8400-e29b-41d4-a716-446655440000"
    oid2_str = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    
    # Mock return values
    # First query: SELECT ... FROM orders
    mock_cursor.fetchall.side_effect = [
        [
            (oid1_str, "2023-01-01", 100.0, "confirmed"),
            (oid2_str, "2023-01-02", 200.0, "pending")
        ],
        # Second query: SELECT ... FROM order_items
        [] 
    ]
    
    # We can't easily use TestClient because we want to inspect the internal cursor calls
    # triggered by the route handler. 
    # But TestClient with mocked app.state.db_pool is the integration way.
    
    # Let's inject the mock pool into the app state
    app.state.db_pool = mock_pool
    
    with TestClient(app) as client:
        # Reset mock to clear calls from startup (table creation)
        mock_cursor.execute.reset_mock()
        
        response = client.get("/orders")
        
        assert response.status_code == 200
        
        # Verify the calls
        # Expected: 2 calls to execute.
        # 1. Select orders
        # 2. Select items with ANY(%s)
        
        assert mock_cursor.execute.call_count == 2
        
        # Check the second call arguments
        second_call = mock_cursor.execute.call_args_list[1]
        sql_query = second_call[0][0]
        params = second_call[0][1]
        
        print(f"SQL: {sql_query}")
        print(f"Params: {params}")
        
        # Verify SQL does NOT have ::uuid[] cast (as per actual code implementation)
        assert "::uuid[]" not in sql_query, "Code should not use SQL cast if it uses Python object conversion"
        assert "order_id = ANY(%s)" in sql_query
        
        # Verify params is a tuple containing a list of uuid.UUID objects
        assert isinstance(params, tuple)
        assert len(params) == 1
        uuid_list = params[0]
        
        assert isinstance(uuid_list, list)
        assert len(uuid_list) == 2
        assert isinstance(uuid_list[0], uuid.UUID)
        assert isinstance(uuid_list[1], uuid.UUID)
        assert str(uuid_list[0]) == oid1_str
        assert str(uuid_list[1]) == oid2_str

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
