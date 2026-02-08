# Store/src/chaos/main.py
"""
Darwin Chaos Controller - Fault injection API.

Provides endpoints to inject chaos into the Darwin Store:
- CPU load spikes
- Artificial latency
- Error injection

Runs on port 9000, separate from Store (port 8080).
"""

import threading
import time
import logging
from pathlib import Path
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Use absolute import from src package
# When running as `uvicorn src.chaos.main:app`, src is the root package
from src.app.chaos_state import get_chaos, set_chaos, reset_chaos, ChaosState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CPU burn thread management
_cpu_threads: list[threading.Thread] = []
_cpu_stop_flag = threading.Event()
CPU_BURN_THREADS = 4  # Number of parallel burn threads

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
        "cpu_threads_total": CPU_BURN_THREADS,
        "memory_chunks": memory_chunks,
        "memory_allocated_mb": memory_chunks * 10
    }


@app.post("/api/settings")
async def update_settings(body: dict = None):
    """
    Update service runtime settings.

    Accepts a JSON body with any combination of:
      cpu_threads: int (0-8)
      memory_mb: int (0-1024)
      latency_ms: int (0-30000)
      error_rate: float (0.0-1.0)
      reset: bool
    """
    global _cpu_threads, _memory_buffer

    if not body:
        return {"status": "current", "settings": asdict(get_chaos())}

    result = {}

    # Reset all
    if body.get("reset"):
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
    if "cpu_threads" in body:
        threads = max(0, min(8, int(body["cpu_threads"])))
        if _cpu_threads:
            _cpu_stop_flag.set()
            for t in _cpu_threads:
                if t.is_alive():
                    t.join(timeout=2.0)
            _cpu_threads = []
            _cpu_stop_flag.clear()
        if threads > 0:
            set_chaos(cpu_load=True)
            for i in range(threads):
                t = threading.Thread(target=_cpu_burn_worker, args=(i,), daemon=True)
                t.start()
                _cpu_threads.append(t)
            result["cpu"] = {"threads": threads, "active": True}
        else:
            set_chaos(cpu_load=False)
            result["cpu"] = {"threads": 0, "active": False}

    # Memory
    if "memory_mb" in body:
        mb = max(0, min(1024, int(body["memory_mb"])))
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
    if "latency_ms" in body:
        ms = max(0, min(30000, int(body["latency_ms"])))
        set_chaos(latency_ms=ms)
        result["latency_ms"] = ms

    # Error rate
    if "error_rate" in body:
        rate = max(0.0, min(1.0, float(body["error_rate"])))
        set_chaos(error_rate=rate)
        result["error_rate"] = rate

    logger.info(f"Settings updated: {result}")
    return {"status": "updated", "applied": result, "settings": asdict(get_chaos())}


# Mount static files (must be after routes)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
