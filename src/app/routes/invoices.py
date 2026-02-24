"""Invoice endpoints for Darwin Store."""

from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional
import json

from ..models import Invoice, InvoiceLineItem, CustomerSnapshot

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _row_to_invoice(row) -> Invoice:
    customer_snapshot_data = row[3] if isinstance(row[3], dict) else json.loads(row[3])
    line_items_data = row[4] if isinstance(row[4], list) else json.loads(row[4])

    return Invoice(
        id=str(row[0]),
        invoice_number=row[1],
        order_id=str(row[2]),
        customer_snapshot=CustomerSnapshot(**customer_snapshot_data),
        line_items=[InvoiceLineItem(**li) for li in line_items_data],
        subtotal=row[5],
        coupon_code=row[6],
        discount_amount=row[7] if row[7] is not None else 0.0,
        grand_total=row[8],
        created_at=row[9],
    )


INVOICE_SELECT = (
    "id, invoice_number, order_id, customer_snapshot, line_items, "
    "subtotal, coupon_code, discount_amount, grand_total, created_at"
)


@router.get("", response_model=list[Invoice])
async def list_invoices(
    request: Request,
    customer_id: Optional[str] = Query(None),
) -> list[Invoice]:
    """List all invoices, optionally filtered by customer_id."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            if customer_id:
                cur.execute(
                    f"SELECT {INVOICE_SELECT} FROM invoices WHERE customer_id = %s "
                    "ORDER BY created_at DESC",
                    (customer_id,)
                )
            else:
                cur.execute(
                    f"SELECT {INVOICE_SELECT} FROM invoices ORDER BY created_at DESC"
                )
            rows = cur.fetchall()
            return [_row_to_invoice(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list invoices: {str(e)}")
    finally:
        pool.putconn(conn)


@router.get("/{invoice_id}", response_model=Invoice)
async def get_invoice(invoice_id: str, request: Request) -> Invoice:
    """Get a single invoice by ID."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {INVOICE_SELECT} FROM invoices WHERE id = %s",
                (invoice_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Invoice not found")
            return _row_to_invoice(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get invoice: {str(e)}")
    finally:
        pool.putconn(conn)
