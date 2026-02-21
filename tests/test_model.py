# Store/tests/test_model.py
# @ai-rules:
# 1. [Pattern]: Tests Pydantic model field existence and defaults. No DB, no HTTP.
# 2. [Constraint]: sys.path handled by conftest.py -- do NOT add manual path hacks.
# 3. [Gotcha]: Product.description defaults to "" (empty string), not None.

from app.models import Product, ProductCreate


def test_product_has_description_field():
    p = Product(
        id="123",
        name="Test",
        price=10.0,
        stock=5,
        sku="SKU123",
        image_data=None,
    )
    assert hasattr(p, "description"), "Product model missing 'description' field"
    assert p.description == "", f"Expected empty default, got '{p.description}'"


def test_product_create_has_description_field():
    pc = ProductCreate(
        name="Test",
        price=10.0,
        stock=5,
        sku="SKU123",
    )
    assert hasattr(pc, "description"), "ProductCreate model missing 'description' field"
    assert pc.description == "", f"Expected empty default, got '{pc.description}'"
