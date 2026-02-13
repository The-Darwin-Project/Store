# Store/src/app/main.py
# @ai-rules:
# 1. [CHAOS_MODE]: Env var gates ChaosMiddleware. "disabled" = middleware short-circuits. Only affects latency/error injection.
# 2. [Middleware order]: ChaosMiddleware must be added before routes. It wraps all incoming requests.
# 3. [Telemetry]: DarwinClient runs as a daemon thread, not async. Do not await it.
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
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .routes.products import router as products_router
from .routes.orders import router as orders_router
from .darwin_client import DarwinClient  # DEPRECATED: Use darwin.io/* annotations. Will be removed in a future release.
from .chaos_state import get_chaos, record_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
SERVICE_NAME = os.getenv("SERVICE_NAME", "darwin-store")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
DARWIN_URL = os.getenv("DARWIN_URL", "http://darwin-blackboard-brain:8000")
CHAOS_MODE = os.getenv("CHAOS_MODE", "disabled")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "darwin")
DB_USER = os.getenv("DB_USER", "darwin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "darwin")
DARWIN_READ_TIMEOUT = float(os.getenv("DARWIN_READ_TIMEOUT", "5.0"))


# Darwin telemetry client (initialized on startup)
darwin_client: Optional[DarwinClient] = None
db_pool: Optional[SimpleConnectionPool] = None


class ChaosMiddleware(BaseHTTPMiddleware):
    """
    Middleware for chaos injection.
    
    Reads chaos state from shared file and applies:
    - Latency injection (delay requests)
    - Error injection (return 500s probabilistically)
    - Error rate tracking
    """
    
    async def dispatch(self, request: Request, call_next):
        # Gate: skip chaos injection when CHAOS_MODE is disabled.
        # NOTE: Only gates latency/error injection (middleware).
        # CPU/memory attacks are direct resource consumption in the chaos process.
        if CHAOS_MODE == "disabled":
            return await call_next(request)

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
app.include_router(orders_router)


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
    """Initialize Darwin telemetry client and database connection on startup."""
    global darwin_client, db_pool
    
    # Initialize Darwin Client (DEPRECATED: use darwin.io/* annotations instead; will be removed in a future release)
    if DARWIN_URL:
        darwin_client = DarwinClient(
            service=SERVICE_NAME,
            url=DARWIN_URL,
            version=SERVICE_VERSION,
            read_timeout=DARWIN_READ_TIMEOUT
        )
        darwin_client.start()
        logger.info(f"Darwin telemetry started: {SERVICE_NAME} -> {DARWIN_URL}")
    else:
        logger.warning("DARWIN_URL not set, telemetry disabled")
    
    logger.info(f"Chaos mode: {CHAOS_MODE}")

    # Initialize Database Connection
    db_dsn = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    db_pool = SimpleConnectionPool(1, 10, dsn=db_dsn)
    app.state.db_pool = db_pool
    
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id UUID PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    price REAL NOT NULL,
                    stock INTEGER NOT NULL,
                    sku VARCHAR(255) NOT NULL UNIQUE,
                    image_data TEXT,
                    description TEXT DEFAULT ''
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id UUID PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT NOW(),
                    total_amount REAL NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending'
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS order_items (
                    id UUID PRIMARY KEY,
                    order_id UUID NOT NULL REFERENCES orders(id),
                    product_id UUID NOT NULL REFERENCES products(id),
                    quantity INTEGER NOT NULL,
                    price_at_purchase REAL NOT NULL
                )
            ''')
            conn.commit()
            logger.info("Database initialized and 'products', 'orders', 'order_items' tables created or verified.")

            # Migration: Ensure description column exists for existing databases
            try:
                cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''")
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration warning: {e}")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    finally:
        if conn:
            db_pool.putconn(conn)


@app.on_event("shutdown")
async def shutdown_event():
    """Stop Darwin telemetry client and close database connections on shutdown."""
    global darwin_client, db_pool
    
    if darwin_client:
        darwin_client.stop()
        logger.info("Darwin telemetry stopped")
    
    if db_pool:
        db_pool.closeall()
        logger.info("Database connection pool closed.")


# Mount static files (must be after routes)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Trigger CI
