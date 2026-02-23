
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
def test_list_orders_uses_sql_cast_for_uuid_array(mock_pool_cls):
    """
    Verify that list_orders uses SQL cast ::uuid[] for the array query
    and passes string parameters (consistent with other endpoints).
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
            (oid1_str, "2023-01-01", 100.0, "pending", None, None, 0.0, None),
            (oid2_str, "2023-01-02", 200.0, "pending", None, None, 0.0, None)
        ],
        # Second query: SELECT ... FROM order_items
        []
    ]
    # Inject mock pool
    app.state.db_pool = mock_pool
    
    with TestClient(app) as client:
        # Reset mock to clear calls from startup
        mock_cursor.execute.reset_mock()
        
        response = client.get("/orders")
        
        assert response.status_code == 200
        
        # Verify the calls
        assert mock_cursor.execute.call_count == 2
        
        # Check the second call arguments
        second_call = mock_cursor.execute.call_args_list[1]
        sql_query = second_call[0][0]
        params = second_call[0][1]
        
        print(f"SQL: {sql_query}")
        print(f"Params: {params}")
        
        # Verify SQL DOES have ::uuid[] cast
        assert "::uuid[]" in sql_query, "SQL query must include ::uuid[] cast"
        assert "order_id = ANY(%s::uuid[])" in sql_query
        
        # Verify params is a tuple containing a list of strings
        assert isinstance(params, tuple)
        assert len(params) == 1
        str_list = params[0]
        
        assert isinstance(str_list, list)
        assert len(str_list) == 2
        assert isinstance(str_list[0], str)
        assert isinstance(str_list[1], str)
        assert str_list[0] == oid1_str
        assert str_list[1] == oid2_str

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
