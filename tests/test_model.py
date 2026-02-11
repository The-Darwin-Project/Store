import sys
import os
from pathlib import Path

# Add src to sys.path
src_path = Path(__file__).resolve().parent.parent / "src"
sys.path.append(str(src_path))

try:
    from app.models import Product, ProductCreate
    from pydantic import ValidationError
except ImportError as e:
    print(f"Failed to import: {e}")
    sys.exit(1)

def test_product_model_has_description():
    # Test field existence and default
    p = Product(
        id="123", 
        name="Test", 
        price=10.0, 
        stock=5, 
        sku="SKU123", 
        image_data=None, 
        # description not provided, should default to "" or None depending on definition, 
        # but the code says default=""
    )
    
    if hasattr(p, "description"):
        print("SUCCESS: Product model has 'description' field.")
        if p.description == "":
            print("SUCCESS: Product.description defaults to empty string.")
        else:
            print(f"FAILURE: Product.description default is '{p.description}', expected ''.")
    else:
        print("FAILURE: Product model missing 'description' field.")

    # Test ProductCreate
    pc = ProductCreate(
        name="Test",
        price=10.0,
        stock=5,
        sku="SKU123"
    )
    if hasattr(pc, "description"):
        print("SUCCESS: ProductCreate model has 'description' field.")
        if pc.description == "":
            print("SUCCESS: ProductCreate.description defaults to empty string.")
        else:
            print(f"FAILURE: ProductCreate.description default is '{pc.description}', expected ''.")
    else:
        print("FAILURE: ProductCreate model missing 'description' field.")

if __name__ == "__main__":
    test_product_model_has_description()
