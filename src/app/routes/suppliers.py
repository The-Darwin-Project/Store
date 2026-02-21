# @ai-rules:
# 1. Max 100 lines per file
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from pydantic import BaseModel
import uuid

from ..models import Supplier, SupplierCreate, Product

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

class SupplierResponse(Supplier):
    low_stock_count: int = 0

@router.get("", response_model=list[SupplierResponse])
async def list_suppliers(request: Request) -> list[SupplierResponse]:
    """List all suppliers including low stock count."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.id, s.name, s.contact_email, s.phone, s.created_at,
                       COUNT(p.id) FILTER (WHERE p.stock <= p.reorder_threshold) AS low_stock_count
                FROM suppliers s
                LEFT JOIN products p ON p.supplier_id = s.id
                GROUP BY s.id
                ORDER BY s.created_at DESC
            """)
            suppliers = [
                SupplierResponse(
                    id=str(row[0]), name=row[1], contact_email=row[2], phone=row[3], created_at=row[4], low_stock_count=row[5] or 0
                )
                for row in cur.fetchall()
            ]
            return suppliers
    finally:
        pool.putconn(conn)

@router.post("", response_model=SupplierResponse, status_code=201)
async def create_supplier(supplier: SupplierCreate, request: Request) -> SupplierResponse:
    """Create a new supplier."""
    new_id = str(uuid.uuid4())
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO suppliers (id, name, contact_email, phone) VALUES (%s, %s, %s, %s) RETURNING created_at",
                (new_id, supplier.name, supplier.contact_email, supplier.phone)
            )
            created_at = cur.fetchone()[0]
            conn.commit()
            return SupplierResponse(id=new_id, name=supplier.name, contact_email=supplier.contact_email, phone=supplier.phone, created_at=created_at)
    finally:
        pool.putconn(conn)

@router.delete("/{supplier_id}", status_code=204)
async def delete_supplier(supplier_id: str, request: Request) -> None:
    """Delete a supplier by ID."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Check for attached products
            cur.execute("SELECT COUNT(*) FROM products WHERE supplier_id = %s", (supplier_id,))
            if cur.fetchone()[0] > 0:
                raise HTTPException(status_code=409, detail="Cannot delete supplier with attached products")
                
            cur.execute("DELETE FROM suppliers WHERE id = %s", (supplier_id,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Supplier not found")
    finally:
        pool.putconn(conn)

@router.get("/{supplier_id}/products", response_model=list[Product])
async def list_supplier_products(supplier_id: str, request: Request) -> list[Product]:
    """List products for a given supplier."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, price, stock, sku, image_data, description, supplier_id, reorder_threshold 
                FROM products WHERE supplier_id = %s
            """, (supplier_id,))
            products = [Product(
                id=str(row[0]), name=row[1], price=row[2], stock=row[3], sku=row[4], 
                image_data=row[5], description=row[6], supplier_id=str(row[7]) if row[7] else None, 
                reorder_threshold=row[8] if row[8] is not None else 10
            ) for row in cur.fetchall()]
            return products
    finally:
        pool.putconn(conn)
