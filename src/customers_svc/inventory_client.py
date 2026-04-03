# @ai-rules:
# 1. [Cross-service]: All inventory operations go through HTTP, not direct DB access.
# 2. [Env]: INVENTORY_SERVICE_URL defaults to in-cluster DNS name.
# 3. [Timeout]: 5s timeout for inter-service calls.
"""HTTP client for cross-service calls to the Inventory backend."""

import os
import logging

import httpx

logger = logging.getLogger(__name__)

INVENTORY_URL = os.getenv("INVENTORY_SERVICE_URL", "http://darwin-store-inventory:8081")


class InventoryClient:
    """Thin HTTP client for cross-service calls to Inventory backend."""

    def __init__(self, base_url: str = INVENTORY_URL):
        self.base_url = base_url

    async def deduct_stock(self, product_id: str, quantity: int) -> dict:
        """POST /internal/stock-deduct -- atomic stock deduction. Returns price info."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{self.base_url}/internal/stock-deduct",
                json={"product_id": product_id, "quantity": quantity},
            )
            if resp.status_code != 200:
                detail = resp.json().get("detail", "Stock deduction failed")
                raise InventoryError(resp.status_code, detail)
            return resp.json()

    async def restore_stock(self, product_id: str, quantity: int) -> dict:
        """POST /internal/stock-restore -- restore stock on cancel/return."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{self.base_url}/internal/stock-restore",
                json={"product_id": product_id, "quantity": quantity},
            )
            if resp.status_code != 200:
                detail = resp.json().get("detail", "Stock restore failed")
                raise InventoryError(resp.status_code, detail)
            return resp.json()

    async def validate_coupon(self, code: str, cart_total: float) -> dict:
        """POST /coupons/validate -- validate coupon for order."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{self.base_url}/coupons/validate",
                json={"code": code, "cart_total": cart_total},
            )
            if resp.status_code != 200:
                detail = resp.json().get("detail", "Coupon validation failed")
                raise InventoryError(resp.status_code, detail)
            return resp.json()

    async def increment_coupon_usage(self, coupon_id: str) -> dict:
        """POST /internal/coupon-use -- atomic usage increment."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{self.base_url}/internal/coupon-use",
                json={"coupon_id": coupon_id},
            )
            if resp.status_code != 200:
                detail = resp.json().get("detail", "Coupon usage increment failed")
                raise InventoryError(resp.status_code, detail)
            return resp.json()

    async def get_product(self, product_id: str) -> dict:
        """GET /products/{id} -- read product details."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self.base_url}/products/{product_id}")
            if resp.status_code != 200:
                detail = resp.json().get("detail", "Product not found")
                raise InventoryError(resp.status_code, detail)
            return resp.json()


class InventoryError(Exception):
    """Error from inventory service call."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)
