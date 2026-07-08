# @ai-rules:
# 1. [Pattern]: PUT = full replacement (all fields required). PATCH = partial update (only provided fields applied).
# 2. [Constraint]: PATCH uses model_dump(exclude_unset=True) to distinguish "not sent" from "sent as null".
# 3. [Gotcha]: PUT intentionally overwrites image_data -- callers must send all fields. Frontend uses PATCH.
"""Product CRUD endpoints for Inventory Service."""

from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
import uuid

from ..models import PaginatedResponse, Product, ProductCreate, ProductUpdate
from .alerts import check_and_create_alert

router = APIRouter(prefix="/products", tags=["products"])

@router.get("")
async def list_products(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    category_id: Optional[str] = Query(None, description="Filter by category"),
) -> PaginatedResponse[Product]:
    """List products with pagination."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            if category_id:
                cur.execute("SELECT COUNT(*) FROM products WHERE category_id = %s", (category_id,))
            else:
                cur.execute("SELECT COUNT(*) FROM products")
            total = cur.fetchone()[0]
            offset = (page - 1) * limit
            pages = (total + limit - 1) // limit if total > 0 else 0

            if category_id:
                cur.execute(
                    "SELECT id, name, price, stock, sku, image_data, description, "
                    "supplier_id, reorder_threshold, sale_price, discount_percent, category_id FROM products "
                    "WHERE category_id = %s ORDER BY name LIMIT %s OFFSET %s",
                    (category_id, limit, offset)
                )
            else:
                cur.execute(
                    "SELECT id, name, price, stock, sku, image_data, description, "
                    "supplier_id, reorder_threshold, sale_price, discount_percent, category_id FROM products "
                    "ORDER BY name LIMIT %s OFFSET %s",
                    (limit, offset)
                )
            products = [
                Product(
                    id=str(row[0]), name=row[1], price=row[2], stock=row[3],
                    sku=row[4], image_data=row[5], description=row[6],
                    supplier_id=str(row[7]) if row[7] else None,
                    reorder_threshold=row[8] if row[8] is not None else 10,
                    sale_price=row[9], discount_percent=row[10],
                    category_id=str(row[11]) if row[11] else None,
                )
                for row in cur.fetchall()
            ]
            return PaginatedResponse(
                items=products, total=total, page=page, limit=limit, pages=pages
            )
    finally:
        pool.putconn(conn)


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str, request: Request) -> Product:
    """Get a single product by ID."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, price, stock, sku, image_data, description, supplier_id, reorder_threshold, sale_price, discount_percent, category_id FROM products WHERE id = %s", (product_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Product not found")
            return Product(id=str(row[0]), name=row[1], price=row[2], stock=row[3], sku=row[4], image_data=row[5], description=row[6], supplier_id=str(row[7]) if row[7] else None, reorder_threshold=row[8] if row[8] is not None else 10, sale_price=row[9], discount_percent=row[10], category_id=str(row[11]) if row[11] else None)
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
        image_data=product.image_data,
        description=product.description,
        supplier_id=product.supplier_id,
        category_id=product.category_id,
        reorder_threshold=product.reorder_threshold,
        sale_price=product.sale_price,
        discount_percent=product.discount_percent,
    )
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO products (id, name, price, stock, sku, image_data, description, supplier_id, reorder_threshold, sale_price, discount_percent, category_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (new_product.id, new_product.name, new_product.price, new_product.stock, new_product.sku, new_product.image_data, new_product.description, new_product.supplier_id, new_product.reorder_threshold, new_product.sale_price, new_product.discount_percent, new_product.category_id)
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
                SET name = %s, price = %s, stock = %s, sku = %s, image_data = COALESCE(%s, image_data), description = %s, supplier_id = %s, reorder_threshold = %s, sale_price = %s, discount_percent = %s, category_id = %s
                WHERE id = %s
                RETURNING id, name, price, stock, sku, image_data, description, supplier_id, reorder_threshold, sale_price, discount_percent, category_id
                """,
                (product.name, product.price, product.stock, product.sku, product.image_data, product.description, product.supplier_id, product.reorder_threshold, product.sale_price, product.discount_percent, product.category_id, product_id)
            )
            row = cur.fetchone()
            conn.commit()
            if not row:
                raise HTTPException(status_code=404, detail="Product not found")
            return Product(id=str(row[0]), name=row[1], price=row[2], stock=row[3], sku=row[4], image_data=row[5], description=row[6], supplier_id=str(row[7]) if row[7] else None, reorder_threshold=row[8] if row[8] is not None else 10, sale_price=row[9], discount_percent=row[10], category_id=str(row[11]) if row[11] else None)
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
            cur.execute("SELECT id, name, price, stock, sku, image_data, description, supplier_id, reorder_threshold, sale_price, discount_percent, category_id FROM products WHERE id = %s", (product_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Product not found")
            existing = Product(id=str(row[0]), name=row[1], price=row[2], stock=row[3], sku=row[4], image_data=row[5], description=row[6], supplier_id=str(row[7]) if row[7] else None, reorder_threshold=row[8] if row[8] is not None else 10, sale_price=row[9], discount_percent=row[10], category_id=str(row[11]) if row[11] else None)

            if not provided:
                return existing

            merged = existing.model_copy(update=provided)
            cur.execute(
                "UPDATE products SET name = %s, price = %s, stock = %s, sku = %s, image_data = %s, description = %s, supplier_id = %s, reorder_threshold = %s, sale_price = %s, discount_percent = %s, category_id = %s WHERE id = %s",
                (merged.name, merged.price, merged.stock, merged.sku, merged.image_data, merged.description, merged.supplier_id, merged.reorder_threshold, merged.sale_price, merged.discount_percent, merged.category_id, product_id)
            )
            conn.commit()

            if 'stock' in provided or 'reorder_threshold' in provided:
                try:
                    check_and_create_alert(conn, product_id)
                except Exception:
                    pass

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


# Alias router: serves identical product CRUD under /catalog (API v2 migration)
catalog_router = APIRouter(prefix="/catalog", tags=["catalog"])

catalog_router.add_api_route("", list_products, methods=["GET"])
catalog_router.add_api_route("", create_product, methods=["POST"], status_code=201, response_model=Product)
catalog_router.add_api_route("/{product_id}", get_product, methods=["GET"])
catalog_router.add_api_route("/{product_id}", update_product, methods=["PUT"])
catalog_router.add_api_route("/{product_id}", patch_product, methods=["PATCH"])
catalog_router.add_api_route("/{product_id}", delete_product, methods=["DELETE"], status_code=204)
