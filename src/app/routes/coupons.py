"""Coupon CRUD and validation endpoints for Darwin Store."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from ..models import (
    Coupon, CouponCreate, CouponUpdate,
    CouponValidateRequest, CouponValidationResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coupons", tags=["coupons"])


def _row_to_coupon(row) -> Coupon:
    """Convert a DB row tuple to a Coupon model."""
    return Coupon(
        id=str(row[0]),
        code=row[1],
        discount_type=row[2],
        discount_value=row[3],
        min_order_amount=row[4] if row[4] is not None else 0.0,
        max_uses=row[5] if row[5] is not None else 0,
        current_uses=row[6] if row[6] is not None else 0,
        is_active=row[7] if row[7] is not None else True,
        expires_at=row[8],
        created_at=row[9],
    )


_COUPON_COLUMNS = (
    "id, code, discount_type, discount_value, min_order_amount, "
    "max_uses, current_uses, is_active, expires_at, created_at"
)


def validate_coupon_for_cart(conn, code: str, cart_total: float) -> tuple[Coupon, float]:
    """Validate a coupon and return (coupon, discount_amount).

    Raises HTTPException on validation failure.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COUPON_COLUMNS} FROM coupons WHERE UPPER(code) = UPPER(%s)",
            (code,)
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=400, detail="Coupon not found")

    coupon = _row_to_coupon(row)

    if not coupon.is_active:
        raise HTTPException(status_code=400, detail="Coupon is not active")

    if coupon.expires_at is not None:
        now = datetime.now(timezone.utc)
        expires = coupon.expires_at if coupon.expires_at.tzinfo else coupon.expires_at.replace(tzinfo=timezone.utc)
        if expires <= now:
            raise HTTPException(status_code=400, detail="Coupon has expired")

    if coupon.max_uses > 0 and coupon.current_uses >= coupon.max_uses:
        raise HTTPException(status_code=400, detail="Coupon usage limit reached")

    if cart_total < coupon.min_order_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum order amount of ${coupon.min_order_amount:.2f} not met"
        )

    # Calculate discount
    if coupon.discount_type == "percentage":
        discount_amount = round(cart_total * (coupon.discount_value / 100), 2)
        discount_amount = min(discount_amount, cart_total)
    else:  # fixed
        discount_amount = round(min(coupon.discount_value, cart_total), 2)

    return coupon, discount_amount


@router.get("", response_model=list[Coupon])
async def list_coupons(request: Request) -> list[Coupon]:
    """List all coupons."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_COUPON_COLUMNS} FROM coupons ORDER BY created_at DESC")
            rows = cur.fetchall()
            return [_row_to_coupon(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load coupons: {str(e)}")
    finally:
        pool.putconn(conn)


@router.post("", response_model=Coupon, status_code=201)
async def create_coupon(coupon_data: CouponCreate, request: Request) -> Coupon:
    """Create a new coupon."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            coupon_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO coupons (id, code, discount_type, discount_value, "
                "min_order_amount, max_uses, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING created_at",
                (coupon_id, coupon_data.code.upper(), coupon_data.discount_type.value,
                 coupon_data.discount_value, coupon_data.min_order_amount,
                 coupon_data.max_uses, coupon_data.expires_at)
            )
            created_at = cur.fetchone()[0]
            conn.commit()
            return Coupon(
                id=coupon_id,
                code=coupon_data.code.upper(),
                discount_type=coupon_data.discount_type,
                discount_value=coupon_data.discount_value,
                min_order_amount=coupon_data.min_order_amount,
                max_uses=coupon_data.max_uses,
                current_uses=0,
                is_active=True,
                expires_at=coupon_data.expires_at,
                created_at=created_at,
            )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create coupon: {str(e)}")
    finally:
        pool.putconn(conn)


@router.get("/{coupon_id}", response_model=Coupon)
async def get_coupon(coupon_id: str, request: Request) -> Coupon:
    """Get a single coupon by ID."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_COUPON_COLUMNS} FROM coupons WHERE id = %s", (coupon_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Coupon not found")
            return _row_to_coupon(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load coupon: {str(e)}")
    finally:
        pool.putconn(conn)


@router.patch("/{coupon_id}", response_model=Coupon)
async def update_coupon(coupon_id: str, coupon_data: CouponUpdate, request: Request) -> Coupon:
    """Partially update a coupon."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        updates = coupon_data.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses = []
        values = []
        for field, value in updates.items():
            if field == "discount_type" and value is not None:
                value = value.value
            set_clauses.append(f"{field} = %s")
            values.append(value)
        values.append(coupon_id)

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE coupons SET {', '.join(set_clauses)} WHERE id = %s "
                f"RETURNING {_COUPON_COLUMNS}",
                values
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Coupon not found")
            conn.commit()
            return _row_to_coupon(row)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update coupon: {str(e)}")
    finally:
        pool.putconn(conn)


@router.delete("/{coupon_id}", status_code=204)
async def delete_coupon(coupon_id: str, request: Request):
    """Delete a coupon."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM coupons WHERE id = %s RETURNING id", (coupon_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Coupon not found")
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete coupon: {str(e)}")
    finally:
        pool.putconn(conn)


@router.post("/validate", response_model=CouponValidationResult)
async def validate_coupon(body: CouponValidateRequest, request: Request) -> CouponValidationResult:
    """Validate a coupon code against a cart total."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        coupon, discount_amount = validate_coupon_for_cart(conn, body.code, body.cart_total)
        final_total = round(body.cart_total - discount_amount, 2)
        return CouponValidationResult(
            valid=True,
            coupon=coupon,
            discount_amount=discount_amount,
            final_total=final_total,
        )
    except HTTPException as e:
        return CouponValidationResult(
            valid=False,
            error=e.detail,
            discount_amount=0.0,
            final_total=body.cart_total,
        )
    finally:
        pool.putconn(conn)
