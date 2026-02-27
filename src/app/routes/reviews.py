# Store/src/app/routes/reviews.py
# @ai-rules:
# 1. [Constraint]: One review per customer per product (UNIQUE constraint). Return 409 on duplicate.
# 2. [Pattern]: Reviews are nested under /products/{id}/reviews. Average rating is a separate endpoint.
# 3. [Gotcha]: Validate product_id and customer_id existence before insert.
"""Product review endpoints for Darwin Store."""

from fastapi import APIRouter, HTTPException, Query, Request
import uuid

from ..models import ReviewCreate, Review, AverageRating

router = APIRouter(prefix="/products", tags=["reviews"])


@router.get("/average-ratings/batch", response_model=list[AverageRating])
async def get_batch_average_ratings(
    request: Request,
    product_ids: str = Query(..., description="Comma-separated product UUIDs"),
) -> list[AverageRating]:
    """Get average ratings for multiple products in a single query."""
    ids = [pid.strip() for pid in product_ids.split(",") if pid.strip()]
    if not ids:
        return []
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                f"SELECT product_id, COALESCE(AVG(rating), 0), COUNT(*) "
                f"FROM reviews WHERE product_id IN ({placeholders}) "
                f"GROUP BY product_id",
                ids,
            )
            results = {
                str(row[0]): AverageRating(
                    product_id=str(row[0]),
                    average_rating=round(float(row[1]), 1),
                    review_count=row[2],
                )
                for row in cur.fetchall()
            }
        # Return a result for every requested id (0 rating if no reviews)
        return [
            results.get(pid, AverageRating(product_id=pid, average_rating=0, review_count=0))
            for pid in ids
        ]
    finally:
        pool.putconn(conn)


@router.get("/{product_id}/reviews", response_model=list[Review])
async def list_reviews(product_id: str, request: Request) -> list[Review]:
    """List all reviews for a product, most recent first."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r.id, r.product_id, r.customer_id, c.name AS customer_name, "
                "r.rating, r.comment, r.created_at "
                "FROM reviews r "
                "LEFT JOIN customers c ON r.customer_id = c.id "
                "WHERE r.product_id = %s "
                "ORDER BY r.created_at DESC",
                (product_id,)
            )
            return [
                Review(
                    id=str(row[0]), product_id=str(row[1]), customer_id=str(row[2]),
                    customer_name=row[3], rating=row[4], comment=row[5], created_at=row[6]
                )
                for row in cur.fetchall()
            ]
    finally:
        pool.putconn(conn)


@router.post("/{product_id}/reviews", response_model=Review, status_code=201)
async def create_review(product_id: str, review: ReviewCreate, request: Request) -> Review:
    """Create a review for a product."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Validate product exists
            cur.execute("SELECT id FROM products WHERE id = %s", (product_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Product not found")

            # Validate customer exists
            cur.execute("SELECT name FROM customers WHERE id = %s", (review.customer_id,))
            customer_row = cur.fetchone()
            if not customer_row:
                raise HTTPException(status_code=404, detail="Customer not found")

            review_id = str(uuid.uuid4())
            try:
                cur.execute(
                    "INSERT INTO reviews (id, product_id, customer_id, rating, comment) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING created_at",
                    (review_id, product_id, review.customer_id, review.rating, review.comment)
                )
                created_at = cur.fetchone()[0]
                conn.commit()
            except Exception as e:
                conn.rollback()
                if "unique" in str(e).lower():
                    raise HTTPException(status_code=409, detail="You have already reviewed this product")
                raise

            return Review(
                id=review_id, product_id=product_id, customer_id=review.customer_id,
                customer_name=customer_row[0], rating=review.rating,
                comment=review.comment, created_at=created_at
            )
    finally:
        pool.putconn(conn)


@router.get("/{product_id}/average-rating", response_model=AverageRating)
async def get_average_rating(product_id: str, request: Request) -> AverageRating:
    """Get the average star rating and review count for a product."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(AVG(rating), 0), COUNT(*) FROM reviews WHERE product_id = %s",
                (product_id,)
            )
            row = cur.fetchone()
            return AverageRating(
                product_id=product_id,
                average_rating=round(float(row[0]), 1),
                review_count=row[1]
            )
    finally:
        pool.putconn(conn)
