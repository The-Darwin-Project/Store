# Store/src/chaos/main.py
"""
Darwin Chaos Controller - Fault injection API.

Provides endpoints to inject chaos into the Darwin Store:
- CPU load spikes
- Artificial latency
- Error injection

Runs on port 9000, separate from Store (port 8080).
"""

import os
import threading
import time
import logging
from pathlib import Path
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
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


@app.post("/api/attack/cpu")
async def attack_cpu(
    threads: int = Query(None, ge=0, le=8, description="Number of burn threads (0 to stop, 1-8 for intensity)")
):
    """
    Control CPU burn attack intensity.
    
    Args:
        threads: Number of CPU burn threads (0=stop, 1-8=intensity level)
                 If not provided, toggles on/off with default threads
    """
    global _cpu_threads
    chaos = get_chaos()
    
    # Determine action
    if threads is not None:
        # Explicit thread count specified
        should_burn = threads > 0
        thread_count = threads
    else:
        # Toggle mode
        should_burn = not chaos.cpu_load
        thread_count = CPU_BURN_THREADS
    
    # Stop existing burn first
    if _cpu_threads:
        _cpu_stop_flag.set()
        for thread in _cpu_threads:
            if thread.is_alive():
                thread.join(timeout=2.0)
        _cpu_threads = []
        _cpu_stop_flag.clear()
    
    if not should_burn or thread_count == 0:
        # Stop burning
        set_chaos(cpu_load=False)
        return {"status": "cpu_attack_stopped", "cpu_load": False, "threads": 0}
    
    # Start new burn with specified threads
    set_chaos(cpu_load=True)
    _cpu_stop_flag.clear()
    for i in range(thread_count):
        thread = threading.Thread(target=_cpu_burn_worker, args=(i,), daemon=True)
        thread.start()
        _cpu_threads.append(thread)
    
    logger.info(f"Started {thread_count} CPU burn threads")
    return {"status": "cpu_attack_started", "cpu_load": True, "threads": thread_count}


@app.post("/api/attack/memory")
async def attack_memory(mb: int = Query(0, ge=0, le=1024, description="Memory to allocate in MB (0 to release)")):
    """
    Control memory pressure attack.
    
    Args:
        mb: Amount of memory to allocate in MB (0=release, max 1024MB=1GB)
    """
    global _memory_buffer
    
    with _memory_lock:
        # Release existing memory first
        if _memory_buffer:
            old_size = len(_memory_buffer) * 10  # Each chunk is ~10MB
            _memory_buffer.clear()
            logger.info(f"Released ~{old_size}MB of memory")
        
        if mb == 0:
            set_chaos(memory_load_mb=0)
            return {"status": "memory_released", "memory_load_mb": 0}
        
        # Allocate memory in 10MB chunks to avoid single large allocation
        chunk_size = 10 * 1024 * 1024  # 10MB per chunk
        chunks_needed = mb // 10
        
        try:
            for i in range(chunks_needed):
                # Allocate and fill with data (prevents memory from being optimized away)
                chunk = bytearray(chunk_size)
                # Write to memory to ensure it's actually allocated
                for j in range(0, len(chunk), 4096):
                    chunk[j] = i % 256
                _memory_buffer.append(chunk)
            
            actual_mb = len(_memory_buffer) * 10
            set_chaos(memory_load_mb=actual_mb)
            logger.info(f"Allocated {actual_mb}MB of memory ({len(_memory_buffer)} chunks)")
            return {"status": "memory_allocated", "memory_load_mb": actual_mb, "chunks": len(_memory_buffer)}
        
        except MemoryError as e:
            # Partial allocation - release what we got
            actual_mb = len(_memory_buffer) * 10
            set_chaos(memory_load_mb=actual_mb)
            logger.warning(f"Memory allocation partial: got {actual_mb}MB of requested {mb}MB")
            return {"status": "memory_partial", "memory_load_mb": actual_mb, "requested_mb": mb, "error": str(e)}


@app.post("/api/attack/latency")
async def attack_latency(ms: int = Query(500, ge=0, le=30000)):
    """
    Set artificial latency for Store requests.
    
    Args:
        ms: Latency in milliseconds (0 to disable)
    """
    set_chaos(latency_ms=ms)
    return {"status": "latency_set", "latency_ms": ms}


@app.post("/api/attack/errors")
async def attack_errors(rate: float = Query(0.5, ge=0.0, le=1.0)):
    """
    Set error injection rate for Store requests.
    
    Args:
        rate: Probability of error (0.0 to 1.0, where 1.0 = 100% errors)
    """
    if os.environ.get("CHAOS_MODE", "enabled").lower() == "disabled":
        raise HTTPException(status_code=403, detail="Chaos mode is disabled")
    
    set_chaos(error_rate=rate)
    return {"status": "error_rate_set", "error_rate": rate}


@app.post("/api/reset")
async def reset():
    """Reset all chaos state, stop CPU burn, and release memory."""
    global _cpu_threads, _memory_buffer
    
    # Stop CPU burn if running
    _cpu_stop_flag.set()
    for thread in _cpu_threads:
        if thread.is_alive():
            thread.join(timeout=2.0)
    _cpu_threads = []
    _cpu_stop_flag.clear()
    
    # Release memory
    with _memory_lock:
        _memory_buffer.clear()
    
    # Reset state file
    reset_chaos()
    
    return {"status": "reset_complete", "chaos": asdict(ChaosState())}


# Mount static files (must be after routes)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
