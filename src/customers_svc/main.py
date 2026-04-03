# @ai-rules:
# 1. [CHAOS_MODE]: Env var gates ChaosMiddleware. "disabled" = middleware short-circuits.
# 2. [Middleware order]: ChaosMiddleware must be added before routes. AdminAuth runs first.
# 3. [Domain]: Customer service owns customers, orders, order_items, invoices, admin_settings tables.
# 4. [Port]: Runs on port 8082.
"""
Darwin Store - Customer Management Service entry point.

Handles customers, orders, invoices, dashboard, and admin authentication.
Runs as a separate FastAPI process on port 8082.
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
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .routes.customers import router as customers_router
from .routes.orders import router as orders_router
from .routes.invoices import router as invoices_router
from .routes.dashboard import router as dashboard_router
from .routes.auth import router as auth_router, validate_session
from .inventory_client import InventoryClient
from ..app.chaos_state import ChaosState, record_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVICE_NAME = os.getenv("SERVICE_NAME", "darwin-store-customers")
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
    """Middleware for chaos injection in the customer service."""

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


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """Protect /admin route with session-based authentication."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/admin":
            if not validate_session(request):
                return RedirectResponse(url="/?auth_error=1", status_code=303)
        return await call_next(request)


app = FastAPI(
    title="Darwin Store - Customer Management Service",
    description="Customer lifecycle, orders, invoices, dashboard, and admin auth",
    version=SERVICE_VERSION
)

app.add_middleware(ChaosMiddleware)
app.add_middleware(AdminAuthMiddleware)

app.include_router(customers_router)
app.include_router(orders_router)
app.include_router(invoices_router)
app.include_router(dashboard_router)
app.include_router(auth_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "customers_online", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.on_event("startup")
async def startup_event():
    """Initialize database connection and create customer-owned tables."""
    global db_pool

    logger.info(f"Customer service starting. Chaos mode: {CHAOS_MODE}")

    # Initialize inventory client on app state
    app.state.inventory_client = InventoryClient()

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
                CREATE TABLE IF NOT EXISTS customers (
                    id UUID PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id UUID PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT NOW(),
                    total_amount REAL NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    customer_id UUID REFERENCES customers(id)
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS order_items (
                    id UUID PRIMARY KEY,
                    order_id UUID NOT NULL REFERENCES orders(id),
                    product_id UUID NOT NULL,
                    quantity INTEGER NOT NULL,
                    price_at_purchase REAL NOT NULL
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS invoices (
                    id UUID PRIMARY KEY,
                    invoice_number SERIAL UNIQUE,
                    order_id UUID NOT NULL UNIQUE REFERENCES orders(id),
                    customer_id UUID REFERENCES customers(id),
                    customer_snapshot JSONB NOT NULL,
                    line_items JSONB NOT NULL,
                    subtotal REAL NOT NULL,
                    coupon_code VARCHAR(50),
                    discount_amount REAL DEFAULT 0.0,
                    grand_total REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS admin_settings (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    password_hash VARCHAR(255) NOT NULL,
                    CONSTRAINT single_row CHECK (id = 1)
                )
            ''')
            conn.commit()
            logger.info("Customer tables created or verified.")

            # Seed default admin password
            import bcrypt
            default_hash = bcrypt.hashpw(b"darwin2026", bcrypt.gensalt()).decode("utf-8")
            cur.execute(
                "INSERT INTO admin_settings (id, password_hash) VALUES (1, %s) ON CONFLICT (id) DO NOTHING",
                (default_hash,)
            )
            conn.commit()
            logger.info("Admin settings initialized")

            # Migrations
            try:
                cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id)")
                cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()")
                cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(50)")
                cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_amount REAL DEFAULT 0.0")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS company VARCHAR(255)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS phone VARCHAR(50)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_street VARCHAR(255)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_city VARCHAR(255)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_state VARCHAR(100)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_zip VARCHAR(20)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_country VARCHAR(100)")
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
