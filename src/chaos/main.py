# Store/src/chaos/main.py
# @ai-rules:
# 1. [Single endpoint]: All mutations go through POST /api/settings with ChaosSettings Pydantic model.
# 2. [Memory cap]: MEMORY_CAP_MB must stay aligned with container limit (320Mi) minus base overhead (~120Mi).
# 3. [In-process state]: _cpu_threads and _memory_buffer are process-local; only the state file crosses processes.
# 4. [No Query import]: Old GET endpoints were removed. Do not re-add fastapi.Query.
"""
Darwin Chaos Controller - Fault injection API.

Provides endpoints to inject chaos into the Darwin Store:
- CPU load spikes
- Memory pressure
- Artificial latency
- Error injection

Runs on port 9000, separate from Store (port 8080).
"""

import threading
import logging
from pathlib import Path
from dataclasses import asdict
from typing import Optional

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


class ChaosSettings(BaseModel):
    """Request body for POST /api/settings."""
    cpu_threads: Optional[int] = Field(None, ge=0, le=8)
    memory_mb: Optional[int] = Field(None, ge=0, le=MEMORY_CAP_MB)
    latency_ms: Optional[int] = Field(None, ge=0, le=30000)
    error_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    reset: Optional[bool] = None


# CPU burn thread management
_cpu_threads: list[threading.Thread] = []
_cpu_stop_flag = threading.Event()

# Memory burn management
_memory_buffer: list[bytearray] = []  # Holds allocated memory
_memory_lock = threading.Lock()


def _cpu_burn_worker(worker_id: int):
    """
    Burns CPU until stop flag is set.
    
    Uses aggressive busy loop to actually spike container CPU.
    Multiple threads needed to saturate multi-core containers.
    """
    logger.info(f"CPU burn worker {worker_id} started")
    
    # Tight busy loop with no sleep - actually burns CPU
    counter = 0
    while not _cpu_stop_flag.is_set():
        # Heavy computation - runs for ~10-20ms per iteration
        for _ in range(100):
            _ = sum(x * x * x for x in range(50000))
        
        counter += 1
        # Check stop flag every ~100 iterations
        if counter % 100 == 0:
            pass  # Just check the flag
    
    logger.info(f"CPU burn worker {worker_id} stopped")


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
    active_threads = sum(1 for t in _cpu_threads if t.is_alive())
    memory_chunks = len(_memory_buffer)
    return {
        "chaos": asdict(chaos),
        "cpu_threads_active": active_threads,
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
    global _cpu_threads, _memory_buffer

    if body is None:
        return {"status": "current", "settings": asdict(get_chaos())}

    result = {}

    # Reset all
    if body.reset:
        _cpu_stop_flag.set()
        for t in _cpu_threads:
            if t.is_alive():
                t.join(timeout=2.0)
        _cpu_threads = []
        _cpu_stop_flag.clear()
        with _memory_lock:
            _memory_buffer.clear()
        reset_chaos()
        logger.info("Settings reset to defaults")
        return {"status": "reset", "settings": asdict(get_chaos())}

    # CPU threads
    if body.cpu_threads is not None:
        threads = body.cpu_threads
        if _cpu_threads:
            _cpu_stop_flag.set()
            for t in _cpu_threads:
                if t.is_alive():
                    t.join(timeout=2.0)
            _cpu_threads = []
            _cpu_stop_flag.clear()
        if threads > 0:
            set_chaos(cpu_threads=threads)
            for i in range(threads):
                t = threading.Thread(target=_cpu_burn_worker, args=(i,), daemon=True)
                t.start()
                _cpu_threads.append(t)
            result["cpu"] = {"threads": threads, "active": True}
        else:
            set_chaos(cpu_threads=0)
            result["cpu"] = {"threads": 0, "active": False}

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
