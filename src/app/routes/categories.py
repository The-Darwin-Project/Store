# @ai-rules:
# 1. [Pattern]: Categories use Create/Update/Read split like other entities.
# 2. [Constraint]: Category names must be unique (enforced by DB UNIQUE constraint).
# 3. [Gotcha]: product_count is computed via LEFT JOIN, not stored.
"""Category CRUD endpoints for Darwin Store."""

from fastapi import APIRouter, HTTPException, Request
import uuid

from ..models import Category, CategoryCreate, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def list_categories(request: Request) -> list[Category]:
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.id, c.name, c.description, c.created_at, "
                "COUNT(p.id) as product_count "
                "FROM categories c "
                "LEFT JOIN products p ON p.category_id = c.id "
                "GROUP BY c.id, c.name, c.description, c.created_at "
                "ORDER BY c.name"
            )
            return [
                Category(
                    id=str(row[0]), name=row[1], description=row[2],
                    created_at=row[3], product_count=row[4],
                )
                for row in cur.fetchall()
            ]
    finally:
        pool.putconn(conn)


@router.post("", response_model=Category, status_code=201)
async def create_category(category: CategoryCreate, request: Request) -> Category:
    new_id = uuid.uuid4()
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO categories (id, name, description) VALUES (%s, %s, %s) "
                "RETURNING id, name, description, created_at",
                (str(new_id), category.name.strip(), category.description or ""),
            )
            row = cur.fetchone()
            conn.commit()
            return Category(id=str(row[0]), name=row[1], description=row[2], created_at=row[3], product_count=0)
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Category '{category.name}' already exists")
        raise
    finally:
        pool.putconn(conn)


@router.patch("/{category_id}", response_model=Category)
async def update_category(category_id: str, updates: CategoryUpdate, request: Request) -> Category:
    provided = updates.model_dump(exclude_unset=True)
    if not provided:
        raise HTTPException(status_code=400, detail="No fields to update")
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            set_clauses = []
            values = []
            for field, value in provided.items():
                set_clauses.append(f"{field} = %s")
                values.append(value)
            values.append(category_id)
            cur.execute(
                f"UPDATE categories SET {', '.join(set_clauses)} WHERE id = %s "
                "RETURNING id, name, description, created_at",
                values,
            )
            row = cur.fetchone()
            conn.commit()
            if not row:
                raise HTTPException(status_code=404, detail="Category not found")
            cur.execute("SELECT COUNT(*) FROM products WHERE category_id = %s", (category_id,))
            count = cur.fetchone()[0]
            return Category(id=str(row[0]), name=row[1], description=row[2], created_at=row[3], product_count=count)
    finally:
        pool.putconn(conn)


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: str, request: Request) -> None:
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM categories WHERE id = %s", (category_id,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Category not found")
    finally:
        pool.putconn(conn)
