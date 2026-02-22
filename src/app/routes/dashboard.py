"""Dashboard endpoint for Darwin Store business metrics."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(request: Request):
    """Return aggregated business metrics for the dashboard."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # 1. Total revenue (sum of all order total_amount)
            cur.execute("SELECT COALESCE(SUM(total_amount), 0) FROM orders")
            total_revenue = float(cur.fetchone()[0])

            # 2. Order count by status
            cur.execute(
                "SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status"
            )
            orders_by_status = {row[0]: row[1] for row in cur.fetchall()}

            # 3. Top 5 products by sales volume (total quantity sold)
            cur.execute("""
                SELECT p.id, p.name, COALESCE(SUM(oi.quantity), 0) AS total_sold
                FROM order_items oi
                JOIN products p ON p.id = oi.product_id
                GROUP BY p.id, p.name
                ORDER BY total_sold DESC
                LIMIT 5
            """)
            top_products = [
                {"id": str(row[0]), "name": row[1], "total_sold": int(row[2])}
                for row in cur.fetchall()
            ]

            # 4. Low-stock alerts (stock < 10) with supplier info
            cur.execute("""
                SELECT p.id, p.name, p.stock, p.reorder_threshold,
                       s.id AS supplier_id, s.name AS supplier_name,
                       s.contact_email AS supplier_email
                FROM products p
                LEFT JOIN suppliers s ON s.id = p.supplier_id
                WHERE p.stock < 10
                ORDER BY p.stock ASC
            """)
            low_stock_alerts = [
                {
                    "id": str(row[0]),
                    "name": row[1],
                    "stock": row[2],
                    "reorder_threshold": row[3] if row[3] is not None else 10,
                    "supplier": {
                        "id": str(row[4]),
                        "name": row[5],
                        "contact_email": row[6],
                    } if row[4] else None,
                }
                for row in cur.fetchall()
            ]

        return {
            "total_revenue": total_revenue,
            "orders_by_status": orders_by_status,
            "top_products": top_products,
            "low_stock_alerts": low_stock_alerts,
        }
    finally:
        pool.putconn(conn)
