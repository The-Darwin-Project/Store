# @ai-rules:
# 1. [Domain]: Internal endpoints for cross-service calls from Customer service.
# 2. [Security]: These endpoints are NOT exposed via nginx -- only accessible within the cluster.
# 3. [Atomicity]: Stock deduction uses UPDATE ... WHERE stock >= N to prevent overselling.
"""Internal API endpoints for cross-service communication."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..models import effective_price

router = APIRouter(prefix="/internal", tags=["internal"])


class StockDeductRequest(BaseModel):
    product_id: str
    quantity: int = Field(ge=1)


class StockDeductResponse(BaseModel):
    product_id: str
    price_at_purchase: float
    remaining_stock: int
    product_name: str


class StockRestoreRequest(BaseModel):
    product_id: str
    quantity: int = Field(ge=1)


class CouponUseRequest(BaseModel):
    coupon_id: str


@router.post("/stock-deduct", response_model=StockDeductResponse)
async def deduct_stock(body: StockDeductRequest, request: Request) -> StockDeductResponse:
    """Atomic stock deduction for order creation."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE products
                SET stock = stock - %s
                WHERE id = %s AND stock >= %s
                RETURNING id, name, price, stock, sale_price, discount_percent
                """,
                (body.quantity, body.product_id, body.quantity)
            )
            row = cur.fetchone()
            if not row:
                cur.execute("SELECT name, stock FROM products WHERE id = %s", (body.product_id,))
                product = cur.fetchone()
                if not product:
                    raise HTTPException(status_code=404, detail=f"Product {body.product_id} not found")
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for '{product[0]}' (available: {product[1]}, requested: {body.quantity})"
                )
            conn.commit()
            price_at_purchase = effective_price(row[2], row[4], row[5])
            return StockDeductResponse(
                product_id=str(row[0]),
                price_at_purchase=price_at_purchase,
                remaining_stock=row[3],
                product_name=row[1],
            )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Stock deduction failed: {str(e)}")
    finally:
        pool.putconn(conn)


@router.post("/stock-restore", status_code=200)
async def restore_stock(body: StockRestoreRequest, request: Request):
    """Restore stock on order cancel/return."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE products SET stock = stock + %s WHERE id = %s RETURNING id",
                (body.quantity, body.product_id)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Product {body.product_id} not found")
            conn.commit()
            return {"status": "restored", "product_id": body.product_id, "quantity": body.quantity}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Stock restore failed: {str(e)}")
    finally:
        pool.putconn(conn)


@router.post("/coupon-use", status_code=200)
async def increment_coupon_usage(body: CouponUseRequest, request: Request):
    """Atomic coupon usage increment."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE coupons SET current_uses = current_uses + 1 "
                "WHERE id = %s AND (max_uses = 0 OR current_uses < max_uses) RETURNING id",
                (body.coupon_id,)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail="Coupon usage limit reached")
            conn.commit()
            return {"status": "incremented", "coupon_id": body.coupon_id}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Coupon usage increment failed: {str(e)}")
    finally:
        pool.putconn(conn)
