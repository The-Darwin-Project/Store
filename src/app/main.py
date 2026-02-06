# Store/src/app/main.py
"""
Darwin Store - FastAPI application entry point.

A self-aware vulnerable application that:
1. Exposes product CRUD endpoints
2. Streams telemetry to Darwin BlackBoard
3. Accepts chaos injection from the Chaos Controller
"""

import os
import asyncio
import random
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .routes.products import router as products_router
from .darwin_client import DarwinClient
from .chaos_state import get_chaos, record_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
SERVICE_NAME = os.getenv("SERVICE_NAME", "darwin-store")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
DARWIN_URL = os.getenv("DARWIN_URL", "http://darwin-blackboard-brain:8000")

# Darwin telemetry client (initialized on startup)
darwin_client: Optional[DarwinClient] = None


class ChaosMiddleware(BaseHTTPMiddleware):
    """
    Middleware for chaos injection.
    
    Reads chaos state from shared file and applies:
    - Latency injection (delay requests)
    - Error injection (return 500s probabilistically)
    - Error rate tracking
    """
    
    async def dispatch(self, request: Request, call_next):
        # Read current chaos state from shared file
        chaos = get_chaos()
        
        # 1. Latency injection
        if chaos.latency_ms > 0:
            await asyncio.sleep(chaos.latency_ms / 1000.0)
        
        # 2. Error injection (probabilistic)
        if chaos.error_rate > 0 and random.random() < chaos.error_rate:
            record_request(is_error=True)
            return Response(
                content='{"error": "Chaos injection - simulated failure"}',
                status_code=500,
                media_type="application/json"
            )
        
        # 3. Normal request processing
        response = await call_next(request)
        
        # 4. Track actual errors
        is_error = response.status_code >= 500
        record_request(is_error=is_error)
        
        return response


# Create FastAPI app
app = FastAPI(
    title="Darwin Store",
    description="Self-aware vulnerable application for Darwin demos",
    version=SERVICE_VERSION
)

# Add chaos middleware
app.add_middleware(ChaosMiddleware)

# Mount routes
app.include_router(products_router)


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the Store UI."""
    static_dir = Path(__file__).parent / "static"
    index_file = static_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text())
    return HTMLResponse(content="<h1>Darwin Store</h1><p>Static files not found</p>")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "store_online", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.on_event("startup")
async def startup_event():
    """Initialize Darwin telemetry client on startup."""
    global darwin_client
    
    if DARWIN_URL:
        darwin_client = DarwinClient(
            service=SERVICE_NAME,
            url=DARWIN_URL,
            version=SERVICE_VERSION
        )
        darwin_client.start()
        logger.info(f"Darwin telemetry started: {SERVICE_NAME} -> {DARWIN_URL}")
    else:
        logger.warning("DARWIN_URL not set, telemetry disabled")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop Darwin telemetry client on shutdown."""
    global darwin_client
    
    if darwin_client:
        darwin_client.stop()
        logger.info("Darwin telemetry stopped")


# Mount static files (must be after routes)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Trigger CI
