# Store/src/app/routes/orders.py
"""Order endpoints for Darwin Store checkout."""

from fastapi import APIRouter, HTTPException, Request
import uuid

from ..models import Order, OrderItem, OrderCreate, OrderStatusUpdate, OrderStatus, ORDER_STATUS_TRANSITIONS
from .alerts import check_and_create_alert
from .coupons import validate_coupon_for_cart

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[Order])
async def list_orders(request: Request) -> list[Order]:
    """Return all orders with their items, most recent first."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, created_at, total_amount, status, customer_id, coupon_code, discount_amount FROM orders ORDER BY created_at DESC"
            )
            order_rows = cur.fetchall()

            if not order_rows:
                return []

            order_ids = [str(row[0]) for row in order_rows]
            cur.execute(
                "SELECT id, order_id, product_id, quantity, price_at_purchase "
                "FROM order_items WHERE order_id = ANY(%s::uuid[])",
                (order_ids,)
            )
            item_rows = cur.fetchall()

            # Group items by order_id
            items_by_order: dict[str, list[OrderItem]] = {}
            for row in item_rows:
                oi = OrderItem(
                    id=str(row[0]),
                    order_id=str(row[1]),
                    product_id=str(row[2]),
                    quantity=row[3],
                    price_at_purchase=row[4]
                )
                items_by_order.setdefault(str(row[1]), []).append(oi)

            orders = []
            for row in order_rows:
                orders.append(Order(
                    id=str(row[0]),
                    created_at=row[1],
                    total_amount=row[2],
                    status=row[3],
                    customer_id=str(row[4]) if row[4] else None,
                    coupon_code=row[5],
                    discount_amount=row[6] if row[6] is not None else 0.0,
                    items=items_by_order.get(str(row[0]), [])
                ))

            return orders
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load orders: {str(e)}")
    finally:
        pool.putconn(conn)


@router.get("/unassigned", response_model=list[Order])
async def list_unassigned_orders(request: Request) -> list[Order]:
    """Return all orders that have no customer attached."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, created_at, total_amount, status FROM orders WHERE customer_id IS NULL ORDER BY created_at DESC"
            )
            order_rows = cur.fetchall()

            if not order_rows:
                return []

            order_ids = [str(row[0]) for row in order_rows]
            cur.execute(
                "SELECT id, order_id, product_id, quantity, price_at_purchase "
                "FROM order_items WHERE order_id = ANY(%s::uuid[])",
                (order_ids,)
            )
            item_rows = cur.fetchall()

            # Group items by order_id
            items_by_order: dict[str, list[OrderItem]] = {}
            for row in item_rows:
                oi = OrderItem(
                    id=str(row[0]),
                    order_id=str(row[1]),
                    product_id=str(row[2]),
                    quantity=row[3],
                    price_at_purchase=row[4]
                )
                items_by_order.setdefault(str(row[1]), []).append(oi)

            orders = []
            for row in order_rows:
                orders.append(Order(
                    id=str(row[0]),
                    created_at=row[1],
                    total_amount=row[2],
                    status=row[3],
                    customer_id=None,
                    items=items_by_order.get(str(row[0]), [])
                ))

            return orders
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load unassigned orders: {str(e)}")
    finally:
        pool.putconn(conn)


@router.put("/{order_id}/customer/{customer_id}", response_model=Order)
async def attach_order_to_customer(order_id: str, customer_id: str, request: Request) -> Order:
    """Attach an unassigned order to a customer."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Validate customer exists
            cur.execute("SELECT id FROM customers WHERE id = %s", (customer_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Customer not found")

            # Update only if currently unassigned
            cur.execute(
                "UPDATE orders SET customer_id = %s WHERE id = %s AND customer_id IS NULL "
                "RETURNING id, created_at, total_amount, status",
                (customer_id, order_id)
            )
            row = cur.fetchone()
            if not row:
                cur.execute("SELECT id, customer_id FROM orders WHERE id = %s", (order_id,))
                existing = cur.fetchone()
                if not existing:
                    raise HTTPException(status_code=404, detail="Order not found")
                raise HTTPException(status_code=400, detail="Order is already assigned to a customer")

            conn.commit()

            return Order(
                id=str(row[0]),
                created_at=row[1],
                total_amount=row[2],
                status=row[3],
                customer_id=customer_id
            )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to attach order: {str(e)}")
    finally:
        pool.putconn(conn)


@router.delete("/{order_id}", status_code=204)
async def delete_order(order_id: str, request: Request):
    """Delete an order and its items."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Check if order exists
            cur.execute("SELECT id FROM orders WHERE id = %s", (order_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Order not found")

            # Delete items first (no CASCADE in schema)
            cur.execute("DELETE FROM order_items WHERE order_id = %s", (order_id,))
            
            # Delete order
            cur.execute("DELETE FROM orders WHERE id = %s", (order_id,))
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete order: {str(e)}")
    finally:
        pool.putconn(conn)


@router.post("", response_model=Order, status_code=201)
async def create_order(order_data: OrderCreate, request: Request) -> Order:
    """
    Create a new order from cart items.

    Validates stock availability and atomically deducts stock using
    UPDATE ... WHERE stock >= quantity to prevent overselling.
    """
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Validate customer existence
            cur.execute("SELECT id FROM customers WHERE id = %s", (order_data.customer_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail="Invalid customer_id: customer does not exist")

            order_id = str(uuid.uuid4())
            total_amount = 0.0
            order_items = []

            for item in order_data.items:
                # Atomic stock deduction: only succeeds if enough stock exists
                cur.execute(
                    """
                    UPDATE products
                    SET stock = stock - %s
                    WHERE id = %s AND stock >= %s
                    RETURNING id, name, price, stock
                    """,
                    (item.quantity, item.product_id, item.quantity)
                )
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    # Check if product exists at all
                    cur.execute("SELECT name, stock FROM products WHERE id = %s", (item.product_id,))
                    product = cur.fetchone()
                    if not product:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Product {item.product_id} not found"
                        )
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient stock for '{product[0]}' (available: {product[1]}, requested: {item.quantity})"
                    )

                price_at_purchase = row[2]
                item_total = price_at_purchase * item.quantity
                total_amount += item_total

                item_id = str(uuid.uuid4())
                order_items.append(OrderItem(
                    id=item_id,
                    order_id=order_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    price_at_purchase=price_at_purchase
                ))

            # Apply coupon discount if provided
            discount_amount = 0.0
            coupon_code = None
            if order_data.coupon_code:
                coupon, discount_amount = validate_coupon_for_cart(
                    conn, order_data.coupon_code, total_amount
                )
                coupon_code = coupon.code
                total_amount = round(total_amount - discount_amount, 2)
                # Atomic usage increment with limit check
                cur.execute(
                    "UPDATE coupons SET current_uses = current_uses + 1 "
                    "WHERE id = %s AND (max_uses = 0 OR current_uses < max_uses) RETURNING id",
                    (coupon.id,)
                )
                if not cur.fetchone():
                    raise HTTPException(status_code=400, detail="Coupon usage limit reached")

            # Insert order record
            cur.execute(
                "INSERT INTO orders (id, total_amount, status, customer_id, coupon_code, discount_amount) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (order_id, total_amount, "pending", order_data.customer_id, coupon_code, discount_amount)
            )

            # Insert order items
            for oi in order_items:
                cur.execute(
                    "INSERT INTO order_items (id, order_id, product_id, quantity, price_at_purchase) VALUES (%s, %s, %s, %s, %s)",
                    (oi.id, oi.order_id, oi.product_id, oi.quantity, oi.price_at_purchase)
                )

            conn.commit()

            # Fetch created_at from the database
            cur.execute("SELECT created_at FROM orders WHERE id = %s", (order_id,))
            created_at = cur.fetchone()[0]

            result = Order(
                id=order_id,
                created_at=created_at,
                total_amount=total_amount,
                status="pending",
                items=order_items,
                customer_id=order_data.customer_id,
                coupon_code=coupon_code,
                discount_amount=discount_amount,
            )

        # Check for restock alerts after stock deduction (outside cursor context)
        for item in order_data.items:
            try:
                check_and_create_alert(conn, item.product_id)
            except Exception:
                pass  # Alert creation is best-effort; don't fail the order

        return result
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Order creation failed: {str(e)}")
    finally:
        pool.putconn(conn)

@router.patch("/{order_id}/status", response_model=Order)
async def update_order_status(order_id: str, body: OrderStatusUpdate, request: Request) -> Order:
    """
    Update the status of an order.

    Enforces valid transitions:
      pending -> processing -> shipped -> delivered -> returned
      Any non-terminal state -> cancelled
    """
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Fetch current order
            cur.execute(
                "SELECT id, created_at, total_amount, status, customer_id FROM orders WHERE id = %s",
                (order_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Order not found")

            current_status = row[3]

            # Validate transition
            try:
                current_enum = OrderStatus(current_status)
            except ValueError:
                # Legacy status value (e.g., "confirmed") -- allow transition to any valid status
                current_enum = None

            if current_enum is not None:
                allowed = ORDER_STATUS_TRANSITIONS.get(current_enum, set())
                if body.status not in allowed:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot transition from '{current_status}' to '{body.status.value}'. "
                               f"Allowed: {[s.value for s in allowed] if allowed else 'none (terminal state)'}"
                    )

            # Restore stock when cancelling or returning
            if body.status in (OrderStatus.CANCELLED, OrderStatus.RETURNED):
                cur.execute(
                    "SELECT product_id, quantity FROM order_items WHERE order_id = %s",
                    (order_id,)
                )
                items = cur.fetchall()
                for product_id, quantity in items:
                    cur.execute(
                        "UPDATE products SET stock = stock + %s WHERE id = %s",
                        (quantity, product_id)
                    )

            # Update status
            cur.execute(
                "UPDATE orders SET status = %s, updated_at = NOW() WHERE id = %s "
                "RETURNING id, created_at, total_amount, status, customer_id, coupon_code, discount_amount",
                (body.status.value, order_id)
            )
            updated = cur.fetchone()
            conn.commit()

            return Order(
                id=str(updated[0]),
                created_at=updated[1],
                total_amount=updated[2],
                status=updated[3],
                customer_id=str(updated[4]) if updated[4] else None,
                coupon_code=updated[5],
                discount_amount=updated[6] if updated[6] is not None else 0.0,
            )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update order status: {str(e)}")
    finally:
        pool.putconn(conn)
