"""Campaign CRUD and active-listing endpoints for Darwin Store."""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from ..models import Campaign, CampaignCreate, CampaignUpdate, CampaignType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


_CAMPAIGN_COLUMNS = (
    "id, title, type, content, image_url, link_url, coupon_code, "
    "product_id, start_date, end_date, is_active, priority, created_at"
)


def _row_to_campaign(row) -> Campaign:
    """Convert a DB row tuple to a Campaign model."""
    return Campaign(
        id=str(row[0]),
        title=row[1],
        type=row[2],
        content=row[3] or "",
        image_url=row[4],
        link_url=row[5],
        coupon_code=row[6],
        product_id=str(row[7]) if row[7] else None,
        start_date=row[8],
        end_date=row[9],
        is_active=row[10] if row[10] is not None else True,
        priority=row[11] if row[11] is not None else 0,
        created_at=row[12],
    )


def _validate_campaign_data(conn, data, existing=None):
    """Validate campaign business rules. Raises HTTPException on failure."""
    # Determine effective values (merge update onto existing if partial update)
    start_date = getattr(data, 'start_date', None)
    end_date = getattr(data, 'end_date', None)
    campaign_type = getattr(data, 'type', None)
    coupon_code = getattr(data, 'coupon_code', None)
    product_id = getattr(data, 'product_id', None)

    if existing:
        # For PATCH: use existing values as fallback
        updates = data.model_dump(exclude_unset=True)
        if 'start_date' not in updates:
            start_date = existing.start_date
        if 'end_date' not in updates:
            end_date = existing.end_date
        if 'type' not in updates:
            campaign_type = existing.type
        if 'coupon_code' not in updates:
            coupon_code = existing.coupon_code
        if 'product_id' not in updates:
            product_id = existing.product_id

    # 1. Date range validation
    if start_date and end_date and end_date <= start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")

    # 2. Coupon code validation
    if coupon_code:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM coupons WHERE UPPER(code) = UPPER(%s)",
                (coupon_code,)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail=f"Coupon code '{coupon_code}' not found")

    # 3. Product spotlight validation
    _is_spotlight = (campaign_type == CampaignType.PRODUCT_SPOTLIGHT
                     or campaign_type == "product_spotlight")
    if _is_spotlight:
        if not product_id:
            raise HTTPException(
                status_code=400,
                detail="product_id is required for product_spotlight campaigns"
            )
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM products WHERE id = %s", (product_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail=f"Product '{product_id}' not found")


@router.get("", response_model=list[Campaign])
async def list_campaigns(request: Request) -> list[Campaign]:
    """List all campaigns (admin use)."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_CAMPAIGN_COLUMNS} FROM campaigns ORDER BY priority DESC, created_at DESC")
            rows = cur.fetchall()
            return [_row_to_campaign(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load campaigns: {str(e)}")
    finally:
        pool.putconn(conn)


@router.post("", response_model=Campaign, status_code=201)
async def create_campaign(campaign_data: CampaignCreate, request: Request) -> Campaign:
    """Create a new campaign with validation."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        _validate_campaign_data(conn, campaign_data)

        campaign_id = str(uuid.uuid4())
        # Clear product_id for non-spotlight campaigns
        product_id = campaign_data.product_id if campaign_data.type == CampaignType.PRODUCT_SPOTLIGHT else None

        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO campaigns (id, title, type, content, image_url, link_url, "
                f"coupon_code, product_id, start_date, end_date, is_active, priority) "
                f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING created_at",
                (campaign_id, campaign_data.title, campaign_data.type.value,
                 campaign_data.content, campaign_data.image_url, campaign_data.link_url,
                 campaign_data.coupon_code, product_id,
                 campaign_data.start_date, campaign_data.end_date,
                 campaign_data.is_active, campaign_data.priority)
            )
            created_at = cur.fetchone()[0]
            conn.commit()
            return Campaign(
                id=campaign_id,
                title=campaign_data.title,
                type=campaign_data.type,
                content=campaign_data.content,
                image_url=campaign_data.image_url,
                link_url=campaign_data.link_url,
                coupon_code=campaign_data.coupon_code,
                product_id=product_id,
                start_date=campaign_data.start_date,
                end_date=campaign_data.end_date,
                is_active=campaign_data.is_active,
                priority=campaign_data.priority,
                created_at=created_at,
            )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create campaign: {str(e)}")
    finally:
        pool.putconn(conn)


@router.get("/active", response_model=list[Campaign])
async def get_active_campaigns(request: Request) -> list[Campaign]:
    """Get currently active campaigns for storefront display."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_CAMPAIGN_COLUMNS} FROM campaigns "
                f"WHERE is_active = TRUE AND NOW() BETWEEN start_date AND end_date "
                f"ORDER BY priority DESC, created_at DESC"
            )
            rows = cur.fetchall()
            return [_row_to_campaign(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load active campaigns: {str(e)}")
    finally:
        pool.putconn(conn)


@router.get("/{campaign_id}", response_model=Campaign)
async def get_campaign(campaign_id: str, request: Request) -> Campaign:
    """Get a single campaign by ID."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_CAMPAIGN_COLUMNS} FROM campaigns WHERE id = %s", (campaign_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Campaign not found")
            return _row_to_campaign(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load campaign: {str(e)}")
    finally:
        pool.putconn(conn)


@router.patch("/{campaign_id}", response_model=Campaign)
async def update_campaign(campaign_id: str, campaign_data: CampaignUpdate, request: Request) -> Campaign:
    """Partially update a campaign."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        updates = campaign_data.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Fetch existing campaign for validation context
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_CAMPAIGN_COLUMNS} FROM campaigns WHERE id = %s", (campaign_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Campaign not found")
            existing = _row_to_campaign(row)

        _validate_campaign_data(conn, campaign_data, existing=existing)

        set_clauses = []
        values = []
        for field, value in updates.items():
            if field == "type" and value is not None:
                value = value.value
            set_clauses.append(f"{field} = %s")
            values.append(value)
        values.append(campaign_id)

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE campaigns SET {', '.join(set_clauses)} WHERE id = %s "
                f"RETURNING {_CAMPAIGN_COLUMNS}",
                values
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Campaign not found")
            conn.commit()
            return _row_to_campaign(row)
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update campaign: {str(e)}")
    finally:
        pool.putconn(conn)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: str, request: Request):
    """Delete a campaign."""
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM campaigns WHERE id = %s RETURNING id", (campaign_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Campaign not found")
            conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete campaign: {str(e)}")
    finally:
        pool.putconn(conn)
