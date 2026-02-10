# Store/src/app/routes/products.py
# @ai-rules:
# 1. [Pattern]: PUT = full replacement (all fields required). PATCH = partial update (only provided fields applied).
# 2. [Constraint]: PATCH uses model_dump(exclude_unset=True) to distinguish "not sent" from "sent as null".
# 3. [Gotcha]: PUT intentionally overwrites image_data -- callers must send all fields. Frontend uses PATCH.
"""Product CRUD endpoints for Darwin Store."""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional
import uuid

from ..models import Product, ProductCreate, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])

@router.get("", response_model=list[Product])
async def list_products(request: Request) -> list[Product]:
    """List all products in the store."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, price, stock, sku, image_data FROM products")
            products = [Product(id=str(row[0]), name=row[1], price=row[2], stock=row[3], sku=row[4], image_data=row[5]) for row in cur.fetchall()]
            return products
    finally:
        pool.putconn(conn)


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str, request: Request) -> Product:
    """Get a single product by ID."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, price, stock, sku, image_data FROM products WHERE id = %s", (product_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Product not found")
            return Product(id=str(row[0]), name=row[1], price=row[2], stock=row[3], sku=row[4], image_data=row[5])
    finally:
        pool.putconn(conn)


@router.post("", response_model=Product, status_code=201)
async def create_product(product: ProductCreate, request: Request) -> Product:
    """Create a new product."""
    new_id = uuid.uuid4()
    new_product = Product(
        id=str(new_id),
        name=product.name,
        price=product.price,
        stock=product.stock,
        sku=product.sku,
        image_data=product.image_data
    )
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO products (id, name, price, stock, sku, image_data) VALUES (%s, %s, %s, %s, %s, %s)",
                (new_product.id, new_product.name, new_product.price, new_product.stock, new_product.sku, new_product.image_data)
            )
            conn.commit()
            return new_product
    finally:
        pool.putconn(conn)


@router.put("/{product_id}", response_model=Product)
async def update_product(product_id: str, product: ProductCreate, request: Request) -> Product:
    """Update an existing product."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE products
                SET name = %s, price = %s, stock = %s, sku = %s, image_data = COALESCE(%s, image_data)
                WHERE id = %s
                RETURNING id, name, price, stock, sku, image_data
                """,
                (product.name, product.price, product.stock, product.sku, product.image_data, product_id)
            )
            row = cur.fetchone()
            conn.commit()
            if not row:
                raise HTTPException(status_code=404, detail="Product not found")
            return Product(id=str(row[0]), name=row[1], price=row[2], stock=row[3], sku=row[4], image_data=row[5])
    finally:
        pool.putconn(conn)


@router.patch("/{product_id}", response_model=Product)
async def patch_product(product_id: str, updates: ProductUpdate, request: Request) -> Product:
    """Partially update a product. Only provided fields are changed; omitted fields are preserved."""
    provided = updates.model_dump(exclude_unset=True)
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Fetch existing product
            cur.execute("SELECT id, name, price, stock, sku, image_data FROM products WHERE id = %s", (product_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Product not found")
            existing = Product(id=str(row[0]), name=row[1], price=row[2], stock=row[3], sku=row[4], image_data=row[5])

            # No-op: empty body returns existing product unchanged
            if not provided:
                return existing

            # Merge provided fields over existing
            merged = existing.model_copy(update=provided)
            cur.execute(
                "UPDATE products SET name = %s, price = %s, stock = %s, sku = %s, image_data = %s WHERE id = %s",
                (merged.name, merged.price, merged.stock, merged.sku, merged.image_data, product_id)
            )
            conn.commit()
            return merged
    finally:
        pool.putconn(conn)


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: str, request: Request) -> None:
    """Delete a product by ID."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Product not found")
    finally:
        pool.putconn(conn)
