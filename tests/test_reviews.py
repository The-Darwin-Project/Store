# Store/tests/test_reviews.py
# @ai-rules:
# 1. [Pattern]: Uses mock_db fixture with patched SimpleConnectionPool (no real DB needed).
# 2. [Constraint]: Uses `with TestClient(app) as client:` inside fixtures, never module-level.
"""Unit tests for product review endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime

from app.main import app


@pytest.fixture
def mock_db():
    with patch("app.main.SimpleConnectionPool") as mock_pool:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool_inst = MagicMock()
        mock_pool.return_value = mock_pool_inst
        mock_pool_inst.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        yield mock_pool, mock_conn, mock_cur


@pytest.fixture
def client(mock_db):
    with TestClient(app) as client:
        yield client


PRODUCT_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"


def test_create_review_success(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    now = datetime.now()
    # Product exists
    mock_cur.fetchone.side_effect = [
        (PRODUCT_ID,),       # product lookup
        ("Test Customer",),  # customer lookup
        (now,),              # RETURNING created_at
    ]

    response = client.post(f"/products/{PRODUCT_ID}/reviews", json={
        "customer_id": CUSTOMER_ID,
        "rating": 5,
        "comment": "Great product!"
    })

    assert response.status_code == 201
    data = response.json()
    assert data["product_id"] == PRODUCT_ID
    assert data["customer_id"] == CUSTOMER_ID
    assert data["rating"] == 5
    assert data["comment"] == "Great product!"
    assert data["customer_name"] == "Test Customer"


def test_create_review_duplicate_returns_409(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    # Product exists, customer exists
    mock_cur.fetchone.side_effect = [
        (PRODUCT_ID,),
        ("Test Customer",),
    ]
    # Simulate unique constraint violation
    from psycopg2 import IntegrityError
    mock_cur.execute.side_effect = [
        None,  # product lookup
        None,  # customer lookup
        IntegrityError("duplicate key value violates unique constraint"),
    ]

    response = client.post(f"/products/{PRODUCT_ID}/reviews", json={
        "customer_id": CUSTOMER_ID,
        "rating": 4,
        "comment": "Duplicate"
    })

    assert response.status_code == 409
    assert "already reviewed" in response.json()["detail"].lower()


def test_create_review_invalid_rating(client, mock_db):
    """Rating outside 1-5 should return 422 from Pydantic validation."""
    response = client.post(f"/products/{PRODUCT_ID}/reviews", json={
        "customer_id": CUSTOMER_ID,
        "rating": 0,
        "comment": "Bad rating"
    })
    assert response.status_code == 422

    response = client.post(f"/products/{PRODUCT_ID}/reviews", json={
        "customer_id": CUSTOMER_ID,
        "rating": 6,
        "comment": "Bad rating"
    })
    assert response.status_code == 422


def test_create_review_product_not_found(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = None  # product not found

    response = client.post(f"/products/{PRODUCT_ID}/reviews", json={
        "customer_id": CUSTOMER_ID,
        "rating": 3,
        "comment": "Missing product"
    })

    assert response.status_code == 404
    assert "product" in response.json()["detail"].lower()


def test_list_reviews(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    now = datetime.now()
    mock_cur.fetchall.return_value = [
        ("r1", PRODUCT_ID, CUSTOMER_ID, "Alice", 5, "Excellent!", now),
        ("r2", PRODUCT_ID, "c2", "Bob", 3, "Okay", now),
    ]

    response = client.get(f"/products/{PRODUCT_ID}/reviews")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["customer_name"] == "Alice"
    assert data[0]["rating"] == 5
    assert data[1]["rating"] == 3


def test_average_rating(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = (4.5, 10)

    response = client.get(f"/products/{PRODUCT_ID}/average-rating")

    assert response.status_code == 200
    data = response.json()
    assert data["product_id"] == PRODUCT_ID
    assert data["average_rating"] == 4.5
    assert data["review_count"] == 10


def test_average_rating_no_reviews(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = (0, 0)

    response = client.get(f"/products/{PRODUCT_ID}/average-rating")

    assert response.status_code == 200
    data = response.json()
    assert data["average_rating"] == 0
    assert data["review_count"] == 0
