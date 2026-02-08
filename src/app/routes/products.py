# Store/src/app/routes/products.py
"""Product CRUD endpoints for Darwin Store."""

from fastapi import APIRouter, HTTPException
from typing import Optional

from ..models import Product, ProductCreate

router = APIRouter(prefix="/products", tags=["products"])

# In-memory product store for PoC (no actual Postgres connection yet)
_products: dict[str, Product] = {}


@router.get("", response_model=list[Product])
async def list_products() -> list[Product]:
    """List all products in the store."""
    return list(_products.values())


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str) -> Product:
    """Get a single product by ID."""
    if product_id not in _products:
        raise HTTPException(status_code=404, detail="Product not found")
    return _products[product_id]


@router.post("", response_model=Product, status_code=201)
async def create_product(product: ProductCreate) -> Product:
    """Create a new product."""
    new_product = Product(
        name=product.name,
        price=product.price,
        stock=product.stock,
        sku=product.sku
    )
    _products[new_product.id] = new_product
    return new_product


@router.put("/{product_id}", response_model=Product)
async def update_product(product_id: str, product: ProductCreate) -> Product:
    """Update an existing product."""
    if product_id not in _products:
        raise HTTPException(status_code=404, detail="Product not found")
    
    updated = Product(
        id=product_id,
        name=product.name,
        price=product.price,
        stock=product.stock,
        sku=product.sku
    )
    _products[product_id] = updated
    return updated


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: str) -> None:
    """Delete a product by ID."""
    if product_id not in _products:
        raise HTTPException(status_code=404, detail="Product not found")
    del _products[product_id]
