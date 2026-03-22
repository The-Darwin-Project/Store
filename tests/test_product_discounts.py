# @ai-rules:
# 1. [Pattern]: Tests for product-level discount logic (effective_price, model validation).
# 2. [Constraint]: Uses model imports only -- no DB or TestClient needed for pure logic tests.
import pytest
from pydantic import ValidationError

from app.models import Product, ProductCreate, ProductUpdate, effective_price


class TestEffectivePrice:
    def test_no_discount(self):
        assert effective_price(99.99, None, None) == 99.99

    def test_sale_price_override(self):
        assert effective_price(99.99, 79.99, None) == 79.99

    def test_discount_percent(self):
        assert effective_price(50.00, None, 20) == 40.00

    def test_sale_price_takes_precedence(self):
        result = effective_price(100.00, 79.99, 30)
        assert result == 79.99

    def test_zero_discount_percent(self):
        assert effective_price(50.00, None, 0) == 50.00

    def test_hundred_percent_discount(self):
        assert effective_price(50.00, None, 100) == 0.00

    def test_rounding(self):
        result = effective_price(9.99, None, 33)
        assert result == 6.69

    def test_zero_sale_price(self):
        assert effective_price(50.00, 0.0, None) == 0.0


class TestProductModelsDiscount:
    def test_product_defaults(self):
        p = Product(name="Widget", price=10.0, sku="W1", stock=5)
        assert p.sale_price is None
        assert p.discount_percent is None

    def test_product_with_sale_price(self):
        p = Product(name="Widget", price=10.0, sku="W1", stock=5, sale_price=7.50)
        assert p.sale_price == 7.50

    def test_product_with_discount_percent(self):
        p = Product(name="Widget", price=10.0, sku="W1", stock=5, discount_percent=25)
        assert p.discount_percent == 25

    def test_product_create_with_discounts(self):
        pc = ProductCreate(name="W", price=10, sku="S1", stock=1, sale_price=8.0, discount_percent=15)
        assert pc.sale_price == 8.0
        assert pc.discount_percent == 15

    def test_product_create_defaults(self):
        pc = ProductCreate(name="W", price=10, sku="S1", stock=1)
        assert pc.sale_price is None
        assert pc.discount_percent is None

    def test_product_update_partial(self):
        pu = ProductUpdate(sale_price=5.0)
        provided = pu.model_dump(exclude_unset=True)
        assert "sale_price" in provided
        assert "discount_percent" not in provided

    def test_invalid_negative_sale_price(self):
        with pytest.raises(ValidationError):
            Product(name="W", price=10.0, sku="S1", stock=5, sale_price=-1)

    def test_invalid_discount_over_100(self):
        with pytest.raises(ValidationError):
            Product(name="W", price=10.0, sku="S1", stock=5, discount_percent=101)

    def test_invalid_negative_discount(self):
        with pytest.raises(ValidationError):
            Product(name="W", price=10.0, sku="S1", stock=5, discount_percent=-5)
