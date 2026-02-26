# Store/src/app/main.py
# @ai-rules:
# 1. [CHAOS_MODE]: Env var gates ChaosMiddleware. "disabled" = middleware short-circuits. Only affects latency/error injection.
# 2. [Middleware order]: ChaosMiddleware must be added before routes. It wraps all incoming requests.
# 3. [Discovery]: Service discovery via darwin.io/* K8s annotations on the Deployment. No app-side telemetry.
"""
Darwin Store - FastAPI application entry point.

A self-aware vulnerable application that:
1. Exposes product CRUD endpoints
2. Accepts chaos injection from the Chaos Controller
3. Discovered by Darwin Brain via K8s annotations (darwin.io/*)
"""

import os
import asyncio
import random
import logging
import time
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
import httpx

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .routes.products import router as products_router
from .routes.orders import router as orders_router
from .routes.customers import router as customers_router
from .routes.suppliers import router as suppliers_router
from .routes.dashboard import router as dashboard_router
from .routes.alerts import router as alerts_router
from .routes.coupons import router as coupons_router
from .routes.invoices import router as invoices_router
from .routes.reviews import router as reviews_router
from .routes.campaigns import router as campaigns_router
from .routes.auth import router as auth_router, validate_session
from .chaos_state import ChaosState, record_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
SERVICE_NAME = os.getenv("SERVICE_NAME", "darwin-store")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
CHAOS_MODE = os.getenv("CHAOS_MODE", "disabled")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "darwin")
DB_USER = os.getenv("DB_USER", "darwin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "darwin")

CHAOS_CONTROLLER_URL = os.getenv("CHAOS_CONTROLLER_URL", "http://darwin-store-chaos:9000")

db_pool: Optional[SimpleConnectionPool] = None

# Simple cache for chaos state fetched from chaos controller (avoid HTTP call on every request)
_chaos_cache: dict = {"state": None, "expires": 0.0}
CHAOS_CACHE_TTL = 1.0  # seconds


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
    return ChaosState()  # Safe default: no chaos


class ChaosMiddleware(BaseHTTPMiddleware):
    """
    Middleware for chaos injection.

    Fetches chaos state from the chaos controller via HTTP and applies:
    - Latency injection (delay requests)
    - Error injection (return 500s probabilistically)
    - Error rate tracking
    """

    async def dispatch(self, request: Request, call_next):
        # Gate: skip chaos injection when CHAOS_MODE is disabled.
        # NOTE: Only gates latency/error injection (middleware).
        # CPU load testing is handled by the chaos controller via HTTP requests.
        if CHAOS_MODE == "disabled":
            return await call_next(request)

        # Fetch current chaos state from chaos controller via HTTP
        chaos = await _get_remote_chaos()
        
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


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """Protect /admin route with session-based authentication."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/admin":
            if not validate_session(request):
                return RedirectResponse(url="/?auth_error=1", status_code=303)
        return await call_next(request)


# Create FastAPI app
app = FastAPI(
    title="Darwin Store",
    description="Self-aware vulnerable application for Darwin demos",
    version=SERVICE_VERSION
)

# Add middleware (Starlette processes in reverse order: AdminAuth runs first, then Chaos)
app.add_middleware(ChaosMiddleware)
app.add_middleware(AdminAuthMiddleware)

# Mount routes
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(customers_router)
app.include_router(suppliers_router)
app.include_router(dashboard_router)
app.include_router(alerts_router)
app.include_router(coupons_router)
app.include_router(invoices_router)
app.include_router(reviews_router)
app.include_router(campaigns_router)
app.include_router(auth_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "store_online", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup."""
    global db_pool
    
    logger.info(f"Chaos mode: {CHAOS_MODE}")

    # Initialize Database Connection
    db_dsn = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
    max_retries = 5
    retry_delay = 2  # seconds
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
                    product_id UUID NOT NULL REFERENCES products(id),
                    quantity INTEGER NOT NULL,
                    price_at_purchase REAL NOT NULL
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
            cur.execute('''
                CREATE TABLE IF NOT EXISTS reviews (
                    id UUID PRIMARY KEY,
                    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    customer_id UUID NOT NULL REFERENCES customers(id),
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
            logger.info("Database initialized and 'products', 'orders', 'order_items', 'coupons', 'invoices' tables created or verified.")

            # Seed default admin password (ON CONFLICT DO NOTHING keeps existing password)
            import bcrypt
            default_hash = bcrypt.hashpw(b"darwin2026", bcrypt.gensalt()).decode("utf-8")
            cur.execute(
                "INSERT INTO admin_settings (id, password_hash) VALUES (1, %s) ON CONFLICT (id) DO NOTHING",
                (default_hash,)
            )
            conn.commit()
            logger.info("Admin settings initialized")

            # Migration: Ensure description column exists for existing databases
            try:
                cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''")
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration warning: {e}")

            # Migration: Ensure customer_id column exists on orders for existing databases
            try:
                cur.execute("""
                    ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id)
                """)
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration warning (customer_id): {e}")

            # Migration: Add updated_at column to orders
            try:
                cur.execute("""
                    ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()
                """)
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration warning (updated_at): {e}")

            # Migration: Add supplier_id to products
            try:
                cur.execute("""
                    ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_id UUID REFERENCES suppliers(id)
                """)
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration warning (supplier_id): {e}")

            # Migration: Add reorder_threshold to products
            try:
                cur.execute("""
                    ALTER TABLE products ADD COLUMN IF NOT EXISTS reorder_threshold INTEGER DEFAULT 10
                """)
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration warning (reorder_threshold): {e}")

            # Migration: Add coupon_code column to orders
            try:
                cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(50)")
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration warning (coupon_code): {e}")

            # Migration: Add discount_amount column to orders
            try:
                cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_amount REAL DEFAULT 0.0")
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration warning (discount_amount): {e}")

            # Migration: Add shipping address fields to customers
            try:
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS company VARCHAR(255)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS phone VARCHAR(50)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_street VARCHAR(255)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_city VARCHAR(255)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_state VARCHAR(100)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_zip VARCHAR(20)")
                cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS shipping_country VARCHAR(100)")
                conn.commit()
            except Exception as e:
                logger.warning(f"Migration warning (customer address fields): {e}")
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


# Trigger CI
