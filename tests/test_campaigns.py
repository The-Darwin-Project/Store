import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

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


def _future_dates():
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    end = start + timedelta(days=7)
    return start.isoformat(), end.isoformat()


def test_create_campaign(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = (datetime.now(),)
    start, end = _future_dates()

    response = client.post("/campaigns", json={
        "title": "Summer Sale",
        "type": "banner",
        "content": "Big savings this summer!",
        "start_date": start,
        "end_date": end,
        "priority": 10
    })

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Summer Sale"
    assert data["type"] == "banner"
    assert data["priority"] == 10


def test_create_campaign_invalid_dates(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    end = datetime.now(timezone.utc).isoformat()
    start = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    response = client.post("/campaigns", json={
        "title": "Bad Dates",
        "type": "banner",
        "start_date": start,
        "end_date": end
    })

    assert response.status_code == 400
    assert "end_date" in response.json()["detail"].lower()


def test_create_campaign_invalid_coupon(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    # First call returns None (coupon not found)
    mock_cur.fetchone.return_value = None
    start, end = _future_dates()

    response = client.post("/campaigns", json={
        "title": "Promo with bad coupon",
        "type": "discount_promo",
        "coupon_code": "NONEXISTENT",
        "start_date": start,
        "end_date": end
    })

    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


def test_create_spotlight_missing_product(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    start, end = _future_dates()

    response = client.post("/campaigns", json={
        "title": "Spotlight without product",
        "type": "product_spotlight",
        "start_date": start,
        "end_date": end
    })

    assert response.status_code == 400
    assert "product_id" in response.json()["detail"].lower()


def test_list_campaigns(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    now = datetime.now(timezone.utc)
    mock_cur.fetchall.return_value = [
        ("id1", "Banner 1", "banner", "content", None, None, None,
         None, now, now + timedelta(days=7), True, 10, now)
    ]

    response = client.get("/campaigns")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Banner 1"


def test_get_active_campaigns(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    now = datetime.now(timezone.utc)
    mock_cur.fetchall.return_value = [
        ("id1", "Active Banner", "banner", "Live now", None, None, None,
         None, now - timedelta(hours=1), now + timedelta(days=7), True, 5, now)
    ]

    response = client.get("/campaigns/active")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Active Banner"


def test_update_campaign(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    now = datetime.now(timezone.utc)
    # First fetchone: existing campaign for validation
    # Second fetchone: updated campaign from RETURNING
    existing_row = ("id1", "Old Title", "banner", "old content", None, None, None,
                    None, now, now + timedelta(days=7), True, 5, now)
    updated_row = ("id1", "New Title", "banner", "old content", None, None, None,
                   None, now, now + timedelta(days=7), True, 5, now)
    mock_cur.fetchone.side_effect = [existing_row, updated_row]

    response = client.patch("/campaigns/id1", json={
        "title": "New Title"
    })

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"


def test_delete_campaign(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = ("id1",)

    response = client.delete("/campaigns/id1")
    assert response.status_code == 204


def test_delete_campaign_not_found(client, mock_db):
    _, mock_conn, mock_cur = mock_db
    mock_cur.fetchone.return_value = None

    response = client.delete("/campaigns/nonexistent")
    assert response.status_code == 404
