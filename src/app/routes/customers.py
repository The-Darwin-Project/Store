"""Customer endpoints for Darwin Store."""

from fastapi import APIRouter, HTTPException, Request
import uuid

from ..models import Customer, CustomerCreate, Order

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=Customer, status_code=201)
async def create_customer(customer: CustomerCreate, request: Request) -> Customer:
    """Create a new customer."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            customer_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO customers (id, name, email) VALUES (%s, %s, %s) RETURNING created_at",
                (customer_id, customer.name, customer.email)
            )
            created_at = cur.fetchone()[0]
            conn.commit()
            
            return Customer(
                id=customer_id,
                name=customer.name,
                email=customer.email,
                created_at=created_at
            )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="A customer with this email already exists")
        raise HTTPException(status_code=500, detail=f"Failed to create customer: {str(e)}")
    finally:
        pool.putconn(conn)


@router.get("", response_model=list[Customer])
async def list_customers(request: Request) -> list[Customer]:
    """List all customers."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, email, created_at FROM customers ORDER BY created_at DESC")
            rows = cur.fetchall()
            return [
                Customer(id=str(row[0]), name=row[1], email=row[2], created_at=row[3])
                for row in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list customers: {str(e)}")
    finally:
        pool.putconn(conn)


@router.get("/{customer_id}/orders", response_model=list[Order])
async def list_customer_orders(customer_id: str, request: Request) -> list[Order]:
    """List orders for a specific customer."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, created_at, total_amount, status FROM orders WHERE customer_id = %s ORDER BY created_at DESC",
                (customer_id,)
            )
            rows = cur.fetchall()
            return [
                Order(
                    id=str(row[0]),
                    created_at=row[1],
                    total_amount=row[2],
                    status=row[3],
                    customer_id=customer_id
                )
                for row in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list customer orders: {str(e)}")
    finally:
        pool.putconn(conn)


@router.delete("/{customer_id}/orders/{order_id}", status_code=204)
async def detach_order(customer_id: str, order_id: str, request: Request):
    """Detach an order from a customer (set customer_id to NULL)."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET customer_id = NULL WHERE id = %s AND customer_id = %s",
                (order_id, customer_id)
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Order not found or not attached to this customer")
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to detach order: {str(e)}")
    finally:
        pool.putconn(conn)
