"""Customer endpoints for Darwin Store."""

from fastapi import APIRouter, HTTPException, Request
import uuid
from psycopg2 import errors as pg_errors

from ..models import Customer, CustomerCreate, CustomerUpdate, Order

router = APIRouter(prefix="/customers", tags=["customers"])

CUSTOMER_COLUMNS = [
    "id", "name", "email", "company", "phone",
    "shipping_street", "shipping_city", "shipping_state",
    "shipping_zip", "shipping_country", "created_at"
]

CUSTOMER_SELECT = ", ".join(CUSTOMER_COLUMNS)


def _row_to_customer(row) -> Customer:
    return Customer(
        id=str(row[0]),
        name=row[1],
        email=row[2],
        company=row[3],
        phone=row[4],
        shipping_street=row[5],
        shipping_city=row[6],
        shipping_state=row[7],
        shipping_zip=row[8],
        shipping_country=row[9],
        created_at=row[10],
    )


@router.post("", response_model=Customer, status_code=201)
async def create_customer(customer: CustomerCreate, request: Request) -> Customer:
    """Create a new customer."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            customer_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO customers (id, name, email, company, phone, "
                "shipping_street, shipping_city, shipping_state, shipping_zip, shipping_country) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING created_at",
                (customer_id, customer.name, customer.email, customer.company,
                 customer.phone, customer.shipping_street, customer.shipping_city,
                 customer.shipping_state, customer.shipping_zip, customer.shipping_country)
            )
            created_at = cur.fetchone()[0]
            conn.commit()

            return Customer(
                id=customer_id,
                name=customer.name,
                email=customer.email,
                company=customer.company,
                phone=customer.phone,
                shipping_street=customer.shipping_street,
                shipping_city=customer.shipping_city,
                shipping_state=customer.shipping_state,
                shipping_zip=customer.shipping_zip,
                shipping_country=customer.shipping_country,
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
            cur.execute(f"SELECT {CUSTOMER_SELECT} FROM customers ORDER BY created_at DESC")
            rows = cur.fetchall()
            return [_row_to_customer(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list customers: {str(e)}")
    finally:
        pool.putconn(conn)


@router.get("/{customer_id}", response_model=Customer)
async def get_customer(customer_id: str, request: Request) -> Customer:
    """Get a single customer by ID."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {CUSTOMER_SELECT} FROM customers WHERE id = %s", (customer_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Customer not found")
            return _row_to_customer(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get customer: {str(e)}")
    finally:
        pool.putconn(conn)


@router.patch("/{customer_id}", response_model=Customer)
async def update_customer(customer_id: str, updates: CustomerUpdate, request: Request) -> Customer:
    """Partially update a customer."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        update_data = updates.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clauses = []
        values = []
        for field, value in update_data.items():
            set_clauses.append(f"{field} = %s")
            values.append(value)
        values.append(customer_id)

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE customers SET {', '.join(set_clauses)} WHERE id = %s "
                f"RETURNING {CUSTOMER_SELECT}",
                values
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Customer not found")
            conn.commit()
            return _row_to_customer(row)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="A customer with this email already exists")
        raise HTTPException(status_code=500, detail=f"Failed to update customer: {str(e)}")
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


@router.delete("/{customer_id}", status_code=204)
async def delete_customer(customer_id: str, request: Request):
    """Delete a customer by ID.

    Returns 204 on success, 404 if not found, 409 if FK constraints
    (orders, invoices, reviews) block deletion.
    """
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM customers WHERE id = %s", (customer_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Customer not found")
            conn.commit()
    except HTTPException:
        raise
    except pg_errors.ForeignKeyViolation:
        conn.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cannot delete customer: referenced by orders, invoices, or reviews",
        )
    except Exception as e:
        conn.rollback()
        if "violates foreign key" in str(e).lower() or "integrity" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail="Cannot delete customer: referenced by orders, invoices, or reviews",
            )
        raise HTTPException(status_code=500, detail=f"Failed to delete customer: {str(e)}")
    finally:
        pool.putconn(conn)
