from datetime import datetime, timedelta
import pytest
from pydantic import ValidationError

try:
    from app.models import CouponCreate, DiscountType, CouponUpdate, Coupon, CouponValidationResult, OrderCreate
except ImportError:
    pytest.fail("Models not yet implemented")

def test_coupon_create_valid():
    coupon = CouponCreate(
        code="SAVE20",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=20.0,
        min_order_amount=50.0,
        max_uses=100
    )
    assert coupon.code == "SAVE20"
    assert coupon.discount_type == DiscountType.PERCENTAGE
    assert coupon.discount_value == 20.0
    assert coupon.min_order_amount == 50.0
    assert coupon.max_uses == 100

def test_coupon_create_invalid_discount():
    with pytest.raises(ValidationError):
        CouponCreate(
            code="SAVE20",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=0.0,  # Invalid: must be > 0
        )

def test_coupon_create_invalid_max_uses():
    with pytest.raises(ValidationError):
        CouponCreate(
            code="SAVE20",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=10.0,
            max_uses=-1  # Invalid: must be >= 0
        )

def test_coupon_default_values():
    coupon = Coupon(
        code="WELCOME",
        discount_type=DiscountType.FIXED,
        discount_value=10.0
    )
    assert coupon.id is not None
    assert coupon.min_order_amount == 0.0
    assert coupon.max_uses == 0
    assert coupon.current_uses == 0
    assert coupon.is_active is True

def test_order_create_coupon():
    try:
        from app.models import OrderItemCreate
        order = OrderCreate(
            items=[OrderItemCreate(product_id="prod1", quantity=2)],
            customer_id="cust1",
            coupon_code="WINTER20"
        )
        assert order.coupon_code == "WINTER20"
    except ImportError:
        pass
