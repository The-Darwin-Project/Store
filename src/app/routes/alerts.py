"""Alerts endpoints and helpers for Darwin Store restock notifications."""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request

from ..models import Alert, AlertCreate, AlertStatusUpdate, AlertStatus, AlertType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


class EmailNotifier:
    """Stub email notifier for future integration."""

    @staticmethod
    def send(to: str, subject: str, body: str) -> None:
        logger.info(f"[EmailNotifier stub] To: {to}, Subject: {subject}, Body: {body}")


def check_and_create_alert(conn, product_id: str) -> None:
    """Check if a product's stock is below its reorder threshold and create an alert if needed.

    Skips creation if an active alert already exists for this product.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, stock, reorder_threshold, supplier_id FROM products WHERE id = %s",
            (product_id,)
        )
        row = cur.fetchone()
        if not row:
            return

        name, stock, reorder_threshold, supplier_id = row
        reorder_threshold = reorder_threshold if reorder_threshold is not None else 10

        if stock > reorder_threshold:
            return

        # Check for existing active alert for this product
        cur.execute(
            "SELECT id FROM alerts WHERE product_id = %s AND status = %s",
            (product_id, AlertStatus.ACTIVE.value)
        )
        if cur.fetchone():
            return

        # Look up supplier name for the message
        supplier_name = None
        supplier_email = None
        if supplier_id:
            cur.execute("SELECT name, contact_email FROM suppliers WHERE id = %s", (supplier_id,))
            supplier_row = cur.fetchone()
            if supplier_row:
                supplier_name = supplier_row[0]
                supplier_email = supplier_row[1]

        message = (
            f"Restock needed: '{name}' stock is {stock}, below threshold of {reorder_threshold}."
        )
        if supplier_name:
            message += f" Supplier: {supplier_name}."

        alert_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO alerts (id, type, message, status, product_id, supplier_id, current_stock, reorder_threshold) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (alert_id, AlertType.RESTOCK.value, message, AlertStatus.ACTIVE.value,
             product_id, str(supplier_id) if supplier_id else None, stock, reorder_threshold)
        )
        conn.commit()

        # Fire email notification stub
        if supplier_email:
            EmailNotifier.send(
                to=supplier_email,
                subject=f"Restock Alert: {name}",
                body=message
            )

        logger.info(f"Created restock alert for product '{name}' (stock={stock}, threshold={reorder_threshold})")


@router.get("", response_model=list[Alert])
async def list_alerts(request: Request, status: str = None) -> list[Alert]:
    """List all alerts, optionally filtered by status."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            base_query = (
                "SELECT a.id, a.type, a.message, a.status, a.product_id, a.supplier_id, "
                "a.current_stock, a.reorder_threshold, a.created_at, "
                "p.name AS product_name, s.name AS supplier_name "
                "FROM alerts a "
                "LEFT JOIN products p ON a.product_id = p.id "
                "LEFT JOIN suppliers s ON a.supplier_id = s.id"
            )
            if status:
                cur.execute(
                    base_query + " WHERE a.status = %s ORDER BY a.created_at DESC",
                    (status,)
                )
            else:
                cur.execute(base_query + " ORDER BY a.created_at DESC")
            rows = cur.fetchall()
            return [
                Alert(
                    id=str(row[0]), type=row[1], message=row[2], status=row[3],
                    product_id=str(row[4]) if row[4] else None,
                    supplier_id=str(row[5]) if row[5] else None,
                    current_stock=row[6], reorder_threshold=row[7],
                    created_at=row[8],
                    product_name=row[9],
                    supplier_name=row[10],
                )
                for row in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load alerts: {str(e)}")
    finally:
        pool.putconn(conn)


@router.post("", response_model=Alert, status_code=201)
async def create_alert(alert_data: AlertCreate, request: Request) -> Alert:
    """Manually create a new alert."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            alert_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO alerts (id, type, message, status, product_id, supplier_id, current_stock, reorder_threshold) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING created_at",
                (alert_id, alert_data.type.value, alert_data.message, AlertStatus.ACTIVE.value,
                 alert_data.product_id, alert_data.supplier_id,
                 alert_data.current_stock, alert_data.reorder_threshold)
            )
            created_at = cur.fetchone()[0]
            conn.commit()
            return Alert(
                id=alert_id, type=alert_data.type, message=alert_data.message,
                status=AlertStatus.ACTIVE, product_id=alert_data.product_id,
                supplier_id=alert_data.supplier_id,
                current_stock=alert_data.current_stock,
                reorder_threshold=alert_data.reorder_threshold,
                created_at=created_at
            )
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create alert: {str(e)}")
    finally:
        pool.putconn(conn)


@router.patch("/{alert_id}", response_model=Alert)
async def update_alert_status(alert_id: str, body: AlertStatusUpdate, request: Request) -> Alert:
    """Update the status of an alert (e.g., mark as ordered or dismissed)."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE alerts SET status = %s WHERE id = %s "
                "RETURNING id, type, message, status, product_id, supplier_id, current_stock, reorder_threshold, created_at",
                (body.status.value, alert_id)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Alert not found")
            conn.commit()
            # Look up product and supplier names
            product_name = None
            supplier_name = None
            if row[4]:
                cur.execute("SELECT name FROM products WHERE id = %s", (str(row[4]),))
                p = cur.fetchone()
                if p:
                    product_name = p[0]
            if row[5]:
                cur.execute("SELECT name FROM suppliers WHERE id = %s", (str(row[5]),))
                s = cur.fetchone()
                if s:
                    supplier_name = s[0]
            return Alert(
                id=str(row[0]), type=row[1], message=row[2], status=row[3],
                product_id=str(row[4]) if row[4] else None,
                supplier_id=str(row[5]) if row[5] else None,
                current_stock=row[6], reorder_threshold=row[7],
                created_at=row[8],
                product_name=product_name,
                supplier_name=supplier_name,
            )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update alert: {str(e)}")
    finally:
        pool.putconn(conn)
