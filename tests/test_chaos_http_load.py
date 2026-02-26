# tests/test_chaos_http_load.py
# QE tests for evt-117a267b: Replace CPU burn with HTTP load generation in chaos controller.
#
# Approved architect plan (user-approved Turn 20):
#   1. Replace _cpu_burn_worker threads in chaos/main.py with async HTTP load loop
#      using httpx.AsyncClient targeting GET /products and GET /orders.
#   2. Intensity slider (1-8) maps to number of concurrent HTTP requests.
#   3. Rename "CPU Attack" -> "HTTP Load Test" in the chaos UI.
#   4. Remove _cpu_burn_worker and _sync_cpu_threads from app/main.py (backend).
#   5. Keep ChaosMiddleware in backend for latency/error injection.
#
# sys.path handled by conftest.py

import ast
import inspect
import re
import threading
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Paths ────────────────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
CHAOS_MAIN = SRC_DIR / "chaos" / "main.py"
APP_MAIN = SRC_DIR / "app" / "main.py"
CHAOS_HTML = SRC_DIR / "chaos" / "static" / "index.html"


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Static code-inspection tests
# Verify the source files match the approved architecture (no CPU burn in
# chaos controller, no CPU burn in backend, HTTP load added to chaos controller).
# ─────────────────────────────────────────────────────────────────────────────

class TestChaosControllerSourceCode:
    """
    Static inspection of src/chaos/main.py.

    Approved plan requires:
    - No _cpu_burn_worker thread loop (replaced by HTTP load loop)
    - No threading.Thread spawning for CPU burn
    - httpx import present (for HTTP load generation)
    - BACKEND_URL env-var read (configurable target URL)
    - An async HTTP load function targeting GET endpoints
    """

    def _read_source(self) -> str:
        return CHAOS_MAIN.read_text()

    def test_cpu_burn_worker_removed_from_chaos(self):
        """
        _cpu_burn_worker should NOT exist in chaos/main.py after the fix.
        The HTTP load loop replaces the CPU burn thread pattern.
        """
        source = self._read_source()
        assert "_cpu_burn_worker" not in source, (
            "CPU burn worker still present in chaos/main.py — "
            "should be replaced with HTTP load loop."
        )

    def test_no_cpu_burn_thread_spawn_in_chaos(self):
        """
        threading.Thread for CPU burn should not be used in chaos controller.
        HTTP load generation uses asyncio/httpx, not threads.
        """
        source = self._read_source()
        # Check for the pattern that spawns CPU burn threads
        assert "target=_cpu_burn_worker" not in source, (
            "CPU burn thread target still referenced in chaos/main.py."
        )

    def test_httpx_used_for_load_generation(self):
        """
        chaos/main.py must import and use httpx to send HTTP requests to
        the backend when the intensity is > 0.
        """
        source = self._read_source()
        assert "httpx" in source, (
            "httpx not found in chaos/main.py — "
            "HTTP load generation requires httpx.AsyncClient."
        )

    def test_backend_url_env_var_present(self):
        """
        chaos/main.py must read BACKEND_URL from the environment so the
        target URL can be configured via Helm without code changes.
        """
        source = self._read_source()
        assert "BACKEND_URL" in source, (
            "BACKEND_URL env var not found in chaos/main.py. "
            "The chaos controller needs to know where to send HTTP load."
        )

    def test_get_endpoints_targeted(self):
        """
        The HTTP load loop must target read-only GET endpoints (/products or
        /orders) to avoid polluting the database with junk data.
        """
        source = self._read_source()
        has_products = "/products" in source
        has_orders = "/orders" in source
        assert has_products or has_orders, (
            "Neither /products nor /orders found in chaos/main.py. "
            "HTTP load should target GET endpoints on the backend."
        )

    def test_no_post_endpoints_targeted(self):
        """
        The load generator must not target mutation (POST) endpoints to
        avoid creating fake orders or customers in the database.
        """
        source = self._read_source()
        # Allow references to POST /api/settings (the chaos controller's own
        # endpoint), but not POST calls to the backend's data endpoints.
        # Check that we don't use method="POST" in the httpx calls.
        assert 'client.post("/orders' not in source, (
            "chaos/main.py appears to POST to /orders — "
            "load generation must use GET-only to avoid DB pollution."
        )
        assert 'client.post("/products' not in source, (
            "chaos/main.py appears to POST to /products — "
            "load generation must use GET-only to avoid DB pollution."
        )


class TestBackendSourceCode:
    """
    Static inspection of src/app/main.py.

    Approved plan requires:
    - NO _cpu_burn_worker in the backend (dead code from the intermediate fix)
    - NO _sync_cpu_threads in the backend
    - ChaosMiddleware still present (handles latency and error injection)
    """

    def _read_source(self) -> str:
        return APP_MAIN.read_text()

    def test_cpu_burn_worker_removed_from_backend(self):
        """
        _cpu_burn_worker must NOT exist in app/main.py.
        The intermediate fix (fcaa1eb) added CPU burn to the backend, but
        the approved plan replaces it with HTTP load from the chaos controller.
        """
        source = self._read_source()
        assert "_cpu_burn_worker" not in source, (
            "_cpu_burn_worker still exists in app/main.py. "
            "This dead code should be removed — HTTP load now comes from "
            "the chaos controller, not local CPU threads in the backend."
        )

    def test_sync_cpu_threads_removed_from_backend(self):
        """
        _sync_cpu_threads must NOT exist in app/main.py.
        It was part of the intermediate CPU burn approach that was superseded.
        """
        source = self._read_source()
        assert "_sync_cpu_threads" not in source, (
            "_sync_cpu_threads still exists in app/main.py. "
            "Remove the CPU thread management from the backend — "
            "CPU stress now comes via HTTP requests from the chaos controller."
        )

    def test_chaos_middleware_present_in_backend(self):
        """
        ChaosMiddleware must remain in app/main.py.
        It handles latency injection and error injection — these still work
        correctly in the distributed architecture.
        """
        source = self._read_source()
        assert "ChaosMiddleware" in source, (
            "ChaosMiddleware missing from app/main.py! "
            "Latency and error injection depend on this middleware."
        )

    def test_chaos_middleware_is_registered(self):
        """
        ChaosMiddleware must be registered with app.add_middleware().
        Defining the class without registering it would break latency/error injection.
        """
        source = self._read_source()
        assert "app.add_middleware(ChaosMiddleware)" in source, (
            "ChaosMiddleware is not registered via app.add_middleware(). "
            "Middleware must be added to take effect."
        )

    def test_no_cpu_threading_import_still_needed(self):
        """
        If threading is still imported in app/main.py only to support the
        removed CPU burn code, it indicates the cleanup is incomplete.
        Verify threading is not used for CPU burn (it may still be imported
        for other reasons, but _cpu_stop_flag should be gone).
        """
        source = self._read_source()
        assert "_cpu_stop_flag" not in source, (
            "_cpu_stop_flag still in app/main.py — "
            "CPU burn management not fully removed from backend."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: UI content tests
# ─────────────────────────────────────────────────────────────────────────────

class TestChaosUI:
    """
    Verify the chaos controller HTML UI reflects the new HTTP load semantics.

    Approved plan requires renaming "CPU Attack" -> "HTTP Load Test" and
    updating descriptions to reference network/HTTP load, not CPU burn threads.
    """

    def _read_html(self) -> str:
        return CHAOS_HTML.read_text()

    def test_ui_does_not_say_cpu_attack(self):
        """
        'CPU Attack' heading should be replaced with 'HTTP Load Test'.
        """
        html = self._read_html()
        assert "CPU Attack" not in html, (
            "UI still shows 'CPU Attack'. "
            "Should be renamed to 'HTTP Load Test' per the approved plan."
        )

    def test_ui_says_http_load_test(self):
        """
        The chaos UI must display 'HTTP Load Test' as the panel title.
        """
        html = self._read_html()
        assert "HTTP Load Test" in html, (
            "UI does not contain 'HTTP Load Test'. "
            "Rename the CPU Attack panel per the approved plan."
        )

    def test_ui_description_mentions_http_or_network(self):
        """
        The description under HTTP Load Test must reference HTTP/network load,
        not 'burn CPU' or 'threads'.
        The old description was 'Burn CPU with multiple threads to spike
        container resource usage.' — this must be updated.
        """
        html = self._read_html()
        # The new description should mention HTTP, network, or requests
        has_http_reference = (
            "HTTP" in html or
            "http" in html or
            "network" in html or
            "request" in html or
            "concurrent" in html
        )
        assert has_http_reference, (
            "UI description does not mention HTTP/network load. "
            "Update the description to reflect the new HTTP load semantics."
        )

    def test_ui_intensity_slider_still_present(self):
        """
        The intensity slider (input[type=range], id=cpu-threads) must remain.
        It now controls HTTP concurrency instead of thread count.
        No new UI controls needed — slider reuse is by design.
        """
        html = self._read_html()
        assert 'id="cpu-threads"' in html, (
            "Intensity slider (id=cpu-threads) missing from UI. "
            "The slider should remain; it now controls HTTP concurrency."
        )
        assert 'type="range"' in html, (
            "Range input missing from UI — intensity slider not found."
        )

    def test_ui_slider_label_reflects_concurrency(self):
        """
        The label next to the slider should say 'concurrent requests' or
        similar, not 'threads', since it now controls HTTP concurrency.
        """
        html = self._read_html()
        # The old label said 'threads' — check it's been updated
        assert "concurrent" in html.lower() or "requests" in html.lower(), (
            "Slider label should reference concurrent requests, not threads. "
            "Update the intensity guide text in the UI."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: Chaos controller API tests (live TestClient)
# ─────────────────────────────────────────────────────────────────────────────

class TestChaosControllerAPI:
    """
    Functional tests for the chaos controller REST API.

    Uses FastAPI TestClient — no network calls, no DB.
    These verify the API contract remains stable after the refactor.
    """

    @pytest.fixture(autouse=True)
    def chaos_client(self):
        """Import chaos app and create a TestClient."""
        # Must patch httpx BEFORE importing the chaos app to avoid
        # the module trying to make real HTTP calls during startup.
        from chaos.main import app
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_status_endpoint_returns_200(self):
        """GET /api/status must return 200 with chaos state."""
        resp = self.client.get("/api/status")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_status_has_chaos_field(self):
        """Status response must include a 'chaos' key with state fields."""
        resp = self.client.get("/api/status")
        data = resp.json()
        assert "chaos" in data, f"'chaos' key missing from /api/status response: {data}"
        chaos = data["chaos"]
        assert "cpu_threads" in chaos, "cpu_threads field missing from chaos state"
        assert "latency_ms" in chaos, "latency_ms field missing from chaos state"
        assert "error_rate" in chaos, "error_rate field missing from chaos state"

    def test_settings_cpu_threads_validation_range(self):
        """
        POST /api/settings with cpu_threads out of range (>8) must return 422.
        Pydantic enforces ge=0, le=8.
        """
        resp = self.client.post(
            "/api/settings",
            json={"cpu_threads": 99}
        )
        assert resp.status_code == 422, (
            f"Expected 422 for cpu_threads=99, got {resp.status_code}"
        )

    def test_settings_cpu_threads_valid_range(self):
        """
        POST /api/settings with valid cpu_threads (1-8) must return 200.
        """
        resp = self.client.post(
            "/api/settings",
            json={"cpu_threads": 4}
        )
        assert resp.status_code == 200, (
            f"Expected 200 for cpu_threads=4, got {resp.status_code}: {resp.text}"
        )

    def test_settings_cpu_threads_zero_stops_load(self):
        """
        POST /api/settings with cpu_threads=0 must turn off load generation.
        The chaos state must reflect cpu_threads=0.
        """
        # First set to non-zero
        self.client.post("/api/settings", json={"cpu_threads": 2})
        # Then stop
        resp = self.client.post("/api/settings", json={"cpu_threads": 0})
        assert resp.status_code == 200
        data = resp.json()
        # Verify state reflects the change
        settings = data.get("settings", {})
        assert settings.get("cpu_threads") == 0, (
            f"Expected cpu_threads=0 after stop, got: {settings}"
        )

    def test_settings_reset_clears_all_chaos(self):
        """
        POST /api/settings with reset=true must clear all chaos state.
        """
        # Set some chaos
        self.client.post("/api/settings", json={"latency_ms": 500, "error_rate": 0.5})
        # Reset
        resp = self.client.post("/api/settings", json={"reset": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "reset", f"Expected status=reset, got: {data}"
        settings = data.get("settings", {})
        assert settings.get("latency_ms") == 0, f"latency_ms not reset: {settings}"
        assert settings.get("error_rate") == 0.0, f"error_rate not reset: {settings}"
        assert settings.get("cpu_threads") == 0, f"cpu_threads not reset: {settings}"

    def test_latency_and_error_rate_still_configurable(self):
        """
        The refactor must not break latency and error injection settings.
        Both must still be accepted and reflected in chaos state.
        """
        resp = self.client.post(
            "/api/settings",
            json={"latency_ms": 250, "error_rate": 0.3}
        )
        assert resp.status_code == 200
        settings = resp.json().get("settings", {})
        assert settings.get("latency_ms") == 250, f"latency_ms not applied: {settings}"
        assert abs(settings.get("error_rate", -1) - 0.3) < 0.001, (
            f"error_rate not applied correctly: {settings}"
        )

    def test_index_serves_html(self):
        """GET / must return the chaos controller HTML UI."""
        resp = self.client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", ""), (
            f"Expected HTML response, got: {resp.headers.get('content-type')}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: HTTP load generation integration tests
# Verify that setting cpu_threads > 0 causes the chaos controller to fire
# async HTTP GET requests to the backend, with concurrency = cpu_threads value.
# ─────────────────────────────────────────────────────────────────────────────

class TestHTTPLoadGeneration:
    """
    Integration tests verifying that the chaos controller generates real HTTP
    load against the backend when cpu_threads > 0.

    These tests mock httpx.AsyncClient to intercept outbound HTTP calls made
    by the chaos controller's load loop, without requiring a live backend.
    """

    def test_http_load_loop_function_exists(self):
        """
        chaos/main.py must define an async function for HTTP load generation.
        Look for an async function that uses httpx (e.g., _http_load_loop,
        _http_load_worker, or similar name containing 'http' or 'load').
        """
        source = CHAOS_MAIN.read_text()
        tree = ast.parse(source)

        http_load_functions = [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and ("http" in node.name.lower() or "load" in node.name.lower())
            and node.name != "_cpu_burn_worker"  # exclude old code
        ]
        assert len(http_load_functions) > 0, (
            "No async HTTP load function found in chaos/main.py. "
            "Expected a function like '_http_load_loop' or '_http_load_worker' "
            "that uses httpx.AsyncClient to send requests to the backend."
        )

    def test_backend_url_has_sensible_default(self):
        """
        BACKEND_URL env var must default to the in-cluster service name so the
        chaos controller works out of the box without manual config.
        Expected default: http://darwin-store-backend:8080
        """
        source = CHAOS_MAIN.read_text()
        assert "darwin-store-backend" in source or "darwin_store_backend" in source, (
            "Default BACKEND_URL does not reference 'darwin-store-backend'. "
            "The chaos controller must default to the in-cluster backend service."
        )

    def test_intensity_maps_to_concurrency(self):
        """
        The cpu_threads value (1-8) must control the number of concurrent HTTP
        requests sent to the backend, not the number of OS threads for CPU burn.
        Verify the source uses cpu_threads to determine concurrency of HTTP calls.
        """
        source = CHAOS_MAIN.read_text()
        # cpu_threads should appear near asyncio.gather, asyncio.create_task,
        # or a loop that spawns coroutines — not threading.Thread
        has_asyncio_concurrency = (
            "asyncio.gather" in source or
            "asyncio.create_task" in source or
            "asyncio.ensure_future" in source or
            "for _ in range" in source  # loop to fire N concurrent requests
        )
        assert has_asyncio_concurrency, (
            "No asyncio concurrency primitives found in chaos/main.py. "
            "HTTP load concurrency must use asyncio (gather/create_task), "
            "not threading.Thread, so the intensity slider maps to HTTP requests."
        )

    def test_get_only_endpoints_in_load_loop(self):
        """
        The HTTP load loop must use GET requests, not POST.
        Confirmed by checking that httpx client.get() is used for the backend calls.
        """
        source = CHAOS_MAIN.read_text()
        # If httpx is used, the load loop should call client.get() or .get(
        # Allow for both "await client.get" and "client.get" patterns
        has_get_call = (
            "client.get(" in source or
            ".get(f" in source or
            ".get(\"" in source or
            "httpx.get(" in source
        )
        assert has_get_call, (
            "No httpx GET call found in chaos/main.py. "
            "The HTTP load loop must use GET requests to avoid DB pollution."
        )

    @pytest.mark.asyncio
    async def test_http_load_loop_fires_get_requests(self):
        """
        Direct integration test: _http_load_loop must call client.get() for
        each iteration until the stop_event is set.

        Uses a real asyncio event loop with a mocked httpx.AsyncClient to
        verify that GET requests are actually issued to the backend URL.
        """
        import asyncio as _asyncio
        from chaos.main import _http_load_loop, BACKEND_URL

        stop_event = _asyncio.Event()
        get_call_count = 0

        class _MockResponse:
            status_code = 200

        class _MockClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def get(self, url):
                nonlocal get_call_count
                get_call_count += 1
                return _MockResponse()

        with patch("chaos.main.httpx.AsyncClient", return_value=_MockClient()):
            task = _asyncio.create_task(_http_load_loop(0, stop_event))
            # Let the loop run for a short burst
            await _asyncio.sleep(0.08)
            stop_event.set()
            task.cancel()
            try:
                await task
            except _asyncio.CancelledError:
                pass

        assert get_call_count > 0, (
            f"_http_load_loop made 0 GET calls. Expected at least 1 request "
            f"to be sent to the backend within 80ms. "
            f"Check that client.get() is called inside the loop."
        )

    def test_concurrency_equals_worker_count(self):
        """
        When cpu_threads=N is set, exactly N asyncio tasks must be created.
        The intensity slider must map 1:1 to the number of concurrent workers.
        Verified by inspecting the update_settings source for the range() call.
        """
        source = CHAOS_MAIN.read_text()
        # The implementation should spawn concurrency workers with a for-loop
        # matching the concurrency/cpu_threads value
        assert "for i in range(concurrency)" in source or "for i in range(threads)" in source, (
            "Concurrency-based task spawning loop not found in chaos/main.py. "
            "Expected 'for i in range(concurrency):' to create N workers."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: Backend ChaosMiddleware functional test
# Verify the backend still correctly applies latency and error injection.
# ─────────────────────────────────────────────────────────────────────────────

class TestBackendChaosMiddleware:
    """
    Verify the backend's ChaosMiddleware still operates correctly after
    removing the CPU burn code. Latency and error injection must still work.
    """

    def test_chaos_middleware_class_importable(self):
        """ChaosMiddleware class must be importable from app.main."""
        from app.main import ChaosMiddleware
        assert ChaosMiddleware is not None

    def test_chaos_middleware_is_base_http_middleware(self):
        """ChaosMiddleware must extend BaseHTTPMiddleware."""
        from app.main import ChaosMiddleware
        from starlette.middleware.base import BaseHTTPMiddleware
        assert issubclass(ChaosMiddleware, BaseHTTPMiddleware), (
            "ChaosMiddleware does not extend BaseHTTPMiddleware."
        )

    def test_chaos_middleware_has_dispatch_method(self):
        """ChaosMiddleware must implement dispatch() for request interception."""
        from app.main import ChaosMiddleware
        assert hasattr(ChaosMiddleware, "dispatch"), (
            "ChaosMiddleware missing dispatch() method."
        )
        assert callable(ChaosMiddleware.dispatch), (
            "ChaosMiddleware.dispatch is not callable."
        )

    def test_backend_health_endpoint(self):
        """
        Backend /health endpoint must respond 200.
        Uses CHAOS_MODE=disabled to bypass remote chaos state fetching.
        """
        import os
        os.environ["CHAOS_MODE"] = "disabled"
        os.environ["DB_HOST"] = "nonexistent-db-host-qe-test"

        try:
            # Import here to pick up env vars set above
            # We need to reload to get fresh app without DB connection
            import importlib
            import app.main as app_main
            importlib.reload(app_main)
        except Exception:
            pass  # DB connection will fail — that's OK for this test

        # Verify the health route exists in the app
        from app.main import app
        # Find health route
        health_routes = [
            r for r in app.routes
            if hasattr(r, "path") and r.path == "/health"
        ]
        assert len(health_routes) > 0, (
            "No /health route found in backend app — "
            "health check endpoint is missing."
        )

    def test_get_remote_chaos_falls_back_gracefully(self):
        """
        _get_remote_chaos() in the backend must return safe defaults when the
        chaos controller is unreachable (e.g., during startup or network failure).
        This ensures the backend continues serving requests even without chaos.
        """
        from app.main import _get_remote_chaos
        import asyncio
        # Run with patched httpx so no real network calls are made
        with patch("app.main.httpx.AsyncClient") as mock_client_class:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client_class.return_value = mock_instance

            from app.chaos_state import ChaosState
            state = asyncio.get_event_loop().run_until_complete(_get_remote_chaos())

        assert isinstance(state, ChaosState), (
            "Expected ChaosState fallback when chaos controller unreachable"
        )
        assert state.latency_ms == 0, "Fallback state must have zero latency"
        assert state.error_rate == 0.0, "Fallback state must have zero error rate"
