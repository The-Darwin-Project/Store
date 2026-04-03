# @ai-rules:
# 1. [CHAOS_MODE]: Env var gates ChaosMiddleware. "disabled" = middleware short-circuits.
# 2. [Middleware order]: ChaosMiddleware must be added before routes.
# 3. [Domain]: Inventory service owns products, suppliers, alerts, coupons, campaigns, reviews tables.
# 4. [Port]: Runs on port 8081.
"""
Darwin Store - Inventory Service entry point.

Handles product catalog, suppliers, alerts, coupons, campaigns, and reviews.
Runs as a separate FastAPI process on port 8081.
"""

import os
import asyncio
import random
import logging
import time
from typing import Optional
import psycopg2
from psycopg2.pool import SimpleConnectionPool
import httpx

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .routes.products import router as products_router
from .routes.suppliers import router as suppliers_router
from .routes.alerts import router as alerts_router
from .routes.coupons import router as coupons_router
from .routes.campaigns import router as campaigns_router
from .routes.reviews import router as reviews_router
from .routes.internal import router as internal_router
from ..app.chaos_state import ChaosState, record_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVICE_NAME = os.getenv("SERVICE_NAME", "darwin-store-inventory")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
CHAOS_MODE = os.getenv("CHAOS_MODE", "disabled")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "darwin")
DB_USER = os.getenv("DB_USER", "darwin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "darwin")

CHAOS_CONTROLLER_URL = os.getenv("CHAOS_CONTROLLER_URL", "http://darwin-store-chaos:9000")

db_pool: Optional[SimpleConnectionPool] = None

_chaos_cache: dict = {"state": None, "expires": 0.0}
CHAOS_CACHE_TTL = 1.0


async def _get_remote_chaos() -> ChaosState:
    """Fetch chaos state from the chaos controller service via HTTP."""
    now = time.time()
    if _chaos_cache["state"] is not None and now < _chaos_cache["expires"]:
        return _chaos_cache["state"]
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{CHAOS_CONTROLLER_URL}/api/status")
            if resp.status_code == 200:
                data = resp.json().get("chaos", {})
                state = ChaosState(**data)
                _chaos_cache["state"] = state
                _chaos_cache["expires"] = now + CHAOS_CACHE_TTL
                return state
    except Exception:
        pass
    return ChaosState()


class ChaosMiddleware(BaseHTTPMiddleware):
    """Middleware for chaos injection in the inventory service."""

    async def dispatch(self, request: Request, call_next):
        if CHAOS_MODE == "disabled":
            return await call_next(request)

        chaos = await _get_remote_chaos()

        if chaos.latency_ms > 0:
            await asyncio.sleep(chaos.latency_ms / 1000.0)

        if chaos.error_rate > 0 and random.random() < chaos.error_rate:
            record_request(is_error=True)
            return Response(
                content='{"error": "Chaos injection - simulated failure"}',
                status_code=500,
                media_type="application/json"
            )

        response = await call_next(request)
        is_error = response.status_code >= 500
        record_request(is_error=is_error)
        return response


app = FastAPI(
    title="Darwin Store - Inventory Service",
    description="Product catalog, suppliers, alerts, coupons, campaigns, and reviews",
    version=SERVICE_VERSION
)

app.add_middleware(ChaosMiddleware)

app.include_router(products_router)
app.include_router(suppliers_router)
app.include_router(alerts_router)
app.include_router(coupons_router)
app.include_router(campaigns_router)
app.include_router(reviews_router)
app.include_router(internal_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "inventory_online", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.on_event("startup")
async def startup_event():
    """Initialize database connection and create inventory-owned tables."""
    global db_pool

    logger.info(f"Inventory service starting. Chaos mode: {CHAOS_MODE}")

    db_dsn = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    max_retries = 5
    retry_delay = 2
    for attempt in range(1, max_retries + 1):
        try:
            db_pool = SimpleConnectionPool(1, 10, dsn=db_dsn)
            app.state.db_pool = db_pool
            logger.info(f"Database connection pool established (attempt {attempt})")
            break
        except psycopg2.OperationalError as e:
            if attempt < max_retries:
                logger.warning(f"Database connection attempt {attempt}/{max_retries} failed: {e}. Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                raise

    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS suppliers (
                    id UUID PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    contact_email VARCHAR(255),
                    phone VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
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
                CREATE TABLE IF NOT EXISTS alerts (
                    id UUID PRIMARY KEY,
                    type VARCHAR(50) NOT NULL DEFAULT 'restock',
                    message TEXT NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'active',
                    product_id UUID REFERENCES products(id),
                    supplier_id UUID REFERENCES suppliers(id),
                    current_stock INTEGER,
                    reorder_threshold INTEGER,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS coupons (
                    id UUID PRIMARY KEY,
                    code VARCHAR(50) NOT NULL UNIQUE,
                    discount_type VARCHAR(20) NOT NULL,
                    discount_value REAL NOT NULL,
                    min_order_amount REAL DEFAULT 0.0,
                    max_uses INTEGER DEFAULT 0,
                    current_uses INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS reviews (
                    id UUID PRIMARY KEY,
                    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    customer_id UUID NOT NULL,
                    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(product_id, customer_id)
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS campaigns (
                    id UUID PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    type VARCHAR(20) NOT NULL CHECK (type IN ('banner', 'discount_promo', 'product_spotlight')),
                    content TEXT DEFAULT '',
                    image_url TEXT,
                    link_url TEXT,
                    coupon_code VARCHAR(50),
                    product_id UUID REFERENCES products(id),
                    start_date TIMESTAMP NOT NULL,
                    end_date TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    priority INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT valid_date_range CHECK (end_date > start_date)
                )
            ''')
            conn.commit()
            logger.info("Inventory tables created or verified.")

            # Migrations
            try:
                cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''")
                cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_id UUID REFERENCES suppliers(id)")
                cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS reorder_threshold INTEGER DEFAULT 10")
                cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS sale_price REAL")
                cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS discount_percent REAL")
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
    """Close database connections on shutdown."""
    global db_pool
    if db_pool:
        db_pool.closeall()
        logger.info("Database connection pool closed.")
