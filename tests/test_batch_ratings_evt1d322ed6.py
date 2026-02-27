# Store/tests/test_batch_ratings_evt1d322ed6.py
# QE tests for evt-1d322ed6 — batch average-ratings endpoint + frontend + deployment
#
# Covers:
#  1. GET /products/average-ratings/batch endpoint (reviews.py)
#  2. Frontend index.html uses a single batch call, not N+1 per-product calls
#  3. deployment-backend.yaml init container uses backend image + Python wait script
"""QE verification tests for evt-1d322ed6: batch ratings endpoint and init container fix."""

import pytest
import re
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


# ---------------------------------------------------------------------------
# Shared fixtures (same pattern as test_reviews.py)
# ---------------------------------------------------------------------------

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
    with TestClient(app) as c:
        yield c


PRODUCT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PRODUCT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
PRODUCT_C = "cccccccc-cccc-cccc-cccc-cccccccccccc"


# ---------------------------------------------------------------------------
# 1. Batch endpoint — core functionality
# ---------------------------------------------------------------------------

class TestBatchAverageRatings:
    """Tests for GET /products/average-ratings/batch"""

    def test_batch_returns_ratings_for_all_requested_ids(self, client, mock_db):
        """Two products with reviews both appear in the response."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = [
            (PRODUCT_A, 4.5, 10),
            (PRODUCT_B, 3.0, 5),
        ]

        resp = client.get(f"/products/average-ratings/batch?product_ids={PRODUCT_A},{PRODUCT_B}")

        assert resp.status_code == 200
        data = {r["product_id"]: r for r in resp.json()}
        assert data[PRODUCT_A]["average_rating"] == 4.5
        assert data[PRODUCT_A]["review_count"] == 10
        assert data[PRODUCT_B]["average_rating"] == 3.0
        assert data[PRODUCT_B]["review_count"] == 5

    def test_batch_returns_zero_rating_for_products_without_reviews(self, client, mock_db):
        """Products not in the DB result set get average_rating=0, review_count=0."""
        _, _, mock_cur = mock_db
        # Only PRODUCT_A has reviews; PRODUCT_B is absent from DB
        mock_cur.fetchall.return_value = [
            (PRODUCT_A, 4.0, 3),
        ]

        resp = client.get(f"/products/average-ratings/batch?product_ids={PRODUCT_A},{PRODUCT_B}")

        assert resp.status_code == 200
        data = {r["product_id"]: r for r in resp.json()}
        assert data[PRODUCT_A]["average_rating"] == 4.0
        assert data[PRODUCT_B]["average_rating"] == 0
        assert data[PRODUCT_B]["review_count"] == 0

    def test_batch_empty_product_ids_returns_empty_list(self, client, mock_db):
        """Empty product_ids query param returns []."""
        resp = client.get("/products/average-ratings/batch?product_ids=")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_batch_single_product(self, client, mock_db):
        """Single product ID works correctly."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = [
            (PRODUCT_A, 5.0, 1),
        ]

        resp = client.get(f"/products/average-ratings/batch?product_ids={PRODUCT_A}")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["product_id"] == PRODUCT_A
        assert data[0]["average_rating"] == 5.0
        assert data[0]["review_count"] == 1

    def test_batch_all_products_no_reviews(self, client, mock_db):
        """All requested products have no reviews — all return 0."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = []

        resp = client.get(f"/products/average-ratings/batch?product_ids={PRODUCT_A},{PRODUCT_B},{PRODUCT_C}")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        for item in data:
            assert item["average_rating"] == 0
            assert item["review_count"] == 0

    def test_batch_strips_whitespace_from_ids(self, client, mock_db):
        """Whitespace around product IDs is stripped before querying."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = [
            (PRODUCT_A, 3.5, 2),
        ]

        resp = client.get(f"/products/average-ratings/batch?product_ids= {PRODUCT_A} , {PRODUCT_B} ")

        assert resp.status_code == 200
        data = {r["product_id"]: r for r in resp.json()}
        assert PRODUCT_A in data
        assert PRODUCT_B in data

    def test_batch_requires_product_ids_param(self, client, mock_db):
        """Missing product_ids query param returns 422 validation error."""
        resp = client.get("/products/average-ratings/batch")
        assert resp.status_code == 422

    def test_batch_ratings_rounded_to_one_decimal(self, client, mock_db):
        """Average ratings are rounded to 1 decimal place."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = [
            (PRODUCT_A, 4.333333, 3),
        ]

        resp = client.get(f"/products/average-ratings/batch?product_ids={PRODUCT_A}")

        assert resp.status_code == 200
        assert resp.json()[0]["average_rating"] == 4.3

    def test_batch_preserves_order_of_requested_ids(self, client, mock_db):
        """Response order matches the order of requested product IDs."""
        _, _, mock_cur = mock_db
        # DB returns in arbitrary order (B first, then A)
        mock_cur.fetchall.return_value = [
            (PRODUCT_B, 2.0, 1),
            (PRODUCT_A, 4.0, 5),
        ]

        resp = client.get(f"/products/average-ratings/batch?product_ids={PRODUCT_A},{PRODUCT_B}")

        assert resp.status_code == 200
        data = resp.json()
        # First item should be PRODUCT_A (as requested)
        assert data[0]["product_id"] == PRODUCT_A
        assert data[1]["product_id"] == PRODUCT_B

    def test_batch_uses_single_db_query_not_n_plus_1(self, client, mock_db):
        """Verify only one DB execute() call is made regardless of product count."""
        _, mock_conn, mock_cur = mock_db
        mock_cur.fetchall.return_value = []

        # Reset call count after app startup may have triggered its own queries
        mock_cur.execute.reset_mock()

        client.get(f"/products/average-ratings/batch?product_ids={PRODUCT_A},{PRODUCT_B},{PRODUCT_C}")

        # Only one execute call should be made for the entire batch
        assert mock_cur.execute.call_count == 1

    def test_batch_sql_uses_in_clause(self, client, mock_db):
        """The SQL query uses an IN clause to batch all IDs in one query."""
        _, _, mock_cur = mock_db
        mock_cur.fetchall.return_value = []

        client.get(f"/products/average-ratings/batch?product_ids={PRODUCT_A},{PRODUCT_B}")

        call_args = mock_cur.execute.call_args
        query = call_args[0][0]
        assert "IN" in query.upper(), "SQL should use IN clause for batch lookup"
        assert "GROUP BY" in query.upper(), "SQL should GROUP BY product_id"


# ---------------------------------------------------------------------------
# 2. Frontend — batch call pattern verification (static analysis)
# ---------------------------------------------------------------------------

class TestFrontendBatchCallPattern:
    """Static analysis of index.html to confirm the N+1 pattern is gone."""

    @pytest.fixture
    def html_content(self):
        html_path = Path(__file__).parent.parent / "src" / "app" / "static" / "index.html"
        return html_path.read_text()

    def test_frontend_uses_batch_endpoint(self, html_content):
        """index.html calls /products/average-ratings/batch."""
        assert "/products/average-ratings/batch" in html_content

    def test_frontend_does_not_use_n1_promise_all_pattern(self, html_content):
        """The old N+1 pattern (Promise.all with per-product calls) is removed."""
        # The old pattern made individual calls inside Promise.all per product
        # It used map() + individual /average-rating calls
        old_pattern_regex = r"productIds\.map\(.*average-rating"
        assert not re.search(old_pattern_regex, html_content, re.DOTALL), \
            "N+1 pattern detected: productIds.map() with per-product average-rating calls still present"

    def test_frontend_no_individual_per_product_rating_calls_in_loadratings(self, html_content):
        """loadRatings() does not call the individual /products/{id}/average-rating endpoint."""
        # Extract loadRatings function body
        match = re.search(
            r"async function loadRatings\(productIds\)\s*\{(.*?)\n\s*\}",
            html_content,
            re.DOTALL,
        )
        assert match, "loadRatings function not found in index.html"
        func_body = match.group(1)

        # The individual per-product endpoint should not be called inside loadRatings
        assert "/products/' + id + '/average-rating" not in func_body
        assert "average-ratings/batch" in func_body, \
            "loadRatings() should use batch endpoint"

    def test_frontend_batch_call_joins_ids(self, html_content):
        """The batch call joins product IDs with commas."""
        assert "productIds.join(',')" in html_content or \
               "productIds.join(\"," in html_content, \
            "Frontend should join product IDs as comma-separated string"

    def test_frontend_has_fallback_on_batch_failure(self, html_content):
        """loadRatings() has a catch block as fallback when batch call fails."""
        # Find the loadRatings function and the next function declaration
        # to bound the search area (avoiding greedy regex issues with nested braces)
        start = html_content.find("async function loadRatings(productIds)")
        assert start != -1, "loadRatings function not found in index.html"
        # Find the next function declaration after loadRatings
        next_func = html_content.find("async function ", start + 1)
        if next_func == -1:
            next_func = start + 1000  # fallback bound
        func_region = html_content[start:next_func]
        assert "catch" in func_region, (
            "loadRatings() should have a catch block for fallback on batch call failure"
        )


# ---------------------------------------------------------------------------
# 3. Deployment YAML — init container fix verification (static analysis)
# ---------------------------------------------------------------------------

class TestInitContainerDeploymentFix:
    """Static analysis of deployment-backend.yaml to confirm init container fix."""

    @pytest.fixture
    def deployment_yaml(self):
        yaml_path = (
            Path(__file__).parent.parent
            / "helm" / "templates" / "deployment-backend.yaml"
        )
        return yaml_path.read_text()

    def test_init_container_does_not_use_ubi_minimal_image(self, deployment_yaml):
        """Init container no longer references registry.access.redhat.com/ubi9/ubi-minimal."""
        assert "registry.access.redhat.com" not in deployment_yaml, \
            "External Red Hat registry reference still present in deployment"
        assert "ubi-minimal" not in deployment_yaml, \
            "ubi-minimal image still referenced in deployment"

    def test_init_container_uses_backend_image_reference(self, deployment_yaml):
        """Init container image uses the backend Helm values reference."""
        assert ".Values.image.backend.repository" in deployment_yaml
        assert ".Values.image.backend.tag" in deployment_yaml

    def test_init_container_uses_python_not_shell(self, deployment_yaml):
        """Init container command uses python instead of sh/bash."""
        # Find the wait-for-postgres initContainer block
        assert "- python" in deployment_yaml, \
            "Init container should use 'python' command, not 'sh'"
        assert "microdnf" not in deployment_yaml, \
            "microdnf package install should not be present in init container"

    def test_init_container_uses_socket_create_connection(self, deployment_yaml):
        """Python wait script uses socket.create_connection for TCP check."""
        assert "socket.create_connection" in deployment_yaml, \
            "Init container should use Python socket.create_connection()"

    def test_init_container_does_not_install_bash(self, deployment_yaml):
        """Init container no longer installs bash at runtime."""
        assert "install" not in deployment_yaml or "microdnf" not in deployment_yaml, \
            "Init container should not run runtime package installs"
        # More specific check
        assert "microdnf install" not in deployment_yaml

    def test_init_container_has_timeout_logic(self, deployment_yaml):
        """Python wait script has a max_wait timeout and exits with non-zero on timeout."""
        assert "max_wait" in deployment_yaml
        assert "sys.exit(1)" in deployment_yaml, \
            "Init container should exit non-zero on timeout"

    def test_init_container_image_matches_backend_container_image(self, deployment_yaml):
        """Init container and main backend container use the same image reference."""
        # Both should reference .Values.image.backend.repository and .Values.image.backend.tag
        backend_image_ref = '"{{ .Values.image.backend.repository }}:{{ .Values.image.backend.tag }}"'
        count = deployment_yaml.count(backend_image_ref)
        assert count >= 2, (
            f"Expected backend image reference to appear at least twice "
            f"(init container + main container), found {count}"
        )
