# Store/src/app/routes/orders.py
"""Order endpoints for Darwin Store checkout."""

from fastapi import APIRouter, HTTPException, Query, Request
import uuid

import json

from ..models import (
    Order, OrderItem, OrderCreate, OrderStatusUpdate, OrderStatus,
    ORDER_STATUS_TRANSITIONS, Invoice, InvoiceLineItem, CustomerSnapshot,
    PaginatedResponse,
)
from .alerts import check_and_create_alert
from .coupons import validate_coupon_for_cart

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
async def list_orders(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginatedResponse[Order]:
    """Return orders with pagination, most recent first."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM orders")
            total = cur.fetchone()[0]
            offset = (page - 1) * limit
            pages = (total + limit - 1) // limit if total > 0 else 0

            cur.execute(
                "SELECT o.id, o.created_at, o.total_amount, o.status, o.customer_id, "
                "o.coupon_code, o.discount_amount, c.name AS customer_name, "
                "i.id AS invoice_id "
                "FROM orders o "
                "LEFT JOIN customers c ON o.customer_id = c.id "
                "LEFT JOIN invoices i ON i.order_id = o.id "
                "ORDER BY o.created_at DESC "
                "LIMIT %s OFFSET %s",
                (limit, offset)
            )
            order_rows = cur.fetchall()

            if not order_rows:
                return PaginatedResponse(
                    items=[], total=total, page=page, limit=limit, pages=pages
                )

            order_ids = [str(row[0]) for row in order_rows]
            cur.execute(
                "SELECT oi.id, oi.order_id, oi.product_id, oi.quantity, oi.price_at_purchase, "
                "p.name AS product_name "
                "FROM order_items oi "
                "LEFT JOIN products p ON oi.product_id = p.id "
                "WHERE oi.order_id = ANY(%s::uuid[])",
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
                    price_at_purchase=row[4],
                    product_name=row[5]
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
                    customer_name=row[7],
                    invoice_id=str(row[8]) if row[8] else None,
                    items=items_by_order.get(str(row[0]), [])
                ))

            return PaginatedResponse(
                items=orders, total=total, page=page, limit=limit, pages=pages
            )
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


@router.post("/{order_id}/invoice", response_model=Invoice, status_code=201)
async def generate_invoice(order_id: str, request: Request) -> Invoice:
    """Generate an invoice for a delivered order."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # 1. Fetch the order
            cur.execute(
                "SELECT id, status, customer_id, total_amount, coupon_code, discount_amount "
                "FROM orders WHERE id = %s",
                (order_id,)
            )
            order_row = cur.fetchone()
            if not order_row:
                raise HTTPException(status_code=404, detail="Order not found")

            order_status = order_row[1]
            customer_id = order_row[2]
            order_total = order_row[3]
            coupon_code = order_row[4]
            discount_amount = order_row[5] if order_row[5] is not None else 0.0

            if order_status != "delivered":
                raise HTTPException(
                    status_code=400,
                    detail=f"Invoice can only be generated for delivered orders (current status: {order_status})"
                )

            # 2. Check for existing invoice
            cur.execute("SELECT id FROM invoices WHERE order_id = %s", (order_id,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Invoice already exists for this order")

            # 3. Fetch customer snapshot
            cur.execute(
                "SELECT name, email, company, phone, shipping_street, shipping_city, "
                "shipping_state, shipping_zip, shipping_country FROM customers WHERE id = %s",
                (customer_id,)
            )
            cust_row = cur.fetchone()
            if not cust_row:
                raise HTTPException(status_code=404, detail="Customer not found for this order")

            customer_snapshot = CustomerSnapshot(
                name=cust_row[0],
                email=cust_row[1],
                company=cust_row[2],
                phone=cust_row[3],
                shipping_street=cust_row[4],
                shipping_city=cust_row[5],
                shipping_state=cust_row[6],
                shipping_zip=cust_row[7],
                shipping_country=cust_row[8],
            )

            # 4. Fetch order items joined with products
            cur.execute(
                "SELECT oi.quantity, oi.price_at_purchase, p.name, p.sku "
                "FROM order_items oi "
                "LEFT JOIN products p ON oi.product_id = p.id "
                "WHERE oi.order_id = %s",
                (order_id,)
            )
            item_rows = cur.fetchall()

            line_items = []
            subtotal = 0.0
            for item_row in item_rows:
                qty = item_row[0]
                unit_price = item_row[1]
                product_name = item_row[2] or "Unknown product"
                sku = item_row[3] or "N/A"
                line_total = round(qty * unit_price, 2)
                subtotal += line_total
                line_items.append(InvoiceLineItem(
                    product_name=product_name,
                    sku=sku,
                    unit_price=unit_price,
                    quantity=qty,
                    line_total=line_total,
                ))

            subtotal = round(subtotal, 2)
            grand_total = order_total

            # 5. Insert invoice
            invoice_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO invoices (id, order_id, customer_id, customer_snapshot, line_items, "
                "subtotal, coupon_code, discount_amount, grand_total) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING invoice_number, created_at",
                (
                    invoice_id, order_id, str(customer_id),
                    json.dumps(customer_snapshot.model_dump()),
                    json.dumps([li.model_dump() for li in line_items]),
                    subtotal, coupon_code, discount_amount, grand_total
                )
            )
            result_row = cur.fetchone()
            conn.commit()

            return Invoice(
                id=invoice_id,
                invoice_number=result_row[0],
                order_id=order_id,
                customer_snapshot=customer_snapshot,
                line_items=line_items,
                subtotal=subtotal,
                coupon_code=coupon_code,
                discount_amount=discount_amount,
                grand_total=grand_total,
                created_at=result_row[1],
            )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to generate invoice: {str(e)}")
    finally:
        pool.putconn(conn)
