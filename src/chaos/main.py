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

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# Use absolute import from src package
# When running as `uvicorn src.chaos.main:app`, src is the root package
from src.app.chaos_state import get_chaos, set_chaos, reset_chaos, ChaosState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CPU burn thread management
_cpu_thread: threading.Thread | None = None
_cpu_stop_flag = threading.Event()


def _cpu_burn_worker():
    """
    Burns CPU until stop flag is set.
    
    Runs in the Chaos Controller process (port 9000).
    psutil.cpu_percent() in Store process captures container-wide CPU.
    """
    logger.info("CPU burn started")
    while not _cpu_stop_flag.is_set():
        # Busy loop - burns CPU at container level
        _ = sum(i * i for i in range(10000))
        # Brief yield to allow stop check
        time.sleep(0.001)
    logger.info("CPU burn stopped")


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
    return {
        "chaos": asdict(chaos),
        "cpu_thread_alive": _cpu_thread is not None and _cpu_thread.is_alive()
    }


@app.post("/api/attack/cpu")
async def attack_cpu():
    """
    Toggle CPU burn attack.
    
    First call starts burning CPU, second call stops it.
    """
    global _cpu_thread
    chaos = get_chaos()
    
    if chaos.cpu_load:
        # Stop existing burn
        _cpu_stop_flag.set()
        if _cpu_thread and _cpu_thread.is_alive():
            _cpu_thread.join(timeout=1.0)
        set_chaos(cpu_load=False)
        _cpu_stop_flag.clear()
        return {"status": "cpu_attack_stopped", "cpu_load": False}
    else:
        # Start new burn
        set_chaos(cpu_load=True)
        _cpu_stop_flag.clear()
        _cpu_thread = threading.Thread(target=_cpu_burn_worker, daemon=True)
        _cpu_thread.start()
        return {"status": "cpu_attack_started", "cpu_load": True}


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
    set_chaos(error_rate=rate)
    return {"status": "error_rate_set", "error_rate": rate}


@app.post("/api/reset")
async def reset():
    """Reset all chaos state and stop CPU burn."""
    global _cpu_thread
    
    # Stop CPU burn if running
    _cpu_stop_flag.set()
    if _cpu_thread and _cpu_thread.is_alive():
        _cpu_thread.join(timeout=1.0)
    _cpu_stop_flag.clear()
    _cpu_thread = None
    
    # Reset state file
    reset_chaos()
    
    return {"status": "reset_complete", "chaos": asdict(ChaosState())}


# Mount static files (must be after routes)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
