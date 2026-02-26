# Store/src/chaos/main.py
# @ai-rules:
# 1. [Single endpoint]: All mutations go through POST /api/settings with ChaosSettings Pydantic model.
# 2. [Memory cap]: MEMORY_CAP_MB must stay aligned with container limit (320Mi) minus base overhead (~120Mi).
# 3. [HTTP load]: cpu_threads (1-8) maps to HTTP concurrency against the backend. Uses GET-only to avoid DB pollution.
# 4. [No Query import]: Old GET endpoints were removed. Do not re-add fastapi.Query.
"""
Darwin Chaos Controller - Fault injection API.

Provides endpoints to inject chaos into the Darwin Store:
- HTTP load testing (concurrent GET requests to backend)
- Memory pressure
- Artificial latency
- Error injection

Runs on port 9000, separate from Store (port 8080).
"""

import os
import asyncio
import threading
import logging
from pathlib import Path
from dataclasses import asdict
from typing import Optional

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Use absolute import from src package
# When running as `uvicorn src.chaos.main:app`, src is the root package
from src.app.chaos_state import get_chaos, set_chaos, reset_chaos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Max safe chaos memory: container limit (320Mi) minus base overhead (~120Mi)
MEMORY_CAP_MB = 200

# Backend URL for HTTP load testing (resolved via K8s service DNS)
BACKEND_URL = os.getenv("BACKEND_URL", "http://darwin-store-backend:8080")

# GET endpoints to cycle through for load generation (no DB writes)
_LOAD_ENDPOINTS = ["/products", "/orders", "/customers", "/health"]


class ChaosSettings(BaseModel):
    """Request body for POST /api/settings."""
    cpu_threads: Optional[int] = Field(None, ge=0, le=8)
    memory_mb: Optional[int] = Field(None, ge=0, le=MEMORY_CAP_MB)
    latency_ms: Optional[int] = Field(None, ge=0, le=30000)
    error_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    reset: Optional[bool] = None


# HTTP load task management
_load_tasks: list[asyncio.Task] = []
_load_stop_event: Optional[asyncio.Event] = None

# Memory burn management
_memory_buffer: list[bytearray] = []  # Holds allocated memory
_memory_lock = threading.Lock()


async def _http_load_loop(worker_id: int, stop_event: asyncio.Event):
    """
    Send continuous GET requests to the backend until stopped.

    Each worker cycles through _LOAD_ENDPOINTS, generating real HTTP
    traffic that exercises the full backend stack (FastAPI routing,
    Pydantic validation, DB queries).
    """
    logger.info(f"HTTP load worker {worker_id} started -> {BACKEND_URL}")
    idx = worker_id  # Start each worker at a different endpoint offset
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=5.0) as client:
        while not stop_event.is_set():
            endpoint = _LOAD_ENDPOINTS[idx % len(_LOAD_ENDPOINTS)]
            try:
                await client.get(endpoint)
            except Exception:
                pass  # Backend may be slow/down under load; keep hammering
            idx += 1
            # Tiny yield to avoid starving the event loop
            await asyncio.sleep(0.01)
    logger.info(f"HTTP load worker {worker_id} stopped")


async def _stop_load_tasks():
    """Signal all HTTP load workers to stop and wait for them to finish."""
    global _load_tasks, _load_stop_event
    if _load_stop_event is not None:
        _load_stop_event.set()
    for task in _load_tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _load_tasks = []
    _load_stop_event = None


# Create FastAPI app
app = FastAPI(
    title="Darwin Chaos Controller",
    description="Fault injection API for Darwin demos",
    version="1.0.0"
)


@app.get("/")
async def index():
    """Serve the Chaos UI."""
    static_dir = Path(__file__).parent / "static"
    index_file = static_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text())
    return HTMLResponse(content="<h1>Chaos Controller</h1><p>Static files not found</p>")


@app.get("/api/status")
async def get_status():
    """Get current chaos state."""
    chaos = get_chaos()
    active_workers = sum(1 for t in _load_tasks if not t.done())
    memory_chunks = len(_memory_buffer)
    return {
        "chaos": asdict(chaos),
        "cpu_threads_active": active_workers,
        "memory_chunks": memory_chunks,
        "memory_allocated_mb": memory_chunks * 10
    }


@app.post("/api/settings")
async def update_settings(body: ChaosSettings = None):
    """
    Update chaos injection settings.

    Accepts a JSON body validated by ChaosSettings model.
    All fields are optional; only provided fields are applied.
    Pydantic enforces ranges (e.g., cpu_threads 0-8, memory_mb 0-MEMORY_CAP_MB).
    """
    global _load_tasks, _load_stop_event, _memory_buffer

    if body is None:
        return {"status": "current", "settings": asdict(get_chaos())}

    result = {}

    # Reset all
    if body.reset:
        await _stop_load_tasks()
        with _memory_lock:
            _memory_buffer.clear()
        reset_chaos()
        logger.info("Settings reset to defaults")
        return {"status": "reset", "settings": asdict(get_chaos())}

    # HTTP load (mapped from cpu_threads slider: 1-8 = concurrency level)
    if body.cpu_threads is not None:
        concurrency = body.cpu_threads
        await _stop_load_tasks()
        if concurrency > 0:
            set_chaos(cpu_threads=concurrency)
            _load_stop_event = asyncio.Event()
            for i in range(concurrency):
                task = asyncio.create_task(_http_load_loop(i, _load_stop_event))
                _load_tasks.append(task)
            result["http_load"] = {"concurrency": concurrency, "active": True, "target": BACKEND_URL}
        else:
            set_chaos(cpu_threads=0)
            result["http_load"] = {"concurrency": 0, "active": False}

    # Memory
    if body.memory_mb is not None:
        mb = body.memory_mb
        with _memory_lock:
            _memory_buffer.clear()
            if mb > 0:
                chunk_size = 10 * 1024 * 1024
                for i in range(mb // 10):
                    try:
                        chunk = bytearray(chunk_size)
                        for j in range(0, len(chunk), 4096):
                            chunk[j] = i % 256
                        _memory_buffer.append(chunk)
                    except MemoryError:
                        break
            actual = len(_memory_buffer) * 10
            set_chaos(memory_load_mb=actual)
            result["memory_mb"] = actual

    # Latency
    if body.latency_ms is not None:
        set_chaos(latency_ms=body.latency_ms)
        result["latency_ms"] = body.latency_ms

    # Error rate
    if body.error_rate is not None:
        set_chaos(error_rate=body.error_rate)
        result["error_rate"] = body.error_rate

    logger.info(f"Settings updated: {result}")
    return {"status": "updated", "applied": result, "settings": asdict(get_chaos())}


# Mount static files (must be after routes)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
