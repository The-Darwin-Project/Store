import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import sys
import os
import uuid

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app

@patch("app.main.SimpleConnectionPool")
def test_dashboard_metrics(mock_pool_cls):
    """Verify that the dashboard endpoint aggregates business metrics correctly."""
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # 1. total_revenue -> fetchone
    # 2. orders_by_status -> fetchall
    # 3. top_products -> fetchall
    # 4. low_stock_alerts -> fetchall
    
    mock_cursor.fetchone.side_effect = [
        (1500.50,) # Total revenue
    ]
    
    mock_cursor.fetchall.side_effect = [
        # Orders by status
        [("pending", 5), ("shipped", 10), ("delivered", 20)],
        
        # Top products
        [
            (uuid.uuid4(), "Product A", 100),
            (uuid.uuid4(), "Product B", 80),
            (uuid.uuid4(), "Product C", 50),
            (uuid.uuid4(), "Product D", 30),
            (uuid.uuid4(), "Product E", 10),
        ],
        
        # Low stock alerts
        [
            (uuid.uuid4(), "Low Stock Prod 1", 5, 10, uuid.uuid4(), "Supplier Inc", "contact@supplier.com"),
            (uuid.uuid4(), "Out of Stock Prod 2", 0, 10, None, None, None), # No supplier
        ]
    ]

    with TestClient(app) as client:
        response = client.get("/dashboard")
        
        assert response.status_code == 200
        data = response.json()
        
        # 1. Total revenue calculation
        assert data["total_revenue"] == 1500.50
        
        # 2. Order counts by status
        assert data["orders_by_status"]["pending"] == 5
        assert data["orders_by_status"]["shipped"] == 10
        assert data["orders_by_status"]["delivered"] == 20
        
        # 3. Top 5 products list
        assert len(data["top_products"]) == 5
        assert data["top_products"][0]["name"] == "Product A"
        assert data["top_products"][0]["total_sold"] == 100
        
        # 4. Low-stock alerts
        assert len(data["low_stock_alerts"]) == 2
        assert data["low_stock_alerts"][0]["name"] == "Low Stock Prod 1"
        assert data["low_stock_alerts"][0]["stock"] == 5
        assert data["low_stock_alerts"][0]["supplier"]["name"] == "Supplier Inc"
        assert data["low_stock_alerts"][0]["supplier"]["contact_email"] == "contact@supplier.com"
        
        assert data["low_stock_alerts"][1]["name"] == "Out of Stock Prod 2"
        assert data["low_stock_alerts"][1]["stock"] == 0
        assert data["low_stock_alerts"][1]["supplier"] is None
