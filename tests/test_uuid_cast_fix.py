# Store/tests/test_uuid_cast_fix.py
"""Test that GET /orders handles UUID objects from PostgreSQL correctly.

Reproduces the bug: 'operator does not exist: uuid = text'
which occurred because psycopg2 returns uuid.UUID objects from UUID columns,
and ANY(%s) without ::uuid[] cast caused a type mismatch.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, call
import sys
import os
import datetime
import uuid

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from app.main import app


@patch("app.main.SimpleConnectionPool")
def test_get_orders_with_uuid_objects(mock_pool_cls):
    """Verify GET /orders works when PostgreSQL returns uuid.UUID objects.

    psycopg2 returns uuid.UUID instances for UUID columns. The query
    must cast the parameter array to uuid[] so PostgreSQL can compare
    uuid = uuid instead of uuid = text.
    """
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Simulate PostgreSQL returning uuid.UUID objects (not strings)
    order_id_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    order_id_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
    product_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    item_id_1 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    item_id_2 = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    now = datetime.datetime.now()

    mock_cursor.fetchall.side_effect = [
        # Query 1: orders table returns uuid.UUID objects
        [
            (order_id_1, now, 50.0, "pending", None, None, 0.0),
            (order_id_2, now, 30.0, "pending", None, None, 0.0),
        ],
        # Query 2: order_items table returns uuid.UUID objects
        [
            (item_id_1, order_id_1, product_id, 2, 25.0),
            (item_id_2, order_id_2, product_id, 3, 10.0),
        ],
    ]

    with TestClient(app) as client:
        response = client.get("/orders")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Verify the SQL used ::uuid[] cast
    sql_calls = mock_cursor.execute.call_args_list
    order_items_query = [c for c in sql_calls if "FROM order_items" in c[0][0]][0]
    assert "::uuid[]" in order_items_query[0][0], (
        "Query must cast parameter to uuid[] to avoid 'uuid = text' mismatch"
    )

    # Verify order IDs are returned as strings in the response
    assert data[0]["id"] == str(order_id_1)
    assert data[1]["id"] == str(order_id_2)

    # Verify items are correctly associated with orders
    assert len(data[0]["items"]) == 1
    assert data[0]["items"][0]["product_id"] == str(product_id)
    assert len(data[1]["items"]) == 1


@patch("app.main.SimpleConnectionPool")
def test_get_orders_passes_string_ids_to_query(mock_pool_cls):
    """Verify order_ids are converted to strings before passing to ANY().

    Even though PostgreSQL returns uuid.UUID objects, we convert them to
    strings and rely on ::uuid[] cast for proper type handling.
    """
    mock_pool = MagicMock()
    mock_pool_cls.return_value = mock_pool

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    order_id = uuid.UUID("33333333-3333-3333-3333-333333333333")

    mock_cursor.fetchall.side_effect = [
        [(order_id, datetime.datetime.now(), 10.0, "pending", None, None, 0.0)],
        [],  # no items
    ]

    with TestClient(app) as client:
        response = client.get("/orders")

    assert response.status_code == 200

    # Verify the parameter passed to the order_items query is a list of strings
    sql_calls = mock_cursor.execute.call_args_list
    order_items_call = [c for c in sql_calls if "FROM order_items" in c[0][0]][0]
    param_list = order_items_call[0][1][0]  # first param of second query
    assert all(isinstance(x, str) for x in param_list), (
        "order_ids should be strings to ensure consistent type handling"
    )
